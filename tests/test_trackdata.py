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
    "brandshatch": ["Paddock Hill Bend", "Druids", "Graham Hill Bend", "Surtees",
                    "Hawthorn Bend", "Westfield Bend", "Sheene Curve",
                    "Stirling's", "Clearways", "Clark Curve"],
    "zandvoort": ["Tarzanbocht", "Gerlachbocht", "Hugenholtzbocht", "Hunserug",
                  "Slotemakerbocht", "Scheivlak", "Mastersbocht", "Hans Ernst",
                  "Arie Luyendijkbocht"],
    "hockenheim": ["Nordkurve", "Spitzkehre", "Sachskurve", "Elf-Kurve",
                   "Südkurve"],
    "catalunya": ["Elf", "Renault", "Repsol", "Seat", "Campsa", "La Caixa",
                  "Banc Sabadell", "Europcar"],
    "mexicocity": ["Peraltada"],
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


# --- a circuit curated by number (2026-08-03) ------------------------------

def test_the_nurburgring_is_numbered_all_the_way_round():
    """Half a numbering is worse than none: an official "Corner 3" printed next
    to a detector-counted "Corner 4" gives the driver two numbering schemes in
    one list and no way to tell them apart."""
    labels = [n for n, _p in trackdata._CORNERS["nurburgring"]]
    assert labels == list(range(1, len(labels) + 1))
    assert all(isinstance(n, int) for n in labels)


def test_a_numbered_circuit_reads_in_the_page_s_language():
    table = trackdata._CORNERS["nurburgring"]
    corners = [_corner(i, pos) for i, (_n, pos) in enumerate(table)]
    assert name_corners("nurburgring", corners, "en")[:3] == \
        ["Corner 1", "Corner 2", "Corner 3"]
    assert name_corners("nurburgring", corners, "it")[:3] == \
        ["Curva 1", "Curva 2", "Curva 3"]


def test_the_nurburgring_is_reachable_from_assetto_corsa_s_spelling():
    """Kunos ships it as ``ks-nurburgring``; ACC calls it ``nurburgring``."""
    assert name_corners("ks-nurburgring",
                        [_corner(0, 0.079)], "en") == ["Corner 1"]


# --- the geometry the tables are read off (2026-08-03) ---------------------

def test_every_bundled_circuit_turns_the_way_it_really_turns():
    """The cheapest check that the traces and the mirror applied to them are
    both right — and it is decided by a number computed from the raw trace,
    which knows nothing about the circuit's name.

    Suzuka is why it is worth keeping: it is a **figure of eight**, the only one
    in the set, so its lap crosses itself and its net turning cancels to zero
    instead of reaching ±360. Nothing in the code knows that; it falls out.
    """
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    from corner_atlas import rotation, TRACKS

    anticlockwise = {"Austin", "SaoPaulo", "MountPanorama", "YasMarina", "IMS",
                     "MoscowRaceway", "Norisring"}
    for csv in sorted(TRACKS.glob("*.csv")):
        deg = rotation(csv.name)
        if csv.stem == "Suzuka":
            assert abs(deg) < 90.0, "Suzuka's lap crosses itself"
            continue
        assert abs(abs(deg) - 360.0) < 1.0, f"{csv.stem} is not a closed lap"
        way = "anticlockwise" if deg > 0 else "clockwise"
        want = "anticlockwise" if csv.stem in anticlockwise else "clockwise"
        assert way == want, f"{csv.stem} reads {way}, it runs {want}"


def test_cota_is_numbered_all_twenty_turns():
    labels = [n for n, _p in trackdata._CORNERS["austin"]]
    assert labels == list(range(1, 21))


def test_cota_is_reachable_under_accs_spelling():
    """ACC ships it as ``cota``; the trace and every guide call it Austin."""
    assert trackdata.has_names("cota")
    assert corner_name("cota", 0, 0.121, "it", "left") == "Curva 1"


def test_cotas_back_straight_survives_in_the_table():
    """T11 to T12 is 1195 m with no corner in it, against a published back
    straight of 1016 m. It is the anchor that says the twenty positions sit on
    the real circuit and not on a plausible shift of it — so if an edit ever
    slides them, this is what notices."""
    pos = dict((n, p) for n, p in trackdata._CORNERS["austin"])
    gap_m = (pos[12] - pos[11]) * 5503.0
    assert 1100 < gap_m < 1300


# --- circuits curated by name on 2026-08-04 --------------------------------
#
# Three more, and each one is here because of a different failure it survived.

def test_the_spitzkehre_is_a_right_because_the_only_full_guide_was_invented():
    """A guide laid out all seventeen Hockenheim turns and got them wrong: it
    calls the Parabolika — a straight — "a very long, constant-radius left" and
    the Spitzkehre "an extremely tight hairpin left". A prose source says
    "170-degree right-hander" and the tightest apex of the lap turns right.

    This is the fourth time a generated turn-by-turn has invented a direction,
    so the outcome is pinned rather than trusted to the comment beside it."""
    assert trackdata._DIRECTIONS["hockenheim"]["Spitzkehre"] == "right"
    wrong = [_corner(0, 0.462)]
    wrong[0].direction = "left"
    assert name_corners("hockenheim", wrong, "en") == ["Corner 1"]


def test_hockenheims_hairpin_is_the_tightest_thing_on_the_lap():
    """The Spitzkehre was placed by *character*, not by turn number: it is the
    slowest corner of the circuit at the end of the Parabolika. The position
    below must therefore sit in the second half of the lap's longest gap."""
    pos = dict(trackdata._CORNERS["hockenheim"])
    assert 0.40 < pos["Spitzkehre"] < 0.50
    assert pos["Nordkurve"] < 0.10           # first corner off the pit straight
    assert pos["Südkurve"] > 0.90            # last one before the line


def test_barcelona_keeps_the_name_the_chicane_could_not_move():
    """Catalunya was held back on 03/08 because the bundled trace has 14 turns
    and the ACC guides describe 16. That was right about the *numbers* and
    wrong about the *names*: the chicane renumbered everything after Turn 13
    and renamed nothing, so Campsa is Campsa on both layouts.

    New Holland is the exception and is deliberately absent — it is the only
    name that sits after where the chicane was, so it is the only one whose
    position genuinely moves."""
    names = [n for n, _p in trackdata._CORNERS["catalunya"]]
    assert "Campsa" in names and "La Caixa" in names
    assert "New Holland" not in names
    assert max(p for _n, p in trackdata._CORNERS["catalunya"]) < 0.90


def test_barcelona_answers_to_both_games_spellings():
    assert trackdata.has_names("barcelona") and trackdata.has_names("kscatalunya")


def test_la_caixa_is_a_left_and_will_not_take_a_right():
    """La Caixa is the tightest left of the lap at the end of the longest
    straight after the pit straight — the pin the whole alignment hangs on."""
    right = [_corner(0, 0.754)]
    right[0].direction = "right"
    assert name_corners("catalunya", right, "en") == ["Corner 1"]
    left = [_corner(0, 0.754)]
    left[0].direction = "left"
    assert name_corners("catalunya", left, "en") == ["La Caixa"]


def test_mexico_city_gets_one_row_and_that_is_the_honest_number():
    """Everything else this circuit is known for is a *section* — the Foro Sol
    is a stadium, the Esses are Turns 7 to 11 — and a section has no apex to
    anchor a name to. One name beats five invented ones, and the rest of the
    lap keeps its numbers."""
    assert [n for n, _p in trackdata._CORNERS["mexicocity"]] == ["Peraltada"]
    assert trackdata.has_names("autodromohermanosrodriguez")
    corners = [_corner(0, 0.230), _corner(1, 0.936)]
    assert name_corners("mexicocity", corners, "it") == ["Curva 1", "Peraltada"]


# --- i due circuiti che la regola sbagliata teneva fermi (2026-08-04) -------

def test_sepang_is_numbered_all_fifteen():
    """Era fermo perché il rilevatore trova 18 apici e il circuito ha 15 curve.
    La regola («conteggi diversi, niente tabella») era sbagliata: la numerazione
    ufficiale fonde i complessi, e la guida di Sepang lo dice da sola chiamando
    le T7-T8 «un lungo destro a doppio apex»."""
    assert [n for n, _p in trackdata._CORNERS["sepang"]] == list(range(1, 16))


def test_sepang_directions_are_five_lefts_and_ten_rights():
    """Il vincolo che ha forzato la sequenza: la fonte dichiara «5 sinistre e 10
    destre» e ne nomina a parole esattamente cinque. Le altre dieci sono destre
    per aritmetica, non per fiducia — e sulla geometria l'allineamento dà 15/15."""
    d = trackdata._DIRECTIONS["sepang"]
    assert sum(v == "left" for v in d.values()) == 5
    assert sum(v == "right" for v in d.values()) == 10
    assert [n for n, v in sorted(d.items()) if v == "left"] == [2, 6, 9, 12, 15]


def test_sepangs_back_straight_survives_in_the_table():
    """Fra T14 e T15 non c'è niente per 950 m: è il rettilineo posteriore in cui
    la fonte dice che la T14 ti lancia. È l'ancoraggio che dice che le quindici
    posizioni stanno sul circuito vero e non su uno scorrimento plausibile."""
    pos = dict(trackdata._CORNERS["sepang"])
    assert 850 < (pos[15] - pos[14]) * 5535.0 < 1050


def test_the_red_bull_ring_is_numbered_all_ten():
    assert [n for n, _p in trackdata._CORNERS["redbullring"]] == list(range(1, 11))


def test_the_red_bull_ring_answers_to_both_spellings():
    assert trackdata.has_names("ks_red_bull_ring") and trackdata.has_names("Spielberg")


def test_turn_two_is_the_kink_the_drivers_laps_never_saw():
    """La conferma più forte non viene da una fonte: quattro giri veri in
    archivio trovano NOVE curve, e quella che manca è la T2 — che una guida
    liquida come «un kink a sinistra tutto gas, non è una curva vera». La
    geometria le dà r=172 m, cioè la misura di quella frase.

    Quindi la T2 c'è nella tabella (la numerazione è tutto o niente) ma sta fra
    la T1 e la T3, dove il rilevatore non la cerca."""
    pos = dict(trackdata._CORNERS["redbullring"])
    assert pos[1] < pos[2] < pos[3]
    assert trackdata._DIRECTIONS["redbullring"][2] == "left"


def test_the_red_bull_ring_is_anchored_to_the_drivers_own_laps():
    """Le otto curve che i giri vedono hanno la LORO posizione, non quella della
    traccia: le due sorgenti concordano sulla forma e non sull'origine, e fra
    loro ci sono 105 m costanti. Misurato beats derivato.

    T1 sta a 0.076 nei giri e a 0.104 nella traccia. Se un giorno qualcuno
    riscrive la tabella dalla traccia, questo test lo dice."""
    pos = dict(trackdata._CORNERS["redbullring"])
    assert pos[1] == pytest.approx(0.076, abs=0.005)


def test_shanghai_is_numbered_all_sixteen():
    assert [n for n, _p in trackdata._CORNERS["shanghai"]] == list(range(1, 17))


def test_shanghais_back_straight_is_where_the_hairpin_was_found():
    """L'ancoraggio che ha corretto il solutore, e il motivo per cui la T13 non
    sta dove l'aveva messa lui.

    Fra la T12 e il tornante ci sono quattro destre di fila e il criterio della
    prominenza tira su quelle strette: il solutore ha allungato, per la quarta
    volta. La fonte però dice che il lungo rettilineo sta **fra T13 e T14**, e
    nella geometria c'è un solo vuoto di quella taglia."""
    pos = dict(trackdata._CORNERS["shanghai"])
    assert 1150 < (pos[14] - pos[13]) * 5440.0 < 1450


def test_shanghais_hairpin_complex_stays_one_complex():
    """La T15 è «parte del complesso del tornante»: 109 m dopo la T14, non
    dall'altra parte del circuito."""
    pos = dict(trackdata._CORNERS["shanghai"])
    assert 0 < (pos[15] - pos[14]) * 5440.0 < 200


def test_shanghai_turn_five_has_no_direction_because_nobody_stated_one():
    """Quindici versi su sedici sono dichiarati a parole da una fonte. La T5 no,
    e resta fuori dal controllo invece di essere dedotta: un verso indovinato
    passerebbe il test e potrebbe spostare un nome."""
    assert 5 not in trackdata._DIRECTIONS["shanghai"]
    assert len(trackdata._DIRECTIONS["shanghai"]) == 15


def test_melbourne_is_numbered_all_sixteen():
    """La traccia è il tracciato 1996-2020, non quello di oggi: 5294 m contro i
    5303 pubblicati (0.17%), mentre l'Albert Park attuale fa 5278 m e ha 14
    curve. Quindi sedici, con la chicane T9-T10 ancora al suo posto."""
    assert [n for n, _p in trackdata._CORNERS["melbourne"]] == list(range(1, 17))


def test_melbourne_directions_are_six_lefts_and_ten_rights():
    """Il vincolo globale, e qui vale doppio perché è stato **previsto prima di
    essere letto**: la ricostruzione geometrica dava 6 sinistre e 10 destre, e
    solo dopo si è trovata la fonte che dice «16 corners with 10 right turns and
    6 left turns».

    La controprova sta nella stessa pagina: il tracciato di oggi è dato a 14
    curve e 5L/9R, cioè questo meno una destra e una sinistra — che sono
    esattamente la T9 e la T10 rimosse nel 2022."""
    d = trackdata._DIRECTIONS["melbourne"]
    assert sum(v == "left" for v in d.values()) == 6
    assert sum(v == "right" for v in d.values()) == 10
    assert [n for n, v in sorted(d.items()) if v == "left"] == [2, 4, 7, 10, 11, 15]


def test_melbournes_nine_ten_complex_is_forced_and_not_chosen():
    """Il perno di tutta la tabella, e non è una lettura: è un'eliminazione.

    L'unica frase strutturale disponibile dice che il complesso T9-T10 era «a
    heavy right-left corner». Nella traccia ci sono cinque coppie consecutive
    destra-poi-sinistra, ma otto curve devono starci davanti e sei dietro:
    quattro delle cinque non ce la fanno per aritmetica. Ne resta **una**, e da
    lì scende tutto il resto della numerazione."""
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    import corner_atlas

    found, _total = corner_atlas.analyse(
        *corner_atlas.centreline(corner_atlas.TRACKS / "Melbourne.csv"), flip=True)
    survivors = [i for i, (a, b) in enumerate(zip(found, found[1:]))
                 if a[2] == "right" and b[2] == "left"
                 and i >= 8 and len(found) - (i + 2) >= 6]
    assert len(survivors) == 1, "il complesso T9-T10 non è più forzato"

    pos = dict(trackdata._CORNERS["melbourne"])
    assert pos[9] == round(found[survivors[0]][0], 3)
    assert pos[10] == round(found[survivors[0] + 1][0], 3)


def test_melbourne_shows_that_a_matching_count_is_not_a_matching_layout():
    """Il controesempio che questo circuito regala, e che vale oltre Melbourne.

    A soglia 150 m il rilevatore trova **esattamente sedici** apici, che è il
    numero pubblicato — la coincidenza che invita a fidarsi del conteggio. E
    quell'assegnazione è falsa: mette la nona e la decima curva entrambe a
    sinistra, mentre la fonte dice che erano una destra e una sinistra."""
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    import corner_atlas

    keep = corner_atlas.MAX_RADIUS_M
    try:
        corner_atlas.MAX_RADIUS_M = 150.0
        found, _t = corner_atlas.analyse(
            *corner_atlas.centreline(corner_atlas.TRACKS / "Melbourne.csv"),
            flip=True)
    finally:
        corner_atlas.MAX_RADIUS_M = keep

    assert len(found) == 16, "la coincidenza che rende utile questo test"
    assert [found[8][2], found[9][2]] == ["left", "left"]
    assert [trackdata._DIRECTIONS["melbourne"][9],
            trackdata._DIRECTIONS["melbourne"][10]] == ["right", "left"]


def test_melbourne_turn_thirteen_is_the_only_candidate_at_the_end_of_a_straight():
    """Delle quattro destre in coda al giro, la T13 è decisa da tre frasi
    indipendenti: fu allargata «under brakes», la sua erede di oggi sta «at the
    end of the second-longest straight», ed è «the once-tight entry of Turn 11».

    La prima stesura di questo test si accontentava di «il vuoto sta fra 600 e
    800 m», che non distingue niente: anche T10→T11 misura 688 m. Qui si rifà
    il conto che ha davvero scelto — la rincorsa **netta**, contando piatti i
    kink con r>130 m — e si pretende che una sola candidata la superi."""
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    import corner_atlas

    found, total = corner_atlas.analyse(
        *corner_atlas.centreline(corner_atlas.TRACKS / "Melbourne.csv"), flip=True)
    metri = [(round(f, 3), f * total, r) for f, r, _d in found]

    def rincorsa(pos):
        i = next(k for k, (p, _m, _r) in enumerate(metri) if p == pos)
        j = i - 1
        while j >= 0 and metri[j][2] > 130.0:      # un kink piatto non spezza un rettilineo
            j -= 1
        return metri[i][1] - metri[j][1]

    lunghe = [p for p in (0.701, 0.724, 0.788, 0.834) if rincorsa(p) > 600.0]
    assert lunghe == [0.788], f"la T13 non è più l'unica in fondo a un rettilineo: {lunghe}"
    assert dict(trackdata._CORNERS["melbourne"])[13] == 0.788
    assert trackdata._DIRECTIONS["melbourne"][13] == "right"


def test_melbourne_directions_come_from_sources_not_from_the_arithmetic():
    """Il difetto trovato in verifica il 05/08, fissato perché non torni.

    La prima stesura sosteneva che, inchiodate T9-T12, «le sei sinistre sono
    esaurite e il verso non può sbagliare». È **circolare**: l'eliminazione
    fissa quattro righe, non tredici, e da sola lascia otto sequenze
    ammissibili. A chiudere la sequenza sono le fonti — una guida che percorre
    il tracciato di oggi e dichiara lei stessa la rinumerazione del 2022.

    Il test conta quelle otto: se un domani diventassero una, la frase
    «l'aritmetica basta» sarebbe vera e questo test lo direbbe."""
    from itertools import combinations
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    import corner_atlas

    found, _t = corner_atlas.analyse(
        *corner_atlas.centreline(corner_atlas.TRACKS / "Melbourne.csv"), flip=True)
    versi = [a[2][0].upper() for a in found]

    ammissibili = set()
    for davanti in combinations(range(9), 8):          # T1..T8 fra i primi nove apici
        for dietro in combinations(range(13, 19), 4):  # T13..T16 fra gli ultimi sei
            s = "".join(versi[i] for i in list(davanti) + [9, 10, 11, 12] + list(dietro))
            if s.count("L") == 6 and s.count("R") == 10:
                ammissibili.add(s)

    assert len(ammissibili) == 8, "l'eliminazione da sola non basta, ed è il punto"
    tabella = "".join(trackdata._DIRECTIONS["melbourne"][n][0].upper()
                      for n in range(1, 17))
    assert tabella in ammissibili, "la sequenza scelta deve almeno essere ammissibile"


def test_melbourne_turn_eight_is_the_one_row_that_is_not_settled():
    """L'unica riga non risolta, e sta scritta invece che nascosta.

    La T8 è uno di due kink piatti a destra distanti 165 m, e la fonte li
    descrive entrambi allo stesso modo. Scelto il più stretto — la regola di
    spareggio già scritta nello strumento. Il test fissa il costo massimo
    dell'errore: dentro la tolleranza dei nomi, e dallo stesso lato."""
    pos = dict(trackdata._CORNERS["melbourne"])
    altra = 0.399
    assert abs(pos[8] - altra) * 5294.0 < trackdata._NAME_TOL * 5294.0
    assert trackdata._DIRECTIONS["melbourne"][8] == "right"


def test_a_circuit_is_never_both_curated_and_held():
    """La lista dei fermi **marcisce**, ed è il motivo per cui `--check` la
    riverifica invece di limitarsi a scriverla. Ma quel controllo protesta solo
    verso un umano che legge lo stdout: lo script esce sempre con codice 0 e
    nessuno lo lancia in CI. Trovato in verifica il 05/08 — qui la stessa
    condizione diventa un test che può fallire davvero.

    Serve anche a chiudere il conto: ogni traccia in bundle o è curata o è
    ferma con un motivo scritto, mai tutt'e due e mai nessuna delle due."""
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    import corner_atlas

    doppi = sorted(set(corner_atlas.HELD) & set(trackdata._CORNERS))
    assert not doppi, f"curati e fermi allo stesso tempo: {doppi}"

    tracce = {p.stem for p in corner_atlas.TRACKS.glob("*.csv")}
    curati = {corner_atlas.CSV_FOR[k][:-4] for k in trackdata._CORNERS
              if corner_atlas.CSV_FOR.get(k)}
    fermi = {corner_atlas.CSV_FOR[k][:-4] for k in corner_atlas.HELD}
    assert curati | fermi == tracce, f"tracce senza destino: {tracce - curati - fermi}"
    assert not (curati & fermi)
