"""The driven line, measured.

Two things are checked here that a screenshot cannot check: that a metre to the
right of the reference is reported as *inside* on a right-hander and *outside*
on a left-hander (the sign convention the whole view rests on), and that nothing
is reported at all when the difference is inside the floor the module declares.

The fixture is a circle, because a circle is the one shape whose radius, arc
length and offsets are known in closed form — so the numbers can be asserted
against geometry rather than against whatever the code happened to produce.
"""
import math

import pytest

from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType
from accoach.track import Corner, detect_corners
from accoach.trajectory import (
    build_line_report,
    corner_path,
    curvature_profile,
    lateral_offsets,
    line_points,
    path_length,
    radius_over,
    tag_text,
)

R = 100.0          # radius of the fixture circle, metres
N = 720            # samples per lap (one every half degree ≈ 0.87 m)


def _circle_lap(radius=R, turn="right", speed=90.0, n=N) -> Lap:
    """A lap driven round a circle of ``radius`` metres, turning one way.

    ``turn`` is stated in the sim's own convention (positive curvature = right),
    not in the sense the points would *look* like if you plotted x rightwards:
    AC/ACC world coordinates are left-handed, so a top-down plot of raw (x, z)
    comes out mirrored — which is why the track map flips X before drawing. The
    fixture follows the convention the code is validated against, so a test
    can't quietly encode the mirrored one.
    """
    s = []
    for i in range(n):
        pos = i / n
        a = 2 * math.pi * pos * (-1.0 if turn == "right" else 1.0)
        x = radius * math.sin(a)
        z = radius * math.cos(a)
        # A gentle speed dip so there is one unambiguous "apex" per lap half.
        v = speed - 20.0 * math.sin(2 * math.pi * pos)
        s.append(LapSample(int(pos * 100000), pos, v, 0.5, 0.0,
                           0.2, "3", 5000, 0.0, 0.0, car_x=x, car_z=z))
    return Lap("Fixture", "Circle", SessionType.PRACTICE, 100000, True, samples=s)


def _corner(index=0, entry=0.10, apex=0.20, exit=0.30, direction="right") -> Corner:
    return Corner(index=index, entry_pos=entry, apex_pos=apex, exit_pos=exit,
                  direction=direction, kind="medium")


# --- the primitives ---------------------------------------------------------

def test_path_length_of_a_circle_is_its_circumference():
    pts = line_points(_circle_lap())
    # One chord short of the full circle on purpose: a lap's path runs from the
    # first sample to the last, and the closing segment back over the line
    # belongs to the next lap.
    chord = 2 * math.pi * R / N
    assert path_length(pts) == pytest.approx(2 * math.pi * R - chord, abs=0.05)


def test_path_length_of_a_quarter_is_a_quarter():
    pts = line_points(_circle_lap())
    assert path_length(pts, 0.0, 0.25) == pytest.approx(2 * math.pi * R / 4, rel=2e-3)


def test_curvature_of_a_circle_is_one_over_its_radius():
    pts = line_points(_circle_lap(radius=80.0))
    k = curvature_profile(pts)
    mid = k[len(k) // 2]
    assert abs(mid) == pytest.approx(1 / 80.0, rel=0.02)


def test_curvature_is_positive_going_right_and_negative_going_left():
    right = curvature_profile(line_points(_circle_lap(turn="right")))
    left = curvature_profile(line_points(_circle_lap(turn="left")))
    assert right[len(right) // 2] > 0
    assert left[len(left) // 2] < 0


def test_radius_over_reports_the_circle_and_ignores_a_single_spike():
    lap = _circle_lap(radius=120.0)
    pts = line_points(lap)
    k = curvature_profile(pts)
    # One kerb strike: three samples of wild curvature.
    for i in range(300, 303):
        k[i] = 1 / 5.0
    assert radius_over(pts, k, 0.30, 0.60) == pytest.approx(120.0, rel=0.05)


def test_a_straight_line_reports_no_radius():
    """R = 3 km is a true number that tells nobody anything — we report 0."""
    s = [LapSample(i * 100, i / 200, 200.0, 1.0, 0.0, 0.0, "5", 7000, 0.0, 0.0,
                   car_x=float(i), car_z=0.0) for i in range(200)]
    lap = Lap("Fixture", "Straight", SessionType.PRACTICE, 20000, True, samples=s)
    pts = line_points(lap)
    assert radius_over(pts, curvature_profile(pts), 0.0, 1.0) == 0.0


# --- offsets ----------------------------------------------------------------

def test_a_wider_line_reads_as_offset_to_the_left_of_a_clockwise_reference():
    """Sign convention, pinned: positive = to the right of the reference.

    A car on a bigger circle than the reference through a right-hander is on the
    OUTSIDE, which is to its left — so the raw offset must be negative.
    Everything the view says about inside/outside rests on this.
    """
    ref = line_points(_circle_lap(radius=100.0))
    wide = line_points(_circle_lap(radius=103.0))
    off = lateral_offsets(wide, ref)
    assert off, "offsets should not be empty for two real lines"
    mid = off[len(off) // 2]
    assert mid < 0
    assert abs(mid) == pytest.approx(3.0, abs=0.3)


def test_offsets_are_empty_when_the_reference_has_no_geometry():
    ref = line_points(Lap("F", "T", SessionType.PRACTICE, 1000, True, samples=[]))
    assert lateral_offsets(line_points(_circle_lap()), ref) == []


# --- the corner report ------------------------------------------------------

def _report(review_radius, direction="right", base_radius=100.0):
    base = _circle_lap(radius=base_radius, turn=direction)
    review = _circle_lap(radius=review_radius, turn=direction)
    return build_line_report(review, base, [_corner(direction=direction)],
                             names={0: "Turn 1"})


def test_running_wide_on_a_right_hander_reads_as_outside():
    r = _report(103.0, direction="right")
    c = r.corners[0]
    assert c.apex_m < 0, "outside must be negative"
    assert c.widest_m == pytest.approx(3.0, abs=0.4)
    assert c.tightest_m == 0.0


def test_the_turn_direction_decides_what_a_metre_to_the_right_means():
    """The whole point of the inside/outside column, in one test.

    The same raw displacement — a metre to the right of the reference line — is
    the *inside* of a right-hander and the *outside* of a left-hander. Get this
    backwards and every corner of the view is mirrored, which no amount of
    looking at the map would catch.
    """
    def raw(radius, turn):
        off = lateral_offsets(line_points(_circle_lap(radius=radius, turn=turn)),
                              line_points(_circle_lap(radius=100.0, turn=turn)))
        return off[len(off) // 2]

    # Tighter through a right-hander, wider through a left-hander: geometrically
    # opposite lines, but both sit to the RIGHT of their reference.
    assert raw(97.0, "right") > 0
    assert raw(103.0, "left") > 0

    assert _report(97.0, direction="right").corners[0].apex_m > 0    # inside
    assert _report(103.0, direction="left").corners[0].apex_m < 0    # outside


def test_a_corner_the_detector_could_not_classify_keeps_the_raw_side():
    """No direction means no inside: we report the raw side rather than pick one."""
    base = _circle_lap(radius=100.0)
    review = _circle_lap(radius=103.0)
    c = build_line_report(review, base, [_corner(direction="")]).corners[0]
    assert c.direction == ""
    assert c.apex_m == pytest.approx(-3.0, abs=0.4)


def test_a_wider_line_is_a_longer_line():
    c = _report(103.0).corners[0]
    # The corner spans a fifth of the circle: 2πΔR/5 ≈ 3.8 m more tarmac.
    assert c.extra_m == pytest.approx(2 * math.pi * 3.0 / 5, abs=0.4)


def test_the_radius_you_drove_is_reported_next_to_the_reference_s():
    c = _report(130.0).corners[0]
    assert c.radius_m == pytest.approx(130.0, rel=0.06)
    assert c.radius_ref_m == pytest.approx(100.0, rel=0.06)


def test_an_identical_lap_produces_no_tags_at_all():
    """The floors exist so a driver isn't shown their own noise as findings."""
    c = _report(100.0).corners[0]
    assert c.tags == []
    assert abs(c.extra_m) < 0.5


def test_a_difference_under_the_floor_is_not_reported():
    c = _report(100.4).corners[0]         # 0.4 m — under the 0.8 m floor
    assert [k for k, _ in c.tags if k.startswith(("wide_", "tight_"))] == []


def test_a_wide_exit_is_named_as_such():
    c = _report(104.0).corners[0]
    keys = [k for k, _ in c.tags]
    assert "wide_exit" in keys or "wide_apex" in keys
    assert all(not k.startswith("tight_") for k in keys)


def test_tags_are_capped_and_carry_their_numbers():
    c = _report(115.0).corners[0]
    assert 0 < len(c.tags) <= 3
    for key, values in c.tags:
        text = tag_text(key, values, "en")
        assert key not in text, "the tag rendered as its own key"
        assert any(str(v) in text for v in values.values())


def test_the_tags_speak_italian_too():
    assert tag_text("wide_exit", {"m": 1.4}, "it") == "1.4 m largo in uscita"


def test_a_lap_without_coordinates_reports_nothing_rather_than_zeroes():
    flat = Lap("F", "T", SessionType.PRACTICE, 100000, True, samples=[
        LapSample(int(i / 200 * 100000), i / 200, 120.0, 1.0, 0.0, 0.1, "3",
                  5000, 0.0, 0.0) for i in range(200)])
    r = build_line_report(flat, flat, [_corner()])
    assert r.corners == []
    assert r.path_m == 0.0


def test_the_lap_summary_adds_up():
    r = _report(103.0)
    assert r.path_m > r.ref_path_m
    assert r.extra_m == pytest.approx(2 * math.pi * 3.0, abs=1.0)
    assert r.max_off_m == pytest.approx(3.0, abs=0.4)
    assert r.max_off_where in ("Turn 1", "")


def test_the_curated_corner_name_is_used():
    assert _report(103.0).corners[0].name == "Turn 1"


# --- the zoomed crop --------------------------------------------------------

def test_corner_path_covers_the_corner_plus_a_margin():
    pts = line_points(_circle_lap())
    crop = corner_path(pts, 0.20, 0.30, margin=0.15)
    assert crop["pos"][0] < 0.20 and crop["pos"][-1] > 0.30
    assert crop["pos"][0] == pytest.approx(0.20 - 0.015, abs=0.003)
    assert len(crop["x"]) == len(crop["z"]) == len(crop["speed"])


def test_corner_path_is_capped_so_the_payload_stays_small():
    pts = line_points(_circle_lap(n=4000))
    assert len(corner_path(pts, 0.0, 1.0, max_points=160)["x"]) == 160


# --- it survives a real detected lap ---------------------------------------

def test_it_runs_on_corners_detected_from_the_lap_itself():
    """The circle has no steering channel worth detecting corners from, so this
    only asserts the two modules compose without argument-shape surprises."""
    lap = _circle_lap()
    corners = detect_corners(lap.samples)
    report = build_line_report(lap, lap, corners)
    assert len(report.corners) == len(corners)


# --- when the apex shift means nothing --------------------------------------
# Both cases were found by measuring the archive, not by reading the code: a
# 60 m "apex shift" between two Spa laps whose minimum speed matched to the km/h,
# and a 174 m one on a lap that spun at Ascari. Same number, two different ways
# of being wrong.

def _dip_lap(where: float, floor: float = 60.0, flat: float = 0.0,
             radius: float = R, n: int = N) -> Lap:
    """A circle lap whose speed bottoms out at ``where`` (0..1).

    ``flat`` widens that bottom into a plateau of the given width in position,
    which is what a long corner really looks like: the minimum is a stretch, not
    a point, and which sample inside it is lowest is down to noise.
    """
    s = []
    for i in range(n):
        pos = i / n
        a = 2 * math.pi * pos * -1.0
        d = abs(pos - where)
        v = floor if d <= flat / 2 else min(140.0, floor + (d - flat / 2) * 900.0)
        s.append(LapSample(int(pos * 100000), pos, v, 0.5, 0.0, 0.2, "3", 5000,
                           0.0, 0.0, car_x=radius * math.sin(a),
                           car_z=radius * math.cos(a)))
    return Lap("Fixture", "Circle", SessionType.PRACTICE, 100000, True, samples=s)


def _one(review, base, entry=0.10, exit=0.30):
    return build_line_report(review, base,
                             [_corner(entry=entry, apex=0.20, exit=exit)]).corners[0]


def test_a_flat_bottomed_corner_reports_no_apex_shift():
    """The two minima are 0.04 of a lap apart — 25 m — but both sit inside a
    plateau they share, so the two laps apex in the same place."""
    c = _one(_dip_lap(0.16, flat=0.10), _dip_lap(0.20, flat=0.10))
    assert abs(c.apex_shift_m) > 10.0, "the raw measurement still moves"
    assert c.apex_flat_m > 0.0, "and the shared flat bottom is what says it can't"
    assert not any(k.startswith("apex_") for k, _ in c.tags)


def test_a_pointed_corner_still_reports_a_real_apex_shift():
    """The floor only lifts where the corner is flat: on a sharp one the apex
    moving is exactly what this view is for."""
    c = _one(_dip_lap(0.16), _dip_lap(0.20))
    assert c.apex_flat_m == 0.0
    assert abs(c.apex_shift_m) > 10.0
    assert any(k.startswith("apex_") for k, _ in c.tags)


def test_a_corner_the_car_stopped_in_is_not_a_line():
    """Down to a third of the reference's minimum: the geometry is still
    recorded, but 'your apex moved' is a true number and a false sentence."""
    c = _one(_dip_lap(0.20, floor=25.0), _dip_lap(0.20, floor=90.0))
    assert c.off_here
    assert not any(k.startswith("apex_") for k, _ in c.tags)
    assert c.tags[0][0] == "off_here", "it leads: everything else is qualified by it"
    assert "25" in tag_text(*c.tags[0], lang="en")


def test_a_normal_slower_lap_is_not_called_an_off():
    """A lap 15% down on minimum speed is a slow lap, not a spin — the badge has
    to stay off or it fires on every early-season lap."""
    assert not _one(_dip_lap(0.20, floor=76.0), _dip_lap(0.20, floor=90.0)).off_here


def test_the_recorder_can_flag_the_off_by_itself():
    """`lost_at` (v8+) is the recorder's own verdict on where the lap stopped
    counting; it doesn't need the speed to collapse to be believed."""
    review = _dip_lap(0.20, floor=88.0)
    review.lost_at = 0.22
    c = _one(review, _dip_lap(0.20, floor=90.0))
    assert c.off_here


# --- una variante non ha un "dentro" solo -----------------------------------

def test_a_chicane_reports_sides_not_an_inside():
    """Trovato il 2026-07-31 correggendo l'etichetta della Variante del
    Rettifilo.

    Il segno dentro/fuori e' **uno solo per tutta la curva**, ma l'interno di
    una variante sta a destra nella prima meta' e a sinistra nella seconda.
    Qualunque segno si scelga, meta' dei numeri in pagina esce invertita — e a
    lungo e' stato quello dell'apex, che rendeva sbagliato l'ingresso.

    Non si sceglie: si smette di dire «dentro». «3.3 m a destra della linea» e'
    vero in tutte e due le meta'.
    """
    review, base = _circle_lap(radius=R - 3), _circle_lap()
    chic = Corner(index=0, entry_pos=0.10, apex_pos=0.20, exit_pos=0.30, name="",
                  direction="right", kind="chicane", radius_m=40.0,
                  apex_speed_kmh=70.0)
    plain = Corner(index=0, entry_pos=0.10, apex_pos=0.20, exit_pos=0.30, name="",
                   direction="right", kind="medium", radius_m=90.0,
                   apex_speed_kmh=110.0)
    assert build_line_report(review, base, [chic]).corners[0].sided is False
    assert build_line_report(review, base, [plain]).corners[0].sided is True


def test_the_two_framings_differ_only_by_a_sign():
    """Il ripiego non butta via la misura: cambia la parola, non i metri."""
    review, base = _circle_lap(radius=R - 3), _circle_lap()
    mk = lambda kind: Corner(index=0, entry_pos=0.10, apex_pos=0.20, exit_pos=0.30,
                             name="", direction="left", kind=kind, radius_m=90.0,
                             apex_speed_kmh=110.0)
    a = build_line_report(review, base, [mk("medium")]).corners[0]
    b = build_line_report(review, base, [mk("chicane")]).corners[0]
    assert abs(a.apex_m) == pytest.approx(abs(b.apex_m), abs=1e-6)
    assert a.apex_m == pytest.approx(-b.apex_m, abs=1e-6)


def test_a_chicane_says_which_side_of_the_line_not_wide_or_tight():
    """Le pastiglie in cima alla curva usavano le stesse parole del pannello.
    Corrette insieme: «largo in uscita» presuppone un esterno, e in una
    variante non c'e'."""
    from accoach.track import Corner
    from accoach.trajectory import build_line_report

    review, base = _circle_lap(radius=R - 3), _circle_lap()
    mk = lambda kind: Corner(index=0, entry_pos=0.10, apex_pos=0.20, exit_pos=0.30,
                             name="", direction="right", kind=kind, radius_m=60.0,
                             apex_speed_kmh=90.0)
    keys = lambda rows: {k for k, _v in rows[0].tags}
    plain = keys(build_line_report(review, base, [mk("medium")]).corners)
    chic = keys(build_line_report(review, base, [mk("chicane")]).corners)
    assert any(k.startswith(("wide_", "tight_")) for k in plain), plain
    assert not any(k.startswith(("wide_", "tight_")) for k in chic), chic
    assert any(k.startswith(("left_", "right_")) for k in chic), chic


def test_every_side_phrase_exists_in_both_languages():
    """Una chiave senza testo esce in pagina come 'left_apex'."""
    from accoach.trajectory import tag_text
    for key in ("left_entry", "right_entry", "left_apex", "right_apex",
                "left_exit", "right_exit"):
        for lang in ("en", "it"):
            got = tag_text(key, {"m": 1.4}, lang)
            assert key not in got and "1.4" in got, f"{key}/{lang}: {got!r}"


def test_the_server_rounds_the_way_the_browser_does():
    """Lo stesso metro non deve avere due cifre a otto righe di distanza.

    `round()` di Python arrotonda alla cifra pari, `toFixed()` del browser no:
    su un giro reale il chip diceva «5,2 m largo in uscita» e la tabella sotto
    «Uscita 5,3 m fuori». Il numero era lo stesso (5.25), i due formattatori no.
    """
    from accoach.trajectory import _round_half_up

    assert _round_half_up(5.25, 1) == 5.3
    assert round(5.25, 1) == 5.2, "se questo cambia, il motivo del helper è caduto"
    assert _round_half_up(-5.25, 1) == -5.3
    assert _round_half_up(5.24, 1) == 5.2
    assert _round_half_up(0.0, 1) == 0.0
