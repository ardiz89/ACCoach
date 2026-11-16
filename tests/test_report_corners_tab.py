"""La scheda «Curva per curva» del report: la sessione intera, curva per curva.

Statici sul markup e sul sorgente, come `test_web_pagella.py`: la pagina è un
file piatto senza toolchain. La prova vera (Imola, Acque Minerali, i suoi
blocchi e le voci «Una fonte dice») è nel browser.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tono  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "accoach" / "web"
_HTML = (WEB / "index.html").read_text(encoding="utf-8")
_APPJS = (WEB / "app.js").read_text(encoding="utf-8")
_CSS = (WEB / "style.css").read_text(encoding="utf-8")
_CAT = tono.i18n_catalogue()
_CORNERS = {k: v for k, v in _CAT.items() if k.startswith("corners.")}


def _body_of(head: str) -> str:
    assert head in _APPJS, f"manca {head!r} in app.js"
    return _APPJS.split(head, 1)[1].split("\n}", 1)[0]


def _first_group() -> str:
    m = re.search(r'<div class="tab-group"[^>]*data-i18n-label="tabgroup\.today"[^>]*>(.*?)</div>',
                  _HTML, re.S)
    assert m, "il gruppo «Com'è andata oggi» non c'è più"
    return m.group(1)


def test_the_tab_sits_in_the_first_group_right_after_session():
    views = re.findall(r'data-view="([\w-]+)"', _first_group())
    assert "corners" in views
    assert views.index("corners") == views.index("session") + 1
    assert re.search(r'data-view="corners"[^>]*data-i18n="tab.corners"', _HTML)


def test_the_tab_has_its_panel():
    assert 'id="view-corners"' in _HTML


def test_the_tab_label_is_curva_per_curva():
    assert _CAT["tab.corners"] == {"en": "Corner by corner", "it": "Curva per curva"}


def test_every_corners_key_has_both_languages():
    assert len(_CORNERS) >= 20, sorted(_CORNERS)
    missing = sorted(k for k, v in _CORNERS.items() if set(v) != {"en", "it"} or
                     not v["en"].strip() or not v["it"].strip())
    assert not missing, missing


@pytest.mark.parametrize("key", sorted(_CORNERS))
def test_every_italian_corners_string_passes_the_tone_check(key):
    assert tono.violations(_CORNERS[key]["it"], "it") == [], (key, _CORNERS[key]["it"])


@pytest.mark.parametrize("key", sorted(_CORNERS))
def test_the_two_languages_have_the_same_placeholders(key):
    v = _CORNERS[key]
    assert tono.placeholders(v["it"]) == tono.placeholders(v["en"]), key


def test_the_exact_italian_copy():
    it = {k: v["it"] for k, v in _CORNERS.items()}
    for text in ("Quanto e dove perdi", "La tua frenata", "La tua traiettoria",
                 "Cosa dicono le fonti", "Riferimento", "Una fonte dice",
                 "Le fonti non concordano", "Errori che altri segnalano qui",
                 "Una sola tornata valida. Sono i numeri di quel giro.",
                 "Nessun giro valido in questa sessione.",
                 "{n} {n|giro non analizzato|giri non analizzati}."):
        assert text in it.values(), text
    # La dispersione e' max - min: «±» la leggerebbe come meta' dell'intervallo.
    assert it["corners.brake"] == ("{m} m prima del punto più lento, e "
                                   "fra un giro e l'altro cambia di {spread} m.")
    assert _CORNERS["corners.brake"]["en"] == ("{m} m before the slowest point, "
                                               "and it varies by {spread} m from lap to lap.")
    assert not any("±" in v[lg] for v in _CORNERS.values() for lg in ("en", "it"))
    # Le fasi vengono solo dai giri che perdono: la riga lo dice.
    assert it["corners.phases"] == "Mediana per fase, nei giri in cui perdi"
    assert _CORNERS["corners.phases"]["en"] == "Median by phase, on the laps where you lose"
    gears = [it[f"corners.gear.{n}"] for n in range(1, 7)]
    assert gears == ["prima", "seconda", "terza", "quarta", "quinta", "sesta"]
    # «Tu: terza. Una fonte: seconda.» del piano, senza i due punti che il
    # controllo del tono rifiuta.
    assert it["corners.gear.single"] == "Tu in {you}, una fonte in {source}."
    assert it["corners.gear.reference"] == "Tu in {you}, il riferimento in {source}."


def test_the_page_draws_the_tab():
    assert "function renderCorners(" in _APPJS
    assert "async function loadCorners(" in _APPJS
    assert "/api/corners?" in _body_of("async function loadCorners(")


def test_the_tab_is_wired_like_session():
    redraw = _body_of("function redrawCurrentView(")
    assert 'VIEW === "corners"' in redraw
    reload_ = _body_of("function reloadViewData(")
    assert 'VIEW === "corners"' in reload_


def test_no_braking_board_is_ever_a_target():
    low = _APPJS.lower()
    assert "frena ai" not in low and "brake at the" not in low
    for v in _CORNERS.values():
        assert "frena ai" not in v["it"].lower() and "brake at the" not in v["en"].lower()


def test_every_api_string_is_escaped():
    body = _body_of("function renderCorners(") + "".join(
        _body_of(f"function {name}(") for name in
        ("cpcCorner", "cpcSourceItem", "cpcDisputedItem", "cpcQuotes"))
    # Le stringhe che arrivano dalle fonti o dal backend passano da `esc`.
    for field in ("s.quote", "c.name", "c.cause_message", "it.reason"):
        assert f"esc({field})" in body, field


def test_a_link_is_only_http_and_opens_in_a_new_tab():
    body = _body_of("function cpcLink(")
    assert "https?:" in body or "http://" in body
    assert "t=" in body and "Math.floor" in body
    quotes = _body_of("function cpcQuotes(")
    assert 'target="_blank"' in quotes and 'rel="noopener"' in quotes


def test_una_fonte_dice_is_never_styled_as_a_reference():
    # La voce singola ha il colore del testo; il riferimento il suo accento.
    m = re.search(r"\.cpc-src\.single\s*\{([^}]*)\}", _CSS)
    assert m, "manca la regola di .cpc-src.single"
    assert "var(--text)" in m.group(1)
    for token in ("--cyan", "--adv", "--green", "--amber"):
        assert token not in m.group(1)


def test_the_guides_describe_the_tab():
    assert "Curva per curva" in (ROOT / "GUIDA.md").read_text(encoding="utf-8")
    assert "Corner by corner" in (ROOT / "docs" / "FAQ.md").read_text(encoding="utf-8")


def _flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def test_una_fonte_dice_is_what_the_check_did_not_confirm():
    # Il gruppo puo' avere due autori: non e' «un autore solo», e' quello che
    # il controllo non ha confermato, col numero di autori accanto.
    guida = _flat(ROOT / "GUIDA.md")
    faq = _flat(ROOT / "docs" / "FAQ.md")
    assert "un autore solo" not in guida
    assert "a single author said" not in faq
    assert ("**Una fonte dice** è quello che il controllo sulle fonti non ha "
            "confermato, anche quando lo dice più di un autore.") in guida
    assert ("**One source says** is what the check against the sources didn't "
            "confirm, even when more than one author says it.") in faq
    assert "quanti autori lo dicono" in guida
    assert "how many authors say it" in faq
