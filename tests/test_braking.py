"""BrakingDetector: coasting and trail-braking faults."""
from dataclasses import replace

from accoach.coaching.braking import BrakingDetector
from accoach.coaching.cue import CueCategory
from accoach.engineer import CarClass
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=150.0,
)


def _snap(brake=0.0, throttle=0.0, steer=0.0, speed=150.0, pos=0.3):
    return replace(_BASE, brake=brake, throttle=throttle, steer_angle=steer,
                   speed_kmh=speed, lap_position=pos)


def test_coasting_fires_once():
    det = BrakingDetector()
    out, now = [], 0.0
    for _ in range(20):
        out += det.update(_snap(brake=0.0, throttle=0.0), now)
        now += 0.05
    assert sum(c.category is CueCategory.COASTING for c in out) == 1


def test_brief_handover_no_coast():
    det = BrakingDetector()
    out, now = [], 0.0
    seq = [_snap(brake=0.6)] * 4 + [_snap()] * 3 + [_snap(throttle=0.8)] * 6
    for s in seq:
        out += det.update(s, now)
        now += 0.05
    assert not any(c.category is CueCategory.COASTING for c in out)


def test_no_trail_fires():
    det = BrakingDetector()
    out, now = [], 0.0
    for _ in range(5):
        out += det.update(_snap(brake=0.9, steer=0.0), now); now += 0.05
    for _ in range(2):
        out += det.update(_snap(brake=0.0, steer=0.02), now); now += 0.05
    out += det.update(_snap(brake=0.0, steer=0.20), now)
    assert any(c.category is CueCategory.TRAIL_BRAKE for c in out)


def test_good_trail_silent():
    det = BrakingDetector()
    out, now = [], 0.0
    for _ in range(5):
        out += det.update(_snap(brake=0.9, steer=0.0), now); now += 0.05
    out += det.update(_snap(brake=0.4, steer=0.20), now)
    assert not any(c.category is CueCategory.TRAIL_BRAKE for c in out)


def test_corner_exit_not_flagged():
    det = BrakingDetector()
    out, now = [], 0.0
    for _ in range(5):
        out += det.update(_snap(throttle=0.7, steer=0.0), now); now += 0.05
    out += det.update(_snap(throttle=0.7, steer=0.20), now)
    assert not any(c.category is CueCategory.TRAIL_BRAKE for c in out)


def _straight_stop_then_turn_in(det, now=0.0):
    """The pattern that fires trail_brake: hard stop, brake dropped, then turn in."""
    out = []
    for _ in range(5):
        out += det.update(_snap(brake=0.9, steer=0.0), now); now += 0.05
    for _ in range(2):
        out += det.update(_snap(brake=0.0, steer=0.02), now); now += 0.05
    out += det.update(_snap(brake=0.0, steer=0.20), now)
    return out, now


def test_road_car_silent_on_trail_brake():
    # Braking straight then turning is correct technique on a low-downforce car;
    # the road audit (M3 E92) called all 6 of these cues false.
    det = BrakingDetector(CarClass.ROAD)
    out, _ = _straight_stop_then_turn_in(det)
    assert not any(c.category is CueCategory.TRAIL_BRAKE for c in out)


def test_downforce_classes_still_coached():
    for car_class in (CarClass.GT3, CarClass.FORMULA):
        det = BrakingDetector(car_class)
        out, _ = _straight_stop_then_turn_in(det)
        assert any(c.category is CueCategory.TRAIL_BRAKE for c in out), car_class


def test_coasting_still_fires_on_road_car():
    # Only the trail-brake cue is class-gated: dead pedal time costs metres on
    # anything, so coasting must survive the gate.
    det = BrakingDetector(CarClass.ROAD)
    out, now = [], 0.0
    for _ in range(20):
        out += det.update(_snap(brake=0.0, throttle=0.0), now)
        now += 0.05
    assert sum(c.category is CueCategory.COASTING for c in out) == 1


def test_turn_in_state_survives_a_mid_session_class_change():
    # The car can change mid-session (set_car_class). The turn-in state machine has
    # to keep stepping while the cue is off, or switching to a coached class in the
    # middle of a corner reads the corner we're already in as a fresh turn-in and
    # fires a cue for a stop that happened under the previous car.
    det = BrakingDetector(CarClass.ROAD)
    out, now = _straight_stop_then_turn_in(det)
    assert not any(c.category is CueCategory.TRAIL_BRAKE for c in out)

    det.set_car_class(CarClass.GT3)
    now += 0.05
    # Still in the same corner, still within _RECENT_BRAKE_S of that hard stop.
    out = det.update(_snap(brake=0.0, steer=0.20), now)
    assert not any(c.category is CueCategory.TRAIL_BRAKE for c in out)
