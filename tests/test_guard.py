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

# L'iPad del pilota (iOS 9.3.6) non legge i QR con la fotocamera: la chiave si
# scrive a mano. Sedici caratteri Crockford (niente I L O U, che si confondono
# con 1 e 0 o diventano parolacce), cioe' 80 bit, invece dei 32 di base64.
_CROCKFORD = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_lan_key_persistente_16_crockford_dove_dice_key_path():
    a = guard.lan_key()
    guard._dimentica()
    b = guard.lan_key()
    assert a == b and len(a) == 16
    assert set(a) <= _CROCKFORD
    assert guard.key_path().read_text(encoding="utf-8").strip() == a


def test_lan_key_ogni_installazione_la_sua():
    a = guard.lan_key()
    guard.key_path().unlink()
    guard._dimentica()
    assert guard.lan_key() != a


@pytest.mark.parametrize("vecchia", [
    "x" * 32,                         # il formato di prima (token_urlsafe)
    "",                               # vuoto
    "ABCDEFGHJKMNPQR",                # 15 caratteri
    "ABCDEFGHJKMNPQRSU",              # 17
    "ABCDEFGHJKMNPQ-_",               # fuori alfabeto
])
def test_una_chiave_non_valida_sul_disco_si_rifa(vecchia):
    guard.key_path().parent.mkdir(parents=True, exist_ok=True)
    guard.key_path().write_text(vecchia, encoding="utf-8")
    guard._dimentica()
    k = guard.lan_key()
    assert len(k) == 16 and set(k) <= _CROCKFORD
    assert guard.key_path().read_text(encoding="utf-8").strip() == k
    # nessun file temporaneo lasciato accanto
    assert sorted(p.name for p in guard.key_path().parent.iterdir()) == [
        "lan-key.txt"]


def test_una_chiave_valida_sul_disco_resta():
    guard.key_path().parent.mkdir(parents=True, exist_ok=True)
    guard.key_path().write_text("7K3M9P2QXR4T8VWZ\r\n", encoding="utf-8")
    guard._dimentica()
    assert guard.lan_key() == "7K3M9P2QXR4T8VWZ"


def test_la_chiave_scritta_a_mano_in_minuscolo_passa_e_il_cookie_e_maiuscolo():
    key = guard.lan_key()
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        r = c.get("/x", params={"k": key.lower()})
        assert r.status_code == 200
        assert f"hone_key={key};" in r.headers["set-cookie"]
        assert c.get("/x").status_code == 200
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        assert c.get("/x", headers={"X-HONE-Key": key.lower()}).status_code == 200
        c.cookies.set("hone_key", key.lower())
        assert c.get("/x").status_code == 200


def test_la_chiave_con_trattini_o_lettere_ambigue_passa():
    # Crockford: O si legge 0, I e L si leggono 1, i trattini non contano.
    guard.key_path().parent.mkdir(parents=True, exist_ok=True)
    guard.key_path().write_text("10ABCDEFGHJKMNPQ", encoding="utf-8")
    guard._dimentica()
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        assert c.get("/x", params={"k": "lo-abcd-efgh-jkmn-pq"}).status_code == 200
    # un client nuovo: quello di prima ha gia' il cookie
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET) as c:
        assert c.get("/x", params={"k": "10ABCDEFGHJKMNPR"}).status_code == 401


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


def test_dopo_l_aggiornamento_chi_arriva_secondo_non_butta_la_chiave_nuova(monkeypatch):
    """Le due app trovano la chiave vecchia nello stesso istante. Una la rifa',
    l'altra -- che aveva letto la vecchia un attimo prima -- sposta via il file
    e si ritrova in mano la chiave nuova: deve rimetterla, non farne una terza
    (il tablet avrebbe un QR diverso a seconda di quale app ha risposto)."""
    import os as _os

    p = guard.key_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x" * 32, encoding="utf-8")
    vera = _os.replace
    fatto = []

    def replace_con_l_altro_processo(src, dst):
        if not fatto and str(src) == str(p):
            fatto.append(1)
            vera(str(p) + "", str(p) + ".parked")   # l'altro sposta la vecchia...
            p.write_text("7K3M9P2QXR4T8VWZ", encoding="utf-8")   # ...e scrive la sua
        return vera(src, dst)

    monkeypatch.setattr(guard.os, "replace", replace_con_l_altro_processo)
    guard._dimentica()
    assert guard.lan_key() == "7K3M9P2QXR4T8VWZ"
    assert fatto
    assert p.read_text(encoding="utf-8").strip() == "7K3M9P2QXR4T8VWZ"


# --- la chiave che non si puo' creare --------------------------------------
# Accesso controllato alle cartelle di Windows: Documenti non si scrive, e
# `lan_key()` solleva. Il guardiano non deve rispondere 500 a ogni richiesta:
# il PC entra lo stesso (non porta chiavi), il tablet legge perche' no.

@pytest.fixture
def chiave_impossibile(tmp_path, monkeypatch):
    un_file = tmp_path / "non-una-cartella"
    un_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(guard, "key_path", lambda: un_file / "lan-key.txt")
    guard._dimentica()
    with pytest.raises(OSError):
        guard.lan_key()
    yield


def test_senza_chiave_il_pc_entra_anche_con_k(chiave_impossibile):
    with TestClient(_mini(), base_url="http://127.0.0.1:8778") as c:
        assert c.get("/x").status_code == 200
        assert c.get("/x", params={"k": "7K3M9P2QXR4T8VWZ"}).status_code == 200
        assert c.post("/w", json={}).status_code == 200


@pytest.mark.parametrize("lang,frase", [
    ("en", "HONE can't save the network key on the PC."),
    ("it", "HONE non riesce a salvare la chiave di rete sul PC."),
])
def test_senza_chiave_il_tablet_legge_perche_non_un_500(
        chiave_impossibile, monkeypatch, lang, frase):
    monkeypatch.setattr(guard, "current_language", lambda: lang)
    with TestClient(_mini(), base_url=f"http://{PC_LAN}:8778", client=TABLET,
                    raise_server_exceptions=False) as c:
        for r in (c.get("/x"), c.get("/x", params={"k": "7K3M9P2QXR4T8VWZ"}),
                  c.post("/w", json={})):
            assert r.status_code == 503
            assert frase in r.text
            assert r.headers["content-type"].startswith("text/html")
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(f"ws://{PC_LAN}:8777/ws?k=7K3M9P2QXR4T8VWZ") as s:
                s.receive_text()


# --- dopo un cambio di rete ------------------------------------------------
# Il portatile passa dal Wi-Fi di casa a quello del circuito: il QR nuovo porta
# il nuovo IP, ma la lista in cache (scaduta) e' ancora quella di prima e il
# ricalcolo parte in un thread senza essere aspettato. Il primo colpo dal
# tablet prendeva 403. Con una lista scaduta, prima di dire no si aspetta un
# ricalcolo.

@pytest.fixture
def rete_che_cambia(monkeypatch):
    import time as _t
    indirizzi = {"127.0.0.1", "::1", PC_LAN}
    chiamate = []

    def local_addresses():
        chiamate.append(1)
        _t.sleep(0.2)   # un resolver vero non e' istantaneo
        return set(indirizzi)

    monkeypatch.setattr(netinfo, "local_addresses", local_addresses)
    guard._dimentica()
    guard.allowed_hosts()   # cache piena con la rete di casa
    chiamate.clear()
    return indirizzi, chiamate


def test_il_nuovo_ip_nell_host_passa_al_primo_colpo(rete_che_cambia):
    indirizzi, _chiamate = rete_che_cambia
    indirizzi.add("10.0.0.7")
    guard._invecchia()
    key = guard.lan_key()
    with TestClient(_mini(), base_url="http://10.0.0.7:8778", client=TABLET) as c:
        assert c.get("/x", params={"k": key}).status_code == 200


def test_il_pc_dal_nuovo_ip_resta_locale_al_primo_colpo(rete_che_cambia):
    indirizzi, _chiamate = rete_che_cambia
    indirizzi.add("10.0.0.7")
    guard._invecchia()
    with TestClient(_mini(), base_url="http://127.0.0.1:8778",
                    client=("10.0.0.7", 51000)) as c:
        assert c.get("/x").status_code == 200


def test_con_la_lista_fresca_un_host_estraneo_non_ricalcola(rete_che_cambia):
    _indirizzi, chiamate = rete_che_cambia
    with TestClient(_mini(), base_url="http://evil.example:8778") as c:
        assert c.get("/x").status_code == 403
        assert c.get("/x").status_code == 403
    assert chiamate == []


def test_con_la_lista_scaduta_un_host_estraneo_ricalcola_una_volta(rete_che_cambia):
    _indirizzi, chiamate = rete_che_cambia
    guard._invecchia()
    with TestClient(_mini(), base_url="http://evil.example:8778") as c:
        assert c.get("/x").status_code == 403
        assert c.get("/x").status_code == 403   # ora la lista e' fresca
    assert len(chiamate) == 1
