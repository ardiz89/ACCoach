"""BrakingDetector: coasting and trail-braking faults."""
from dataclasses import replace

from accoach.coaching.braking import BrakingDetector
from accoach.coaching.cue import CueCategory
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
