"""/api/sessions — the laps of one sitting, and what moved since the one before.

The grouping rule itself is tested in ``test_sessions.py``; what's checked here
is the endpoint's judgement: which laps are allowed to set the numbers, what it
says when there is nothing to compare against, and that it never prints advice
aimed at a lap you already stopped driving.
"""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _lap(tmp_path, when, *, amt=0, corner=0, valid=True, clean=True):
    lap = synth.build_lap(slow_corner=corner, amt=amt) if amt else synth.build_lap()
    lap.recorded_utc = when
    lap.valid = valid
    lap.clean = clean
    save_lap(lap, tmp_path)
    return lap


def _client(tmp_path):
    return TestClient(create_api(tmp_path))


def _get(c, **kw):
    return c.get("/api/sessions",
                 params={"car": CAR, "track": TRACK, **kw}).json()


# --- the split into runs ---------------------------------------------------

def test_two_evenings_are_two_sessions(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    _lap(tmp_path, "2026-07-20T18:03:00+00:00", amt=20)
    _lap(tmp_path, "2026-07-27T18:00:00+00:00", amt=10)
    j = _get(_client(tmp_path))
    assert len(j["sessions"]) == 2
    assert j["current"]["laps"] == 1          # newest run is on screen


def test_you_can_ask_for_an_older_session(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    _lap(tmp_path, "2026-07-20T18:03:00+00:00", amt=20)
    _lap(tmp_path, "2026-07-27T18:00:00+00:00", amt=10)
    j = _get(_client(tmp_path), index=1)
    assert j["index"] == 1 and j["current"]["laps"] == 2


def test_an_out_of_range_index_is_clamped_not_an_error(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    j = _get(_client(tmp_path), index=99)
    assert j["index"] == 0 and j["current"] is not None


def test_no_laps_is_an_empty_answer_not_a_404(tmp_path):
    j = TestClient(create_api(tmp_path)).get(
        "/api/sessions", params={"car": CAR, "track": TRACK}).json()
    assert j["sessions"] == [] and j["current"] is None


# --- which laps may set the numbers ---------------------------------------

def test_a_cut_lap_is_listed_but_cannot_be_the_best(tmp_path):
    """It's a lap you drove — leaving it out would show a session you didn't
    have — but it's faster for a reason."""
    _lap(tmp_path, "2026-07-27T18:00:00+00:00", amt=20)          # slower, clean
    _lap(tmp_path, "2026-07-27T18:03:00+00:00", clean=False)     # faster, cut
    cur = _get(_client(tmp_path))["current"]
    assert cur["laps"] == 2 and cur["valid"] == 1
    assert cur["best_ms"] != 100000
    assert any(l["off_track"] for l in cur["laps_detail"])


def test_a_session_with_nothing_that_counts_says_so(tmp_path):
    _lap(tmp_path, "2026-07-27T18:00:00+00:00", valid=False)
    cur = _get(_client(tmp_path))["current"]
    assert cur["best_ms"] is None and cur["best_path"] is None
    assert cur["previous"] is None or cur["previous"]["delta_ms"] is None


def test_the_laps_are_listed_in_the_order_they_were_driven(tmp_path):
    _lap(tmp_path, "2026-07-27T18:00:00+00:00", amt=30)
    _lap(tmp_path, "2026-07-27T18:03:00+00:00", amt=20)
    _lap(tmp_path, "2026-07-27T18:06:00+00:00")
    detail = _get(_client(tmp_path))["current"]["laps_detail"]
    assert [l["lap_time_ms"] for l in detail] == sorted(
        [l["lap_time_ms"] for l in detail], reverse=True)
    assert detail[-1]["is_best"]


# --- comparison with the run before ---------------------------------------

def test_the_first_session_has_nothing_to_compare_with(tmp_path):
    _lap(tmp_path, "2026-07-27T18:00:00+00:00")
    assert _get(_client(tmp_path))["current"]["previous"] is None


def test_a_faster_session_reports_a_negative_delta(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00", amt=40)
    _lap(tmp_path, "2026-07-27T18:00:00+00:00")
    prev = _get(_client(tmp_path))["current"]["previous"]
    assert prev["delta_ms"] < 0
    assert prev["best_ms"] > 100000


def test_improvements_carry_no_advice(tmp_path):
    """Reversing the comparison names what the *older* lap did wrong. Printed
    under "you got faster here" that's an instruction aimed at a lap you already
    stopped driving."""
    _lap(tmp_path, "2026-07-20T18:00:00+00:00", corner=0, amt=40)
    _lap(tmp_path, "2026-07-27T18:00:00+00:00")
    prev = _get(_client(tmp_path))["current"]["previous"]
    assert prev["improved"], "the newer lap is faster somewhere"
    for row in prev["improved"]:
        assert "message" not in row
        assert row["label"] and row["gain_s"] > 0


def test_corners_that_went_backwards_do_carry_the_advice(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    _lap(tmp_path, "2026-07-27T18:00:00+00:00", corner=0, amt=40)
    prev = _get(_client(tmp_path))["current"]["previous"]
    assert prev["regressed"]
    assert all("message" in r and r["message"] for r in prev["regressed"])


def test_a_corner_that_barely_moved_is_not_reported(tmp_path):
    """Inside the spread of one driver's own laps; calling it progress would be
    flattering rather than true."""
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    _lap(tmp_path, "2026-07-27T18:00:00+00:00")     # identical synthetic lap
    prev = _get(_client(tmp_path))["current"]["previous"]
    assert prev["improved"] == [] and prev["regressed"] == []


def test_an_unreadable_previous_lap_does_not_break_the_view(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00", amt=40)
    _lap(tmp_path, "2026-07-27T18:00:00+00:00")
    for f in sorted(tmp_path.glob("*.json.gz"))[:1]:
        f.write_bytes(b"not a lap")
    cur = _get(_client(tmp_path))["current"]
    assert cur is not None
    if cur["previous"]:
        assert cur["previous"]["improved"] == []
        assert cur["previous"]["regressed"] == []
