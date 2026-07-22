"""trackdata: friendly corner names assigned by apex position."""
from accoach.track import Corner
from accoach.trackdata import corner_name, has_names, name_corners


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
    """0.447 and 0.500 are closer together than the tolerance is wide."""
    assert corner_name("monza", 3, 0.447) != corner_name("monza", 4, 0.500)
