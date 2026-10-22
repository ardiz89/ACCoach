"""Il controllo Safari 9: l'iPad 3 del pilota non sa niente di ES2015+.

`tests/safari9.py` e' il controllo; qui si prova che trovi ogni forma vietata,
che non si lasci ingannare da stringhe e commenti, e che i file spediti passino.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from safari9 import TABLET_FILES, safari9_problems

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")


@pytest.mark.parametrize("src", [
    "var f = () => 1;", "let a = 1;", "const a = 1;", "async function f() {}",
    "var a = b ?? c;", "var a = b?.c;", "f(...xs);", "fetch('/x');",
    "document.querySelectorAll('a').forEach(g);", "var s = x.padStart(2);",
    "class A {}", "await x;", "var s = x.padEnd(2);", "Intl.NumberFormat();",
    "Object.entries(o);", "Object.values(o);", "new URLSearchParams(s);",
    "document.getElementsByClassName('a').forEach(g);",
])
def test_checker_catches_each_forbidden_form(src):
    assert safari9_problems(src, "js"), src


def test_checker_ignores_strings_and_comments():
    src = "// let a => 1\nvar s = 'const ?? => ...'; var t = `class ${x}`;"
    assert safari9_problems(src, "js") == []
    # dentro un ${...} il codice e' codice
    assert len(safari9_problems("var t = `${a ?? b}`;", "js")) == 1


def test_checker_allows_the_ternary_with_a_number():
    assert safari9_problems("var a = b?.5:1;", "js") == []
    assert safari9_problems("var a = x.forEach(g); var l = [].forEach.call(n, g);", "js") == []


def test_problems_carry_the_line_number():
    out = safari9_problems("var a = 1;\n\nlet b = 2;", "js")
    assert len(out) == 1 and out[0].startswith("3: ")


@pytest.mark.parametrize("src", [
    ".a{display:grid}", ".a{width:clamp(1px,2px,3px)}", ".a{color:var(--x)}",
    ".a{display:flex;gap:4px}", ".a{width:min(1px,2px)}", ".a{width:max(1px,2px)}",
])
def test_checker_css(src):
    assert len(safari9_problems(src, "css")) == 1, src


def test_checker_css_ignores_comments():
    assert safari9_problems("/* grid */ .a{display:flex}", "css") == []


@pytest.mark.parametrize("name", TABLET_FILES)
def test_shipped_files_pass(name):
    path = _WEB / name
    if not path.exists():
        pytest.skip(name + " non esiste ancora")
    kind = "css" if name.endswith(".css") else "js"
    assert safari9_problems(path.read_text(encoding="utf-8"), kind, name) == []


def test_tablet_files_exist():
    # Senza i file, il controllo qui sopra si salta e passa senza aver guardato.
    for name in ("tablet.js", "tablet.css"):
        assert (_WEB / name).exists(), name


def test_tablet_js_has_no_foreach_at_all():
    # Su una variabile il controllo generico non sa se e' una NodeList: in
    # tablet.js non si rischia, i cicli sono `for`.
    src = "var l = document.querySelectorAll('a'); l.forEach(g);"
    assert safari9_problems(src, "js", "tablet.js")
    assert safari9_problems(src, "js") == []


def test_tablet_js_mutation_is_caught():
    src = (_WEB / "tablet.js").read_text(encoding="utf-8")
    assert safari9_problems(src + "\nvar f = () => 1;\n", "js", "tablet.js")
    assert safari9_problems(src + "\n[].forEach(g);\n", "js", "tablet.js")
    css = (_WEB / "tablet.css").read_text(encoding="utf-8")
    assert safari9_problems(css + "\n.z{display:grid}\n", "css", "tablet.css")


def test_mutation_is_caught():
    src = (_WEB / "i18n.js").read_text(encoding="utf-8") + "\nvar x = () => 1;\n"
    assert safari9_problems(src, "js")


@pytest.mark.skipif(_NODE is None, reason="serve node")
def test_i18n_parses_in_node():
    assert subprocess.run([_NODE, "--check", str(_WEB / "i18n.js")]).returncode == 0
