"""Corner shape derived from the driven line: direction, kind, radius.

The point of deriving it instead of tabulating it per track is that it works on
any circuit, mods included. So the tests pin the geometry (a circle of known
radius must read back as that radius) rather than any particular track.
"""
import math

import pytest
import synth

from accoach.track import _classify, _menger_curvature, detect_corners


def _arc(radius: float, clockwise: bool, n: int = 41) -> list[tuple[float, float]]:
    """Points on a circle of known radius, so the expected answer is exact."""
    step = 0.02                      # rad between samples
    out = []
    for i in range(n):
        a = i * step * (-1 if clockwise else 1)
        out.append((radius * math.cos(a), radius * math.sin(a)))
    return out


@pytest.mark.parametrize("radius", [15.0, 40.0, 130.0, 400.0])
def test_curvature_recovers_a_known_radius(radius):
    pts = _arc(radius, clockwise=False)
    mid = len(pts) // 2
    k = _menger_curvature(pts[mid - 3], pts[mid], pts[mid + 3])
    assert 1.0 / abs(k) == pytest.approx(radius, rel=1e-3)


def test_sign_convention_is_the_one_measured_on_track():
    """Negative curvature is left, positive is right.

    This mapping isn't derivable from the maths — it depends on how the game
    orients its world axes — so it was *measured*: on real Imola laps the sign
    agreed with the steering on 5 corners out of 5 (Tamburello, Tosa, Piratella,
    Rivazza left; Acque Minerali right). This test pins that mapping so a future
    refactor can't quietly mirror every corner in the product.
    """
    for clockwise in (False, True):
        pts = _arc(50.0, clockwise=clockwise)
        mid = len(pts) // 2
        k = _menger_curvature(pts[mid - 3], pts[mid], pts[mid + 3])
        assert _classify(pts, mid, 90.0)[0] == ("right" if k > 0 else "left")


def test_the_two_ways_round_are_opposite():
    mid = len(_arc(50.0, clockwise=False)) // 2
    left = _classify(_arc(50.0, clockwise=False), mid, 90.0)[0]
    right = _classify(_arc(50.0, clockwise=True), mid, 90.0)[0]
    assert {left, right} == {"left", "right"}


def test_hairpin_wins_over_apex_speed():
    """A tight radius reads as a hairpin even if the apex speed says otherwise.

    A hairpin is a hairpin: it's the geometry that dictates the technique, and
    apex speed on its own would mislabel a slow corner that simply isn't tight.
    """
    tight = _arc(25.0, clockwise=False)
    mid = len(tight) // 2
    assert _classify(tight, mid, 70.0)[1] == "hairpin"
    assert _classify(tight, mid, 200.0)[1] == "hairpin"


def test_kind_splits_on_apex_speed_when_not_tight():
    wide = _arc(180.0, clockwise=False)
    mid = len(wide) // 2
    assert _classify(wide, mid, 80.0)[1] == "slow"
    assert _classify(wide, mid, 130.0)[1] == "medium"
    assert _classify(wide, mid, 200.0)[1] == "fast"


def test_straight_line_has_no_shape():
    """Three collinear points have no circle through them — report unknown."""
    straight = [(float(i) * 5.0, 0.0) for i in range(20)]
    assert _classify(straight, 10, 150.0) == ("", "", 0.0)


def test_corners_on_a_synthetic_lap_are_classified():
    corners = detect_corners(synth.build_lap().samples)
    assert corners, "the synthetic lap should still produce corners"
    for c in corners:
        assert c.direction in ("left", "right")
        assert c.kind in ("hairpin", "slow", "medium", "fast")
        assert c.radius_m > 0.0
        assert c.apex_speed_kmh > 0.0


def test_lap_without_coordinates_still_detects_corners():
    """Laps recorded before the map update must degrade, not break."""
    lap = synth.build_lap()
    for s in lap.samples:
        s.car_x = 0.0
        s.car_z = 0.0
    corners = detect_corners(lap.samples)
    assert corners, "corner detection must not depend on coordinates"
    for c in corners:
        assert c.direction == ""
        assert c.kind == ""
        assert c.radius_m == 0.0
        # Apex speed comes from the speed trace, so it survives.
        assert c.apex_speed_kmh > 0.0


def test_median_ignores_a_single_wobble():
    """One bad sample at the apex — a kerb, a correction — must not set the shape."""
    pts = _arc(60.0, clockwise=False)
    mid = len(pts) // 2
    clean = _classify(pts, mid, 120.0)
    pts[mid] = (pts[mid][0] + 3.0, pts[mid][1] - 3.0)     # yank the line sideways
    assert _classify(pts, mid, 120.0)[0] == clean[0]      # direction holds
    assert _classify(pts, mid, 120.0)[1] == clean[1]      # kind holds
