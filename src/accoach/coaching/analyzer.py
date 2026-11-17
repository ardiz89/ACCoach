"""Turn the live delta into coaching cues, corner by corner.

The track is divided into **zones** — the real corners detected from the
reference lap (see :mod:`accoach.track`), or equal fixed segments as a fallback
when no corners are available. As you drive, :class:`CoachAnalyzer` accumulates a
paired comparison of your channels vs the reference's (both available each frame
from :class:`~accoach.comparison.DeltaState`). When you leave a zone in which you
lost meaningful time, it works out the most likely cause and emits one
:class:`Cue`. On the straights between corners it stays silent.

Why per-zone, not per-instant: instant-by-instant nagging is noisy and badly
timed. Judging a whole corner once you've left it gives a stable signal ("you
lost 0.2s through there, and the cause was X") that's worth speaking.

Feed-forward timing
-------------------
A real coach doesn't tell you about a corner *after* you've left it — that's
nagging about the past. So a loss cue isn't spoken at the corner exit where it's
computed; instead it's remembered as that corner's advice and spoken on the
**approach to the same corner on the next lap**, where it can still change what
you do. When you then take the corner well, the advice is cleared — the coach
stops repeating a fixed mistake. (Acute events like lock-ups are immediate and
handled separately in :mod:`accoach.coaching.events`.)

Cause attribution is deliberately conservative — it only blames a channel when
the difference is clearly outside noise, and otherwise falls back to a plain
"you're losing time here". Better silent than wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from ..comparison import DeltaState
from ..recording.lap import BRAKE_ON
from ..telemetry.snapshot import TelemetrySnapshot
from ..track import Corner
from .cue import Cue, CueCategory
from .diagnosis import _APEX_HALF

if TYPE_CHECKING:
    from ..comparison.reference import ReferencePoint
    from .corner_refs import CornerBests, CornerRef

# Tuning. Thresholds are intentionally above sensor/driving noise.
_BRAKE_ON = BRAKE_ON        # brake pedal fraction that counts as "braking"
_LOSS_MS = 120.0           # min time lost in a segment before we say anything
_SPOKEN_TENTHS = 25        # «Qui perdi N decimi» ha un WAV fino a qui (coaching/spoken.py)
_GAIN_MS = 250.0           # gain this big earns a brief "good"
_THROTTLE_MARGIN = 0.10    # avg throttle deficit that blames throttle
_BRAKE_MARGIN = 0.10       # avg brake excess that blames over-braking
_SPEED_MARGIN = 6.0        # km/h min-speed deficit that blames entry speed
_LEAD_POS = 0.025          # how far before a corner (in pos) to speak its advice
# How much earlier than the reference you must brake before we say so. Every other
# branch of `classify_corner` carries a margin; this one did not, so touching the
# brake ONE METRE early was enough to answer "you can brake later" — and since it
# is tested first, that answer displaced the real cause. In normalized position
# because the live path has no track length; 0.0025 is ~12 m at Monza and ~17 m on
# a 7 km circuit, which is above both sensor noise and lap-to-lap variation.
_BRAKE_EARLY_POS = 0.0025

# Cross-module coherence: a live handling/grip fault in a corner contradicts some
# of the reference-delta advice for that same corner, and the live evidence (you
# *did* understeer there) is more credible than "the fast lap braked later". When
# such a fault was seen recently in a zone we hold the contradicting cue. Keyed by
# the live fault category -> the reference categories it silences in that zone.
_SUPPRESSED_BY: dict[CueCategory, set[CueCategory]] = {
    CueCategory.UNDERSTEER: {CueCategory.CARRY_SPEED, CueCategory.BRAKE_LATER},
    CueCategory.OVERSTEER: {CueCategory.MORE_THROTTLE, CueCategory.CARRY_SPEED},
    CueCategory.LOCKED: {CueCategory.BRAKE_LATER},
    CueCategory.WHEELSPIN: {CueCategory.MORE_THROTTLE},
}
_FAULT_TTL_LAPS = 2        # how many laps a noted fault keeps suppressing


@dataclass(slots=True)
class CornerStats:
    """Aggregated live-vs-reference comparison for one corner.

    Shared currency between the live analyzer and the post-lap debrief so both
    attribute a cause with identical logic (:func:`classify_corner`). Channel
    fields are averages over the corner; speeds are minima.
    """

    lost_ms: float
    throttle_live: float
    throttle_ref: float
    brake_live: float
    brake_ref: float
    min_speed_live: float
    min_speed_ref: float
    braking_early: bool
    # Senza default di proposito, come il suo gemello: i due costruttori di
    # CornerStats (qui e nel debrief) devono rispondere entrambi, altrimenti la
    # meta' che dimentica tace invece di sbagliare, ed e' il modo in cui una
    # regola sola torna a essere due.
    braking_late: bool
    # Quanto e' costata ogni fase della curva (chiavi `phases.PHASES`), o None
    # se non si sa. Senza default per lo stesso motivo di `braking_late`. Con le
    # fasi la causa la sceglie il costo; senza, resta l'ordine fisso di prima.
    phase_ms: dict[str, float] | None


#: In quale tratto della curva si paga ogni causa. La frenata si paga prima
#: dell'apex; arrivare lungo e frenare troppo si pagano anche all'apex, dove la
#: velocita' persa si vede; la velocita' minima e' l'apex; il gas mancante si
#: paga in uscita e sul rettilineo dopo (`after`, che esiste solo nel debrief:
#: dal vivo la zona finisce a `exit_pos` e vale 0).
CAUSE_PHASES: dict[CueCategory, tuple[str, ...]] = {
    CueCategory.BRAKE_LATER: ("entry",),
    CueCategory.BRAKE_EARLIER: ("entry", "apex"),
    CueCategory.LESS_BRAKE: ("entry", "apex"),
    CueCategory.CARRY_SPEED: ("apex",),
    CueCategory.MORE_THROTTLE: ("exit", "after"),
}


@dataclass(slots=True)
class CornerCard:
    """L'ultima curva chiusa: quale era, e quanto è costata.

    `classify_corner` risponde a «vale la pena dire qualcosa?» e sotto i 120 ms
    la risposta è no — giustamente, per la voce. Ma il numero che ha usato per
    rispondere è misurato ed è la metà buona della funzione: la curva presa bene
    è l'unica informazione che il pilota oggi non riceve mai. La carta la
    trattiene per chi mostra, non per chi parla.
    """

    index: int
    lost_ms: float


def _braked_early(live_onset: float, ref_onset: float, ref_brake_at_onset: float) -> bool:
    """Did you get on the brakes meaningfully earlier than the reference?

    Shared by the live analyzer and the post-lap debrief so both answer this the
    same way. Two cases:

    * the reference brakes in this corner too — then it is a distance question,
      and the gap has to clear :data:`_BRAKE_EARLY_POS`;
    * the reference never brakes here at all — then you braked in a corner it
      takes flat, which is a difference no margin can shrink.
    """
    if live_onset < 0.0:
        return False                       # you never braked here
    if ref_onset < 0.0:
        return 0.0 <= ref_brake_at_onset < _BRAKE_ON
    return live_onset <= ref_onset - _BRAKE_EARLY_POS


def _braked_late(live_onset: float, ref_onset: float) -> bool:
    """Did you get on the brakes meaningfully later than the reference?

    The mirror of :func:`_braked_early`, and deliberately narrower: it answers
    only where both of you braked. Not having braked at all is not "braking
    late" — it is a different corner, taken a different way — and you cannot be
    later than someone who never brakes. Both of those have their own answers
    elsewhere; giving them this one would be inventing a third.
    """
    if live_onset < 0.0 or ref_onset < 0.0:
        return False
    return live_onset >= ref_onset + _BRAKE_EARLY_POS


def classify_corner(st: CornerStats, index: int, pos: float) -> Cue | None:
    """Pick the single most likely cause of a corner's time delta (or None).

    With ``st.phase_ms`` the cause whose phases (:data:`CAUSE_PHASES`) cost the
    most wins; without, the first true cause in the fixed order.
    """
    lost = st.lost_ms
    if lost <= -_GAIN_MS:
        return Cue(CueCategory.GOOD, "Qui guadagni, rifalla così",
                   priority=abs(lost), segment=index, pos=pos)
    if lost < _LOSS_MS:
        return None
    # Le candidate sono le cause le cui condizioni sono vere, nell'ordine di
    # sempre. Prima vinceva la prima: una frenata anticipata di pochi metri
    # zittiva un'uscita senza gas che costava sei volte tanto, perche' veniva
    # provata prima. Ora, quando le fasi ci sono, vince quella che costa di piu';
    # a parita' resta l'ordine di sempre (`max` tiene il primo).
    candidates = _candidates(st, lost, index, pos)
    if st.phase_ms is None:
        return candidates[0] if candidates else _time_loss(lost, index, pos)
    phase_ms = st.phase_ms
    priced = [(sum(phase_ms.get(p, 0.0) for p in CAUSE_PHASES[c.category]), c)
              for c in candidates]
    # Una causa il cui tratto ha guadagnato tempo non spiega la perdita: se
    # nessuna paga, si dice solo quanto perdi.
    paying = [pc for pc in priced if pc[0] > 0.0]
    if not paying:
        return _time_loss(lost, index, pos)
    return max(paying, key=lambda pc: pc[0])[1]


def _candidates(st: CornerStats, lost: float, index: int, pos: float) -> list[Cue]:
    """Le cause vere per questa curva, nell'ordine in cui si provavano.

    Restano chiamate a `Cue(...)` scritte per intero: `spoken.py` trova le
    frasi da registrare leggendo il sorgente, e cerca proprio quelle.
    """
    out: list[Cue] = []
    if st.braking_early:
        out.append(Cue(CueCategory.BRAKE_LATER, "Qui hai margine, frena più tardi",
                       priority=lost, segment=index, pos=pos))
    # …e il suo opposto, che fino a oggi non aveva nessuno che lo dicesse.
    # Frenare dopo il riferimento non e' un errore — e' come si guadagna, e su 3
    # delle 25 curve misurate in archivio quella staccata ha prodotto un
    # *guadagno*. Diventa un errore quando non ha pagato: sei arrivato lungo e
    # all'apex sei piu' lento di lui lo stesso. Il divario di velocita' e' lo
    # stesso che poco piu' sotto fa dire «porta piu' velocita' in curva», che
    # su quelle curve e' l'istruzione opposta a quella giusta: e' il punto di
    # frenata a essere a monte, e chi arriva lungo non ha bisogno di piu'
    # velocita' d'ingresso, ha bisogno di prendersi il tempo per usarla.
    if (st.braking_late
            and st.min_speed_ref - st.min_speed_live >= _SPEED_MARGIN):
        out.append(Cue(CueCategory.BRAKE_EARLIER, "Arrivi lungo, frena prima",
                       priority=lost, segment=index, pos=pos))
    if st.throttle_ref - st.throttle_live >= _THROTTLE_MARGIN:
        out.append(Cue(CueCategory.MORE_THROTTLE, "Dai più gas qui",
                       priority=lost, segment=index, pos=pos))
    if st.brake_live - st.brake_ref >= _BRAKE_MARGIN:
        out.append(Cue(CueCategory.LESS_BRAKE, "Freni troppo qui, alleggerisci",
                       priority=lost, segment=index, pos=pos))
    if st.min_speed_ref - st.min_speed_live >= _SPEED_MARGIN:
        out.append(Cue(CueCategory.CARRY_SPEED, "Porta più velocità in curva",
                       priority=lost, segment=index, pos=pos))
    return out


def _time_loss(lost: float, index: int, pos: float) -> Cue:
    """Nessuna causa spiega la perdita: si dice quanto, e basta."""
    # La parola si decide sulla cifra STAMPATA, non sul numero: sono due
    # arrotondamenti diversi e prima o poi si separano. E non e' un caso di
    # bordo — il coach parla da 120 ms in su, quindi tutto fra 120 e 149 ms
    # arrotonda a uno: la frase piu' piccola che dice era anche la piu'
    # frequente, e diceva «1 decimi».
    n = f"{lost / 100.0:.0f}"
    if n == "1":
        msg = f"Qui perdi {n} decimo"
    else:
        msg = f"Qui perdi {n} decimi"
    # Le frasi a voce coi decimi sono registrate da 1 a 25: oltre, il numero
    # resta sullo schermo e la voce dice una frase fissa, vera per ogni cifra
    # da 26 in su (cioe' da 2,55 s). Fermarsi a «25 decimi» direbbe meno di
    # quanto perdi.
    voice = "Qui perdi più di due secondi e mezzo" if int(n) > _SPOKEN_TENTHS else None
    return Cue(CueCategory.TIME_LOSS, msg,
               priority=lost, segment=index, pos=pos, voice=voice)


def corner_level(lost_ms: float) -> str:
    """Il semaforo di una curva chiusa: "gain" | "ok" | "warn" | "bad".

    Non introduce soglie: usa le due che il coach già usa per decidere se
    parlare, misurate in pista. `_LOSS_MS` è «hai perso qualcosa che vale
    dirtelo», `_GAIN_MS` è «questa è una lode» — e la stessa entità in senso
    opposto è ciò che fa passare il giallo al rosso. Riusarle è l'unica cosa che
    garantisce che colore e voce non si contraddicano: se il coach parla, il
    colore non può essere verde. Un terzo numero qui sarebbe una taratura nostra
    che nessuno ha misurato, e questo progetto ha già pagato due volte per due
    metà dell'app che dicevano cose diverse.
    """
    if lost_ms <= -_GAIN_MS:
        return "gain"
    if lost_ms < _LOSS_MS:
        return "ok"
    if lost_ms <= _GAIN_MS:
        return "warn"
    return "bad"


@dataclass(slots=True)
class _Seg:
    """Running comparison for the segment currently being driven."""

    index: int
    n: int = 0
    delta_start: float = 0.0
    delta_last: float = 0.0
    throttle_live: float = 0.0
    throttle_ref: float = 0.0
    brake_live: float = 0.0
    brake_ref: float = 0.0
    min_speed_live: float = field(default=1e9)
    min_speed_ref: float = field(default=1e9)
    live_brake_onset: float = -1.0
    ref_brake_at_onset: float = -1.0  # what the reference brake was where you first braked
    ref_brake_onset: float = -1.0     # …and WHERE the reference started braking
    # I due tagli della finestra dell'apex (gli stessi ±_APEX_HALF di
    # `phases.py`) e il delta al primo frame che li ha passati. None = mai
    # passato: la fase che comincia li' vale 0, come il taglio stretto di
    # `split_loss` quando l'apex cade oltre la fine della finestra.
    mid: float = 0.0
    delta_apex_in: float | None = None
    delta_apex_out: float | None = None
    # Il gesto migliore di questa curva (`corner_refs`), scelto all'ingresso e
    # tenuto fino all'uscita. Con lui la zona misura il suo delta e i canali del
    # riferimento su quel giro; senza, sul riferimento principale come sempre.
    ref: CornerRef | None = None


class CoachAnalyzer:
    """Stateful: fed (snapshot, delta) each frame, yields cues at zone ends."""

    def __init__(self, num_segments: int = 24) -> None:
        self.num_segments = max(4, num_segments)
        self._zones: list[tuple[float, float, float]] = []  # (lo, hi, mid)
        self._seg: _Seg | None = None
        self._last_pos: float = -1.0
        self._advice: dict[int, Cue] = {}     # zone index -> latest loss advice
        self._announced: set[int] = set()     # zones announced this lap
        # (zone index, live fault category) -> laps since last seen there.
        self._faults: dict[tuple[int, CueCategory], int] = {}
        # L'ultima curva chiusa, comunque sia andata. Non è uno stato del giro:
        # sopravvive al traguardo di proposito, così il riquadro resta finché non
        # chiudi la curva dopo — nessun timer da tarare.
        self.last_corner: CornerCard | None = None
        # Ha il gioco smesso di contare questo giro? Non è una latch nostra: la
        # tiene già il sim (su ACC `isValidLap` cade al taglio e resta giù fino
        # al traguardo), quindi qui si legge e basta. Una seconda latch nostra
        # si sarebbe azzerata su un fronte diverso dal suo — e le due metà che
        # decidono la stessa cosa su fronti diversi le abbiamo già pagate.
        # Su AC il campo è None e questo resta False: lì i limiti di pista si
        # deducono da `tyres_out`, e «non lo so» non è «hai tagliato».
        self._lap_cut = False
        # Il gesto migliore di ogni curva, o None (Decisione 6: vale per il
        # consiglio e il riquadro dell'ultima curva, non per il delta a schermo).
        self._bests: CornerBests | None = None
        self._set_fixed_zones()

    def reset(self) -> None:
        # Keep the learned advice (same track); just drop in-progress lap state.
        # La carta NON è stato del giro in corso: sopravvive al traguardo di
        # proposito (vedi `last_corner` in `__init__`). Azzerarla qui rendeva il
        # riquadro assente dal traguardo alla prima curva su OGNI giro — il
        # motore ricostruisce il riferimento dopo ogni giro salvato e passa di
        # qui — cioè proprio sul rettilineo dove il pilota ha occhi per leggerlo.
        self._seg = None
        self._last_pos = -1.0
        self._announced.clear()
        self._lap_cut = False

    def drop_last_corner(self) -> None:
        """Butta la carta. La chiama chi sa che il giro non è rappresentativo:
        nascondere e basta la farebbe riapparire identica dopo il pit stop, con
        addosso un numero di dieci minuti fa."""
        self.last_corner = None

    def set_corner_refs(self, bests: CornerBests | None) -> None:
        """Confronta ogni curva col suo gesto migliore (None = col principale).

        Non tocca consigli, annunci, difetti, la carta né le zone: le curve sono
        le stesse, cambia solo il metro delle prossime. Un consiglio misurato col
        metro di prima resta vero per la curva in cui è stato misurato, e la zona
        in corso tiene il riferimento con cui è cominciata — cambiarlo a metà
        sottrarrebbe due orologi diversi.
        """
        self._bests = bests

    def set_corners(self, corners: list[Corner]) -> None:
        """Use detected corners as the zones (or fall back to fixed segments)."""
        previous = self._zones
        if corners:
            self._zones = corner_zones(corners)
        else:
            self._set_fixed_zones()
        # Consigli e difetti sono indicizzati per zona, e un layout nuovo sposta
        # gli indici: con zone diverse un `index` conservato significa un'altra
        # curva, e un consiglio sulla curva sbagliata manda il pilota a lavorare
        # su quella accanto. Quindi non si tengono dove sono — ma nemmeno si
        # buttano: **seguono la curva**. Buttarli era il difetto, due volte.
        # Con lo stesso layout (il caso di quasi ogni giro salvato) voleva dire
        # non dirli mai, perche' si mettono da parte a fine curva per il giro
        # dopo. E con un layout nuovo voleva dire toglierli proprio a chi
        # migliora, che cambia riferimento a ogni giro.
        if self._zones != previous:
            moved = self._follow(previous)
            self._advice = {
                moved[i]: replace(c, segment=moved[i])
                for i, c in self._advice.items() if i in moved}
            self._announced = {moved[i] for i in self._announced if i in moved}
            self._faults = {(moved[z], cat): age
                            for (z, cat), age in self._faults.items() if z in moved}
            # La carta invece porta un nome e un numero già scritti a schermo:
            # quella si butta, com'era.
            self.last_corner = None
        self._seg = None

    def _follow(self, previous: list[tuple[float, float, float]]) -> dict[int, int]:
        """Dove è finita ogni zona di prima: indice vecchio -> indice nuovo.

        Una curva è la stessa se il suo apex cade dentro una zona di adesso. Le
        zone che non ritrovano casa mancano dal risultato, e quello che
        portavano si perde: meglio tacere che parlare della curva sbagliata.
        """
        moved: dict[int, int] = {}
        for old, (_lo, _hi, mid) in enumerate(previous):
            new = self._zone_at(mid)
            if new >= 0:
                moved[old] = new
        return moved

    def _set_fixed_zones(self) -> None:
        n = self.num_segments
        self._zones = [(i / n, (i + 1) / n, (i + 0.5) / n) for i in range(n)]

    def zone_at(self, pos: float) -> int:
        """Index of the zone containing ``pos``, or -1 on a straight.

        Public because the engine has to tell the scheduler which zone is the
        focus corner, and the zone numbering is this class's own.
        """
        return self._zone_at(pos)

    def _zone_at(self, pos: float) -> int:
        """Index of the zone containing ``pos``, or -1 on a straight."""
        for i, (lo, hi, _mid) in enumerate(self._zones):
            if lo <= pos <= hi:
                return i
        return -1

    def update(self, s: TelemetrySnapshot, delta: DeltaState | None) -> list[Cue]:
        """Consume one frame; return cues finalized this frame (usually none)."""
        if delta is None:
            # No reference / not comparable -> drop any partial zone.
            self._seg = None
            self._last_pos = s.lap_position if s.connected else -1.0
            return []

        pos = s.lap_position
        cues: list[Cue] = []
        self._lap_cut = s.lap_valid is False

        # New lap (position wrapped back past the line): a fresh set of approaches.
        if self._last_pos >= 0.0 and pos < self._last_pos - 0.5:
            self._seg = None
            self._announced.clear()
            self._age_faults()
        self._last_pos = pos

        zone_idx = self._zone_at(pos)
        # Leaving the current zone (into another zone or a straight): finalize it
        # into this corner's advice (spoken next lap, not now).
        if self._seg is not None and zone_idx != self._seg.index:
            self._apply_result(self._seg.index, self._finalize(self._seg), cues)
            self._seg = None
        # Entering a zone.
        if zone_idx >= 0 and self._seg is None:
            self._seg = self._new_segment(zone_idx, s, delta)
        if self._seg is not None:
            self._accumulate(self._seg, s, delta)

        # Speak any stored advice for a corner we're now approaching.
        self._feed_forward(pos, cues)
        return cues

    def note_faults(self, fault_cues: list[Cue]) -> None:
        """Record live grip/handling faults (from the event & balance detectors)
        so the feed-forward can hold contradicting advice for that zone. Call this
        each tick *before* :meth:`update`."""
        for cue in fault_cues:
            if cue.category not in _SUPPRESSED_BY:
                continue
            zone = self._zone_at(cue.pos)
            if zone >= 0:
                self._faults[(zone, cue.category)] = 0   # seen this lap

    def _age_faults(self) -> None:
        """Each new lap, age fault memory and forget anything past its TTL."""
        for key in list(self._faults):
            self._faults[key] += 1
            if self._faults[key] > _FAULT_TTL_LAPS:
                del self._faults[key]

    def _suppressed(self, zone: int, category: CueCategory) -> bool:
        """True if a recent fault in ``zone`` contradicts ``category``."""
        for (fzone, fault), _age in self._faults.items():
            if fzone == zone and category in _SUPPRESSED_BY.get(fault, ()):
                return True
        return False

    def _apply_result(self, zone: int, cue: Cue | None, cues: list[Cue]) -> None:
        """Route a finalized zone result: remember a loss, praise/clear otherwise."""
        if cue is None:
            self._advice.pop(zone, None)          # taken fine — stop reminding
        elif cue.category == CueCategory.GOOD:
            self._advice.pop(zone, None)
            cues.append(cue)                      # praise is fine right after
        else:
            self._advice[zone] = cue              # remember; speak on next approach

    def _feed_forward(self, pos: float, cues: list[Cue]) -> None:
        """Emit a corner's advice once, as the car enters its approach window."""
        for i, (lo, _hi, _mid) in enumerate(self._zones):
            if i in self._announced or i not in self._advice:
                continue
            if lo - _LEAD_POS <= pos < lo:
                adv = self._advice[i]
                # Hold advice the live data just contradicted in this zone.
                if self._suppressed(i, adv.category):
                    continue
                self._announced.add(i)
                # `replace` e non un Cue nuovo: una copia campo per campo
                # dimenticava `voice`, e oltre i 25 decimi la frase registrata
                # non usciva mai.
                cues.append(replace(adv, pos=pos))

    def _new_segment(self, index: int, s: TelemetrySnapshot,
                     delta: DeltaState) -> _Seg:
        mid = self._zones[index][2]
        ref = self._bests.at(mid) if self._bests is not None else None
        seg = _Seg(index=index, mid=mid, ref=ref)
        d, _rp = _seg_delta(seg, s, delta)
        seg.delta_start = seg.delta_last = d
        return seg

    def _accumulate(self, seg: _Seg, s: TelemetrySnapshot, delta: DeltaState) -> None:
        seg.n += 1
        # Un delta solo per tutto: perdita, tagli di fase e canali leggono lo
        # stesso riferimento, cosi' le fasi risommano proprio `lost_ms`.
        d, rp = _seg_delta(seg, s, delta)
        seg.delta_last = d
        pos = s.lap_position
        if seg.delta_apex_in is None and pos >= seg.mid - _APEX_HALF:
            seg.delta_apex_in = d
        if seg.delta_apex_out is None and pos >= seg.mid + _APEX_HALF:
            seg.delta_apex_out = d
        seg.throttle_live += s.throttle
        seg.throttle_ref += rp.throttle
        seg.brake_live += s.brake
        seg.brake_ref += rp.brake
        seg.min_speed_live = min(seg.min_speed_live, s.speed_kmh)
        seg.min_speed_ref = min(seg.min_speed_ref, rp.speed_kmh)
        # Capture, at the instant you first hit the brakes, what the reference was
        # doing there. If it was still on throttle, you braked too early.
        if seg.live_brake_onset < 0.0 and s.brake >= _BRAKE_ON:
            seg.live_brake_onset = s.lap_position
            seg.ref_brake_at_onset = rp.brake
        if seg.ref_brake_onset < 0.0 and rp.brake >= _BRAKE_ON:
            seg.ref_brake_onset = s.lap_position

    def _finalize(self, seg: _Seg) -> Cue | None:
        if seg.n == 0:
            return None
        st = CornerStats(
            lost_ms=seg.delta_last - seg.delta_start,
            throttle_live=seg.throttle_live / seg.n,
            throttle_ref=seg.throttle_ref / seg.n,
            brake_live=seg.brake_live / seg.n,
            brake_ref=seg.brake_ref / seg.n,
            min_speed_live=seg.min_speed_live,
            min_speed_ref=seg.min_speed_ref,
            # You braked here while the reference was not yet braking at that
            # point — and by a margin worth mentioning.
            braking_early=_braked_early(
                seg.live_brake_onset, seg.ref_brake_onset, seg.ref_brake_at_onset),
            braking_late=_braked_late(seg.live_brake_onset, seg.ref_brake_onset),
            # Le fasi solo dove la finestra dell'apex sta dentro la zona: se
            # no un taglio cade fuori e la sua fase vale 0 per costruzione.
            phase_ms=(_live_phases(seg)
                      if phases_priceable(*self._zones[seg.index][:2], seg.mid)
                      else None),
        )
        cue = classify_corner(st, seg.index, _seg_pos(seg, self))
        if self._lap_cut and cue is not None and cue.category is CueCategory.GOOD:
            # Il giro non lo conta più il gioco, e in questa curva hai guadagnato
            # tempo: le due cose insieme sono la scorciatoia, non il talento.
            # Trovato dal pilota in pista il 2026-08-12 — tagliava e il coach gli
            # faceva i complimenti mentre il giro veniva invalidato.
            #
            # Muore la lode, non il consiglio: «hai frenato troppo presto» resta
            # vero anche su un giro buttato, e tacere tutto per un taglio
            # spegnerebbe il coach proprio nel giro in cui stai sbagliando di più.
            # Per lo stesso motivo il tempo *perso* resta una carta e questo
            # *guadagno* no: una perdita l'hai fatta davvero, un guadagno preso
            # fuori dai cordoli non è un tuo numero, e un valore che non abbiamo
            # non si finge (stessa regola di `engine._corner_block`).
            #
            # Resta scoperta la curva SUBITO DOPO il taglio: ci arrivi con una
            # velocità che il riferimento non aveva, quindi anche lì il delta è
            # sporco. Qui non è trattata: servirebbe sapere dove il taglio è
            # finito, e inventarlo sarebbe peggio del difetto.
            return None
        self.last_corner = CornerCard(index=seg.index, lost_ms=st.lost_ms)
        return cue


def corner_zones(corners: list[Corner]) -> list[tuple[float, float, float]]:
    """Le zone delle curve, ``(lo, hi, apex)`` ordinate per ingresso.

    Una zona va da ``entry_pos`` a ``min(exit_pos, ingresso della curva dopo)``:
    l'estensione di ingresso e uscita puo' sovrapporre due curve, e un frame
    deve stare in una zona sola. La usa anche il debrief per sapere se le fasi
    di una curva si possono prezzare (:func:`phases_priceable`).
    """
    zones = sorted((c.entry_pos, c.exit_pos, c.apex_pos) for c in corners)
    for i in range(len(zones) - 1):
        lo, hi, mid = zones[i]
        next_lo = zones[i + 1][0]
        if hi >= next_lo:
            zones[i] = (lo, max(lo, next_lo - 1e-4), mid)
    return zones


def phases_priceable(lo: float, hi: float, apex: float) -> bool:
    """La finestra dell'apex (``apex ± _APEX_HALF``) sta tutta in ``[lo, hi]``?

    Se no, le fasi di quella curva non dicono quale causa costa di piu': una
    zona che finisce prima di ``apex + _APEX_HALF`` ha l'uscita a 0, e «dai piu'
    gas» non puo' pagare mai. Sulla copia dell'archivio succedeva a 89 zone dal
    vivo su 149 (finiscono prima) e a 56 (cominciano dopo ``apex - _APEX_HALF``):
    «dai piu' gas» scendeva da 143 a 37 e «frena piu' tardi» da 16 a 4. Li' resta
    l'ordine fisso di sempre. Una regola sola, chiamata dal vivo e dal debrief,
    cosi' voce e report scelgono la stessa causa sulla stessa curva.
    """
    return lo <= apex - _APEX_HALF and apex + _APEX_HALF <= hi


def _seg_delta(seg: _Seg, s: TelemetrySnapshot,
               delta: DeltaState) -> tuple[float, ReferencePoint]:
    """Il delta di questo frame e il punto del riferimento, per questa zona.

    Con il gesto migliore della curva si leggono sul suo giro, con la stessa
    sottrazione di `LapComparator.compare`; senza, quelli del principale che il
    comparatore ha già calcolato.
    """
    if seg.ref is None:
        return delta.delta_ms, delta.reference_point
    pos = s.lap_position
    ref = seg.ref.reference
    return float(s.current_lap_ms) - ref.time_at(pos), ref.point_at(pos)


def _live_phases(seg: _Seg) -> dict[str, float]:
    """Le fasi di una zona dal vivo, tagliando il suo stesso delta.

    Una scomposizione come quella di `phases.split_loss`: entry + apex + exit
    risommano `lost_ms` esattamente. Un taglio mai passato prende il valore
    finale, cosi' la fase che comincia li' vale 0. `after` dal vivo non c'e':
    la zona finisce a `exit_pos`.
    """
    end = seg.delta_last
    out_ = end if seg.delta_apex_out is None else seg.delta_apex_out
    in_ = out_ if seg.delta_apex_in is None else seg.delta_apex_in
    return {"entry": in_ - seg.delta_start, "apex": out_ - in_,
            "exit": end - out_, "after": 0.0}


def _seg_pos(seg: _Seg, analyzer: CoachAnalyzer) -> float:
    """Track position of a zone's reference point (corner apex / segment centre)."""
    if 0 <= seg.index < len(analyzer._zones):
        return analyzer._zones[seg.index][2]
    return 0.0
