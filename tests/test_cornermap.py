"""The corner map learned from your own laps.

What is defended here is a number holding still. The detector reads each lap on
its own merits, so the count moves between laps — sixteen Monza laps by one car
give five to nine corners — and the corner's *number* moved with it: 0.371 was
"Corner 4" on one lap and "Corner 5" on the next, with everything after it
sliding too. The map is the reference to number against.

The second thing defended is the refusal. A map built from two laps would call
every apex real, so under four laps nothing is learned at all, and an apex the
map does not recognise keeps falling back rather than being given a number it
hasn't earned.
"""
import pytest

from accoach import cornermap
from accoach.cornermap import CornerMap, learn
from accoach.trackdata import name_corners


class _C:
    """A detected corner, as much of one as `name_corners` touches."""

    def __init__(self, index, apex_pos, direction=""):
        self.index = index
        self.apex_pos = apex_pos
        self.direction = direction


def _laps(n, positions, direction="right"):
    return [[(p, direction) for p in positions] for _ in range(n)]


# --- what a map is made of ------------------------------------------------

def test_corners_every_lap_agrees_on_become_the_map():
    m = learn(_laps(6, [0.10, 0.40, 0.75]))
    assert [c.pos for c in m.corners] == [0.10, 0.40, 0.75]
    assert all(c.seen == 6 for c in m.corners)
    assert m.laps == 6


def test_an_apex_seen_on_one_odd_lap_is_not_a_corner():
    """Monza's real corners turn up in 13-16 laps out of 16 and the spurious
    ones in 2 or 3. The gap is wide enough that no judgement is being made."""
    laps = _laps(9, [0.10, 0.40, 0.75])
    laps[0].append((0.55, "left"))
    laps[1].append((0.55, "left"))
    m = learn(laps)
    assert [c.pos for c in m.corners] == [0.10, 0.40, 0.75]


def test_a_corner_most_laps_find_survives_the_ones_that_missed_it():
    laps = _laps(8, [0.10, 0.40, 0.75])
    for lap in laps[:2]:
        lap.remove((0.40, "right"))
    m = learn(laps)
    assert [c.pos for c in m.corners] == [0.10, 0.40, 0.75]
    assert m.corners[1].seen == 6


def test_the_position_is_the_median_of_where_it_was_found():
    """Not the mean: one lap that ran wide and moved its slowest point 150 m
    must not drag the anchor the other laps agree on."""
    laps = [[(0.400, "right")], [(0.402, "right")], [(0.398, "right")],
            [(0.401, "right")], [(0.430, "right")]]
    m = learn(laps)
    assert m.corners[0].pos == pytest.approx(0.401, abs=0.001)


def test_the_direction_is_the_one_most_laps_measured():
    laps = [[(0.4, "right")]] * 5 + [[(0.4, "left")]]
    assert learn(laps).corners[0].direction == "right"


def test_laps_with_no_coordinates_leave_the_direction_empty():
    assert learn(_laps(5, [0.4], direction="")).corners[0].direction == ""


def test_two_apexes_of_one_split_complex_do_not_outvote_a_real_corner():
    """The detector splitting Ascari into three on one lap must not make that
    lap count three times towards "this is a corner"."""
    laps = _laps(8, [0.10])
    laps[0] += [(0.500, "right"), (0.505, "right"), (0.510, "right")]
    laps[1] += [(0.500, "right"), (0.505, "right"), (0.510, "right")]
    m = learn(laps)
    assert [c.pos for c in m.corners] == [0.10]


# --- when it refuses ------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_a_handful_of_laps_teaches_nothing(n):
    """Two laps cannot tell a corner from a coincidence — every apex would be
    in "half the laps" by having appeared once."""
    m = learn(_laps(n, [0.10, 0.40]))
    assert len(m) == 0 and m.laps == n


def test_an_unrecognised_apex_gets_no_number_from_the_map():
    m = learn(_laps(6, [0.10, 0.40, 0.75]))
    assert m.number_of(0.40) == 2
    assert m.number_of(0.55) is None


def test_an_empty_map_numbers_nothing():
    assert CornerMap([], 0).number_of(0.4) is None


# --- the number holding still, which is the whole point -------------------

def test_a_missed_corner_no_longer_slides_every_number_after_it():
    """Measured on the archive: two Imola laps by the same car detected nine
    corners where the others detected ten, and from the missing one on, every
    corner answered to the number of the corner before it."""
    m = learn(_laps(8, [0.10, 0.30, 0.50, 0.70, 0.90]))
    short = [_C(0, 0.10), _C(1, 0.50), _C(2, 0.70), _C(3, 0.90)]
    assert name_corners("no-table", short, "en") == \
        ["Corner 1", "Corner 2", "Corner 3", "Corner 4"]        # the old slide
    assert name_corners("no-table", short, "en", m) == \
        ["Corner 1", "Corner 3", "Corner 4", "Corner 5"]        # what it is


def test_an_extra_apex_does_not_push_the_rest_along():
    m = learn(_laps(8, [0.10, 0.30, 0.50]))
    long = [_C(0, 0.10), _C(1, 0.20), _C(2, 0.30), _C(3, 0.50)]
    assert name_corners("no-table", long, "en", m)[2:] == ["Corner 2", "Corner 3"]


def test_a_curated_name_still_wins_over_the_learned_number():
    """The map numbers what the tables leave numbered. It never renames."""
    m = learn(_laps(8, [0.058, 0.351, 0.567]))
    corners = [_C(0, 0.058, "right"), _C(1, 0.351, "right")]
    assert name_corners("spa", corners, "en", m) == ["La Source", "Les Combes"]


def test_without_a_map_nothing_changes():
    corners = [_C(0, 0.10), _C(1, 0.40)]
    assert name_corners("no-table", corners, "en") == \
        name_corners("no-table", corners, "en", CornerMap([], 0))


# --- what the catalog stores ----------------------------------------------

def test_a_map_survives_the_round_trip_through_text():
    m = learn(_laps(6, [0.10, 0.40, 0.75]))
    back = cornermap.deserialize(cornermap.serialize(m), m.laps)
    assert [c.pos for c in back.corners] == [c.pos for c in m.corners]
    assert [c.direction for c in back.corners] == [c.direction for c in m.corners]
    assert back.laps == 6


def test_a_corrupt_row_costs_the_map_and_not_the_page():
    """The catalog is a rebuildable cache; a row that won't parse must degrade
    to "no map", never to an exception on a page that only wanted a lap."""
    assert len(cornermap.deserialize("nonsense;0.4:right", 3)) == 0
    assert len(cornermap.deserialize("", 0)) == 0
