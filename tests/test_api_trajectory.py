"""api: /api/trajectory — the driven line, corner by corner.

The geometry itself is pinned in test_trajectory.py against a circle. What is
checked here is the endpoint's own promises: that the payload carries what the
view draws, that a lap with no coordinates comes back empty instead of full of
zeroes, that the CSV is the same numbers, and that a lap path the catalog never
indexed can't be read off disk through this route either.
"""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.lap import Lap, LapSample
from accoach.recording.storage import save_lap
from accoach.telemetry.snapshot import SessionType

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _client(tmp_path, wide: int = 30):
    fast = synth.build_lap()
    fast.recorded_utc = "2026-06-20T18:00:00+00:00"
    save_lap(fast, tmp_path)
    slow = synth.build_lap(slow_corner=0, amt=wide)
    slow.recorded_utc = "2026-06-21T18:00:00+00:00"
    save_lap(slow, tmp_path)
    return TestClient(create_api(tmp_path))


def _get(c, **kw):
    params = {"car": CAR, "track": TRACK}
    params.update(kw)
    r = c.get("/api/trajectory", params=params)
    assert r.status_code == 200, r.text
    return r


def test_it_measures_every_detected_corner(tmp_path):
    j = _get(_client(tmp_path)).json()
    assert j["corners"], "the synthetic lap has two corners"
    for c in j["corners"]:
        assert set(("name", "entry_m", "apex_m", "exit_m", "extra_m",
                    "radius_m", "apex_shift_m", "tags")) <= set(c)


def test_the_corner_that_ran_wide_is_the_one_reported_wide(tmp_path):
    """synth's slow corner nudges the line outward — the report must find it
    there and nowhere else, which is the end-to-end version of the sign test."""
    j = _get(_client(tmp_path)).json()
    wide = [c for c in j["corners"] if c["widest_m"] > 1.0]
    assert len(wide) == 1
    assert wide[0]["index"] == 0
    assert j["lap"]["max_off_where"] == wide[0]["name"]
    assert j["lap"]["extra_m"] > 0, "a wider line is a longer line"


def test_each_corner_carries_both_lines_for_the_zoom(tmp_path):
    c0 = _get(_client(tmp_path)).json()["corners"][0]
    for side in ("you", "ref"):
        crop = c0["line"][side]
        assert len(crop["x"]) == len(crop["z"]) == len(crop["pos"]) > 5
        assert len(crop["speed"]) == len(crop["brake"]) == len(crop["x"])


def test_the_curvature_trace_is_served_for_both_laps(tmp_path):
    j = _get(_client(tmp_path)).json()
    for side in ("you", "ref"):
        k = j["curvature"][side]
        assert len(k["pos"]) == len(k["k"]) > 10


def test_the_tags_follow_the_requested_language(tmp_path):
    c = _client(tmp_path)
    en = _get(c, lang="en").json()["corners"][0]["tags"]
    it = _get(c, lang="it").json()["corners"][0]["tags"]
    assert en and it and en != it


def test_two_identical_laps_produce_no_tags(tmp_path):
    """Same lap on both sides of the comparison: the view must be silent rather
    than dressing up rounding noise as a finding."""
    c = _client(tmp_path)
    laps = c.get("/api/laps", params={"car": CAR, "track": TRACK}).json()
    fast = min(laps, key=lambda r: r["lap_time_ms"])["path"]
    j = _get(c, lap=fast, baseline=fast).json()
    assert j["corners"]
    assert all(not x["tags"] for x in j["corners"])


def test_a_lap_without_coordinates_comes_back_empty(tmp_path):
    """Laps recorded before schema v3 have no map. Empty, not zeroed: the view
    shows its "no coordinates" note instead of drawing a lap on top of itself."""
    flat = Lap(CAR, "nordschleife", SessionType.PRACTICE, 100000, True, samples=[
        LapSample(int(i / 200 * 100000), i / 200, 120.0, 1.0, 0.0,
                  0.3 if 40 < i < 90 else 0.0, "3", 5000, 0.0, 0.0)
        for i in range(200)])
    save_lap(flat, tmp_path)
    c = TestClient(create_api(tmp_path))
    j = _get(c, track="nordschleife").json()
    assert j["has_map"] is False
    assert j["corners"] == []


def test_csv_is_a_download_of_the_same_rows(tmp_path):
    c = _client(tmp_path)
    rows = _get(c).json()["corners"]
    r = c.get("/api/trajectory", params={"car": CAR, "track": TRACK, "fmt": "csv"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    lines = [l for l in r.text.splitlines() if l.strip()]
    assert len(lines) == len(rows) + 1          # + header
    assert lines[0].startswith("index,name,direction")
    assert lines[1].split(",")[1] == rows[0]["name"]


def test_an_unknown_lap_path_is_refused_not_read(tmp_path):
    """Same guard as the other endpoints: this app can be exposed on the LAN."""
    c = _client(tmp_path)
    r = c.get("/api/trajectory",
              params={"car": CAR, "track": TRACK, "lap": "../../etc/passwd"})
    assert r.status_code == 404


def test_the_dynamics_line_trace_still_lines_up_with_its_position_channel(tmp_path):
    """/api/analysis' line_offset moved into trajectory.py. It is plotted index
    by index against the review channels, so one value per plotted sample is not
    an implementation detail — it's the contract."""
    c = _client(tmp_path)
    a = c.get("/api/analysis", params={"car": CAR, "track": TRACK}).json()
    assert len(a["review"]["line_offset"]) == len(a["review"]["channels"]["pos"])
