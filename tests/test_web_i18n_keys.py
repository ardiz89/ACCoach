"""The web pages only ask i18n.js for keys it actually has.

A missing key doesn't crash: ``t()`` echoes the key back, so the UI quietly shows
``tour.a3.t`` where a title should be. That silence is how the tour's own buttons
stayed English on an Italian page for months — nobody ever declared them.

So: collect every key the JS asks for, and check the catalogue answers in *both*
languages. Parsed with regexes rather than a JS engine on purpose — the assets are
plain ES5 with a flat ``{key: {en, it}}`` catalogue, and a test that needs a
toolchain to run is a test that stops being run.
"""
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"

# Catalogue entries:  "some.key": { en: `…`, it: `…` },
_ENTRY = re.compile(r'"([\w.]+)"\s*:\s*\{\s*en:', re.M)
# Call sites:  t("some.key")  /  HoneI18n.t("some.key")
_CALL = re.compile(r'\bt\(\s*"([\w.]+)"\s*\)')


def _catalogue() -> dict[str, str]:
    """{key: the source text of its entry} — enough to check both languages exist."""
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in _ENTRY.finditer(src):
        # The entry runs to the closing brace of its object literal; the values are
        # backtick strings, so the first "}" after the match ends it.
        end = src.index("}", m.end())
        out[m.group(1)] = src[m.end():end]
    return out


@pytest.fixture(scope="module")
def cat() -> dict[str, str]:
    return _catalogue()


@pytest.mark.parametrize("asset", ["app.js", "engineer.js"])
def test_every_key_a_page_asks_for_is_declared(asset: str, cat: dict[str, str]) -> None:
    asked = set(_CALL.findall((WEB / asset).read_text(encoding="utf-8")))
    missing = sorted(asked - set(cat))
    assert not missing, f"{asset} asks for keys i18n.js doesn't have: {missing}"


def test_the_tour_buttons_are_declared(cat: dict[str, str]) -> None:
    """tour.js builds these keys by concatenation, so no regex over it would see them."""
    src = (WEB / "tour.js").read_text(encoding="utf-8")
    assert '"tour.btn." + key' in src, "tour.js no longer reads its labels from i18n"
    for name in ("skip", "back", "next", "done", "step"):
        assert f"tour.btn.{name}" in cat


def test_the_catalogue_answers_in_italian_too(cat: dict[str, str]) -> None:
    # English-only entries are the silent half of the bug: the page looks translated
    # everywhere except the one string nobody wrote an Italian for.
    missing = sorted(k for k, body in cat.items() if "it:" not in body)
    assert not missing, f"no Italian for: {missing}"
