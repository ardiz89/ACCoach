"""Le pagine e il QR portano la chiave del Wi-Fi.

Il guardiano (`accoach.guard`) chiede una chiave a chi non e' il PC. Il tablet
la riceve dal QR dell'hub (`?k=`), il guardiano la ricorda in un cookie, e da li'
le pagine la devono passare a mano alla 8777: il cookie della 8778 non viaggia
con una richiesta cross-origin senza credenziali, e il WebSocket di un browser
non accetta header. Qui si prova ogni anello: il QR, le pagine, il viaggio del
tablet da `/tablet?k=` a `/engineer` col solo cookie, e le scritture verso il
motore che il guardiano accetta solo in JSON.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accoach import guard, netinfo
from accoach.api import create_api
from accoach.server import create_app
from safari9 import TABLET_FILES, safari9_problems

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="node non installato")

TABLET = ("192.168.1.50", 51000)
PC_LAN = "192.168.1.23"
CASA = f"http://{PC_LAN}:8778"


@pytest.fixture(autouse=True)
def _rete_finta(monkeypatch):
    monkeypatch.setattr(netinfo, "lan_ip", lambda: PC_LAN)
    guard._dimentica()
    yield


# --- il QR ---------------------------------------------------------------

def test_device_urls_with_key_end_with_k():
    urls = netinfo.device_urls(8778, ip="192.168.1.23", key="abc")
    assert urls == {
        "report": "http://192.168.1.23:8778/?k=abc",
        "engineer": "http://192.168.1.23:8778/engineer?k=abc",
        "tablet": "http://192.168.1.23:8778/tablet?k=abc",
        "test": "http://192.168.1.23:8778/test?k=abc",
    }


def test_device_urls_without_key_unchanged():
    assert netinfo.device_urls(8778, ip="192.168.1.23")["tablet"] == \
        "http://192.168.1.23:8778/tablet"


# --- le pagine ------------------------------------------------------------

_PAGES = {"engineer.js": "WS_PORT", "tablet.js": "WS_PORT", "test.js": "LIVE_PORT"}


@pytest.mark.parametrize("name,port", sorted(_PAGES.items()))
def test_every_live_url_goes_through_honelive(name, port):
    src = (_WEB / name).read_text(encoding="utf-8")
    usi = [ln for ln in src.splitlines()
           if port in ln and not re.search(r"\b(var|const|let)\s+" + port + r"\b", ln)]
    # Senza almeno un uso il controllo passerebbe senza aver guardato niente.
    assert usi, name
    for ln in usi:
        assert "liveUrl(" in ln, (name, ln)
    # E `liveUrl` e' la porta verso `window.honeLive` di lankey.js, non un
    # nome che restituisce l'URL com'era.
    assert re.search(r"liveUrl\b[^\n]*window\.honeLive\(", src), name


@pytest.mark.parametrize("page,script", [
    ("engineer.html", "engineer.js"), ("tablet.html", "tablet.js"), ("test.html", "test.js")])
def test_pages_load_lankey_before_their_script(page, script):
    html = (_WEB / page).read_text(encoding="utf-8")
    lk = html.find('<script src="/static/lankey.js"></script>')
    own = html.find(f'<script src="/static/{script}"></script>')
    assert lk != -1 and own != -1 and lk < own, page


def test_engineer_applied_posts_send_json():
    src = (_WEB / "engineer.js").read_text(encoding="utf-8")
    # Le chiamate, non i commenti che nominano l'endpoint.
    chiamate = [m.start() for m in re.finditer(r"fetch\([^\n]*/engineer/applied", src)]
    assert len(chiamate) == 3
    for at in chiamate:
        tratto = src[at:at + 200]
        assert '"Content-Type": "application/json"' in tratto, tratto
        assert 'body: "{}"' in tratto, tratto
    tab = (_WEB / "tablet.js").read_text(encoding="utf-8")
    # Il corpo `{}` e' anche quello che fa mettere a `xhr` il Content-Type.
    assert re.search(r'xhr\("POST", liveUrl\([^\n]*/engineer/applied"\), \{\}, null\)', tab)


def test_no_write_without_json_in_pages():
    """Ogni scrittura delle pagine dichiara JSON, se no il guardiano dice 415."""
    for name in ("app.js", "engineer.js", "test.js"):
        src = (_WEB / name).read_text(encoding="utf-8")
        for m in re.finditer(r'method:\s*"(POST|PUT|DELETE|PATCH)"', src):
            tratto = src[m.start():m.start() + 120]
            assert "application/json" in tratto, (name, tratto)
    i18n = (_WEB / "i18n.js").read_text(encoding="utf-8")
    for m in re.finditer(r'\.open\("(POST|PUT|DELETE|PATCH)"', i18n):
        assert "application/json" in i18n[m.start():m.start() + 160]


def test_lankey_passes_safari9():
    assert "lankey.js" in TABLET_FILES
    src = (_WEB / "lankey.js").read_text(encoding="utf-8")
    assert safari9_problems(src, "js", "lankey.js") == []
    # ES3 vero: niente template string ne' lookbehind (fuori dai commenti).
    codice = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)
    assert "`" not in codice and "(?<" not in codice


_LANKEY = r"""
var fs = require("fs");
var window = {};
var document = {cookie: process.argv[2]};
eval(fs.readFileSync(process.argv[1], "utf8"));
process.stdout.write(JSON.stringify([
  window.honeLive("ws://pc:8777/ws"),
  window.honeLive("http://pc:8777/engineer/applied?x=1")]));
"""


@needs_node
@pytest.mark.parametrize("cookie,attesi", [
    ("", ["ws://pc:8777/ws", "http://pc:8777/engineer/applied?x=1"]),
    ("a=1; hone_key=Ab-_9; b=2",
     ["ws://pc:8777/ws?k=Ab-_9", "http://pc:8777/engineer/applied?x=1&k=Ab-_9"]),
    ("hone_key=Zz", ["ws://pc:8777/ws?k=Zz", "http://pc:8777/engineer/applied?x=1&k=Zz"]),
    # Un cookie che finisce come il nostro non e' il nostro.
    ("xhone_key=no", ["ws://pc:8777/ws", "http://pc:8777/engineer/applied?x=1"]),
])
def test_honelive_reads_the_cookie(cookie, attesi):
    r = subprocess.run([_NODE, "-e", _LANKEY, str(_WEB / "lankey.js"), cookie],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == attesi


# --- il viaggio del tablet (Review Focus 1) --------------------------------

def test_tablet_from_qr_then_engineer_with_cookie_only(tmp_path):
    key = guard.lan_key()
    c = TestClient(create_api(laps_dir=tmp_path), client=TABLET)
    assert c.get("/engineer").status_code == 401   # senza QR non si entra
    r = c.get(f"/tablet?k={key}")
    assert r.status_code == 200
    assert c.cookies.get(guard.COOKIE) == key
    # Il link «Pagina completa» non porta `k`: basta il cookie.
    assert c.get("/engineer").status_code == 200


def test_tablet_reaches_the_live_port_with_the_key():
    class _Motore:
        applied = 0

        def tick(self):
            return None

        def close(self):
            pass

        def mark_setup_applied(self):
            self.applied += 1

    eng = _Motore()
    c = TestClient(create_app(engine=eng, hz=50), client=TABLET)
    key = guard.lan_key()
    hdr = {"Content-Type": "application/json", "Origin": CASA}
    # Senza chiave il motore non si avvisa; con `?k=` (quello di honeLive) si.
    assert c.post("/engineer/applied", content="{}", headers=hdr).status_code == 401
    r = c.post(f"/engineer/applied?k={key}", content="{}", headers=hdr)
    assert r.status_code == 200 and eng.applied == 1
    # Il corpo vuoto di oggi cade: e' per questo che le pagine mandano `{}`.
    assert c.post(f"/engineer/applied?k={key}", headers={"Origin": CASA}).status_code == 415


def test_the_json_post_preflight_from_the_tablet_passes():
    """`Content-Type: application/json` verso un'altra porta fa partire un
    preflight che prima non c'era: se il CORS della 8777 lo rifiuta, il POST
    vero non parte e l'ingegnere ripropone la stessa modifica per sempre."""
    c = TestClient(create_app(engine=None, hz=50), client=TABLET)
    r = c.options(f"/engineer/applied?k={guard.lan_key()}", headers={
        "Origin": CASA, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == CASA
