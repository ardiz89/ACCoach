"""The editing rules: what gets said, in what order, and what gets dropped.

Every assertion here is about a decision this module makes on the driver's
behalf. The analysis is the debrief's job and is tested elsewhere; what can go
wrong *here* is saying too much, saying it in the wrong order, or — worst —
saying something the debrief never found.
"""
import pytest

from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief, LapNote
from accoach.coaching.flow import MAX_STEPS, MIN_STEP_MS, build_flow


def _loss(lost_ms, index=0, category=CueCategory.CARRY_SPEED, **kw):
    return CornerLoss(
        index=index, entry_pos=0.10 * (index + 1), apex_pos=0.10 * (index + 1) + 0.02,
        exit_pos=0.10 * (index + 1) + 0.04, lost_ms=lost_ms, category=category,
        message=kw.pop("message", "Porta più velocità in ingresso"),
        name=kw.pop("name", f"Curva {index + 1}"), **kw)


def _note(lost_ms, kind="lift", **kw):
    return LapNote(kind=kind, message=kw.pop("message", "Sollevi in pieno"),
                   lost_ms=lost_ms, pos=kw.pop("pos", 0.5), **kw)


def _debrief(losses=(), notes=(), headline="", lap_ms=100_000, ref_ms=99_000):
    return LapDebrief(car_model="ferrari_488", track="monza", lap_time_ms=lap_ms,
                      reference_lap_ms=ref_ms, losses=list(losses),
                      notes=list(notes), headline=headline)


# --- how much gets said ----------------------------------------------------

def test_a_long_debrief_is_cut_to_a_few_steps():
    """Eighteen corners is a list. The point of the flow is that it isn't one."""
    d = _debrief(losses=[_loss(900 - i * 10, i) for i in range(18)])
    assert len(build_flow(d)) == MAX_STEPS


def test_the_worst_thing_is_first():
    d = _debrief(losses=[_loss(200, 0), _loss(800, 1), _loss(400, 2)])
    assert build_flow(d)[0].lost_ms == 800


def test_findings_below_the_floor_are_dropped():
    d = _debrief(losses=[_loss(500, 0), _loss(MIN_STEP_MS - 1, 1)])
    steps = build_flow(d)
    assert len(steps) == 1 and steps[0].lost_ms == 500


def test_when_everything_is_small_the_biggest_is_still_said():
    """"Nothing above my threshold" and "nothing" are different answers, and the
    driver asked what happened on this lap."""
    d = _debrief(losses=[_loss(20, 0), _loss(45, 1)])
    steps = build_flow(d)
    assert len(steps) == 1
    assert steps[0].lost_ms == 45
    assert steps[0].kind == "corner"


# --- the order -------------------------------------------------------------

def test_lap_wide_findings_come_before_corners_even_when_they_cost_less():
    """A driver who fixes a corner while lifting on the back straight has fixed
    the smaller thing. The per-corner list structurally can't hold this."""
    d = _debrief(losses=[_loss(900, 0)], notes=[_note(300)])
    steps = build_flow(d)
    assert [s.kind for s in steps] == ["lapwide", "corner"]


def test_lap_wide_findings_are_ranked_among_themselves():
    d = _debrief(notes=[_note(200, message="piccola"), _note(700, message="grossa")])
    assert build_flow(d)[0].title == "grossa"


def test_the_theme_leads_and_shortens_the_flow():
    """The theme exists because the gap is too big for corner-by-corner to be
    the right lens; following it with three corners contradicts it."""
    d = _debrief(losses=[_loss(900 - i * 10, i) for i in range(6)],
                 headline="Sei a 3.1% dal riferimento: lavora sulla frenata.")
    steps = build_flow(d)
    assert steps[0].kind == "headline"
    assert len(steps) == 2
    assert steps[1].kind == "corner"


# --- what a step carries ---------------------------------------------------

def test_the_cause_is_not_repeated_in_the_numbers():
    """`build_lap_debrief` prepends the cause to `detail` for the text debrief.
    On a card with a body and a figures line, that would say it twice."""
    d = _debrief(losses=[_loss(
        500, 0, cause="L'anteriore scivola in ingresso.",
        detail="L'anteriore scivola in ingresso. Minima all'apex 92 vs 98 km/h.")])
    step = build_flow(d)[0]
    assert step.body == "L'anteriore scivola in ingresso."
    assert step.detail == "Minima all'apex 92 vs 98 km/h."


def test_a_detail_that_does_not_start_with_the_cause_is_left_alone():
    d = _debrief(losses=[_loss(500, 0, cause="Sovrasterzo.",
                               detail="Gas medio 41% contro 62%.")])
    assert build_flow(d)[0].detail == "Gas medio 41% contro 62%."


def test_the_step_opens_the_chart_that_shows_its_point():
    """A step about the brake release that opens a speed chart makes the reader
    do the translation."""
    pedals = _debrief(losses=[_loss(500, 0, category=CueCategory.MORE_THROTTLE)])
    speed = _debrief(losses=[_loss(500, 0, category=CueCategory.CARRY_SPEED)])
    assert build_flow(pedals)[0].chart == "inputs"
    assert build_flow(speed)[0].chart == "speed"


def test_the_window_leaves_more_room_after_the_corner_than_before():
    """The debrief credits the following straight to the corner that caused it,
    so the exit is where the time actually appears."""
    step = build_flow(_debrief(losses=[_loss(500, 0)]))[0]
    assert step.from_pos < 0.10
    assert step.to_pos > 0.14
    assert (step.to_pos - 0.14) > (0.10 - step.from_pos)


def test_the_window_never_leaves_the_lap():
    at_the_line = _loss(500, 0)
    at_the_line.entry_pos, at_the_line.exit_pos = 0.001, 0.995
    step = build_flow(_debrief(losses=[at_the_line]))[0]
    assert step.from_pos >= 0.0 and step.to_pos <= 1.0


def test_the_corner_is_named():
    step = build_flow(_debrief(losses=[_loss(500, 0, name="Variante Ascari")]))[0]
    assert step.where == "Variante Ascari"


# --- when there is nothing to say ------------------------------------------

def test_the_reference_lap_says_so_instead_of_inventing_a_lesson():
    d = _debrief(losses=[], lap_ms=99_000, ref_ms=100_000)
    steps = build_flow(d)
    assert len(steps) == 1 and steps[0].kind == "clean"
    assert steps[0].fix == ""


def test_a_slower_lap_with_no_findings_is_honest_about_it():
    d = _debrief(losses=[], notes=[], lap_ms=100_000, ref_ms=99_000)
    steps = build_flow(d)
    assert len(steps) == 1 and steps[0].kind == "clean"
    assert steps[0].body


def test_a_flow_is_never_empty():
    assert build_flow(_debrief())


# --- languages -------------------------------------------------------------

@pytest.mark.parametrize("lang", ("it", "en"))
def test_both_languages_have_the_frame_strings(lang):
    d = _debrief(losses=[_loss(900, 0)], headline="tema")
    steps = build_flow(d, lang=lang)
    assert steps[0].title
    clean = build_flow(_debrief(lap_ms=99_000, ref_ms=100_000), lang=lang)[0]
    assert clean.title and clean.body


def test_an_unknown_language_falls_back_rather_than_showing_keys():
    step = build_flow(_debrief(lap_ms=99_000, ref_ms=100_000), lang="de")[0]
    assert step.title and "clean" not in step.title


# --- the boundary this module must not cross -------------------------------

def test_no_step_states_a_fact_the_debrief_did_not_produce():
    """This module edits; it must never analyse. Every figure on a step has to
    be traceable to the debrief it was handed."""
    losses = [_loss(500, 0, detail="Minima 92 vs 98 km/h.", fix="Frena meno.")]
    notes = [_note(300, detail="0.21 s sul rettilineo.")]
    d = _debrief(losses=losses, notes=notes)
    known = {l.detail for l in losses} | {n.detail for n in notes} | {""}
    known |= {l.fix for l in losses}
    for step in build_flow(d):
        assert step.detail in known
        assert step.fix in known
