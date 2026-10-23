"""La CSP sulle pagine della 8778, e l'elenco degli assetti che resta nel gioco.

Una pagina con un buco di escape (il Task 3 ne ha chiusi tre) e' uno script
che gira sulla 8778 e scrive assetti. La CSP e' la seconda cintura: anche se
domani un testo entra nell'HTML senza escape, uno `<script>` iniettato non ha
il nonce e il browser non lo esegue. Regge solo se le pagine stesse non hanno
script inline senza nonce, `onclick=` o `new Function`: per questo qui si
guardano anche i file.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accoach import guard
from accoach.api import create_api
from safari9 import TABLET_FILES, safari9_problems

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")
PAGES = ("/", "/engineer", "/tablet", "/test", "/guida")


@pytest.fixture
def client(tmp_path):
    return TestClient(create_api(tmp_path / "laps", setups_root=tmp_path / "Setups"))


def _nonce(resp) -> str:
    csp = resp.headers.get("content-security-policy", "")
    m = re.search(r"'nonce-([^']+)'", csp)
    assert m, f"nessun nonce nella CSP: {csp!r}"
    return m.group(1)


def _inline_scripts(html: str) -> list[str]:
    """I tag di apertura degli `<script>` senza `src`."""
    return [m.group(0) for m in re.finditer(r"<script\b[^>]*>", html, re.I)
            if "src=" not in m.group(0)]


# --- l'header ---------------------------------------------------------------

def test_csp_is_exactly_the_decided_string():
    assert guard.csp("192.168.1.5:8778", "N0NCE", 8777) == (
        "default-src 'self'; script-src 'self' 'nonce-N0NCE' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self' ws://192.168.1.5:8777 http://192.168.1.5:8777; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


def test_csp_keeps_ipv6_brackets():
    assert "ws://[::1]:9000 http://[::1]:9000" in guard.csp("[::1]:8778", "x", 9000)


@pytest.mark.parametrize("page", PAGES)
def test_pages_carry_the_csp(client, page):
    r = client.get(page)
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "script-src 'self' 'nonce-" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # TestClient manda `Host: testserver`; la porta live e' quella del config.
    assert "ws://testserver:8777" in csp


@pytest.mark.parametrize("page", PAGES)
def test_every_inline_script_has_the_header_nonce(client, page):
    r = client.get(page)
    nonce = _nonce(r)
    for tag in _inline_scripts(r.text):
        assert f'nonce="{nonce}"' in tag, f"{page}: {tag}"


def test_pages_with_inline_scripts_really_have_them(client):
    # Senza questa prova, il test qui sopra passa anche su pagine senza script
    # inline: la lingua scritta da `_serve` e il sommario della guida ci sono.
    assert _inline_scripts(client.get("/").text)
    assert _inline_scripts(client.get("/guida").text)


@pytest.mark.parametrize("page", PAGES)
def test_the_nonce_changes_every_request(client, page):
    assert _nonce(client.get(page)) != _nonce(client.get(page))


def test_connect_src_follows_the_request_host(client):
    r = client.get("/tablet", headers={"host": "localhost:8778"})
    csp = r.headers["content-security-policy"]
    assert "ws://localhost:8777 http://localhost:8777" in csp


def test_connect_src_uses_the_configured_live_port(tmp_path, monkeypatch):
    from accoach import config
    cfg = config.load_config()
    monkeypatch.setattr(cfg.server, "port", 9123)
    monkeypatch.setattr(config, "load_config", lambda *a, **k: cfg)
    c = TestClient(create_api(tmp_path / "laps"))
    assert "ws://testserver:9123" in c.get("/").headers["content-security-policy"]


def test_the_offline_guide_has_no_nonce():
    # La copia aperta dal disco non ha server ne' CSP: niente nonce finto.
    from accoach.guide import render_guide
    html = render_guide("it", standalone=True)
    assert _inline_scripts(html) == ["<script>"]


# --- nosniff e X-Frame-Options su ogni risposta della 8778 -------------------

@pytest.mark.parametrize("path", ["/", "/api/setup/combos", "/static/app.js",
                                  "/non-esiste"])
def test_every_response_has_nosniff_and_deny(client, path):
    r = client.get(path)
    assert r.headers.get("x-content-type-options") == "nosniff", path
    assert r.headers.get("x-frame-options") == "DENY", path


def test_json_responses_have_no_csp_but_have_nosniff(client):
    r = client.get("/api/setup/combos")
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_even_the_guard_refusal_has_nosniff(client):
    r = client.get("/", headers={"host": "evil.example"})
    assert r.status_code == 403
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_the_live_backend_is_untouched():
    # La 8777 parla JSON e WebSocket con i client Python: gli header delle
    # pagine non la riguardano, e non devono rompere nulla.
    from accoach.server import create_app

    class _Motore:
        def tick(self):
            return None

        def close(self):
            pass

    with TestClient(create_app(engine=_Motore(), hz=50)) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert "content-security-policy" not in r.headers
        with c.websocket_connect("/ws"):
            pass


# --- /static non serve le pagine senza CSP --------------------------------------
# Le pagine stanno nella stessa cartella dei loro file e usano percorsi
# /static/... assoluti: /static/engineer.html era la pagina intera, senza CSP.

@pytest.mark.parametrize("name", [
    "engineer.html", "index.html", "tablet.html", "test.html",
    # Windows: maiuscole, punto finale e flusso NTFS aprono lo stesso file.
    "ENGINEER.HTML", "engineer.html.", "engineer.html%20", "engineer.html::$DATA",
])
def test_static_does_not_serve_pages(client, name):
    r = client.get("/static/" + name)
    assert r.status_code == 404, name
    assert "text/html" not in r.headers.get("content-type", ""), name


@pytest.mark.parametrize("name", ["engineer.js", "style.css", "modern.js",
                                  "test_plan.json", "hone_icon.png"])
def test_static_still_serves_assets(client, name):
    assert client.get("/static/" + name).status_code == 200, name


# --- i file serviti ------------------------------------------------------------

def _served_files():
    return sorted(p for p in _WEB.iterdir() if p.suffix in (".html", ".js"))


def test_no_new_function_or_eval_anywhere():
    for p in _served_files():
        src = p.read_text(encoding="utf-8")
        assert "new Function" not in src, p.name
        assert not re.search(r"\beval\s*\(", src), p.name
        assert not re.search(r"set(Timeout|Interval)\s*\(\s*['\"`]", src), p.name


def test_no_inline_handlers_or_javascript_urls_in_html():
    for p in _WEB.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        assert not re.search(r"<[^>]*\son[a-z]+\s*=", html, re.I), p.name
        assert "javascript:" not in html.lower(), p.name
        # Gli script inline li scrive solo il server, col nonce.
        assert _inline_scripts(html) == [], p.name


# --- la prova «pagina completa» senza new Function -----------------------------

def _head(name):
    return (_WEB / name).read_text(encoding="utf-8").split("</head>", 1)[0]


def test_engineer_loads_modern_then_the_gate_first():
    head = _head("engineer.html")
    srcs = re.findall(r'<script src="([^"]+)"', head)
    assert srcs[:2] == ["/static/modern.js", "/static/modern-gate.js"]


def test_modern_js_uses_both_forms_the_full_page_needs():
    # engineer.js scrive `async` e `??`: Safari 10-13 conosce il primo e non
    # il secondo, e una prova del solo `async` lo lascerebbe sulla pagina bianca.
    src = (_WEB / "modern.js").read_text(encoding="utf-8")
    assert "async function" in src and "??" in src
    assert "HONE_MODERN" in src
    # Fallisce il controllo Safari 9 apposta: e' cosi' che la bandierina manca.
    assert safari9_problems(src, "js")
    assert "modern.js" not in TABLET_FILES


def test_gate_and_tablet_pass_safari9():
    for name in ("modern-gate.js", "tablet.js"):
        src = (_WEB / name).read_text(encoding="utf-8")
        assert safari9_problems(src, "js", name) == [], name


def test_gate_redirects_without_the_flag():
    src = (_WEB / "modern-gate.js").read_text(encoding="utf-8")
    assert 'location.replace("/tablet")' in src
    assert "HONE_MODERN" in src


def test_tablet_reads_the_flag_and_loads_modern_js():
    js = (_WEB / "tablet.js").read_text(encoding="utf-8")
    body = js.split("function fullPageWorks", 1)[1].split("}", 1)[0]
    assert "HONE_MODERN" in body
    html = (_WEB / "tablet.html").read_text(encoding="utf-8")
    assert html.index('src="/static/modern.js"') < html.index('src="/static/tablet.js"')


def _run(js):
    out = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


_FAKE = "var window = {}; var location = {replace: function (u) { console.log(u); }};\n"


@pytest.mark.skipif(_NODE is None, reason="node non disponibile")
def test_modern_js_sets_the_flag_on_a_modern_engine():
    src = (_WEB / "modern.js").read_text(encoding="utf-8")
    assert _run(_FAKE + src + "\nconsole.log(window.HONE_MODERN === true);") == "true"


@pytest.mark.skipif(_NODE is None, reason="node non disponibile")
def test_gate_stays_with_the_flag_and_redirects_without():
    gate = (_WEB / "modern-gate.js").read_text(encoding="utf-8")
    assert _run(_FAKE + "window.HONE_MODERN = true;\n" + gate) == ""
    assert _run(_FAKE + gate) == "/tablet"


# --- /api/setup/list resta nelle cartelle del gioco ---------------------------

def _setup_client(tmp_path):
    root = tmp_path / "Setups"
    d = root / "car_a" / "Imola"
    d.mkdir(parents=True)
    (d / "base.json").write_text(json.dumps({"carName": "car_a"}), encoding="utf-8")
    return TestClient(create_api(tmp_path / "laps", setups_root=root))


@pytest.mark.parametrize("params", [
    {"car": "..", "track": "x"},
    {"car": "C:/x", "track": "x"},
    {"car": "car_a", "track": "a/b"},
    {"car": "car_a", "track": "a\\b"},
    {"car": "car_a", "track": "."},
    {"car": "car_a", "track": ".."},
    {"car": "C:", "track": "x"},
])
def test_setup_list_refuses_paths(tmp_path, params):
    c = _setup_client(tmp_path)
    assert c.get("/api/setup/list", params=params).status_code == 400


def test_setup_list_normal_names_unchanged(tmp_path):
    c = _setup_client(tmp_path)
    r = c.get("/api/setup/list", params={"car": "car_a", "track": "Imola"})
    assert r.status_code == 200
    assert [x["name"] for x in r.json()] == ["base"]
    # Un nome con spazi e punti (non `.`/`..`) resta un nome qualunque.
    d = tmp_path / "Setups" / "car_a" / "Red Bull Ring v1.2"
    d.mkdir(parents=True)
    (d / "q.json").write_text("{}", encoding="utf-8")
    r = c.get("/api/setup/list", params={"car": "car_a", "track": "Red Bull Ring v1.2"})
    assert [x["name"] for x in r.json()] == ["q"]
    # Una combinazione che non c'e' resta una lista vuota, non un errore.
    assert c.get("/api/setup/list", params={"car": "car_b", "track": "Monza"}).json() == []


# --- nessuna pagina HTML senza CSP, e niente documentazione automatica ---------
# FastAPI di serie pubblica /docs e /redoc: due pagine HTML che caricano script
# da una CDN, senza la nostra CSP. Sulla 8778 erano una pagina senza cintura, e
# /openapi.json l'elenco di ogni route che scrive. Si spengono su tutte e due
# le app, e qui si prova ogni GET senza parametri, non un elenco scritto a mano:
# la route aggiunta domani ci finisce dentro da sola.

def _get_routes_senza_parametri(app):
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "GET" in methods and "{" not in path:
            yield path


def test_every_html_response_of_the_pages_app_has_the_csp(client):
    percorsi = sorted(set(_get_routes_senza_parametri(client.app)) | set(PAGES))
    assert len(percorsi) > len(PAGES)   # l'elenco viene davvero dalle route
    html_visti = 0
    for path in percorsi:
        r = client.get(path)
        if "text/html" in r.headers.get("content-type", ""):
            html_visti += 1
            assert "script-src 'self' 'nonce-" in r.headers.get(
                "content-security-policy", ""), path
    assert html_visti >= len(PAGES)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json",
                                  "/docs/oauth2-redirect"])
def test_no_auto_docs_on_either_app(client, path):
    from accoach.server import create_app

    class _Motore:
        def tick(self):
            return None

        def close(self):
            pass

    assert client.get(path).status_code == 404, path
    with TestClient(create_app(engine=_Motore(), hz=50)) as live:
        assert live.get(path).status_code == 404, path
