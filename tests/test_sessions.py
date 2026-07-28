"""Grouping laps back into the runs they were driven in.

The rule is a heuristic on timestamps, so what matters is that it errs in the
direction it claims to: splitting one long stint is acceptable, merging two
evenings is not — a merged pair averages lap times across different track
temperatures and calls the result your consistency.
"""
from datetime import datetime, timedelta, timezone

from accoach.sessions import SESSION_GAP_S, group_sessions, parse_utc

_T0 = datetime(2026, 7, 28, 18, 0, tzinfo=timezone.utc)


def _lap(minutes, ms=120_000, valid=1, clean=1, **kw):
    return {"path": f"lap_{minutes}.json.gz", "lap_time_ms": ms,
            "valid": valid, "clean": clean,
            "recorded_utc": (_T0 + timedelta(minutes=minutes)).isoformat(), **kw}


# --- the split -------------------------------------------------------------

def test_laps_two_minutes_apart_are_one_session():
    s = group_sessions([_lap(0), _lap(2), _lap(4)])
    assert len(s) == 1 and len(s[0].laps) == 3


def test_a_long_break_starts_a_new_session():
    s = group_sessions([_lap(0), _lap(2), _lap(60), _lap(62)])
    assert [len(x.laps) for x in s] == [2, 2]


def test_the_boundary_is_the_gap_not_the_lap_count():
    just_under = SESSION_GAP_S / 60 - 1
    assert len(group_sessions([_lap(0), _lap(just_under)])) == 1
    assert len(group_sessions([_lap(0), _lap(just_under + 2)])) == 2


def test_the_newest_session_comes_first():
    s = group_sessions([_lap(0), _lap(120)])
    assert s[0].laps[0]["recorded_utc"] > s[1].laps[0]["recorded_utc"]


def test_laps_inside_a_session_read_in_the_order_they_were_driven():
    """The catalogue hands them over newest-first; a session is a story."""
    rows = [_lap(4), _lap(0), _lap(2)]
    laps = group_sessions(rows)[0].laps
    assert [l["path"] for l in laps] == ["lap_0.json.gz", "lap_2.json.gz",
                                         "lap_4.json.gz"]


def test_no_laps_no_sessions():
    assert group_sessions([]) == []


# --- laps that can't be placed --------------------------------------------

def test_a_lap_without_a_timestamp_is_dropped_not_guessed():
    """Placing it in the newest run would invent a fact about when you drove."""
    rows = [_lap(0), {"path": "old.json.gz", "lap_time_ms": 1, "valid": 1}]
    s = group_sessions(rows)
    assert len(s) == 1 and len(s[0].laps) == 1


def test_an_unparseable_timestamp_is_dropped_too():
    rows = [_lap(0), {"path": "x", "lap_time_ms": 1, "recorded_utc": "boh"}]
    assert len(group_sessions(rows)[0].laps) == 1


def test_parse_utc_assumes_utc_when_the_stamp_has_no_zone():
    assert parse_utc("2026-07-28T18:00:00").tzinfo is timezone.utc
    assert parse_utc("2026-07-28T18:00:00Z").tzinfo is not None


# --- what a session reports ------------------------------------------------

def test_the_best_ignores_a_cut_lap():
    """A lap that left the track is faster for a reason."""
    s = group_sessions([_lap(0, ms=120_000), _lap(2, ms=118_000, clean=0)])[0]
    assert s.best["lap_time_ms"] == 120_000


def test_the_best_ignores_an_invalid_lap():
    s = group_sessions([_lap(0, ms=120_000), _lap(2, ms=110_000, valid=0)])[0]
    assert s.best["lap_time_ms"] == 120_000


def test_a_cut_lap_still_appears_in_the_list():
    """It is a lap you drove; it just can't set the numbers."""
    s = group_sessions([_lap(0), _lap(2, clean=0)])[0]
    assert len(s.laps) == 2 and len(s.valid_laps) == 1


def test_a_lap_of_unknown_cleanliness_still_counts():
    """`clean` is -1 on AC when the sim never told us; that is not 'dirty'."""
    s = group_sessions([_lap(0, ms=120_000, clean=-1)])[0]
    assert s.best is not None


def test_a_session_with_nothing_valid_has_no_best():
    assert group_sessions([_lap(0, valid=0)])[0].best is None


def test_duration_spans_first_to_last():
    # Laps at 0/8/15 minutes: three laps in one run, since no single gap
    # reaches the threshold. A 38-minute jump would be a second session.
    s = group_sessions([_lap(0), _lap(8), _lap(15)])[0]
    assert s.duration_s == 15 * 60


def test_road_temps_skip_the_laps_that_never_recorded_one():
    s = group_sessions([_lap(0, road_temp=37.8), _lap(2, road_temp=None),
                        _lap(4, road_temp=0.0), _lap(6, road_temp=41.0)])[0]
    assert s.road_temps == [37.8, 41.0]
