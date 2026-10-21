"""I numeri dei testi: una funzione di formato per lingua, in Python e in JS.

Il pilota legge «0,18 s» in italiano e «0.18 s» in inglese, mai «-0,00», e
l'unità sta sempre a uno spazio dal numero. Prima c'erano tre funzioni (`fmt_s`
in Python, `fmtDec` e `fmtSecs` in app.js) e i numeri composti a runtime
sfuggivano; ora la regola vive in `textfmt.fmt_num` e in `HoneI18n.fmtNum`, e
le altre la chiamano.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from accoach.coaching.howto import fmt_s
from accoach.textfmt import fmt_num

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"
_I18N = (WEB / "i18n.js").read_text(encoding="utf-8")
_APP = (WEB / "app.js").read_text(encoding="utf-8")


def test_italian_uses_the_comma_and_english_the_point():
    assert fmt_num(0.18, 2, "it", "s") == "0,18 s"
    assert fmt_num(0.18, 2, "en", "s") == "0.18 s"
    assert fmt_num(14.0, 0, "it", "m") == "14 m"
    assert fmt_num(165.4, 1, "it") == "165,4"


def test_no_unit_means_no_trailing_space():
    assert fmt_num(3.5, 1, "en") == "3.5"
    assert fmt_num(3.5, 1, "it", None) == "3,5"


def test_a_value_that_rounds_to_nothing_is_zero_never_minus_zero():
    assert fmt_num(-0.001, 2, "it", "s") == "0,00 s"
    assert fmt_num(-0.0, 1, "en") == "0.0"
    assert fmt_num(-0.004, 2, "en") == "0.00"
    assert fmt_num(-0.006, 2, "en") == "−0.01"


def test_an_unknown_language_reads_as_english():
    assert fmt_num(0.5, 1, "de") == "0.5"


def test_fmt_s_is_fmt_num_in_seconds_with_two_decimals():
    assert fmt_s(0.18, "it") == "0,18 s" and fmt_s(0.18, "en") == "0.18 s"
    assert fmt_s(-0.001, "it") == "0,00 s"        # prima stampava «-0,00 s»


# --- lo stesso formato in JS ------------------------------------------------

def test_the_report_numbers_come_from_the_one_function():
    assert "function fmtNum(" in _I18N
    assert "fmtNum: fmtNum" in _I18N
    dec = _APP[_APP.index("function fmtDec("):]
    dec = dec[:dec.index("\n}")]
    assert "fmtNum(" in dec and 'replace(".", ",")' not in dec
    secs = _APP[_APP.index("function fmtSecs("):]
    secs = secs[:secs.index("\n}")]
    assert 'fmtNum(' in secs and '"s"' in secs


def _js(lang: str, calls: list[list]) -> list[str]:
    """Esegue il vero `fmtNum` di i18n.js in node, con la lingua data."""
    src = _I18N
    body = src[src.index("function fmtNum("):]
    body = body[:body.index("\n  }\n") + 4]
    prog = (f"var lang = {json.dumps(lang)};\nvar window = {{HoneI18n: {{lang: {json.dumps(lang)}}}}};\n"
            f"{body}\nconsole.log(JSON.stringify({json.dumps(calls)}.map(a => fmtNum(a[0], a[1], a[2]))));")
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="serve node per eseguire il JS")
@pytest.mark.parametrize("lang,expected", [
    ("it", ["0,18 s", "14 m", "0,00 s", "3,5"]),
    ("en", ["0.18 s", "14 m", "0.00 s", "3.5"]),
])
def test_js_fmt_num_matches_python(lang, expected):
    calls = [[0.18, 2, "s"], [14, 0, "m"], [-0.001, 2, "s"], [3.5, 1, None]]
    assert _js(lang, calls) == expected
    assert expected == [fmt_num(v, d, lang, u) for v, d, u in calls]


def test_the_engineer_page_reads_its_language_from_the_same_place():
    # `fmtNum` guarda `HoneI18n.lang`, che `set()` aggiorna: la pagina Ingegnere
    # carica lo stesso i18n.js e legge la lingua da lì (`LANG`).
    eng = (WEB / "engineer.js").read_text(encoding="utf-8")
    assert "window.HoneI18n.lang" in eng
    fn = _I18N[_I18N.index("function fmtNum("):]
    assert "HoneI18n.lang" in fn[:fn.index("\n  }\n")]
