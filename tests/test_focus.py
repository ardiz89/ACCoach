"""The Focus/Lesson layer — the driver's twin of the race engineer.

It runs over per-lap debriefs (where you lost time vs the reference), picks the
single recurring weakness and coaches it: assess → brief → drill → improved/stuck.
These tests drive it with hand-built debriefs (cheap, exact) and then check the
engine wires a real debrief→focus path into the payload.
"""
import pytest

from accoach import config
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.focus import (
    FocusCoach,
    FocusKind,
    FocusReport,
    format_focus,
)
from accoach.engine import CoachEngine
from accoach.comparison.reference import Reference
from accoach.track import detect_corners

import synth


@pytest.fixture
def it_lang(tmp_path, monkeypatch):
    """Switch the app language to Italian, resetting the config cache after."""
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


def _loss(index: int, ms: float, category: CueCategory = CueCategory.BRAKE_LATER,
          cause: str = "") -> CornerLoss:
    return CornerLoss(
        index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4, lost_ms=ms,
        category=category, message="m", detail="d",
        fix="Ritarda la staccata.", cause=cause)


def _debrief(*losses: CornerLoss, lap_ms: int = 101000, ref_ms: int = 100000) -> LapDebrief:
    return LapDebrief("ferrari_488_gt3", "monza", lap_ms, ref_ms, losses=list(losses))


def _feed(coach: FocusCoach, debrief: LapDebrief, times: int, *, stable: bool = True):
    report = None
    for _ in range(times):
        report = coach.observe(debrief, stable=stable)
    return report


# --- weakness selection ----------------------------------------------------

def test_assess_until_min_laps():
    coach = FocusCoach()
    r1 = coach.observe(_debrief(_loss(0, 300)))
    r2 = coach.observe(_debrief(_loss(0, 300)))
    assert r1.kind is FocusKind.ASSESS and r2.kind is FocusKind.ASSESS


def test_brief_on_recurring_loss():
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 300)), 3)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 0
    assert report.focus.theme == "braking"             # BRAKE_LATER → braking
    assert report.drill                                # a concrete instruction
    assert "0.30 s" in report.message                  # measured baseline


def test_picks_worst_recurring_not_a_one_off():
    """A single huge loss in c1 must not beat a recurring loss in c0."""
    coach = FocusCoach()
    coach.observe(_debrief(_loss(0, 300)))
    coach.observe(_debrief(_loss(0, 300), _loss(1, 900)))   # c1 spikes once
    report = coach.observe(_debrief(_loss(0, 300)))
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 0                   # recurring beats one-off


def test_baseline_uses_full_window_denominator():
    # A corner that's a loss in only some laps must get a baseline measured over
    # the WHOLE window (good laps = 0), the same denominator the drill uses — else
    # IMPROVED would fire without real progress.
    coach = FocusCoach()
    coach.observe(_debrief())                      # good
    coach.observe(_debrief())                      # good
    coach.observe(_debrief(_loss(0, 300)))         # loss, not yet recurring
    r = coach.observe(_debrief(_loss(0, 300)))     # 2/4 -> systematic -> BRIEF
    assert r.kind is FocusKind.BRIEF
    assert r.focus.baseline_ms == 150.0            # median([0,0,300,300]), not 300


def test_no_focus_when_losses_insignificant():
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 50)), 3)         # below the threshold
    assert report.kind is FocusKind.CLEAN


# --- the drill → verdict loop ----------------------------------------------

def test_focus_improved_promotes_and_praises():
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300)), 3)                 # BRIEF on c0 (baseline 300)
    report = _feed(coach, _debrief(_loss(0, 50)), 3)         # then nail it
    assert report.kind is FocusKind.IMPROVED
    assert 0 in coach.mastered
    assert coach.focus is None                               # ready for the next one
    assert "0.30 s" in report.message and "0.05 s" in report.message  # measured praise


def test_focus_stuck_is_parked():
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300, cause="L'auto sottosterza in ingresso.")), 3)
    report = _feed(coach, _debrief(_loss(0, 300)), 6)        # never improves
    assert report.kind is FocusKind.STUCK
    assert 0 in coach.parked
    assert coach.focus is None
    assert "setup" in report.message.lower()                # hints it may be the car


def test_next_focus_after_promotion():
    coach = FocusCoach()
    # c0 is worse; coach it, solve it, then c1 should become the focus.
    base = _debrief(_loss(0, 300), _loss(1, 200))
    _feed(coach, base, 3)                                    # BRIEF on c0
    _feed(coach, _debrief(_loss(0, 40), _loss(1, 200)), 3)   # solve c0 (IMPROVED)
    report = _feed(coach, _debrief(_loss(0, 40), _loss(1, 200)), 1)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 1                   # moved on to the next


# --- robustness ------------------------------------------------------------

def test_unstable_lap_does_not_move_the_plan():
    coach = FocusCoach()
    coach.observe(_debrief(_loss(0, 300)))
    coach.observe(_debrief(_loss(0, 300)))
    before = len(coach.window)
    report = coach.observe(_debrief(_loss(0, 9000)), stable=False)   # an off
    assert report.kind is FocusKind.ASSESS                  # last report stands
    assert len(coach.window) == before                      # excursion ignored


def test_brief_theme_and_message_are_italian(it_lang):
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 300)), 3)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.theme == "frenata"             # BRAKE_LATER → frenata (IT)
    assert "Il nuovo focus" in report.message
    assert "Lavoriamo sulla frenata" in report.message
    assert "0,30 s" in report.message                  # la virgola decimale


def test_stuck_message_is_italian(it_lang):
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300, cause="L'auto sottosterza in ingresso.")), 3)
    report = _feed(coach, _debrief(_loss(0, 300)), 6)
    assert report.kind is FocusKind.STUCK
    assert "metto da parte" in report.message.lower()
    assert "dipendere dall'assetto" in report.message.lower()
    assert "L'auto sottosterza in ingresso." in report.message


def test_format_focus_is_a_line():
    r = FocusReport(FocusKind.CLEAN, "Guida costante.")
    assert "Guida costante." in format_focus(r)


@pytest.mark.parametrize("kind", list(FocusKind))
def test_format_focus_has_no_emoji(kind):
    """Il coach da terminale apriva ogni riga con 🎯 ✅ ⏸ ✨: le emoji sono
    fuori da ogni testo di HONE, e la frase dice già cos'è successo."""
    from tono import _EMOJI
    line = format_focus(FocusReport(kind, "Guida costante."))
    assert not _EMOJI.search(line), line
    assert "Guida costante." in line


def test_the_terminal_coach_writes_no_emoji():
    """Lo stesso per i pannelli del coach da terminale (voce/testo, focus, stato)."""
    from pathlib import Path
    from tono import _EMOJI
    src = (Path(__file__).resolve().parents[1] / "src" / "accoach"
           / "coach_app.py").read_text(encoding="utf-8")
    found = sorted(set(_EMOJI.findall(src)))
    assert not found, f"emoji in coach_app.py: {found}"


# --- engine wiring (real debrief → focus → payload) ------------------------

def test_engine_focus_block_from_real_debriefs(tmp_path):
    class _Dummy:
        def read(self): ...
        def close(self): ...

    eng = CoachEngine(reader=_Dummy(), laps_dir=tmp_path)
    ref_lap = synth.build_lap(n=300, clean=True)
    eng._reference = Reference(ref_lap)
    eng._corners = detect_corners(ref_lap.samples)
    eng._focus = FocusCoach()

    # Three clean laps that lose time in corner 0 → a recurring weakness.
    slow = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)
    for _ in range(3):
        eng._observe_lap(slow)

    block = eng._focus_block()
    assert block is not None
    assert block["kind"] in ("brief", "drill", "assess")
    if block["kind"] == "brief":
        assert block["focus"]["theme"]
    eng.close()


# --- un focus, un solo metro ----------------------------------------------
#
# Il motore rifa' il riferimento a ogni personal best, quindi la perdita a una
# curva e' misurata contro un metro che si muove. Misurato sui 16 giri veri del
# 14/08 (3 cambi di riferimento), le due letture della stessa curva **cambiano
# verso**, non solo entita':
#
#     Variante della Roggia   metro che rincorre  0 -> 280 ms
#                             metro fisso       519 -> 190 ms
#
# Nei primi giri il riferimento e' il giro lento del pilota, quindi non si perde
# niente contro nessuno e una base misurata li' nasce piccola; poi il
# riferimento accelera e la stessa curva "peggiora" mentre il pilota migliora.
# Cosi' com'era, «0.49 -> 0.00» non era una misura di quanto sei migliorato.

def test_a_new_reference_makes_the_focus_start_measuring_again():
    """La finestra e' fatta di misure contro un metro: cambiato il metro, quelle
    misure non si mediano piu' con le nuove. Si ricomincia a guardare — che e'
    quello che il coach dice gia' quando non ha abbastanza giri."""
    fc = FocusCoach(min_laps=3)
    for _ in range(2):
        fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    assert len(fc.window) == 2
    r = fc.observe(_debrief(_loss(0, 500)), reference="giro-B")
    assert r.kind is FocusKind.ASSESS
    assert len(fc.window) == 1


def test_the_same_reference_does_not_reset_anything():
    fc = FocusCoach(min_laps=3)
    for _ in range(4):
        fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    assert len(fc.window) == 4


def test_without_a_reference_token_nothing_changes():
    """Chi non lo passa si comporta esattamente come prima: un metro che non si
    dichiara e' un metro che si assume fermo."""
    fc = FocusCoach(min_laps=3)
    for _ in range(4):
        fc.observe(_debrief(_loss(0, 500)))
    assert len(fc.window) == 4


def test_a_reference_that_moves_under_an_elected_focus_drops_it():
    """Non dovrebbe succedere — il motore congela il riferimento finche' un
    focus e' aperto — ma se succede il verdetto non e' piu' difendibile, e un
    verdetto indifendibile non si da'."""
    fc = FocusCoach(min_laps=3)
    for _ in range(4):
        fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    assert fc.focus is not None
    fc.observe(_debrief(_loss(0, 500)), reference="giro-B")
    assert fc.focus is None


def test_the_engine_holds_the_reference_still_under_an_open_focus(tmp_path):
    """Il pezzo che il coach da solo non puo' provare: che il metro stia fermo.

    Il motore rifa' il riferimento dopo ogni giro salvato, quindi senza questo
    un personal best a meta' esercizio spazzerebbe via la base del focus e il
    verdetto — che e' esattamente la cosa che il pilota aspetta."""
    from accoach.telemetry.snapshot import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    ref_a = synth.build_lap()
    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    eng._reference = Reference(ref_a)
    eng._corners = detect_corners(ref_a.samples)
    for _ in range(4):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
    assert eng._focus.focus is not None, "il fixture deve eleggere un focus"
    frozen = eng._focus_ref
    assert frozen is not None

    # Personal best a meta' esercizio: il resto dell'app passa al giro nuovo.
    ref_b = synth.build_lap(slow_corner=1, amt=10)
    eng._reference = Reference(ref_b)
    eng._corners = detect_corners(ref_b.samples)
    eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))

    assert eng._focus.focus is not None, "il focus non deve cadere col riferimento"
    # Il metro, non la scatola che lo contiene: la tupla si ricostruisce a ogni
    # giro (e' l'atto di ri-appuntare quello che si e' appena usato), quindi
    # quello che deve stare fermo e' il riferimento dentro, e le sue curve.
    assert eng._focus_ref[0] is frozen[0], "e il metro deve essere ancora quello"
    assert eng._focus_ref[1] is frozen[1], "con le curve con cui era stato letto"
    eng.close()


def test_the_engine_holds_the_reference_still_while_it_is_still_assessing(tmp_path):
    """La regressione del 23/08, a Imola: il focus non elegge se il pilota migliora.

    Il congelamento del metro c'era gia' ma partiva **troppo tardi** — solo dopo
    che un focus era stato eletto. In fase di valutazione il metro restava quello
    vivo, che `_rebuild_reference` rifa' dopo ogni giro salvato per inseguire il
    nuovo migliore: 1:51 -> 1:49 -> 1:48 -> 1:47 sono quattro metri diversi,
    quindi la finestra si svuotava quattro volte e non arrivava mai ai tre giri
    che servono per eleggere. Cioe' il focus si spegneva **proprio mentre il
    pilota migliora**, che e' lo scopo di una sessione di prove.

    A Brands Hatch era passato inosservato solo perche' li' c'erano stati quattro
    giri senza migliorare, e la finestra aveva fatto in tempo a riempirsi.
    """
    from accoach.telemetry.snapshot import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    ref = synth.build_lap()
    eng._reference = Reference(ref)
    eng._corners = detect_corners(ref.samples)

    for i in range(4):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
        # Personal best: il resto dell'app passa al giro nuovo, come fa il motore
        # dopo ogni giro salvato. Ogni ricostruzione e' un metro diverso.
        # I passi da 5 sono quello che serve perche' i quattro giri abbiano
        # davvero quattro tempi diversi: sotto quel passo `synth.build_lap`
        # arrotonda allo stesso `lap_time_ms` e il motore vedrebbe un metro solo
        # (misurato: amt 4, 6 e 8 danno tutti 100089).
        better = synth.build_lap(slow_corner=1, amt=5 * (i + 1))
        eng._reference = Reference(better)
        eng._corners = detect_corners(better.samples)

    assert eng._focus.focus is not None, (
        "quattro giri puliti con la stessa perdita devono eleggere un focus, "
        "anche se il pilota ha migliorato a ogni giro")
    eng.close()


def test_a_closed_focus_lets_the_reference_go(tmp_path):
    """Il metro sta fermo per la durata di un ciclo, non per sempre.

    Dato un verdetto (migliorata o parcheggiata) il ciclo e' finito: il prossimo
    si pesa su oggi, non sul giro con cui misuravamo mezz'ora fa.
    """
    from accoach.telemetry.snapshot import TelemetrySnapshot
    from accoach.coaching.focus import FocusKind

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    ref = synth.build_lap()
    eng._reference = Reference(ref)
    eng._corners = detect_corners(ref.samples)

    kinds = []
    for _ in range(12):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
        kinds.append(eng._focus_report.kind)
        if eng._focus_report.kind in (FocusKind.IMPROVED, FocusKind.STUCK):
            break

    assert kinds[-1] in (FocusKind.IMPROVED, FocusKind.STUCK), (
        f"il fixture deve arrivare a un verdetto, non a {kinds}")
    assert eng._focus_ref is None, "dato il verdetto, il metro si libera"
    eng.close()


def _motore_fermo(tmp_path):
    from accoach.telemetry.snapshot import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._focus = FocusCoach(min_laps=3)
    return eng


def _metti_riferimento(eng, lap):
    eng._reference = Reference(lap)
    eng._corners = detect_corners(lap.samples)


def test_no_recurring_weakness_against_a_stale_reference_is_measured_again(tmp_path):
    """Il 24/09 a Imola: «nessun punto debole», e la Rivazza perdeva mezzo secondo.

    Il metro si appunta al primo giro della finestra. A inizio sessione quel
    giro e' il giro lento del pilota stesso, e contro se' stessi non si perde
    niente: il verdetto e' CLEAN. Finche' CLEAN non liberava il metro, li' si
    restava per tutta la sessione — il riferimento del resto dell'app andava
    avanti, il focus continuava a misurare contro un'ora prima.

    Qui: il pilota gira uguale al suo riferimento lento (niente da dire), poi il
    riferimento diventa un giro che alla prima curva va 30 km/h piu' forte. Lui
    continua a girare come prima. Deve sentirselo dire.
    """
    from accoach.coaching.focus import FocusKind

    eng = _motore_fermo(tmp_path)
    lento = synth.build_lap(slow_corner=0, amt=30)
    _metti_riferimento(eng, lento)
    for _ in range(3):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
    assert eng._focus_report.kind is FocusKind.CLEAN, "il fixture parte da CLEAN"

    _metti_riferimento(eng, synth.build_lap())      # il nuovo migliore
    kinds = []
    for _ in range(5):
        eng._observe_lap(synth.build_lap(slow_corner=0, amt=30))
        kinds.append(eng._focus_report.kind.value)

    assert eng._focus.focus is not None, (
        f"contro il riferimento di oggi la curva perde: serve un focus, non {kinds}")
    assert eng._focus.focus.corner_index == 0
    eng.close()


def test_no_recurring_weakness_keeps_the_window_when_the_reference_stood_still(tmp_path):
    """Liberare su CLEAN non deve costare giri a chi non ha cambiato niente:
    stesso riferimento, stessa finestra, che continua a scorrere."""
    from accoach.coaching.focus import FocusKind

    eng = _motore_fermo(tmp_path)
    _metti_riferimento(eng, synth.build_lap())
    for _ in range(5):
        eng._observe_lap(synth.build_lap())

    assert eng._focus_report.kind is FocusKind.CLEAN
    assert len(eng._focus.window) == 5, "nessun giro e' stato buttato"
    eng.close()


def test_a_driver_who_improves_every_lap_still_gets_a_verdict(tmp_path):
    """La trappola gemella della regressione del 23/08, che e' il motivo per cui
    CLEAN non liberava: se il metro si muovesse a ogni giro la finestra non
    arriverebbe mai a tre e il coach resterebbe a «valuto 0/3».

    Liberato su CLEAN, il metro si muove **una volta per verdetto**: mentre la
    finestra si riempie resta appuntato. Quindi anche con un riferimento nuovo a
    ogni giro la valutazione arriva in fondo, ogni tre giri.
    """
    from accoach.coaching.focus import FocusKind

    eng = _motore_fermo(tmp_path)
    _metti_riferimento(eng, synth.build_lap())
    kinds = []
    for i in range(9):
        eng._observe_lap(synth.build_lap())
        kinds.append(eng._focus_report.kind)
        # un metro diverso a ogni giro (passi da 5: sotto, `build_lap`
        # arrotonda allo stesso tempo e il motore vedrebbe un metro solo)
        _metti_riferimento(eng, synth.build_lap(slow_corner=1, amt=5 * (i + 1)))

    assert kinds.count(FocusKind.CLEAN) >= 3, (
        f"in nove giri devono arrivare tre verdetti, non {[k.value for k in kinds]}")
    eng.close()


# --- i giri scartati si contano, e si contano sulla finestra ----------------
#
# Il coach scarta i giri non puliti (un'escursione gonfia la perdita di OGNI
# curva e inventerebbe una debolezza) e finora lo faceva in silenzio. Il 01/09,
# su 14 giri 6 erano sporchi — i due piu' veloci compresi — e il focus e' rimasto
# in `assess` per tutta la sessione senza che nessuno potesse dire perche'.
#
# Il conto esiste solo per essere letto, e chi lo legge lo divide per i giri che
# il coach ha in mano: deve percio' misurare lo STESSO span della finestra. La
# prima versione contava di sessione mentre la finestra scorreva in silenzio
# (`self.window[-_WINDOW:]`): su 60 giri alternati stampava «scartati=30» accanto
# a una finestra di 6, e i 20 giri buttati prima che la finestra cominciasse si
# trascinavano dietro per sempre. Non era un difetto di comportamento — il conto
# non entra in nessuna decisione — era un numero che mentiva a chi lo leggeva.
#
# Quali giri contano non cambia: qui si conta soltanto.

def _scarti_veri(fc: FocusCoach, dati) -> int:
    """L'oracolo: quanti sporchi sono passati DOPO il giro piu' vecchio che il
    coach ha ancora in finestra.

    Ricavato dalla sequenza davvero somministrata e da `fc.window`, non dalla
    formula del contatore: se domani la formula si stacca di nuovo dalla
    finestra, questo numero resta quello giusto e il confronto cade.
    """
    if not fc.window:
        return sum(1 for _, pulito in dati if not pulito)
    primo = next(i for i, (d, _) in enumerate(dati) if d is fc.window[0])
    return sum(1 for _, pulito in dati[primo + 1:] if not pulito)


def test_un_giro_non_pulito_si_conta_fra_gli_scartati():
    fc = FocusCoach(min_laps=3)
    fc.observe(_debrief(_loss(0, 300)))
    assert fc.discarded == 0
    fc.observe(_debrief(_loss(0, 9000)), stable=False)
    fc.observe(_debrief(_loss(0, 9000)), stable=False)
    assert fc.discarded == 2
    assert len(fc.window) == 1, "e restano scartati davvero"


def test_su_sessanta_giri_alternati_il_conto_e_quello_della_finestra():
    """Lo scenario che ha smascherato la prima versione: 30 contro 6.

    Il confronto non e' con un numero atteso a mano ma con la finestra vera:
    l'oracolo va a vedere qual e' il giro piu' vecchio che il coach ha ancora, e
    conta gli sporchi da li' in poi.
    """
    fc = FocusCoach(min_laps=3)
    dati = []
    for i in range(60):
        pulito = (i % 2 == 0)
        d = _debrief(_loss(0, 300))
        dati.append((d, pulito))
        fc.observe(d, stable=pulito)
    assert len(fc.window) == 6
    assert fc.discarded == _scarti_veri(fc, dati)
    assert fc.discarded != 30, "il conto e' tornato a essere quello di sessione"


def test_gli_scarti_di_prima_della_finestra_non_la_seguono():
    """Venti giri buttati, poi sei puliti: quei venti non dicono piu' niente su
    cio' che il coach ha in mano, e restarci attaccati e' l'unico modo che il
    numero ha di mentire senza sembrare sbagliato."""
    fc = FocusCoach(min_laps=3)
    dati = []

    def _giro(pulito: bool):
        d = _debrief(_loss(0, 300))
        dati.append((d, pulito))
        fc.observe(d, stable=pulito)

    for _ in range(20):
        _giro(False)
    assert fc.discarded == 20, "finestra vuota: non c'e' niente da cui contare"
    for _ in range(6):
        _giro(True)
    _giro(False)
    assert fc.discarded == _scarti_veri(fc, dati)
    assert fc.discarded == 1


def test_gli_scarti_della_valutazione_non_seguono_dentro_il_ciclo():
    """Il caso che attraversa il BRIEF.

    Sette giri buttati mentre valutavo non sono sette giri buttati
    sull'esercizio che sto assegnando adesso: la riga li mostrerebbe accanto a
    nome, tema e perdita di un focus appena aperto.
    """
    fc = FocusCoach(min_laps=3)
    dati = []
    for _ in range(7):
        d = _debrief(_loss(0, 9000))
        dati.append((d, False))
        fc.observe(d, stable=False)
    report = None
    for _ in range(3):
        d = _debrief(_loss(0, 300))
        dati.append((d, True))
        report = fc.observe(d)
    assert report.kind is FocusKind.BRIEF
    d = _debrief(_loss(0, 9000))
    dati.append((d, False))
    fc.observe(d, stable=False)
    assert fc.discarded == _scarti_veri(fc, dati)
    assert fc.discarded == 1


def test_un_verdetto_non_azzera_il_conto_perche_non_azzera_la_finestra():
    """Il conto non e' un contatore che qualcuno deve ricordarsi di azzerare al
    momento giusto: e' una lettura della finestra, e la finestra un verdetto non
    la tocca. Il giro sporco di meta' esercizio e' ancora dentro lo span dei sei
    giri su cui il prossimo focus verra' scelto, quindi si vede ancora."""
    fc = FocusCoach(min_laps=3)
    dati = []

    def _giro(pulito: bool, ms: float):
        d = _debrief(_loss(0, ms))
        dati.append((d, pulito))
        return fc.observe(d, stable=pulito)

    for _ in range(3):
        report = _giro(True, 300)
    assert report.kind is FocusKind.BRIEF
    _giro(False, 9000)
    for _ in range(3):
        report = _giro(True, 20)
    assert report.kind is FocusKind.IMPROVED
    assert fc.discarded == _scarti_veri(fc, dati) == 1


def test_e_se_ne_va_quando_la_finestra_gli_scorre_oltre():
    """L'altra faccia: il giro sporco sparisce dal conto quando la finestra lo
    supera, non quando un verdetto lo dichiara chiuso."""
    fc = FocusCoach(min_laps=3)
    dati = []

    def _giro(pulito: bool, ms: float):
        d = _debrief(_loss(0, ms))
        dati.append((d, pulito))
        return fc.observe(d, stable=pulito)

    for _ in range(3):
        _giro(True, 300)                    # BRIEF
    _giro(False, 9000)
    for _ in range(6):
        report = _giro(True, 300)           # STUCK
    assert report.kind is FocusKind.STUCK
    assert fc.discarded == _scarti_veri(fc, dati) == 0


def test_su_pulito_il_conto_non_riparte():
    """CLEAN non e' un verdetto ed e' uno stato che si ripete a ogni giro: se il
    conto ripartisse li', chi gira sporco meta' delle volte leggerebbe sempre
    «scartati=1». Ora non puo' per costruzione — non c'e' nessun azzeramento da
    piazzare nel posto sbagliato — e questa prova lo tiene fermo."""
    fc = FocusCoach(min_laps=3)
    for _ in range(3):
        fc.observe(_debrief())                         # niente da eleggere
    assert fc._last.kind is FocusKind.CLEAN
    fc.observe(_debrief(), stable=False)
    fc.observe(_debrief())
    assert fc._last.kind is FocusKind.CLEAN
    fc.observe(_debrief(), stable=False)
    assert fc.discarded == 2


def test_un_metro_nuovo_si_porta_via_anche_il_conto():
    """Gli scartati descrivono una finestra, e quella finestra non c'e' piu'."""
    fc = FocusCoach(min_laps=3)
    fc.observe(_debrief(_loss(0, 500)), reference="giro-A")
    fc.observe(_debrief(_loss(0, 9000)), stable=False, reference="giro-A")
    assert fc.discarded == 1
    fc.observe(_debrief(_loss(0, 500)), reference="giro-B")
    assert len(fc.window) == 1
    assert fc.discarded == 0
