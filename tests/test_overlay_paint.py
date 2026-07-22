"""The overlay's numbers fit in their boxes, and the braking cue flips on time.

The delta was drawn at 28px into a 34px-high rect, top-aligned: on screen the
bottom of the digits was sliced off (reported from a real session, "+156.454"
with its baseline cut). Qt clips silently, so nothing but a rendered pixel or the
font metrics can catch it — this measures the metrics.

The braking countdown switches on *time* to the point, not metres, because ten
metres is 0.14 s at 250 km/h and half a second in a slow corner. These pin the
behaviour at both ends of that range.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from accoach.overlay import (       # noqa: E402
    _BRAKE_NEAR_S,
    _BRAKE_NOW_S,
    _DELTA_BOX_H,
    _DELTA_FONT_PX,
)


def test_the_delta_box_is_taller_than_the_glyphs_line_box():
    """A line box is ~1.2-1.4x the pixel size; the box must clear that.

    Measured with QFontMetrics instead? No: headless Qt ships no fonts at all
    ("Cannot find font directory"), and reports a 28px font's height as exactly
    28 — it would have passed the old 34px box that was demonstrably clipping.
    """
    assert _DELTA_BOX_H >= _DELTA_FONT_PX * 1.4


def test_the_box_that_used_to_clip_would_now_fail():
    """Pins the regression: 34 was the value that sliced the digits."""
    assert 34 < _DELTA_FONT_PX * 1.4


# --- braking cue: the threshold is seconds, not metres --------------------

def _seconds(metres: float, kmh: float) -> float:
    return metres / max(1.0, kmh / 3.6)


def test_ten_metres_is_already_too_late_at_speed():
    """The reason the old fixed-distance idea was wrong, stated as a test."""
    assert _seconds(10, 250) < _BRAKE_NOW_S


def test_the_same_ten_metres_is_early_in_a_slow_corner():
    assert _seconds(10, 60) > _BRAKE_NOW_S


def test_now_fires_before_human_reaction_time_runs_out():
    """~0.25 s is the reaction; the colour has to land with the foot, not after."""
    assert _BRAKE_NOW_S >= 0.25


def test_near_leaves_room_to_prepare_but_not_to_stare():
    assert _BRAKE_NOW_S < _BRAKE_NEAR_S <= 2.5


def test_the_bands_are_ordered_the_way_the_driver_meets_them():
    """Far → near → now, as the metres count down at any fixed speed."""
    kmh = 200.0
    far, near, now = (_seconds(m, kmh) for m in (150, 80, 15))
    assert far > _BRAKE_NEAR_S >= near > _BRAKE_NOW_S >= now
