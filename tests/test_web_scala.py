"""Il testo che cresce con lo schermo (spec «La lettura sugli schermi grandi»).

Una sola base (`--fs` sul :root) cresce con la finestra da 14 px (fino a 1600 px)
a 20 px (2880 px); ogni testo e' in rem, ogni larghezza che regge testo pure, e i
caratteri dei canvas passano da `canvasFont`. Statici sul sorgente, piu' un
harness node che esegue `canvasFont`.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"
CSS = ("style.css", "engineer.css", "test.css")
_SRC = {n: (WEB / n).read_text(encoding="utf-8") for n in CSS + ("app.js", "engineer.js", "tour.js")}

CLAMP = "clamp(14px, calc(14px + (100vw - 1600px) * 6 / 1280), 20px)"
MIN_REM = 0.857          # 12 px a base 14


def _outside_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _root_block(css: str) -> str:
    m = re.search(r"(?m)^:root\s*\{(.*?)\n\}", _outside_comments(css), re.S)
    assert m
    return m.group(1)


def _without_root(css: str) -> str:
    # Solo style.css e test.css hanno un :root; engineer.css eredita la base.
    css = _outside_comments(css)
    m = re.search(r"(?m)^:root\s*\{(.*?)\n\}", css, re.S)
    return css.replace(m.group(1), "") if m else css


@pytest.mark.parametrize("fname", ["style.css", "test.css"])
def test_root_carries_the_growing_base(fname):
    root = _root_block(_SRC[fname])
    assert f"--fs: {CLAMP}" in root
    assert "font-size: var(--fs)" in root


@pytest.mark.parametrize("fname", CSS)
def test_no_font_size_in_px_outside_root(fname):
    bad = re.findall(r"font(?:-size)?\s*:[^;}]*\d(?:\.\d+)?px", _without_root(_SRC[fname]))
    assert bad == []


@pytest.mark.parametrize("fname", CSS)
def test_no_font_size_below_12px_at_base_14(fname):
    sizes = [float(v) for v in re.findall(r"font-size\s*:\s*([\d.]+)rem", _without_root(_SRC[fname]))]
    assert sizes and min(sizes) >= MIN_REM


def test_body_font_is_rem():
    assert re.search(r"(?m)^body\s*\{[^}]*font:\s*1rem/1\.4", _SRC["style.css"])


def test_page_width_and_reading_columns_are_rem():
    css = _outside_comments(_SRC["style.css"])
    assert re.search(r"--page:\s*114\.286rem", css)       # 1600 px a base 14
    for sel in (r"\.flow-shell", r"\.session-shell", r"\.pag-shell", r"\.sheet \.vmin-table"):
        m = re.search(sel + r"\s*\{[^}]*max-width:\s*([\d.]+)(\w+)", css)
        assert m and m.group(2) in ("rem", "ch"), sel
    assert not re.search(r"(?<![\w-])(?:min-|max-)?width\s*:\s*[^;}]*\d{3,}px", re.sub(r"@media[^{]*", "", css))


def test_media_queries_stay_in_px():
    # rem in un @media vale il carattere del browser (16 px), non la nostra base.
    for f in CSS:
        assert not re.search(r"@media[^{]*\d(?:rem|em)\b", _outside_comments(_SRC[f])), f


def test_every_canvas_font_goes_through_canvasfont():
    for f in ("app.js", "engineer.js"):
        for n, line in enumerate(_SRC[f].splitlines(), 1):
            if re.search(r"\.font\s*=", line):
                assert "canvasFont(" in line, f"{f}:{n}: {line.strip()}"
    assert "function canvasFont(" in _SRC["app.js"]


def test_no_hand_written_px_in_canvas_font():
    assert not re.search(r"\.font\s*=\s*[\"'`][^;]*\d+px", _SRC["app.js"])


def test_tour_text_is_in_rem():
    assert not re.search(r"font-size:\s*[\d.]+px", _SRC["tour.js"])


_NODE = shutil.which("node")


def _canvas_font(base, px):
    src = _SRC["app.js"]
    i = src.index("function canvasFont(")
    depth = 0
    for k in range(src.index("{", i), len(src)):
        depth += {"{": 1, "}": -1}.get(src[k], 0)
        if src[k] == "}" and not depth:
            fn = src[i:k + 1]
            break
    prog = (f"var document = {{documentElement: {{}}}};"
            f"var getComputedStyle = () => ({{fontSize: '{base}px'}});\nlet _fontBase = 0;\n{fn}\n"
            f"console.log(JSON.stringify(canvasFont({px})));")
    out = subprocess.run([_NODE, "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(_NODE is None, reason="serve node")
def test_canvasfont_scales_with_the_root():
    assert _canvas_font(14, 10) == 10
    assert abs(_canvas_font(18, 10) - 12.9) < 0.06
    assert abs(_canvas_font(20, 12) - 17.1) < 0.06


def test_resize_rereads_the_canvas_base():
    src = _SRC["app.js"]
    i = src.index('window.addEventListener("resize"')
    assert "_fontBase = 0" in src[i:i + 120]


def test_small_has_an_explicit_size():
    # `small` eredita `smaller` (10-11 px a base 14): va dichiarato.
    assert re.search(r"(?m)^small\s*\{[^}]*font-size:\s*0\.857rem", _outside_comments(_SRC["style.css"]))


# --- l'effetto, misurato in un browser vero ---------------------------------

def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


_MEASURE = """() => {
  const small = [];
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = tw.nextNode())) {
    if (!n.textContent.trim() || ['SCRIPT', 'STYLE'].includes(n.parentElement.tagName)) continue;
    const fs = parseFloat(getComputedStyle(n.parentElement).fontSize);
    if (fs < 11.99) small.push([n.parentElement.tagName + '.' + n.parentElement.className, fs]);
  }
  return {body: parseFloat(getComputedStyle(document.body).fontSize), small,
          over: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


@pytest.fixture(scope="module")
def static_site():
    import functools
    import http.server
    import threading

    class H(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            path = path.split("?")[0]
            if path.startswith("/static/"):
                path = path[len("/static"):]
            return str(WEB / path.lstrip("/"))

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.mark.skipif(_chromium() is None, reason="serve playwright")
@pytest.mark.parametrize("page", ["index.html", "engineer.html"])
@pytest.mark.parametrize("width,base", [(1366, 14), (1600, 14), (2560, 18.5), (2880, 20)])
def test_in_a_real_browser_the_base_grows_and_no_text_is_under_12px(static_site, page, width, base):
    with _chromium()() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            pytest.skip("manca chromium")
        pg = b.new_page(viewport={"width": width, "height": 900})
        pg.goto(f"{static_site}/{page}")
        pg.wait_for_timeout(300)
        r = pg.evaluate(_MEASURE)
        b.close()
    assert r["body"] == pytest.approx(base, abs=0.01)
    assert r["small"] == []
    assert r["over"] <= 0


def test_right_edge_labels_are_anchored_not_guessed():
    # `w - 70` e simili indovinano la larghezza del testo: a base 20 esce dal bordo.
    assert not re.search(r"fillText\([^;]*,\s*w - (?:44|62|70|74)\b", _SRC["app.js"])
    assert "function fillTextRight(" in _SRC["app.js"]
    assert _SRC["app.js"].count("fillTextRight(ctx") >= 8


def test_top_labels_follow_the_font_size():
    assert "function labelTop()" in _SRC["app.js"]
    assert not re.search(r"width\) / 2, 11\)", _SRC["app.js"])
