"""Lap / LapSample model: serialization round-trip and version tolerance."""
from dataclasses import replace

from accoach.recording.lap import SAMPLE_FIELDS, SCHEMA_VERSION, Lap, LapSample
from accoach.telemetry.snapshot import SessionType

import synth


def test_sample_from_snapshot_maps_channels():
    s = synth.snap(
        pos=0.4, speed_kmh=180.0, throttle=0.7, brake=0.1, steer_angle=-0.2,
        gear="5", rpm=7200, accel_g=(1.2, 0.0, -0.8), yaw_rate=0.3,
        wheel_slip=(0.1, 0.2, 0.3, 0.4), abs_active=0.5, tc_active=0.6,
        tyre_core_temp=(90.0, 91.0, 92.0, 93.0), current_lap_ms=12345,
    )
    smp = LapSample.from_snapshot(s)
    assert smp.t_ms == 12345
    assert smp.pos == 0.4
    assert smp.gear == "5"
    assert smp.g_lat == 1.2 and smp.g_long == -0.8     # accel_g[0] / accel_g[2]
    assert smp.wheel_slip == (0.1, 0.2, 0.3, 0.4)
    assert smp.tyre_core_temp == (90.0, 91.0, 92.0, 93.0)


def test_lap_dict_roundtrip_preserves_samples():
    lap = synth.build_lap(n=50)
    lap.recorded_utc = "2026-06-26T18:00:00+00:00"
    back = Lap.from_dict(lap.to_dict())
    assert back.car_model == lap.car_model and back.track == lap.track
    assert back.session == lap.session
    assert back.lap_time_ms == lap.lap_time_ms
    assert back.valid == lap.valid
    assert back.recorded_utc == lap.recorded_utc
    assert len(back.samples) == len(lap.samples)
    a, b = lap.samples[10], back.samples[10]
    # as_row() rounds pos to 5 decimals on the way out.
    assert round(a.pos, 5) == b.pos and a.gear == b.gear
    assert round(a.speed_kmh, 2) == round(b.speed_kmh, 2)


def test_to_dict_is_self_describing():
    d = synth.build_lap(n=5).to_dict()
    assert d["schema"] == SCHEMA_VERSION
    assert d["fields"] == list(SAMPLE_FIELDS)
    assert len(d["samples"][0]) == len(SAMPLE_FIELDS)


def test_from_named_defaults_missing_channels_to_zero():
    # A v1-style file: only the first 10 columns, no slip/abs/tc/yaw/tyre.
    fields = list(SAMPLE_FIELDS[:10])
    row = [1000, 0.5, 200.0, 1.0, 0.0, 0.1, "4", 7000, 0.5, -0.3]
    smp = LapSample.from_named(fields, row)
    assert smp.t_ms == 1000 and smp.gear == "4"
    assert smp.wheel_slip == (0.0, 0.0, 0.0, 0.0)   # absent -> zero
    assert smp.abs_active == 0.0 and smp.yaw_rate == 0.0
    assert smp.tyre_core_temp == (0.0, 0.0, 0.0, 0.0)


def test_from_dict_loads_legacy_v1_without_fields_list():
    legacy = {
        "car_model": "x", "track": "y", "session": 0,
        "lap_time_ms": 90000, "valid": True,
        # no "fields", no "schema": the v1 column order must be assumed
        "samples": [[0, 0.0, 100.0, 1.0, 0.0, 0.0, "3", 6000, 0.0, 0.0]],
    }
    lap = Lap.from_dict(legacy)
    assert lap.schema_version == 1
    assert len(lap.samples) == 1
    assert lap.samples[0].speed_kmh == 100.0
    assert lap.samples[0].wheel_slip == (0.0, 0.0, 0.0, 0.0)


def test_car_xz_roundtrip():
    s = synth.snap(pos=0.5, car_x=123.45, car_z=-67.89, current_lap_ms=1000)
    smp = LapSample.from_snapshot(s)
    assert smp.car_x == 123.45 and smp.car_z == -67.89
    back = LapSample.from_named(list(SAMPLE_FIELDS), smp.as_row())
    assert round(back.car_x, 2) == 123.45 and round(back.car_z, 2) == -67.89


def test_v2_lap_without_coords_loads_with_zero():
    # A v2 file (no car_x/car_z columns) must still load, coords defaulting to 0.
    fields = list(SAMPLE_FIELDS[:21])   # everything up to tyre_rr, no car_x/car_z
    row = [0, 0.5, 100.0, 1.0, 0.0, 0.0, "4", 6000, 0.0, 0.0,
           0, 0, 0, 0, 0, 0, 0, 80, 80, 80, 80]
    smp = LapSample.from_named(fields, row)
    assert smp.car_x == 0.0 and smp.car_z == 0.0


def test_current_sector_roundtrip():
    s = synth.snap(pos=0.5, current_sector=2, current_lap_ms=1000)
    smp = LapSample.from_snapshot(s)
    assert smp.current_sector == 2
    back = LapSample.from_named(list(SAMPLE_FIELDS), smp.as_row())
    assert back.current_sector == 2


def test_v3_lap_without_sector_loads_as_unknown():
    # A v3 file (through car_z, no current_sector column) loads with sector -1.
    fields = list(SAMPLE_FIELDS[:23])   # up to car_z, no current_sector
    row = [0, 0.5, 100.0, 1.0, 0.0, 0.0, "4", 6000, 0.0, 0.0,
           0, 0, 0, 0, 0, 0, 0, 80, 80, 80, 80, 12.3, -4.5]
    smp = LapSample.from_named(fields, row)
    assert smp.current_sector == -1
    assert smp.car_x == 12.3 and smp.car_z == -4.5


def test_from_dict_tolerates_bad_session():
    lap = Lap.from_dict({"session": 999, "samples": []})
    assert lap.session == SessionType.UNKNOWN


def test_duration_s():
    lap = replace(synth.build_lap(n=2), lap_time_ms=83456)
    assert lap.duration_s == 83.456


def test_clean_and_conditions_roundtrip():
    lap = replace(synth.build_lap(n=5, clean=True, compound="dry_compound"),
                  air_temp=24.5, road_temp=33.2, grip=0.98)
    back = Lap.from_dict(lap.to_dict())
    assert back.clean is True
    assert back.tyre_compound == "dry_compound"
    assert back.air_temp == 24.5 and back.road_temp == 33.2 and back.grip == 0.98


def test_clean_false_roundtrip():
    back = Lap.from_dict(synth.build_lap(n=5, clean=False).to_dict())
    assert back.clean is False


def test_legacy_lap_without_clean_is_unknown_not_dirty():
    # A pre-v5 file has no "clean" key: it must load as None (unknown), never
    # False — so it stays eligible as a reference instead of being discarded.
    legacy = {
        "car_model": "x", "track": "y", "session": 0,
        "lap_time_ms": 90000, "valid": True,
        "samples": [[0, 0.0, 100.0, 1.0, 0.0, 0.0, "3", 6000, 0.0, 0.0]],
    }
    lap = Lap.from_dict(legacy)
    assert lap.clean is None
    assert lap.air_temp == 0.0 and lap.tyre_compound == ""
