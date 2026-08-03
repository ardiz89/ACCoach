"""La prima ora di un utente nuovo: i vicoli ciechi.

Non un audit di codice — un percorso. Scarichi HONE, non hai un giro, guidi la
prima sessione, apri il report per la prima volta, provi l'Ingegnere. In ognuno
di quei passi c'era uno stato in cui la schermata non spiega cosa fare dopo, e
il progetto ha una regola forte contro esattamente questo: **ogni silenzio deve
dire perché tace**, perché un gate silenzioso si legge come un'app rotta.
"""
import re
from pathlib import Path

from accoach.i18n import t

_ROOT = Path(__file__).resolve().parent.parent
_WEB = _ROOT / "src" / "accoach" / "web"
_CSS = (_WEB / "style.css").read_text(encoding="utf-8")
_APPJS = (_WEB / "app.js").read_text(encoding="utf-8")
_ENGJS = (_WEB / "engineer.js").read_text(encoding="utf-8")
_I18NJS = (_WEB / "i18n.js").read_text(encoding="utf-8")


# --- zero giri: il messaggio deve essere l'unica cosa a schermo ------------

def test_nothing_interactive_survives_the_empty_state():
    """`init()` esce prima di collegare le schede, quindi ciò che resta a schermo
    è *finto*: otto tab che al clic non fanno niente, tendine vuote, e la card
    di `#view-flow` che riempiva la finestra spingendo «ancora nessun giro»
    **sotto la piega**."""
    rule = re.search(r"body\.no-data[^{]*\{[^}]*display:\s*none[^}]*\}", _CSS)
    assert rule, "manca del tutto la regola dello stato vuoto"
    block = rule.group(0)
    for sel in ("nav.tabs", "#lapbar", "header .controls", "#view-flow"):
        assert sel in block, f"{sel} resta a schermo senza fare niente"


# --- l'Ingegnere senza setup su disco -------------------------------------

def test_no_setups_on_disk_does_not_contradict_itself():
    """Una tendina che dice «(nessun setup trovato)» sopra un pannello che
    ordina di scegliere da quella tendina. Ci finisce quasi ogni primo utente:
    un'installazione ACC nuova ha la cartella dei setup vuota."""
    body = _ENGJS[_ENGJS.index("async function loadCombos"):]
    body = body[:body.index("\n}")]
    assert "noSetupHTML()" in body, "il testo giusto esiste e non veniva usato"


def test_the_engineer_says_what_it_is_waiting_for():
    """Un trattino dentro un riquadro intitolato «Il tecnico suggerisce» è un
    silenzio che non dice perché tace."""
    assert '"eng.warmup"' in _I18NJS
    assert "eng.warmup" in _ENGJS


# --- la scheda frenate ----------------------------------------------------

def test_a_failed_brake_sheet_still_says_something():
    """Era l'unico punto del codice dove un errore produceva silenzio assoluto:
    pannello svuotato, zero testo, zero motivo. E `/api/braking` fa 404 finché
    non c'è un giro valido e pulito, cioè il caso normale di un debuttante."""
    body = _APPJS[_APPJS.index("async function loadBraking"):]
    body = body[:body.index("\n}")]
    assert 'innerHTML = ""' not in body
    assert "renderBrakeSheet(null)" in body


# --- l'archivio illeggibile non è «non hai mai guidato» --------------------

def test_an_unreadable_archive_is_its_own_state():
    """Catalogo bloccato da un altro processo, schema vecchio, file corrotto:
    tutto atterrava su «Nessuna sessione ancora», detto a chi aveva appena
    finito una sessione. Non è tacere senza spiegare — è dire la cosa sbagliata
    sul perché, e manda a guidare di più invece che a guardare i log."""
    import inspect

    from accoach import hub_home

    src = inspect.getsource(hub_home)
    assert 'HomeData(status="error")' in src
    assert 'status == "error"' in src
    for lang in ("it", "en"):
        assert t("home.error_title", lang=lang) != "home.error_title"
        assert len(t("home.error_body", lang=lang)) > 40


# --- «Guida» non può significare due cose ---------------------------------

def test_the_sidebar_does_not_collide_with_the_manual():
    """Sidebar: Home · Guida · Analisi… e il manuale sta in Impostazioni, sotto
    «Strumenti avanzati». Chi ha appena chiuso il wizard e vuole rileggere le
    istruzioni clicca «Guida» e trova i pulsanti di Coach Live. In inglese la
    collisione non c'era mai stata (Drive / Guide)."""
    for lang in ("it", "en"):
        assert t("nav.live", lang=lang).strip() != t("btn.guide", lang=lang) \
            .replace("❓", "").split("—")[0].strip()
    assert t("nav.live", lang="it").strip() != "Guida"
