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
    # The forward samples are 0.1 and 0.3; a finish-line anchor at pos=1.0 (t=lap
    # time) is then appended so time_at doesn't freeze on the run-in to the line.
    lap = _lap([_smp(0.1, 0), _smp(0.1, 50), _smp(0.05, 60), _smp(0.3, 200)])
    ref = Reference(lap)
    assert ref._pos == [0.1, 0.3, 1.0]


def test_time_at_interpolates_linearly():
    lap = _lap([_smp(0.0, 0), _smp(0.5, 1000), _smp(1.0, 3000)])
    ref = Reference(lap)
    assert ref.time_at(0.0) == 0.0
    assert ref.time_at(0.5) == 1000.0
    assert ref.time_at(0.25) == 500.0          # halfway in first span
    assert ref.time_at(0.75) == 2000.0         # halfway in second span


def test_anchors_endpoints_at_the_line():
    # Real samples start after the line and end before it; the index is anchored at
    # pos=0 (t=0) and pos=1 (t=lap_time) so the live delta doesn't freeze on the
    # run-in to the finish (it would otherwise clamp to the last sample's time).
    lap = _lap([_smp(0.2, 100), _smp(0.8, 700)])     # lap_time_ms = 100000
    ref = Reference(lap)
    assert ref._pos[0] == 0.0 and ref._pos[-1] == 1.0
    assert ref.time_at(0.0) == 0.0                    # anchored start
    assert ref.time_at(1.0) == 100000.0              # anchored to the lap time


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


def test_comparator_skips_the_lap_wrap_frame():
    # At the line, pos resets before the lap timer (or vice-versa) for one frame;
    # the delta would spike by ~a full lap. That frame must be skipped.
    from accoach.comparison.delta import LapComparator

    cmp = LapComparator(Reference(synth.build_lap()))   # lap_time_ms = 100000
    wrap = synth.snap(pos=0.01, current_lap_ms=99000)   # pos reset, timer hasn't
    assert cmp.compare(wrap) is None
    normal = synth.snap(pos=0.5, current_lap_ms=45000)  # a clean mid-lap frame
    assert cmp.compare(normal) is not None


def test_local_delta_tracks_recent_gain_or_loss():
    # The local delta is the cumulative delta now minus ~one window of track back:
    # it says whether you're gaining or losing *right now*, not over the whole lap.
    from accoach.comparison.delta import LapComparator

    ref = Reference(synth.build_lap())                   # lap_time_ms = 100000
    cmp = LapComparator(ref)
    # Walk the lap losing a growing amount of time vs the reference.
    last = None
    for i in range(1, 40):
        pos = i / 50.0
        extra = i * 30                                   # falling further behind
        last = cmp.compare(synth.snap(pos=pos, current_lap_ms=int(ref.time_at(pos)) + extra))
    assert last is not None
    assert last.local_delta_ms > 0.0                     # losing time right now
    assert last.local_losing is True
    # A new lap resets the rolling window (no stale carry-over).
    fresh = cmp.compare(synth.snap(pos=0.02, current_lap_ms=int(ref.time_at(0.02))))
    assert fresh.local_delta_ms == 0.0


def test_point_at_on_real_lap_tracks_speed_dip():
    ref = Reference(synth.build_lap())
    apex = ref.point_at(0.31)
    straight = ref.point_at(0.05)
    assert apex.speed_kmh < straight.speed_kmh   # apex is slower than the straight
    assert apex.brake >= 0.0
