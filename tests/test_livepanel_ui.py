"""Il pannello «In pista»: disegna lo stato che `livepanel` decide, e il clic
«Ho finito» ferma il coach prima di aprire la Pagella.

Le regole (quando il gioco e' chiuso, quando il coach non risponde) stanno in
`tests/test_livepanel.py`, senza Qt. Qui si prova il cablaggio: cosa compare in
ogni stato, l'ordine delle azioni, e che il pannello interroghi `/health` solo
mentre Coach Live gira. Nessun processo vero, nessuna porta vera: `_spawn`,
`port_open`, `webbrowser.open` e la rete sono finti.
"""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from accoach.livepanel import PanelState  # noqa: E402

# La pagina dell'hub: finestra da 900x600 meno la barra laterale da 210.
PAGE_W, PAGE_H = 900 - 210, 600
CAR, TRACK = "mclaren_720s_gt3", "imola"


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

    def port_open(self, port, *a, **k):
        self.calls.append(("port_open", port))
        return port in self.open_ports

    def spawn(self, args, console=False):
        self.calls.append(("spawn", tuple(args)))

    def browse(self, url, *a, **k):
        self.calls.append(("open", url))
        return True


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    from accoach import config, launcher, livepanel_ui
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    net = _Net()
    monkeypatch.setattr(livepanel_ui, "port_open", net.port_open)
    monkeypatch.setattr(launcher, "port_open", net.port_open)
    monkeypatch.setattr(livepanel_ui.webbrowser, "open", net.browse)
    monkeypatch.setattr(livepanel_ui, "device_urls", lambda port: {
        "report": f"http://192.168.1.23:{port}/",
        "engineer": f"http://192.168.1.23:{port}/engineer",
        "test": f"http://192.168.1.23:{port}/test"})
    monkeypatch.setattr(livepanel_ui, "laps_root", lambda: tmp_path / "laps")
    win = launcher.MainWindow()
    monkeypatch.setattr(win, "_spawn", net.spawn)
    panel = win._live_panel
    # Nessuna richiesta vera: il poll registra soltanto.
    monkeypatch.setattr(panel, "_poll_once", lambda: net.calls.append(("poll",)))
    yield win, panel, net, tmp_path
    win._children.clear()
    win._timer.stop()
    win._watch_timer.stop()
    panel._poll.stop()


def _cfg():
    from accoach.config import load_config
    return load_config()


def _texts(panel) -> list[str]:
    """I testi che il pannello mostra (etichette e bottoni non nascosti)."""
    from PySide6.QtWidgets import QLabel, QPushButton
    out = []
    for w in panel.findChildren(QLabel) + panel.findChildren(QPushButton):
        if not w.isHidden() and _visible_in(w, panel):
            out.append(w.text())
    return out


def _visible_in(w, panel) -> bool:
    """Visibile rispetto al pannello (la finestra non e' mai mostrata)."""
    p = w
    while p is not None and p is not panel:
        if p.isHidden():
            return False
        p = p.parentWidget()
    return True


def _joined(panel) -> str:
    return "\n".join(_texts(panel))


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
    go = panel.findChild(QPushButton, "liveToDevices")
    go.click()
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
    win._children.append((_FakeProc(), ["live"]))
    win._refresh_buttons()
    panel.findChild(QPushButton, "liveSkip").click()
    assert panel.findChild(QLabel, "liveQr") is None
    assert t("live.tablet_skipped") in _joined(panel)


def _save_advice(tmp, status):
    from accoach.recording.catalog import LapCatalog
    from accoach.recording.storage import _catalog_path
    with LapCatalog(_catalog_path(tmp / "laps")) as cat:
        cat.save_advice(CAR, TRACK, {"defect": "brake_early", "status": status,
                                     "corners": []})


def test_following_line_only_with_an_active_advice(env):
    from accoach.coaching.howto import defect_name
    from accoach.i18n import current_language
    _win, panel, _net, tmp = env
    name = defect_name("brake_early", current_language())
    st = _states()["driving"]

    panel.render_state(st)                      # nessun catalogo
    assert name not in _joined(panel)

    _save_advice(tmp, "proposed")               # proposto, non seguito
    panel.render_state(_states()["driving"])
    assert name not in _joined(panel)

    _save_advice(tmp, "active")
    panel.render_state(_states()["driving"])
    assert name in _joined(panel)


def test_the_panel_never_creates_a_catalog(env):
    """L'hub legge il consiglio, non fonda un archivio dei giri dove non c'e'."""
    _win, panel, _net, tmp = env
    panel.render_state(_states()["driving"])
    assert not (tmp / "laps").exists()


def _finish_button(panel):
    from PySide6.QtWidgets import QPushButton
    btn = panel.findChild(QPushButton, "liveFinish")
    assert btn is not None and _visible_in(btn, panel)
    return btn


def test_finish_stops_coach_then_opens_the_pagella(env, monkeypatch):
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    monkeypatch.setattr(win, "_stop_live_and_wait",
                        lambda timeout=5.0: net.calls.append(("stop", timeout))
                        or True)
    panel.render_state(_states()["driving"])
    net.calls.clear()
    _finish_button(panel).click()
    assert net.calls == [
        ("stop", 5.0), ("port_open", 8778),
        ("open", f"http://127.0.0.1:8778/?view=pagella&car={CAR}&track={TRACK}")]


def test_finish_from_the_finished_view_does_the_same(env, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    monkeypatch.setattr(win, "_stop_live_and_wait",
                        lambda timeout=5.0: net.calls.append(("stop",)) or True)
    panel.render_state(_states()["finished"])
    net.calls.clear()
    panel.findChild(QPushButton, "liveShow").click()
    assert net.calls[0] == ("stop",)
    assert net.calls[-1][0] == "open" and "view=pagella" in net.calls[-1][1]


def test_finish_without_a_combo_opens_the_plain_report(env, monkeypatch):
    from accoach.i18n import t
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    monkeypatch.setattr(win, "_stop_live_and_wait", lambda timeout=5.0: True)
    for st in (PanelState("driving", tablet_done=True),             # mai partito
               PanelState("driving", tablet_done=True, car=CAR, track=TRACK,
                          saved_laps=0, laps_done=0)):             # zero giri
        panel.render_state(st)
        assert t("live.no_laps") in _joined(panel)
        net.calls.clear()
        _finish_button(panel).click()
        assert net.calls[-1] == ("open", "http://127.0.0.1:8778/")


def test_with_laps_the_no_laps_line_is_absent(env):
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    panel.render_state(_states()["driving"])
    assert t("live.no_laps") not in _joined(panel)


def test_finish_starts_the_report_when_it_is_off(env, monkeypatch):
    win, panel, net, _tmp = env
    monkeypatch.setattr(win, "_stop_live_and_wait", lambda timeout=5.0: True)
    panel.render_state(_states()["driving"])
    net.calls.clear()
    _finish_button(panel).click()
    assert ("spawn", ("web",)) in net.calls
    assert not [c for c in net.calls if c[0] == "open"]   # non ancora
    assert panel._web_timer.isActive()                    # riprova, non blocca
    net.open_ports.add(8778)
    panel._web_tick()
    assert net.calls[-1] == (
        "open", f"http://127.0.0.1:8778/?view=pagella&car={CAR}&track={TRACK}")
    assert not panel._web_timer.isActive()


def test_a_report_that_never_starts_still_opens_and_says_so(env, monkeypatch):
    from accoach.i18n import t
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    monkeypatch.setattr(win, "_stop_live_and_wait", lambda timeout=5.0: True)
    panel.render_state(_states()["driving"])
    _finish_button(panel).click()
    clock = [livepanel_ui.time.monotonic() + livepanel_ui.WEB_WAIT_S + 1]
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: clock[0])
    panel._web_tick()
    assert net.calls[-1][0] == "open"
    assert t("live.report_late") in _joined(panel)


def test_a_coach_that_will_not_stop_is_said(env, monkeypatch):
    from accoach.i18n import t
    win, panel, net, _tmp = env
    net.open_ports.add(8778)
    monkeypatch.setattr(win, "_stop_live_and_wait", lambda timeout=5.0: False)
    panel.render_state(_states()["driving"])
    _finish_button(panel).click()
    assert net.calls[-1][0] == "open"
    assert t("live.stop_late") in _joined(panel)


def test_stay_on_track_goes_back_to_driving(env):
    from PySide6.QtWidgets import QPushButton
    from accoach.i18n import t
    win, panel, _net, _tmp = env
    win._children.append((_FakeProc(), ["live"]))
    win._refresh_buttons()
    panel.render_state(_states()["finished"])
    panel.findChild(QPushButton, "liveStay").click()
    assert panel.state.phase == "driving"
    assert t("live.finished") not in _joined(panel)


def test_silent_does_not_claim_the_tablet(env):
    """Durante il silenzio `tablet_now` e' l'ultimo valore visto, non adesso."""
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    panel.render_state(_states()["silent"])
    text = _joined(panel)
    assert t("live.silent") in text
    assert t("live.tablet_on") not in text
    assert "1:41" not in text                     # i dati non ci sono
    _finish_button(panel)                         # i bottoni si'


def test_driving_shows_the_tablet_now(env):
    from accoach.i18n import t
    _win, panel, _net, _tmp = env
    panel.render_state(_states()["driving"])
    assert t("live.tablet_on") in _joined(panel)
    panel.render_state(PanelState("driving", tablet_done=True, tablet_now=False,
                                  car=CAR, track=TRACK))
    assert t("live.tablet_on") not in _joined(panel)
    assert t("live.tablet_off") in _joined(panel)


def test_polling_runs_only_while_coach_live_runs(env):
    win, panel, _net, _tmp = env
    assert not panel._poll.isActive()
    proc = _FakeProc()
    win._children.append((proc, ["live"]))
    win._refresh_buttons()
    assert panel._poll.isActive()
    assert panel.state.phase == "before"
    proc.exit()
    win._refresh_buttons()
    assert not panel._poll.isActive()
    assert panel.state.phase == "idle"


def test_a_reply_moves_the_panel(env):
    win, panel, _net, _tmp = env
    win._children.append((_FakeProc(), ["live"]))
    win._refresh_buttons()
    panel._on_health({"connected": True, "car": CAR, "track": TRACK,
                      "saved_laps": 1, "laps_done": 1, "remote_clients": 1})
    assert panel.state.phase == "driving"
    assert panel.state.tablet_now is True
    for _ in range(3):
        panel._on_health(None)
    assert panel.state.phase == "silent"


def test_starting_coach_live_starts_the_report_for_the_tablet(env):
    win, panel, net, _tmp = env
    _cfg().lan = True
    win._children.append((_FakeProc(), ["live"]))
    win._refresh_buttons()
    assert ("spawn", ("web",)) in net.calls


def test_no_report_started_without_lan_or_when_already_up(env):
    win, panel, net, _tmp = env
    _cfg().lan = False
    proc = _FakeProc()
    win._children.append((proc, ["live"]))
    win._refresh_buttons()
    assert ("spawn", ("web",)) not in net.calls
    proc.exit()
    win._refresh_buttons()

    _cfg().lan = True
    net.open_ports.add(8778)
    win._children.append((_FakeProc(), ["live"]))
    win._refresh_buttons()
    assert ("spawn", ("web",)) not in net.calls


def test_a_report_that_does_not_start_is_said_in_step_two(env, monkeypatch):
    from accoach.i18n import t
    from accoach import livepanel_ui
    win, panel, net, _tmp = env
    _cfg().lan = True
    win._children.append((_FakeProc(), ["live"]))
    win._refresh_buttons()
    assert panel._web_timer.isActive()
    clock = [livepanel_ui.time.monotonic() + livepanel_ui.WEB_WAIT_S + 1]
    monkeypatch.setattr(livepanel_ui.time, "monotonic", lambda: clock[0])
    panel._web_tick()
    assert t("live.s2_web_down") in _joined(panel)
    assert not [c for c in net.calls if c[0] == "open"]   # nessun browser


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
    bad = re.compile(r"^\s*(import|from)\s+(urllib|requests|http\.client|httpx)\b",
                     re.M)
    assert not bad.search(src)
    assert "QNetworkAccessManager" in src


def test_every_live_text_speaks_both_languages_once():
    from accoach.i18n import LANGUAGES, _UI
    keys = [k for k in _UI if k.startswith("live.")]
    assert len(keys) >= 20
    for k in keys:
        for lang in LANGUAGES:
            assert _UI[k].get(lang), f"{k} manca in {lang}"
    # Mai la stessa frase in due posti.
    others = {v["it"] for k, v in _UI.items() if not k.startswith("live.")}
    seen = set()
    for k in keys:
        it = _UI[k]["it"]
        assert it not in seen, k
        assert it not in others, k
        seen.add(it)
