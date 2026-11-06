"""api: /api/mapbg e i tasselli — lo sfondo dal gioco, solo per il PC.

Si controlla quello che la rotta promette: chi non e' sul PC non riceve nulla,
ogni motivo di rifiuto ha il suo nome, i parametri fatti a mano non arrivano al
disco, e un tassello vuoto e' 204.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accoach import guard, trackart, trackedges
from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"
KEY = "0123456789abcdef"
LOCAL, REMOTE = ("127.0.0.1", 5000), ("192.168.1.20", 5000)


@pytest.fixture(autouse=True)
def _rete(monkeypatch):
    monkeypatch.setattr(guard, "_rete",
                        lambda: (0.0, frozenset({"127.0.0.1"}), frozenset()))
    monkeypatch.setattr(guard, "lan_key", lambda: "ABCD-EFGH-JKMN-PQRS")


def _client(tmp_path, who=LOCAL, coords=True):
    lap = synth.build_lap()
    lap.recorded_utc = "2026-06-20T18:00:00+00:00"
    if not coords:
        for s in lap.samples:
            s.car_x = s.car_z = 0.0
    save_lap(lap, tmp_path)
    # Chi e' in rete entra col tasto giusto: e' proprio il caso da chiudere.
    return TestClient(create_api(tmp_path), client=who,
                      headers={guard.HEADER: "ABCD-EFGH-JKMN-PQRS"})


def _ask(c):
    return c.get("/api/mapbg", params={"car": CAR, "track": TRACK})


def _ac(monkeypatch, fit=True, key=KEY, p95=1.0):
    monkeypatch.setattr(trackedges, "tracks_dir", lambda: Path("x"))
    f = trackedges.Fit(scale=1.0, cos=1.0, sin=0.0, dx=2.0, dz=3.0,
                       p95_m=p95, mirror=False)
    monkeypatch.setattr(trackedges, "ac_fit",
                        lambda pts: (Path("s.ai"), f) if fit else None)
    monkeypatch.setattr(trackart, "art_key", lambda spline: key)


def test_a_remote_client_gets_no_background(tmp_path, monkeypatch):
    _ac(monkeypatch)
    c = _client(tmp_path, REMOTE)
    assert _ask(c).json() == {"ok": False, "reason": "remote"}
    monkeypatch.setattr(trackart, "tile", lambda *a: b"jpg")
    assert c.get(f"/api/mapbg/tile/{KEY}/0/0/0").status_code == 403


def test_without_ac_the_reason_is_no_ac(tmp_path, monkeypatch):
    monkeypatch.setattr(trackedges, "tracks_dir", lambda: None)
    assert _ask(_client(tmp_path)).json() == {"ok": False, "reason": "no_ac"}


def test_a_bundled_only_track_is_no_fit(tmp_path, monkeypatch):
    _ac(monkeypatch, fit=False)
    assert _ask(_client(tmp_path)).json() == {"ok": False, "reason": "no_fit"}


def test_the_background_has_its_own_tighter_gate():
    # Riconoscere il circuito tollera 35 m; posare una foto sotto la linea no.
    assert trackart.BG_FIT_P95_M == 10.0
    assert trackart.BG_FIT_P95_M < trackedges._FIT_P95_M


def test_a_loose_fit_is_no_fit_for_the_background(tmp_path, monkeypatch):
    # 12 m al 95-esimo: l'auto finirebbe fuori dall'asfalto della foto.
    _ac(monkeypatch, p95=12.0)
    assert _ask(_client(tmp_path)).json() == {"ok": False, "reason": "no_fit"}


def test_a_tight_fit_gets_the_background(tmp_path, monkeypatch):
    _ac(monkeypatch, p95=6.0)
    assert _ask(_client(tmp_path)).json()["ok"] is True


def test_a_lap_without_coordinates_is_no_fit(tmp_path, monkeypatch):
    _ac(monkeypatch)
    c = _client(tmp_path, coords=False)
    assert _ask(c).json() == {"ok": False, "reason": "no_fit"}


def test_no_model_when_the_key_is_missing(tmp_path, monkeypatch):
    _ac(monkeypatch, key=None)
    assert _ask(_client(tmp_path)).json() == {"ok": False, "reason": "no_model"}


def test_a_placed_lap_gets_key_fit_and_levels(tmp_path, monkeypatch):
    _ac(monkeypatch)
    j = _ask(_client(tmp_path)).json()
    assert j["ok"] is True and j["key"] == KEY
    assert set(j["fit"]) == {"scale", "cos", "sin", "dx", "dz", "mirror"}
    assert j["levels"] == list(trackart.LEVELS_M)
    assert j["tile_px"] == trackart.TILE_PX


@pytest.mark.parametrize("path", [
    "../../x/0/0/0", "ZZZZZZZZZZZZZZZZ/0/0/0", "0123456789abcde/0/0/0",
    f"{KEY}/9/0/0", f"{KEY}/-1/0/0", f"{KEY}/0/a/0", f"{KEY}/0/0/..",
])
def test_tile_params_are_checked(tmp_path, monkeypatch, path):
    calls = []
    monkeypatch.setattr(trackart, "tile", lambda *a: calls.append(a))
    r = _client(tmp_path).get("/api/mapbg/tile/" + path)
    assert r.status_code in (404, 422)
    assert not calls


def test_an_unknown_key_is_404(tmp_path):
    assert _client(tmp_path).get(f"/api/mapbg/tile/{KEY}/0/0/0").status_code == 404


def test_an_empty_tile_is_204(tmp_path, monkeypatch):
    monkeypatch.setattr(trackart, "tile", lambda *a: None)
    r = _client(tmp_path).get(f"/api/mapbg/tile/{KEY}/0/0/0")
    assert r.status_code == 204 and r.content == b""


def test_a_tile_is_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(trackart, "tile", lambda *a: b"\xff\xd8jpg")
    r = _client(tmp_path).get(f"/api/mapbg/tile/{KEY}/2/-1/3")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == b"\xff\xd8jpg"
    assert "max-age" in r.headers["cache-control"]
