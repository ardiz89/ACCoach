"""Regression guards for the thresholds calibrated against live AC1 GT3 data
(McLaren MP4-12C, Imola, 2026-06-26). These pin the values so a later edit can't
silently revert them.

Measured that day: abs/tc channels read constant garbage (~0.12/0.10), so the
slip-ratio fallback does all the lock/spin work; hardest deliberate lock reached
front slip -0.225 (typical hard braking -0.073); biggest wheelspin +0.138
(typical traction +0.071); clean fast corners ran yaw/steer ~1.9.
"""
from dataclasses import replace

from accoach.coaching.events import EventDetector
from accoach.coaching.balance import BalanceDetector
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=140.0, abs_active=0.12, tc_active=0.10,   # AC1 constant-garbage aids
)


def _hold(det, s, frames=8, dt=0.02):
    out, now = [], 0.0
    for _ in range(frames):
        out += det.update(s, now)
        now += dt
    return out


# ---- lock-up (slip-only, since abs is stuck at 0.12) ----
def test_lockup_fires_on_real_lock():
    det = EventDetector()
    s = replace(_BASE, brake=0.8, slip_ratio=(-0.18, -0.18, 0.0, 0.0))
    out = _hold(det, s)
    assert any(c.category is CueCategory.LOCKED for c in out)


def test_lockup_silent_on_normal_hard_braking():
    det = EventDetector()
    # Typical hard braking sat at ~-0.073; must not be called a lock-up.
    s = replace(_BASE, brake=0.8, slip_ratio=(-0.08, -0.07, 0.0, 0.0))
    out = _hold(det, s)
    assert not any(c.category is CueCategory.LOCKED for c in out)


# ---- wheelspin (slip-only, since tc is stuck at 0.10) ----
def test_wheelspin_fires_on_real_spin():
    det = EventDetector()
    s = replace(_BASE, throttle=0.9, gear="3", slip_ratio=(0.0, 0.0, 0.12, 0.12))
    out = _hold(det, s)
    assert any(c.category is CueCategory.WHEELSPIN for c in out)


def test_wheelspin_silent_on_normal_traction():
    det = EventDetector()
    s = replace(_BASE, throttle=0.9, gear="3", slip_ratio=(0.0, 0.0, 0.06, 0.06))
    out = _hold(det, s)
    assert not any(c.category is CueCategory.WHEELSPIN for c in out)


# ---- understeer (yaw/steer ratio model) ----
def test_understeer_fires_on_low_ratio_corner():
    det = BalanceDetector()
    # Genuinely cornering (steer 0.25) but rotating little: ratio 0.18/0.25=0.72.
    s = replace(_BASE, steer_angle=0.25, yaw_rate=0.18)
    out = _hold(det, s, frames=12)
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_understeer_silent_on_normal_corner():
    det = BalanceDetector()
    # Normal rotation: ratio 0.50/0.25 = 2.0 (above the ~1.9 norm) -> no push.
    s = replace(_BASE, steer_angle=0.25, yaw_rate=0.50)
    out = _hold(det, s, frames=12)
    assert not any(c.category is CueCategory.UNDERSTEER for c in out)
