"""Il pannello «In pista»: disegna lo stato che `livepanel` decide, e il clic
«Ho finito» ferma il coach prima di aprire la Pagella.

Le regole (quando il gioco e' chiuso, quando il coach non risponde) stanno in
`tests/test_livepanel.py`, senza Qt. Qui si prova il cablaggio: cosa compare in
ogni stato, l'ordine delle azioni, che il pannello interroghi `/health` solo
mentre Coach Live gira, e che niente aspetti sul thread dell'interfaccia.
Nessun processo vero e nessuna porta 8777/8778: `_spawn`, la sonda della porta,
`webbrowser.open` e la rete sono finti (tranne nei test della sonda, su una
porta libera).
"""
import os
import re
import socket
import sqlite3
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from accoach.livepanel import PanelState  # noqa: E402

# La pagina dell'hub: finestra da 900x600 meno la barra laterale da 210.
PAGE_W, PAGE_H = 900 - 210, 600
CAR, TRACK = "mclaren_720s_gt3", "imola"
PAGELLA = f"http://127.0.0.1:8778/?view=pagella&car={CAR}&track={TRACK}"


class _FakeProc:
    """Un figlio vivo finche' non gli si dice il contrario."""

    def __init__(self) -> None:
        self._done = None

    def poll(self):
        return self._done

    def wait(self, timeout=None):
        return self._done

    def exit(self) -> None:
        self._done = 0


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Net:
    """Porte, processi e browser finti, con il registro delle chiamate."""

    def __init__(self) -> None:
        self.open_ports: set[int] = set()
        self.calls: list[tuple] = []
        self.win = None

    def probe(self, port, cb):
        self.calls.append(("probe", port))
        cb(port in self.open_ports)

    def spawn(self, args, console=False):
        self.calls.append(("spawn", tuple(args)))
        self.win._children.append((_FakeProc(), list(args)))

    def browse(self, url, *a, **k):
        self.calls.append(("open", url))
        return True

    def spawns(self, what=("web", "--no-browser")):
        return [c for c in self.calls if c == ("spawn", what)]


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    from accoach import config, launcher, livepanel_ui
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    net = _Net()
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(livepanel_ui.webbrowser, "open", net.browse)
    monkeypatch.setattr(livepanel_ui, "device_urls", lambda port: {
        "report": f"http://192.168.1.23:{port}/",
        "engineer": f"http://192.168.1.23:{port}/engineer",
        "test": f"http://192.168.1.23:{port}/test"})
    monkeypatch.setattr(livepanel_ui, "laps_root", lambda: tmp_path / "laps")
    win = launcher.MainWindow()
    net.win = win
    monkeypatch.setattr(win, "_spawn", net.spawn)
    panel = win._live_panel
    monkeypatch.setattr(panel, "_probe", net.probe)
    # Nessuna richiesta vera: il poll registra soltanto.
    monkeypatch.setattr(panel, "_poll_once", lambda: net.calls.append(("poll",)))
    yield win, panel, net, tmp_path
    for t in (win._timer, win._watch_timer, panel._poll, panel._web_timer,
              panel._stop_timer):
        t.stop()
    win._children.clear()


def _cfg():
    from accoach.config import load_config
    return load_config()


def _visible_in(w, panel) -> bool:
    """Visibile rispetto al pannello (la finestra non e' mai mostrata)."""
    p = w
    while p is not None and p is not panel:
        if p.isHidden():
            return False
        p = p.parentWidget()
    return True


def _texts(panel) -> list[str]:
    """I testi che il pannello mostra (etichette e bottoni non nascosti)."""
    from PySide6.QtWidgets import QLabel, QPushButton
    return [w.text() for w in panel.findChildren(QLabel) + panel.findChildren(QPushButton)
            if _visible_in(w, panel)]


def _joined(panel) -> str:
    return "\n".join(_texts(panel))


def _settle(panel, timeout=3.0) -> None:
    """Lascia finire la lettura del catalogo (in un thread) e consegnare."""
    from PySide6.QtWidgets import QApplication
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if panel._cat_job is None:
            return
        time.sleep(0.01)
    raise AssertionError("la lettura del catalogo non e' tornata")


def _states():
    return {
        "idle": PanelState("idle"),
        "before": PanelState("before"),
        "driving": PanelState("driving", tablet_done=True, tablet_now=True,
                              car=CAR, track=TRACK, saved_laps=6, laps_done=7,
                              best="1:41.882"),
        "finished": PanelState("finished", tablet_done=True, car=CAR,
                               track=TRACK, saved_laps=14, laps_done=14,
                               best="1:41.882"),
        "silent": PanelState("silent", tablet_done=True, tablet_now=True,
                             car=CAR, track=TRACK, saved_laps=6, laps_done=7,
                             best="1:41.882"),
    }


def _live(win):
    """Coach Live acceso: un processo finto e il poll dell'hub."""
    proc = _FakeProc()
    win._children.append((proc, ["live"]))
    win._refresh_buttons()
    return proc


def _stop_kills(monkeypatch, win, net, proc=None):
    """`_stop_live` finto: registra e, se gli si da' il processo, lo fa morire."""
    def stop():
        net.calls.append(("stop",))
        if proc is not None:
            proc.exit()
        win._refresh_buttons()
    monkeypatch.setattr(win, "_stop_live", stop)


# --- i cinque stati --------------------------------------------------------

@pytest.mark.parametrize("lang", ["it", "en"])
def test_each_state_renders_and_fits(env, lang):
    from accoach.config import set_language
    win, panel, _net, _tmp = env
    set_language(lang)
    _cfg().lan = True
    raw_key = re.compile(r"\blive\.[a-z_]")
    for name, st in _states().items():
        panel.render_state(st)
        hint = panel.sizeHint()
        assert hint.width() <= PAGE_W, (name, hint)
        assert hint.height() <= PAGE_H, (name, hint)
        panel.resize(PAGE_W, PAGE_H)
        assert not panel.grab().isNull()
        for text in _texts(panel):
            assert not raw_key.search(text), (name, text)


def test_the_qr_is_there_only_with_lan_on(env):
    from PySide6.QtWidgets import QLabel, QPushButton
    from accoach.i18n import t
    win, panel, _net, _tmp = env

    _cfg().lan = True
    panel.render_state(PanelState("before"))
    qr = panel.findChild(QLabel, "liveQr")
    assert qr is not None and _visible_in(qr, panel)
    assert "192.168.1.23:8778/engineer" in _joined(panel)

    _cfg().lan = False
    panel.render_state(PanelState("before"))
    assert panel.findChild(QLabel, "liveQr") is None
    assert "192.168.1.23" not in _joined(panel)
    assert t("live.s2_lan_off") in _joined(panel)
    # Il bottone porta alla pagina «Dispositivi», dove la rete si accende.
    panel.findChild(QPushButton, "liveToDevices").click()
    assert win._stack.currentWidget() is win._devices


def test_once_the_tablet_step_is_done_the_qr_goes(env):
    from PySide6.QtWidgets import QLabel
    _win, panel, _net, _tmp = env
    _cfg().lan = True
    panel.render_state(PanelState("before", tablet_done=True, tablet_now=True))
    assert panel.findChild(QLabel, "liveQr") is None


def test_skip_ticks_the_tablet_step(env):
    from PySide6.QtWidgets import QLabel, QPushButton
    from accoach.i18n import t
    win, panel, _net, _tmp = env
    _cfg().lan = True
    _live(win)
    panel.findChild(QPushButton, "liveSkip").click()
    assert panel.findChild(QLabel, "liveQr") is None
    assert t("live.tablet_skipped") in _joined(panel)


def test_silent_does_not_claim_the_tablet(env):
    """Durante il silenzio `tablet_now` e' l'ultimo valore visto, non adesso."""
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    panel.render_state(_states()["silent"])
    text = _joined(panel)
    assert t("live.silent") in text
    assert t("live.tablet_on") not in text
    assert "1:41" not in text                     # i dati non ci sono
    from PySide6.QtWidgets import QPushButton
    assert "liveFinish" in [w.objectName() for w in panel.findChildren(QPushButton)
                            if _visible_in(w, panel)]   # i bottoni si'


def test_driving_shows_the_tablet_now(env):
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    panel.render_state(_states()["driving"])
    assert t("live.tablet_on") in _joined(panel)
    panel.render_state(PanelState("driving", tablet_done=True, tablet_now=False,
                                  car=CAR, track=TRACK))
    assert t("live.tablet_on") not in _joined(panel)
    assert t("live.tablet_off") in _joined(panel)


def test_stay_on_track_goes_back_to_driving(env):
    from PySide6.QtWidgets import QPushButton
    from accoach.i18n import t
    win, panel, _net, _tmp = env
    _live(win)
    panel.render_state(_states()["finished"])
    panel.findChild(QPushButton, "liveStay").click()
    assert panel.state.phase == "driving"
    assert t("live.finished") not in _joined(panel)


# --- il catalogo: consiglio e giri della corsa -----------------------------

def _save_advice(tmp, status):
    from accoach.recording.catalog import LapCatalog
    from accoach.recording.storage import _catalog_path
    with LapCatalog(_catalog_path(tmp / "laps")) as cat:
        cat.save_advice(CAR, TRACK, {"defect": "brake_early", "status": status,
                                     "corners": []})


def _add_laps(tmp, rows):
    """`rows` = (car, track, recorded_utc, lap_time_ms, valid)."""
    from accoach.recording.catalog import LapCatalog
    from accoach.recording.storage import _catalog_path, _slug
    db = _catalog_path(tmp / "laps")
    with LapCatalog(db):
        pass
    conn = sqlite3.connect(str(db))
    for i, (car, track, utc, ms, valid) in enumerate(rows):
        conn.execute(
            "INSERT INTO lap (path, car_key, track_key, car_model, track, session,"
            " lap_time_ms, valid, recorded_utc, sample_count, schema_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"lap{i}.json.gz", _slug(car), _slug(track), car, track, 1, ms,
             valid, utc, 100, 11))
    conn.commit()
    conn.close()


def test_following_line_only_with_an_active_advice(env):
    from accoach.coaching.howto import defect_name
    from accoach.i18n import current_language
    _win, panel, _net, tmp = env
    name = defect_name("brake_early", current_language())

    panel.render_state(_states()["driving"])         # nessun catalogo
    _settle(panel)
    assert name not in _joined(panel)

    _save_advice(tmp, "proposed")                     # proposto, non seguito
    panel.render_state(_states()["driving"])
    _settle(panel)
    assert name not in _joined(panel)

    _save_advice(tmp, "active")
    panel.render_state(_states()["driving"])
    _settle(panel)
    assert name in _joined(panel)


def test_the_panel_never_creates_a_catalog(env):
    """L'hub legge il consiglio, non fonda un archivio dei giri dove non c'e'."""
    from accoach.recording.storage import _catalog_path
    _win, panel, _net, tmp = env
    (tmp / "laps").mkdir()                    # la cartella c'e', il catalogo no
    panel.render_state(_states()["driving"])
    panel.render_state(_states()["finished"])
    _settle(panel)
    assert list((tmp / "laps").iterdir()) == []
    assert not _catalog_path(tmp / "laps").exists()


def test_finished_says_valid_over_total_and_how_long(env):
    from accoach.livepanel_ui import _utc_iso
    _win, panel, _net, tmp = env
    now = time.time()
    panel._run_started = now - 3600
    _add_laps(tmp, [
        (CAR, TRACK, _utc_iso(now - 7200), 100_000, 1),   # corsa di prima
        (CAR, TRACK, _utc_iso(now - 600), 100_000, 1),
        (CAR, TRACK, _utc_iso(now - 500), 100_000, 1),
        (CAR, TRACK, _utc_iso(now - 400), 100_000, 0),
        ("other_car", TRACK, _utc_iso(now - 450), 100_000, 1),
    ])
    panel.render_state(_states()["finished"])
    _settle(panel)
    text = _joined(panel)
    # 3 giri della corsa, 2 validi; dal via del primo (−700 s) alla fine
    # dell'ultimo (−400 s) = 300 s = 5 minuti.
    assert "3 laps saved, 2 valid" in text
    assert "5 minutes" in text
    assert "14 laps" not in text                  # il conto di /health cede


def test_the_catalog_is_read_off_the_ui_thread_and_read_only(env, monkeypatch):
    from accoach import livepanel_ui
    from accoach.recording import catalog
    _win, panel, _net, tmp = env
    _save_advice(tmp, "active")
    seen = []
    real = sqlite3.connect

    def spy(*a, **k):
        seen.append((threading.current_thread() is threading.main_thread(), a, k))
        return real(*a, **k)

    monkeypatch.setattr(livepanel_ui.sqlite3, "connect", spy)
    monkeypatch.setattr(catalog.LapCatalog, "__init__",
                        lambda *a, **k: pytest.fail("LapCatalog sul pannello"))
    panel.render_state(_states()["driving"])
    _settle(panel)
    assert seen, "nessuna lettura"
    for on_main, args, kw in seen:
        assert not on_main
        assert args[0].endswith("?mode=ro") and kw.get("uri") is True
        assert kw.get("timeout", 5.0) <= 1.0


# --- «Ho finito» -----------------------------------------------------------

def _click(panel, name):
    from PySide6.QtWidgets import QPushButton
    btn = panel.findChild(QPushButton, name)
    assert btn is not None and _visible_in(btn, panel), name
    btn.click()


def test_finish_stops_coach_then_opens_the_pagella(env, monkeypatch):
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    proc = _live(win)
    _stop_kills(monkeypatch, win, net, proc)
    panel.render_state(_states()["driving"])
    net.calls.clear()
    _click(panel, "liveFinish")
    assert net.calls == [("stop",)]                  # chiesto, non aspettato
    assert panel._stop_timer.isActive()
    panel._stop_tick()
    assert net.calls == [("stop",), ("probe", 8778), ("open", PAGELLA)]


def test_finish_does_not_wait_for_the_process(env, monkeypatch):
    """Il clic torna subito: si aspetta col timer, non con `wait()`."""
    win, panel, net, _tmp = env
    _live(win)
    monkeypatch.setattr(win, "_stop_live_and_wait",
                        lambda *a, **k: pytest.fail("attesa sul clic"))
    _stop_kills(monkeypatch, win, net)              # il processo non muore
    panel.render_state(_states()["driving"])
    from accoach.i18n import t
    _click(panel, "liveFinish")
    net.calls.clear()
    panel._stop_tick()
    assert net.calls == []                    # ancora vivo: aspetta, non procede
    assert panel._stop_timer.isActive()
    assert t("live.stop_late") not in _joined(panel)


def test_finish_from_the_finished_view_does_the_same(env, monkeypatch):
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    _stop_kills(monkeypatch, win, net)
    panel.render_state(_states()["finished"])
    net.calls.clear()
    _click(panel, "liveShow")
    panel._stop_tick()
    assert net.calls[0] == ("stop",)
    assert net.calls[-1] == ("open", PAGELLA)


def test_finish_without_a_combo_opens_the_plain_report(env, monkeypatch):
    from accoach.i18n import t
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    _stop_kills(monkeypatch, win, net)
    for st in (PanelState("driving", tablet_done=True),             # mai partito
               PanelState("driving", tablet_done=True, car=CAR, track=TRACK,
                          saved_laps=0, laps_done=0)):             # zero giri
        panel.render_state(st)
        assert t("live.no_laps") in _joined(panel)
        net.calls.clear()
        _click(panel, "liveFinish")
        panel._stop_tick()
        assert net.calls[-1] == ("open", "http://127.0.0.1:8778/")


def test_with_laps_the_no_laps_line_is_absent(env):
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    panel.render_state(_states()["driving"])
    assert t("live.no_laps") not in _joined(panel)


def test_the_opening_line_stays_through_the_whole_finish(env, monkeypatch):
    """Il coach si ferma, il pannello torna ai bottoni, e la riga resta finche'
    il report non si apre."""
    from accoach.i18n import t
    win, panel, net, _tmp = env
    proc = _live(win)
    _stop_kills(monkeypatch, win, net, proc)
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")
    assert panel.state.phase == "idle"
    assert t("live.report_wait") in _joined(panel)
    panel._stop_tick()                     # report spento: si accende e si aspetta
    assert t("live.report_wait") in _joined(panel)
    net.open_ports.add(8778)
    panel._web_tick()
    assert net.calls[-1] == ("open", PAGELLA)
    assert t("live.report_wait") not in _joined(panel)


def test_finish_starts_the_report_when_it_is_off(env, monkeypatch):
    win, panel, net, _tmp = env
    _stop_kills(monkeypatch, win, net)
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")
    panel._stop_tick()
    assert len(net.spawns()) == 1
    assert not [c for c in net.calls if c[0] == "open"]   # non ancora
    assert panel._web_timer.isActive()                    # riprova, non blocca
    net.open_ports.add(8778)
    panel._web_tick()
    assert net.calls[-1] == ("open", PAGELLA)
    assert not panel._web_timer.isActive()


def test_a_report_that_never_starts_still_opens_and_says_so(env, monkeypatch):
    from accoach.i18n import t
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    _stop_kills(monkeypatch, win, net)
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")
    panel._stop_tick()
    later = time.monotonic() + livepanel_ui.WEB_WAIT_S + 1
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: later)
    panel._web_tick()
    assert net.calls[-1][0] == "open"
    assert t("live.report_late") in _joined(panel)


def test_a_coach_that_will_not_stop_is_said(env, monkeypatch):
    from accoach.i18n import t
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    _live(win)
    _stop_kills(monkeypatch, win, net)              # non muore
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")
    later = time.monotonic() + livepanel_ui.STOP_WAIT_S + 1
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: later)
    panel._stop_tick()
    assert net.calls[-1][0] == "open"
    assert t("live.stop_late") in _joined(panel)


def test_a_note_follows_the_language(env, monkeypatch):
    from accoach.config import set_language
    from accoach.i18n import t
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    set_language("it")
    net.open_ports.add(8778)
    _live(win)
    _stop_kills(monkeypatch, win, net)
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")
    later = time.monotonic() + livepanel_ui.STOP_WAIT_S + 1
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: later)
    panel._stop_tick()
    assert t("live.stop_late", "it") in _joined(panel)
    set_language("en")
    panel.retranslate()
    assert t("live.stop_late", "en") in _joined(panel)
    assert t("live.stop_late", "it") not in _joined(panel)


# --- il processo `web` -----------------------------------------------------

def test_starting_coach_live_starts_the_report_for_the_tablet(env):
    win, panel, net, _tmp = env
    _cfg().lan = True
    _live(win)
    assert len(net.spawns()) == 1


def test_no_report_started_without_lan_or_when_already_up(env):
    win, panel, net, _tmp = env
    _cfg().lan = False
    proc = _live(win)
    assert not net.spawns()
    proc.exit()
    win._refresh_buttons()

    _cfg().lan = True
    net.open_ports.add(8778)
    _live(win)
    assert not net.spawns()


def test_the_report_is_started_once(env, monkeypatch):
    """Avvio con la LAN, poi «Ho finito» mentre si aspetta, poi di nuovo dopo
    che il primo e' andato a vuoto: un solo `web`."""
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    _cfg().lan = True
    proc = _live(win)
    _stop_kills(monkeypatch, win, net, proc)
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")
    panel._stop_tick()                            # si mette in coda
    assert len(net.spawns()) == 1
    assert net.calls.count(("probe", 8778)) == 1  # nessuna seconda sonda
    later = time.monotonic() + livepanel_ui.WEB_WAIT_S + 1
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: later)
    panel._web_tick()                             # a vuoto, ma il browser si apre
    assert net.calls[-1][0] == "open"
    panel._open_here()                            # il nostro `web` e' ancora vivo
    assert len(net.spawns()) == 1


def test_a_report_that_does_not_start_is_said_in_step_two(env, monkeypatch):
    from accoach.i18n import t
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    _cfg().lan = True
    _live(win)
    assert panel._web_timer.isActive()
    later = time.monotonic() + livepanel_ui.WEB_WAIT_S + 1
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: later)
    panel._web_tick()
    assert t("live.s2_web_down") in _joined(panel)
    assert not [c for c in net.calls if c[0] == "open"]   # nessun browser


def _run_until(cond, timeout=3.0):
    from PySide6.QtWidgets import QApplication
    end = time.monotonic() + timeout
    while time.monotonic() < end and not cond():
        QApplication.processEvents()
        time.sleep(0.005)
    return cond()


def test_the_port_probe_answers_without_blocking(app):
    """La sonda vera, su una porta libera (mai 8777/8778)."""
    from PySide6.QtCore import QObject
    from accoach.livepanel_ui import _PortProbe
    parent = QObject()
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    got = []
    t0 = time.monotonic()
    _PortProbe(parent, port, got.append)
    assert time.monotonic() - t0 < 0.05          # torna subito
    assert _run_until(lambda: got) and got == [True]
    srv.close()
    got.clear()
    _PortProbe(parent, port, got.append)
    assert _run_until(lambda: got) and got == [False]


def test_no_socket_or_sqlite_wait_on_the_ui_thread(env, monkeypatch):
    """render_state e l'attesa del report con la sonda vera: nessun connect
    sincrono e nessun SQLite sul thread dell'interfaccia."""
    from accoach import livepanel_ui, netinfo
    win, panel, net, tmp = env
    _save_advice(tmp, "active")
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()                                  # una porta chiusa vera
    _cfg().web.port = port
    main_hits = []

    def on_main(what):
        if threading.current_thread() is threading.main_thread():
            main_hits.append(what)

    real_connect = sqlite3.connect
    monkeypatch.setattr(livepanel_ui.sqlite3, "connect",
                        lambda *a, **k: on_main("sqlite") or real_connect(*a, **k))
    real_cx, real_c = socket.socket.connect_ex, socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect_ex",
                        lambda s, *a: on_main("connect_ex") or real_cx(s, *a))
    monkeypatch.setattr(socket.socket, "connect",
                        lambda s, *a: on_main("connect") or real_c(s, *a))
    monkeypatch.setattr(netinfo, "port_open",
                        lambda *a, **k: on_main("port_open") or False)
    monkeypatch.setattr(livepanel_ui, "WEB_WAIT_S", 0.6)
    monkeypatch.delattr(panel, "_probe")          # la sonda vera

    panel.render_state(_states()["driving"])
    panel.render_state(_states()["finished"])
    _settle(panel)
    done = []
    panel._ensure_web(done.append)
    assert _run_until(lambda: done, timeout=5.0)
    assert done == [False]
    assert main_hits == []


# --- la rete di /health ----------------------------------------------------

def test_polling_runs_only_while_coach_live_runs(env):
    win, panel, _net, _tmp = env
    assert not panel._poll.isActive()
    proc = _live(win)
    assert panel._poll.isActive()
    assert panel.state.phase == "starting"      # nessuna risposta, ancora
    proc.exit()
    win._refresh_buttons()
    assert not panel._poll.isActive()
    assert panel.state.phase == "idle"


def test_a_reply_moves_the_panel(env):
    win, panel, _net, _tmp = env
    _live(win)
    panel._on_health({"connected": True, "car": CAR, "track": TRACK,
                      "saved_laps": 1, "laps_done": 1, "remote_clients": 1})
    assert panel.state.phase == "driving"
    assert panel.state.tablet_now is True
    for _ in range(3):
        panel._on_health(None)
    assert panel.state.phase == "silent"


def test_the_request_goes_to_health_with_a_short_timeout(env, monkeypatch):
    """La richiesta passa da QtNetwork, sulla porta del backend, e non aspetta
    oltre 1,5 s."""
    from accoach import livepanel_ui
    _win, panel, _net, _tmp = env
    gets = []

    class _Reply:
        class _Sig:
            def connect(self, fn):
                pass
        finished = _Sig()

    monkeypatch.setattr(panel._nam, "get", lambda req: gets.append(req) or _Reply())
    livepanel_ui.LivePanel._poll_once(panel)
    req = gets[0]
    assert req.url().toString() == "http://127.0.0.1:8777/health"
    assert req.transferTimeout() == livepanel_ui.HEALTH_TIMEOUT_MS <= 1500
    # Una richiesta ancora in volo non ne fa partire un'altra.
    livepanel_ui.LivePanel._poll_once(panel)
    assert len(gets) == 1


def test_no_http_on_the_ui_thread():
    src = (Path(__file__).resolve().parents[1] / "src" / "accoach"
           / "livepanel_ui.py").read_text(encoding="utf-8")
    bad = re.compile(
        r"^\s*(import|from)\s+(urllib|requests|http\.client|httpx)\b", re.M)
    assert not bad.search(src)
    # La sonda sincrona non si importa e non si chiama.
    assert not re.search(r"\bport_open\s*\(|import[^\n]*\bport_open\b", src)
    assert "QNetworkAccessManager" in src


# --- i testi ---------------------------------------------------------------

def test_every_live_text_speaks_both_languages_once():
    from accoach.i18n import LANGUAGES, _UI
    keys = [k for k in _UI if k.startswith("live.")]
    assert len(keys) >= 20
    for k in keys:
        for lang in LANGUAGES:
            assert _UI[k].get(lang), f"{k} manca in {lang}"
    # Mai la stessa frase in due posti, in nessuna delle due lingue.
    for lang in LANGUAGES:
        others = {v.get(lang) for k, v in _UI.items() if not k.startswith("live.")}
        seen = set()
        for k in keys:
            text = _UI[k][lang]
            assert text not in seen, (lang, k)
            assert text not in others, (lang, k)
            seen.add(text)


def test_finished_falls_back_to_health_when_the_catalog_has_no_laps(env):
    """Catalogo leggibile ma senza i giri della corsa (non ancora indicizzati):
    resta il conto di /health, senza validi ne' durata inventati."""
    _win, panel, _net, tmp = env
    _save_advice(tmp, "active")
    panel.render_state(_states()["finished"])
    _settle(panel)
    text = _joined(panel)
    assert "14 laps saved" in text
    assert not re.search(r"\d+ valid", text)
    assert not re.search(r"\d+ minutes?\b", text)


# --- i ritocchi della revisione finale -------------------------------------

def test_every_web_the_panel_starts_opens_no_browser_tab(env, monkeypatch):
    """Il `web` del pannello serve il QR e la Pagella: la scheda la apre il
    pannello quando serve, non `api.main` a ogni avvio (due schede per clic)."""
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    _cfg().lan = True
    proc = _live(win)                             # avvio con la LAN
    _stop_kills(monkeypatch, win, net, proc)
    panel.render_state(_states()["driving"])
    _click(panel, "liveFinish")                   # «Ho finito» col web giu'
    panel._stop_tick()
    later = time.monotonic() + livepanel_ui.WEB_WAIT_S + 1
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: later)
    panel._web_tick()
    win._children.clear()
    panel._open_here()                            # «Apri su questo PC»
    spawned = [c[1] for c in net.calls if c[0] == "spawn"]
    assert spawned and all(a == ("web", "--no-browser") for a in spawned), spawned
    # Il bottone «Analisi» dell'hub resta quello di sempre, col suo browser.
    assert ("web",) in {k for k, label, _b in win._actions
                        if label == "btn.analysis"}


def test_driving_keeps_the_tablet_step_until_it_is_done(env):
    """La telemetria puo' arrivare prima del tablet: il passo 2 non sparisce."""
    from PySide6.QtWidgets import QLabel, QPushButton
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    _cfg().lan = True
    st = PanelState("driving", car=CAR, track=TRACK, saved_laps=1, laps_done=1)
    panel.render_state(st)
    text = _joined(panel)
    assert t("live.s2") in text
    assert "192.168.1.23:8778/engineer" in text
    qr = panel.findChild(QLabel, "liveQr")
    assert qr is not None and _visible_in(qr, panel)
    names = [w.objectName() for w in panel.findChildren(QPushButton)
             if _visible_in(w, panel)]
    assert {"liveOpenHere", "liveSkip", "liveFinish"} <= set(names)
    # sopra il resto: il passo viene prima della combo e del bottone grande
    texts = _texts(panel)
    assert texts.index(t("live.s2")) < texts.index(t("live.finish"))
    # e col QR in piu' la pagina ci sta ancora
    panel.layout().activate()
    assert panel.minimumSizeHint().width() <= PAGE_W
    assert panel.sizeHint().height() <= PAGE_H, panel.sizeHint()
    # senza LAN la riga per accenderla, non il QR
    _cfg().lan = False
    panel.render_state(_more_laps(st))
    assert panel.findChild(QLabel, "liveQr") is None
    assert t("live.s2") in _joined(panel)
    # collegato (o saltato): il passo se ne va
    _cfg().lan = True
    panel.render_state(PanelState("driving", tablet_done=True, tablet_now=True,
                                  car=CAR, track=TRACK))
    assert t("live.s2") not in _joined(panel)
    assert panel.findChild(QLabel, "liveQr") is None


def _more_laps(st):
    from dataclasses import replace
    return replace(st, laps_done=(st.laps_done or 0) + 1)


def test_skip_from_the_driving_view(env):
    from accoach.i18n import t
    win, panel, _net, _tmp = env
    _cfg().lan = True
    _live(win)
    panel.render_state(PanelState("driving", car=CAR, track=TRACK))
    _click(panel, "liveSkip")
    assert t("live.s2") not in _joined(panel)
    assert t("live.tablet_skipped") in _joined(panel)


def test_starting_and_unreachable_are_not_silent(env):
    from accoach.i18n import t
    win, panel, _net, _tmp = env
    _live(win)
    assert panel.state.phase == "starting"
    text = _joined(panel)
    assert t("live.starting") in text
    assert t("live.silent") not in text
    panel.render_state(PanelState("unreachable"))
    text = _joined(panel)
    assert t("live.unreachable") in text
    assert t("live.silent") not in text and t("live.starting") not in text
    assert t("live.unreachable", "it").startswith(
        "Coach Live è acceso ma non risponde")


@pytest.mark.parametrize("lang", ["it", "en"])
def test_starting_and_unreachable_fit(env, lang):
    from accoach.config import set_language
    _win, panel, _net, _tmp = env
    set_language(lang)
    _cfg().lan = True
    for phase in ("before", "starting", "unreachable"):
        panel.render_state(PanelState(phase))
        # Il layout si ricalcola adesso, non al prossimo giro di eventi: senza,
        # `sizeHint` e' quello dello stato di prima. La larghezza che conta e'
        # la minima (le righe lunghe vanno a capo), l'altezza quella voluta.
        panel.layout().activate()
        assert panel.minimumSizeHint().width() <= PAGE_W, phase
        assert panel.sizeHint().height() <= PAGE_H, phase
        for text in _texts(panel):
            assert not re.search(r"\blive\.[a-z_]", text), (phase, text)


def test_a_run_started_without_lan_shows_no_qr_even_if_lan_comes_on(env):
    """Coach Live ascolta la rete solo se la LAN era accesa quando e' partito:
    accenderla dopo non basta, il QR porterebbe a una pagina che non risponde."""
    from PySide6.QtWidgets import QLabel, QPushButton
    from accoach.i18n import t
    win, panel, _net, _tmp = env
    _cfg().lan = False
    _live(win)
    panel.render_state(PanelState("before"))
    assert t("live.s2_lan_off") in _joined(panel)
    assert panel.findChild(QPushButton, "liveToDevices") is not None
    _cfg().lan = True                              # accesa a corsa iniziata
    panel.render_state(PanelState("before"))
    assert panel.findChild(QLabel, "liveQr") is None
    assert "192.168.1.23" not in _joined(panel)
    assert t("live.s2_lan_restart") in _joined(panel)
    # una corsa nuova, con la LAN accesa, ha il QR
    win._children.clear()
    win._refresh_buttons()
    _live(win)
    panel.render_state(PanelState("before"))
    assert panel.findChild(QLabel, "liveQr") is not None


def test_lan_texts_say_how_to_get_the_qr():
    from accoach.i18n import t
    it_off, en_off = t("live.s2_lan_off", "it"), t("live.s2_lan_off", "en")
    assert "Dispositivi" in it_off and "riavvia" in it_off.lower()
    assert "Devices" in en_off and "restart" in en_off.lower()
    assert "riavvia" in t("live.s2_lan_restart", "it").lower()
    assert "restart" in t("live.s2_lan_restart", "en").lower()


def test_the_closed_line_does_not_count_the_minute():
    """Dopo «Resto in pista» la scheda torna quando vuole: «da un minuto» non
    sarebbe piu' vero."""
    from accoach.i18n import t
    assert "minut" not in t("live.closed", "it")
    assert "minute" not in t("live.closed", "en")


def test_web_down_does_not_send_to_the_same_dead_page():
    from accoach.i18n import t
    assert "questo PC" not in t("live.s2_web_down", "it")
    assert "this PC" not in t("live.s2_web_down", "en")


def test_a_destroyed_bridge_does_not_raise_in_the_worker(env, monkeypatch):
    from accoach import livepanel_ui
    _win, panel, _net, tmp = env

    class _Dead:
        class done:
            @staticmethod
            def emit(_x):
                raise RuntimeError("Internal C++ object already deleted.")

    monkeypatch.setattr(panel, "_bridge", _Dead())
    monkeypatch.setattr(livepanel_ui, "read_catalog", lambda *a: None)
    panel._catalog_worker(None, tmp / "x.db", CAR, TRACK, "")  # non solleva


def test_the_starting_clock_begins_when_coach_live_starts(env, monkeypatch):
    """I 30 s dell'avvio contano da quando Coach Live parte, non dal primo
    poll andato a vuoto."""
    from accoach import livepanel, livepanel_ui
    win, panel, _net, _tmp = env
    now = [1000.0]
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: now[0])
    _live(win)
    now[0] += livepanel.STARTING_S + 1
    panel._on_health(None)
    assert panel.state.phase == "unreachable"
