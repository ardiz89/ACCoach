"""The names the driver typed.

Twelve bundled circuits have no name table and ten ACC circuits have no bundled
geometry at all, so for those the driver is the only source there is. What is
defended here is that their names behave like curated ones where it matters —
handed out once, matched by position and not by number — and unlike them where
it matters more: they win, and they can be taken back off.
"""
import json

import pytest

from accoach import cornernames
from accoach.cornernames import CustomNames, for_track, load, put
from accoach.trackdata import corner_name, name_corners


class _C:
    def __init__(self, index, apex_pos, direction=""):
        self.index = index
        self.apex_pos = apex_pos
        self.direction = direction


@pytest.fixture
def store(tmp_path):
    return tmp_path / "corner-names.json"


# --- the file -------------------------------------------------------------

def test_a_name_survives_being_written_and_read_back(store):
    put("zolder", 0.31, "Sacramento", store)
    assert for_track("zolder", store).of(0.31) == "Sacramento"


def test_the_file_is_something_a_person_can_read_and_edit(store):
    """It is the only copy of something a human typed. JSON with indentation
    and a trailing newline is not decoration — it is what makes the file
    recoverable by hand when this code is the thing that broke."""
    put("zolder", 0.31, "Sacramento", store)
    raw = store.read_text(encoding="utf-8")
    assert raw.endswith("\n") and "\n  " in raw
    assert json.loads(raw)["zolder"] == {
        "corners": [{"pos": 0.31, "name": "Sacramento"}]}


def test_it_is_keyed_on_the_circuit_and_not_on_the_sims_spelling(store):
    """The same circuit is `ks-nurburgring` in one game and `nurburgring` in the
    other. A name saved under one spelling and invisible under the other is the
    bug the alias map exists to kill."""
    put("ks-nurburgring", 0.42, "Il mio tornante", store)
    assert for_track("nurburgringgp", store).of(0.42) == "Il mio tornante"


def test_renaming_the_same_corner_replaces_rather_than_piles_up(store):
    put("zolder", 0.31, "Sacramento", store)
    put("zolder", 0.315, "Chicane", store)
    assert len(for_track("zolder", store)) == 1
    assert for_track("zolder", store).of(0.31) == "Chicane"


def test_an_empty_name_takes_the_name_back_off(store):
    put("zolder", 0.31, "Sacramento", store)
    put("zolder", 0.31, "", store)
    assert for_track("zolder", store).of(0.31) is None
    assert json.loads(store.read_text(encoding="utf-8")) == {}


def test_two_corners_far_apart_both_keep_their_names(store):
    put("zolder", 0.10, "Prima", store)
    put("zolder", 0.60, "Seconda", store)
    assert len(for_track("zolder", store)) == 2


def test_a_missing_file_is_no_names_and_not_an_error(store):
    assert len(for_track("zolder", store)) == 0
    assert load(store) == {}


def test_a_corrupt_file_costs_the_names_and_not_the_page(store):
    """The report's job is to show a lap, and it must still do it when this
    file is half-written — the same call already made for the learned map."""
    store.write_text("{not json", encoding="utf-8")
    assert load(store) == {}


@pytest.mark.parametrize("row", [
    {"pos": "nowhere", "name": "X"},        # unparseable position
    {"pos": 1.4, "name": "X"},              # outside the lap
    {"pos": 0.3, "name": "   "},            # a name that is only whitespace
    {"name": "X"},                          # no position at all
])
def test_a_row_that_makes_no_sense_is_dropped_and_the_rest_survive(store, row):
    store.write_text(json.dumps({"zolder": [row, {"pos": 0.6, "name": "Buona"}]}),
                     encoding="utf-8")
    names = for_track("zolder", store)
    assert [n for _p, n in names.names] == ["Buona"]


def test_the_file_is_written_whole_or_not_at_all(store, monkeypatch):
    """A plain overwrite leaves a truncated file when the write fails, and
    `load` reads that as "no names" — quietly, on the next page load."""
    put("zolder", 0.31, "Sacramento", store)

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(cornernames.os, "replace", _boom)
    with pytest.raises(OSError):
        put("zolder", 0.60, "Seconda", store)
    assert for_track("zolder", store).of(0.31) == "Sacramento"
    assert not list(store.parent.glob("*.tmp"))


# --- how far a name reaches ------------------------------------------------

def test_the_apex_wandering_between_laps_still_finds_its_name():
    """0.032 is the measured wander of one apex between laps by the same car
    (see cornermap.CLUSTER_TOL) — inside it, this is the corner that was named."""
    names = CustomNames(((0.400, "Mia"),))
    assert names.of(0.430) == "Mia"


def test_a_name_does_not_reach_the_corner_next_door():
    names = CustomNames(((0.400, "Mia"),))
    assert names.of(0.460) is None


def test_the_nearer_of_two_names_wins():
    names = CustomNames(((0.400, "Prima"), (0.425, "Seconda")))
    assert names.of(0.421) == "Seconda"


# --- precedence, which is the point ----------------------------------------

def test_the_driver_beats_the_curated_table():
    """Being told a name is wrong is information, not vandalism. It is stored
    in a file they can read and removing it is the same gesture as adding it."""
    names = CustomNames(((0.169, "La mia prima variante"),))
    corners = [_C(0, 0.169)]
    assert name_corners("monza", corners, "en", None, names) == \
        ["La mia prima variante"]
    assert name_corners("monza", corners, "en") == ["Variante del Rettifilo"]


def test_the_driver_beats_the_learned_number():
    from accoach.cornermap import learn
    learned = learn([[(0.10, "right"), (0.40, "right"), (0.75, "right")]] * 6)
    names = CustomNames(((0.40, "Sacramento"),))
    corners = [_C(0, 0.10), _C(1, 0.40)]
    assert name_corners("no-table", corners, "en", learned, names) == \
        ["Corner 1", "Sacramento"]


def test_a_typed_name_is_handed_out_once_like_a_curated_one():
    """If the detector splits a complex into three, every part is nearest to
    the same typed name — and the report grows three identical rows."""
    names = CustomNames(((0.686, "Ascari mia"),))
    corners = [_C(0, 0.672), _C(1, 0.686), _C(2, 0.700)]
    out = name_corners("monza", corners, "en", None, names)
    assert out.count("Ascari mia") == 1
    assert len(set(out)) == 3


def test_a_typed_name_ignores_the_direction_check():
    """The curated tables gate on direction because a source can put a name on
    the wrong corner. Nobody typed this name from a source — they typed it
    while looking at the corner on screen."""
    names = CustomNames(((0.567, "Pouhon mia"),))
    wrong = [_C(0, 0.567, "right")]          # Pouhon is a left; curated refuses
    assert name_corners("spa", wrong, "en") == ["Corner 1"]
    assert name_corners("spa", wrong, "en", None, names) == ["Pouhon mia"]


def test_without_any_typed_names_nothing_changes():
    corners = [_C(0, 0.169), _C(1, 0.247)]
    assert name_corners("monza", corners, "en", None, CustomNames()) == \
        name_corners("monza", corners, "en")


def test_the_single_corner_lookup_honours_it_too():
    """`corner_name` is what the live coach and the overlay call. The web app
    naming a corner while the voice says "Corner 7" is the failure that is
    already written into this module's history."""
    names = CustomNames(((0.169, "La mia"),))
    assert corner_name("monza", 0, 0.169, "en", "", names) == "La mia"
    assert corner_name("monza", 0, 0.169, "en") == "Variante del Rettifilo"


# --- braking references: the other half of roadmap item 2 ------------------
#
# The positions were measured long ago; the *words* could not be sourced. Two
# independent guides contradict each other on almost every corner at Imola —
# boards against flag-lights — and no measurement arbitrates between a 50 m
# board and a 100 m one. The driver is looking at the thing.

from accoach.cornernames import CustomMarks, marks_for, put_mark
from accoach.trackdata import landmark_at


def test_a_braking_reference_survives_the_round_trip(store):
    put_mark("zolder", 0.31, "alla fine del verde", store)
    assert marks_for("zolder", store).of(0.31) == "alla fine del verde"


def test_names_and_references_live_in_one_file_without_treading_on_each_other(store):
    put("zolder", 0.31, "Sacramento", store)
    put_mark("zolder", 0.31, "al cartello dei 100", store)
    assert for_track("zolder", store).of(0.31) == "Sacramento"
    assert marks_for("zolder", store).of(0.31) == "al cartello dei 100"


def test_a_file_written_before_references_existed_still_reads(store):
    """The file shipped earlier the same day as a bare list per circuit. Nobody
    should have to convert one — including the one on this machine."""
    store.write_text(json.dumps({"monza": [{"pos": 0.169, "name": "Mia"}]}),
                     encoding="utf-8")
    assert for_track("monza", store).of(0.169) == "Mia"
    assert len(marks_for("monza", store)) == 0
    # …and writing a reference onto it keeps the name.
    put_mark("monza", 0.12, "al cartello dei 150", store)
    assert for_track("monza", store).of(0.169) == "Mia"


def test_an_empty_reference_takes_it_back_off(store):
    put_mark("zolder", 0.31, "alla fine del verde", store)
    put_mark("zolder", 0.31, "", store)
    assert marks_for("zolder", store).of(0.31) is None


def test_a_reference_reaches_as_far_as_a_braking_zone_not_an_apex():
    """MARK_TOL is `trackdata._LANDMARK_TOL`, not the corner-name tolerance: the
    question here is "is the car braking here", and 0.02 is about 116 m at
    Monza — the length of a braking zone."""
    marks = CustomMarks(((0.400, "al cartello"),))
    assert marks.of(0.415) == "al cartello"
    assert marks.of(0.430) is None


def test_the_driver_beats_the_shipped_landmark():
    """Monza's landmarks came from published GT3 guides. The driver's own words
    outrank them for the same reason their corner names do."""
    assert landmark_at("monza", 0.122, "it") == "al cartello dei 150 m"
    mine = CustomMarks(((0.122, "dove finisce la riga blu"),))
    assert landmark_at("monza", 0.122, "it", mine) == "dove finisce la riga blu"


def test_a_phrase_is_not_translated_because_it_is_not_a_string_with_a_twin():
    """"alla fine del verde" has no English equivalent to look up — it is what
    the driver sees out of the window. Same words in both languages."""
    mine = CustomMarks(((0.122, "dove finisce la riga blu"),))
    assert landmark_at("monza", 0.122, "en", mine) == "dove finisce la riga blu"


def test_a_circuit_with_no_shipped_landmarks_can_still_get_one():
    """The point of the feature: Imola ships none, on purpose, because the
    sources contradict each other."""
    assert landmark_at("imola", 0.143, "it") is None
    mine = CustomMarks(((0.143, "al secondo cartello"),))
    assert landmark_at("imola", 0.143, "it", mine) == "al secondo cartello"
