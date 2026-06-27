"""Telemetry plumbing for the new aid levels: plausibility guards + payload."""
from dataclasses import replace

from accoach.telemetry.reader import SharedMemoryReader
from accoach.telemetry.snapshot import TelemetrySnapshot
from accoach.serialize import snapshot_to_dict


def test_aid_level_clamps_out_of_range():
    f = SharedMemoryReader._aid_level
    assert f(0) == 0
    assert f(4) == 4
    assert f(20) == 20
    assert f(-1) == -1        # AC zero-pad / garbage
    assert f(999) == -1
    assert f(-5) == -1


def test_brake_bias_plausibility():
    f = SharedMemoryReader._brake_bias
    assert f(0.62) == 0.62
    assert f(0.0) == -1.0     # implausible (AC tail garbage)
    assert f(1.5) == -1.0
    assert f(0.1) == 0.1
    assert f(0.9) == 0.9


def test_disconnected_defaults_are_unknown():
    s = TelemetrySnapshot.disconnected()
    assert s.tc_level == -1 and s.abs_level == -1
    assert s.engine_map == -1 and s.brake_bias == -1.0


def test_serialize_exposes_aids_block():
    s = replace(TelemetrySnapshot.disconnected(),
                connected=True, tc_level=4, abs_level=3, engine_map=2)
    d = snapshot_to_dict(s)
    assert d["aids"] == {"tc": 4, "abs": 3, "engine_map": 2}
