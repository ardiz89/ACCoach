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


# --- the fuel confound ------------------------------------------------------
# The baseline laps are driven before the change and the re-test laps after, and
# in between the driver goes to the garage to load the setup — which usually
# refuels. The two windows are routinely driven at different weights, in a
# direction that isn't predictable. This is the normal shape of the loop, not an
# edge case, which is why the verdict has to notice.

def _fuel_lap(time_ms, scores, fuel):
    s = _lap(time_ms, scores)
    s.fuel_l = fuel
    return s


def _run(eng, *, before_fuel, after_fuel, after_scores, after_time,
         before_scores=None, before_time=100000):
    before_scores = before_scores or {SYM: 0.60}
    for _ in range(6):
        d = eng.observe(_fuel_lap(before_time, before_scores, before_fuel))
        if d.kind is DecisionKind.PROPOSE:
            break
    assert d.kind is DecisionKind.PROPOSE
    eng.mark_applied()
    for _ in range(3):
        out = eng.observe(_fuel_lap(after_time, after_scores, after_fuel))
    return out


def test_a_refuelled_car_is_not_the_same_car_and_the_verdict_says_so():
    """The handling improved, but the clock is comparing 20 L against 60 L.
    Reporting that time difference as evidence would be reporting the fuel."""
    out = _run(_eng(), before_fuel=20.0, after_fuel=60.0,
               after_scores={SYM: 0.20}, after_time=101000)
    assert out.kind is DecisionKind.ACCEPTED, "the symptom score still decides"
    assert out.outcome.time_confounded is True
    assert out.outcome.fuel_before_l == pytest.approx(20.0)
    assert out.outcome.fuel_after_l == pytest.approx(60.0)
    assert "20" in out.message and "60" in out.message


def test_the_time_veto_is_suspended_rather_than_corrected():
    """A change that improves the symptom but shows a slower time is kept when
    the loads differ. Converting litres to seconds instead would need a weight
    sensitivity we have never measured — and that made-up number would be the
    thing deciding whether a setup change survives."""
    out = _run(_eng(), before_fuel=20.0, after_fuel=60.0,
               after_scores={SYM: 0.20}, after_time=104000)   # 4 s "slower"
    assert out.kind is DecisionKind.ACCEPTED


def test_comparable_loads_leave_the_time_veto_armed():
    out = _run(_eng(), before_fuel=40.0, after_fuel=39.0,
               after_scores={SYM: 0.20}, after_time=104000)
    assert out.outcome.time_confounded is False
    assert out.kind is DecisionKind.REVERTED, "same weight → the clock counts"


def test_laps_with_no_fuel_reading_are_unknown_not_matched():
    """Laps recorded before v11 carry no fuel. "We don't know" must not be read
    as "the loads matched" — that would silently re-arm a veto on evidence we
    don't have."""
    out = _run(_eng(), before_fuel=0.0, after_fuel=0.0,
               after_scores={SYM: 0.20}, after_time=104000)
    assert out.outcome.time_confounded is False
    assert out.outcome.fuel_before_l == 0.0
    assert out.kind is DecisionKind.REVERTED, "no reading → behave as before"


def test_a_structural_change_that_cannot_be_judged_is_said_to_be_unjudged():
    """Pressures have no symptom to fall back on. Keeping it silently would
    claim a verdict we didn't reach; reverting would put the phase gate straight
    back into proposing the same change, forever."""
    eng = _eng()
    cold = {"front": 24.0, "rear": 24.0}
    d = None
    for _ in range(6):
        s = _lap(100000, {}, press=cold)
        s.fuel_l = 20.0
        d = eng.observe(s)
        if d.kind is DecisionKind.PROPOSE:
            break
    assert d.kind is DecisionKind.PROPOSE and d.change.symptom is None
    eng.mark_applied()
    for _ in range(3):
        s = _lap(103000, {}, press=cold)      # 3 s slower, but on 60 L
        s.fuel_l = 60.0
        out = eng.observe(s)
    assert out.kind is DecisionKind.ACCEPTED
    assert out.outcome.time_confounded is True
    assert "serbatoio" in out.message or "tank" in out.message


def test_the_fuel_reading_comes_from_the_lap_itself():
    """`build_lap_stats` has to fill it, or the engine is blind by default."""
    from accoach.coaching.diagnosis import _mean_fuel

    class _S:
        def __init__(self, f):
            self.fuel = f
    assert _mean_fuel([_S(50.0), _S(48.0)]) == pytest.approx(49.0)
    assert _mean_fuel([_S(0.0), _S(0.0)]) == 0.0, "no reading is 0, not a mean"
    assert _mean_fuel([]) == 0.0


# --- the rain ---------------------------------------------------------------
# There is not one wet lap in the 39-lap archive, so nothing about wet setup
# work could be validated. What *can* be done honestly is refuse — and the
# refusal is worth more than it sounds: without it the engineer judges your
# pressures against a dry target in the rain, 2.5 psi the wrong way.

def _wet_lap(wet, scores=None, time_ms=100000):
    s = _lap(time_ms, scores or {SYM: 0.60})
    s.wet = wet
    return s


def test_the_engineer_stands_down_in_the_rain():
    eng = _eng()
    for _ in range(5):
        d = eng.observe(_wet_lap(True))
    assert d.kind is DecisionKind.STAND_DOWN
    assert d.change is None, "it must not propose anything"


def test_the_refusal_says_why_rather_than_going_quiet():
    """A tool that just stops looks broken. The reason is the message."""
    eng = _eng()
    d = eng.observe(_wet_lap(True))
    assert "dry" in d.message.lower() or "asciutto" in d.message.lower()


def test_a_lap_that_does_not_say_which_tyres_is_not_treated_as_dry():
    """Sixteen of the archive's 39 laps carry no compound. Unknown must not be
    read as dry, and must not be read as a change either."""
    eng = _eng()
    for _ in range(5):
        d = eng.observe(_wet_lap(None))
    assert d.kind is not DecisionKind.STAND_DOWN, "unknown is not a wet flag"


def test_the_track_drying_out_mid_test_drops_the_verdict():
    """A baseline on wets and a re-test on slicks is two cars on two circuits.
    Reading a verdict off that would be a number with no meaning, presented as
    one with one."""
    eng = _eng()
    for _ in range(6):
        d = eng.observe(_wet_lap(False))
        if d.kind is DecisionKind.PROPOSE:
            break
    assert d.kind is DecisionKind.PROPOSE
    eng.mark_applied()
    eng.observe(_wet_lap(False, {SYM: 0.20}))
    out = eng.observe(_wet_lap(True, {SYM: 0.20}))     # it started raining
    assert out.kind is DecisionKind.STAND_DOWN
    assert out.outcome is None, "no verdict may be read off a mixed window"
    assert eng.active is None, "the test in flight is abandoned, not judged"
    # The lap that announced the change is itself the first of the new
    # conditions, so it starts the new baseline rather than being thrown away.
    assert [s.wet for s in eng.window] == [True]


def test_the_window_survives_a_lap_that_simply_does_not_say():
    eng = _eng()
    eng.observe(_wet_lap(False))
    eng.observe(_wet_lap(None))
    d = eng.observe(_wet_lap(False))
    assert d.kind is not DecisionKind.STAND_DOWN
    assert len(eng.window) == 3, "an unknown lap is still a lap"


def test_the_wet_pressure_window_exists_only_where_it_is_sourced():
    """ACC's wet Pirelli has a published optimum (30.0 psi, 29.5-31.0) that
    several independent guides agree on. Open-wheel and road cars have no such
    figure and no wet lap here — and `None` has to stay `None`, because the dry
    fallback is 2.5 psi the wrong way."""
    from accoach.engineer.pressures import pressure_window, wet_pressure_window
    gt3 = wet_pressure_window("ferrari_488_gt3_evo")
    assert gt3 is not None and gt3[0] == pytest.approx(30.0)
    assert gt3[0] > pressure_window("ferrari_488_gt3_evo")[0]
    assert wet_pressure_window("bmw_m3_e92") is None
    assert wet_pressure_window("gp_2025_sf25") is None


def test_wet_is_read_from_the_tyres_the_driver_fitted():
    """Not from grip: `surface_grip` reads 0.0 on all 39 laps in the archive,
    on both games, so it is not a signal."""
    from accoach.coaching.diagnosis import _is_wet

    class _L:
        def __init__(self, c):
            self.tyre_compound = c
    assert _is_wet(_L("wet_compound")) is True
    assert _is_wet(_L("dry_compound")) is False
    assert _is_wet(_L("Semislicks (SM)")) is False
    assert _is_wet(_L("")) is None, "no compound is unknown, not dry"
    assert _is_wet(_L(None)) is None


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
