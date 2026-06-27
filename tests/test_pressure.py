"""PressureAdvisor: lap-aggregated hot-pressure advice."""
from dataclasses import replace

from accoach.coaching.pressure import PressureAdvisor, _COOLDOWN_LAPS
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=180.0,
)
_FRAMES = 50   # comfortably above PressureAdvisor._MIN_SAMPLES


def _snap(pos, press, temp=85.0, speed=180.0, in_pit=False):
    return replace(_BASE, lap_position=pos, tyre_pressure=press,
                   tyre_core_temp=(temp,) * 4, speed_kmh=speed, in_pit=in_pit)


def _drive_lap(adv, press, now=0.0, temp=85.0, speed=180.0):
    out = []
    for i in range(_FRAMES):
        out += adv.update(_snap(i / _FRAMES + 0.001, press, temp, speed), now)
        now += 0.05
    out += adv.update(_snap(0.01, press, temp, speed), now)
    return out, now


def test_high_fronts():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (29.2, 29.0, 27.4, 27.5))
    assert len(out) == 1 and out[0].category is CueCategory.TYRE_PRESSURE
    assert "anteriori" in out[0].message and "troppo alte" in out[0].message
    assert "1.6 psi" in out[0].message


def test_low_rears():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (27.5, 27.4, 26.0, 26.2))
    assert len(out) == 1 and "posteriori" in out[0].message
    assert "troppo basse" in out[0].message


def test_in_window_silent():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (27.5, 27.6, 27.4, 27.3))
    assert out == []


def test_cold_tyres_silent():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (24.0, 24.1, 24.0, 23.9), temp=30.0)
    assert out == []


def test_under_temp_tyres_silent():
    # Tyres warming but not yet at operating temp (68 C): pressure reads low, but
    # advising "+pressure" here would be wrong — it comes up once hot. Stay quiet.
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (24.5, 24.6, 24.4, 24.5), temp=68.0)
    assert out == []


def test_picks_worst_axle():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (28.9, 28.9, 24.5, 24.5))
    assert "posteriori" in out[0].message


def test_pit_lap_silent():
    adv = PressureAdvisor()
    now = 0.0
    for i in range(_FRAMES):
        adv.update(_snap(i / _FRAMES + 0.001, (29.5,) * 4, in_pit=True), now)
        now += 0.05
    out = adv.update(_snap(0.01, (29.5,) * 4, in_pit=True), now)
    assert out == []


def test_cooldown():
    adv = PressureAdvisor()
    p = (29.2, 29.0, 27.4, 27.5)
    out, now = _drive_lap(adv, p)
    assert len(out) == 1
    for _ in range(_COOLDOWN_LAPS - 1):
        out, now = _drive_lap(adv, p, now)
        assert out == []
    out, now = _drive_lap(adv, p, now)
    assert len(out) == 1


def test_slow_lap_no_samples():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (29.2, 29.0, 27.4, 27.5), speed=40.0)
    assert out == []
