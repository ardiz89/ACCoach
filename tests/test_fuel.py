"""FuelEngineer: burn-rate tracking and laps-remaining warnings."""
from dataclasses import replace

from accoach.coaching.fuel import FuelEngineer
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.RACE,
)


def _lap(eng, fuel, now=0.0, in_pit=False, frames=10):
    out = []
    for i in range(frames):
        pos = i / frames + 0.001
        out += eng.update(replace(_BASE, lap_position=pos, fuel=fuel, in_pit=in_pit), now)
        now += 0.1
    out += eng.update(replace(_BASE, lap_position=0.01, fuel=fuel, in_pit=in_pit), now)
    return out, now + 0.1


def test_warning_sequence():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)          # baseline
    assert out == []
    out, now = _lap(eng, 9.5, now)      # burn 2.5; remaining 3.8 -> none
    assert out == []
    out, now = _lap(eng, 7.0, now)      # remaining 2.8 -> floor "2 giri"
    assert any("2 giri" in c.message for c in out)
    out, now = _lap(eng, 4.5, now)      # remaining 1.8 -> floor "1 giro"
    assert any("1 giro" in c.message for c in out)
    out, now = _lap(eng, 2.0, now)      # remaining 0.8 -> last lap
    assert any(c.category is CueCategory.FUEL and "Ultimo giro" in c.message for c in out)


def test_each_warning_once():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 9.5, now)
    out, now = _lap(eng, 7.0, now)      # remaining 2.8 -> floor "2 giri", once
    assert sum("2 giri" in c.message for c in out) == 1
    out2, now = _lap(eng, 6.0, now)     # remaining 2.4: no new threshold crossed
    assert not any("2 giri" in c.message for c in out2)


def test_refuel_resets():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 9.5, now)
    out, now = _lap(eng, 7.0, now)      # remaining 2.8 -> floor "2 giri"
    assert any("2 giri" in c.message for c in out)
    out, now = _lap(eng, 30.0, now, in_pit=True)   # refuel
    assert out == []
    out, now = _lap(eng, 27.5, now)
    f, fired = 27.5, False
    while f > 5.0:
        f -= 2.5
        out, now = _lap(eng, f, now)
        if any("3 giri" in c.message for c in out):
            fired = True
            break
    assert fired


def test_pit_lap_not_counted():
    eng = FuelEngineer()
    out, now = _lap(eng, 12.0)
    out, now = _lap(eng, 11.8, now, in_pit=True)
    assert out == []
