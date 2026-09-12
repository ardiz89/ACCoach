"""Chi è cliccabile, cosa dice il rifiuto, in che ordine si fa lo scambio.

Trovato in pista il 2026-09-01: il briefing ai box dice «apri la pagina
Ingegnere», quella pagina la alimenta solo il Backend live, e sotto Coach Live
il bottone del Backend live era **spento e muto**. Il coach mandava il pilota
contro un muro e il muro non diceva niente.

La decisione sta qui, fuori da Qt, perché un bottone grigio non si interroga in
un test headless — ma la regola che lo rende grigio sì.
"""
import pytest

from accoach import hubgate
from accoach.hubgate import (
    BLOCKED,
    CLICKABLE,
    EXPLAIN,
    LIVE_SAFE_KEYS,
    RECORDING_CMDS,
    button_state,
    swap_is_safe,
    swap_plan,
    swap_text,
)


# --- lo stato dei bottoni ---------------------------------------------------

def test_the_backend_button_explains_itself_instead_of_going_quiet():
    """Era spento e senza spiegazione: il difetto in una riga."""
    assert button_state(("server",), live=True, busy=True) == EXPLAIN


def test_the_engineer_page_offers_the_swap_too():
    """È il bottone su cui il briefing ai box manda il pilota: aprirlo durante
    Coach Live dà una pagina che nessuno alimenta."""
    assert button_state(("web", "--engineer"), live=True, busy=True) == EXPLAIN


def test_the_backend_button_is_ordinary_when_nothing_is_running():
    assert button_state(("server",), live=False, busy=False) == CLICKABLE


def test_a_second_recorder_stays_blocked_while_something_records():
    """Fuori da Coach Live la vecchia regola non cambia: chi registra è spento
    finché qualcos'altro registra."""
    assert button_state(("recorder",), live=False, busy=True) == BLOCKED
    assert button_state(("coach",), live=False, busy=True) == BLOCKED


def test_everything_else_is_still_shut_during_coach_live():
    assert button_state(("monitor",), live=True, busy=True) == BLOCKED
    assert button_state(("debrief",), live=True, busy=True) == BLOCKED


def test_the_live_safe_buttons_keep_working():
    assert button_state(("web",), live=True, busy=True) == CLICKABLE
    assert button_state(hubgate.STOP_LIVE, live=True, busy=True) == CLICKABLE
    assert button_state(hubgate.GUIDE, live=True, busy=True) == CLICKABLE


def test_the_backend_never_becomes_live_safe():
    """Il vincolo che non si tocca: si passa fermando, mai affiancando."""
    assert ("server",) not in LIVE_SAFE_KEYS
    assert "server" in RECORDING_CMDS


# --- lo scambio -------------------------------------------------------------

def test_the_swap_stops_before_it_starts():
    """L'ordine è la sostanza: avviare prima e fermare dopo vorrebbe dire due
    motori accesi insieme, fosse anche per un istante."""
    steps = swap_plan()
    assert steps[0].action == "stop"
    assert steps[0].args == ("live",)
    first_start = min(i for i, s in enumerate(steps) if s.action == "start")
    assert first_start > 0
    assert all(s.action == "start" for s in steps[1:])


def test_the_swap_brings_up_the_backend_and_the_engineer_page():
    started = [s.args for s in swap_plan() if s.action == "start"]
    assert ("server",) in started
    assert ("web", "--engineer") in started


def test_only_the_engineer_page_can_be_opened_anyway():
    """La pagina Ingegnere sono due cose in una: la diagnosi dal vivo (che senza
    il Backend live non c'è) e l'editor assetti, il registro delle prove e i
    setup salvati — che stanno sul REST dell'app di analisi e non hanno bisogno
    di niente. Il Backend live invece non ha una metà da aprire lo stesso."""
    assert hubgate.opens_anyway(("web", "--engineer")) is True
    assert hubgate.opens_anyway(("server",)) is False


def test_open_anyway_is_only_ever_offered_for_something_harmless():
    """La regola, non l'elenco: si può offrire «apri comunque» solo a ciò che è
    già sicuro durante Coach Live e non registra nulla. Se un domani qualcuno
    aggiunge una chiave all'uscita di comodo, questo test glielo chiede."""
    for key in hubgate.OPEN_ANYWAY_KEYS:
        assert key in LIVE_SAFE_KEYS, key
        assert key[0] not in RECORDING_CMDS, key


def test_the_swap_refuses_to_start_next_to_anything_that_records():
    """La guardia vera: se Coach Live non è morto davvero, il backend non parte."""
    assert swap_is_safe([]) is True
    assert swap_is_safe([["web"]]) is True
    assert swap_is_safe([["live"]]) is False
    assert swap_is_safe([["live", "--demo"]]) is False
    assert swap_is_safe([["web"], ["recorder"]]) is False


# --- le parole --------------------------------------------------------------

@pytest.mark.parametrize("lang", ("en", "it"))
def test_the_refusal_says_why_in_the_driver_words(lang):
    txt = swap_text(lang)
    why = txt["why"].lower()
    assert ("due volte" in why) if lang == "it" else ("twice" in why)


@pytest.mark.parametrize("lang", ("en", "it"))
def test_the_warning_names_the_overlay_before_it_disappears(lang):
    assert "overlay" in swap_text(lang)["warn"].lower()


@pytest.mark.parametrize("lang", ("en", "it"))
def test_open_anyway_says_which_half_you_get_and_which_you_lose(lang):
    """Non «funziona a metà»: quale metà. L'editor assetti sì, la diagnosi dal
    vivo no."""
    line = swap_text(lang)["open_anyway_why"].lower()
    wanted = (("setup", "live"), ("assetti", "vivo"))[lang == "it"]
    for word in wanted:
        assert word in line, (lang, word)


def test_the_swap_speaks_every_language_the_app_has():
    """Una funzionalità che esiste solo in italiano è già stata un difetto."""
    from accoach.i18n import LANGUAGES, _UI

    for key in hubgate.SWAP_TEXT_KEYS:
        assert key in _UI, f"{key} non è nel catalogo"
        for lang in LANGUAGES:
            assert _UI[key].get(lang), f"{key} manca in {lang}"


def test_the_two_languages_are_actually_two():
    """`t()` ripiega sull'inglese: se l'italiano mancasse il test sopra
    passerebbe lo stesso guardando solo `t()`. Qui si controlla che siano
    testi diversi, non la stessa frase due volte."""
    en, it = swap_text("en"), swap_text("it")
    for field in ("title", "why", "warn", "confirm", "cancel", "failed",
                  "open_anyway", "open_anyway_why"):
        assert en[field] != it[field], field
