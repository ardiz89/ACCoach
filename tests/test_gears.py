"""GearDetector: limiter bounce and lugging too tall a gear."""
from dataclasses import replace

from accoach.coaching.gears import GearDetector
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    max_rpm=8000,
)


def _snap(rpm, gear, throttle=1.0, speed=120.0, pos=0.3):
    return replace(_BASE, rpm=rpm, gear=gear, throttle=throttle,
                   speed_kmh=speed, lap_position=pos)


def _hold(det, s, frames=10, dt=0.05, start=0.0):
    out, now = [], start
    for _ in range(frames):
        out += det.update(s, now)
        now += dt
    return out, now


def test_limiter_when_taller_gear_exists():
    det = GearDetector()
    out, now = _hold(det, _snap(7990, "6", speed=250.0))   # learn 6th exists
    assert out == []
    out, _ = _hold(det, _snap(7990, "4", speed=180.0), start=now)
    assert any(c.category is CueCategory.LIMITER for c in out)


def test_bog_too_tall():
    det = GearDetector()
    out, _ = _hold(det, _snap(3000, "5", throttle=1.0, speed=90.0))
    assert any(c.category is CueCategory.GEAR_TOO_TALL for c in out)


def test_healthy_rpm_silent():
    det = GearDetector()
    out, _ = _hold(det, _snap(6000, "4", throttle=1.0, speed=150.0))
    assert out == []


def test_standing_start_not_bog():
    det = GearDetector()
    out, _ = _hold(det, _snap(3000, "1", throttle=1.0, speed=20.0))
    assert out == []
