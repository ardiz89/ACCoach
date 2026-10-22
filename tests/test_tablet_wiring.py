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


def _redirect_script() -> str:
    html = (_SRC / "web" / "engineer.html").read_text(encoding="utf-8")
    head = html.split("</head>", 1)[0]
    for m in re.finditer(r"<script>(.*?)</script>", head, re.S):
        if 'location.replace("/tablet")' in m.group(1):
            return m.group(1)
    raise AssertionError("nessuno script di rinvio nel <head> di engineer.html")


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
    html = (_SRC / "web" / "engineer.html").read_text(encoding="utf-8")
    head = html.split("</head>", 1)[0]
    at = head.index('location.replace("/tablet")')
    assert "<script src=" not in head[:at]
    assert "<script src=" in html  # i file veri vengono dopo
    assert safari9_problems(_redirect_script(), "js") == []


@pytest.mark.skipif(_NODE is None, reason="node non disponibile")
def test_redirect_skips_modern_browsers():
    js = ("var location = {replace: function (u) { console.log(u); }};\n"
          + _redirect_script())
    out = subprocess.run([_NODE, "-e", js], capture_output=True, text=True,
                         timeout=20)
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.skipif(_NODE is None, reason="node non disponibile")
def test_redirect_fires_when_async_is_unknown():
    # La prova contraria: se `new Function` rifiuta `async`, il rinvio scatta.
    js = ("var location = {replace: function (u) { console.log(u); }};\n"
          "var NativeFunction = Function;\n"
          "Function = function (body) {\n"
          "  if (/async/.test(body)) throw new SyntaxError('no async');\n"
          "  return NativeFunction.apply(null, arguments);\n"
          "};\n" + _redirect_script())
    out = subprocess.run([_NODE, "-e", js], capture_output=True, text=True,
                         timeout=20)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "/tablet"
