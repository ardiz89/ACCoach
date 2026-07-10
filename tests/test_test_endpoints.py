"""Test-checklist backend: page, latest-lap auto-attach, run save + bundled plan."""
import json

from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _seed(tmp_path):
    fast = synth.build_lap()
    fast.recorded_utc = "2026-06-20T18:00:00+00:00"
    save_lap(fast, tmp_path)
    for day, amt in (("2026-06-21", 30), ("2026-06-22", 16)):
        lap = synth.build_lap(slow_corner=0, amt=amt)
        lap.recorded_utc = f"{day}T18:00:00+00:00"
        save_lap(lap, tmp_path)


def test_test_page_served(tmp_path):
    c = TestClient(create_api(tmp_path))
    r = c.get("/test")
    assert r.status_code == 200 and "HONE" in r.text


def test_latest_lap_returns_most_recent(tmp_path):
    _seed(tmp_path)
    c = TestClient(create_api(tmp_path))
    lap = c.get("/api/test/latest_lap").json()["lap"]
    assert lap is not None
    assert lap["car"] == CAR and lap["track"] == TRACK
    assert lap["recorded_utc"] == "2026-06-22T18:00:00+00:00"   # the newest one
    assert lap["path"].endswith(".lap.json.gz")
    assert lap["valid"] is True


def test_latest_lap_empty_store(tmp_path):
    c = TestClient(create_api(tmp_path))
    assert c.get("/api/test/latest_lap").json() == {"lap": None}


def test_save_run_writes_json_to_disk(tmp_path):
    c = TestClient(create_api(tmp_path))
    payload = {"run_id": "abc123", "category": "GT3", "car": "Ferrari 296",
               "track": "Monza", "results": [{"id": "GT3-2", "outcome": "partial"}]}
    out = c.post("/api/test/save", json=payload).json()
    assert out["ok"] is True
    saved = tmp_path.parent / "test_runs" / out["file"]
    assert saved.is_file()
    back = json.loads(saved.read_text(encoding="utf-8"))
    assert back["category"] == "GT3"
    assert back["results"][0]["outcome"] == "partial"


def test_save_run_overwrites_per_run_id(tmp_path):
    c = TestClient(create_api(tmp_path))
    base = {"run_id": "same", "category": "GT3", "results": []}
    f1 = c.post("/api/test/save", json=base).json()["file"]
    f2 = c.post("/api/test/save", json={**base, "car": "x"}).json()["file"]
    assert f1 == f2   # stable run_id -> one file per session, not a pile of them
    # exactly one file for THIS run_id (tmp_path.parent is shared across tests).
    runs = list((tmp_path.parent / "test_runs").glob(f1))
    assert len(runs) == 1


def test_bundled_test_plan_is_valid(tmp_path):
    c = TestClient(create_api(tmp_path))
    plan = c.get("/static/test_plan.json").json()
    ids = [t["id"] for cat in plan["categories"] for t in cat["tests"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 40    # unique, non-trivial
    assert {cat["id"] for cat in plan["categories"]} == {"GT3", "Formula", "Stradali", "Generale"}
    assert plan["glossary"]
