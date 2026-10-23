"""Il guardiano dei server: Host, chiave per il Wi-Fi, scritture solo JSON da casa.

Quattro buchi trovati in revisione: nessun controllo dell'Host (DNS
rebinding), nessuna chiave per i dispositivi in rete, CSRF sulle POST JSON,
CORS `*` sul backend dal vivo. Ogni caso qui si prova contro una app minima e
contro le due app vere, perche' un middleware che non e' montato non protegge
niente anche se i suoi test sono verdi.
"""
from __future__ import annotations

import pytest
from fastapi import Body, FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from accoach import guard, netinfo
from accoach.api import create_api
from accoach.server import create_app

TABLET = ("192.168.1.50", 51000)
PC_LAN = "192.168.1.23"
PAGINE = 8778


@pytest.fixture(autouse=True)
def _rete_finta(monkeypatch):
    # L'IP di rete del PC lo decide il test, non la scheda di rete di chi
    # lancia la suite.
    monkeypatch.setattr(netinfo, "lan_ip", lambda: PC_LAN)
    guard._dimentica()
    yield


def _mini() -> FastAPI:
    app = FastAPI()

    @app.get("/x")
    def x() -> dict:
        return {"ok": True}

    @app.post("/w")
    def w(body: dict = Body(...)) -> dict:
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        await sock.send_text("ciao")
        await sock.close()

    app.add_middleware(guard.GuardMiddleware, page_port=PAGINE)
    return app


class _Motore:
    def __init__(self):
        self.applied = 0

    def tick(self):
        return None

    def close(self):
        pass

    def mark_setup_applied(self):
        self.applied += 1


def _apps(tmp_path):
    return {
        "mini": _mini(),
        "api": create_api(laps_dir=tmp_path),
        "server": create_app(engine=_Motore(), hz=50),
    }


_GET = {"mini": "/x", "api": "/", "server": "/health"}
_POST = {"mini": "/w", "api": "/api/corner-name", "server": "/engineer/applied"}


# --- Host -------------------------------------------------------------------

@pytest.mark.parametrize("nome", ["mini", "api", "server"])
def test_host_estraneo_403_su_get_post_e_websocket(tmp_path, nome):
    app = _apps(tmp_path)[nome]
    with TestClient(app, base_url="http://evil.example:8778") as c:
        r = c.get(_GET[nome])
        assert r.status_code == 403 and "host not allowed" in r.text
        r = c.post(_POST[nome], json={})
        assert r.status_code == 403
        # `websocket_connect` non usa `base_url`: l'Host va nell'URL.
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("ws://evil.example:8777/ws") as s:
                s.receive_text()


def test_host_con_porta_e_localhost_passano():
    with TestClient(_mini(), base_url="http://localhost:8778") as c:
        assert c.get("/x").status_code == 200
    with TestClient(_mini(), base_url="http://127.0.0.1:1234") as c:
        assert c.get("/x").status_code == 200
    # Il TestClient non regge un IPv6 in `base_url`: la parte che conta, il
    # nome senza porta, si prova da sola.
    assert guard._host_name("[::1]:8778") == "[::1]"
    assert guard._host_name("LocalHost:8778") == "localhost"
    assert "[::1]" in guard.allowed_hosts()


# --- la chiave --------------------------------------------------------------

@pytest.mark.parametrize("nome", ["mini", "api", "server"])
def test_tablet_senza_chiave_401_poi_con_chiave_passa(tmp_path, nome):
    app = _apps(tmp_path)[nome]
    key = guard.lan_key()
    with TestClient(app, base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        r = c.get(_GET[nome])
        assert r.status_code == 401
        assert "Open HONE from the hub's QR code." in r.text

        r = c.get(_GET[nome], params={"k": key})
        assert r.status_code == 200
        sc = r.headers["set-cookie"]
        assert f"hone_key={key}" in sc and "SameSite=Lax" in sc
        assert "httponly" not in sc.lower()

        # il cookie e' rimasto nel client: basta lui
        assert c.get(_GET[nome]).status_code == 200


def test_tablet_con_header_passa_con_chiave_sbagliata_no():
    key = guard.lan_key()
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        assert c.get("/x", headers={"X-HONE-Key": key}).status_code == 200
        assert c.get("/x", headers={"X-HONE-Key": "x" * 32}).status_code == 401
        assert c.get("/x", params={"k": "sbagliata"}).status_code == 401
        c.cookies.set("hone_key", "sbagliata")
        assert c.get("/x").status_code == 401


def test_401_nella_lingua_del_pilota(monkeypatch):
    monkeypatch.setattr(guard, "current_language", lambda: "it")
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        r = c.get("/x")
    assert r.status_code == 401
    assert "Apri HONE dal codice QR dell" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_il_pc_dal_suo_ip_di_rete_non_porta_chiavi():
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778",
                    client=(PC_LAN, 51000)) as c:
        assert c.get("/x").status_code == 200


def test_ipv4_mappato_e_locale():
    assert guard.is_local_client("::ffff:127.0.0.1")
    assert not guard.is_local_client("192.168.1.50")
    assert not guard.is_local_client(None)


def test_options_da_tablet_senza_chiave_non_401():
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        r = c.options("/w", headers={
            "Origin": f"http://{PC_LAN}:8778",
            "Access-Control-Request-Method": "POST"})
    assert r.status_code != 401


# --- le scritture -----------------------------------------------------------

def test_post_solo_json_e_solo_dalle_pagine():
    with TestClient(_mini(), base_url="http://127.0.0.1:8778") as c:
        assert c.post("/w", content=b"{}").status_code == 415
        assert c.post("/w", content=b"{}",
                      headers={"Content-Type": "text/plain"}).status_code == 415
        assert c.post("/w", json={}).status_code == 200
        assert c.post("/w", json={},
                      headers={"Origin": "http://evil.example"}).status_code == 403
        assert c.post("/w", json={},
                      headers={"Origin": "http://127.0.0.1:8778"}).status_code == 200
        assert c.post("/w", json={},
                      headers={"Origin": "http://127.0.0.1:9999"}).status_code == 403
        assert c.post("/w", json={}, headers={
            "Content-Type": "application/json; charset=utf-8"}).status_code == 200


# --- WebSocket --------------------------------------------------------------

def test_websocket_origin_estraneo_rifiutato_senza_origin_accettato():
    with TestClient(_mini(), base_url="http://127.0.0.1:8777") as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(
                    "/ws", headers={"Origin": "http://evil.example"}) as s:
                s.receive_text()
        with c.websocket_connect("/ws") as s:
            assert s.receive_text() == "ciao"
        with c.websocket_connect(
                "/ws", headers={"Origin": "http://127.0.0.1:8778"}) as s:
            assert s.receive_text() == "ciao"


def test_websocket_dal_tablet_vuole_la_chiave():
    key = guard.lan_key()
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8777", client=TABLET) as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(f"ws://{PC_LAN}:8777/ws") as s:
                s.receive_text()
        with c.websocket_connect(f"ws://{PC_LAN}:8777/ws?k={key}") as s:
            assert s.receive_text() == "ciao"


# --- la 8777 vera -----------------------------------------------------------

def test_engineer_applied_da_sito_estraneo_non_arriva_al_motore():
    m = _Motore()
    with TestClient(create_app(engine=m, hz=50),
                    base_url="http://127.0.0.1:8777") as c:
        r = c.post("/engineer/applied", json={},
                   headers={"Origin": "http://evil.example"})
        assert r.status_code == 403
        assert m.applied == 0
        r = c.post("/engineer/applied", json={},
                   headers={"Origin": "http://127.0.0.1:8778"})
        assert r.status_code == 200 and m.applied == 1


def test_cors_8777_non_e_piu_asterisco():
    with TestClient(create_app(engine=_Motore(), hz=50),
                    base_url="http://127.0.0.1:8777") as c:
        r = c.options("/engineer/applied", headers={
            "Origin": "http://127.0.0.1:8778",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-hone-key"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:8778"
        r = c.options("/engineer/applied", headers={
            "Origin": "http://127.0.0.1:9999",
            "Access-Control-Request-Method": "POST"})
        assert r.headers.get("access-control-allow-origin") != "*"
        assert "access-control-allow-origin" not in r.headers


# --- la chiave sul disco ----------------------------------------------------

def test_lan_key_persistente_lunga_32_dove_dice_key_path():
    a = guard.lan_key()
    guard._dimentica()
    b = guard.lan_key()
    assert a == b and len(a) == 32
    assert guard.key_path().read_text(encoding="utf-8").strip() == a


# --- giro 1 della revisione -------------------------------------------------

def test_un_sito_sulla_porta_8778_non_legge_health():
    """Il CORS ammette `http://<qualunque>:8778`: senza un controllo dell'Origin
    anche sulle letture, un sito ospitato altrove sulla porta 8778 leggeva
    `/health` dal browser del PC (che e' locale e non porta chiavi)."""
    evil = "http://evil.example:8778"
    with TestClient(create_app(engine=_Motore(), hz=50),
                    base_url="http://127.0.0.1:8777") as c:
        r = c.get("/health", headers={"Origin": evil})
        assert r.headers.get("access-control-allow-origin") != evil
        assert r.status_code == 403
        r = c.options("/health", headers={
            "Origin": evil, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") != evil
        assert r.status_code == 403

        buona = "http://127.0.0.1:8778"
        r = c.get("/health", headers={"Origin": buona})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == buona
        r = c.options("/health", headers={
            "Origin": buona, "Access-Control-Request-Method": "GET"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == buona


def test_i_client_python_passano_da_127_senza_origin_ne_chiave():
    """L'overlay (QWebSocket) e il pannello dell'hub (GET /health): locali,
    senza Origin e senza chiave. Provato col loro IP vero, non col nome
    `testclient` che la conftest ammette per comodita'."""
    app = create_app(engine=_Motore(), hz=50)
    with TestClient(app, base_url="http://127.0.0.1:8777",
                    client=("127.0.0.1", 5000)) as c:
        assert c.get("/health").status_code == 200
        with c.websocket_connect("ws://127.0.0.1:8777/ws"):
            pass


def test_un_resolver_lento_non_ferma_le_richieste(monkeypatch):
    """`local_addresses` puo' metterci secondi dietro una VPN, e la 8777
    trasmette a 15 Hz sullo stesso loop: con una cache gia' piena il ricalcolo
    va fuori dal loop e intanto vale quella vecchia."""
    import threading
    import time as _t

    guard.allowed_hosts()   # cache piena
    guard._invecchia()      # ...e scaduta
    via = threading.Event()
    chiamate = []

    def lento():
        chiamate.append(1)
        via.wait(5.0)
        return {"127.0.0.1", "::1", PC_LAN}

    monkeypatch.setattr(netinfo, "local_addresses", lento)
    try:
        with TestClient(_mini(), base_url="http://127.0.0.1:8778") as c:
            t0 = _t.monotonic()
            assert c.get("/x").status_code == 200
            assert c.get("/x").status_code == 200
            assert _t.monotonic() - t0 < 2.0
            # liberato dentro il `with`: all'uscita il TestClient aspetta i
            # suoi thread, e qui si misura la richiesta, non la chiusura
            via.set()
    finally:
        via.set()
    # un ricalcolo solo, anche con due richieste mentre era in corso
    assert len(chiamate) <= 1
