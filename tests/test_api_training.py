"""api: /api/training — the Training tab, wired to the same laps as the rest.

The programme's own rules are pinned in test_training.py. What belongs here is
what only the endpoint can get wrong: opening the section on too little
evidence, reading a different set of laps from the tab next door, and printing
a plan in the language it was accepted in rather than the one being asked for.
"""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.coaching.training import MIN_LAPS
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _seed(tmp_path, laps=MIN_LAPS - 1, amt=26, road_temp=None):
    """A reference lap plus ``laps`` slower ones — `laps + 1` valid in total."""
    ref = synth.build_lap()
    ref.recorded_utc = "2026-07-20T18:00:00+00:00"
    if road_temp is not None:
        ref.road_temp = road_temp
    save_lap(ref, tmp_path)
    for i in range(laps):
        lap = synth.build_lap(slow_corner=0, amt=amt)
        lap.recorded_utc = f"2026-07-{21 + i:02d}T18:00:00+00:00"
        if road_temp is not None:
            lap.road_temp = road_temp
        save_lap(lap, tmp_path)
    return TestClient(create_api(tmp_path))


def _train(client, lang="it"):
    r = client.get("/api/training",
                   params={"car": CAR, "track": TRACK, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


# --- the gate ---------------------------------------------------------------

def test_below_the_bar_the_answer_is_one_sentence(tmp_path):
    b = _train(_seed(tmp_path, laps=2))          # 3 valid
    assert b["ready"] is False and b["plan"] is None
    assert b["steps"] == [] and b["session"] is None
    assert b["readiness"]["reason"]
    assert b["readiness"]["laps_needed"] == MIN_LAPS - 3


def test_the_bar_is_counted_in_valid_laps(tmp_path):
    assert _train(_seed(tmp_path, laps=MIN_LAPS - 2))["ready"] is False
    assert _train(_seed(tmp_path, laps=MIN_LAPS - 1))["ready"] is True


def test_a_combo_with_no_laps_at_all_is_not_a_500(tmp_path):
    c = TestClient(create_api(tmp_path))
    r = c.get("/api/training", params={"car": CAR, "track": "spa"})
    assert r.status_code == 200 and r.json()["ready"] is False


# --- what a ready programme carries ----------------------------------------

def test_a_ready_programme_carries_the_gap_the_steps_and_the_session(tmp_path):
    b = _train(_seed(tmp_path))
    assert b["gap"] and b["gap"]["headline"]
    assert b["steps"] and b["steps"][0]["drill"]["steps"]
    assert b["session"]["laps"] > 0 and b["session"]["lines"]
    assert b["plan"]["saved"] is False, "proposed until you accept it"


def test_the_consistency_gap_matches_the_levels_ladder(tmp_path):
    """Trends and Training must not disagree about your theoretical ideal."""
    c = _seed(tmp_path)
    b = _train(c)
    prog = c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()
    ideal = next(lv for lv in prog["levels"] if lv["key"] == "ideal")
    assert b["gap"]["ideal_ms"] == ideal["lap_time_ms"]
    assert b["gap"]["consistency_ms"] == ideal["gain_ms"]


def test_the_drill_and_the_map_sheet_pool_the_very_same_laps(tmp_path):
    """A drill saying you brake at 214 km/h while the sheet two tabs over says
    209 is two answers to one question. Both go through `_sheet_pool`, so the
    rule is pinned once, here: the same asphalt-temperature band the live coach
    uses to elect a reference, then the most recent of what's left.
    """
    from accoach.api import _SHEET_LAPS, _TEMP_BAND_C, _sheet_pool

    rows = [{"path": f"cold{i}", "road_temp": 12.0, "recorded_utc": f"2026-06-0{i}"}
            for i in range(1, 4)]
    rows += [{"path": f"warm{i}", "road_temp": 30.0, "recorded_utc": f"2026-07-0{i}"}
             for i in range(1, 4)]
    ref = rows[-1]

    pool = _sheet_pool(rows, ref)
    assert [r["path"] for r in pool] == ["warm1", "warm2", "warm3"]
    assert all(abs(r["road_temp"] - ref["road_temp"]) <= _TEMP_BAND_C for r in pool)

    # And it never pools more than the sheet's own window, oldest dropped first.
    many = [{"path": f"l{i:02d}", "road_temp": 30.0,
             "recorded_utc": f"2026-07-{i:02d}"} for i in range(1, 20)]
    recent = _sheet_pool(many, many[-1])
    assert len(recent) == _SHEET_LAPS and recent[-1]["path"] == "l19"


def test_no_drill_quotes_a_braking_point_the_sheet_disagrees_with(tmp_path):
    c = _seed(tmp_path, road_temp=30.0)
    sheet = c.get("/api/braking", params={"car": CAR, "track": TRACK}).json()
    assert sheet["rows"], "the fixture has to produce a sheet to mean anything"
    by_index = {r["index"]: r for r in sheet["rows"]}
    for step in _train(c, lang="en")["steps"]:
        row = by_index.get(step["corner_index"])
        for line in step["drill"]["steps"]:
            if "you hit the brakes at" not in line:
                continue
            assert row is not None, line
            assert f"{row['speed_kmh']:.0f} km/h" in line, (line, row["speed_kmh"])


# --- accepting, and the words that outlive the language --------------------

def test_accepting_the_plan_here_is_what_the_programme_then_measures(tmp_path):
    c = _seed(tmp_path)
    b = _train(c)
    r = c.post("/api/plan", json={"car": CAR, "track": TRACK,
                                  "goals": b["plan"]["goals"]})
    assert r.status_code == 200
    again = _train(c)
    assert again["plan"]["saved"] is True
    assert again["plan"]["created_utc"] == r.json()["created_utc"]
    assert again["session"]["lines"][-1].endswith(".")


def test_a_plan_accepted_in_one_language_reads_in_the_other(tmp_path):
    """Found on screen: an Italian page whose every goal read "Time lost here",
    because the plan stores the words of the day it was accepted. The numbers
    are the agreement and stay put; the labels are not."""
    c = _seed(tmp_path)
    en = _train(c, lang="en")
    c.post("/api/plan", json={"car": CAR, "track": TRACK,
                              "goals": en["plan"]["goals"]})
    it = _train(c, lang="it")
    assert it["plan"]["saved"] is True
    for a, b in zip(en["plan"]["goals"], it["plan"]["goals"]):
        assert a["target_s"] == b["target_s"]
        assert a["baseline_s"] == b["baseline_s"]
        assert a["what"] != b["what"], "the label follows the page"
    for step in it["steps"]:
        assert "Time lost here" not in step["what"]


def test_the_plan_no_longer_rides_along_with_the_trends_tab(tmp_path):
    """One home, so there is one place to disagree about what you're training."""
    c = _seed(tmp_path)
    prog = c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()
    assert "plan" not in prog
    assert prog["trends"], "Trends still computes what a plan is picked from"
