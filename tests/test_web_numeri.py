"""I numeri mostrati al pilota nel report e nella pagina Ingegnere.

Un numero che il pilota legge passa da `fmtNum` (virgola in italiano, spazio
prima dell'unita', mai «-0,00»); il punto resta solo dove il numero non e' un
testo: stili CSS, coordinate del canvas, JSON, e i tempi sul giro («1:47.427»).
Statici sul sorgente, piu' un harness node che esegue i formati veri.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"
_SRC = {n: (WEB / n).read_text(encoding="utf-8") for n in ("app.js", "engineer.js", "test.js")}

# Le sole funzioni dove `.toFixed(` e' ammesso, e perche'.
ALLOWED = {
    "app.js": {
        "fixz": "numero per CSS, attributi e canvas: il punto e' voluto",
        "fmtMs": "tempo sul giro, 1:47.427",
        "fmtSec": "tempo di settore, 34.512",
    },
    "engineer.js": {"fmtN": "ripiego se i18n.js manca"},
    "test.js": {"fmtIt": "la pagina di test e' solo in italiano",
                "round": "dati, non testo"},
}


def _body_arrow_or_fn(src: str, name: str) -> str:
    if f"function {name}(" in src:
        return _body(src, name)
    m = re.search(rf"^\s*const {name} = .*$", src, re.M)
    assert m, name
    return m.group(0)


def _body(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    depth = 0
    for k in range(src.index("{", i), len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if not depth:
                return src[i:k + 1]
    raise AssertionError(name)


def _strip_allowed(fname: str) -> str:
    src = _SRC[fname]
    for name in ALLOWED[fname]:
        src = src.replace(_body_arrow_or_fn(src, name), "")
    return src


@pytest.mark.parametrize("fname", sorted(ALLOWED))
def test_no_raw_tofixed_outside_the_listed_formatters(fname):
    left = [l.strip() for l in _strip_allowed(fname).splitlines() if ".toFixed(" in l]
    assert left == []


@pytest.mark.parametrize("fname", sorted(ALLOWED))
def test_the_listed_formatters_exist_and_are_used(fname):
    for name in ALLOWED[fname]:
        assert f"function {name}(" in _SRC[fname] or f"const {name} =" in _SRC[fname]


_UNIT_GLUED = [
    re.compile(r'\+\s*"(?:s|m|g|°|%|psi|L|km/h)"'),                 # + "s"
    re.compile(r"\}(?:s|m|g|°|%|psi|L|km/h)(?![A-Za-z0-9_])"),      # ${x}s
]


@pytest.mark.parametrize("fname", sorted(ALLOWED))
def test_no_number_glued_to_its_unit(fname):
    bad = []
    for n, line in enumerate(_SRC[fname].splitlines(), 1):
        if "style=" in line or "style." in line or line.lstrip().startswith("//"):
            continue
        if any(p.search(line) for p in _UNIT_GLUED):
            bad.append(f"{fname}:{n}: {line.strip()}")
    assert bad == []


# --- i formati veri, eseguiti ------------------------------------------------

_NODE = shutil.which("node")


def _grab(src: str, name: str) -> str:
    return _body(src, name)


def _run(lang: str, exprs: list[str]) -> list[str]:
    app = _SRC["app.js"]
    i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
    fn = i18n[i18n.index("function fmtNum("):]
    fn = fn[:fn.index("\n  }\n") + 4]
    parts = [f"var window = {{HoneI18n: {{lang: {json.dumps(lang)}}}}};", fn,
             "window.HoneI18n.fmtNum = fmtNum;"]
    for name in ("fixz", "fmtDec", "fmtSecs", "fmtSgn", "fmtPct"):
        parts.append(_grab(app, name))
    parts.append(f"console.log(JSON.stringify([{','.join(exprs)}]));")
    out = subprocess.run([_NODE, "-e", "\n".join(parts)], capture_output=True,
                         text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


EXPRS = ['fmtDec(3.25, 3, "s")', 'fmtSgn(0.5, 2, "s")', 'fmtSgn(-0.5, 2, "s")',
         'fmtSgn(-0.001, 2, "s")', "fmtPct(0.456)", 'fmtDec(85, 0, "°")', 
         'fmtDec(1.5, 1, "m")']


@pytest.mark.skipif(_NODE is None, reason="serve node")
def test_driver_formats_in_italian():
    assert _run("it", EXPRS) == ["3,250 s", "+0,50 s", "−0,50 s", "0,00 s", "46 %",
                                 "85 °", "1,5 m"]


@pytest.mark.skipif(_NODE is None, reason="serve node")
def test_driver_formats_in_english():
    assert _run("en", EXPRS) == ["3.250 s", "+0.50 s", "−0.50 s", "0.00 s", "46 %",
                                 "85 °", "1.5 m"]


@pytest.mark.skipif(_NODE is None, reason="serve node")
@pytest.mark.parametrize("lang,expected", [("it", "0,50 s"), ("en", "0.50 s")])
def test_engineer_page_formats_through_the_shared_rule(lang, expected):
    i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
    fn = i18n[i18n.index("function fmtNum("):]
    fn = fn[:fn.index("\n  }\n") + 4]
    prog = (f"var window = {{HoneI18n: {{lang: {json.dumps(lang)}}}}};\n{fn}\n"
            "window.HoneI18n.fmtNum = fmtNum;\n" + _body(_SRC["engineer.js"], "fmtN") +
            '\nconsole.log(fmtN(0.5, 2, "s"));')
    out = subprocess.run([_NODE, "-e", prog], capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == expected


# `fixz` tiene il punto: va bene per CSS, attributi e coordinate, mai per un
# numero che il pilota legge (proprio cosi' un asse mostrava «-1.5 m» in italiano).
_FIXZ_OK_FORMATTERS = ("fixz", "fmtMs", "fmtSec", "fmtDec", "fmtSecs")
_FIXZ_CSS_LINE = re.compile(r"style=|width|const w = fixz\(")


def test_fixz_is_not_used_for_numbers_the_driver_reads():
    src = _SRC["app.js"]
    for name in _FIXZ_OK_FORMATTERS:
        src = src.replace(_body(src, name), "")
    bad = [l.strip() for l in src.splitlines()
           if "fixz(" in l and not _FIXZ_CSS_LINE.search(l)]
    assert bad == []


@pytest.mark.skipif(_NODE is None, reason="serve node")
@pytest.mark.parametrize("lang,expected", [("it", "24,5 °"), ("en", "24.5 °")])
def test_a_road_temperature_float_is_formatted_not_interpolated(lang, expected):
    # La temperatura dell'asfalto arriva dal server come float: il menu dei giri
    # e la fascia del giro la scrivono con `fmtDec`, mai col punto grezzo.
    app = _SRC["app.js"]
    assert "fmtDec(l.road_temp, 1" in app and "fmtDec(a.review.road_temp, 1" in app
    assert "temp: c.road_temp," not in app
    i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
    fn = i18n[i18n.index("function fmtNum("):]
    fn = fn[:fn.index("\n  }\n") + 4]
    parts = [f"var window = {{HoneI18n: {{lang: {json.dumps(lang)}}}}};", fn,
             "window.HoneI18n.fmtNum = fmtNum;", _body(app, "fixz"), _body(app, "fmtDec"),
             'console.log(fmtDec(24.5, 1, "°"));']
    out = subprocess.run([_NODE, "-e", "\n".join(parts)], capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == expected
