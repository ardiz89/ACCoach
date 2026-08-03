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
    # I percorsi su disco restano ACCoach: è la cartella vera.
    stray = [ln for ln in _GUIDA.splitlines()
             if "ACCoach" in ln and "Documenti/ACCoach/" not in ln]
    assert not stray, f"nome vecchio rimasto: {stray}"


def _guide_commands() -> set[str]:
    """I comandi che la guida elenca nelle sue tabelle, senza gli argomenti."""
    rows = re.findall(r"^\|\s*`([a-z-]+[^`]*)`\s*\|", _GUIDA, re.M)
    # Le voci di `config.toml` stanno in una tabella con la stessa forma, ma sono
    # chiavi puntate (`data.laps_dir`), non comandi. Il punto le distingue.
    return {r.split()[0] for r in rows if "." not in r.split()[0]}


def test_the_guide_does_not_send_you_to_deleted_wrappers():
    """I dodici `run_*.py` sono spariti coi tagli del 27/07, e la guida li
    offriva ancora come alternativa a ogni comando. Un'istruzione che fallisce
    con «file non trovato» è peggio di un'istruzione mancante."""
    assert "run_*.py" not in _GUIDA
    stray = re.findall(r"`run_[a-z_]+\.py`", _GUIDA)
    assert not stray, f"wrapper cancellati citati nella guida: {stray}"


def test_every_command_the_guide_names_still_exists():
    """La tabella dei comandi non ha modo di accorgersi di un comando rinominato.

    Il confronto è con i due testi di aiuto della CLI, che a loro volta un test
    tiene allineati a ciò che il dispatcher accetta davvero
    (``tests/test_cli.py``): così la catena guida → aiuto → dispatcher si chiude.
    """
    import accoach.__main__ as cli

    documented = cli._HELP + cli._HELP_TOOLS
    commands = _guide_commands()
    assert commands, "nessun comando trovato nelle tabelle della guida"
    for cmd in commands:
        assert re.search(rf"^  {re.escape(cmd)}\b", documented, re.M), cmd


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


# --- la guida racconta il rientro ai box -----------------------------------

def _flat(text: str) -> str:
    """Il testo senza gli a capo del sorgente.

    Le frasi della guida sono mandate a capo a 80 colonne, quindi cercarle come
    sottostringa fallisce a seconda di dove cade l'a capo — cioè il test
    fallirebbe per la formattazione invece che per il contenuto.
    """
    return re.sub(r"\s+", " ", text)


def test_the_guide_explains_being_called_into_the_pits():
    """Una voce nuova che ti parla mentre guidi, e che ti chiede di perdere un
    giro: se la guida non la nomina, la prima volta sembra un guasto."""
    assert "rientra ai box a fine giro" in _flat(_GUIDA)
    assert "Ingresso box qui davanti" in _flat(_GUIDA)


def test_the_guide_says_why_the_pit_entry_warning_can_be_missing():
    """È l'unica parte del coach che tace **di proposito** su una pista nuova.
    Non spiegarlo lo fa sembrare rotto proprio dove è più prudente."""
    assert "nessun gioco lo pubblica" in _flat(_GUIDA)
    assert "mediana" in _GUIDA


def test_the_guide_says_the_menu_teleport_teaches_nothing():
    """È la domanda che ha posto il pilota, ed è comportamento voluto."""
    assert "torna ai box" in _flat(_GUIDA) and "non insegna niente" in _flat(_GUIDA)


def test_the_guide_explains_that_a_dial_needs_no_confirmation():
    """Il ciclo dell'ingegnere si chiude da solo su ACC e con un pulsante su AC:
    due comportamenti diversi sullo stesso schermo vanno detti, o il pulsante
    che non compare sembra un pezzo mancante."""
    assert "Al volo" in _flat(_GUIDA) and "guarda il canale" in _flat(_GUIDA)
    assert "eng.avDone" in _I18NJS


def test_the_engineer_tour_introduces_the_at_the_wheel_panel():
    engjs = (_ROOT / "src" / "accoach" / "web" / "engineer.js").read_text(
        encoding="utf-8")
    assert "tour.e6.t" in engjs and '"tour.e6.t"' in _I18NJS


# --- e la regola nuova su chi diventa il riferimento ------------------------

def test_both_guides_explain_the_lap_nobody_judged():
    """Il pilota apre il report, trova il proprio record personale scavalcato da
    un giro più lento e non trova scritto perché da nessuna parte: è la stessa
    cosa di un'app rotta. La frase è sullo schermo — deve esserci anche qui."""
    assert "nessuno ha guardato" in _flat(_GUIDA)
    assert "1:53.712" in _GUIDA, "il caso vero da cui è nata la regola"
    assert "nothing looked" in _flat(_FAQ)
    assert "1:53.712" in _FAQ


def test_the_screen_and_the_guide_use_the_same_words():
    """Se il riepilogo dice una cosa e la guida un'altra, il driver non collega
    le due e cerca un guasto."""
    assert "verificato i limiti di pista" in _flat(_I18NJS)
    assert "verificato i limiti di pista" in _flat(_GUIDA)
    assert "checked it for track limits" in _flat(_I18NJS)
    assert "checked it for track limits" in _flat(_FAQ)
