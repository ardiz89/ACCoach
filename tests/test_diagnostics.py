"""Diagnostics formatting/verdict helpers (the live loops aren't unit-tested)."""
from dataclasses import replace

from accoach.diagnostics import _live_line, _sectors_verdict, _yaw_verdict
from accoach.telemetry.snapshot import TelemetrySnapshot


def test_live_line_formats_without_error():
    s = replace(
        TelemetrySnapshot.disconnected(),
        connected=True, speed_kmh=212.4, gear="5", rpm=7200, max_rpm=8000,
        throttle=1.0, brake=0.0, steer_angle=-0.18, yaw_rate=0.42,
        slip_ratio=(-0.30, -0.10, 0.05, 0.20),
        abs_active=0.0, tc_active=0.3, tc_level=4, abs_level=3, brake_bias=0.61,
    )
    line = _live_line(s)
    assert "212" in line and "0.61" in line
    assert " 4  3" in line          # tc_level / abs_level columns


def test_live_line_handles_unknown_aids():
    s = replace(TelemetrySnapshot.disconnected(), connected=True,
                max_rpm=0, tc_level=-1, abs_level=-1, brake_bias=-1.0)
    line = _live_line(s)            # must not raise on -1 / zero max_rpm
    assert "--" in line             # brake bias shown as placeholder


def test_yaw_verdict_runs(capsys):
    # Just exercise each branch; it prints, returns None.
    _yaw_verdict(agree=90, disagree=5, left_seen=40, right_seen=55)
    assert "CORRECT" in capsys.readouterr().out
    _yaw_verdict(agree=5, disagree=90, left_seen=40, right_seen=55)
    assert "_YAW_SIGN = -1.0" in capsys.readouterr().out
    _yaw_verdict(agree=2, disagree=2, left_seen=2, right_seen=2)
    assert "not enough" in capsys.readouterr().out


def test_sectors_verdict_runs(capsys):
    # All three sectors seen, count matches -> confirmed.
    _sectors_verdict({"count": 3, "seen": {0, 1, 2}, "valid": 900,
                      "bounds": {1: 0.31, 2: 0.66}, "prev": 2})
    assert "✓" in capsys.readouterr().out
    # current_sector never read -> offset wrong.
    _sectors_verdict({"count": 0, "seen": set(), "valid": 0,
                      "bounds": {}, "prev": None})
    assert "sempre -1" in capsys.readouterr().out
    # Indices read but sector_count is 0 -> works via transitions.
    _sectors_verdict({"count": 0, "seen": {0, 1, 2}, "valid": 500,
                      "bounds": {1: 0.3, 2: 0.6}, "prev": 2})
    assert "sector_count è 0" in capsys.readouterr().out
