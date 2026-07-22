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

from dataclasses import dataclass, field

from ..comparison import DeltaState
from ..telemetry.snapshot import TelemetrySnapshot
from ..track import Corner
from .cue import Cue, CueCategory

# Tuning. Thresholds are intentionally above sensor/driving noise.
_BRAKE_ON = 0.15            # brake pedal fraction that counts as "braking"
_LOSS_MS = 120.0           # min time lost in a segment before we say anything
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


def classify_corner(st: CornerStats, index: int, pos: float) -> Cue | None:
    """Pick the single most likely cause of a corner's time delta (or None)."""
    lost = st.lost_ms
    if lost <= -_GAIN_MS:
        return Cue(CueCategory.GOOD, "Bel tratto, continua così",
                   priority=abs(lost), segment=index, pos=pos)
    if lost < _LOSS_MS:
        return None
    # Most actionable cause first.
    if st.braking_early:
        return Cue(CueCategory.BRAKE_LATER, "Puoi frenare più tardi",
                   priority=lost, segment=index, pos=pos)
    if st.throttle_ref - st.throttle_live >= _THROTTLE_MARGIN:
        return Cue(CueCategory.MORE_THROTTLE, "Più gas qui",
                   priority=lost, segment=index, pos=pos)
    if st.brake_live - st.brake_ref >= _BRAKE_MARGIN:
        return Cue(CueCategory.LESS_BRAKE, "Stai frenando troppo, alleggerisci",
                   priority=lost, segment=index, pos=pos)
    if st.min_speed_ref - st.min_speed_live >= _SPEED_MARGIN:
        return Cue(CueCategory.CARRY_SPEED, "Porta più velocità in curva",
                   priority=lost, segment=index, pos=pos)
    tenths = lost / 100.0
    return Cue(CueCategory.TIME_LOSS, f"Stai perdendo {tenths:.0f} decimi qui",
               priority=lost, segment=index, pos=pos)


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
        self._set_fixed_zones()

    def reset(self) -> None:
        # Keep the learned advice (same track); just drop in-progress lap state.
        self._seg = None
        self._last_pos = -1.0
        self._announced.clear()

    def set_corners(self, corners: list[Corner]) -> None:
        """Use detected corners as the zones (or fall back to fixed segments)."""
        if corners:
            zones = sorted(
                (c.entry_pos, c.exit_pos, c.apex_pos) for c in corners
            )
            # Clip any overlap introduced by entry/exit extension.
            for i in range(len(zones) - 1):
                lo, hi, mid = zones[i]
                next_lo = zones[i + 1][0]
                if hi >= next_lo:
                    zones[i] = (lo, max(lo, next_lo - 1e-4), mid)
            self._zones = zones
        else:
            self._set_fixed_zones()
        # A new zone layout invalidates the old per-zone advice and fault memory
        # (both are keyed by zone index).
        self._advice.clear()
        self._announced.clear()
        self._faults.clear()
        self._seg = None

    def _set_fixed_zones(self) -> None:
        n = self.num_segments
        self._zones = [(i / n, (i + 1) / n, (i + 0.5) / n) for i in range(n)]

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
            self._seg = self._new_segment(zone_idx, delta)
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
                cues.append(Cue(adv.category, adv.message, adv.priority,
                                adv.segment, pos))

    def _new_segment(self, index: int, delta: DeltaState) -> _Seg:
        return _Seg(index=index, delta_start=delta.delta_ms, delta_last=delta.delta_ms)

    def _accumulate(self, seg: _Seg, s: TelemetrySnapshot, delta: DeltaState) -> None:
        seg.n += 1
        seg.delta_last = delta.delta_ms
        rp = delta.reference_point
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
        )
        return classify_corner(st, seg.index, _seg_pos(seg, self))


def _seg_pos(seg: _Seg, analyzer: CoachAnalyzer) -> float:
    """Track position of a zone's reference point (corner apex / segment centre)."""
    if 0 <= seg.index < len(analyzer._zones):
        return analyzer._zones[seg.index][2]
    return 0.0
