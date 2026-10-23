"""Un tetto alle richieste e ai file che crescono (sicurezza, fase 2)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from accoach import cornernames, guard, netinfo
from accoach import api as api_mod
from accoach.api import create_api

LAN = "192.168.1.23"


@pytest.fixture(autouse=True)
def _rete_finta(monkeypatch):
    monkeypatch.setattr(netinfo, "lan_ip", lambda: LAN)
    guard._dimentica()
    yield


def _client(tmp_path):
    return TestClient(create_api(laps_dir=tmp_path / "laps"),
                      base_url="http://localhost:8778")


def test_un_assetto_vero_e_una_prova_da_200_kb_passano(tmp_path):
    with _client(tmp_path) as c:
        prova = {"category": "g", "run_id": "r1", "note": "x" * 200_000}
        assert c.post("/api/test/save", json=prova).status_code == 200


def test_test_save_si_ferma_a_200_file_ma_riscrive_quelli_che_ci_sono(
        tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "MAX_TEST_RUNS", 3)
    with _client(tmp_path) as c:
        for i in range(3):
            assert c.post("/api/test/save",
                          json={"category": "g", "run_id": f"r{i}"}).status_code == 200
        r = c.post("/api/test/save", json={"category": "g", "run_id": "nuovo"})
        assert r.status_code == 409
        assert r.json()["detail"] == "too many saved test runs"
        # l'autosave del tablet riscrive lo stesso file anche al tetto
        r = c.post("/api/test/save", json={"category": "g", "run_id": "r1", "n": 2})
        assert r.status_code == 200
    assert len(list((tmp_path / "test_runs").glob("*.json"))) == 3


def test_tetti_di_default():
    assert api_mod.MAX_TEST_RUNS == 200
    assert cornernames.MAX_TRACK == 80 and cornernames.MAX_TRACKS == 500


def test_corner_name_con_track_troppo_lunga_o_pista_501_e_400(tmp_path, monkeypatch):
    p = tmp_path / "cn.json"
    monkeypatch.setattr(cornernames, "path", lambda: p)
    with pytest.raises(ValueError):
        cornernames.put("T" * 81, 0.5, "x")
    with pytest.raises(ValueError):
        cornernames.put_mark("T" * 81, 0.5, "x")
    monkeypatch.setattr(cornernames, "MAX_TRACKS", 2)
    cornernames.put("a", 0.1, "uno")
    cornernames.put("b", 0.1, "due")
    with pytest.raises(ValueError):
        cornernames.put("c", 0.1, "tre")
    with pytest.raises(ValueError):
        cornernames.put_mark("c", 0.1, "tre")
    # una pista che c'e' gia' riceve nomi nuovi anche al tetto
    cornernames.put("a", 0.6, "altro")
    cornernames.put_mark("b", 0.3, "cartello")
    assert len(json.loads(p.read_text(encoding="utf-8"))) == 2
    with _client(tmp_path) as c:
        r = c.post("/api/corner-name", json={"track": "c", "pos": 0.2, "name": "x"})
        assert r.status_code == 400
        r = c.post("/api/braking-reference", json={"track": "c", "pos": 0.2, "text": "x"})
        assert r.status_code == 400
        r = c.post("/api/corner-name", json={"track": "T" * 81, "pos": 0.2, "name": "x"})
        assert r.status_code == 400
