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


def _entry_end(src: str, start: int) -> int:
    """Index of the brace that closes this entry's object literal.

    Not "the first `}`", which is what this used to be: the values are backtick
    strings and a string is allowed to contain a brace. The guided flow's steps
    are the first to do it (`Step {n} of {total}`), and under the old rule the
    entry was cut before its Italian, so a fully translated string was reported
    as missing one. Skipping over backtick spans is the whole fix.
    """
    i = start
    while i < len(src):
        c = src[i]
        if c == "`":
            i = src.index("`", i + 1) + 1
            continue
        if c == "}":
            return i
        i += 1
    raise ValueError("unterminated i18n entry")


def _catalogue() -> dict[str, str]:
    """{key: the source text of its entry} — enough to check both languages exist."""
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in _ENTRY.finditer(src):
        out[m.group(1)] = src[m.end():_entry_end(src, m.end())]
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


def test_no_key_is_declared_twice() -> None:
    """In un letterale d'oggetto la seconda dichiarazione vince, in silenzio:
    `ses.none` era dichiarata due volte, e la scheda Sessione senza giri diceva
    la frase delle curve per sessione."""
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    keys = _ENTRY.findall(src)
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"declared twice in i18n.js: {dupes}"


# --- frasi scritte nel codice invece che nel catalogo -----------------------
# «No steering data for this lap.» era un letterale passato a `fillText`: sulla
# pagina in italiano restava in inglese, e nessuna chiave lo dichiarava, quindi
# il controllo qui sopra non poteva vederlo. Si cerca allora dove il testo
# arriva allo schermo (fillText, textContent, innerHTML, innerText, title,
# placeholder) e si guarda ogni stringa letterale del lato destro, tolte quelle
# passate a t()/tf(): una frase di tre parole o più è testo non tradotto.
_SINK = re.compile(
    r"(?:\.fillText\(|\.(?:textContent|innerHTML|innerText|title|placeholder)\s*\+?=)")
_STR = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', re.S)
_T_ARG = re.compile(
    r'\b(?:t|tf|HoneI18n\.t)\(\s*(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`)')
_SENTENCE = re.compile(r"[A-Za-zÀ-ÿ']+(?:[ ,]+[A-Za-zÀ-ÿ']+){2,}")


def _statement_after(src: str, i: int) -> str:
    """Il lato destro fino al `;` (o alla parentesi che chiude), saltando le stringhe."""
    depth, j = 0, i
    while j < len(src):
        c = src[j]
        if c in "\"'`":
            m = _STR.match(src, j)
            if m:
                j = m.end()
                continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                break
        elif c == ";" and depth == 0:
            break
        j += 1
    return src[i:j]


def _literal_sentences(src: str) -> list[tuple[int, str]]:
    found = []
    for m in _SINK.finditer(src):
        rhs = _T_ARG.sub("t(", _statement_after(src, m.end()))
        for s in _STR.finditer(rhs):
            text = re.sub(r"\$\{[^}]*\}", " ", s.group(0)[1:-1])
            text = re.sub(r"<[^>]*>", " ", text)
            hit = _SENTENCE.search(text)
            if hit:
                found.append((src.count("\n", 0, m.start()) + 1, hit.group(0)))
    return found


@pytest.mark.parametrize("asset", ["app.js", "engineer.js"])
def test_no_sentence_reaches_the_screen_outside_the_catalogue(asset: str) -> None:
    found = _literal_sentences((WEB / asset).read_text(encoding="utf-8"))
    assert not found, f"{asset}: frasi scritte nel codice, non da t()/tf(): {found}"


def test_the_sentence_scan_sees_a_literal_and_spares_the_catalogue() -> None:
    # Il controllo qui sopra passa anche se lo scanner è cieco: questo lo tiene onesto.
    assert _literal_sentences('ctx.fillText("No steering data for this lap.", 10, h);')
    assert _literal_sentences("el.innerHTML = `<b>${n}</b> laps to go here`;")
    assert not _literal_sentences('ctx.fillText(t("steer.none"), 10, h / 2);')
    assert not _literal_sentences('el.innerHTML = `<b>${t("a.b")}</b> ` + tf("c.d", { n: 3 });')
