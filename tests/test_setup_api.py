"""setup REST routes: discover, read, preview (no write), apply (confirm), undo."""
import json

from fastapi.testclient import TestClient

from accoach.api import create_api

CAR, TRACK = "mclaren_720s_gt3_evo", "Imola"

SAMPLE = {
    "carName": CAR,
    "basicSetup": {
        "tyres": {"tyreCompound": 0, "tyrePressure": [57, 52, 51, 48]},
        "alignment": {"camber": [0, 0, 0, 0], "toe": [18, 18, 21, 20],
                      "casterLF": 46, "casterRF": 46},
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


def _seed(tmp_path):
    """Write a real-shaped setup under <root>/<car>/<track>/ and return paths."""
    setups_root = tmp_path / "Setups"
    laps_dir = tmp_path / "laps"
    d = setups_root / CAR / TRACK
    d.mkdir(parents=True)
    setup_path = d / "base.json"
    setup_path.write_text(json.dumps(SAMPLE, indent="\t"), encoding="utf-8")
    return setups_root, laps_dir, setup_path


def _client(tmp_path):
    setups_root, laps_dir, setup_path = _seed(tmp_path)
    client = TestClient(create_api(laps_dir, setups_root=setups_root))
    return client, str(setup_path)


def test_combos_and_list(tmp_path):
    c, _ = _client(tmp_path)
    combos = c.get("/api/setup/combos").json()
    assert combos == [{"car": CAR, "track": TRACK, "count": 1}]
    lst = c.get("/api/setup/list", params={"car": CAR, "track": TRACK}).json()
    assert [x["name"] for x in lst] == ["base"]


def test_current_returns_structured_params(tmp_path):
    c, path = _client(tmp_path)
    data = c.get("/api/setup/current", params={"path": path}).json()
    assert data["car"] == CAR
    assert "Gomme" in data["groups"]
    press = next(p for p in data["params"] if p["key"] == "tyrePressure")
    assert [s["slot"] for s in press["slots"]] == ["Ant-Sx", "Ant-Dx",
                                                   "Post-Sx", "Post-Dx"]
    assert press["slots"][3]["click"] == 48
    assert press["slots"][3]["physical"].startswith("25.1")


def test_preview_does_not_write(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "changes": [
        {"param": "tyrePressure", "slot": "Post-Dx", "delta_clicks": 2}]}
    res = c.post("/api/setup/preview", json=body).json()
    assert res["ok"] is True
    assert res["diff"][0]["delta"] == 2
    # original on disk unchanged
    on_disk = json.loads(open(path, encoding="utf-8").read())
    assert on_disk["basicSetup"]["tyres"]["tyrePressure"][3] == 48


def test_preview_reports_errors(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "changes": [
        {"param": "nope", "delta_clicks": 1},
        {"param": "rearWing", "value": -3}]}
    res = c.post("/api/setup/preview", json=body).json()
    assert res["ok"] is False
    assert len(res["errors"]) == 2


def test_apply_requires_confirm(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "as_name": "ACCoach_run1",
            "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    r = c.post("/api/setup/apply", json=body)
    assert r.status_code == 400


def test_apply_writes_new_file(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "as_name": "ACCoach_run1", "confirm": True,
            "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    r = c.post("/api/setup/apply", json=body).json()
    assert r["ok"] is True and r["name"] == "ACCoach_run1"
    assert "box" in r["reload_hint"].lower()
    # the new file exists with the change; original untouched
    newp = r["path"]
    assert json.loads(open(newp, encoding="utf-8").read())[
        "advancedSetup"]["aeroBalance"]["rearWing"] == 10
    assert json.loads(open(path, encoding="utf-8").read())[
        "advancedSetup"]["aeroBalance"]["rearWing"] == 11


def test_apply_rejects_duplicate_without_overwrite(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "as_name": "dup", "confirm": True,
            "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    assert c.post("/api/setup/apply", json=body).status_code == 200
    assert c.post("/api/setup/apply", json=body).status_code == 409


def test_apply_invalid_change_is_422(tmp_path):
    c, path = _client(tmp_path)
    body = {"path": path, "as_name": "bad", "confirm": True,
            "changes": [{"param": "rearWing", "value": -5}]}
    assert c.post("/api/setup/apply", json=body).status_code == 422


def test_undo_after_overwrite(tmp_path):
    c, path = _client(tmp_path)
    # write run1
    base = {"path": path, "as_name": "run1", "confirm": True,
            "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    newp = c.post("/api/setup/apply", json=base).json()["path"]
    # overwrite run1 from itself (backs up), then undo restores
    over = {"path": newp, "as_name": "run1", "confirm": True, "overwrite": True,
            "changes": [{"param": "rearWing", "delta_clicks": -3}]}
    c.post("/api/setup/apply", json=over)
    assert json.loads(open(newp, encoding="utf-8").read())[
        "advancedSetup"]["aeroBalance"]["rearWing"] == 7
    r = c.post("/api/setup/undo", json={"path": newp}).json()
    assert r["ok"] is True
    assert json.loads(open(newp, encoding="utf-8").read())[
        "advancedSetup"]["aeroBalance"]["rearWing"] == 10


def test_path_escape_is_forbidden(tmp_path):
    c, _ = _client(tmp_path)
    r = c.get("/api/setup/current", params={"path": str(tmp_path / "secret.json")})
    assert r.status_code == 403


def test_class_endpoint(tmp_path):
    c, _ = _client(tmp_path)
    data = c.get("/api/setup/class", params={"car": CAR}).json()
    assert data["class"] == "GT3"
    assert data["profile"]["name"] == "GT3"
    assert data["profile"]["phases"][0] == "Pressioni"
    assert "Bilanciamento freni" in data["profile"]["al_volo"]
    # a formula car gets the Formula engineer
    f = c.get("/api/setup/class", params={"car": "f1_1990_mclaren"}).json()
    assert f["class"] == "Formula"
    assert f["profile"]["phases"].index("Aero / rake") < \
           f["profile"]["phases"].index("Grip meccanico")


def test_engineer_page_is_served(tmp_path):
    c, _ = _client(tmp_path)
    r = c.get("/engineer")
    assert r.status_code == 200
    assert "Ingegnere" in r.text
    # its static assets are reachable too
    assert c.get("/static/engineer.js").status_code == 200
    assert c.get("/static/engineer.css").status_code == 200
