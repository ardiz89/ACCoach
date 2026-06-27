"""BalanceDetector: live understeer / oversteer."""
from dataclasses import replace

from accoach.coaching.balance import BalanceDetector
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=120.0,
)


def _snap(steer, yaw, speed=120.0, pos=0.3):
    return replace(_BASE, steer_angle=steer, yaw_rate=yaw, speed_kmh=speed,
                   lap_position=pos)


def _hold(det, s, frames=5, dt=0.05, start=0.0):
    out, now = [], start
    for _ in range(frames):
        out += det.update(s, now)
        now += dt
    return out, now


def test_understeer():
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.25, 0.05))
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_oversteer_opposite_lock():
    det = BalanceDetector()
    # Raw yaw_rate is signed opposite to steer in this game (see balance._YAW_SIGN);
    # oversteer = rear rotating the same RAW way as steer, caught with the wheel.
    out, _ = _hold(det, _snap(-0.15, -0.6))
    assert any(c.category is CueCategory.OVERSTEER for c in out)


def test_clean_corner_silent():
    det = BalanceDetector()
    # Clean corner: steer and RAW yaw_rate have opposite signs in this game.
    out, _ = _hold(det, _snap(0.25, -0.45), frames=10)
    assert out == []


def test_low_speed_silent():
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.30, 0.02, speed=20.0), frames=10)
    assert out == []


def test_debounce_single_frame():
    det = BalanceDetector()
    out = det.update(_snap(0.25, 0.05), 0.0)
    out += det.update(_snap(0.0, 0.4), 0.05)
    assert out == []


def test_fires_once_per_episode():
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.25, 0.05), frames=20)
    assert sum(c.category is CueCategory.UNDERSTEER for c in out) == 1
