"""Where inside a corner the time went — and the property that makes it honest.

The whole feature rests on one invariant: the four stretches are a
*decomposition* of the corner's loss, so they add back up to it exactly. If they
ever stop doing that, the panel becomes four plausible numbers next to a fifth
that disagrees with them, which is worse than not splitting at all.
"""
import math

import pytest

from accoach.coaching.debrief import build_lap_debrief
from accoach.coaching.diagnosis import _APEX_HALF
from accoach.coaching.phases import (
    PHASES,
    PhaseLoss,
    phase_note,
    split_loss,
)
from accoach.coaching.thresholds import SIGNIF_LOSS_MS
from accoach.comparison import Reference
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType
from accoach.track import Corner, detect_corners


def _lap(penalty_zones=(), n=800) -> Lap:
    """A two-corner circuit; time can be added over any stretch of it.

    Time, not speed: the split measures how the gap grows, so a test that wants
    a tenth to appear inside the apex window has to put it exactly there.
    """
    s = []
    penalty = 0.0
    for i in range(n):
        pos = i / (n - 1)
        speed, steer, brake, thr = 250.0, 0.0, 0.0, 1.0
        for lo, apex, hi in ((0.20, 0.27, 0.35), (0.60, 0.67, 0.75)):
            if lo - 0.05 <= pos <= hi:
                d = min(1.0, abs(pos - apex) / ((hi - lo) / 2))
                speed = 100.0 + 150.0 * d
                steer = 0.30 * (1.0 - d)
                brake = 0.9 if lo - 0.05 <= pos < apex else 0.0
                thr = 1.0 if pos >= apex else 0.0
        for a, b in penalty_zones:
            if a <= pos <= b:
                penalty += 3.0
        s.append(LapSample(int(pos * 100000 + penalty), pos, speed, thr, brake,
                           steer, "4", 8000, 0.0, 0.0,
                           car_x=1000.0 * math.cos(2 * math.pi * pos),
                           car_z=1000.0 * math.sin(2 * math.pi * pos)))
    return Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE,
               int(100000 + penalty), True, samples=s)


def _setup(review):
    ref = _lap()
    corners = detect_corners(ref.samples)
    assert len(corners) == 2
    return review, Reference(ref), corners


def _window(lap, corner, end):
    return [s for s in lap.samples if corner.entry_pos <= s.pos < end]


# --- the invariant ----------------------------------------------------------

def test_the_parts_add_up_to_the_whole():
    """Not an estimate: a decomposition. This is the property the panel sells."""
    review, reference, corners = _setup(_lap(penalty_zones=((0.20, 0.45),)))
    c = corners[0]
    window = _window(review, c, corners[1].entry_pos)
    parts = split_loss(window, reference, c)
    first, last = window[0], window[-1]
    whole = ((last.t_ms - reference.time_at(last.pos))
             - (first.t_ms - reference.time_at(first.pos)))
    assert sum(p.lost_ms for p in parts) == pytest.approx(whole, abs=1.0)


def test_it_always_returns_the_same_four_stretches():
    """A corner where you never reached the apex window is a corner with a zero
    apex phase, not one with three phases and a reader left guessing."""
    review, reference, corners = _setup(_lap())
    parts = split_loss(_window(review, corners[0], corners[1].entry_pos),
                       reference, corners[0])
    assert [p.phase for p in parts] == list(PHASES)


def test_a_lap_identical_to_the_reference_loses_nothing_anywhere():
    review, reference, corners = _setup(_lap())
    parts = split_loss(_window(review, corners[0], corners[1].entry_pos),
                       reference, corners[0])
    assert all(abs(p.lost_ms) < 1.0 for p in parts)


def test_a_window_too_short_to_cut_is_not_cut():
    review, reference, corners = _setup(_lap())
    assert split_loss([], reference, corners[0]) == []


# --- the time lands where it was spent --------------------------------------

def _lost_in(phase, parts):
    return next(p.lost_ms for p in parts if p.phase == phase)


def test_time_lost_on_entry_is_reported_on_entry():
    c0 = detect_corners(_lap().samples)[0]
    # Everything from the corner's entry to just before the apex window.
    review, reference, corners = _setup(
        _lap(penalty_zones=((c0.entry_pos, c0.apex_pos - _APEX_HALF - 0.01),)))
    parts = split_loss(_window(review, corners[0], corners[1].entry_pos),
                       reference, corners[0])
    assert _lost_in("entry", parts) > 100.0
    assert _lost_in("apex", parts) < 20.0
    assert _lost_in("exit", parts) < 20.0


def test_time_lost_on_the_straight_after_is_not_blamed_on_the_corner():
    """The window reaches to the next corner on purpose; naming that stretch is
    what keeps the other three honest."""
    c0, c1 = detect_corners(_lap().samples)[:2]
    review, reference, corners = _setup(
        _lap(penalty_zones=((c0.exit_pos + 0.01, c1.entry_pos - 0.01),)))
    parts = split_loss(_window(review, corners[0], corners[1].entry_pos),
                       reference, corners[0])
    assert _lost_in("after", parts) > 100.0
    assert _lost_in("entry", parts) < 20.0


def test_a_stretch_where_you_were_quicker_reads_as_a_gain():
    """Signs are kept: "you lose four tenths on entry and take one back on exit"
    is a truer sentence than "you lose three tenths somewhere"."""
    parts = [PhaseLoss("entry", 400.0), PhaseLoss("apex", 0.0),
             PhaseLoss("exit", -100.0), PhaseLoss("after", 0.0)]
    note = phase_note(parts, 300.0, "en")
    assert "0.40s on entry" in note
    assert "0.10s back on exit" in note


# --- the sentence -----------------------------------------------------------

def test_the_sentence_names_the_stretch_that_dominates():
    parts = [PhaseLoss("entry", 60.0), PhaseLoss("apex", 250.0),
             PhaseLoss("exit", 10.0), PhaseLoss("after", 0.0)]
    assert phase_note(parts, 320.0, "it") == "Di questi, 0.25s all'apex."


def test_nothing_is_named_when_the_loss_is_spread_around_the_corner():
    """A corner that leaks a little everywhere has "everywhere" for an answer,
    and dressing that up as a place would be a confident wrong one."""
    parts = [PhaseLoss(p, 80.0) for p in PHASES]
    assert phase_note(parts, 320.0, "it") == ""


def test_nothing_is_named_for_a_corner_that_barely_cost_anything():
    parts = [PhaseLoss("entry", SIGNIF_LOSS_MS - 20.0)] + \
            [PhaseLoss(p, 0.0) for p in PHASES[1:]]
    assert phase_note(parts, SIGNIF_LOSS_MS - 20.0, "it") == ""


def test_it_speaks_both_languages():
    parts = [PhaseLoss("entry", 300.0)] + [PhaseLoss(p, 0.0) for p in PHASES[1:]]
    assert "in ingresso" in phase_note(parts, 300.0, "it")
    assert "on entry" in phase_note(parts, 300.0, "en")


def test_the_words_match_the_ones_the_cause_already_uses():
    """"all'apex" in one sentence and "sull'apice" in the next would read as two
    different places."""
    from accoach.coaching.debrief import _CAUSE_PHASE
    from accoach.coaching.diagnosis import Phase
    from accoach.coaching.phases import _WORDS

    for lang in ("it", "en"):
        cause = _CAUSE_PHASE[lang]
        assert _WORDS[lang]["entry"] == cause[Phase.ENTRY]
        assert _WORDS[lang]["apex"] == cause[Phase.APEX]
        assert _WORDS[lang]["exit"] == cause[Phase.EXIT]


# --- through a real debrief -------------------------------------------------

def test_every_loss_a_debrief_publishes_carries_its_breakdown():
    review, reference, corners = _setup(_lap(penalty_zones=((0.20, 0.45),)))
    debrief = build_lap_debrief(review, reference, corners, "en")
    assert debrief.losses
    for loss in debrief.losses:
        assert [p.phase for p in loss.phases] == list(PHASES)
        assert sum(p.lost_ms for p in loss.phases) == pytest.approx(loss.lost_ms,
                                                                   abs=1.0)


def test_the_debrief_writes_the_sentence_in_the_asked_language():
    review, reference, corners = _setup(_lap(penalty_zones=((0.20, 0.32),)))
    it = build_lap_debrief(review, reference, corners, "it").losses[0]
    en = build_lap_debrief(review, reference, corners, "en").losses[0]
    assert it.phase_note and en.phase_note
    assert it.phase_note != en.phase_note
