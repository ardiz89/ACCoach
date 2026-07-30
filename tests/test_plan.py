"""The training plan: proposed, accepted, then measured against what came after.

Three properties separate this from the list of weak points it is built from,
and they are what the tests below are about: it stays put once accepted, it
carries a target you can check, and it judges itself only on the laps driven
*after* you agreed to it.
"""
import pytest
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.coaching.plan import (
    MAX_GOALS,
    Goal,
    TrainingPlan,
    measure,
    propose,
)
from accoach.coaching.thresholds import SIGNIF_LOSS_MS
from accoach.coaching.trends import LossTrend, classify_losses
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _loss(index, lost_ms, message="Carry more speed", fix="Less brake."):
    return CornerLoss(index=index, entry_pos=0.1, apex_pos=0.2, exit_pos=0.3,
                      lost_ms=lost_ms, category=CueCategory.CARRY_SPEED,
                      message=message, fix=fix, name=f"Turn {index + 1}")


def _debrief(*losses):
    return LapDebrief(car_model=CAR, track=TRACK, lap_time_ms=100_000,
                      reference_lap_ms=99_000, losses=list(losses))


def _trend(index, median_ms, systematic=True, laps=6):
    return LossTrend(corner_index=index, name=f"Turn {index + 1}",
                     category=CueCategory.CARRY_SPEED,
                     occurrences=laps if systematic else 1, laps=laps,
                     median_ms=median_ms, total_ms=median_ms * laps,
                     systematic=systematic)


# --- what gets chosen -------------------------------------------------------

def test_a_plan_is_built_from_systematic_weaknesses(tmp_path):
    debriefs = [_debrief(_loss(0, 400.0)) for _ in range(5)]
    plan = propose([_trend(0, 400.0)], debriefs)
    assert len(plan.goals) == 1
    g = plan.goals[0]
    assert g.corner_index == 0
    assert g.what == "Carry more speed" and g.fix == "Less brake."


def test_a_one_off_is_never_a_goal():
    """A plan is for what you do every lap; you can't practise a one-off."""
    debriefs = [_debrief(_loss(1, 900.0))]
    assert propose([_trend(1, 900.0, systematic=False)], debriefs).goals == []


def test_a_corner_the_live_coach_has_cleared_is_skipped():
    """Two surfaces disagreeing about whether you've got a corner is worse than
    either answer alone — the Focus coach's memory wins."""
    debriefs = [_debrief(_loss(0, 400.0), _loss(3, 300.0)) for _ in range(5)]
    plan = propose([_trend(0, 400.0), _trend(3, 300.0)], debriefs, mastered={0})
    assert [g.corner_index for g in plan.goals] == [3]


def test_a_plan_is_short_on_purpose():
    debriefs = [_debrief(*(_loss(i, 500.0 - i) for i in range(5))) for _ in range(5)]
    trends = [_trend(i, 500.0 - i) for i in range(5)]
    assert len(propose(trends, debriefs).goals) == MAX_GOALS


def test_the_words_come_from_the_worst_example_not_the_last_lap():
    """The message and the fix are per-lap; the plan takes the version the
    debrief itself thought most worth explaining."""
    debriefs = [
        _debrief(_loss(0, 200.0, message="mild", fix="mild fix")),
        _debrief(_loss(0, 800.0, message="the real one", fix="the real fix")),
        _debrief(_loss(0, 300.0, message="middling", fix="middling fix")),
    ]
    g = propose([_trend(0, 300.0)], debriefs).goals[0]
    assert g.what == "the real one" and g.fix == "the real fix"


# --- the target -------------------------------------------------------------

def test_the_target_asks_for_half_of_it_back():
    g = propose([_trend(0, 600.0)], [_debrief(_loss(0, 600.0))]).goals[0]
    assert g.baseline_ms == 600.0
    assert g.target_ms == 300.0


def test_the_target_never_goes_under_the_floor_the_app_itself_uses():
    """Asking for less than the loss we'd refuse to talk about is asking for
    perfection with extra steps."""
    g = propose([_trend(0, 150.0)], [_debrief(_loss(0, 150.0))]).goals[0]
    assert g.target_ms == SIGNIF_LOSS_MS


# --- measuring --------------------------------------------------------------

def _plan_with_target(target_ms=300.0):
    return TrainingPlan(car=CAR, track=TRACK, created_utc="2026-07-01T00:00:00+00:00",
                        goals=[Goal(corner_index=0, name="Turn 1",
                                    category="carry_speed", what="w", fix="f",
                                    baseline_ms=600.0, target_ms=target_ms,
                                    laps_seen=5)])


def test_a_lap_under_the_target_is_a_hit():
    p = measure(_plan_with_target(), [_debrief(_loss(0, 250.0))])[0]
    assert p.hits == 1 and p.laps == 1


def test_a_corner_that_stopped_costing_anything_counts_as_a_hit():
    """A corner missing from a debrief cost nothing worth naming. That is the
    goal achieved, not missing data."""
    p = measure(_plan_with_target(), [_debrief()])[0]
    assert p.hits == 1
    assert p.median_ms == 0.0


def test_one_good_lap_is_not_a_habit():
    """Under three laps, "done" would be reading a fluke as a fix."""
    p = measure(_plan_with_target(), [_debrief(_loss(0, 100.0))])[0]
    assert p.hits == 1 and not p.done


def test_done_when_the_target_holds_in_half_the_laps():
    """The mirror image of how it became a weakness: a corner can't be both
    systematic and beaten, so both use the same fraction."""
    laps = [_debrief(_loss(0, 100.0)), _debrief(_loss(0, 120.0)),
            _debrief(_loss(0, 800.0)), _debrief(_loss(0, 900.0))]
    p = measure(_plan_with_target(), laps)[0]
    assert p.hits == 2 and p.needed == 2 and p.done


def test_still_missing_it_is_not_done():
    laps = [_debrief(_loss(0, 800.0)) for _ in range(4)]
    p = measure(_plan_with_target(), laps)[0]
    assert p.hits == 0 and not p.done
    assert p.median_ms == 800.0


def test_no_laps_since_means_no_verdict():
    p = measure(_plan_with_target(), [])[0]
    assert p.laps == 0 and not p.done


def test_a_plan_survives_the_round_trip_through_storage():
    plan = _plan_with_target()
    again = TrainingPlan.from_dict(plan.to_dict())
    assert again.goals == plan.goals and again.created_utc == plan.created_utc


# --- through the API --------------------------------------------------------

def _seed(tmp_path, laps=5, amt=26, first_day=21):
    ref = synth.build_lap()
    ref.recorded_utc = "2026-07-20T18:00:00+00:00"
    save_lap(ref, tmp_path)
    for i in range(laps):
        lap = synth.build_lap(slow_corner=0, amt=amt)
        lap.recorded_utc = f"2026-07-{first_day + i:02d}T18:00:00+00:00"
        save_lap(lap, tmp_path)
    return TestClient(create_api(tmp_path))


def _plan(c, lang="en"):
    r = c.get("/api/progress", params={"car": CAR, "track": TRACK, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()["plan"]


def test_the_page_proposes_a_plan_before_you_accept_one(tmp_path):
    p = _plan(_seed(tmp_path))
    assert p["saved"] is False and p["created_utc"] is None
    assert p["goals"] and p["goals"][0]["target_s"] < p["goals"][0]["baseline_s"]


def test_accepting_a_plan_stores_it_with_a_date(tmp_path):
    c = _seed(tmp_path)
    proposed = _plan(c)
    r = c.post("/api/plan", json={"car": CAR, "track": TRACK,
                                  "goals": proposed["goals"]})
    assert r.status_code == 200 and r.json()["ok"]
    saved = _plan(c)
    assert saved["saved"] is True
    assert saved["created_utc"] == r.json()["created_utc"]
    assert [g["corner_index"] for g in saved["goals"]] == \
           [g["corner_index"] for g in proposed["goals"]]


def test_the_client_can_hand_back_exactly_what_it_was_shown(tmp_path):
    """Seconds in, seconds out, `progress` and all: the driver agrees to the
    plan on the screen, so the object on the screen has to be acceptable."""
    c = _seed(tmp_path)
    goals = _plan(c)["goals"]
    assert "progress" in goals[0] and "baseline_s" in goals[0]
    assert c.post("/api/plan", json={"car": CAR, "track": TRACK,
                                     "goals": goals}).status_code == 200
    saved = _plan(c)["goals"][0]
    assert saved["baseline_s"] == goals[0]["baseline_s"]
    assert saved["target_s"] == goals[0]["target_s"]


def test_an_accepted_plan_does_not_move_when_new_laps_land(tmp_path):
    """The whole reason it is saved: you cannot work on a target that shifts."""
    c = _seed(tmp_path)
    c.post("/api/plan", json={"car": CAR, "track": TRACK, "goals": _plan(c)["goals"]})
    before = _plan(c)["goals"][0]
    for i in range(3):                       # three much better laps
        lap = synth.build_lap(slow_corner=0, amt=2)
        lap.recorded_utc = f"2026-08-{i + 1:02d}T18:00:00+00:00"
        save_lap(lap, tmp_path)
    after = _plan(c)["goals"][0]
    assert after["baseline_s"] == before["baseline_s"]
    assert after["target_s"] == before["target_s"]
    assert after["progress"]["laps"] == 3, "and it now has something to judge"


def test_progress_only_counts_laps_driven_after_you_accepted(tmp_path):
    c = _seed(tmp_path)
    c.post("/api/plan", json={"car": CAR, "track": TRACK, "goals": _plan(c)["goals"]})
    assert _plan(c)["laps_since"] == 0, "the laps that built the plan aren't progress"


def test_giving_up_on_a_plan_proposes_a_fresh_one(tmp_path):
    c = _seed(tmp_path)
    c.post("/api/plan", json={"car": CAR, "track": TRACK, "goals": _plan(c)["goals"]})
    assert _plan(c)["saved"] is True
    assert c.delete("/api/plan", params={"car": CAR, "track": TRACK}).status_code == 200
    assert _plan(c)["saved"] is False


def test_a_plan_without_goals_is_refused(tmp_path):
    c = _seed(tmp_path)
    assert c.post("/api/plan", json={"car": CAR, "track": TRACK,
                                     "goals": []}).status_code == 422


def test_a_malformed_goal_is_refused_rather_than_stored(tmp_path):
    c = _seed(tmp_path)
    bad = [{"name": "no index here"}]
    assert c.post("/api/plan", json={"car": CAR, "track": TRACK,
                                     "goals": bad}).status_code == 422


def test_the_goal_carries_the_curated_corner_name(tmp_path):
    """It is read for weeks: "Corner 1" where the rest of the page says
    "Variante del Rettifilo" would be the one panel that doesn't know."""
    p = _plan(_seed(tmp_path), lang="it")
    assert p["goals"][0]["name"] in ("Curva 1", "Variante del Rettifilo")


def test_no_valid_laps_is_an_empty_plan_not_a_crash(tmp_path):
    c = TestClient(create_api(tmp_path))
    r = c.get("/api/progress", params={"car": CAR, "track": "spa"})
    assert r.status_code == 200
    assert r.json()["plan"]["goals"] == []


def test_classify_and_propose_agree_on_what_systematic_means():
    """propose() filters on LossTrend.systematic rather than re-deciding."""
    debriefs = [_debrief(_loss(0, 400.0)) for _ in range(4)] + [_debrief()]
    trends = classify_losses(debriefs)
    plan = propose(trends, debriefs)
    assert [t.systematic for t in trends if t.corner_index == 0] == [True]
    assert [g.corner_index for g in plan.goals] == [0]


@pytest.mark.parametrize("bad", [None, {}])
def test_measure_is_defensive_about_an_empty_plan(bad):
    assert measure(TrainingPlan(), []) == []
