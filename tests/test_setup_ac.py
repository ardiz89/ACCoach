"""AC (.ini) setup: parse, edit (clicks), round-trip, loader dispatch, REST."""
import pytest
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.setup import ac_format
from accoach.setup.loader import load_any

SAMPLE_INI = """[CAR]
MODEL=f1_1990_mclaren

[PRESSURE_LF]
VALUE=17

[PRESSURE_RF]
VALUE=17

[PRESSURE_LR]
VALUE=18

[PRESSURE_RR]
VALUE=18

[ARB_FRONT]
VALUE=30

[ARB_REAR]
VALUE=0

[WING_1]
VALUE=3

[WING_2]
VALUE=13

[FRONT_BIAS]
VALUE=53

[DIFF_POWER]
VALUE=15

[__EXT_PATCH]
DATA=keepme
"""


def _setup():
    return ac_format.loads(SAMPLE_INI)


def _spec(s, key):
    return s.spec_by_key(key)


def test_parse_car_name_and_format():
    s = _setup()
    assert s.car_name == "f1_1990_mclaren"
    assert s.ext == "ini"


def test_read_scalar_and_wheel():
    s = _setup()
    assert s.click(_spec(s, "aRBFront")) == 30
    assert s.slots(_spec(s, "tyrePressure")) == 4
    assert s.click(_spec(s, "tyrePressure"), 3) == 18      # RR


def test_adjust_and_set():
    s = _setup()
    assert s.adjust(_spec(s, "frontWing"), 0, +2) == 5
    s.set_click(_spec(s, "rearWing"), 0, 10)
    assert s.click(_spec(s, "rearWing")) == 10


def test_present_false_for_missing():
    s = _setup()
    # SPRING_RATE_* sections aren't in the sample → wheelRate absent
    assert not s.present(_spec(s, "wheelRate"))
    assert s.present(_spec(s, "tyrePressure"))


def test_roundtrip_preserves_all_sections():
    s = _setup()
    text = s.to_text()
    assert "MODEL=f1_1990_mclaren" in text
    assert "DATA=keepme" in text                # non-VALUE keys survive
    again = ac_format.loads(text)
    assert again.to_text() == text              # idempotent
    assert again.click(_spec(again, "tyrePressure"), 3) == 18


def test_copy_is_independent():
    s = _setup()
    c = s.copy()
    c.adjust(_spec(c, "frontWing"), 0, +5)
    assert s.click(_spec(s, "frontWing")) == 3
    assert c.click(_spec(c, "frontWing")) == 8


def test_loads_rejects_non_ini():
    with pytest.raises(ac_format.AcSetupError):
        ac_format.loads("not an ini at all")


def test_loader_dispatches_by_extension(tmp_path):
    ini = tmp_path / "s.ini"
    ini.write_text(SAMPLE_INI, encoding="utf-8")
    s = load_any(ini)
    assert s.ext == "ini"
    json_path = tmp_path / "s.json"
    json_path.write_text('{"carName":"x","basicSetup":{"tyres":{}}}', encoding="utf-8")
    assert load_any(json_path).ext == "json"
    with pytest.raises(ValueError):
        load_any(tmp_path / "s.txt")


# --- REST works on an AC .ini path ----------------------------------------

def _client(tmp_path):
    ac_root = tmp_path / "ac"
    d = ac_root / "f1_1990_mclaren" / "monza"
    d.mkdir(parents=True)
    setup = d / "race.ini"
    setup.write_text(SAMPLE_INI, encoding="utf-8")
    client = TestClient(create_api(tmp_path / "laps", setups_root=[ac_root]))
    return client, str(setup)


def test_rest_current_on_ini(tmp_path):
    c, path = _client(tmp_path)
    data = c.get("/api/setup/current", params={"path": path}).json()
    assert data["format"] == "ini"
    assert data["car"] == "f1_1990_mclaren"
    wing = next(p for p in data["params"] if p["key"] == "frontWing")
    assert wing["slots"][0]["click"] == 3


def test_rest_preview_and_apply_ini(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "changes": [{"param": "frontWing", "delta_clicks": 1}]}
    prev = c.post("/api/setup/preview", json=body).json()
    assert prev["ok"] and prev["diff"][0]["delta"] == 1
    # apply writes a new .ini
    ap = {**body, "as_name": "ACCoach_run1", "confirm": True}
    res = c.post("/api/setup/apply", json=ap).json()
    assert res["name"] == "ACCoach_run1"
    assert res["path"].endswith(".ini")


def test_combos_lists_ac(tmp_path):
    c, _ = _client(tmp_path)
    combos = c.get("/api/setup/combos").json()
    assert {"car": "f1_1990_mclaren", "track": "monza", "count": 1} in combos
