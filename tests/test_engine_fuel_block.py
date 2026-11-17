"""Il blocco carburante dello stato dal vivo (sezione C): litri, percentuale, giri."""
from dataclasses import replace

from accoach.coaching.fuel import FuelEngineer, fuel_block
from accoach.telemetry.snapshot import ACStatus, TelemetrySnapshot

_BASE = replace(TelemetrySnapshot.disconnected(), connected=True, status=ACStatus.LIVE)


def _engineer_with_burn(per_lap):
    eng = FuelEngineer()
    eng._burns = [per_lap]
    return eng


def test_block_has_litres_pct_and_laps():
    eng = _engineer_with_burn(2.5)
    b = fuel_block(eng, replace(_BASE, fuel=24.5, max_fuel=60.0))
    assert b == {"litres": 24.5, "pct": 41, "laps": 9}


def test_pct_is_null_without_capacity():
    b = fuel_block(_engineer_with_burn(2.5), replace(_BASE, fuel=24.5, max_fuel=0.0))
    assert b["pct"] is None and b["laps"] == 9 and b["litres"] == 24.5


def test_laps_is_null_until_a_burn_is_measured():
    b = fuel_block(FuelEngineer(), replace(_BASE, fuel=24.5, max_fuel=60.0))
    assert b["laps"] is None and b["pct"] == 41


def test_whole_block_is_null_when_the_game_is_not_live():
    assert fuel_block(FuelEngineer(), TelemetrySnapshot.disconnected()) is None
