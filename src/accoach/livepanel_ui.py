"""Il pannello «In pista» dell'hub: dal via di Coach Live alla Pagella.

Disegna soltanto: lo stato (prima di partire, in pista, sessione finita, coach
muto) lo decide :mod:`accoach.livepanel` da `/health` e dal processo. Qui ci
sono i tre momenti approvati col pilota, il clic «Ho finito» (ferma il coach,
poi apre la Pagella della combo guidata) e l'interrogazione di `/health`.

L'hub sta dietro al gioco mentre il pilota guida: non deve mai bloccarsi. Per
questo `/health` si chiede con la rete asincrona di Qt, con un tetto di 1,5 s,
una richiesta alla volta e solo mentre Coach Live gira; e l'attesa del report
che parte e' un timer che riprova, non un ciclo che aspetta.
"""
from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import replace
from functools import partial

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import load_config
from .hubgate import STOP_LIVE
from .i18n import current_language, t
from .launcher import _hint, _qr_image
from .livepanel import POLL_S, LiveTracker, PanelState, parse_health, report_url
from .netinfo import device_urls, port_open
from .recording.storage import _catalog_path, laps_root

# Tetto di una richiesta a /health: sotto POLL_S, cosi' una risposta lenta non
# si accavalla alla successiva (che comunque non parte finche' c'e' questa).
HEALTH_TIMEOUT_MS = 1500
# Quanto si aspetta che il processo `web` appena acceso risponda.
WEB_WAIT_S = 5.0
_WEB_TICK_MS = 250


def _bold(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold;")
    lbl.setWordWrap(True)
    return lbl


def _role(lbl: QLabel, role: str) -> QLabel:
    lbl.setProperty("role", role)
    return lbl


def _best(text: str) -> str:
    """Il tempo come lo scrive il gioco («1:41.882»), con la virgola in italiano."""
    return text.replace(".", ",") if current_language() == "it" else text


class LivePanel(QWidget):
    """La pagina «In pista». Con Coach Live spento: i bottoni di sempre e, sotto,
    i tre passi in anteprima. Acceso: il pannello del momento."""

    def __init__(self, hub) -> None:
        super().__init__()
        self._hub = hub
        self._tracker = LiveTracker()
        self.state = PanelState("idle")
        self._running = False
        # Cose che `PanelState` non porta: chi ha premuto «Salta» e se il
        # tablet si e' mai visto in questa corsa (per dire «si e' scollegato»
        # invece di «nessun tablet»).
        self._skipped = False
        self._tablet_seen = False
        self._web_failed = False
        self._pending_url: str | None = None
        self._web_deadline = 0.0
        self._note = ""
        self._reply = None
        self._advice_stamp = None
        self._advice_name: str | None = None
        self._sig = None

        self._nam = QNetworkAccessManager(self)
        # /health e' sempre su 127.0.0.1: un proxy di sistema non c'entra.
        self._nam.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self._poll = QTimer(self)
        self._poll.setInterval(int(POLL_S * 1000))
        self._poll.timeout.connect(lambda: self._poll_once())
        self._web_timer = QTimer(self)
        self._web_timer.setInterval(_WEB_TICK_MS)
        self._web_timer.timeout.connect(self._web_tick)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel(t("nav.live"))
        title.setProperty("role", "title")
        title.setProperty("i18nKey", "nav.live")
        root.addWidget(title)

        # I bottoni di sempre. Registrati nell'hub, che li accende e li spegne:
        # per questo stanno fuori dalla parte che si ridisegna.
        self._idle = QWidget()
        il = QVBoxLayout(self._idle)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(12)
        il.addWidget(hub.action_button("btn.coach_live", ["live"], accent=True))
        il.addWidget(hub.action_button("btn.coach_live_demo", ["live", "--demo"]))
        il.addWidget(_hint(t("ui.tip_borderless"), key="ui.tip_borderless"))
        root.addWidget(self._idle)

        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        self._body_lay.setSpacing(10)
        root.addWidget(self._body)

        self._note_lbl = _hint("")
        root.addWidget(self._note_lbl)

        # Il vecchio «Ferma Coach Live», piccolo: l'hub lo mostra solo mentre
        # Coach Live gira.
        stop = hub.special_button("live.stop_quiet", STOP_LIVE, hub._stop_live)
        stop.setObjectName("liveStopQuiet")
        stop.setMinimumHeight(28)
        row = QHBoxLayout()
        row.addWidget(stop)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)

        self.render_state(self.state)

    # --- il processo e /health --------------------------------------------
    def sync(self, live: bool) -> None:
        """Chiamato dall'hub a ogni giro del suo poll: accende e spegne il
        pannello quando Coach Live parte o finisce."""
        if live == self._running:
            return
        self._running = live
        # Una corsa nuova parte pulita: niente di quella prima.
        self._tracker.feed(None, time.monotonic(), False)
        if live:
            self._skipped = self._tablet_seen = self._web_failed = False
            self._note = ""
            self._advice_stamp = None
            self._start_web_for_tablet()
            self._poll.start()
            self.render_state(PanelState("before"))
        else:
            self._poll.stop()
            self.render_state(PanelState("idle"))

    def _poll_once(self) -> None:
        if self._reply is not None:      # quella di prima e' ancora in volo
            return
        port = load_config().server.port
        req = QNetworkRequest(QUrl(f"http://127.0.0.1:{port}/health"))
        req.setTransferTimeout(HEALTH_TIMEOUT_MS)
        reply = self._nam.get(req)
        self._reply = reply
        reply.finished.connect(partial(self._on_reply, reply))

    def _on_reply(self, reply) -> None:
        if reply is self._reply:
            self._reply = None
        data = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except ValueError:
                data = None
        reply.deleteLater()
        self._on_health(data)

    def _on_health(self, data) -> None:
        """Una risposta di /health (o la sua mancanza, `None`)."""
        if not self._running:
            return
        self.render_state(self._tracker.feed(parse_health(data),
                                             time.monotonic(), True))

    # --- il processo `web` --------------------------------------------------
    def _start_web_for_tablet(self) -> None:
        """Il QR punta alla pagina Ingegnere del processo `web`: con la rete
        locale attiva lo si accende, se non c'e' gia'."""
        cfg = load_config()
        if cfg.lan and not port_open(cfg.web.port):
            self._hub._spawn(["web"], False)
            self._start_web_wait()

    def _start_web_wait(self) -> None:
        self._web_deadline = time.monotonic() + WEB_WAIT_S
        self._web_timer.start()

    def _web_tick(self) -> None:
        if port_open(load_config().web.port):
            self._web_timer.stop()
            self._web_failed = False
            self._web_done(True)
        elif time.monotonic() >= self._web_deadline:
            self._web_timer.stop()
            self._web_failed = True
            self._web_done(False)

    def _web_done(self, up: bool) -> None:
        url, self._pending_url = self._pending_url, None
        if url is not None:
            # Si apre lo stesso: una pagina che non carica si ricarica, un
            # bottone che non fa niente no.
            if not up:
                self._note = " ".join(x for x in (self._note, t("live.report_late")) if x)
            webbrowser.open(url)
        self._rerender()

    def _open_when_up(self, url: str) -> None:
        port = load_config().web.port
        if port_open(port):
            webbrowser.open(url)
            self._rerender()
            return
        self._hub._spawn(["web"], False)
        self._pending_url = url
        self._start_web_wait()
        self._rerender()

    # --- i clic ---------------------------------------------------------------
    def _finish(self) -> None:
        """«Ho finito»: ferma il coach, poi apre la Pagella della combo guidata.
        Senza auto, pista o giri salvati apre il report cosi' com'e'."""
        st = self.state
        stopped = self._hub._stop_live_and_wait(5.0)
        self._note = "" if stopped else t("live.stop_late")
        base = f"http://127.0.0.1:{load_config().web.port}/"
        url = report_url(base, st.car, st.track) if self._has_laps(st) else base
        self._open_when_up(url)

    def _open_here(self) -> None:
        self._open_when_up(f"http://127.0.0.1:{load_config().web.port}/engineer")

    def _skip(self) -> None:
        self._skipped = True
        self._tracker.skip_tablet()
        self.render_state(replace(self.state, tablet_done=True))

    def _stay(self) -> None:
        self._tracker.dismiss_finished()
        self.render_state(replace(self.state, phase="driving"))

    def _to_devices(self) -> None:
        keys = [k for k, _glyph in self._hub._NAV]
        self._hub._nav.setCurrentRow(keys.index("nav.devices"))

    # --- il consiglio in corso -----------------------------------------------
    def _following(self, st: PanelState) -> str | None:
        """Il nome del difetto del consiglio `active` di questa combo, o None.

        Il catalogo si riapre solo quando i suoi file cambiano (un giro salvato,
        un consiglio accettato), non a ogni risposta di /health: e' SQLite sul
        thread dell'interfaccia. E non si crea mai: l'hub legge, non fonda un
        archivio dei giri."""
        if not st.car or not st.track:
            return None
        db = _catalog_path(laps_root())
        stamp = [st.car, st.track]
        for p in (db, db.with_name(db.name + "-wal")):
            try:
                s = p.stat()
                stamp += [s.st_mtime_ns, s.st_size]
            except OSError:
                stamp += [None, None]
        if stamp == self._advice_stamp:
            return self._advice_name
        self._advice_stamp = stamp
        self._advice_name = None
        if stamp[2] is None:
            return None
        try:
            from .coaching.advice import ACTIVE
            from .coaching.howto import defect_name
            from .recording.catalog import LapCatalog

            # Le chiavi le normalizza il catalogo (`_slug`): auto e pista
            # passano come le da' il gioco.
            with LapCatalog(db) as cat:
                advice = cat.load_advice(st.car, st.track)
            active = next((a for a in advice if a.get("status") == ACTIVE), None)
            if active is not None:
                self._advice_name = defect_name(active["defect"], current_language())
        except Exception:   # noqa: BLE001 - un catalogo illeggibile = nessun consiglio
            self._advice_name = None
        return self._advice_name

    # --- il disegno -----------------------------------------------------------
    @staticmethod
    def _has_laps(st: PanelState) -> bool:
        return bool(st.car and st.track and st.saved_laps)

    def retranslate(self) -> None:
        self._rerender()

    def _rerender(self) -> None:
        self._sig = None
        self.render_state(self.state)

    def render_state(self, state: PanelState) -> None:
        """Disegna `state`. Non ridisegna se nulla di visibile e' cambiato: il
        poll arriva ogni 2 s e il QR non va rifatto ogni volta."""
        self.state = state
        if state.tablet_now:
            self._tablet_seen = True
        following = self._following(state) if state.phase == "driving" else None
        cfg = load_config()
        sig = (state, following, self._skipped, self._tablet_seen,
               self._web_failed, self._pending_url, self._note, cfg.lan,
               cfg.web.port, current_language())
        if sig == self._sig:
            return
        self._sig = sig

        self._idle.setVisible(state.phase == "idle")
        self._clear_body()
        draw = getattr(self, f"_draw_{state.phase}", self._draw_idle)
        draw(state, following)
        self._note_lbl.setText(self._note)
        self._note_lbl.setVisible(bool(self._note))

    def _clear_body(self) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # Fuori dall'albero subito, non al prossimo giro di eventi.
                w.setParent(None)
                w.deleteLater()

    def _add(self, w: QWidget) -> QWidget:
        self._body_lay.addWidget(w)
        return w

    def _header(self, key: str) -> None:
        self._add(_role(QLabel(t(key)), "headline"))

    def _step(self, mark: str, title: str, *extra: QWidget,
              done: bool = False, dim: bool = False) -> QWidget:
        """Un passo: il segno (✓ o il numero), il titolo, e sotto quello che
        serve per farlo."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        m = QLabel(mark)
        m.setFixedWidth(22)
        m.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        if done:
            _role(m, "good")
        elif dim:
            _role(m, "muted")
        else:
            m.setStyleSheet("font-weight: bold;")
        h.addWidget(m)
        col = QVBoxLayout()
        col.setSpacing(4)
        head = _role(QLabel(title), "muted") if dim else _bold(title)
        col.addWidget(head)
        for x in extra:
            col.addWidget(x)
        h.addLayout(col, 1)
        return w

    def _tablet_line(self, st: PanelState) -> QLabel:
        """Lo stato del tablet adesso, non quello del passo 2."""
        seen = self._tablet_seen or (st.tablet_done and not self._skipped)
        if st.tablet_now:
            return _role(QLabel("✓ " + t("live.tablet_on")), "good")
        if seen:
            return _role(_hint(t("live.tablet_off")), "bad")
        if self._skipped:
            return _hint(t("live.tablet_skipped"))
        return _hint(t("live.tablet_none"))

    def _button(self, key: str, name: str, handler, *, accent: bool = False,
                height: int = 36) -> QPushButton:
        b = QPushButton(t(key))
        b.setObjectName(name)
        b.setMinimumHeight(height)
        if accent:
            b.setProperty("accent", True)
        b.clicked.connect(lambda: handler())
        return b

    def _row(self, *widgets: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for x in widgets:
            h.addWidget(x)
        h.addStretch(1)
        return w

    def _finish_block(self, st: PanelState, key: str, name: str,
                      sub: str | None = None) -> None:
        if not self._has_laps(st):
            self._add(_hint(t("live.no_laps")))
        btn = self._add(self._button(key, name, self._finish, accent=True,
                                     height=52))
        if self._pending_url is not None:
            btn.setEnabled(False)
            self._add(_hint(t("live.report_wait")))
        elif sub:
            self._add(_hint(t(sub)))

    def _draw_idle(self, st: PanelState, _following) -> None:
        self._body_lay.addSpacing(8)
        self._add(_hint(t("live.preview")))
        for i, key in enumerate(("live.s1", "live.s2", "live.s3"), 1):
            self._add(self._step(str(i), t(key), dim=True))

    def _draw_before(self, st: PanelState, _following) -> None:
        self._header("live.before")
        self._add(self._step("✓", t("live.s1"), _hint(t("live.s1_sub")),
                             done=True))
        if st.tablet_done:
            self._add(self._step("✓", t("live.s2"), self._tablet_line(st),
                                 done=True))
        else:
            self._add(self._step("2", t("live.s2"), *self._tablet_how()))
        self._add(self._step("3", t("live.s3"), _hint(t("live.s3_sub"))))

    def _tablet_how(self) -> list[QWidget]:
        """Come si collega il tablet: il QR con la rete locale attiva, altrimenti
        la strada per attivarla. «Apri su questo PC» c'e' in tutti e due i casi."""
        cfg = load_config()
        out: list[QWidget] = []
        buttons = [self._button("live.open_here", "liveOpenHere", self._open_here)]
        if not cfg.lan:
            out.append(_hint(t("live.s2_lan_off")))
            buttons.insert(0, self._button("live.s2_to_devices", "liveToDevices",
                                           self._to_devices))
        else:
            urls = device_urls(cfg.web.port)
            if not urls:
                out.append(_hint(t("live.s2_no_ip")))
            else:
                url = urls["engineer"]
                qr = _qr_image(url, scale=4)
                qr.setObjectName("liveQr")
                addr = url.split("://", 1)[-1]
                side = QWidget()
                v = QVBoxLayout(side)
                v.setContentsMargins(0, 0, 0, 0)
                v.addWidget(_hint(t("live.s2_scan", addr=addr)))
                v.addStretch(1)
                pair = QWidget()
                h = QHBoxLayout(pair)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(12)
                h.addWidget(qr, 0, Qt.AlignTop)
                h.addWidget(side, 1)
                out.append(pair)
            if self._web_failed:
                out.append(_role(_hint(t("live.s2_web_down")), "bad"))
        buttons.append(self._button("live.skip", "liveSkip", self._skip))
        out.append(self._row(*buttons))
        return out

    def _combo(self, st: PanelState) -> None:
        if not (st.car or st.track):
            return
        self._add(_bold(" · ".join(x for x in (st.track, st.car) if x)))
        n = st.laps_done or 0
        laps = (t("live.no_lap_yet") if n <= 0 else
                t("live.laps_one") if n == 1 else t("live.laps", n=n))
        if st.best:
            laps += " · " + t("live.best", time=_best(st.best))
        self._add(_hint(laps))

    def _draw_driving(self, st: PanelState, following) -> None:
        self._header("live.driving")
        self._add(self._tablet_line(st))
        self._combo(st)
        if following:
            self._add(_bold("▶ " + t("live.following", name=following)))
            self._add(_hint(t("live.following_sub")))
        self._finish_block(st, "live.finish", "liveFinish", "live.finish_sub")

    def _draw_finished(self, st: PanelState, _following) -> None:
        self._header("live.finished")
        if st.saved_laps:
            saved = (t("live.saved_one") if st.saved_laps == 1
                     else t("live.saved", n=st.saved_laps))
            self._add(_role(QLabel("✓ " + saved), "good"))
            self._add(_hint(" · ".join(x for x in (st.track, st.car) if x)))
        self._add(_hint(t("live.closed")))
        self._finish_block(st, "live.show", "liveShow")
        self._add(self._button("live.stay", "liveStay", self._stay))

    def _draw_silent(self, st: PanelState, _following) -> None:
        # Al posto dei dati, che sono quelli dell'ultima risposta e non di
        # adesso: anche la riga del tablet, che direbbe «collegato» a vuoto.
        self._header("live.driving")
        self._add(_role(_hint(t("live.silent")), "bad"))
        self._finish_block(st, "live.finish", "liveFinish", "live.finish_sub")
