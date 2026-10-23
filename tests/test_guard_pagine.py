"""Le pagine e il QR portano la chiave del Wi-Fi.

Il guardiano (`accoach.guard`) chiede una chiave a chi non e' il PC. Il tablet
la riceve dal QR dell'hub (`?k=`), il guardiano la ricorda in un cookie, e da li'
le pagine la devono passare a mano alla 8777: il cookie non guarda la porta, ma
una richiesta cross-origin senza credenziali non lo manda (il WebSocket si', e
li' `?k=` e' una cintura in piu'). Qui si prova ogni anello: il QR, le pagine, il viaggio del
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
    assert re.search(r'xhr\("POST", liveUrl\([^\n]*/engineer/applied"\), \{\}, appliedRefused\)', tab)


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


# --- un 401 dentro la pagina Ingegnere ------------------------------------------
# `api()` leggeva lo `statusText` («Unauthorized») perche' il 401 del guardiano
# e' HTML; e le tre chiamate a `/engineer/applied` tacevano.

_API_401 = r"""
const fs = require("fs");
const [i18nPath, engPath, lang, status] = process.argv.slice(2);
global.window = {}; window.HONE_LANG = lang;
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(i18nPath, "utf8"));
const src = fs.readFileSync(engPath, "utf8");
function grab(name) {
  let i = src.indexOf("async function " + name + "(");
  if (i < 0) i = src.indexOf("function " + name + "(");
  if (i < 0) throw new Error("manca " + name);
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
const line = (re) => src.split("\n").find((l) => re.test(l));
eval(line(/^const t = /).replace(/^const /, "var "));
eval(line(/^const LANG = /).replace(/^const /, "var "));
const toasts = [];
var showToast = (m, bad) => toasts.push([m, !!bad]);
var fetch = async () => ({ ok: false, status: Number(status), statusText: "Unauthorized",
                           json: async () => { throw new SyntaxError("html"); } });
eval(grab("api"));
eval(grab("liveRefused"));
(async () => {
  let msg = null;
  try { await api("/api/setup/combos"); } catch (e) { msg = e.message; }
  liveRefused(await fetch());
  liveRefused({});              // il fetch finto dei test vecchi: niente
  console.log(JSON.stringify({ msg, toasts }));
})();
"""


def _api_401(tmp_path, lang, status):
    script = tmp_path / "a.js"
    script.write_text(_API_401, encoding="utf-8")
    r = subprocess.run([_NODE, str(script), str(_WEB / "i18n.js"), str(_WEB / "engineer.js"),
                        lang, str(status)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
@pytest.mark.parametrize("lang,frase", [
    ("it", "Apri HONE dal codice QR dell'hub."),
    ("en", "Open HONE from the hub's QR code."),
])
def test_engineer_says_open_from_the_qr_on_a_401(tmp_path, lang, frase):
    out = _api_401(tmp_path, lang, 401)
    assert out["msg"] == frase
    assert out["toasts"] == [[frase, True]]


@needs_node
def test_engineer_other_errors_keep_their_text(tmp_path):
    out = _api_401(tmp_path, "it", 500)
    assert out["msg"] == "Unauthorized"   # lo statusText finto, non la frase del QR
    assert out["toasts"] == []


def test_the_qr_phrase_is_the_guards_own():
    """La pagina dice la stessa frase della pagina 401 del guardiano."""
    src = (_WEB / "i18n.js").read_text(encoding="utf-8")
    for lang, frase in guard._MESSAGGIO_401.items():
        assert f"{lang}: `{frase}`" in src, lang
