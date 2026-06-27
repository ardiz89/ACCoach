"""detect_corners: derive a track's corners from a reference lap."""
from accoach.track import Corner, detect_corners

import synth


def test_too_few_samples_yields_no_corners():
    assert detect_corners(synth.build_lap(n=8).samples) == []


def test_detects_both_corners_of_the_demo_track():
    corners = detect_corners(synth.build_lap().samples)
    assert len(corners) == 2
    # Apexes near the known speed minima at 0.31 and 0.71.
    assert abs(corners[0].apex_pos - 0.31) < 0.05
    assert abs(corners[1].apex_pos - 0.71) < 0.05


def test_entry_extends_back_over_the_braking_zone():
    corners = detect_corners(synth.build_lap().samples)
    c0 = corners[0]
    # Entry is pulled before the apex (over the braking zone) and ordered.
    assert c0.entry_pos < c0.apex_pos < c0.exit_pos


def test_corner_contains_and_indices():
    corners = detect_corners(synth.build_lap().samples)
    assert [c.index for c in corners] == [0, 1]
    c0 = corners[0]
    assert c0.contains(c0.apex_pos)
    assert not c0.contains(0.0)
    assert c0.mid == c0.apex_pos


def test_straights_are_outside_every_corner():
    corners = detect_corners(synth.build_lap().samples)
    # 0.5 sits on the straight between the two corners.
    assert all(not c.contains(0.5) for c in corners)
