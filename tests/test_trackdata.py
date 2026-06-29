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
    assert not has_names("nordschleife")
    assert corner_name("nordschleife", 0, 0.3) == "Corner 1"
    assert corner_name("nordschleife", 4, 0.8) == "Corner 5"


def test_apex_outside_tolerance_falls_back():
    # 0.42 sits in the gap between Tosa (0.351) and Piratella (0.484), >tol from
    # both -> numbered fallback rather than a wrong name.
    assert corner_name("imola", 3, 0.42) == "Corner 4"


def test_name_corners_maps_a_list():
    corners = [_corner(0, 0.143), _corner(1, 0.291), _corner(2, 0.351)]
    assert name_corners("imola", corners) == ["Tamburello", "Villeneuve", "Tosa"]
