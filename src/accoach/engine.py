"""The headless coaching engine.

All the live logic — read telemetry, record laps, compare to the reference,
analyze corners, detect events, schedule and (optionally) speak cues — lives
here, decoupled from any UI. Drive it from a loop:

    engine = CoachEngine(voice=Voice())
    while True:
        state = engine.tick(time.monotonic())
        render(state)              # terminal, overlay, websocket — anything

The terminal coach, the websocket server and any future overlay all consume the
same :class:`EngineState`, so there's exactly one implementation of the coaching
behaviour. The reader and voice are injectable, which makes the engine testable
with scripted snapshots and no audio.
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .coaching import (
    BalanceDetector,
    BrakingDetector,
    CoachAnalyzer,
    Cue,
    CueScheduler,
    EventDetector,
    FuelEngineer,
    GearDetector,
    PressureAdvisor,
    SetupAdvisor,
    TyreTempAdvisor,
    Voice,
)
from .coaching.analyzer import corner_level
from .coaching.fuel import fuel_block
from .coaching.cue import Cue, CueCategory, gates_voice, theme_key, trigger_text
from .coaching.debrief import build_lap_debrief
from .coaching.diagnosis import build_lap_stats
from .coaching.atwheel import WheelWatch
from .coaching.corner_refs import POOL_SIZE, CornerBests
from .coaching.focus import FocusCoach, FocusKind, FocusReport
from .coaching.lapvalid import LapValidityCoach
from .coaching.pitcall import HoldCall, PitCall
from .i18n import cue_text, current_language
from .logging_setup import get_logger
from .comparison import DeltaState, LapComparator, Reference
from .engineer import DecisionKind, RaceEngineer, classify, engineer_for
from .engineer.fingerprint import PitWatch
from .engineer.session_log import SessionLog
from .recording import Lap, LapRecorder, find_reference_lap, laps_root, save_lap
from .recording.recorder import StartLineWatcher
from .recording.storage import reference_pool
from .telemetry import SharedMemoryReader, TelemetrySnapshot
from .telemetry.snapshot import ACStatus
from .telemetry.feed import TelemetryFeed
from .track import Corner, detect_corners

_log = get_logger("coach")

# When you're not on a representative flying lap — delta has ballooned because
# you're crawling, recovering from an off, or parked — only acute safety cues
# (lock-up, wheelspin, slides, fuel) are worth speaking. Technique and setup
# advice on a throw-away lap is noise (live validation 2026-06-26: the coach
# machine-gunned coasting/trail cues and even praised a +12 s disaster lap).
_GATE_DELTA_MS = 3000.0

# Only these are spoken on an abnormal lap. Note: under/oversteer cues are ACUTE
# (real-time faults) but NOT here — on a cold/recovery lap the car slides
# everywhere and naming it is the exact spam the gate exists to remove; a genuine
# lock-up or wheelspin still gets called.
_SAFETY_CATEGORIES = {
    CueCategory.LOCKED, CueCategory.WHEELSPIN, CueCategory.FUEL,
    # The pit calls pass every gate by construction. The gate's job is to stop
    # driving advice on a lap it can't apply to; these two are the opposite —
    # PIT_BRIEFING is spoken *because* the car is stopped in the box, which is
    # exactly the state `quiet == "pit"` describes, and gating it would make the
    # one cue that only makes sense there the one cue that never arrives.
    CueCategory.PIT_IN, CueCategory.PIT_APPROACH, CueCategory.PIT_BRIEFING,
    # Spesso il giro cade proprio quando il delta e' saltato: va detto lo stesso.
    CueCategory.LAP_INVALID,
}


def _focus_theme_key(report: FocusReport | None) -> str | None:
    """The English theme key of the active focus, or None if there isn't one.

    Deliberately not `report.focus.theme`: that one is translated for the driver
    ("frenata"), and comparing it against the scheduler's key would work in
    Italian and silently stop filtering in English.
    """
    if report is None or report.focus is None:
        return None
    return theme_key(report.focus.category)


def _gate_theme_key(report: FocusReport | None) -> str | None:
    """Il tema a cui restringere la voce: quello del focus, se lo sa dire.

    Non sempre coincide con :func:`_focus_theme_key`. Un focus sulla
    percorrenza o sulla linea resta un focus — pannello, verdetti, la sua
    curva — ma non chiude la voce: quei temi esistono solo come verdetto su una
    curva gia' persa, e sul resto della pista il filtro zittirebbe tutto in
    cambio di niente (vedi :func:`accoach.coaching.cue.gates_voice`). Il log
    del focus continua a scrivere il tema vero, con l'altra funzione.
    """
    key = _focus_theme_key(report)
    if key is None or not gates_voice(report.focus.category):
        return None
    return key


def _spoken_forms(cue: Cue, focus_theme: str | None, lang: str) -> tuple[str, str]:
    """What the ear hears and what the eye reads: (voice, screen).

    They are the same string until a focus is active, or until a cue carries a
    general sentence of its own (`Cue.voice`: the rule without the numbers, the
    screen keeps the value). With a focus the voice gets the trigger word and the
    screen keeps the whole sentence — the driver in a corner has room for three
    words, the debrief afterwards has room for the rest.

    In English the voice stays the translation of `message`: `Cue.voice` is
    Italian only, and the engine translates `message` before calling here.
    """
    general = cue.voice if (cue.voice and lang != "en") else cue.message
    if focus_theme is None:
        return general, cue.message
    trigger = trigger_text(cue.category, lang)
    if trigger is None:
        return general, cue.message
    return trigger, cue.message

# A spoken alert prefix for an engineer proposal, by confidence-tone × tag ×
# language. The change itself follows it — only the action, not the whole
# rationale with its symptom: the voice has room for eight words a sentence, the
# Engineer page keeps the rest. In italiano l'azione e' la frase scritta a mano
# senza click (`engineer/voice_levers.py`, «Ammorbidisci la barra antirollio
# anteriore»), detta come frase a se'; in inglese `ProposedChange.named`. The prefix tells the driver *whether* it needs
# the garage (BOX) or can be dialled from the wheel (AV). A medium-confidence
# proposal gets a tentative wording so the tone itself signals how much to trust
# it — the advice still reaches the ear, but the voice doesn't oversell a guess.
_ENG_VOICE_PREFIX = {
    "firm": {
        "BOX": {"it": "Ingegnere, rientra ai box.",
                "en": "Engineer here, box this lap."},
        "AV": {"it": "Ingegnere, cambia dal volante.",
               "en": "Engineer here, change it from the wheel."},
    },
    "tentative": {
        "BOX": {"it": "Ingegnere, se vuoi prova ai box.",
                "en": "Engineer here, maybe try this in the box."},
        "AV": {"it": "Ingegnere, se vuoi prova dal volante.",
               "en": "Engineer here, maybe try this from the wheel."},
    },
}

# Un ripristino porta la leva della modifica provata (`ProposedChange.reversed`
# la tiene per citarla fra virgolette): detta da sola, la voce direbbe al pilota
# di rifare proprio la modifica da togliere.
_ENG_VOICE_REVERT = {"it": "Riporta l'assetto com'era.",
                     "en": "Put the setup back as it was."}

# Un giro pulito che l'Ingegnere non conta solo perche' le gomme sono sotto i
# 75 °C di media. Il 25/10 un pilota lento ha fatto sei giri puliti a 65-70 °C
# e nessuno e' entrato nel conto: il coach diceva «gomme fredde», ma non che
# per questo l'assetto aspettava. Si dice una volta per sessione.
_ENG_VOICE_COLD = {"it": "Gomme ancora fredde. Questo giro non conta per l'assetto.",
                   "en": "Tyres still cold. This lap doesn't count for the setup."}
# La stessa situazione, quando il giro e' molto lontano dal riferimento: li' le
# gomme fredde sono la conseguenza del ritmo, e «spingi» e' il consiglio
# sbagliato per chi sta ancora imparando la pista. Al posto dell'altra frase,
# non in piu'.
_ENG_VOICE_SLOW = {"it": "Con questo ritmo le gomme restano fredde. "
                         "Prima prendi confidenza con la pista.",
                   "en": "At this pace the tyres stay cold. "
                         "Get to know the track first."}
# Quanto piu' lento del riferimento vale «molto lontano»: il 25/10 i giri del
# pilota alle prime armi erano dal 54 al 140 % sopra il riferimento, quelli di
# chi guida da mesi stanno sotto il 3 %.
_SLOW_FRAC = 0.10


#: «di 2 click», «1 click di»: il numero dei click dentro una leva dello schermo.
_CLICKS = (re.compile(r"\s+di\s+\d+\s+click\b"),
           re.compile(r"\b\d+\s+click\s+(?:di\s+)?"))


def _eng_voice_lever(change) -> str:
    """La leva come la dice la voce italiana: la frase scritta a mano
    (`engineer/voice_levers.py`), senza click.

    Se manca, la leva dello schermo senza il numero: l'italiano puo' venire
    zoppo e la frase non ha un WAV, quindi la dice la voce di Windows. Non
    deve succedere (lo impedisce `tests/test_voce_leve.py`); se succede, il
    log dice quale leva manca, che e' la riga da aggiungere alla tabella.
    """
    from .engineer.voice_levers import voice_lever
    phrase = voice_lever(change)
    if phrase is not None:
        return phrase
    atoms = ", ".join(f"{a.param}[{a.slot}]{a.delta_clicks:+d}"
                      for a in change.changes)
    _log.warning("ingegnere: leva senza frase a voce: %s", atoms)
    text = _voice_clean(change.named)
    for rx in _CLICKS:
        text = rx.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().rstrip(".") + "."


def _spoken_log_line(category, focus_theme: str | None,
                     voice_text: str, screen_text: str) -> str:
    """La riga che registra cosa il coach ha DETTO, e contro che filtro.

    Pura, e con la forma decisa qui, perche' e' l'unica prova che avremo di due
    domande che dal sedile non hanno risposta:

    * **prova 16** — in pista arrivano parole corte o frasi intere? Si legge da
      `voce=`, e il confronto con `schermo=` mostra cosa e' stato scritto e non
      detto, che e' esattamente il comportamento da verificare;
    * **prova 21** — i venti secondi fra due ripetizioni sono assillanti? E' una
      domanda sui *tempi*, e le marche temporali le mette il logger.

    Il 10/08 in pista tutt'e due sono rimaste indecidibili: il pilota stava
    frenando, e a memoria non si cronometra niente.
    """
    tema = focus_theme or "-"
    nome = getattr(category, "value", category)
    return f"detto | {nome:<12} | tema={tema:<10} | voce={voice_text!r} | schermo={screen_text!r}"


def _reference_token(reference) -> tuple | None:
    """Chi e' il giro di riferimento, in una forma confrontabile.

    Non l'oggetto: `_rebuild_reference` ne costruisce uno nuovo dopo ogni giro
    salvato, anche quando il giro sotto e' lo stesso, quindi l'identita'
    dell'oggetto direbbe «cambiato» a ogni giro. Il giro invece ha un'ora e un
    tempo, e due giri diversi non li condividono.
    """
    lap = getattr(reference, "lap", None)
    if lap is None:
        return None
    return (lap.recorded_utc, lap.lap_time_ms)


def _focus_log_line(report: FocusReport | None, *, counted: bool = True,
                    discarded: int = 0) -> str:
    """Il contesto senza cui le righe `detto |` non si interpretano.

    «Nessuna parola di trazione in cinque giri» significa una cosa se il focus
    era la trazione, e un'altra se non e' mai stato eletto.

    E «non eletto» sono a loro volta tre cose diverse, che portano a letture
    opposte della stessa riga `detto |`: *sto ancora guardando* (non ho ancora
    abbastanza giri), *sei pulito* (nessuna debolezza che ricorre), e *questo
    giro non l'ho nemmeno giudicato* (senza riferimento o senza curve il coach
    non lo vede). Il coach tace in tutti e tre, per tre motivi che non si
    somigliano.

    E ce n'e' un quarto, che finora si travestiva da primo: *questo giro non
    l'ho contato perche' non era pulito*. Il coach scarta i giri con
    un'escursione apposta — gonfiano la perdita di ogni curva e inventerebbero
    una debolezza — ma `observe` restituisce l'ultimo rapporto, quindi la riga
    usciva identica a quella del giro prima. Il 01/09 su 14 giri 6 erano sporchi,
    i due piu' veloci compresi: dieci righe «valuto 2/3» di fila, e nessun modo
    di sapere se il coach stava aspettando o era rotto. ``counted=False`` lo
    dice, e ``discarded`` dice quanti ne ha buttati — perche' un giro solo e'
    sfortuna, meta' dei giri e' la sessione.

    Quel numero e' misurato sulla **finestra**, non sulla sessione: sono i
    giri buttati da quando e' stato contato il piu' vecchio dei giri su cui il
    coach sta decidendo (vedi :attr:`FocusCoach.discarded`). E' la lettura che
    un numero accanto a `stato=assess` invita comunque a fare — dividerlo per i
    giri che il coach ha in mano — e per reggerla dev'essere lo stesso span.
    Il totale di sessione resta leggibile lo stesso: c'e' una riga per ogni
    giro scartato, e si contano.
    """
    focus = report.focus if report else None
    if focus is None:
        stato = report.kind.value if report else "non valutato"
        riga = f"focus | nessuno | stato={stato}"
    else:
        riga = (f"focus | {focus.name} | tema={_focus_theme_key(report)} "
                f"| base {focus.baseline_ms:.0f} ms")
    if counted:
        return riga
    # Il resto della riga descrive il giro *precedente*, che sotto un focus
    # aperto e' l'equivoco peggiore: nome, tema e progresso sembrano quelli di
    # questo giro. La coda dice che non lo sono.
    return f"{riga} | non contato: giro non valido | scartati={discarded}"


def _decision_sig(decision) -> tuple | None:
    """Identity of an engineer proposal, for "have we already handled this one".

    Same shape the spoken-once latch uses: the kind plus the rationale, which is
    what actually distinguishes two proposals to a driver. ``None`` for anything
    carrying no change (COLLECT / EVALUATING / …) so those can never match a real
    proposal's signature.
    """
    if decision is None or decision.change is None:
        return None
    return (decision.kind.value, decision.change.rationale or "")


def _voice_clean(text: str) -> str:
    """Trim a rationale for speech: drop the trailing click parenthetical (e.g.
    ' (−1)') that SAPI5 reads awkwardly — the direction word ('più morbida',
    'meno') already conveys it; the exact click count stays on screen."""
    import re  # noqa: PLC0415 (local: keeps the hot-path import list lean)
    return re.sub(r"\s*\([+\-−–]?\d+\)\s*$", "", text).strip()


@dataclass(slots=True)
class EngineState:
    """One tick of everything a frontend needs to show."""

    snapshot: TelemetrySnapshot
    delta: DeltaState | None
    spoken: Cue | None           # the cue spoken this tick, if any
    saved_laps: int
    reference_ms: int            # reference lap time, 0 if none
    history: list[str]           # recent spoken cue messages, newest last
    engineer: dict | None = None  # latest race-engineer decision (setup advice)
    focus: dict | None = None     # latest Focus/Lesson report (driver coaching)
    fuel: dict | None = None      # litres, pct, laps left (the tablet's third big number)
    # L'ultima curva chiusa: indice, nome, millisecondi persi, semaforo. Un
    # consuntivo muto — la voce resta invariata e arriva al giro dopo, che è
    # quando può ancora cambiare qualcosa. I due non si pestano i piedi: questo
    # è informazione, quello è un consiglio.
    corner: dict | None = None
    # Sei stato richiamato ai box e non sei ancora in corsia. Una condizione,
    # non un evento: il cue che la annuncia scatta una volta per giro, questa
    # resta vera in mezzo — ed è per questo che l'overlay può tenerla accesa.
    pit_due: bool = False
    # Why the coach is holding back, "" when it's coaching normally. Every gate
    # has to say so: a silent gate reads as a broken app (the driver's own words
    # after a calibration session were "I drove and nothing happened").
    quiet: str = ""              # "" | "pit" | "out_lap" | "no_reference" | "off_pace"
    # The game says this lap is already invalidated (ACC only; None on AC, where
    # the page ends before the flag). Not a gate: an invalidated lap is a free
    # lap, and everything but the stopwatch still applies. It only tells the
    # frontend to stop showing a delta that compares against a lap that won't
    # count.
    lap_invalid: bool = False


def _load_reference(car: str, track: str, laps_dir: Path | str,
                    road_temp: float | None = None,
                    grip: float | None = None,
                    compound: str | None = None) -> Reference | None:
    lap = find_reference_lap(car, track, laps_dir, road_temp, grip, compound)
    if lap is None:
        return None
    ref = Reference(lap)
    return ref if ref.usable else None


def _build_corner_bests(main: Reference, corners: list[Corner],
                        car: str, track: str, laps_dir: Path,
                        road_temp: float | None, grip: float | None,
                        compound: str | None) -> CornerBests:
    """Il gesto migliore di ogni curva, dal bacino. Gira sul thread del bacino.

    Il ``CornerBests`` nasce qui e qui riceve i giri del bacino; al tick passa
    finito, e da lì in poi lo tocca solo il tick (non è thread-safe). Auto,
    pista e condizioni sono quelle che hanno eletto ``main`` in
    `_load_reference`, così il bacino si rilassa come si è rilassato lui.
    """
    bests = CornerBests(main, corners)
    for other in reference_pool(car, track, laps_dir,
                                road_temp, grip, compound, POOL_SIZE):
        bests.offer(other)
    return bests


def _corner_labels(car: str, track: str, corners: list[Corner],
                   laps_dir: Path | str) -> dict[int, str]:
    """Nome di ogni **zona** dell'analyzer, nell'ordine in cui l'analyzer le indicizza.

    L'ordinamento è ripetuto qui apposta: `CoachAnalyzer.set_corners` ordina le
    zone per `entry_pos` e l'indice di zona è la posizione in quella lista, che
    non è per costruzione `Corner.index`. Chiamare `name_corners` sulla stessa
    lista ordinata toglie l'assunzione invece di fidarsene — e un nome sbagliato
    qui non è un dettaglio estetico: manda il pilota a lavorare sulla curva
    accanto.

    Best-effort come `_load_focus_state`: un catalogo illeggibile vale «nessun
    nome», mai un'eccezione che ferma un giro.
    """
    if not corners:
        return {}
    # La chiave è la stessa tupla di `set_corners`, non il solo `entry_pos`: le
    # due liste divergerebbero solo su un pareggio esatto fra float, ma è
    # esattamente il caso in cui questo docstring esiste per non far finire un
    # nome sulla curva accanto. Ordinare in due modi diversi «quasi uguali» è il
    # modo classico di pagarlo una volta sola, molto dopo.
    ordered = sorted(corners, key=lambda c: (c.entry_pos, c.exit_pos, c.apex_pos))
    try:
        from . import cornernames
        from .recording.catalog import LapCatalog
        from .recording.storage import _catalog_path
        from .trackdata import name_corners

        with LapCatalog(_catalog_path(Path(laps_dir))) as cat:
            learned = cat.load_corner_map(car, track)
        names = name_corners(track, ordered, current_language(), learned,
                             cornernames.for_track(track))
    except Exception:
        return {}
    return dict(enumerate(names))


def _name_the_corner(cue: Cue, text: str, corners, names: dict) -> str:
    """Sullo schermo «Veleggi» dice dove, perche' vale per ogni curva.

    Solo sullo schermo: a voce resta la frase registrata, e un WAV per ogni
    curva di ogni pista non c'e'. Fuori da una curva non si nomina niente.
    """
    if cue.category not in (CueCategory.COASTING, CueCategory.LAP_INVALID):
        return text
    for c in corners:
        if c.entry_pos <= cue.pos <= c.exit_pos and names.get(c.index):
            return f"{names[c.index]}. {text}"
    return text


class CoachEngine:
    """Stateful coaching engine; one :meth:`tick` per frame."""

    def __init__(
        self,
        reader: SharedMemoryReader | None = None,
        voice: Voice | None = None,
        num_segments: int = 24,
        laps_dir: Path | str | None = None,
        feed: TelemetryFeed | None = None,
        acquire_hz: float | None = None,
        engineer_voice: bool = True,
        setup_roots=None,
        logs_dir: Path | str | None = None,
    ) -> None:
        self.reader = reader if reader is not None else SharedMemoryReader()
        # Dove stanno i file di setup, per riconoscere quale e' in macchina:
        # le stesse radici dell'app web (`setup/web_api.py`), in sola lettura.
        # I test passano una cartella loro.
        from .setup.store import DEFAULT_ROOTS
        if setup_roots is None:
            setup_roots = DEFAULT_ROOTS
        elif isinstance(setup_roots, (str, Path)):
            setup_roots = (setup_roots,)
        self.setup_roots = tuple(Path(r) for r in setup_roots)
        self.voice = voice
        # Whether to speak the race engineer's proposals (the per-cue coaching
        # voice is governed by ``voice`` itself; this gates only the engineer).
        self.engineer_voice = engineer_voice
        self.laps_dir = Path(laps_dir) if laps_dir else laps_root()
        # Il registro della sessione: una riga per giro e per evento dei box,
        # per chi deve capire dopo cosa ha fatto l'Ingegnere. La cartella si
        # crea alla prima riga.
        # Solo se gli si dice dove: chi guida il gioco vero passa
        # `paths.logs_dir()`; la demo e i test no, e non scrivono nulla.
        self._session_log = SessionLog(logs_dir) if logs_dir else None
        self._setup_files: list[str] = []
        self.recorder = LapRecorder()   # used only on the legacy inline path

        # High-fidelity acquisition: a background thread reads + records at a
        # fixed rate, decoupled from this engine's tick rate. ``feed`` may be
        # injected (tests drive it manually); ``acquire_hz`` makes the engine
        # own one and run it. With neither, tick() reads+records inline (legacy).
        if feed is not None:
            self._feed: TelemetryFeed | None = feed
            self._owns_feed = False
        elif acquire_hz:
            self._feed = TelemetryFeed(self.reader, hz=acquire_hz, laps_dir=laps_dir)
            self._feed.start()
            self._owns_feed = True
        else:
            self._feed = None
            self._owns_feed = False
        self.analyzer = CoachAnalyzer(num_segments=num_segments)
        self.events = EventDetector()
        self.balance = BalanceDetector()
        self.braking = BrakingDetector()
        self.gears = GearDetector()
        self.fuel = FuelEngineer()
        self.lapvalid = LapValidityCoach()
        self.advisor = SetupAdvisor()
        self.pressure = PressureAdvisor()
        self.tyretemp = TyreTempAdvisor()
        self.pitcall = PitCall()
        # L'Ingegnere che aspetta la risposta sull'assetto (vedi coaching/pitcall.py).
        self.holdcall = HoldCall()
        # Watches the dials so an "al volo" change can finish by being *done*
        # rather than by being clicked on a web page (see coaching/atwheel.py).
        self.wheelwatch = WheelWatch()
        self.scheduler = CueScheduler()

        self._comparator: LapComparator | None = None
        self._reference: Reference | None = None
        self._corners: list[Corner] = []
        self._corner_names: dict[int, str] = {}
        self._key: tuple[str, str] = ("", "")
        self.saved_laps = 0
        self.history: list[str] = []
        # Out-lap tracking, mirroring LapRecorder's rule: a lap is "flying" only
        # once we've watched it open at the start/finish line. Kept here rather
        # than read off the recorder because that one lives on the feed thread.
        self._line = StartLineWatcher()
        self._flying_lap = False
        # Today's conditions, for the reference election. Read together when the
        # car or track changes, because they answer one question between them:
        # how much grip the track is giving *today*.
        self._road_temp: float | None = None
        self._grip: float | None = None
        self._compound: str | None = None
        # Whether to retire the braking countdown at mastered corners.
        from .config import load_config
        self._wean = load_config().overlay.wean

        # Race engineer: rebuilt per car/track; fed a per-lap diagnosis (LapStats)
        # at each completed lap, surfaces its latest decision in the payload.
        self._engineer: RaceEngineer | None = None
        self._engineer_decision = None
        # Signature of the last proposal spoken aloud, so a proposal that the
        # engine re-emits every lap (until the driver applies it) is announced
        # once, not on a loop. Reset when the engineer is rebuilt.
        self._engineer_spoken_sig: tuple | None = None
        # La frase delle gomme fredde e' gia' stata detta in questa sessione.
        self._cold_spoken = False
        # …and the proposal the driver has already written at the box, so the pit
        # calls go quiet for it (see _garage_change_pending).
        self._engineer_done_sig: tuple | None = None
        # …and the "al volo" proposal the dial watch is currently armed on.
        self._armed_sig: tuple | None = None

        # Focus/Lesson coach: the driver's twin of the engineer. Fed a per-lap
        # debrief (vs the reference), it picks one recurring weakness at a time and
        # coaches it. Rebuilt per car/track; needs a reference to produce debriefs.
        self._focus: FocusCoach | None = None
        self._focus_key: tuple[str, str] | None = None
        #: Auto+pista di cui l'Ingegnere sta tenendo la memoria su disco.
        self._engineer_key: tuple[str, str] | None = None
        self._focus_report: FocusReport | None = None
        #: Il riferimento (e le sue curve) contro cui il ciclo del focus sta
        #: misurando, tenuto fermo dal primo giro della finestra fino al
        #: verdetto. None solo prima che un ciclo cominci e subito dopo che uno
        #: si e' chiuso, cioe' quando il prossimo va pesato su oggi.
        #: Vedi `FocusCoach.observe` e `_observe_lap`.
        self._focus_ref: tuple | None = None

        # Commands from other threads (e.g. the server's POST /engineer/applied,
        # which runs on the asyncio loop while tick() runs in an executor) are
        # queued here and drained on the tick thread — never applied inline — so
        # they can't race _observe_lap, which also mutates the engineer.
        self._cmd_lock = threading.Lock()
        self._applied_pending = False
        # Il pilota ha detto ai box quale assetto ha caricato (POST
        # /engineer/base): scioglie la base tenuta da `_base_moved`.
        self._base_pending = False
        # …e i file che viaggiano con i due segnali (il corpo `{"path": ...}`),
        # None quando la pagina non lo manda.
        self._applied_path: str | None = None
        self._base_path: str | None = None

        # L'impronta dell'assetto ai box (engineer/fingerprint.py): chi guarda
        # la sosta frame per frame, e cosa ha riconosciuto per ultimo (il
        # blocco `loaded` del frame). Si azzera con l'Ingegnere.
        self.pitwatch = PitWatch()
        self._loaded: dict | None = None
        #: Il file che HONE si aspetta in macchina: l'ultimo arrivato da
        #: `/engineer/applied` o `/engineer/base` per questa auto e pista.
        self._expected_path: str | None = None
        #: L'ultimo file scritto da HONE (`/engineer/applied`): la risposta
        #: della pagina dice se il pilota ha caricato proprio quello.
        self._written_path: str | None = None
        #: HONE ha cambiato l'assetto in questa sosta (una scrittura ai box,
        #: una manopola al volo girata in corsia, la risposta della pagina):
        #: allora un cambio fra entrata e uscita non e' un cambio non chiesto.
        #: Si azzera a ogni uscita dai box.
        self._hone_touched = False
        #: Il gioco dell'Ingegnere di adesso: su Assetto Corsa l'impronta tace
        #: e le proposte non portano le manopole tenute.
        self._acc = False

        # Il gesto migliore di ogni curva (coaching/corner_refs.py). Il bacino
        # si carica fuori dal tick. Misurato il 03/11 sulla copia dell'archivio
        # (Monza, 720S): `load_lap` 6,5 ms a giro, 133 ms per 20 giri; il
        # bacino intero 118-273 ms col catalogo, più 10 ms di confronti. Ogni
        # giro sta sotto i 50 ms, la somma no: dentro un tick a 20 Hz sarebbero
        # da 2 a 5 frame saltati a ogni nuovo riferimento, e crescerebbero con
        # l'archivio. Un solo lavoratore, creato alla prima costruzione.
        self._pool: ThreadPoolExecutor | None = None
        #: La costruzione in volo e il riferimento per cui è partita.
        self._bests_future: Future | None = None
        self._bests_token: tuple | None = None
        #: I giri salvati mentre la costruzione era in volo: il bacino può non
        #: averli visti, e al passaggio di mano si offrono.
        self._bests_waiting: list[Lap] = []
        #: I gesti migliori consegnati all'analyzer; li tocca solo il tick.
        self._bests: CornerBests | None = None

    def _drop_corner_bests(self) -> None:
        """Il riferimento è cambiato: i gesti di prima misuravano altre zone."""
        self.analyzer.set_corner_refs(None)
        self._bests = None
        self._bests_waiting = []
        self._bests_token = None
        if self._bests_future is not None:
            self._bests_future.cancel()      # se è già partita, la butta il token
            self._bests_future = None

    def _start_corner_bests(self, car: str, track: str) -> None:
        """Parte la costruzione per il riferimento di adesso, se ha senso."""
        ref = self._reference
        if ref is None or ref.lap.source == "pro" or not self._corners:
            return                           # Decisione 5: spento
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1,
                                            thread_name_prefix="hone-bacino")
        self._bests_token = _reference_token(ref)
        # Le stesse curve date a `analyzer.set_corners`: le finestre del
        # CornerBests devono essere le zone dell'analyzer, non un altro calcolo.
        self._bests_future = self._pool.submit(
            _build_corner_bests, ref, self._corners, car, track, self.laps_dir,
            self._road_temp, self._grip, self._compound)

    def _take_corner_bests(self) -> None:
        """Nel tick: se la costruzione è finita, passa all'analyzer.

        Non aspetta mai. Una costruzione per un riferimento che non è più quello
        di adesso si butta; un errore del bacino lascia il principale e basta.
        """
        fut = self._bests_future
        if fut is None or not fut.done():
            return
        self._bests_future = None
        waiting, self._bests_waiting = self._bests_waiting, []
        if fut.cancelled():
            return
        if self._bests_token != _reference_token(self._reference):
            return
        try:
            bests = fut.result()
        except Exception:
            _log.warning("gesti migliori per curva non costruiti; resta il "
                         "riferimento principale", exc_info=True)
            return
        for lap in waiting:
            bests.offer(lap)
        self._bests = bests
        self.analyzer.set_corner_refs(bests)

    def _rebuild_reference(self, car: str, track: str) -> None:
        # Today's track temperature decides which past lap is a fair benchmark:
        # a personal best set on a rubbered-in evening track is the wrong target
        # for a cold morning, and every tenth in the debrief would be weather.
        #
        # Questa funzione gira dopo **ogni** giro salvato, per inseguire il
        # nuovo miglior giro, e quasi sempre scopre che il riferimento e' quello
        # di prima. In quel caso esce subito: e' solo un risparmio (niente curve
        # da ricalcolare, niente catalogo da aprire, a ogni giro) e non regge
        # nessuna proprieta' — quello che il coach deve ricordare da un giro
        # all'altro e' protetto altrove. Fino al 12/10 qui dentro si azzerava
        # anche il coach: vedi `_forget_session`, la meta' che qui non deve stare.
        reference = _load_reference(car, track, self.laps_dir,
                                    self._road_temp, self._grip,
                                    self._compound)
        if (reference is not None and self._reference is not None
                and _reference_token(reference) == _reference_token(self._reference)):
            return
        self._reference = reference
        self._comparator = LapComparator(self._reference) if self._reference else None
        corners = detect_corners(self._reference.lap.samples) if self._reference else []
        self._corners = corners
        self._corner_names = _corner_labels(car, track, corners, self.laps_dir)
        # Butta i consigli di curva solo se le zone sono cambiate davvero: sono
        # indicizzati per zona, e con un altro layout parlerebbero della curva
        # accanto.
        self.analyzer.set_corners(corners)
        self.analyzer.reset()
        # I gesti migliori di prima misuravano le zone del riferimento di
        # prima: si spengono subito, e i nuovi arrivano dal thread del bacino.
        self._drop_corner_bests()
        self._start_corner_bests(car, track)
        # Il comparatore nuovo non sa quali staccate il pilota ha gia' imparato.
        self._update_wean()

    def _forget_session(self) -> None:
        """Auto o pista nuove: quello che il coach sapeva riguardava altro.

        Sta fuori da `_rebuild_reference` perche' quella gira anche a ogni giro
        salvato sulla **stessa** auto e pista, e li' dimenticare e' il difetto:
        dal 28/06 al 12/10 un giro salvato svuotava i consigli di curva (detti
        zero volte su 24 dopo un giro salvato, 26 dopo un giro d'uscita),
        riportava a «primo traguardo» il conto della benzina — l'avviso non
        poteva arrivare mai — e azzerava i cooldown, cosi' le pressioni
        tornavano a ogni giro. Nessun modulo era rotto: lo era la chiamata.
        """
        self.advisor.reset()
        self.pressure.reset()
        self.tyretemp.reset()
        self.fuel.reset()
        self.lapvalid.reset()
        self.scheduler.reset()
        self._cold_spoken = False

    def acquisition_hz(self) -> float | None:
        """Measured acquisition rate when a background feed is running, else None."""
        return self._feed.measured_hz if self._feed is not None else None

    def _rel_setup(self, path) -> str | None:
        """Il percorso di un setup com'e' scritto nel registro: relativo alla
        radice dei setup, o il solo nome del file. Mai assoluto, cosi' la casa
        dell'utente non finisce nel registro."""
        if not path:
            return None
        try:
            p = Path(path)
            for root in self.setup_roots:
                for r in (root, root.resolve()):
                    try:
                        return p.relative_to(r).as_posix()
                    except ValueError:
                        continue
            return p.name
        except Exception:  # noqa: BLE001
            return None

    def _write_log(self, kind: str, **fields) -> None:
        if self._session_log is not None:
            self._session_log.write(kind, **fields)

    def _log_lap(self, lap: Lap, stats, decision) -> None:
        try:
            eng = self._engineer
            reading = eng._pressure_reading()
            self._write_log(
                "lap", car=lap.car_model, track=lap.track,
                lap_ms=stats.lap_time_ms, stable=stats.stable,
                warm=stats.warmed_up, stint=stats.stint,
                settling=stats.settling,
                decision=decision.kind.value if decision is not None else None,
                message=decision.message if decision is not None else None,
                progress=eng.progress(),
                reading=dict(reading.pressures_hot) if reading else None)
        except Exception:  # noqa: BLE001 - il registro non rompe un giro
            _log.debug("session log (lap) failed", exc_info=True)

    def _observe_lap(self, lap: Lap) -> None:
        """Diagnose a completed lap: feed the engineer (setup) and the Focus
        coach (driving). Both run on the reference that was the target *during*
        this lap — the rebuild to chase a new best happens after, in tick()."""
        if self._engineer is not None:
            # I nomi delle curve li ha gia' il motore, e sono gli stessi che il
            # pilota vede ovunque: passarli qui e' l'unico modo perche'
            # l'Ingegnere possa dire DOVE hai perso il giro senza ribattezzare
            # la curva per conto suo.
            stats = build_lap_stats(lap, self._corners or None,
                                    corner_names=self._corner_names)
            previous = self._engineer_decision
            self._engineer_decision = self._engineer.observe(stats)
            self._announce_engineer(self._engineer_decision)
            self._announce_cold_lap(stats, self._engineer_decision)
            # Un ripristino non ancora eseguito torna identico a ogni giro (vedi
            # `RaceEngineer.observe`), numeri compresi, perche' il pilota deve
            # poterli rileggere. Ma la prova e' stata una: nel registro ci va
            # una volta, o tre giri d'attesa diventerebbero tre bocciature e la
            # percentuale di riuscita — l'unico numero che puo' darci torto —
            # scenderebbe da sola.
            if self._engineer_decision is not previous:
                self._log_engineer_outcome(lap, self._engineer_decision)
            self._save_engineer_state()
            self._log_lap(lap, stats, self._engineer_decision)

        # The Focus coach needs a reference to know where time was lost.
        if self._focus is None or self._reference is None or not self._corners:
            # Fail open. Everything that could retire the theme lives inside the
            # branch below, so a lap we can't observe is a lap on which nobody
            # can park the focus or elect the next one — and `_rebuild_reference`
            # runs after every saved lap and may leave no reference (nothing in
            # today's condition band, or an unusable one) or no corners. Holding
            # the last theme there would filter every technique cue against a
            # theme that nothing can change again for the rest of the session:
            # not silence, which the driver would notice, but a coach quietly
            # wedged shut. If we can't confirm the focus, we speak.
            self.scheduler.set_focus(None)
        else:
            debrief = build_lap_debrief(lap, self._reference, self._corners)
            # Il focus conta anche i giri **sporchi**: resta fuori solo cio'
            # che non e' un giro intero. Deciso misurando, il 09/10, sui 95 giri
            # di Monza e Imola in archivio (26 sporchi): contandoli, il focus
            # insegna **le stesse curve nello stesso ordine** e ci arriva da 2 a
            # 6 giri prima (a Imola la Tosa al giro 17 invece che al 23).
            # Divergono solo sulla quarta elezione, dove le perdite sono 73 e
            # 101 ms, cioe' rumore. Regge perche' il focus misura **per curva**
            # su una mediana di sei giri: una curva sbagliata avvelena se' stessa
            # e la mediana assorbe.
            #
            # `valid` invece resta: un giro incompleto o di rientro ai box dura
            # il triplo e la sua perdita per curva non vuol dire niente.
            #
            # E NON si allinea con l'Ingegnere, che la sua regola se la calcola
            # da solo in `diagnosis.py` e tiene anche `clean`. Non e'
            # un'incoerenza, e' la misura: tutti e 26 i giri sporchi cadono
            # fuori dalla sua banda di decisione, e **sei su tredici sono piu'
            # veloci** della mediana pulita (fino a 2.8 s) perche' tagliare la
            # Variante fa guadagnare. Con quelli accetterebbe una modifica
            # d'assetto sulla forza di una chicane tagliata.
            stable = bool(lap.valid)
            before = (frozenset(self._focus.mastered), frozenset(self._focus.parked))
            # Il focus e' un esperimento, e un esperimento tiene fermo il
            # controllo: finche' un focus e' aperto giudica contro lo stesso
            # riferimento con cui ha misurato la base, anche se nel frattempo il
            # pilota ha fatto un personal best e il resto dell'app e' passato a
            # quello. Costa un secondo debrief per giro, e solo mentre un focus
            # e' aperto. Perche' non basti dichiararlo e' misurato sui 16 giri
            # del 14/08: contro il metro che rincorre, la Variante della Roggia
            # va 0 -> 280 ms; contro un metro fermo, 519 -> 190. Due risposte di
            # verso opposto alla stessa domanda.
            fref, fcorners = self._focus_ref or (self._reference, self._corners)
            focus_debrief = (debrief if fref is self._reference
                             else build_lap_debrief(lap, fref, fcorners))
            # Il consiglio seguito si rilegge a ogni giro, sulle curve con cui
            # il focus conta (`fcorners`, non quelle di adesso): il riferimento
            # cambia sotto la sessione, e il pilota puo' scegliere un consiglio
            # dal tablet mentre guida. Conta solo quando il focus sceglie, cioe'
            # quando non ce n'e' uno aperto: aprire il catalogo a fine giro,
            # mentre il registratore puo' scriverci, fa aspettare il tick fino
            # al busy_timeout, e durante un esercizio sarebbe per niente.
            if self._focus.focus is None:
                self._focus.preferred = self._followed_advice_corners(fcorners)
            self._focus_report = self._focus.observe(
                focus_debrief, stable=stable, reference=_reference_token(fref))
            # Il metro si tiene fermo per **tutto** il ciclo, non da quando il
            # focus ha un nome: la base si misura in fase di valutazione, quindi
            # e' li' che l'esperimento comincia. Fissarlo solo alla nomina —
            # com'era — lasciava scoperta proprio la finestra: il motore rifa' il
            # riferimento dopo ogni giro salvato, e a Imola il 23/08 quattro
            # personal best di fila (1:51 -> 1:47) l'hanno svuotata quattro volte.
            # Il focus non eleggeva **mentre il pilota migliorava**.
            #
            # Si libera su un verdetto: dato «migliorata» o «parcheggiata» il
            # ciclo e' chiuso e il prossimo si pesa su oggi.
            #
            # E si libera su CLEAN. Fino al 13/10 non lo faceva, per paura della
            # regressione del 23/08. Il costo si e' visto sul log del 24/09 a
            # Imola: il metro appuntato al primo giro della finestra era il giro
            # lento del pilota stesso, contro cui non si perde niente da
            # nessuno; il coach ha detto «nessun punto debole» e li' e'
            # rimasto, mentre contro il riferimento del momento la Rivazza
            # perdeva mezzo secondo. Un metro fermo per sempre non e' un
            # controllo, e' un orologio fermo.
            #
            # Non rifa' la regressione perche' la regressione stava nel muovere
            # il metro **mentre la finestra si riempie** (ASSESS), e quello
            # resta vietato: liberato su CLEAN, se il riferimento nel frattempo
            # e' cambiato il giro dopo svuota la finestra una volta, la
            # valutazione riparte, e per i tre giri che servono il metro e' di
            # nuovo appuntato. Chi migliora a ogni giro riceve un verdetto ogni
            # tre giri, non «valuto 0/3» per tutta la sessione. E se il
            # riferimento non si e' mosso, liberare non cambia niente: il giro
            # dopo si riappunta lo stesso metro e la finestra continua a
            # scorrere.
            if self._focus_report.kind in (FocusKind.IMPROVED, FocusKind.STUCK,
                                           FocusKind.CLEAN):
                self._focus_ref = None
            else:
                self._focus_ref = (fref, fcorners)
            # Tell the voice which theme the session is on. The FocusCoach has
            # elected one weakness at a time since it was written; until now
            # nobody downstream was listening.
            self.scheduler.set_focus(_gate_theme_key(self._focus_report))
            # Senza questa riga il log direbbe cosa e' stato detto ma non contro
            # che cosa: «nessuna parola di trazione» significa una cosa se il
            # focus e' la trazione e un'altra se non e' mai stato eletto.
            # `stable` e' lo stesso valore passato a `observe`, non una seconda
            # lettura: la riga dice del giro esattamente cio' che il coach ne ha
            # fatto, e le due non possono divergere.
            _log.info("%s", _focus_log_line(self._focus_report, counted=stable,
                                            discarded=self._focus.discarded))
            after = (frozenset(self._focus.mastered), frozenset(self._focus.parked))
            if after != before:
                self._save_focus_state()   # a corner just changed status; persist
            self._update_wean()

    def _focus_zone(self) -> int | None:
        """La zona dell'analyzer in cui cade la curva del focus, o None.

        Il focus conta le curve sul metro con cui le ha misurate (`_focus_ref`,
        tenuto fermo per tutto il ciclo), la voce sulle zone del riferimento di
        adesso: le due numerazioni possono non coincidere, quindi si passa per
        la posizione dell'apex, che e' un punto della pista e non un indice.

        None quando un focus non c'e', o quando la sua curva non cade in
        nessuna zona di adesso: meglio nessuna curva aperta che quella accanto.
        """
        rep = self._focus_report
        if rep is None or rep.focus is None:
            return None
        corners = self._focus_ref[1] if self._focus_ref else self._corners
        corner = next((c for c in corners if c.index == rep.focus.corner_index), None)
        if corner is None:
            return None
        zone = self.analyzer.zone_at(corner.apex_pos)
        return zone if zone >= 0 else None

    def _load_focus_state(self, car: str, track: str) -> tuple[set[int], set[int]]:
        """Last session's mastered/parked corners for this car+track, or empty.

        Best-effort: a missing or locked catalog just means "start fresh", never
        an error that stops coaching.
        """
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                return cat.load_focus_state(car, track)
        except Exception:
            return set(), set()

    def _followed_advice_corners(self, corners: list[Corner]) -> list[int]:
        """Le curve del consiglio in corso, tradotte nelle curve di ``corners``.

        Il consiglio le ha numerate sul riferimento dello storico, il focus le
        conta su quello del motore: le due numerazioni non coincidono, quindi si
        passa per la posizione dell'apex (`advice.corner_at`, la stessa regola
        della Pagella quando cambia il riferimento). Una curva il cui
        apex non cade in nessuna curva di adesso si scarta — meglio la scelta di
        sempre che la curva accanto — e cosi' una curva senza posizione (0.0: un
        obiettivo del vecchio piano, migrato).

        Best-effort come `_load_focus_state`: un catalogo illeggibile vale
        «nessun consiglio», e il focus sceglie da solo.
        """
        if self._focus_key is None or not corners:
            return []
        try:
            from .coaching.advice import ACTIVE, corner_at
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                advice = cat.load_advice(*self._focus_key)
            active = next((a for a in advice if a.get("status") == ACTIVE), None)
            apexes = [float(c.get("apex_pos") or 0.0)
                      for c in (active or {}).get("corners", [])]
        except Exception:
            return []
        out: list[int] = []
        for apex in apexes:
            hit = corner_at(apex, corners)
            if hit is not None and hit.index not in out:
                out.append(hit.index)
        return out

    def _save_focus_state(self) -> None:
        if self._focus is None or self._focus_key is None:
            return
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            car, track = self._focus_key
            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                cat.save_focus_state(car, track,
                                     self._focus.mastered, self._focus.parked)
        except Exception:
            pass   # persistence is a convenience; never let it break a lap

    def _load_engineer_state(self, car: str, track: str) -> dict | None:
        """La memoria dell'Ingegnere per questo auto+pista, o None.

        Best-effort come la gemella del focus: un catalogo mancante o bloccato
        vuol dire «riparti da zero», mai un errore che ferma la sessione.
        """
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                return cat.load_engineer_state(car, track)
        except Exception:
            return None

    def _save_engineer_state(self) -> None:
        if self._engineer is None or self._engineer_key is None:
            return
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            car, track = self._engineer_key
            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                cat.save_engineer_state(car, track, self._engineer.state())
        except Exception:
            pass   # persistence is a convenience; never let it break a lap

    def _watch_at_wheel(self, snap: TelemetrySnapshot) -> None:
        """Close the loop on an "al volo" proposal by watching the dial move.

        Without this an ``AV`` change could never be marked applied: the only
        caller of ``mark_applied`` was the setup-file writer, which exists only
        for ``BOX`` changes. So the engineer re-proposed the same click every
        lap and its phase never closed — two phases out of five on the GT3
        profile. See coaching/atwheel.py for why the answer is the car and not
        a button.
        """
        d = self._engineer_decision
        sig = _decision_sig(d)
        if (self._engineer is None or d is None or d.change is None
                or d.change.tag != "AV" or sig == self._engineer_done_sig):
            self.wheelwatch.disarm()
            self._armed_sig = None
            return
        if sig != self._armed_sig:
            self._armed_sig = sig
            atom = d.change.changes[0] if d.change.changes else None
            if atom is not None:
                self.wheelwatch.arm(atom.param, atom.delta_clicks, snap)
        if self.wheelwatch.update(snap):
            self._engineer.mark_applied()
            self._engineer_done_sig = sig
            # Girata ai box e' HONE che cambia l'assetto in questa sosta. In
            # pista no: la lettura d'entrata in corsia la contiene gia'.
            if snap.in_pit or snap.in_pit_lane:
                self._hone_touched = True
            # Fra «applicata» e il giro dopo ci sta un intero spegnimento, ed e'
            # esattamente li' che il 14/08 si e' perso un ciclo.
            self._save_engineer_state()

    def _garage_change_pending(self) -> bool:
        """Is there a setup change waiting that can only be made in the garage?

        Only ``BOX`` changes count. Something the driver can dial at the wheel is
        not a reason to give up a lap, and the engineer already separates the two
        — so this reads its answer rather than inventing a second rule.
        """
        d = self._engineer_decision
        if d is None or d.change is None or d.change.tag != "BOX":
            return False
        return _decision_sig(d) != self._engineer_done_sig

    def _load_pit_entry(self, track: str) -> list[float]:
        """This track's measured pit-entry positions; empty if never measured.

        Best-effort like the Focus memory next to it: no catalog means no
        approach call, never a failure.
        """
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                return cat.load_pit_entry(track)
        except Exception:
            return []

    def _save_pit_entry(self, track: str) -> None:
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                cat.save_pit_entry(track, self.pitcall.samples())
        except Exception:
            pass    # a convenience memory; never let it break a lap
        finally:
            # Cleared either way: a catalog we can't write must not make every
            # subsequent frame retry the write.
            self.pitcall.mark_entry_saved()

    def _update_wean(self) -> None:
        """Retire the braking countdown at corners the Focus coach has cleared.

        Reuses the coach's own "mastered" set rather than inventing a second
        notion of "you've got this corner", so the crutch retires exactly where
        the lesson plan says the weakness is gone. Guarded by config so a driver
        who wants every braking board forever can keep them.
        """
        if self._comparator is None:
            return
        if not (self._wean and self._focus is not None):
            self._comparator.set_muted_spans([])
            return
        spans = [(c.entry_pos, c.exit_pos) for c in self._corners
                 if c.index in self._focus.mastered]
        self._comparator.set_muted_spans(spans)

    def _announce_cold_lap(self, stats, decision) -> None:
        """Dice, una volta per sessione, che un giro pulito non conta per
        l'assetto perche' le gomme sono fredde.

        Solo quando il motivo e' quello e basta: un giro tagliato o non valido
        ha gia' il suo perche' sulla pagina, e qui si parlerebbe d'altro. E solo
        mentre l'Ingegnere sta contando (COLLECT, EVALUATING): una proposta o un
        ripristino hanno gia' la loro frase."""
        if (self._cold_spoken or not self.engineer_voice or self.voice is None
                or decision is None or stats is None):
            return
        if stats.unstable_why or stats.warmed_up:
            return
        if decision.kind not in (DecisionKind.COLLECT, DecisionKind.EVALUATING):
            return
        self._cold_spoken = True
        lang = current_language()
        ref_ms = self._reference.lap_time_ms if self._reference is not None else 0
        slow = (ref_ms > 0 and stats.lap_time_ms > 0
                and stats.lap_time_ms > ref_ms * (1.0 + _SLOW_FRAC))
        table = _ENG_VOICE_SLOW if slow else _ENG_VOICE_COLD
        self.voice.say(table.get(lang) or table["en"])

    def _announce_engineer(self, decision) -> None:
        """Speak a brief alert when the engineer wants a setup change.

        Fires on any decision that carries a change to write — a new PROPOSE or a
        REVERTED (restore). Only proposals are spoken (COLLECT / EVALUATING /
        ACCEPTED / PHASE_DONE / DONE carry no change), and each distinct proposal
        is announced once: the engine re-emits the same PROPOSE every lap until the
        driver applies it, but :attr:`_engineer_spoken_sig` suppresses the repeat.
        The detailed parameter + click count stays on the Engineer page; the voice
        gives just the headline so it doesn't step on live driving cues."""
        if (not self.engineer_voice or self.voice is None
                or decision is None or decision.change is None):
            return
        rationale = decision.change.rationale or ""
        sig = (decision.kind.value, rationale)
        if sig == self._engineer_spoken_sig:
            return
        self._engineer_spoken_sig = sig
        lang = current_language()
        # Medium-confidence proposals are voiced tentatively; a high-confidence
        # proposal or a revert (confidence "") gets the firm wording.
        tone = "tentative" if decision.confidence == "medium" else "firm"
        by_tag = _ENG_VOICE_PREFIX[tone]
        prefixes = by_tag.get(decision.change.tag) or by_tag["BOX"]
        prefix = prefixes.get(lang) or prefixes["en"]
        if decision.kind is DecisionKind.REVERTED:
            action = _ENG_VOICE_REVERT.get(lang) or _ENG_VOICE_REVERT["en"]
        elif lang == "it":
            from .engineer.voice_levers import voice_levers as _two
            action = ("" if _two(decision.change) is not None
                      else _eng_voice_lever(decision.change))
        else:
            action = _voice_clean(decision.change.named).rstrip(".") + "."
        if lang != "it":
            self.voice.say(f"{prefix} {action}")
            return
        # In italiano due frasi, due WAV in fila: il prefisso (quattro frasi)
        # e la leva (una tabella chiusa). Le frasi intere sarebbero il
        # prodotto delle due, otto volte i caratteri da registrare.
        self.voice.say(prefix)
        # Due assi in una sosta (le pressioni): le due frasi che esistono
        # gia', in fila, invece di una terza da registrare.
        from .engineer.voice_levers import voice_levers
        parts = (None if decision.kind is DecisionKind.REVERTED
                 else voice_levers(decision.change))
        for phrase in (parts or [action]):
            self.voice.say(phrase)

    def _log_engineer_outcome(self, lap, decision) -> None:
        """Write a finished test to the engineer's ledger.

        The one thing this app can prove that a setup generator can't is that a
        change was measured after it was made. That verdict used to exist for as
        long as the message was on screen; now it is kept, and after enough laps
        it answers the only question worth asking a setup tool — how many of its
        changes actually worked. Best-effort: a ledger that can't be written must
        never cost the driver a setup change (see engineer/ledger.py).
        """
        out = getattr(decision, "outcome", None)
        if out is None:
            return
        from datetime import datetime, timezone

        from .engineer.ledger import Record, append
        change = decision.change or out.tested
        # On a REVERTED the decision carries the *reversal*, so its clicks are
        # the opposite of the change that was actually tested.
        atom = change.changes[0] if (change and change.changes) else None
        delta = -atom.delta_clicks if (atom and not out.kept) else (
            atom.delta_clicks if atom else 0)
        try:
            append(Record(
                when_utc=datetime.now(timezone.utc).isoformat(),
                car=getattr(lap, "car_model", "") or "",
                track=getattr(lap, "track", "") or "",
                car_class=classify(getattr(lap, "car_model", "") or "").value,
                phase=change.phase_label if change else "",
                symptom=str(out.prediction.symptom) if out.prediction.symptom else "",
                param=atom.param if atom else "",
                slot=atom.slot if atom else None,
                delta_clicks=delta,
                remedy_rank=out.remedy_rank,
                kept=out.kept,
                laps=out.laps,
                score_before=out.prediction.score_now,
                score_after=out.score_after,
                time_before_ms=out.time_before_ms,
                time_after_ms=out.time_after_ms,
                fuel_before_l=out.fuel_before_l,
                fuel_after_l=out.fuel_after_l,
                time_confounded=out.time_confounded,
                temp_confounded=out.temp_confounded,
                road_temp_before=out.road_temp_before,
                road_temp_after=out.road_temp_after,
                side_effects={str(sym): d for sym, d in out.side_effects},
            ))
        except Exception:  # noqa: BLE001 - evidence for us, never a live failure
            pass

    def _engineer_block(self) -> dict | None:
        """The latest engineer decision, in the shape the setup UI consumes."""
        d = self._engineer_decision
        from .engineer.profiles._common import tr
        if d is None:
            # Prima del primo giro non c'e' ancora una decisione, ma la strada
            # (le fasi e il punto in cui si e') il pilota la vede da subito.
            # Blocco parziale: niente kind/message/change, e chi legge protegge
            # ogni campo con `eng && eng.x`.
            if self._engineer is None:
                return None
            ph = getattr(self._engineer, "phase", None)
            prog = getattr(self._engineer, "progress", None)
            return {"phase": {"key": ph.key, "label": tr(ph.label)} if ph else None,
                    "progress": prog() if callable(prog) else None,
                    # Il file in macchina si vede gia' alla prima sosta.
                    "loaded": self._loaded}
        sym = d.change.symptom if d.change else None
        corners = self._engineer.corners_for(sym) if self._engineer else []
        # Current phase (key + localized label) so the UI can tell the driver what
        # THIS phase wants — "phase X done → moving to Y" alone doesn't say what to
        # do next. After a PHASE_DONE the engine has already advanced, so this is
        # the phase now in progress. None once the setup is complete.
        from .engineer.core import symptom_words
        ph = self._engineer.phase if self._engineer else None
        phase = {"key": ph.key, "label": tr(ph.label)} if ph else None
        change = d.change.as_setup_payload() if d.change else None
        carry = self._carry_payload(d)
        if carry:
            change = change + carry
        return {
            "kind": d.kind.value,
            "message": d.message,
            # La parte del messaggio oltre il contatore, su raccolta e prova
            # (None altrove): la pagina, che i giri li conta nella strada,
            # mostra solo questa.
            "tail": d.tail,
            "phase": phase,
            # La strada: fasi, quella in corso, giri raccolti. Calcolata dal motore.
            "progress": self._engineer.progress() if self._engineer else None,
            # Su una proposta ai box anche le manopole al volo tenute: il file
            # nuovo e' una copia di quello di partenza, e senza queste voci
            # caricarlo annullerebbe in silenzio un TC +1 gia' tenuto. `carry`
            # le elenca a parte: si scrivono, ma non sono la modifica da
            # provare (budget e registro le hanno contate quando sono state
            # accettate).
            "change": change,
            "carry": carry,
            "rationale": d.change.rationale if d.change else None,
            "tag": d.change.tag if d.change else None,
            # Has this exact proposal already been written to the setup file?
            # The engineer keeps re-emitting it until the next completed lap, so
            # without this the page can't tell "still to do" from "done, go load
            # it" — and both the pit calls and the on-screen reminder need to.
            "applied": _decision_sig(d) == self._engineer_done_sig,
            # Is the engine watching the dial for this one? Answered here rather
            # than worked out again in the browser, so there is one place that
            # knows which parameters are readable on which game. False on an AV
            # proposal means the page has to offer a "done" button, or the change
            # can never be finished (AC reports every aid level as -1).
            "watched": self.wheelwatch.armed,
            "confidence": d.confidence,
            # Le gomme non hanno risposto come la modifica prevedeva: il tablet
            # e la pagina Ingegnere richiedono quale assetto hai caricato.
            "confirm_base": bool(getattr(d, "confirm_base", False)),
            # 1-based corner labels the proposal is anchored to ("Corners 7, 9").
            "corners": [i + 1 for i in corners],
            # Quale assetto e' in macchina, riconosciuto ai box (None prima
            # della prima sosta e su Assetto Corsa).
            "loaded": self._loaded,
            # The bar the change will be judged against, so the driver reads it
            # *before* the re-test laps instead of only hearing the verdict.
            "prediction": (None if d.prediction is None else {
                "text": d.prediction.text,
                "score_now": d.prediction.score_now,
                "score_below": d.prediction.score_below,
                "time_band_ms": round(d.prediction.time_band_ms, 1),
            }),
            # …and what actually happened, on the lap the verdict lands.
            "outcome": (None if d.outcome is None else {
                "kept": d.outcome.kept,
                "laps": d.outcome.laps,
                "score_before": d.outcome.prediction.score_now,
                "score_after": d.outcome.score_after,
                "time_before_ms": d.outcome.time_before_ms,
                "time_after_ms": d.outcome.time_after_ms,
                "fuel_before_l": d.outcome.fuel_before_l,
                "fuel_after_l": d.outcome.fuel_after_l,
                "time_confounded": d.outcome.time_confounded,
                # `words` e' come la pagina lo scrive; `symptom` resta la chiave.
                "side_effects": [{"symptom": str(s), "words": symptom_words(s),
                                  "delta": v}
                                 for s, v in d.outcome.side_effects],
            }),
        }

    def _focus_block(self) -> dict | None:
        """The latest Focus/Lesson report, in the shape a frontend consumes.

        ``focus.trigger`` is the word the voice will actually use, and it is
        filled only while the gate is really on that theme — so a frontend can
        show the driver the word without ever promising one the coach isn't
        going to say (the gate releases the theme on a lap it can't confirm).
        """
        r = self._focus_report
        if r is None:
            return None
        f = r.focus
        on_theme = self.scheduler.focus_theme is not None
        return {
            "kind": r.kind.value,
            "message": r.message,
            "drill": r.drill,
            "progress_ms": round(r.progress_ms, 1),
            "focus": None if f is None else {
                "corner_index": f.corner_index,
                "name": f.name,
                "theme": f.theme,
                "category": f.category.value,
                "trigger": trigger_text(f.category, current_language()) if on_theme else None,
                "baseline_ms": round(f.baseline_ms, 1),
            },
        }

    def _corner_block(self) -> dict | None:
        """L'ultima curva chiusa, nella forma che overlay e web consumano.

        `None` in tre casi, e sono tre assenze diverse che qui collassano nella
        stessa risposta: nessun riferimento (l'analyzer non produce carte senza
        delta), giro non rappresentativo (la carta è già stata buttata in
        `tick`), e prima della prima curva chiusa. Assente, non un trattino: un
        valore che non abbiamo non si finge.
        """
        card = self.analyzer.last_corner
        if card is None:
            return None
        if not self._corners:
            # Riferimento c'è ma `detect_corners` non ha trovato niente (giro
            # corto o strano, o senza coordinate): l'analyzer ripiega su 24
            # segmenti fissi e il numero resta misurato, ma il *nome* no —
            # «Curva 7» sarebbe il nome di un ventiquattresimo di pista. Un
            # valore che non abbiamo non si finge, nemmeno per metà riquadro.
            return None
        name = self._corner_names.get(card.index)
        if name is None:
            # Same fallback `name_corners` itself uses for an unnamed corner —
            # an empty track finds no curated table, so this is just "Corner N"
            # / "Curva N" in the active language. A hardcoded Italian string
            # here would be a second naming path: the one thing the plan's
            # global constraints forbid outright.
            from .trackdata import corner_name
            name = corner_name("", card.index, 0.0)
        return {
            "index": card.index,
            "name": name,
            "lost_ms": round(card.lost_ms, 1),
            "level": corner_level(card.lost_ms),
        }

    def mark_setup_applied(self, path: str | None = None) -> None:
        """Request that the engineer mark its proposal applied. Thread-safe: only
        sets a flag here; the actual mutation runs on the tick thread (drained in
        :meth:`tick`), so it can't race :meth:`_observe_lap`, which also touches
        the engineer.

        ``path`` e' il file scritto, quando la pagina lo manda: viaggia col
        segnale fino al tick, e da li' e' il file atteso in macchina."""
        with self._cmd_lock:
            self._applied_pending = True
            self._applied_path = path

    def mark_base_confirmed(self, path: str | None = None) -> None:
        """Il pilota ha risposto «quale assetto hai caricato» ai box. Come
        :meth:`mark_setup_applied`: qui solo il segnale (e il file scelto,
        se la pagina lo manda), il lavoro nel tick."""
        with self._cmd_lock:
            self._base_pending = True
            self._base_path = path

    # -- l'assetto in macchina, riconosciuto ai box ----------------------------
    def _setup_path(self, raw) -> str | None:
        """Il percorso mandato da una pagina, se e' un file sotto le radici dei
        setup; se no None, e il segnale vale come senza percorso.

        Come `_safe` nell'app web: il motore legge quel file, e una pagina non
        gli fa leggere altro. Prima si guarda il testo (assoluto, niente NUL,
        niente percorso di rete, dentro una radice), e solo allora si chiede
        al disco: `resolve` su un `\\\\altro-pc\\...` andrebbe in rete, e su un
        NUL puo' sollevare un ValueError che uscirebbe dal tick. La radice vale
        com'e' scritta o risolta: l'app web manda percorsi risolti (`_safe`).
        """
        import os
        if (not isinstance(raw, str) or not raw.strip() or "\x00" in raw
                or raw.startswith(("\\\\", "//"))):
            return None
        try:
            p = Path(raw)
            if not p.is_absolute():
                return None
            here = os.path.normcase(os.path.normpath(raw))
            for root in self.setup_roots:
                real = root.resolve()
                if not any(here.startswith(os.path.join(
                        os.path.normcase(os.path.normpath(str(r))), ""))
                        for r in (root, real)):
                    continue
                # …e i collegamenti: il file risolto resta dentro la radice.
                p.resolve().relative_to(real)
                return raw
        except (OSError, RuntimeError, ValueError):
            return None
        return None

    @staticmethod
    def _same_file(a: str, b: str) -> bool:
        import os
        try:
            return (os.path.normcase(str(Path(a).resolve()))
                    == os.path.normcase(str(Path(b).resolve())))
        except (OSError, RuntimeError, ValueError):
            return a == b

    def _carry_payload(self, d) -> list[dict] | None:
        """Le manopole al volo tenute, da scrivere insieme a una proposta ai
        box, nella forma di `as_setup_payload`; None se non ce ne sono.

        Solo su ACC, dove il file e' fatto di click e le chiavi delle manopole
        sono quelle del file (`tC1`, `abs`, `eCUMap`, `brakeBias`).
        """
        if (not self._acc or d.kind is not DecisionKind.PROPOSE
                or d.change is None or d.change.tag != "BOX"):
            return None
        clicks = getattr(self._engineer, "carry_clicks", None)
        if not callable(clicks):
            return None
        try:
            carry = clicks()
        except Exception:  # noqa: BLE001 - la proposta si mostra lo stesso
            return None
        return [{"param": k, "slot": None, "delta_clicks": v}
                for k, v in carry.items()] or None

    def _answer_base(self, raw_path):
        """La risposta della pagina a «quale assetto hai caricato», nel tick.

        Col file scelto: lo scarto del ripartitore si impara da li' (la
        lettura da fermo, o quella dell'uscita, contro i click del file piu'
        quelli girati al volante e tenuti), e l'Ingegnere sa se e' il file che
        HONE aveva scritto. Senza, come prima.
        """
        eng = self._engineer
        path = self._setup_path(raw_path)
        self._hone_touched = True
        if path is None:
            self._expected_path = None      # non sappiamo cosa ha caricato
            self._write_log("base", path=None, expected=None)
            return eng.base_confirmed()
        try:
            from .engineer.fingerprint import file_values
            w = self.pitwatch
            seen = next((r.bias for r in (w.live, w.exit)
                         if r is not None and r.bias >= 0), None)
            f = file_values(Path(path))
            if seen is not None and f is not None:
                clicks = f.bias_clicks + eng.carry_clicks().get("brakeBias", 0)
                eng.learn_bias(seen, clicks)
        except Exception:  # noqa: BLE001 - la taratura e' una comodita'
            _log.debug("bias calibration failed", exc_info=True)
        written = self._written_path
        expected = None if written is None else self._same_file(path, written)
        self._expected_path = path
        self._write_log("base", path=self._rel_setup(path),
                                expected=expected)
        return eng.base_confirmed(expected=expected)

    def _setup_report(self, event: str):
        """(SetupReport, blocco `loaded`) per l'evento dei box, o None.

        I file sono quelli della cartella di quest'auto e pista; il confronto
        e' col file piu' le manopole tenute (`carry_clicks`) e col ripartitore
        solo se tarato. Se cosi' non torna nessun file ma senza le manopole si'
        (``carry_lost``), il pilota ha ricaricato un file a mano.
        """
        from .engineer.core import SetupReport
        from .engineer.fingerprint import (
            changed, compare, describe, file_values, match,
        )
        from .setup import store

        w = self.pitwatch
        now = w.exit if event == "exit" else w.live
        if now is None or self._engineer_key is None:
            return None
        eng = self._engineer
        car, track = self._engineer_key
        files = [f for f in (file_values(p) for p in
                             store.find_setup_files(car, track, self.setup_roots))
                 if f is not None]
        self._setup_files = [f.name for f in files]
        carry = eng.carry_clicks()
        offset = eng.bias_offset
        m = match(now, files, carry=carry, bias_offset=offset)
        carry_lost = False
        if m.state == "unsaved" and carry:
            bare = match(now, files, carry={}, bias_offset=offset)
            if bare.state in ("match", "ambiguous"):
                m, carry, carry_lost = bare, {}, True
        lang = current_language()
        unsaved_diff = ""
        if m.state == "unsaved":
            best = next((f for f in files if f.name == m.best), None)
            if best is not None:
                certain, _psi = compare(now, best, carry=carry, bias_offset=offset)
                unsaved_diff = describe(certain, lang)
        expected = expected_ok = None
        expected_diff = psi_doubt = ""
        if self._expected_path:
            expected = Path(self._expected_path).stem
            want = file_values(Path(self._expected_path))
            if want is not None and -1 not in (now.tc, now.abs, now.emap):
                certain, psi = compare(now, want, carry=carry, bias_offset=offset)
                expected_ok = not certain
                expected_diff = describe(certain, lang)
                psi_doubt = describe(psi, lang)
        moved = ""
        if w.entry is not None and not self._hone_touched:
            moved = describe(changed(w.entry, now), lang)
        name = m.best if m.state == "match" else None
        report = SetupReport(
            state=m.state, name=name, probable=m.probable, changed=moved,
            expected=expected, expected_ok=expected_ok,
            expected_diff=expected_diff, psi_doubt=psi_doubt,
            unsaved_diff=unsaved_diff, carry_lost=carry_lost)
        loaded = {"state": m.state, "name": name, "names": list(m.names),
                  "probable": m.probable, "at": event,
                  "observed": now.to_dict()}
        return report, loaded

    def _watch_the_pits(self, snap: TelemetrySnapshot) -> None:
        """Ai box: quale assetto c'e' in macchina, detto all'Ingegnere.

        Dal vivo, fermo in piazzola, ogni volta che la lettura cambia; e
        all'uscita dalla corsia box. Il «live» puo' tornare piu' volte in una
        sosta lunga (le pressioni che scivolano su un decimo): la decisione
        cambia solo quando l'Ingegnere ne da' una nuova. Best-effort come la
        memoria: un file illeggibile o un errore qui non fermano mai un giro.
        """
        event = None
        try:
            event = self.pitwatch.update(snap)
            if (event is None or self._engineer is None
                    or not callable(getattr(self._engineer, "setup_seen", None))):
                return
            built = self._setup_report(event)
            if built is None:
                return
            report, self._loaded = built
            w = self.pitwatch
            now = w.exit if event == "exit" else w.live
            self._write_log(
                "setup", at=event, report=report.to_dict(),
                reading=now.to_dict() if now is not None else None,
                entry=w.entry.to_dict() if w.entry is not None else None,
                files=list(self._setup_files),
                expected=self._rel_setup(self._expected_path),
                # Quello letto da fermo, a gomme fredde o no: la soglia delle
                # gomme fredde (`COLD_TYRE_MARGIN_C`) si verifica da qui.
                box_psi=list(w.box_psi) if w.box_psi else None,
                box_core_c=w.box_core_c)
            decision = self._engineer.setup_seen(report, at_exit=event == "exit")
            if decision is not None:
                self._engineer_decision = decision
                self._save_engineer_state()
        except Exception:  # noqa: BLE001 - mai un giro perso per l'impronta
            _log.debug("setup fingerprint failed", exc_info=True)
        finally:
            if event == "exit":
                self._hone_touched = False      # la prossima sosta riparte

    def tick(self, now: float) -> EngineState:
        if self._feed is not None:
            # Acquisition + recording happen on the feed thread; here we just
            # read the latest frame and learn which laps it saved.
            snap = self._feed.latest()
            saved = self._feed.drain_saved()
        else:
            snap = self.reader.read()
            saved = []

        if snap.connected and (snap.car_model, snap.track) != self._key:
            self._key = (snap.car_model, snap.track)
            self._road_temp = snap.road_temp or None
            self._grip = snap.surface_grip or None
            self._compound = snap.tyre_compound or None
            self._reference = None      # un'altra auto o pista: mai «lo stesso giro»
            self._rebuild_reference(snap.car_model, snap.track)
            self._forget_session()
            # Auto o pista nuove: la carta della curva precedente parla di
            # un'altra sessione. `set_corners` butta da sé quando il layout
            # delle zone cambia, ma due auto sulla stessa pista hanno lo stesso
            # layout — lì solo il cambio di chiave sa che è un'altra cosa.
            self.analyzer.drop_last_corner()
            # Retune the class-dependent live thresholds (wheelspin, trail-brake
            # coaching) for this car.
            car_class = classify(snap.car_model)
            self.events.set_car_class(car_class)
            self.braking.set_car_class(car_class)
            self.balance.set_car_class(car_class)
            # …e le due finestre gomme, che fuori dalla GT3 non le conosciamo e
            # quindi lì si tace (vedi il blocco in coaching/tuning.py).
            self.pressure.set_car_class(car_class)
            self.tyretemp.set_car_class(car_class)
            # A new car/track is a new setup problem: start a fresh engineer —
            # ma non smemorato. Quello che torna e' il registro di cosa e' gia'
            # stato provato (fase, rimedi, click spesi), mai le misure: due
            # sessioni non si confrontano. Vedi `RaceEngineer.state`.
            # `is_acc` decide quanto vale un click nel file: su Assetto Corsa
            # lo dichiara l'auto, e dove non si legge l'Ingegnere non scrive.
            self._engineer = engineer_for(snap.car_model, snap.track,
                                          is_acc=snap.is_acc)
            self._engineer_key = (snap.car_model, snap.track)
            self._engineer.restore(
                self._load_engineer_state(snap.car_model, snap.track))
            self._engineer_decision = None
            self._engineer_spoken_sig = None
            self._engineer_done_sig = None
            self._armed_sig = None
            self.wheelwatch.disarm()
            # L'impronta nasce con l'Ingegnere: la sosta, il file riconosciuto
            # e quello atteso erano di un'altra auto o pista.
            self.pitwatch.reset()
            self._loaded = None
            self._expected_path = self._written_path = None
            self._hone_touched = False
            self._acc = bool(snap.is_acc)
            # The pit calls: fresh latches, and this track's measured pit entry
            # (see coaching/pitcall.py — it's learned, so a track never visited
            # simply has no approach call until the first time you come in).
            self.pitcall.reset()
            self.holdcall.reset()
            for pos in self._load_pit_entry(snap.track):
                self.pitcall.note_pit_entry(pos)
            self.pitcall.mark_entry_saved()
            # …and the lesson plan, restored from last session's memory for this
            # car+track so a mastered corner stays mastered across restarts.
            self._focus_key = (snap.car_model, snap.track)
            mastered, parked = self._load_focus_state(snap.car_model, snap.track)
            # …e le curve del consiglio che il pilota ha scelto di seguire nel
            # report, che prendono il posto della scelta del coach.
            self._focus = FocusCoach(
                mastered=mastered, parked=parked,
                preferred=self._followed_advice_corners(self._corners))
            self._focus_report = None
            self._focus_ref = None
            # Il comparatore e' nato qualche riga sopra, quando il focus era
            # ancora quello dell'auto di prima.
            self._update_wean()
            # A focus theme belongs to one car/track combination. Left set, it
            # would keep filtering technique advice on a theme that no longer
            # applies — possibly for the whole session, if this combination
            # never gets a reference to observe a lap against. NOT in
            # `CueScheduler.reset()`: that also runs from `_rebuild_reference`
            # after every completed lap on the SAME car/track (chasing a new
            # best), which would erase the theme `_observe_lap` just set a few
            # lines above.
            self.scheduler.set_focus(None)

        # Drain cross-thread commands on this (the engine's) thread.
        with self._cmd_lock:
            apply_setup, applied_path = self._applied_pending, self._applied_path
            self._applied_pending, self._applied_path = False, None
            base_answered, base_path = self._base_pending, self._base_path
            self._base_pending, self._base_path = False, None
        if base_answered and self._engineer is not None:
            # La decisione tenuta portava `confirm_base` a ogni frame: dopo la
            # risposta non deve piu', o le pagine richiederebbero da capo.
            freed = self._answer_base(base_path)
            if freed is not None:
                self._engineer_decision = freed
            self._save_engineer_state()
        if apply_setup and self._engineer is not None:
            # Quello che l'Ingegnere aveva in attesa, prima che `mark_applied`
            # lo prenda: decide se la sosta e' di HONE (sotto).
            pending = getattr(self._engineer, "_pending", None)
            self._engineer.mark_applied()
            # The change has been written: stop calling the driver in for it.
            # Without this the proposal — which the engineer keeps re-emitting
            # until the next completed lap — would call them back to the box on
            # the out-lap they just left it on.
            self._engineer_done_sig = _decision_sig(self._engineer_decision)
            # Da qui il file atteso in macchina e' quello scritto; senza un
            # percorso non lo sappiamo, e quello di prima non vale piu'.
            self._expected_path = self._written_path = self._setup_path(applied_path)
            self._write_log(
                "applied", path=self._rel_setup(self._written_path))
            # HONE ha cambiato l'assetto solo se ha preso una sua modifica: ai
            # box sempre, al volo solo se confermata in corsia («Fatto» in
            # pista e' gia' nella lettura d'entrata, come per le manopole).
            # Una scrittura senza niente in attesa sono le modifiche del pilota.
            if pending is not None and (getattr(pending, "tag", "") == "BOX"
                                        or snap.in_pit or snap.in_pit_lane):
                self._hone_touched = True
            # …e la modifica e' sulla macchina anche se il pilota chiude adesso.
            self._save_engineer_state()

        if self._feed is None:
            lap = self.recorder.update(snap)
            if lap is not None and lap.valid:
                save_lap(lap, self.laps_dir)
                saved = [lap]

        # Prima dei giri salvati: un giro di questo tick si offre ai gesti
        # appena arrivati, non si mette in coda per una costruzione già finita.
        self._take_corner_bests()

        for lap in saved:
            self.saved_laps += 1
            # Use the LAP's own car/track, not snap's: between completing the lap
            # and this tick the game may have disconnected (snap blank) or switched
            # car/track, which would diagnose the lap against the wrong reference.
            if lap.car_model and (lap.car_model, lap.track) != self._key:
                continue                                            # not this session
            self._observe_lap(lap)
            # Prima di `_rebuild_reference`, che quasi sempre esce subito perché
            # il principale è lo stesso: il giro può aver preso una curva, e il
            # bacino non si ricarica per un giro solo. Se invece diventa lui il
            # principale, `_rebuild_reference` butta tutto e riparte comunque.
            if self._bests is not None:
                if self._bests.offer(lap):
                    self.analyzer.set_corner_refs(self._bests)
            elif self._bests_future is not None:
                self._bests_waiting.append(lap)
            self._rebuild_reference(lap.car_model, lap.track)        # chase the new best
        if saved:
            # Dopo il riferimento, non dentro `_observe_lap`: la curva si dice
            # allo scheduler come zona dell'analyzer, e le zone le ha appena
            # rifatte `_rebuild_reference`.
            self.scheduler.set_focus_corner(self._focus_zone())

        self._watch_at_wheel(snap)
        # Dopo le manopole: una girata ai box in questo frame e' gia' una
        # modifica di HONE, e gia' nel confronto (`carry_clicks`).
        self._watch_the_pits(snap)

        delta = self._comparator.compare(snap) if self._comparator else None
        # On an abnormal lap (out of the pits, no comparison, or delta blown out)
        # gate everything except acute safety cues — detectors still run so their
        # state advances, we just don't speak advice that isn't worth hearing.
        self._track_flying_lap(snap)
        quiet = self._quiet_reason(snap, delta)

        # "No reference yet" is NOT an abnormal lap — it's a normal lap we can't
        # put a stopwatch on. Lumping it in with pit/out-lap/off-pace silenced
        # every detector that never needed a reference in the first place
        # (under/oversteer, coasting, trail braking, gears, tyres, pressures, all
        # of them absolute by construction), so the first session on a new car or
        # track produced lock-ups, fuel and nothing else. The analyzer is the only
        # consumer that needs the delta, and with no delta it emits nothing
        # anyway, so it needs no gate of its own here.
        unrepresentative = bool(quiet) and quiet != "no_reference"

        # Sul giro di uscita dai box le gomme sono fredde e pattinare e' normale:
        # l'08/11 «Pattini in uscita» dopo ogni uscita. Lo si toglie qui, dove si
        # sa che giro e': il rilevatore non ha idea di cosa sia un giro, e lo
        # scheduler riceverebbe una regola in piu' sul traguardo. Solo il
        # pattinamento: un bloccaggio, o la benzina, restano veri anche li'.
        on_out_lap = quiet in ("pit", "out_lap")

        def _submit(cues: list[Cue]) -> None:
            kept = cues if not unrepresentative else [
                c for c in cues if c.category in _SAFETY_CATEGORIES]
            if on_out_lap:
                kept = [c for c in kept if c.category is not CueCategory.WHEELSPIN]
            self.scheduler.submit_all(kept, now)

        # Corner advice (needs a reference) + acute events (don't) + the aid
        # advisor, which aggregates those same events into setup-knob suggestions.
        event_cues = self.events.update(snap, now)
        balance_cues = self.balance.update(snap, now)
        # Let the analyzer hold feed-forward advice the live data contradicts in
        # the same zone (e.g. don't say "carry more speed" where you understeered).
        self.analyzer.note_faults(event_cues + balance_cues)
        # Su un giro che non rappresenta niente l'analyzer non prende nemmeno
        # appunti: zittire la voce non bastava, perche' quello che metteva da
        # parte sul giro d'uscita lo leggeva sul primo giro lanciato.
        _submit(self.analyzer.update(snap, None if unrepresentative else delta))
        if unrepresentative:
            # Nascondere e basta la farebbe riapparire identica dopo il pit stop.
            self.analyzer.drop_last_corner()
        _submit(event_cues)
        _submit(balance_cues)
        _submit(self.braking.update(snap, now))
        _submit(self.gears.update(snap, now))
        _submit(self.advisor.update(snap, event_cues, now))
        # Le gomme le racconta una voce sola. Dove l'Ingegnere sa giudicare le
        # pressioni di quest'auto, il consiglio del coach («alza 0.7 psi a
        # freddo») tace: era un giudizio su un giro solo, senza chiamata ai box
        # e senza modifica pronta, e il 14/10 al Red Bull Ring diceva «troppo
        # basse» al primo giro lanciato mentre l'Ingegnere, giri dopo, le
        # trovava in finestra. Due voci con due numeri. Ora parla l'Ingegnere,
        # che chiama dentro e prepara il cambio sulla pagina. Il consigliere
        # continua a girare (tiene i suoi conti) ma non parla; dove l'Ingegnere
        # non sa (auto senza finestra), resta quello di prima.
        pressure_cues = self.pressure.update(snap, now)
        handles = getattr(self._engineer, "handles_pressures", None)
        if not (handles is not None and handles()):
            _submit(pressure_cues)
        _submit(self.tyretemp.update(snap, now))
        _submit(self.fuel.update(snap, now))
        _submit(self.lapvalid.update(snap, self._flying_lap, now, self._corners,
                                     self._reference))
        self.pitcall.set_pending(self._garage_change_pending())
        _submit(self.pitcall.update(snap, now))
        # L'attesa di `confirm_base` non porta una modifica, quindi la
        # chiamata sopra non la vede, e `_announce_engineer` nemmeno: senza
        # questa chi guida a voce non saprebbe mai che l'Ingegnere aspetta.
        d = self._engineer_decision
        _submit(self.holdcall.update(
            snap, self.engineer_voice and d is not None
            and bool(getattr(d, "confirm_base", False))))
        if self.pitcall.entry_dirty and snap.track:
            self._save_pit_entry(snap.track)
        spoken = self.scheduler.poll(now)
        if spoken is not None and spoken.category is CueCategory.PIT_BRIEFING:
            # Latch on the *spoken*, not on the emitted. The scheduler is allowed
            # to drop a cue, and this one used to be emitted once in the life of
            # a setup change — so a drop left the driver sitting in the garage
            # with nothing said and no second chance.
            self.pitcall.mark_briefed()
        if spoken is not None:
            # Cues are authored in Italian (so the neural WAVs match); render them
            # in the active language for both the voice and the on-screen text.
            spoken.message = cue_text(spoken.message)
            voice_text, screen_text = _spoken_forms(
                spoken, self.scheduler.focus_theme, current_language())
            screen_text = _name_the_corner(spoken, screen_text, self._corners,
                                           self._corner_names)
            spoken.message = screen_text
            # La traccia di cio' che il coach ha DETTO, con accanto il tema che
            # stava filtrando. Esiste perche' il 10/08, in pista, due prove sono
            # rimaste indecidibili: se in pista arrivino parole o frasi (prova
            # 16) e se i 20 secondi di ripetizione siano assillanti (prova 21).
            # Nessuna delle due si risponde a memoria — la 21 e' una domanda sui
            # tempi, e il pilota stava frenando. Qui, e non dentro `Voice.say`,
            # perche' solo qui si sanno anche la categoria e il tema attivo:
            # senza quelli il log direbbe cosa e' uscito ma non se il filtro
            # avesse ragione di farlo uscire.
            _log.info("%s", _spoken_log_line(spoken.category,
                                             self.scheduler.focus_theme,
                                             voice_text, screen_text))
            if self.voice is not None:
                self.voice.say(voice_text)
            self.history.append(spoken.message)
            del self.history[:-20]

        return EngineState(
            snapshot=snap,
            delta=delta,
            spoken=spoken,
            saved_laps=self.saved_laps,
            reference_ms=self._reference.lap_time_ms if self._reference else 0,
            history=list(self.history),
            engineer=self._engineer_block(),
            focus=self._focus_block(),
            fuel=fuel_block(self.fuel, snap),
            corner=self._corner_block(),
            pit_due=self.pitcall.calling,
            quiet=quiet,
            # Only on a lap that actually started at the line: on ACC the flag is
            # 0 for the whole out-lap too, and answering "invalidated" there would
            # be technically true and useless — the out-lap has its own message.
            lap_invalid=self._flying_lap and snap.lap_valid is False,
        )

    def _track_flying_lap(self, s: TelemetrySnapshot) -> None:
        """Am I on a lap that started at the line, or still on the way out?

        Exactly the recorder's rule, via the shared :func:`crossed_start_line`.
        This used to trust the lap counter alone, with a comment claiming that was
        the one signal holding on both titles — measurement says otherwise, and on
        ACC the counter skips the out-lap crossing, so the coach stayed silent
        through the whole first flying lap after every pit exit. The driver saw
        "out lap" on the overlay while setting a genuine time.
        """
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit or s.in_pit_lane:
            self._line.reset()
            self._flying_lap = False
            return
        if self._line.crossed(s.lap_position, s.completed_laps):
            # Set on the crossing frame itself, not the next tick: the tyre-temp
            # and pressure advisors emit exactly here, and they're the one thing
            # an out-lap is good for.
            self._flying_lap = True
            # Ogni frase di tecnica si puo' ridire una volta: il giro e' questo.
            self.scheduler.new_lap()
            self.lapvalid.new_lap()
            self.holdcall.new_lap()

    def _quiet_reason(self, s: TelemetrySnapshot, delta: DeltaState | None) -> str:
        """Why the coach is holding back this tick, "" if it isn't.

        Ordered most-specific first, because they overlap: an out-lap also has no
        usable delta, and saying "no reference yet" there would be a lie.
        """
        if s.in_pit or s.in_pit_lane:
            return "pit"
        if not self._flying_lap:
            return "out_lap"
        if delta is None:
            return "no_reference"
        if abs(delta.delta_ms) > _GATE_DELTA_MS:
            return "off_pace"
        return ""

    def close(self) -> None:
        # Senza aspettare: una costruzione in volo finisce da sé, chi è in coda
        # non parte. Il bacino è un vantaggio, non vale l'attesa di chi chiude.
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
        if self.voice is not None:
            self.voice.close()
        # Stop the feed before closing the reader it polls.
        if self._feed is not None and self._owns_feed:
            self._feed.stop()
        self.reader.close()
