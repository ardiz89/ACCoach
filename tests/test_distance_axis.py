"""The lap measured in metres — the channel every chart's x-axis is labelled from.

Position arrives from the game as a fraction of the lap, and "50%" is a number
you have to convert before you can drive to it. Turning it into metres is only
worth doing if the metres are real, so the interesting tests here are the ones
about *not* answering: a lap whose coordinates disagree with its own speedometer
gets no distance at all, and the charts fall back to per cent.

That guard is not hypothetical. Six laps in the user's archive (Nürburgring, AC1,
recorded before the coordinate fix of 2026-06-28) describe a 5 km lap with 167 m
of geometry. Without the cross-check they would have been drawn with an axis
running to 150 m and no hint that anything was wrong.
"""
import math

from fastapi.testclient import TestClient

from accoach.api import _distance_channel, _pick_indices, _points, create_api
from accoach.recording.storage import save_lap
from accoach.trajectory import LinePoint, cumulative_distance

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _pt(x, z):
    return LinePoint(0.0, x, z, 0.0, 0.0)


def _clock_metres(samples) -> float:
    """Distance from speed × time — the second, independent measure."""
    out = 0.0
    for i in range(1, len(samples)):
        dt = (samples[i].t_ms - samples[i - 1].t_ms) / 1000.0
        if 0.0 < dt < 1.0:
            out += (samples[i].speed_kmh + samples[i - 1].speed_kmh) / 7.2 * dt
    return out


def _consistent(lap):
    """The synthetic lap with its outline scaled to match its own speeds.

    tests/synth.py draws a 1.8 km circuit and then drives round it at 255 km/h
    for 100 s: fine for everything that reads position, speed or time, and wrong
    for the one thing measured here. Scaling only the coordinates leaves the rest
    of the fixture — and every other test built on it — exactly as it was.
    """
    geo = cumulative_distance(_points(lap.samples))[-1]
    k = _clock_metres(lap.samples) / geo
    for s in lap.samples:
        s.car_x *= k
        s.car_z *= k
    return lap


# --- the measurement itself -------------------------------------------------

def test_distance_is_the_ground_covered():
    """A right-angled path of 3 m then 4 m is 7 m of driving, not 5 m of crow."""
    d = cumulative_distance([_pt(0, 0), _pt(3, 0), _pt(3, 4)])
    assert d == [0.0, 3.0, 7.0]


def test_distance_never_goes_backwards():
    pts = [_pt(math.cos(a / 20) * 50, math.sin(a / 20) * 50) for a in range(40)]
    d = cumulative_distance(pts)
    assert all(b >= a for a, b in zip(d, d[1:]))


def test_a_teleport_is_not_driving():
    """A pit reset jumps the car across the map between two frames. Counting it
    would print a kilometre nobody drove on the axis of every chart."""
    d = cumulative_distance([_pt(0, 0), _pt(10, 0), _pt(4000, 0), _pt(4010, 0)])
    assert d == [0.0, 10.0, 10.0, 20.0]


def test_a_lap_without_coordinates_measures_zero():
    """Not "the start line": zero here means there is no distance to show."""
    assert cumulative_distance([_pt(0, 0)] * 50)[-1] == 0.0


# --- believing it -----------------------------------------------------------

def test_coordinates_that_agree_with_the_clock_are_used():
    lap = _consistent(synth.build_lap())
    d = _distance_channel(lap)
    assert len(d) == len(lap.samples)
    assert abs(d[-1] - _clock_metres(lap.samples)) / d[-1] < 0.01


def test_coordinates_that_contradict_the_speedometer_are_refused():
    """The archive's broken laps, in miniature: a lap whose outline says 500 m
    while its speed and its clock say 5 km. One of the two is wrong, and there is
    no way to tell which — so the axis says nothing rather than something."""
    lap = _consistent(synth.build_lap())
    for s in lap.samples:            # shrink the circuit, leave the driving
        s.car_x /= 10.0
        s.car_z /= 10.0
    assert set(_distance_channel(lap)) == {0.0}


def test_the_refusal_is_not_a_hair_trigger():
    """Real laps agree to 0.1%; a 1% error is still the same lap and must pass,
    or the fallback would swallow every lap ever recorded."""
    lap = _consistent(synth.build_lap())
    for s in lap.samples:
        s.car_x *= 1.01
        s.car_z *= 1.01
    assert _distance_channel(lap)[-1] > 0.0


# --- what the browser gets --------------------------------------------------

def _client(tmp_path, n: int = 401):
    fast = _consistent(synth.build_lap(n=n))
    fast.recorded_utc = "2026-06-20T18:00:00+00:00"
    save_lap(fast, tmp_path)
    slow = _consistent(synth.build_lap(slow_corner=0, amt=30, n=n))
    slow.recorded_utc = "2026-06-21T18:00:00+00:00"
    save_lap(slow, tmp_path)
    return TestClient(create_api(tmp_path))


def _analysis(tmp_path, n: int = 401):
    r = _client(tmp_path, n).get("/api/analysis", params={"car": CAR, "track": TRACK})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_distance_channel_lines_up_with_the_position_channel(tmp_path):
    """One value per plotted frame: the frontend interpolates between the pairs,
    and a channel one frame out of register would shift the whole axis."""
    for side in ("review", "reference"):
        ch = _analysis(tmp_path)[side]["channels"]
        assert len(ch["dist_m"]) == len(ch["pos"])
        assert ch["dist_m"][0] == 0.0
        assert ch["dist_m"][-1] > 1000.0


def test_the_axis_is_measured_at_full_rate_not_over_the_plotting_points(tmp_path):
    """Accumulating over the ~600 points the browser gets would cut every corner
    into chords and quietly report a shorter lap than the Trajectory tab does."""
    ch = _analysis(tmp_path, n=2001)["review"]["channels"]   # thinned to 600
    assert len(ch["pos"]) == 600
    chords = sum(math.hypot(ch["x"][i] - ch["x"][i - 1], ch["z"][i] - ch["z"][i - 1])
                 for i in range(1, len(ch["x"])))
    assert ch["dist_m"][-1] > chords


def test_thinning_keeps_the_frames_the_other_channels_use():
    """_pick_indices is shared with _downsample; if they ever disagree, every
    chart is plotted against somebody else's distance."""
    assert _pick_indices(3) == [0, 1, 2]
    assert len(_pick_indices(10_000)) == 600
    assert _pick_indices(10_000)[0] == 0


def test_a_lost_corner_carries_its_number(tmp_path):
    """The Trajectory view writes the debrief's sentence onto its drawing, and
    matches it to the corner by number — names are curated per track and two of
    them can read alike."""
    losses = _analysis(tmp_path)["losses"]
    assert losses, "the slow lap loses time somewhere"
    corners = {c["index"] for c in _analysis(tmp_path)["corners"]}
    for l in losses:
        assert l["index"] in corners
