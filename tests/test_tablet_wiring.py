"""Il filo fra il resto dell'app e la vista tablet: il QR, il preferito vecchio.

Il QR del pannello In pista deve portare a `/tablet`; e un browser che non sa
leggere `async` (Safari 9) che apre ancora il vecchio `/engineer` ci arriva da
solo, senza che il pilota debba sapere perche' la pagina e' rimasta bianca.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from accoach import netinfo
from safari9 import safari9_problems

_SRC = Path(__file__).resolve().parent.parent / "src" / "accoach"
_NODE = shutil.which("node")


def _web(name: str) -> str:
    return (_SRC / "web" / name).read_text(encoding="utf-8")


def _head_scripts() -> list[str]:
    head = _web("engineer.html").split("</head>", 1)[0]
    return re.findall(r'<script src="([^"]+)"', head)


def _node(js: str) -> str:
    out = subprocess.run([_NODE, "-e", js], capture_output=True, text=True,
                         timeout=20)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


# Il finto browser: una `window` e un `location` che stampa dove si va.
_FINTO = ("var window = {};\n"
          "var location = {replace: function (u) { console.log(u); }};\n")


def test_device_urls_has_tablet():
    urls = netinfo.device_urls(8778, ip="192.168.1.23")
    assert urls["tablet"] == "http://192.168.1.23:8778/tablet"
    assert urls["report"] == "http://192.168.1.23:8778/"
    assert urls["engineer"] == "http://192.168.1.23:8778/engineer"
    assert urls["test"] == "http://192.168.1.23:8778/test"


def test_qr_points_to_tablet():
    src = (_SRC / "livepanel_ui.py").read_text(encoding="utf-8")
    assert 'urls["tablet"]' in src
    assert 'urls["engineer"]' not in src


def test_engineer_redirects_old_browsers():
    # La prova e' la prima cosa del <head>: prima di qualunque altro script,
    # se no un browser vecchio si ferma su engineer.js e resta bianco. Niente
    # script inline: la CSP delle pagine non li lascia passare senza nonce.
    assert _head_scripts()[:2] == ["/static/modern.js", "/static/modern-gate.js"]
    assert "<script src=" in _web("engineer.html").split("</head>", 1)[1]
    assert safari9_problems(_web("modern-gate.js"), "js") == []
    assert 'location.replace("/tablet")' in _web("modern-gate.js")


@pytest.mark.skipif(_NODE is None, reason="node non disponibile")
def test_redirect_skips_modern_browsers():
    assert _node(_FINTO + _web("modern.js") + "\n" + _web("modern-gate.js")) == ""


@pytest.mark.skipif(_NODE is None, reason="node non disponibile")
def test_redirect_fires_when_modern_js_does_not_parse():
    # La prova contraria: un browser che non analizza modern.js non esegue
    # nemmeno la riga della bandierina, ed e' come se il file non ci fosse.
    assert _node(_FINTO + _web("modern-gate.js")) == "/tablet"


def test_the_probe_covers_both_forms_the_full_page_uses():
    # engineer.js scrive `async` e `??`: Safari 10-13 conosce il primo e non
    # il secondo, e una prova del solo `async` lo lascerebbe sulla pagina bianca.
    # Tutte e due nello stesso file della bandierina: un errore di sintassi
    # ferma il file intero, quindi la bandierina si alza solo se passano entrambe.
    src = _web("modern.js")
    assert "async function" in src and "??" in src
    assert "window.HONE_MODERN = true" in src


def test_tablet_hides_the_full_page_link_with_the_same_probe():
    # Il link «Pagina completa» si spegne dove /engineer rimanderebbe indietro:
    # la regola e' una sola, quindi la stessa bandierina dallo stesso file.
    tablet = _web("tablet.js")
    body = tablet.split("function fullPageWorks", 1)[1].split("}", 1)[0]
    assert "window.HONE_MODERN" in body
    assert "window.HONE_MODERN" in _web("modern-gate.js")
    html = _web("tablet.html")
    assert html.index('src="/static/modern.js"') < html.index('src="/static/tablet.js"')
