"""The start/finish rule, now shared by the recorder and the coach.

They had a copy each. Both trusted the lap counter, both were wrong on ACC in the
same way, and the two failures looked nothing alike from the outside: the recorder
threw the first flying lap away, the coach sat through it saying "out lap". One
rule, one place, one fix.
"""
from accoach.recording.recorder import _WRAP_FROM, _WRAP_TO, crossed_start_line


def test_the_counter_alone_is_enough():
    assert crossed_start_line(0.5, 0.5, 3, 4) is True


def test_the_wrap_alone_is_enough():
    """ACC's out lap: over the line, counter still at zero. The measured case."""
    assert crossed_start_line(0.998, 0.002, 0, 0) is True


def test_neither_is_not_a_crossing():
    assert crossed_start_line(0.4, 0.42, 2, 2) is False


def test_the_first_frame_ever_is_not_a_crossing():
    """No previous frame = nothing to compare; opening a lap here would invent one."""
    assert crossed_start_line(None, 0.01, None, 0) is False


def test_going_backwards_over_the_line_is_not_a_crossing():
    """Reversing in the pit exit shouldn't open a lap."""
    assert crossed_start_line(0.02, 0.99, 0, 0) is False


def test_the_margins_are_wide_enough_for_a_slow_acquisition():
    """At 13 Hz and 270 km/h a lap moves ~0.006 between frames.

    The pair straddling the line can land well inside the bounds, so the bounds
    have to be loose. This pins why they aren't 0.99/0.01.
    """
    assert _WRAP_FROM <= 0.95 and _WRAP_TO >= 0.05


def test_a_mid_lap_position_jump_is_not_a_crossing():
    """A teleport to the pits lands mid-lap, not near either end."""
    assert crossed_start_line(0.7, 0.3, 1, 1) is False
