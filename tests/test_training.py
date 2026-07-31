"""The Training tab: from "here is what you lose" to "here is what to do".

The module under test invents nothing — it picks a written drill using the
diagnosis the rest of the app already made, and drops the driver's own measured
numbers into it. So these tests are mostly about the two ways that can go wrong:
choosing the drill from the wrong signal, and printing a number that isn't there
(or one the reader can see doesn't add up).

The ordering tests are the other half. A programme is a *sequence*, and the
sentence explaining why a step comes first is only true relative to where it
ended up — which is how two steps once both came out saying "start here".
"""
import pytest

from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.phases import PhaseLoss
from accoach.coaching.plan import Goal, GoalProgress, TrainingPlan
from accoach.coaching.thresholds import SIGNIF_LOSS_MS
from accoach.coaching.training import (
    MAX_STEPS,
    MIN_LAPS,
    CornerFacts,
    assess,
    build_drill,
    build_gap,
    build_programme,
    dominant_phase,
    drill_key,
)

CAR, TRACK = "ferrari_488_gt3", "monza"


def _loss(index, lost_ms, phases=None, category=CueCategory.TIME_LOSS,
          inherited_from=-1, inherited="", name=None, vmin=0.0, vref=0.0):
    return CornerLoss(
        index=index, entry_pos=0.1, apex_pos=0.2, exit_pos=0.3,
        lost_ms=lost_ms, category=category, message="Time lost here",
        fix="Clean up your line.", name=name or f"Turn {index + 1}",
        inherited_from=inherited_from, inherited=inherited,
        min_speed_live=vmin, min_speed_ref=vref,
        phases=[PhaseLoss(phase=p, lost_ms=v) for p, v in (phases or [])],
    )


def _debrief(*losses):
    return LapDebrief(car_model=CAR, track=TRACK, lap_time_ms=100_000,
                      reference_lap_ms=99_000, losses=list(losses))


def _goal(index, baseline=400.0, target=200.0, category=CueCategory.TIME_LOSS):
    return Goal(corner_index=index, name=f"Turn {index + 1}",
                category=category.value, what="Time lost here",
                fix="Clean up your line.", baseline_ms=baseline,
                target_ms=target, laps_seen=6)


def _plan(*goals):
    return TrainingPlan(car=CAR, track=TRACK, goals=list(goals))


# --- the gate ---------------------------------------------------------------

def test_too_few_laps_is_a_sentence_with_a_number_in_it():
    """"Not enough data" said as a blank panel reads as a broken feature."""
    r = assess(MIN_LAPS - 2, 1)
    assert not r.ready and r.missing == ["laps"]
    assert r.laps_needed == 2
    assert str(MIN_LAPS) in r.reason and str(MIN_LAPS - 2) in r.reason


def test_enough_laps_but_nothing_that_repeats_is_its_own_answer():
    """A different thing from "not enough laps", and it needs different words:
    driving more won't help if what you lose keeps moving corner to corner."""
    r = assess(MIN_LAPS + 4, 0)
    assert not r.ready and r.missing == ["weakness"] and r.laps_needed == 0
    assert r.reason


def test_the_gate_opens_on_laps_and_a_weakness():
    r = assess(MIN_LAPS, 1)
    assert r.ready and not r.missing and not r.reason


@pytest.mark.parametrize("lang", ("it", "en"))
def test_the_gate_speaks_both_languages(lang):
    assert assess(2, 0, lang).reason


# --- where the time is ------------------------------------------------------

def _gap(best=100_000, ideal=99_000, yours=(34_000, 33_000, 33_000),
         bests=(33_800, 32_600, 32_600), **kw):
    return build_gap(best, ideal, list(yours), list(bests), **kw)


def test_the_consistency_gap_is_your_best_minus_your_ideal():
    g = _gap()
    assert g.consistency_ms == 1000


def test_the_per_sector_gaps_add_up_to_the_lap_gap():
    """The whole reason a sector can be named without estimating anything."""
    g = _gap()
    assert sum(s.gap_ms for s in g.sectors) == g.consistency_ms


def test_the_worst_sector_is_named_only_when_it_holds_something():
    g = _gap(best=100_000, ideal=99_880,
             yours=(34_000, 33_000, 33_000), bests=(33_960, 32_960, 32_960))
    assert g.consistency_ms == 120
    assert g.worst_sector == 0, "40ms in a sector is a sentence about rounding"


def test_a_best_lap_that_is_already_the_ideal_is_not_described_as_pieces():
    """Five thousandths is your best lap, not "time you drove in pieces" —
    and telling that driver to practise repeating themselves is wrong."""
    g = _gap(best=100_000, ideal=99_995, yours=(50_000, 50_000, 0),
             bests=(49_998, 49_997, 0))
    assert g.consistency_ms == 5
    assert "5" not in g.headline.split(":")[0]
    assert g.worst_sector == 0 and not g.note


def test_the_two_numbers_are_never_added_together():
    """They measure the same road two ways; summing them counts time twice."""
    g = _gap(per_lap_ms=310.0)
    assert g.note, "with two real numbers on the page, the note has to be there"
    assert "1.00" in g.note and "0.31" in g.note
    assert str(g.consistency_ms + 310) not in g.note


def test_no_ideal_lap_means_no_gap_at_all():
    assert build_gap(100_000, 0, [], []) is None


def test_the_pro_gap_is_stated_beyond_the_ideal_not_beyond_your_best():
    g = _gap(pro_ms=97_000)
    assert g.pro_gap_ms == 2000


# --- which drill ------------------------------------------------------------

def test_the_dominant_phase_is_the_typical_lap_not_the_worst_one():
    """One dramatic entry mistake must not send a driver to practise braking
    for a corner they normally lose on exit."""
    usual = [_debrief(_loss(0, 400.0, [("entry", 20.0), ("apex", 10.0),
                                       ("exit", 320.0), ("after", 50.0)]))
             for _ in range(4)]
    freak = _debrief(_loss(0, 900.0, [("entry", 800.0), ("apex", 40.0),
                                      ("exit", 20.0), ("after", 40.0)]))
    assert dominant_phase(usual + [freak], 0) == "exit"


def test_a_loss_spread_around_the_corner_names_no_phase():
    """Same refusal phases.py already makes: pointing at one part of a corner
    that leaks everywhere sends the driver to a place that isn't the place."""
    ds = [_debrief(_loss(0, 400.0, [("entry", 100.0), ("apex", 100.0),
                                    ("exit", 100.0), ("after", 100.0)]))
          for _ in range(3)]
    assert dominant_phase(ds, 0) == ""


def test_a_corner_with_no_phase_split_names_no_phase():
    assert dominant_phase([_debrief(_loss(0, 400.0))], 0) == ""


def test_the_phase_outranks_the_category():
    """The documented decision: where the clock ran is a measurement, the
    category is a label on the dominant symptom. A corner tagged "carry more
    entry speed" whose time goes on exit needs the exit drill."""
    assert drill_key(CueCategory.CARRY_SPEED.value, "exit") == "exit_throttle"
    assert drill_key(CueCategory.CARRY_SPEED.value, "") == "apex_speed"


def test_the_category_decides_only_when_no_phase_dominates():
    assert drill_key(CueCategory.BRAKE_LATER.value, "") == "brake_move_later"
    assert drill_key(CueCategory.LESS_BRAKE.value, "") == "brake_release"
    assert drill_key(CueCategory.TIME_LOSS.value, "") == "repeat"


def test_braking_too_long_and_braking_too_early_get_opposite_drills():
    assert drill_key(CueCategory.BRAKE_LATER.value, "entry") == "brake_move_later"
    assert drill_key(CueCategory.LESS_BRAKE.value, "entry") == "brake_release"


# --- the drills themselves --------------------------------------------------

_ALL_DRILLS = [
    (CueCategory.BRAKE_LATER.value, "entry"),
    (CueCategory.LESS_BRAKE.value, "entry"),
    (CueCategory.CARRY_SPEED.value, "apex"),
    (CueCategory.MORE_THROTTLE.value, "exit"),
    (CueCategory.TIME_LOSS.value, ""),
]


@pytest.mark.parametrize("category,phase", _ALL_DRILLS)
@pytest.mark.parametrize("lang", ("it", "en"))
def test_every_drill_is_written_in_both_languages(category, phase, lang):
    d = build_drill(category, phase, CornerFacts(), lang)
    assert d.title and d.watch and d.ignore and d.laps > 0
    assert len(d.steps) >= 3


@pytest.mark.parametrize("category,phase", _ALL_DRILLS)
@pytest.mark.parametrize("lang", ("it", "en"))
def test_no_drill_ever_prints_an_unfilled_placeholder(category, phase, lang):
    """A line reading "your point moves {m} m" is worse than no line."""
    rich = CornerFacts(min_speed_kmh=88.0, min_speed_ref_kmh=95.0,
                       spread_kmh=6.0, brake_speed_kmh=212.0, brake_gear="4",
                       brake_distance_m=118.0, brake_spread_m=7.0,
                       brake_spread_kmh=4.0, landmark="at the kerb")
    for facts in (CornerFacts(), rich):
        for line in build_drill(category, phase, facts, lang).steps:
            assert "{" not in line and "}" not in line, line


def test_a_missing_number_drops_its_line_rather_than_leaving_a_hole():
    known = build_drill(CueCategory.BRAKE_LATER.value, "entry",
                        CornerFacts(brake_speed_kmh=212.0, brake_gear="4",
                                    brake_distance_m=118.0,
                                    brake_spread_m=7.0, min_speed_kmh=96.0), "en")
    blank = build_drill(CueCategory.BRAKE_LATER.value, "entry",
                        CornerFacts(), "en")
    assert any("212" in s for s in known.steps)
    assert len(blank.steps) < len(known.steps)


def test_the_braking_drill_keeps_the_speed_when_the_metres_are_missing():
    """Every ACC lap in our own archive reads 0 m for the braking distance —
    it needs coordinates — while the speed and gear are there on all of them.
    Dropping the whole line because half of it is missing threw away the half
    we had."""
    d = build_drill(CueCategory.BRAKE_LATER.value, "entry",
                    CornerFacts(brake_speed_kmh=212.0, brake_gear="4",
                                brake_spread_kmh=4.0), "it")
    assert any("212" in s for s in d.steps)
    assert not any(" m " in s and "212" in s for s in d.steps)
    assert any("4 km/h" in s for s in d.steps), "the wobble, in the unit we have"


def test_the_printed_speed_difference_matches_the_printed_speeds():
    """80.4 against 76.8 printed "80 km/h", "77 km/h" and then "+4"."""
    d = build_drill(CueCategory.CARRY_SPEED.value, "apex",
                    CornerFacts(min_speed_kmh=76.8, min_speed_ref_kmh=80.4), "en")
    line = next(s for s in d.steps if "km/h" in s)
    assert "80 km/h" in line and "77" in line and "+3" in line


def test_a_speed_gap_inside_your_own_spread_is_not_offered_as_a_target():
    """It came out as "the reference goes through at 92, you at 92: +0 km/h"."""
    d = build_drill(CueCategory.CARRY_SPEED.value, "apex",
                    CornerFacts(min_speed_kmh=92.0, min_speed_ref_kmh=92.4), "en")
    assert not any("+0" in s for s in d.steps)


# --- the words a beginner has to get through -------------------------------
# This tab exists for the driver who can't do the last step alone, so the prose
# is part of the feature. Checked here rather than left to review, because
# jargon comes back one edit at a time and nobody notices until a beginner does.

from accoach.coaching.training import _T          # noqa: E402 - prose under test


def _drill_groups(lang):
    """{drill key: all its sentences}, plus the page's own text as one group."""
    groups = {}
    for k, v in _T[lang].items():
        name = k.split(".")[1] if k.startswith("d.") else "_page"
        groups.setdefault(name, []).append(v)
    return groups


@pytest.mark.parametrize("lang,banned", [
    ("it", ("staccata", "stacchi", "digitale")),
    ("en", ("not digital", "radius")),
])
def test_words_a_plain_one_would_have_done_are_gone(lang, banned):
    """"Il punto in cui inizi a frenare" says the same as "la staccata" and
    costs a beginner nothing. Where a plain word loses nothing, it wins."""
    for word in banned:
        hits = [k for k, v in _T[lang].items() if word in v.lower()]
        assert not hits, f"{word!r} is back in {hits}"


@pytest.mark.parametrize("lang,term,gloss", [
    ("it", "apex", "più stretto"),
    ("en", "apex", "tightest"),
])
def test_a_term_that_stays_is_explained_inside_the_drill_that_uses_it(
        lang, term, gloss):
    """The gloss travels with the term because only one drill is ever open on
    screen: explaining "apex" in the drill above is explaining it to nobody."""
    for name, lines in _drill_groups(lang).items():
        text = " ".join(lines).lower()
        if term not in text:
            continue
        assert gloss in text, f"{name} uses {term!r} without explaining it"


@pytest.mark.parametrize("lang,term,definition", [
    ("it", "ideale teorico", "settore"),
    ("en", "theoretical ideal", "sector"),
])
def test_the_app_s_own_jargon_is_defined_before_it_is_named(lang, term,
                                                            definition):
    """Not the other way round: the sentence says what the thing is and *then*
    gives it its name, so the reader is never carrying an undefined word."""
    users = [k for k, v in _T[lang].items() if term in v.lower()]
    assert users, "the term should still be taught — the other tabs use it"
    for k in users:
        v = _T[lang][k].lower()
        assert definition in v, f"{k} names {term!r} without saying what it is"
        assert v.index(definition) < v.index(term), \
            f"{k} names {term!r} before defining it"


# --- the programme ----------------------------------------------------------

def _run(plan, debriefs, gap=None, progress=None, laps=MIN_LAPS + 2,
         inherited=None, lang="it"):
    return build_programme(plan, progress or [], debriefs, gap, {},
                           valid_laps=laps, lang=lang,
                           inherited_sources=inherited)


def test_below_the_gate_the_programme_is_the_gate():
    p = _run(_plan(_goal(0)), [_debrief()], laps=MIN_LAPS - 1)
    assert not p.readiness.ready and not p.steps and p.session is None


def test_exactly_one_step_is_the_one_to_do_now():
    ds = [_debrief(_loss(0, 400.0), _loss(1, 300.0)) for _ in range(4)]
    p = _run(_plan(_goal(0), _goal(1)), ds)
    assert [s.status for s in p.steps].count("now") == 1
    assert p.steps[0].status == "now"


def test_a_finished_goal_is_not_the_step_you_are_told_to_do():
    ds = [_debrief(_loss(0, 400.0), _loss(1, 300.0)) for _ in range(4)]
    done = GoalProgress(corner_index=0, laps=5, hits=4, needed=3,
                        median_ms=100.0, best_ms=50.0, done=True)
    p = _run(_plan(_goal(0), _goal(1)), ds, progress=[done])
    assert p.steps[0].status == "done"
    assert p.steps[1].status == "now"
    assert p.session.lines, "the session belongs to the step you can still do"


def test_the_corner_that_causes_another_ones_loss_goes_first():
    """Fix the corner that hands over the deficit and you fix two; do it the
    other way round and you fix neither."""
    ds = [_debrief(_loss(0, 200.0),
                   _loss(1, 500.0, inherited_from=0, inherited="You arrive 5 km/h down."))
          for _ in range(4)]
    p = _run(_plan(_goal(1, baseline=500.0), _goal(0, baseline=200.0)), ds,
             inherited={0})
    assert p.steps[0].corner_index == 0, "the source, not the bigger number"


def test_the_chain_names_the_corner_that_pays_not_this_one():
    """The debrief's own chain sentence is written from the victim's side, so
    printing it on the causing corner's card read as inheriting from itself."""
    ds = [_debrief(_loss(0, 200.0),
                   _loss(1, 500.0, name="Tamburello", inherited_from=0,
                         inherited="You arrive 5 km/h down."))
          for _ in range(4)]
    p = _run(_plan(_goal(0)), ds, inherited={0})
    assert "Tamburello" in p.steps[0].why


def test_only_one_step_ever_says_start_here():
    """The "why" is about position, and the position isn't settled until the
    consistency step has taken its place. Filled earlier, two steps claimed to
    be first."""
    ds = [_debrief(_loss(0, 400.0), _loss(1, 300.0)) for _ in range(4)]
    gap = _gap(best=100_000, ideal=99_000)     # a real consistency gap
    p = _run(_plan(_goal(0), _goal(1)), ds, gap=gap)
    assert len(p.steps) > 1
    # Two later steps may well share a reason ("one at a time"); what must never
    # repeat is the claim to be the one you start with.
    assert p.steps[0].why not in [s.why for s in p.steps[1:]]


def test_repeating_yourself_comes_first_when_it_is_worth_more():
    """A driver leaving half a second on the table by never stringing two laps
    together is not short of technique."""
    ds = [_debrief(_loss(0, 200.0)) for _ in range(4)]
    gap = _gap(best=100_000, ideal=99_000)     # 1.00s of consistency
    p = _run(_plan(_goal(0, baseline=200.0)), ds, gap=gap)
    assert p.steps[0].kind == "consistency"


def test_repeating_yourself_comes_last_when_the_corners_are_worth_more():
    ds = [_debrief(_loss(0, 900.0)) for _ in range(4)]
    gap = _gap(best=100_000, ideal=99_800)     # 0.20s of consistency
    p = _run(_plan(_goal(0, baseline=900.0)), ds, gap=gap)
    assert p.steps[0].kind == "corner"
    assert p.steps[-1].kind == "consistency"


def test_a_lap_you_already_repeat_gets_no_consistency_step():
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    gap = _gap(best=100_000, ideal=99_950)     # 50ms — under the floor
    p = _run(_plan(_goal(0)), ds, gap=gap)
    assert all(s.kind != "consistency" for s in p.steps)


def test_the_programme_never_grows_past_its_cap():
    ds = [_debrief(*[_loss(i, 400.0) for i in range(4)]) for _ in range(4)]
    p = _run(_plan(*[_goal(i) for i in range(4)]), ds,
             gap=_gap(best=100_000, ideal=99_000))
    assert len(p.steps) <= MAX_STEPS


def test_the_session_runs_one_drill_and_says_so_in_laps():
    """Two drills in one run cancel each other out — one says leave the braking
    point alone, the other says move it."""
    ds = [_debrief(_loss(0, 400.0), _loss(1, 300.0)) for _ in range(4)]
    p = _run(_plan(_goal(0),
                   _goal(1, baseline=300.0, category=CueCategory.BRAKE_LATER)), ds)
    assert p.session.laps == p.steps[0].drill.laps + 6      # warm-up + free laps
    body = " ".join(p.session.lines)
    assert p.steps[0].drill.title != p.steps[1].drill.title
    assert p.steps[0].drill.title in body
    assert p.steps[1].drill.title not in body


def test_the_session_line_has_no_dangling_dash_when_there_is_no_corner():
    """The consistency step has no corner, and the line ended in a dash
    standing where a corner name should be."""
    ds = [_debrief(_loss(0, 200.0)) for _ in range(4)]
    p = _run(_plan(_goal(0, baseline=200.0)), ds,
             gap=_gap(best=100_000, ideal=99_000))
    assert p.steps[0].kind == "consistency"
    assert not any(line.rstrip().endswith("—") or " — ." in line
                   for line in p.session.lines)


def test_an_accepted_plans_date_is_what_the_session_points_at():
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    plan = _plan(_goal(0))
    plan.created_utc = "2026-07-31T12:00:00+00:00"
    p = _run(plan, ds)
    assert "2026-07-31" in p.session.lines[-1]


@pytest.mark.parametrize("lang", ("it", "en"))
def test_nothing_the_programme_prints_is_left_unformatted(lang):
    ds = [_debrief(_loss(0, 400.0), _loss(1, 300.0)) for _ in range(4)]
    p = _run(_plan(_goal(0), _goal(1)), ds,
             gap=_gap(best=100_000, ideal=99_000), lang=lang)
    text = [p.gap.headline, p.gap.note] + p.session.lines
    for s in p.steps:
        text += [s.why, s.target, s.done_when] + s.drill.steps
    for line in text:
        assert "{" not in line and "}" not in line, line


def test_the_programme_serialises_whole():
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    d = _run(_plan(_goal(0)), ds, gap=_gap()).to_dict()
    assert d["ready"] is True
    assert d["steps"][0]["drill"]["steps"]
    assert d["gap"]["sectors"] and d["session"]["lines"]


def test_a_heading_that_says_nothing_is_not_printed():
    """"Time lost here" is the debrief's label for a corner with no dominant
    cause. On a card that already names the corner, says why it's first and
    gives a target, it is a heading that tells the reader nothing — and the
    drill's own first line says it properly."""
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    p = _run(_plan(_goal(0, category=CueCategory.TIME_LOSS)), ds)
    assert p.steps[0].what == ""
    assert p.steps[0].drill.steps[0], "the drill still explains it"


def test_a_heading_that_says_something_is_kept():
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    goal = _goal(0, category=CueCategory.BRAKE_LATER)
    goal.what = "Frena più tardi"
    p = _run(_plan(goal), ds)
    assert p.steps[0].what == "Frena più tardi"


def test_a_goals_target_is_the_plans_and_is_not_recomputed_here():
    """One notion of "done", and it lives in plan.py."""
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    p = _run(_plan(_goal(0, baseline=437.0, target=219.0)), ds)
    assert "0.22" in p.steps[0].target and "0.44" in p.steps[0].target


def test_the_significance_floor_is_the_one_the_rest_of_the_app_uses():
    """A consistency step for a gap the debrief wouldn't mention would be a
    target the app refuses to talk about if you hit it."""
    ds = [_debrief(_loss(0, 400.0)) for _ in range(4)]
    just_under = _gap(best=100_000, ideal=100_000 - int(SIGNIF_LOSS_MS) + 1)
    assert all(s.kind != "consistency"
               for s in _run(_plan(_goal(0)), ds, gap=just_under).steps)
