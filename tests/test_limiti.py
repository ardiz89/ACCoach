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


def test_una_prova_con_una_nota_da_200_kb_passa(tmp_path):
    with _client(tmp_path) as c:
        prova = {"category": "g", "run_id": "r1", "note": "x" * 200_000}
        assert c.post("/api/test/save", json=prova).status_code == 200


def _prova_al_massimo() -> dict:
    """Il peggior corpo che il tablet puo' mandare, costruito come `saveRun` di
    test.js: tutti i 21 test del piano con le 60 righe di avvisi che
    `captureCue` tiene al massimo, ognuna con la telemetria del momento."""
    def avviso(i: int) -> dict:
        return {
            "t": "2026-10-24T10:15:30.123Z", "category": "brake_lock",
            "message": f"Bloccaggio anteriore sinistro in frenata {i}",
            "segment": "T1",
            "tel": {"spd": 212, "br": 0.93, "th": 0, "gear": 4, "pos": 0.4123,
                    "tc": 3, "abs": 4,
                    "tyre_temp": [81.2, 82.5, 84.1, 83.3],
                    "tyre_press": [27.1, 27.3, 26.2, 26.4]},
        }

    def risultato(n: int) -> dict:
        return {
            "id": f"t{n}", "n": n, "what": "Frena forte in rettilineo " * 4,
            "expected": "Avviso di bloccaggio entro mezzo secondo " * 3,
            "outcome": "partial", "notes": "x" * 400,
            "captured_cues": [avviso(i) for i in range(60)],
            "lap": {"path": "lap_0001.json", "car": "mclaren_720s_gt3_evo",
                    "track": "Imola", "lap_time_ms": 114321,
                    "lap_time": "1:54,321", "valid": True,
                    "recorded_utc": "2026-10-24T10:15:30"},
        }

    return {"run_id": "20261024T101530", "started": "2026-10-24T10:00:00Z",
            "app": "HONE test", "sim": "ACC", "category": "gt3",
            "category_title": "GT3", "car": "McLaren 720S GT3 Evo",
            "track": "Imola", "saved": "2026-10-24T10:15:31Z",
            "results": [risultato(n) for n in range(1, 22)]}


def test_la_prova_piu_grossa_possibile_passa_con_margine(tmp_path):
    prova = _prova_al_massimo()
    corpo = len(json.dumps(prova))
    # Il numero deve restare quello vero: sotto i 300 KB il test non prova piu'
    # niente, sopra il tetto la prova del tablet verrebbe rifiutata.
    assert 300_000 < corpo < guard.MAX_BODY // 2, corpo
    with _client(tmp_path) as c:
        assert c.post("/api/test/save", json=prova).status_code == 200


def test_la_richiesta_di_anteprima_di_un_assetto_vero_sta_sotto_il_tetto(tmp_path):
    from test_setup_api import _client as _client_assetti

    c, path = _client_assetti(tmp_path)
    parametri = c.get("/api/setup/current", params={"path": path}).json()["params"]
    # Un cambio per ogni voce e per ogni ruota: piu' di quanto l'ingegnere ne
    # proponga in un giro.
    cambi = [{"param": p["key"], "slot": s["slot"], "delta_clicks": 1}
             for p in parametri for s in (p.get("slots") or [{"slot": None}])]
    corpo = {"path": path, "changes": cambi}
    assert len(json.dumps(corpo)) < guard.MAX_BODY // 10
    r = c.post("/api/setup/preview", json=corpo)
    assert r.status_code == 200 and "ok" in r.json()


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
