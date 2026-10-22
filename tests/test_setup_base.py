"""`/api/setup/base`: il file a cui la vista tablet applica una modifica.

Lo sceglie il processo web, non la pagina: l'ultimo file scritto da
`/api/setup/apply` in questo processo, se no il piu' recente per data.
"""
import json
import os

from fastapi.testclient import TestClient

from accoach.api import create_api
from tests.test_setup_api import CAR, SAMPLE, TRACK, _seed

CHANGE = [{"param": "tyrePressure", "slot": 0, "delta_clicks": 1}]


def _setup(tmp_path):
    setups_root, laps_dir, base = _seed(tmp_path)
    d = base.parent
    a, b = d / "a.json", d / "b.json"
    for p in (a, b):
        p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    os.utime(base, (1_000, 1_000))
    os.utime(a, (2_000, 2_000))
    os.utime(b, (3_000, 3_000))
    client = TestClient(create_api(laps_dir, setups_root=setups_root))
    return client, d, a, b


def _base(client, car=CAR, track=TRACK):
    r = client.get("/api/setup/base", params={"car": car, "track": track})
    assert r.status_code == 200
    return r.json()


def _apply(client, path):
    r = client.post("/api/setup/apply", json={
        "path": str(path), "changes": CHANGE, "as_name": "HONE_1",
        "confirm": True})
    assert r.status_code == 200, r.text


def test_base_is_the_most_recent_file(tmp_path):
    client, d, a, b = _setup(tmp_path)
    out = _base(client)
    assert out["base"].endswith("b.json")
    assert out["last_written"] is None
    assert out["car"] == CAR and out["track"] == TRACK


def test_base_is_the_last_written_after_apply(tmp_path):
    client, d, a, b = _setup(tmp_path)
    _apply(client, b)
    os.utime(a, (9_000_000_000, 9_000_000_000))
    out = _base(client)
    assert out["base"].endswith("HONE_1.json")
    assert out["last_written"] == "HONE_1"


def test_last_written_file_deleted_falls_back(tmp_path):
    client, d, a, b = _setup(tmp_path)
    _apply(client, b)
    (d / "HONE_1.json").unlink()
    out = _base(client)
    assert out["base"].endswith("b.json")
    assert out["last_written"] is None


def test_case_of_frame_names_does_not_matter(tmp_path):
    client, d, a, b = _setup(tmp_path)
    out = _base(client, car=CAR.upper(), track="imola")
    assert out["track"] == "Imola"
    assert out["car"] == CAR
    assert out["base"] is not None


def test_unknown_combo(tmp_path):
    client, d, a, b = _setup(tmp_path)
    assert _base(client, car="nessuna_auto") == {
        "car": None, "track": None, "setups": [], "base": None,
        "last_written": None}


def test_list_carries_mtime(tmp_path):
    client, d, a, b = _setup(tmp_path)
    rows = client.get("/api/setup/list",
                      params={"car": CAR, "track": TRACK}).json()
    assert rows
    for r in rows:
        assert {"name", "path", "mtime"} <= set(r)
        assert isinstance(r["mtime"], (int, float))
