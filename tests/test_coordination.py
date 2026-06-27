"""Cross-module coherence: live faults suppress contradicting corner advice."""
from dataclasses import replace

from accoach.coaching.analyzer import CoachAnalyzer, _FAULT_TTL_LAPS
from accoach.coaching.cue import Cue, CueCategory
from accoach.comparison.delta import DeltaState
from accoach.comparison.reference import ReferencePoint
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
)


def _refpoint():
    return ReferencePoint(
        t_ms=0.0, speed_kmh=100.0, throttle=0.5, brake=0.0, g_long=0.0,
        g_lat=0.0, steer_angle=0.0, gear="4", wheel_slip=(0.0,) * 4,
        abs_active=0.0, tc_active=0.0, yaw_rate=0.0,
    )


def _delta(pos):
    return DeltaState(pos=pos, delta_ms=0.0, predicted_lap_ms=90000.0,
                      reference_lap_ms=90000, live_speed_kmh=100.0,
                      reference_point=_refpoint())


def _fault(category, pos):
    return Cue(category=category, message="x", priority=300.0,
               segment=int(pos * 20), pos=pos)


def _approach(an, pos):
    """One update on the approach to a zone; returns emitted cues."""
    return an.update(replace(_LIVE, lap_position=pos, speed_kmh=100.0), _delta(pos))


def _make_analyzer():
    an = CoachAnalyzer(num_segments=10)        # zone 5 == [0.5, 0.6], lo = 0.5
    an._advice[5] = Cue(CueCategory.CARRY_SPEED, "Porta più velocità", 200.0, 5, 0.55)
    return an


def test_advice_spoken_without_fault():
    an = _make_analyzer()
    cues = _approach(an, 0.49)                  # inside the lead window of zone 5
    assert any(c.category is CueCategory.CARRY_SPEED for c in cues)


def test_understeer_suppresses_carry_speed():
    an = _make_analyzer()
    an.note_faults([_fault(CueCategory.UNDERSTEER, 0.55)])   # same zone (5)
    cues = _approach(an, 0.49)
    assert not any(c.category is CueCategory.CARRY_SPEED for c in cues)


def test_unrelated_fault_does_not_suppress():
    an = _make_analyzer()
    # Wheelspin only silences MORE_THROTTLE, not CARRY_SPEED.
    an.note_faults([_fault(CueCategory.WHEELSPIN, 0.55)])
    cues = _approach(an, 0.49)
    assert any(c.category is CueCategory.CARRY_SPEED for c in cues)


def test_fault_in_other_zone_does_not_suppress():
    an = _make_analyzer()
    an.note_faults([_fault(CueCategory.UNDERSTEER, 0.15)])   # zone 1, not 5
    cues = _approach(an, 0.49)
    assert any(c.category is CueCategory.CARRY_SPEED for c in cues)


def test_fault_decays_after_ttl():
    an = _make_analyzer()
    an.note_faults([_fault(CueCategory.UNDERSTEER, 0.55)])
    # Simulate several lap wraps to age the fault past its TTL.
    for _ in range(_FAULT_TTL_LAPS + 1):
        an._age_faults()
    cues = _approach(an, 0.49)
    assert any(c.category is CueCategory.CARRY_SPEED for c in cues)


def test_oversteer_suppresses_more_throttle():
    an = CoachAnalyzer(num_segments=10)
    an._advice[5] = Cue(CueCategory.MORE_THROTTLE, "Più gas", 200.0, 5, 0.55)
    an.note_faults([_fault(CueCategory.OVERSTEER, 0.55)])
    cues = _approach(an, 0.49)
    assert not any(c.category is CueCategory.MORE_THROTTLE for c in cues)
