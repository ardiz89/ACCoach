"""The engineer's prediction and its track record.

Two things are under test and they are not the same thing.

The **prediction** is the acceptance bar, said before the re-test laps instead
of after. It deliberately cannot fail independently of the verdict — that's the
point of it, and the tests below pin that it is *exactly* the rule the verdict
applies, because a bar that drifted from the rule would be worse than no bar.

The **ledger** is where the real evidence goes: what happened to the symptoms
nobody was aiming at, and which remedy in the ordered list actually worked. Both
are measured, neither is asserted anywhere in the code.
"""
import json

import pytest

from accoach.engineer import (
    Balance,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
)
from accoach.engineer import ledger
from accoach.engineer.core import _EPS_SCORE, _TIME_BAND_FRAC
from accoach.engineer.profiles import GT3_PROFILE

U, O = Balance.UNDERSTEER, Balance.OVERSTEER
EN, AP, EX = Phase.ENTRY, Phase.APEX, Phase.EXIT
LO, HI = Speed.LOW, Speed.HIGH

PRESS_OK = {"front": 27.5, "rear": 27.5}
SYM = Symptom(U, AP, LO)
OTHER = Symptom(O, EX, LO)


def _lap(time_ms=100000, scores=None, corners=4, stable=True, press=PRESS_OK):
    scores = scores or {}
    return LapStats(lap_time_ms=time_ms, stable=stable, symptom_scores=dict(scores),
                    symptom_corners={s: corners for s in scores},
                    pressures_hot=press)


def _eng():
    return RaceEngineer(GT3_PROFILE, min_stable=3)


def _propose(eng, score=0.6, extra=None, time_ms=100000):
    """Drive laps until the engine proposes something for SYM."""
    scores = {SYM: score}
    if extra:
        scores.update(extra)
    for _ in range(6):
        d = eng.observe(_lap(time_ms, scores))
        if d.kind is DecisionKind.PROPOSE:
            return d
    raise AssertionError("the engine never proposed a change")


# --- the prediction ---------------------------------------------------------

def test_a_proposal_states_the_bar_before_the_laps_are_driven():
    d = _propose(_eng())
    assert d.prediction is not None
    assert d.prediction.text, "the driver has to be able to read it"
    assert d.prediction.symptom == SYM


def test_the_bar_is_exactly_the_rule_the_verdict_applies():
    """A prediction that drifted from the acceptance rule would be worse than
    none: the driver would be told one number and judged on another."""
    d = _propose(_eng(), score=0.60)
    p = d.prediction
    assert p.score_now == pytest.approx(0.60)
    assert p.score_below == pytest.approx(0.60 - _EPS_SCORE)
    assert p.time_band_ms == pytest.approx(100000 * _TIME_BAND_FRAC)


def test_the_stated_bar_is_the_one_that_actually_decides():
    """Land the symptom a hair *under* the announced bar: it must be kept."""
    eng = _eng()
    d = _propose(eng, score=0.60)
    bar = d.prediction.score_below
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: bar - 0.01}))
    assert out.kind is DecisionKind.ACCEPTED


def test_a_hair_the_wrong_side_of_the_stated_bar_is_reverted():
    eng = _eng()
    d = _propose(eng, score=0.60)
    bar = d.prediction.score_below
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: bar + 0.01}))
    assert out.kind is DecisionKind.REVERTED


def test_a_structural_change_predicts_only_the_lap_time():
    """Pressures carry no symptom, so the bar can only be the time band — and it
    must not pretend to a symptom target it isn't measuring."""
    eng = _eng()
    cold = {"front": 24.0, "rear": 24.0}        # under the window → it must act
    d = None
    for _ in range(6):
        d = eng.observe(_lap(scores={}, press=cold))
        if d.kind is DecisionKind.PROPOSE:
            break
    assert d.kind is DecisionKind.PROPOSE, "cold pressures must produce a remedy"
    assert d.change.symptom is None, "a pressure change carries no symptom"
    assert d.prediction.symptom is None
    assert d.prediction.score_now == 0.0 and d.prediction.score_below == 0.0
    assert d.prediction.time_band_ms > 0
    assert "0.00" not in d.prediction.text, "it must not quote a symptom target"


# --- the outcome ------------------------------------------------------------

def test_an_accepted_change_carries_the_numbers_on_both_sides():
    eng = _eng()
    _propose(eng, score=0.60)
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(99500, {SYM: 0.20}))
    assert out.kind is DecisionKind.ACCEPTED
    o = out.outcome
    assert o is not None and o.kept is True
    assert o.prediction.score_now == pytest.approx(0.60)
    assert o.score_after == pytest.approx(0.20)
    assert o.time_before_ms == pytest.approx(100000)
    assert o.time_after_ms == pytest.approx(99500)
    assert o.laps == 3


def test_a_reverted_change_keeps_its_numbers_too():
    """Regression: the revert path clears the window, and the outcome is
    measured *from* that window — built one line later it read all zeros."""
    eng = _eng()
    _propose(eng, score=0.60)
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100400, {SYM: 0.62}))
    assert out.kind is DecisionKind.REVERTED
    o = out.outcome
    assert o is not None and o.kept is False
    assert o.time_before_ms == pytest.approx(100000)
    assert o.time_after_ms == pytest.approx(100400), "measured before the reset"
    assert o.score_after == pytest.approx(0.62)


def test_the_remedy_that_worked_is_recorded_by_rank():
    """The profiles claim their remedy lists are ordered most-effective-first.
    That is a falsifiable claim, and the rank is how the ledger can check it."""
    eng = _eng()
    _propose(eng, score=0.60)
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: 0.62}))
    assert out.outcome.remedy_rank == 0
    # …the first lever was reverted, so the next test is of rank 1.
    eng.mark_applied()                       # driver restores the setup
    d = _propose(eng, score=0.60)
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: 0.20}))
    assert out.outcome.remedy_rank == 1


# --- what nobody was aiming at ---------------------------------------------

def test_a_symptom_nobody_was_aiming_at_is_reported_when_it_moves():
    """The verdict only ever looks at the target. A lever that fixes slow-apex
    understeer and costs the rear on exit used to do it in silence."""
    eng = _eng()
    _propose(eng, score=0.60, extra={OTHER: 0.20})
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: 0.20, OTHER: 0.55}))
    assert out.kind is DecisionKind.ACCEPTED
    effects = dict(out.outcome.side_effects)
    assert OTHER in effects and effects[OTHER] == pytest.approx(0.35)
    assert SYM not in effects, "the target is the verdict, not a side effect"


def test_a_side_effect_smaller_than_the_engines_own_floor_is_not_claimed():
    """Below `_EPS_SCORE` the engine refuses to call a move an improvement;
    calling it a side effect would be a stronger claim on weaker evidence."""
    eng = _eng()
    _propose(eng, score=0.60, extra={OTHER: 0.20})
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: 0.20,
                                        OTHER: 0.20 + _EPS_SCORE / 2}))
    assert out.outcome.side_effects == ()


def test_the_side_effect_is_named_in_the_message_the_driver_reads():
    eng = _eng()
    _propose(eng, score=0.60, extra={OTHER: 0.20})
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_lap(100000, {SYM: 0.20, OTHER: 0.55}))
    assert str(OTHER) in out.message


def test_giving_up_on_a_symptom_is_recorded_as_a_claim_we_made():
    """"Setup can't fix this, so it's you" is an assertion, and one we have
    never checked."""
    eng = _eng()
    for _ in range(40):
        d = eng.observe(_lap(100000, {SYM: 0.60}))
        if d.kind is DecisionKind.PROPOSE:
            eng.mark_applied()
        if eng.exhausted_calls:
            break
    assert SYM in eng.exhausted_calls


# --- the ledger file --------------------------------------------------------

def _rec(**kw):
    base = dict(when_utc="2026-07-31T12:00:00+00:00", car="ferrari_488_gt3_evo",
                track="monza", car_class="gt3", phase="Mechanical",
                symptom=str(SYM), param="aRBFront", slot=None, delta_clicks=-1,
                remedy_rank=0, kept=True, laps=3, score_before=0.6,
                score_after=0.2, time_before_ms=100000.0, time_after_ms=99500.0,
                side_effects={})
    base.update(kw)
    return ledger.Record(**base)


def test_a_record_survives_the_round_trip(tmp_path):
    p = tmp_path / "engineer_log.jsonl"
    assert ledger.append(_rec(), p) is True
    assert ledger.append(_rec(kept=False), p) is True
    rows = ledger.read(p)
    assert len(rows) == 2
    assert rows[0]["param"] == "aRBFront" and rows[0]["kept"] is True
    assert rows[1]["kept"] is False


def test_a_half_written_last_line_does_not_lose_the_history(tmp_path):
    """It is appended to from a live session; a crash mid-write must cost the
    last line, not the file."""
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(), p)
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"car": "half-writ')
    rows = ledger.read(p)
    assert len(rows) == 1


def test_a_ledger_that_cannot_be_written_is_not_an_exception(tmp_path):
    """Evidence we collect for ourselves must never cost the driver a change."""
    p = tmp_path / "nope"
    p.mkdir()
    assert ledger.append(_rec(), p) is False        # a directory, not a file
    assert ledger.read(p) == []


def test_reading_can_be_narrowed_to_one_car_and_track(tmp_path):
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(car="a", track="monza"), p)
    ledger.append(_rec(car="b", track="monza"), p)
    ledger.append(_rec(car="a", track="spa"), p)
    assert len(ledger.read(p, car="a")) == 2
    assert len(ledger.read(p, car="a", track="spa")) == 1


def test_the_summary_answers_how_many_changes_actually_worked(tmp_path):
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(kept=True, time_after_ms=99500.0), p)
    ledger.append(_rec(kept=True, time_after_ms=99800.0), p)
    ledger.append(_rec(kept=False, param="toe"), p)
    s = ledger.summarise(ledger.read(p))
    assert s.tests == 3 and s.kept == 2
    assert s.hit_rate == pytest.approx(2 / 3)
    assert s.by_param["aRBFront"] == (2, 2)
    assert s.by_param["toe"] == (0, 1)
    assert s.by_rank[0] == (2, 3)
    assert s.median_gain_ms == pytest.approx(-350.0)


def test_an_empty_ledger_summarises_to_nothing_rather_than_a_zero(tmp_path):
    """Zero per cent and "no evidence yet" are different answers."""
    s = ledger.summarise([])
    assert s.tests == 0 and s.hit_rate is None and s.median_gain_ms is None


def test_side_effects_are_counted_per_lever(tmp_path):
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(side_effects={str(OTHER): 0.35}), p)
    ledger.append(_rec(side_effects={str(OTHER): 0.28}), p)
    ledger.append(_rec(param="toe", side_effects={str(OTHER): 0.12}), p)
    counts = ledger.side_effect_counts(ledger.read(p))
    assert counts[("aRBFront", str(OTHER))] == 2
    assert counts[("toe", str(OTHER))] == 1


def test_the_ledger_lives_next_to_the_rest_of_the_users_data():
    from accoach.paths import base_dir
    assert ledger.ledger_path().parent == base_dir()
    assert ledger.ledger_path().suffix == ".jsonl"


# --- through the API --------------------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    """A client whose ledger lives in tmp_path, not in the user's Documents."""
    from fastapi.testclient import TestClient

    from accoach.api import create_api
    monkeypatch.setattr(ledger, "base_dir", lambda: tmp_path)
    return TestClient(create_api(tmp_path))


def test_no_evidence_yet_is_said_as_no_evidence_not_as_zero(api):
    """Nought per cent and "we haven't measured anything" are different
    answers, and only one of them is true on day one."""
    body = api.get("/api/setup/record").json()
    assert body["tests"] == 0
    assert body["hit_rate"] is None and body["median_gain_ms"] is None


def test_the_record_counts_what_the_driver_actually_drove(api, tmp_path):
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(kept=True, time_after_ms=99500.0), p)
    ledger.append(_rec(kept=False, param="toe", remedy_rank=1), p)
    body = api.get("/api/setup/record").json()
    assert body["tests"] == 2 and body["kept"] == 1
    assert body["hit_rate"] == pytest.approx(0.5)
    assert body["by_param"]["aRBFront"] == {"kept": 1, "tests": 1}
    assert body["by_rank"]["1"] == {"kept": 0, "tests": 1}, "JSON keys are strings"


def test_the_record_can_be_narrowed_to_the_car_on_screen(api, tmp_path):
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(car="a"), p)
    ledger.append(_rec(car="b"), p)
    assert api.get("/api/setup/record", params={"car": "a"}).json()["tests"] == 1


def test_a_record_is_plain_json(tmp_path):
    """It is read by us, by the user, and one day by a support conversation.
    Nothing in it may need this codebase to be interpreted."""
    p = tmp_path / "engineer_log.jsonl"
    ledger.append(_rec(side_effects={str(OTHER): 0.35}), p)
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(row["symptom"], str) and " " in row["symptom"]
    assert isinstance(row["side_effects"], dict)
    assert row["kept"] is True
