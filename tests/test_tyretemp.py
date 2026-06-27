"""TyreTempAdvisor: overdriving / temperature-window advice."""
from dataclasses import replace

from accoach.coaching.tyretemp import TyreTempAdvisor, _COOLDOWN_LAPS
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    max_rpm=8000,
)
_FRAMES = 50


def _drive_lap(adv, temp, now=0.0, speed=160.0):
    out = []
    for i in range(_FRAMES):
        s = replace(_BASE, lap_position=i / _FRAMES + 0.001,
                    tyre_core_temp=(temp,) * 4, speed_kmh=speed)
        out += adv.update(s, now)
        now += 0.05
    s = replace(_BASE, lap_position=0.01, tyre_core_temp=(temp,) * 4, speed_kmh=speed)
    out += adv.update(s, now)
    return out, now + 0.05


def test_hot_tyres_overdriving():
    adv = TyreTempAdvisor()
    out, _ = _drive_lap(adv, 98.0)
    assert len(out) == 1 and out[0].category is CueCategory.TYRE_TEMP
    assert "troppo calde" in out[0].message


def test_cold_tyres():
    adv = TyreTempAdvisor()
    out, _ = _drive_lap(adv, 62.0)
    assert len(out) == 1 and "fredde" in out[0].message


def test_in_window_silent():
    adv = TyreTempAdvisor()
    out, _ = _drive_lap(adv, 82.0)
    assert out == []


def test_cooldown():
    adv = TyreTempAdvisor()
    out, now = _drive_lap(adv, 98.0)
    assert len(out) == 1
    for _ in range(_COOLDOWN_LAPS - 1):
        out, now = _drive_lap(adv, 98.0, now)
        assert out == []
    out, now = _drive_lap(adv, 98.0, now)
    assert len(out) == 1
