"""Le tre superfici che spiegano HONE devono dire la stessa cosa dell'app.

Wizard di primo avvio, visita guidata nel browser, guida scritta. Nessuna delle
tre aveva un proprietario: si aggiornavano quando qualcuno se ne ricordava, e in
48 ore di lavoro sul prodotto nessuno se n'era ricordato. Questi test rendono
almeno le incoerenze meccaniche impossibili da reintrodurre in silenzio.
"""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from accoach.i18n import t

_ROOT = Path(__file__).resolve().parent.parent
_GUIDA = (_ROOT / "GUIDA.md").read_text(encoding="utf-8")
_FAQ = (_ROOT / "docs" / "FAQ.md").read_text(encoding="utf-8")
_APPJS = (_ROOT / "src" / "accoach" / "web" / "app.js").read_text(encoding="utf-8")
_I18NJS = (_ROOT / "src" / "accoach" / "web" / "i18n.js").read_text(encoding="utf-8")


# --- il wizard parla la lingua scelta --------------------------------------

_WIZ = ("wiz.title", "wiz.sub", "wiz.dont_show", "wiz.open_guide", "wiz.go",
        "wiz.s1", "wiz.s2", "wiz.s3", "wiz.s4", "wiz.s5")


@pytest.mark.parametrize("key", _WIZ)
@pytest.mark.parametrize("lang", ("en", "it"))
def test_the_first_screen_is_translated(key, lang):
    """Era interamente hardcoded in inglese: la PRIMA cosa che vede un nuovo
    utente ignorava la lingua che aveva appena scelto."""
    assert t(key, lang=lang) != key


def test_the_wizard_has_no_hardcoded_english_left():
    src = (_ROOT / "src" / "accoach" / "launcher.py").read_text(encoding="utf-8")
    block = src[src.index("class GettingStarted"):src.index("def _guide_path")]
    for phrase in ("Welcome to HONE", "Don't show this again", "Get started",
                   "Open full guide"):
        assert phrase not in block, f"stringa fissa rimasta: {phrase!r}"


# --- la guida descrive l'app di oggi ---------------------------------------

def test_the_guide_describes_the_hub_not_the_old_launcher():
    """Il passo 3 diceva «si apre il Launcher, una finestra con un pulsante per
    ogni funzione». Da luglio è un hub con sei sezioni: è la prima istruzione che
    un nuovo utente esegue, e descriveva un'altra applicazione."""
    assert "hub" in _GUIDA
    assert not re.search(r"Si apre il \*\*Launcher\*\*", _GUIDA)
    assert "Nel Launcher premi" not in _GUIDA


def test_the_guide_calls_the_product_by_its_name():
    """La finestra dice HONE, la guida diceva ACCoach."""
    assert _GUIDA.startswith("# Guida a HONE")
    # Il percorso dei giri su disco resta ACCoach: è la cartella vera.
    stray = [ln for ln in _GUIDA.splitlines()
             if "ACCoach" in ln and "Documenti/ACCoach/laps" not in ln]
    assert not stray, f"nome vecchio rimasto: {stray}"


def test_the_faq_points_at_the_button_not_only_the_command():
    """Il bottone di import è arrivato e la FAQ mandava ancora al terminale."""
    assert "Import a PRO reference lap" in _FAQ


# --- la visita guidata conosce le novità -----------------------------------

def _tour_keys() -> set[str]:
    return set(re.findall(r't\("(tour\.a\d+\.[tx])"\)', _APPJS))


def test_every_tour_step_has_its_text_in_both_languages():
    for key in _tour_keys():
        assert f'"{key}"' in _I18NJS, f"passo del tour senza testo: {key}"
        line = _I18NJS[_I18NJS.index(f'"{key}"'):]
        assert "en:" in line[:400] and "it:" in line[:400]


def test_the_tour_covers_the_lap_wide_findings():
    """I riquadri azzurri sono ora la PRIMA cosa del debrief, sopra le curve."""
    assert "tour.a7.t" in _APPJS


def test_the_tour_explains_the_temperature_in_the_lap_list():
    """Un numero coi gradi accanto a ogni giro, comparso senza presentazioni:
    l'asfalto o l'aria?"""
    assert "tour.a8.t" in _APPJS
    assert "asfalto" in _I18NJS and "not the air" in _I18NJS
