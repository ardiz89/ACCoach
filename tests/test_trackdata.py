"""trackdata: friendly corner names assigned by apex position."""
import pytest

from accoach import trackdata
from accoach.track import Corner
from accoach.trackdata import corner_name, has_names, landmark_at, name_corners


def _corner(index, apex):
    return Corner(index=index, entry_pos=apex - 0.02, apex_pos=apex, exit_pos=apex + 0.02)


def test_imola_names_by_apex():
    assert corner_name("imola", 0, 0.143) == "Tamburello"
    assert corner_name("imola", 2, 0.351) == "Tosa"
    assert corner_name("imola", 6, 0.844) == "Rivazza"


def test_imola_track_slug_is_normalized():
    assert has_names("Imola")
    assert corner_name("IMOLA", 0, 0.143) == "Tamburello"


def test_unknown_track_falls_back_to_numbers():
    # lang is pinned so the numbered fallback is deterministic regardless of the
    # machine's config language ("Corner N" en / "Curva N" it).
    assert not has_names("nordschleife")
    assert corner_name("nordschleife", 0, 0.3, "en") == "Corner 1"
    assert corner_name("nordschleife", 4, 0.8, "en") == "Corner 5"


def test_apex_outside_tolerance_falls_back():
    # 0.42 sits in the gap between Tosa (0.351) and Piratella (0.484), >tol from
    # both -> numbered fallback rather than a wrong name.
    assert corner_name("imola", 3, 0.42, "en") == "Corner 4"


def test_name_corners_maps_a_list():
    corners = [_corner(0, 0.143), _corner(1, 0.291), _corner(2, 0.351)]
    assert name_corners("imola", corners) == ["Tamburello", "Villeneuve", "Tosa"]


# --- Monza -----------------------------------------------------------------
# Anchored to a real lap (Ferrari 488 GT3 Evo, 2:03.7): detected apexes 0.169 /
# 0.247 / 0.378 / 0.447 / 0.500 / 0.686 / 0.888. The minimum speeds pin the
# identification — 49 km/h at the first chicane, 205 through Curva Grande.

def test_monza_first_chicane_is_named():
    """The corner the driver loses the lap at, twice measured at 0.161/0.164."""
    assert corner_name("monza", 0, 0.169) == "Variante del Rettifilo"
    assert corner_name("monza", 0, 0.161) == "Variante del Rettifilo"


def test_monza_ascari_is_named():
    """Where a real lap went off on 2026-07-22 (pos 0.715, 33 km/h)."""
    assert corner_name("monza", 5, 0.715) == "Variante Ascari"


def test_monza_names_the_whole_lap():
    corners = [_corner(i, p) for i, p in enumerate(
        (0.169, 0.227, 0.379, 0.443, 0.508, 0.716, 0.901))]
    assert name_corners("monza", corners) == [
        "Variante del Rettifilo", "Curva Grande", "Variante della Roggia",
        "Lesmo 1", "Lesmo 2", "Variante Ascari", "Parabolica",
    ]


def test_the_two_lesmos_do_not_collapse_into_one():
    """Con gli apici RILEVATI, non con quelli curati.

    La versione precedente passava esattamente 0.447 e 0.500, cioè i valori che
    avevamo scritto noi nella tabella: era una tautologia e sarebbe rimasta verde
    con qualunque tolleranza. I due Lesmo distano 0.053 e la tolleranza è 0.05,
    quindi il caso vero è un apice rilevato un po' spostato.
    """
    corners = [_corner(3, 0.4505), _corner(4, 0.4955)]   # entrambi verso il mezzo
    names = name_corners("monza", corners)
    assert names == ["Lesmo 1", "Lesmo 2"], names


def test_a_split_complex_does_not_produce_three_identical_names():
    """Se il rilevatore spezza l'Ascari in tre, ogni parte è vicina allo stesso
    apice curato: il report finiva con tre righe chiamate "Variante Ascari",
    indistinguibili nelle perdite, nelle velocità e nella voce del coach."""
    corners = [_corner(0, 0.672), _corner(1, 0.686), _corner(2, 0.700)]
    names = name_corners("monza", corners)
    assert names.count("Variante Ascari") == 1, names
    assert len(set(names)) == 3, names


# --- visual braking landmarks ----------------------------------------------
# The lookup is tested against an injected table so the mechanism is proven while
# the *shipped* tables stay empty until their landmarks are verified on track.

@pytest.fixture
def _fake_landmarks(monkeypatch):
    monkeypatch.setitem(
        trackdata._LANDMARKS,
        "monza",
        [("al cordolo bianco-rosso", "at the white-and-red kerb", 0.165),
         ("al cartello dei 100 m", "at the 100 m board", 0.370)],
    )


def test_landmark_by_nearest_position(_fake_landmarks):
    # A braking onset a few thousandths off the curated spot still resolves.
    assert landmark_at("monza", 0.167, "it") == "al cordolo bianco-rosso"
    assert landmark_at("monza", 0.368, "it") == "al cartello dei 100 m"


def test_landmark_language(_fake_landmarks):
    assert landmark_at("monza", 0.165, "en") == "at the white-and-red kerb"
    assert landmark_at("Monza", 0.165, "en") == "at the white-and-red kerb"  # slug


def test_landmark_outside_tolerance_is_none(_fake_landmarks):
    # 0.20 is >0.02 from either landmark -> no phrase rather than a wrong one.
    assert landmark_at("monza", 0.20, "it") is None


def test_landmark_unknown_track_is_none(_fake_landmarks):
    assert landmark_at("nordschleife", 0.165, "it") is None


def test_imola_landmarks_still_unsourced():
    # Guard the honesty rule per track: Imola has no sourced landmarks yet, so it
    # must stay empty and fall back to metres. Filling it is a deliberate change
    # that updates this test — it must never grow landmarks silently.
    assert trackdata._LANDMARKS["imola"] == [], (
        "un landmark Imola è stato spedito senza fonte: aggiorna questo test solo "
        "dopo aver validato i punti su una fonte fidata")


def test_shipped_landmarks_are_well_formed():
    # Every shipped landmark: both languages non-empty, position a real fraction.
    for track, table in trackdata._LANDMARKS.items():
        for it, en, pos in table:
            assert it and en, f"{track}: descrizione vuota"
            assert 0.0 <= pos <= 1.0, f"{track}: pos {pos} fuori da 0..1"


def test_monza_landmarks_resolve_at_measured_positions():
    # The Monza positions were measured from the anchor reference lap's braking
    # onsets; landmark_at must return each at its own position, in both languages.
    assert landmark_at("monza", 0.122, "it") == "al cartello dei 150 m"
    assert landmark_at("monza", 0.122, "en") == "at the 150 m board"
    assert landmark_at("monza", 0.860, "it") == "alla fine del verde sulla sinistra"
    # Curva Grande (0.247) is taken near flat — no braking landmark there.
    assert landmark_at("monza", 0.247, "it") is None


# --- Spa & Suzuka: added 2026-07-30 from real laps in the archive -----------
# Both tables are anchored to a measured lap (see the comments in trackdata).
# The archive itself can't be a test fixture — CI has no laps — so what is
# pinned here is everything that can go wrong *without* one.

_SPA = ["La Source", "Raidillon", "Les Combes", "Rivage", "Pouhon", "Fagnes",
        "Stavelot", "Bus Stop"]
_SUZUKA = ["Esses", "Dunlop", "Degner 1", "Degner 2", "Hairpin", "Spoon",
           "130R", "Casio Triangle"]


@pytest.mark.parametrize("track,expected", [("spa", _SPA), ("suzuka", _SUZUKA)])
def test_each_name_lands_on_its_own_corner(track, expected):
    """The real risk, and the reason the table stores *measured* apexes.

    Suzuka's two Degners are 0.031 of a lap apart — inside _NAME_TOL — so a
    table anchored on approximate positions could hand "Degner 1" to Degner 2
    and leave the other numbered. Anchored on the measured apex, each name wins
    its own corner by a distance of zero.
    """
    table = trackdata._CORNERS[track]
    corners = [_corner(i, pos) for i, (_n, pos) in enumerate(table)]
    assert name_corners(track, corners) == expected


@pytest.mark.parametrize("track", ["spa", "suzuka"])
def test_the_table_is_ordered_and_has_no_duplicates(track):
    table = trackdata._CORNERS[track]
    positions = [p for _n, p in table]
    assert positions == sorted(positions)
    assert all(0.0 < p < 1.0 for p in positions)
    assert len({n for n, _p in table}) == len(table)


def test_suzukas_unnamed_corners_stay_numbered():
    """Turns 1-2, 10 and 12 have no name on any published map of the circuit.
    Filling those rows would make the report authoritative about an invention.

    Two of the three are inside the position tolerance of the Hairpin and are
    kept out of it by which way they turn: they are rights, the Hairpin is a
    left. That is the whole job of the direction check.
    """
    for apex in (0.147, 0.482, 0.551):
        assert corner_name("suzuka", 0, apex, "en", "right") == "Corner 1"


def test_eau_rouge_is_not_called_la_source():
    """Eau Rouge and Blanchimont are deliberately absent from the table: in the
    lap it was measured from, neither is a corner at all. A corner detected at
    the bottom of the hill sits 0.042 from La Source — inside the tolerance —
    and is a left where La Source is a right. Found on 2026-07-30, three hundred
    metres of confident wrong answer."""
    assert corner_name("spa", 0, 0.100, "en", "left") == "Corner 1"
    assert corner_name("spa", 0, 0.860, "en", "left") == "Corner 1"   # Blanchimont


def test_a_lap_with_no_coordinates_still_gets_its_names():
    """Unknown must not mean "no": laps recorded before the map update can't
    classify a corner's direction, and they were being named fine before this
    check existed."""
    assert corner_name("spa", 0, 0.058, "en", "") == "La Source"
    assert corner_name("suzuka", 0, 0.505, "en") == "Hairpin"
    corners = [_corner(i, pos) for i, (_n, pos) in enumerate(trackdata._CORNERS["spa"])]
    assert name_corners("spa", corners) == _SPA


def test_a_corner_turning_the_wrong_way_never_takes_the_name():
    """The check has to bite in the list form too, not only one corner at a
    time — the report and the live coach use different entry points."""
    wrong = [_corner(0, 0.567)]            # Pouhon's position, but a right
    wrong[0].direction = "right"
    assert name_corners("spa", wrong, "en") == ["Corner 1"]


@pytest.mark.parametrize("track,expected", [("spa", _SPA), ("suzuka", _SUZUKA)])
def test_curated_names_are_proper_nouns_in_both_languages(track, expected):
    table = trackdata._CORNERS[track]
    for lang in ("en", "it"):
        assert [corner_name(track, i, p, lang)
                for i, (_n, p) in enumerate(table)] == expected


@pytest.mark.parametrize("track", ["spa", "suzuka"])
def test_the_new_tracks_report_that_they_have_names(track):
    assert has_names(track)


# --- one circuit, however the sim spells it (2026-08-03) --------------------

def test_the_same_circuit_is_found_under_either_game_s_name():
    """Kunos prefixes its Assetto Corsa tracks with ``ks-``; ACC drops the
    prefix and renames outright. A table keyed on one spelling is invisible to
    the other game — the exact bug the track drawings had to stop having, and it
    would have shipped here the day a second circuit arrived."""
    assert trackdata.has_names("ks-silverstone")
    assert trackdata.has_names("Silverstone")
    assert corner_name("ks-silverstone", 0, 0.533, "en", "right") == "Copse"


def test_a_historic_layout_does_not_inherit_the_modern_one_s_corners():
    """Spa 1998 shares a name with Spa and not a circuit: it has no Bus Stop
    where the modern one does. Giving it the modern positions would print Les
    Combes in the middle of a straight."""
    assert not trackdata.has_names("spa-1998")
    assert corner_name("spa-1998", 3, 0.351, "en") == "Corner 4"


def test_every_alias_points_at_a_circuit_we_could_actually_name():
    """An alias to a key with no table is a silent no-op that reads like
    coverage. It is allowed to be empty *today* only if the key exists."""
    for alias, key in trackdata._ALIASES.items():
        assert key == trackdata._slug(key), f"{alias} -> {key} is not a slug"
        assert key not in trackdata._ALIASES, f"{alias} -> {key} chains"


# --- officially numbered corners (2026-08-03) ------------------------------

def test_a_curated_turn_number_is_rendered_in_the_reader_s_language():
    """Most modern circuits name nothing and number everything, and those
    numbers are painted on the track map — they are facts, not our count of
    what a detector happened to find. So a table may hold an integer, and
    unlike a proper noun it gets translated."""
    assert trackdata.render(7, "it") == "Curva 7"
    assert trackdata.render(7, "en") == "Corner 7"
    assert trackdata.render("Parabolica", "it") == "Parabolica"
    assert trackdata.render("Parabolica", "en") == "Parabolica"


def test_a_numbered_corner_goes_through_the_table_like_a_named_one(monkeypatch):
    monkeypatch.setitem(trackdata._CORNERS, "tt", [(7, 0.400), ("Curvone", 0.700)])
    corners = [_corner(0, 0.402), _corner(1, 0.698)]
    assert name_corners("tt", corners, "it") == ["Curva 7", "Curvone"]
    assert name_corners("tt", corners, "en") == ["Corner 7", "Curvone"]


def test_the_fallback_number_is_the_detector_s_count_not_the_circuit_s():
    """On a track with no table the only honest thing to say is "the seventh
    corner I found" — claiming it is the circuit's Turn 7 would be inventing
    an official fact."""
    assert corner_name("no-such-track", 6, 0.5, "en") == "Corner 7"


# --- Silverstone: the first table read off geometry, not off a lap ---------

_SILVERSTONE = ["Abbey", "Farm Curve", "Village", "The Loop", "Aintree",
                "Brooklands", "Luffield", "Woodcote", "Copse", "Maggotts",
                "Becketts", "Chapel", "Stowe", "Vale", "Club"]


def test_silverstone_names_land_on_their_own_corners():
    table = trackdata._CORNERS["silverstone"]
    corners = [_corner(i, pos) for i, (_n, pos) in enumerate(table)]
    assert name_corners("silverstone", corners) == _SILVERSTONE


def test_silverstone_every_name_carries_the_direction_that_proved_it():
    """The table is trusted because the eighteen-symbol sequence of directions
    the geometry produced matched the one the circuit's own corner list implies.
    Dropping a direction would keep the names and throw away the evidence."""
    want = trackdata._DIRECTIONS["silverstone"]
    assert {n for n, _p in trackdata._CORNERS["silverstone"]} == set(want)
    assert set(want.values()) == {"left", "right"}


def test_a_silverstone_name_will_not_take_a_corner_turning_the_other_way():
    assert corner_name("silverstone", 8, 0.533, "en", "right") == "Copse"
    assert corner_name("silverstone", 8, 0.533, "en", "left") == "Corner 9"


# --- circuits sourced from a published corner list (2026-08-03) ------------
# The method: a source supplies the corners in order and which way each turns,
# the bundled centreline supplies where they are, and the two have to agree.
# Pinned here is what can be checked without a lap: every name lands on its own
# corner, and every direction that proved the table is still recorded next to it.

_SOURCED = {
    "silverstone": ["Abbey", "Farm Curve", "Village", "The Loop", "Aintree",
                    "Brooklands", "Luffield", "Woodcote", "Copse", "Maggotts",
                    "Becketts", "Chapel", "Stowe", "Vale", "Club"],
    "mountpanorama": ["Hell Corner", "Griffins Bend", "The Cutting",
                      "Quarry Corner", "Reid Park", "Sulman Park",
                      "McPhillamy Park", "Skyline", "The Dipper",
                      "Forrest's Elbow", "The Chase", "Murray's Corner"],
    "saopaulo": ["S do Senna", "Curva do Sol", "Descida do Lago", "Ferradura",
                 "Laranjinha", "Pinheirinho", "Bico de Pato", "Mergulho",
                 "Junção", "Subida dos Boxes", "Arquibancadas"],
    "zandvoort": ["Tarzanbocht", "Gerlachbocht", "Hugenholtzbocht", "Hunserug",
                  "Slotemakerbocht", "Scheivlak", "Mastersbocht", "Hans Ernst",
                  "Arie Luyendijkbocht"],
}


@pytest.mark.parametrize("track", sorted(_SOURCED))
def test_a_sourced_table_names_each_corner_once_and_in_order(track):
    table = trackdata._CORNERS[track]
    corners = [_corner(i, pos) for i, (_n, pos) in enumerate(table)]
    assert name_corners(track, corners) == _SOURCED[track]


@pytest.mark.parametrize("track", sorted(_SOURCED))
def test_a_sourced_table_is_ordered_with_no_duplicates(track):
    positions = [p for _n, p in trackdata._CORNERS[track]]
    assert positions == sorted(positions)
    assert all(0.0 < p < 1.0 for p in positions)


@pytest.mark.parametrize("track", sorted(_SOURCED))
def test_a_sourced_direction_is_never_recorded_for_a_name_we_do_not_have(track):
    """A direction for a name that left the table is evidence for a claim
    nobody makes any more — and the next person to read it will believe the
    name is still there."""
    names = {n for n, _p in trackdata._CORNERS[track]}
    assert set(trackdata._DIRECTIONS.get(track, {})) <= names


def test_a_complex_is_not_given_a_single_direction():
    """The Chase is right-left-right and S do Senna is left-right. Asking a
    complex which way it turns has no answer, so it isn't asked — the same call
    already made for Spa's Bus Stop and Suzuka's Casio Triangle."""
    assert "The Chase" not in trackdata._DIRECTIONS["mountpanorama"]
    assert "S do Senna" not in trackdata._DIRECTIONS["saopaulo"]
