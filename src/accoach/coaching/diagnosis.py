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

Lock/spin segments and ``pressures_hot`` are computed from the v6 per-wheel
channels (physical ``slip_ratio`` and ``tyre_pressure``); on an older lap that
predates v6 those read zero/None and the engine simply skips them (the pressure
phase auto-passes). The symptom diagnosis (aero/mechanical) is always computed.
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
from .events import (
    _ABS_LEVEL,
    _BRAKE_MIN,
    _LOCK_RATIO,
    _RATIO_MIN_SPEED,
    _SPIN_RATIO,
    _TC_LEVEL,
    _THROTTLE_MIN,
)

# Apex band half-width (normalized track position) around the speed minimum.
_APEX_HALF = 0.02
_BRAKE_ON = 0.15            # entry = braking before the apex
_THROTTLE_ON = 0.20        # exit = on the power after the apex
_SPEED_SPLIT_KMH = 120.0   # low/high corner speed band (per the taxonomy)
# A phase must reach this aggregate intensity to count the symptom present there.
_PRESENCE = 0.15
# Mean tyre core temp above this = warmed up. Slicks read low pressure when cold,
# so this also gates which frames count toward hot pressures — matched to the live
# PressureAdvisor's window so the engineer never tunes pressure on a cold tyre.
_WARM_C = 75.0
_SEG_N = 20               # track segments for counting distinct lock/spin spots


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


def _seg(pos: float) -> int:
    return min(_SEG_N - 1, max(0, int(pos * _SEG_N)))


def _lock_spin_segments(samples: list[LapSample]) -> tuple[int, int]:
    """Distinct track segments with a lock-up / wheelspin (physical slip ratio).

    Same thresholds as the live EventDetector; needs the v6 ``slip_ratio`` channel
    (older laps have it zero → counts as 0, the safe default).
    """
    locks: set[int] = set()
    spins: set[int] = set()
    for s in samples:
        # Mirror the live EventDetector exactly: the aid intervention (abs/tc) is
        # the primary signal and the physical slip ratio the fallback. On an ACC
        # GT3 the aids hold slip low *because they're working*, so a slip-only
        # check would miss every lock/spin and the engineer would never see them.
        if s.brake >= _BRAKE_MIN and (
                s.abs_active >= _ABS_LEVEL
                or (s.speed_kmh >= _RATIO_MIN_SPEED
                    and min(s.slip_ratio[0], s.slip_ratio[1]) <= _LOCK_RATIO)):
            locks.add(_seg(s.pos))
        if (s.throttle >= _THROTTLE_MIN and s.gear not in ("R", "N") and (
                s.tc_active >= _TC_LEVEL
                or (s.speed_kmh >= _RATIO_MIN_SPEED
                    and max(s.slip_ratio[2], s.slip_ratio[3]) >= _SPIN_RATIO))):
            spins.add(_seg(s.pos))
    return len(locks), len(spins)


def _pressures_hot(samples: list[LapSample]) -> dict | None:
    """Mean hot pressure per axle (front = FL/FR, rear = RL/RR), or None if absent.

    Only frames at temperature count: a cold slick reads several psi low, so
    averaging the warm-up laps would tell the engineer to add pressure that then
    over-inflates once the tyre comes in. Frames without temp data are kept (we
    can't tell, so don't drop them)."""
    fronts: list[float] = []
    rears: list[float] = []
    for s in samples:
        temps = [t for t in s.tyre_core_temp if t > 0.0]
        if temps and (sum(temps) / len(temps)) < _WARM_C:
            continue                          # tyre not at temperature yet
        fronts += [p for p in s.tyre_pressure[:2] if p > 0.0]
        rears += [p for p in s.tyre_pressure[2:] if p > 0.0]
    if not fronts or not rears:
        return None
    return {"front": sum(fronts) / len(fronts), "rear": sum(rears) / len(rears)}


def corner_symptoms(samples: list[LapSample], c: Corner) -> dict[Symptom, float]:
    """Handling symptoms for ONE corner: {Symptom: intensity≥_PRESENCE}.

    Shared by :func:`build_lap_stats` (aggregate, for the engineer) and the
    debrief (per-corner, for the "why" of each time loss).
    """
    by_phase: dict[Phase, list[LapSample]] = {}
    corner_speeds: list[float] = []
    for s in samples:
        if not (c.entry_pos <= s.pos <= c.exit_pos):
            continue
        corner_speeds.append(s.speed_kmh)
        ph = _phase_of(s.pos, s, c)
        if ph is not None:
            by_phase.setdefault(ph, []).append(s)
    if not corner_speeds:
        return {}
    speed = _speed_band(corner_speeds)

    out: dict[Symptom, float] = {}
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
            if intensity >= _PRESENCE:
                out[Symptom(balance, phase, speed)] = intensity
    return out


def dominant_symptom(scores: dict[Symptom, float]) -> Symptom | None:
    """The strongest symptom in a score dict, or None if empty."""
    return max(scores, key=scores.get) if scores else None


def build_lap_stats(lap: Lap, corners: list[Corner] | None = None) -> LapStats:
    """Diagnose one recorded lap into a :class:`LapStats` for the engineer."""
    if corners is None:
        corners = detect_corners(lap.samples)

    scores: dict[Symptom, float] = {}
    corner_counts: dict[Symptom, int] = {}
    for c in corners:
        for sym, intensity in corner_symptoms(lap.samples, c).items():
            scores[sym] = max(scores.get(sym, 0.0), intensity)
            corner_counts[sym] = corner_counts.get(sym, 0) + 1

    lock_segments, spin_segments = _lock_spin_segments(lap.samples)
    return LapStats(
        lap_time_ms=lap.lap_time_ms,
        # `valid` means complete; `clean` (from the reference-integrity work) means
        # no off-track. Only a complete, non-dirty lap counts toward the engine's
        # evaluation window.
        stable=lap.valid and lap.clean is not False,
        warmed_up=_warmed_up(lap.samples),
        symptom_scores=scores,
        symptom_corners=corner_counts,
        pressures_hot=_pressures_hot(lap.samples),
        lock_segments=lock_segments,
        spin_segments=spin_segments,
    )
