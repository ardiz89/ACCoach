"""Tre consigli che a Zolder (29/10) non reggevano.

* «Veleggi» detto 12 volte in 13 giri, senza dire in quale curva.
* «Frena più tardi» a Curva 2, dove eri uscito di pista quattro volte.
* Il verdetto sul tempo non guardava quanto era cambiata la pista.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import accoach.api as api
from accoach.api import create_api
from accoach.coaching.cue import Cue, CueCategory
from accoach.coaching.debrief import CornerLoss, mark_runs_wide
from accoach.coaching.scheduler import CueScheduler
from accoach.coaching.training import drill_key
from accoach.engine import _name_the_corner
from accoach.engineer.core import DecisionKind, RaceEngineer
from accoach.engineer.ledger import Record
from accoach.engineer.profiles.gt3 import GT3_PROFILE
from accoach.recording.storage import load_lap, save_lap
from accoach.track import detect_corners
from test_engineer_ledger import SYM, _lap

import synth


# --- Veleggi -------------------------------------------------------------------

def _coast():
    return Cue(CueCategory.COASTING, "Veleggi", 1.0, 3, 0.3)


def _laps_said(sched, laps, cue_of=_coast):
    said, now = 0, 0.0
    for _ in range(laps):
        sched.new_lap()
        now += 100.0
        sched.submit(cue_of(), now)
        if sched.poll(now + 0.1) is not None:
            said += 1
    return said


def test_coasting_is_said_one_lap_in_three():
    assert _laps_said(CueScheduler(), 13) == 5


def test_coasting_keeps_coming_when_it_is_the_focus():
    sched = CueScheduler()
    sched.set_focus("traction")
    assert _laps_said(sched, 6) == 6


def test_other_technique_advice_is_not_rationed():
    def cue():
        return Cue(CueCategory.TRAIL_BRAKE, "Molli", 1.0, 3, 0.3)
    assert _laps_said(CueScheduler(), 6, cue) == 6


CORNERS = [SimpleNamespace(index=5, entry_pos=0.55, exit_pos=0.66)]
NAMES = {5: "Curva 6"}


def test_the_screen_names_the_corner_and_the_voice_stays_the_recording():
    cue = Cue(CueCategory.COASTING, "Veleggi", 1.0, 3, 0.59)
    assert _name_the_corner(cue, "Veleggi", CORNERS, NAMES) == "Curva 6. Veleggi"


def test_on_a_straight_it_invents_no_corner():
    cue = Cue(CueCategory.COASTING, "Veleggi", 1.0, 3, 0.2)
    assert _name_the_corner(cue, "Veleggi", CORNERS, NAMES) == "Veleggi"


def test_only_coasting_gets_the_name():
    cue = Cue(CueCategory.TRAIL_BRAKE, "Molli", 1.0, 3, 0.59)
    assert _name_the_corner(cue, "Molli", CORNERS, NAMES) == "Molli"


# --- Frena più tardi dove esci -------------------------------------------------

def _loss(cat=CueCategory.BRAKE_LATER):
    return CornerLoss(index=1, entry_pos=0.12, apex_pos=0.16, exit_pos=0.23,
                      lost_ms=250.0, category=cat, message="Frena più tardi",
                      detail="Cominci a frenare prima.", fix="Sposta il punto.")


def test_twice_off_at_a_corner_stops_asking_for_a_later_brake():
    x = _loss()
    mark_runs_wide([x], {1: 4}, "it")
    assert "tardi" not in x.message and "Sposta" not in x.fix
    assert "4 volte" in x.detail and x.detail.startswith("Cominci")


def test_once_off_changes_nothing_and_other_advice_stays():
    x = _loss()
    mark_runs_wide([x], {1: 1}, "it")
    assert x.message == "Frena più tardi"
    y = _loss(CueCategory.CARRY_SPEED)
    mark_runs_wide([y], {1: 4}, "it")
    assert y.message == "Frena più tardi"


def test_the_drill_works_on_the_exit_instead():
    assert drill_key("brake_later", "entry") == "brake_move_later"
    assert drill_key("brake_later", "entry", runs_wide=True) == "exit_throttle"


def test_the_report_counts_where_the_recent_laps_went_off(tmp_path, monkeypatch):
    laps = tmp_path / "laps"

    def mine(ms, day, **kw):
        lap = synth.build_lap()
        synth.retime(lap, ms)
        lap.recorded_utc = f"2026-07-{day:02d}T09:00:00+00:00"
        for k, v in kw.items():
            setattr(lap, k, v)
        return save_lap(lap, laps)

    ref = mine(100_000, 20, clean=True)
    c = detect_corners(load_lap(ref).samples)[0]
    inside = (c.entry_pos + c.exit_pos) / 2
    mine(120_000, 21, clean=False, lost_at=inside)
    mine(121_000, 22, clean=False, lost_at=inside)
    seen = {}
    monkeypatch.setattr(api, "mark_runs_wide",
                        lambda losses, wide, lang=None: seen.update(wide))
    r = TestClient(create_api(laps)).get(
        "/api/analysis", params={"car": "ferrari_488_gt3", "track": "monza"})
    assert r.status_code == 200 and seen == {c.index: 2}


# --- La pista cambiata ---------------------------------------------------------

def _with_temp(ms, scores, temp):
    lap = _lap(ms, scores)
    lap.road_temp = temp
    return lap


def _run(before, after, score_after=0.3):
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    for _ in range(6):
        d = eng.observe(_with_temp(100_000, {SYM: 0.6}, before))
        if d.kind is DecisionKind.PROPOSE:
            break
    eng.mark_applied()
    for _ in range(3):
        d = eng.observe(_with_temp(101_000, {SYM: score_after}, after))
    return d


def test_a_slower_lap_on_a_track_that_moved_is_not_held_against_the_change():
    d = _run(30.0, 34.0)
    assert d.kind is DecisionKind.ACCEPTED
    assert d.outcome.temp_confounded and d.outcome.time_confounded
    assert d.outcome.road_temp_before == 30.0 and d.outcome.road_temp_after == 34.0


def test_the_usual_drift_of_a_session_still_counts_against_it():
    """1,7 gradi e' il massimo visto in 16 sessioni: li' il tempo vale."""
    d = _run(37.6, 39.3)
    assert d.kind is DecisionKind.REVERTED
    assert not d.outcome.temp_confounded


def test_an_unknown_temperature_is_not_a_change():
    d = _run(0.0, 34.0)
    assert d.kind is DecisionKind.REVERTED
    assert not d.outcome.temp_confounded


def test_the_ledger_keeps_the_temperature():
    assert {"road_temp_before", "road_temp_after",
            "temp_confounded"} <= set(Record.__dataclass_fields__)
