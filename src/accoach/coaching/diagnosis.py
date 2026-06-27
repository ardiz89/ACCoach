"""Per-lap handling diagnosis → :class:`~accoach.engineer.core.LapStats`.

This is the bridge the race-engineer needs: it turns a recorded :class:`Lap`
into the discilli taxonomy (understeer/oversteer × entry/apex/exit × low/high
speed) that :meth:`RaceEngineer.observe` consumes. The engineer decides *what to
change*; this only *names the problem*, per corner, aggregated over the lap.

The balance logic mirrors :mod:`accoach.coaching.balance` (same yaw/steer ratio
for understeer, same opposite-lock test for oversteer, same sign convention),
applied per corner-phase instead of live, so a symptom is attributed to a phase
and a speed band and counted across distinct corners — exactly the gate the
engine uses to tell a *setup* problem (≥3 corners) from a *driving* one.

Note: ``pressures_hot`` and lock/spin segments are left unset here — tyre
pressure and the physical slip ratio aren't persisted in a lap yet (see the
engineer handoff), so the engine simply skips those (pressure phase auto-passes).
The symptom diagnosis that drives aero/mechanical work is fully computed.
"""

from __future__ import annotations

from ..engineer import Balance, LapStats, Phase, Speed, Symptom
from ..recording.lap import Lap, LapSample
from ..track import Corner, detect_corners
from .balance import (
    _MIN_SPEED_KMH,
    _STEER_CATCH,
    _STEER_HARD,
    _UNDERSTEER_RATIO,
    _YAW_LOOSE,
    _YAW_SIGN,
)

# Apex band half-width (normalized track position) around the speed minimum.
_APEX_HALF = 0.02
_BRAKE_ON = 0.15            # entry = braking before the apex
_THROTTLE_ON = 0.20        # exit = on the power after the apex
_SPEED_SPLIT_KMH = 120.0   # low/high corner speed band (per the taxonomy)
# A phase must reach this aggregate intensity to count the symptom present there.
_PRESENCE = 0.15
_WARM_C = 50.0             # mean tyre core temp above this = warmed up


def _phase_of(pos: float, s: LapSample, c: Corner) -> Phase | None:
    """Which corner phase this sample belongs to (or None if between/straight)."""
    if abs(pos - c.apex_pos) <= _APEX_HALF:
        return Phase.APEX
    if c.entry_pos <= pos < c.apex_pos and s.brake >= _BRAKE_ON:
        return Phase.ENTRY
    if c.apex_pos < pos <= c.exit_pos and s.throttle >= _THROTTLE_ON:
        return Phase.EXIT
    return None


def _understeer_mag(s: LapSample) -> float:
    """0..1 understeer intensity for one frame (0 when not pushing)."""
    if s.speed_kmh < _MIN_SPEED_KMH:
        return 0.0
    steer = abs(s.steer_angle)
    if steer < _STEER_HARD:
        return 0.0
    ratio = abs(s.yaw_rate) / steer          # sign-independent (magnitude)
    if ratio >= _UNDERSTEER_RATIO:
        return 0.0
    return min(1.0, (_UNDERSTEER_RATIO - ratio) / _UNDERSTEER_RATIO)


def _oversteer_mag(s: LapSample) -> float:
    """0..1 oversteer intensity for one frame (opposite-lock test, like balance.py)."""
    if s.speed_kmh < _MIN_SPEED_KMH:
        return 0.0
    yaw = s.yaw_rate * _YAW_SIGN
    if abs(yaw) < _YAW_LOOSE or abs(s.steer_angle) < _STEER_CATCH:
        return 0.0
    if s.steer_angle * yaw >= 0.0:           # same sign = not countersteering
        return 0.0
    return min(1.0, abs(yaw) / (2.0 * _YAW_LOOSE))


def _speed_band(speeds: list[float]) -> Speed:
    vmin = min(speeds) if speeds else 0.0
    return Speed.LOW if vmin < _SPEED_SPLIT_KMH else Speed.HIGH


def _warmed_up(samples: list[LapSample]) -> bool:
    temps = [t for s in samples for t in s.tyre_core_temp if t > 0.0]
    if not temps:
        return True                          # no tyre-temp data → don't block
    return (sum(temps) / len(temps)) >= _WARM_C


def build_lap_stats(lap: Lap, corners: list[Corner] | None = None) -> LapStats:
    """Diagnose one recorded lap into a :class:`LapStats` for the engineer."""
    if corners is None:
        corners = detect_corners(lap.samples)

    scores: dict[Symptom, float] = {}
    corner_counts: dict[Symptom, int] = {}

    for c in corners:
        # Bucket this corner's samples by phase.
        by_phase: dict[Phase, list[LapSample]] = {}
        corner_speeds: list[float] = []
        for s in lap.samples:
            if not (c.entry_pos <= s.pos <= c.exit_pos):
                continue
            corner_speeds.append(s.speed_kmh)
            ph = _phase_of(s.pos, s, c)
            if ph is not None:
                by_phase.setdefault(ph, []).append(s)
        if not corner_speeds:
            continue
        speed = _speed_band(corner_speeds)

        for phase, frames in by_phase.items():
            if not frames:
                continue
            # Oversteer takes precedence per frame (it's the rear genuinely loose).
            over = [_oversteer_mag(s) for s in frames]
            under = [u if o == 0.0 else 0.0
                     for u, o in ((_understeer_mag(s), om) for s, om in zip(frames, over))]
            u_int = sum(under) / len(frames)
            o_int = sum(over) / len(frames)
            for balance, intensity in ((Balance.UNDERSTEER, u_int),
                                       (Balance.OVERSTEER, o_int)):
                if intensity < _PRESENCE:
                    continue
                sym = Symptom(balance, phase, speed)
                scores[sym] = max(scores.get(sym, 0.0), intensity)
                corner_counts[sym] = corner_counts.get(sym, 0) + 1

    return LapStats(
        lap_time_ms=lap.lap_time_ms,
        # `valid` means complete; `clean` (from the reference-integrity work) means
        # no off-track. Only a complete, non-dirty lap counts toward the engine's
        # evaluation window.
        stable=lap.valid and lap.clean is not False,
        warmed_up=_warmed_up(lap.samples),
        symptom_scores=scores,
        symptom_corners=corner_counts,
        pressures_hot=None,        # tyre pressure not persisted in laps yet
        lock_segments=0,
        spin_segments=0,
    )
