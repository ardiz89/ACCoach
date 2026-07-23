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


def test_shipped_landmark_tables_are_empty_until_verified():
    # Guard the honesty rule: no landmark reaches the driver before it's checked
    # against a trusted source. When Monza's data is filled, this test is the one
    # to update deliberately — it should never fail silently.
    assert all(not v for v in trackdata._LANDMARKS.values()), (
        "un landmark è stato spedito senza verifica: aggiorna questo test solo "
        "dopo aver validato i punti su una fonte fidata")
