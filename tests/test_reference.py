"""Reference: monotonic position index + linear interpolation over a lap."""
from accoach.comparison.reference import Reference
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType

import synth


def _lap(samples):
    return Lap("c", "t", SessionType.PRACTICE, 100000, True, samples=samples)


def _smp(pos, t_ms, speed=100.0, **kw):
    return LapSample(t_ms=int(t_ms), pos=pos, speed_kmh=speed, throttle=1.0,
                     brake=0.0, steer_angle=0.0, gear="4", rpm=8000,
                     g_lat=0.0, g_long=0.0, **kw)


def test_needs_two_points_to_be_usable():
    assert not Reference(_lap([])).usable
    assert not Reference(_lap([_smp(0.1, 0)])).usable
    assert Reference(_lap([_smp(0.1, 0), _smp(0.2, 100)])).usable


def test_drops_non_forward_samples():
    # Positions that stall or go backwards must be filtered for a monotonic index.
    lap = _lap([_smp(0.1, 0), _smp(0.1, 50), _smp(0.05, 60), _smp(0.3, 200)])
    ref = Reference(lap)
    assert ref._pos == [0.1, 0.3]


def test_time_at_interpolates_linearly():
    lap = _lap([_smp(0.0, 0), _smp(0.5, 1000), _smp(1.0, 3000)])
    ref = Reference(lap)
    assert ref.time_at(0.0) == 0.0
    assert ref.time_at(0.5) == 1000.0
    assert ref.time_at(0.25) == 500.0          # halfway in first span
    assert ref.time_at(0.75) == 2000.0         # halfway in second span


def test_time_at_clamps_outside_range():
    lap = _lap([_smp(0.2, 100), _smp(0.8, 700)])
    ref = Reference(lap)
    assert ref.time_at(0.0) == 100.0           # below first -> first
    assert ref.time_at(1.0) == 700.0           # above last -> last


def test_point_at_interpolates_channels_and_picks_gear():
    lap = _lap([
        _smp(0.0, 0, speed=100.0, abs_active=0.0),
        _smp(1.0, 1000, speed=200.0, abs_active=1.0),
    ])
    # second sample needs a different gear to test the nearest-gear pick
    lap.samples[1] = _smp(1.0, 1000, speed=200.0, abs_active=1.0)
    lap.samples[0].gear = "2"
    lap.samples[1].gear = "5"
    ref = Reference(lap)
    p = ref.point_at(0.5)
    assert p.speed_kmh == 150.0
    assert p.abs_active == 0.5
    assert p.gear == "5"                       # frac >= 0.5 -> later sample


def test_point_at_on_real_lap_tracks_speed_dip():
    ref = Reference(synth.build_lap())
    apex = ref.point_at(0.31)
    straight = ref.point_at(0.05)
    assert apex.speed_kmh < straight.speed_kmh   # apex is slower than the straight
    assert apex.brake >= 0.0
