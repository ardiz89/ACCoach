"""setup foundation: parse, adjust (in clicks), diff, and safe write/undo."""
import json

import pytest

from accoach.setup import acc_format, store
from accoach.setup.acc_format import SETUP_PARAMS, load, loads, slot_labels
from accoach.setup.diff import diff as compute_diff
from accoach.setup.diff import format_diff

# A trimmed-but-real ACC setup (McLaren 720S GT3 EVO / Imola), enough to cover
# scalars, per-wheel and per-axle arrays.
SAMPLE = {
    "carName": "mclaren_720s_gt3_evo",
    "basicSetup": {
        "tyres": {"tyreCompound": 0, "tyrePressure": [57, 52, 51, 48]},
        "alignment": {"camber": [0, 0, 0, 0], "toe": [18, 18, 21, 20],
                      "casterLF": 46, "casterRF": 46, "steerRatio": 1},
        "electronics": {"tC1": 3, "tC2": 0, "abs": 4, "eCUMap": 0, "fuelMix": 0},
        "strategy": {"fuel": 48},
    },
    "advancedSetup": {
        "mechanicalBalance": {"aRBFront": 11, "aRBRear": 3,
                              "wheelRate": [2, 2, 0, 0], "brakeBias": 0,
                              "brakeTorque": 20},
        "dampers": {"bumpSlow": [0, 0, 0, 0], "bumpFast": [20, 20, 15, 15],
                    "reboundSlow": [10, 10, 40, 40], "reboundFast": [39, 39, 25, 25]},
        "aeroBalance": {"rideHeight": [4, 6, 8, 18], "splitter": 3,
                        "rearWing": 11, "brakeDuct": [3, 3]},
        "drivetrain": {"preload": 0},
    },
}


def _setup():
    return loads(json.dumps(SAMPLE))


def test_loads_and_car_name():
    s = _setup()
    assert s.car_name == "mclaren_720s_gt3_evo"


def test_loads_rejects_non_setup():
    with pytest.raises(acc_format.SetupError):
        loads('{"foo": 1}')


def test_slot_labels():
    assert slot_labels(4) == ("Ant-Sx", "Ant-Dx", "Post-Sx", "Post-Dx")
    assert slot_labels(2) == ("Ant", "Post")
    assert slot_labels(3) == ("0", "1", "2")


def _spec(key):
    return next(s for s in SETUP_PARAMS if s.key == key)


def test_read_scalar_and_array():
    s = _setup()
    assert s.click(_spec("rearWing")) == 11
    assert s.slots(_spec("rearWing")) == 1
    assert s.slots(_spec("tyrePressure")) == 4
    assert s.click(_spec("tyrePressure"), 3) == 48      # Post-Dx


def test_adjust_in_clicks():
    s = _setup()
    new = s.adjust(_spec("tyrePressure"), 3, +2)
    assert new == 50
    assert s.click(_spec("tyrePressure"), 3) == 50


def test_set_click_rejects_negative():
    s = _setup()
    with pytest.raises(acc_format.SetupError):
        s.set_click(_spec("rearWing"), 0, -1)


def test_slot_out_of_range():
    s = _setup()
    with pytest.raises(acc_format.SetupError):
        s.click(_spec("tyrePressure"), 9)


def test_physical_pressure_conversion():
    s = _setup()
    # base 20.3 + 48*0.1 = 25.1 psi (Post-Dx)
    assert s.physical(_spec("tyrePressure"), 3).startswith("25.1")


def test_physical_clicks_only_for_unknown_base():
    s = _setup()
    # brakeBias knows the step (0.2%/click) but not the base -> show clicks
    assert "click" in s.physical(_spec("brakeBias"))


def test_present_false_for_missing_param():
    s = loads(json.dumps({"carName": "x", "basicSetup": {"tyres": {}}}))
    assert not s.present(_spec("rearWing"))


def test_copy_is_independent():
    s = _setup()
    c = s.copy()
    c.adjust(_spec("rearWing"), 0, +5)
    assert s.click(_spec("rearWing")) == 11
    assert c.click(_spec("rearWing")) == 16


def test_to_json_roundtrips():
    s = _setup()
    again = loads(s.to_json())
    assert again.raw == s.raw


def test_diff_lists_only_changes():
    before = _setup()
    after = before.copy()
    after.adjust(_spec("tyrePressure"), 3, +2)
    after.adjust(_spec("rearWing"), 0, -1)
    changes = compute_diff(before, after)
    keys = {(c.label, c.slot) for c in changes}
    assert ("Pressione", "Post-Dx") in keys
    assert ("Ala posteriore", "") in keys
    assert len(changes) == 2
    # delta sign and rendering
    press = next(c for c in changes if c.label == "Pressione")
    assert press.delta == 2
    assert "→" in str(press)


def test_format_diff_empty():
    assert "nessuna" in format_diff([])


# --- store: backup / atomic write / undo --------------------------------

def test_save_refuses_overwrite_then_backs_up(tmp_path):
    s = _setup()
    out = store.save(s, tmp_path, "ACCoach_run1")
    assert out.name == "ACCoach_run1.json"
    # second save without overwrite -> error
    with pytest.raises(FileExistsError):
        store.save(s, tmp_path, "ACCoach_run1")
    # with overwrite -> backs up the previous file
    s.adjust(_spec("rearWing"), 0, +1)
    store.save(s, tmp_path, "ACCoach_run1", overwrite=True)
    assert store.latest_backup(out) is not None


def test_undo_restores_previous(tmp_path):
    s = _setup()
    out = store.save(s, tmp_path, "ACCoach_run1")
    original_wing = load(out).click(_spec("rearWing"))

    s2 = s.copy()
    s2.adjust(_spec("rearWing"), 0, +4)
    store.save(s2, tmp_path, "ACCoach_run1", overwrite=True)   # backs up original
    assert load(out).click(_spec("rearWing")) == original_wing + 4

    store.undo(out)
    assert load(out).click(_spec("rearWing")) == original_wing


def test_undo_without_backup_raises(tmp_path):
    s = _setup()
    out = store.save(s, tmp_path, "fresh")
    with pytest.raises(FileNotFoundError):
        store.undo(out)


def test_list_setups(tmp_path):
    car_dir = tmp_path / "mclaren_720s_gt3_evo" / "Imola"
    car_dir.mkdir(parents=True)
    store.save(_setup(), car_dir, "a")
    store.save(_setup(), car_dir, "b")
    found = store.list_setups("mclaren_720s_gt3_evo", "Imola", tmp_path)
    assert [p.stem for p in found] == ["a", "b"]


def test_list_setups_empty(tmp_path):
    assert store.list_setups("nope", "nope", tmp_path) == []
