"""Il tablet come l'overlay, piu' la mappa (15/11).

Il pilota: chi ha il tablet in mano deve leggere anche il trail braking, come
sull'overlay, e sotto la telemetria vedere la pista con l'auto che si muove,
ingrandibile fino a vedere l'auto rispetto alla strada.

Qui si prova cio' che il tablet riceve (la posizione a ogni frame, la pista una
volta) e le due regole che decide da se': lo stato dei pedali (TRAIL, veleggio)
con le stesse soglie dell'overlay, e quale pezzo di pista mostra a ogni zoom.
"""
import math

import pytest
from fastapi.testclient import TestClient

from accoach import api as api_mod
from accoach import overlay
from accoach.api import create_api
from accoach.recording.storage import save_lap
from accoach.serialize import snapshot_to_dict
from accoach.trackedges import TrackEdges

import synth
from test_tablet_page import _call, needs_node

CAR, TRACK = "ferrari_488_gt3", "monza"


# ---- la posizione dal vivo -------------------------------------------------

def test_lo_stato_dal_vivo_porta_la_posizione_dell_auto():
    d = snapshot_to_dict(synth.snap(pos=0.3, car_x=12.34, car_z=-5.67))
    assert d["pos"] == [12.3, -5.7]


def test_senza_coordinate_la_posizione_non_c_e():
    # 0,0 e' «il gioco non la manda», non un punto della pista.
    assert snapshot_to_dict(synth.snap(pos=0.3))["pos"] is None


# ---- la pista per il tablet ------------------------------------------------

def _client(tmp_path):
    lap = synth.build_lap()
    lap.recorded_utc = "2026-06-20T18:00:00+00:00"
    save_lap(lap, tmp_path)
    return TestClient(create_api(tmp_path))


def test_la_mappa_e_la_linea_del_giro_di_riferimento(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "edges_and_fit", lambda track, pts: (None, None))
    r = _client(tmp_path).get("/api/livemap", params={"car": CAR, "track": TRACK})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["edges"] is None
    line = j["line"]
    assert len(line) >= 50
    assert all(len(p) == 2 for p in line)
    # Diradata: abbastanza per l'iPad, mai due punti a meno di 3 m.
    gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:])]
    assert min(gaps) >= 3.0


def test_con_i_bordi_veri_la_mappa_porta_l_asfalto(tmp_path, monkeypatch):
    n = 40
    xs = [100 * math.cos(2 * math.pi * i / n) for i in range(n)]
    zs = [100 * math.sin(2 * math.pi * i / n) for i in range(n)]
    edges = TrackEdges(TRACK, xs, zs, [6.0] * n, [5.0] * n, breaks={7})
    monkeypatch.setattr(api_mod, "edges_and_fit", lambda track, pts: (edges, None))
    j = _client(tmp_path).get("/api/livemap", params={"car": CAR, "track": TRACK}).json()
    e = j["edges"]
    assert len(e["left"]) == len(e["right"]) == n
    assert e["breaks"] == [7]
    # 6 m a sinistra e 5 a destra della linea, nello stesso punto.
    c = (xs[0], zs[0])
    assert math.hypot(e["left"][0][0] - c[0], e["left"][0][1] - c[1]) == pytest.approx(6, abs=0.1)
    assert math.hypot(e["right"][0][0] - c[0], e["right"][0][1] - c[1]) == pytest.approx(5, abs=0.1)


def test_senza_giri_la_mappa_non_c_e(tmp_path):
    r = TestClient(create_api(tmp_path)).get("/api/livemap",
                                              params={"car": CAR, "track": TRACK})
    assert r.status_code == 404


# ---- le regole del tablet --------------------------------------------------

@needs_node
def test_trail_e_veleggio_con_le_soglie_dell_overlay():
    eps, trail = overlay._PEDAL_EPS, overlay._TRAIL_STEER
    got = _call("pedalTag", [
        [[[0, 0.0, 0.5, trail + 0.01]], 0],                          # freno col volante girato
        [[[0, 0.0, 0.5, trail - 0.02]], 0],                          # freno dritto
        [[[0, 0.5, 0.0, 0.0], [1000, 0.0, 0.0, 0.0],
          [2500, eps, eps, 0.3]], 2500],                             # veleggio da 1,5 s
        [[[0, 0.9, 0.0, 0.0]], 0],                                   # gas
        [[], 0],
    ])
    assert got == [["trail", 0], ["", 0], ["coast", 1.5], ["", 0], ["", 0]]


@needs_node
def test_lo_zoom_pista_intera_la_inquadra_tutta():
    bounds = [-500, -200, 500, 200]               # 1000 x 400 m
    f = _call("mapFrame", [[bounds, [10, 10], "all", 400, 300]])[0]
    assert f["cx"] == 0 and f["cz"] == 0
    # Sta tutta, con un margine: la larghezza comanda (1000 m su 400 px).
    assert 0.3 < f["scale"] <= 0.4


@needs_node
def test_lo_zoom_vicino_segue_l_auto():
    bounds = [-500, -200, 500, 200]
    near, close = _call("mapFrame", [[bounds, [123, -45], "near", 400, 300],
                                     [bounds, [123, -45], "close", 400, 300]])
    for f in (near, close):
        assert [f["cx"], f["cz"]] == [123, -45]
    # Il lato corto della tela copre il diametro dichiarato dello zoom.
    assert 300 / near["scale"] == pytest.approx(400)
    assert 300 / close["scale"] == pytest.approx(120)


@needs_node
def test_senza_auto_lo_zoom_vicino_torna_alla_pista_intera():
    bounds = [-500, -200, 500, 200]
    a, b = _call("mapFrame", [[bounds, None, "near", 400, 300],
                              [bounds, None, "all", 400, 300]])
    assert a == b


def test_nella_pagina_ogni_id_e_unico():
    # La tela della mappa si chiamava «t-map» come la casella della mappa
    # motore: `$("t-map")` trovava la casella, e la mappa restava vuota.
    import re
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
            / "tablet.html").read_text(encoding="utf-8")
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)
