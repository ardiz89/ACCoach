"""Il bottone spento smette di essere muto — e lo scambio ferma prima di avviare.

Trovato in pista il 2026-09-01: sotto Coach Live il Backend live non si accende
(giustamente: due motori salverebbero ogni giro due volte) e la pagina Ingegnere
su cui il briefing ai box manda il pilota resta senza feed. Il bottone non
diceva niente di tutto questo.

Qui si prova il **cablaggio**: che il bottone sia acceso, che il click non avvii
niente, e che lo scambio non avvii il backend finché Coach Live non è morto
davvero. La regola in sé sta in `tests/test_hubgate.py`, senza Qt.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")


class _FakeProc:
    """Un figlio vivo finché non gli si dice il contrario."""

    def __init__(self) -> None:
        self._done = None

    def poll(self):
        return self._done

    def wait(self, timeout=None):
        if self._done is None:
            raise TimeoutError("still running")
        return self._done

    def exit(self) -> None:
        self._done = 0


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def hub(app, tmp_path, monkeypatch):
    from accoach import config, launcher
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    win = launcher.MainWindow()
    yield win
    win._children.clear()


def _button(win, key):
    for k, _label, btn in win._actions:
        if k == key:
            return btn
    raise AssertionError(f"il bottone {key!r} non è registrato")


@pytest.fixture
def live(hub):
    """Coach Live acceso, e il processo finto che lo rappresenta."""
    proc = _FakeProc()
    hub._children.append((proc, ["live"]))
    hub._refresh_buttons()
    return proc


def test_the_backend_button_stays_clickable_and_says_why(hub, live):
    from accoach.i18n import t

    btn = _button(hub, ("server",))
    assert btn.isEnabled() is True          # non più grigio e muto
    assert btn.toolTip() == t("swap.tooltip")


def _answer(monkeypatch, hub, choice, log=None):
    """Metti in bocca all'utente una delle tre uscite del dialogo."""
    def ask(key):
        if log is not None:
            log.append(key)
        return choice
    monkeypatch.setattr(hub, "_ask_swap", ask)


def test_the_click_starts_nothing_by_itself(hub, live, monkeypatch):
    """Premuto, il bottone apre la spiegazione — non avvia il backend."""
    from accoach.hubgate import CANCEL

    spawned = []
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(args))
    _answer(monkeypatch, hub, CANCEL)          # l'utente annulla
    _button(hub, ("server",)).click()
    assert spawned == []


def test_the_engineer_page_offers_the_swap_too(hub, live, monkeypatch):
    """È il bottone che il briefing ai box nomina: da solo aprirebbe una pagina
    senza la sua metà dal vivo."""
    from accoach.hubgate import CANCEL

    asked = []
    spawned = []
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(args))
    _answer(monkeypatch, hub, CANCEL, log=asked)
    _button(hub, ("web", "--engineer")).click()
    assert asked == [("web", "--engineer")]
    assert spawned == []


def test_open_anyway_opens_the_page_and_leaves_coach_live_alone(hub, live,
                                                                monkeypatch):
    """La terza uscita. La pagina Ingegnere è due cose in una: senza il Backend
    live perde la diagnosi dal vivo, ma l'editor assetti, il registro delle
    prove e i setup salvati stanno sul REST dell'app di analisi e restano lì.
    Toglierla sarebbe costato più di quanto lo scambio restituisce."""
    from accoach.hubgate import OPEN_ANYWAY

    spawned = []
    killed = []
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(tuple(args)))
    monkeypatch.setattr(hub, "_kill", lambda proc: killed.append(proc))
    _answer(monkeypatch, hub, OPEN_ANYWAY)
    _button(hub, ("web", "--engineer")).click()

    assert spawned == [("web", "--engineer")]   # e NON ("server",)
    assert killed == []                         # Coach Live non si tocca
    assert hub._live_running() is True


def test_the_backend_button_has_no_open_anyway_exit(hub, live, monkeypatch):
    """L'asimmetria arriva al dialogo: della pagina Ingegnere si apre lo stesso
    la metà che c'è, del Backend live non c'è niente da aprire lo stesso. Chi
    decide è `hubgate.opens_anyway`, non un `if` sepolto nel disegno."""
    from accoach import launcher
    from accoach.hubgate import CANCEL

    built = []

    class _FakeDialog:
        def __init__(self, parent=None, *, open_anyway=False):
            built.append(open_anyway)
            self.choice = CANCEL

        def exec(self):
            return 0

    monkeypatch.setattr(launcher, "SwapToBackend", _FakeDialog)
    monkeypatch.setattr(hub, "_spawn", lambda args, console: None)
    _button(hub, ("server",)).click()
    _button(hub, ("web", "--engineer")).click()
    assert built == [False, True]


def test_the_dialog_grows_the_third_exit_only_when_asked(hub, monkeypatch):
    """E il dialogo lo disegna davvero: tre bottoni o due, non sempre tre."""
    from PySide6.QtWidgets import QPushButton

    from accoach.i18n import t
    from accoach.launcher import SwapToBackend

    def labels(dlg):
        return [b.text() for b in dlg.findChildren(QPushButton)]

    with_third = labels(SwapToBackend(open_anyway=True))
    without = labels(SwapToBackend(open_anyway=False))
    assert t("swap.open_anyway") in with_third
    assert t("swap.open_anyway") not in without
    assert t("swap.confirm") in without and t("swap.cancel") in without


# --- la finestra e quello che ha da dire ------------------------------------
#
# La tipografia non si testa. Questa proprietà sì: **il contenuto non deve
# chiedere più spazio di quanto la finestra gliene dia**, e non deve avercene
# molto di meno — un dialogo con 140 px di vuoto fra l'ultimo paragrafo e i
# bottoni si legge come una finestra che non ha finito di caricare. Misurata in
# tutte e due le lingue perché l'italiano è più lungo dell'inglese: era proprio
# lì che la finestra chiedeva 584 px per un contenuto che ne voleva 681.

@pytest.fixture
def styled(app):
    """Il dialogo misurato com'è davvero: font del brand e stylesheet veri.

    Senza, le metriche sono quelle di un altro carattere e la misura non dice
    niente. Lo stylesheet torna com'era in uscita: l'app di Qt è condivisa da
    tutti i test della sessione.
    """
    from accoach.theme import load_fonts, qss

    old = app.styleSheet()
    load_fonts()
    app.setStyleSheet(qss())
    yield app
    app.setStyleSheet(old)


def _measure(app, monkeypatch, lang, **kw):
    from accoach import hubgate, launcher

    monkeypatch.setattr(launcher, "swap_text", lambda: hubgate.swap_text(lang))
    dlg = launcher.SwapToBackend(**kw)
    dlg.show()
    app.processEvents()
    size, hint = dlg.size(), dlg.sizeHint()
    dlg.close()
    return size, hint


@pytest.mark.parametrize("open_anyway", (False, True))
@pytest.mark.parametrize("lang", ("en", "it"))
def test_the_window_gives_the_text_all_the_room_it_asks_for(styled, monkeypatch,
                                                            lang, open_anyway):
    size, hint = _measure(styled, monkeypatch, lang, open_anyway=open_anyway)
    assert size.width() >= hint.width(), f"{lang}: {size.width()} < {hint.width()}"
    assert size.height() >= hint.height(), f"{lang}: {size.height()} < {hint.height()}"


@pytest.mark.parametrize("open_anyway", (False, True))
@pytest.mark.parametrize("lang", ("en", "it"))
def test_the_window_has_no_dead_space_under_the_text(styled, monkeypatch,
                                                     lang, open_anyway):
    size, hint = _measure(styled, monkeypatch, lang, open_anyway=open_anyway)
    assert size.height() - hint.height() <= 16, \
        f"{lang}: {size.height() - hint.height()} px di vuoto"


@pytest.mark.parametrize("open_anyway", (False, True))
@pytest.mark.parametrize("lang", ("en", "it"))
def test_the_lines_do_not_run_away_in_the_longer_language(styled, monkeypatch,
                                                          lang, open_anyway):
    """Niente costringeva i paragrafi a mandare a capo, quindi l'italiano
    sfondava a 790 px di righe lunghe e faticose."""
    size, _hint = _measure(styled, monkeypatch, lang, open_anyway=open_anyway)
    assert size.width() <= 620, f"{lang}: {size.width()} px di larghezza"


def test_the_failure_dialog_also_fits_what_it_says(styled, monkeypatch):
    from accoach import launcher

    dlg = launcher.SwapFailed()
    dlg.show()
    styled.processEvents()
    size, hint = dlg.size(), dlg.sizeHint()
    dlg.close()
    assert size.width() >= hint.width() and size.height() >= hint.height()


def test_accepting_stops_coach_live_before_starting_anything(hub, live, monkeypatch):
    from accoach.hubgate import SWAP

    log = []

    def fake_kill(proc):
        log.append(("stop", None))
        proc.exit()

    def fake_spawn(args, console):
        # Al momento dell'avvio non deve esserci più nessun motore acceso: se
        # coesistessero anche solo per un istante, il giro si salverebbe due volte.
        hub._prune()
        assert not [a for _p, a in hub._children if a and a[0] == "live"]
        log.append(("start", tuple(args)))

    monkeypatch.setattr(hub, "_kill", fake_kill)
    monkeypatch.setattr(hub, "_spawn", fake_spawn)
    _answer(monkeypatch, hub, SWAP)
    _button(hub, ("server",)).click()

    assert log[0][0] == "stop"
    assert log[1:] == [("start", ("server",)), ("start", ("web", "--engineer"))]


def test_the_backend_does_not_start_if_coach_live_survives(hub, live, monkeypatch):
    """`taskkill` torna prima che il processo sia morto. Se lo stop non ha
    preso, avviare lo stesso sarebbe la coesistenza che stiamo escludendo."""
    from accoach.hubgate import SWAP

    failures = []
    spawned = []
    monkeypatch.setattr(hub, "_kill", lambda proc: None)    # lo stop non prende
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(args))
    _answer(monkeypatch, hub, SWAP)
    monkeypatch.setattr(hub, "_swap_failed", lambda: failures.append(True))
    _button(hub, ("server",)).click()

    assert spawned == []
    assert failures == [True]


def test_the_swap_waits_for_coach_live_to_be_gone_before_starting(hub, live,
                                                                  monkeypatch):
    """Su Windows `taskkill` torna prima che il processo sia morto: chi guarda
    solo `poll()` subito dopo vede ancora Coach Live vivo. Qui il figlio finto
    muore *solo dentro* `wait()` — se lo scambio non aspettasse, il backend non
    partirebbe mai (e in un caso peggiore partirebbe accanto a un motore vivo)."""
    from accoach.hubgate import SWAP

    spawned = []
    failures = []

    def kill_that_takes_its_time(proc):
        proc.dying = True                # chiesto, non ancora morto

    def wait(timeout=None):
        if getattr(live, "dying", False):
            live.exit()
        return live.poll()

    live.wait = wait
    monkeypatch.setattr(hub, "_kill", kill_that_takes_its_time)
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(tuple(args)))
    _answer(monkeypatch, hub, SWAP)
    monkeypatch.setattr(hub, "_swap_failed", lambda: failures.append(True))
    _button(hub, ("server",)).click()

    assert failures == []
    assert spawned == [("server",), ("web", "--engineer")]


def test_without_coach_live_the_button_simply_starts_the_backend(hub, monkeypatch):
    from accoach.hubgate import SWAP

    spawned = []
    asked = []
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(tuple(args)))
    _answer(monkeypatch, hub, SWAP, log=asked)
    hub._refresh_buttons()
    _button(hub, ("server",)).click()
    assert spawned == [("server",)]
    assert asked == []          # niente da spiegare: non c'è niente da fermare


def test_the_home_setup_shortcut_goes_through_the_same_gate(hub, live, monkeypatch):
    """La scorciatoia «Setup» della Home apriva la pagina Ingegnere saltando
    ogni controllo: stesso muro, stesso silenzio."""
    from accoach.hubgate import CANCEL

    asked = []
    spawned = []
    monkeypatch.setattr(hub, "_spawn", lambda args, console: spawned.append(args))
    _answer(monkeypatch, hub, CANCEL, log=asked)
    hub._home._cta_setup.click()
    assert asked == [("web", "--engineer")]
    assert spawned == []
