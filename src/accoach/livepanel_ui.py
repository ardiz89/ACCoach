"""Il pannello «In pista» dell'hub: dal via di Coach Live alla Pagella.

Disegna soltanto: lo stato (in avvio, prima di partire, in pista, sessione
finita, coach muto o mai risposto) lo decide :mod:`accoach.livepanel` da
`/health` e dal processo. Qui ci sono i tre momenti approvati col pilota, il clic
«Ho finito» (ferma il coach, poi apre la Pagella della combo guidata) e
l'interrogazione di `/health`.

L'hub sta dietro al gioco mentre il pilota guida: **non deve mai bloccarsi**.
Quindi niente che aspetta sul thread dell'interfaccia:
- `/health` con la rete asincrona di Qt, tetto 1,5 s, una richiesta alla volta,
  solo mentre Coach Live gira;
- «il report risponde?» con un `QTcpSocket` asincrono, non con `port_open`
  (che su una porta chiusa di Windows costa 0,3 s a chiamata);
- il catalogo (consiglio in corso, giri della corsa) letto in un thread, in sola
  lettura e con un timeout breve: SQLite puo' aspettare chi sta scrivendo;
- «Ho finito» chiede l'arresto e poi controlla con un timer che il processo sia
  morto, invece di aspettarlo.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import webbrowser
from dataclasses import replace
from datetime import datetime, timezone
from functools import partial

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
    QTcpSocket,
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
from .guard import lan_key
from .netinfo import device_urls
from .recording.storage import _catalog_path, _slug, laps_root

# Tetto di una richiesta a /health: sotto POLL_S, cosi' una risposta lenta non
# si accavalla alla successiva (che comunque non parte finche' c'e' questa).
HEALTH_TIMEOUT_MS = 1500
# Quanto si aspetta che il processo `web` appena acceso risponda.
WEB_WAIT_S = 5.0
_WEB_TICK_MS = 250
# Una sonda sulla porta del report: 127.0.0.1 risponde o rifiuta subito.
PROBE_TIMEOUT_MS = 400
# Quanto si aspetta che Coach Live muoia dopo «Ho finito».
STOP_WAIT_S = 5.0
_STOP_TICK_MS = 100
# Il catalogo in sola lettura: meglio «non lo so» che un'attesa lunga.
CATALOG_TIMEOUT_S = 0.5


def _bold(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold;")
    lbl.setWordWrap(True)
    return lbl


def _role(lbl: QLabel, role: str) -> QLabel:
    lbl.setProperty("role", role)
    return lbl


def _utc_iso(ts: float) -> str:
    # Lo stesso formato di `save_lap` (`recorded_utc`), cosi' il confronto
    # fra stringhe nel catalogo e' un confronto fra istanti.
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def read_catalog(db, car: str, track: str, since_utc: str) -> dict | None:
    """Il consiglio `active` della combo e i giri salvati da `since_utc`.

    Gira in un thread. Connessione in sola lettura (`mode=ro`): non crea il
    catalogo e non lo migra; e un timeout breve, perche' se Coach Live sta
    scrivendo un giro la risposta puo' aspettare il prossimo poll. Le chiavi
    sono normalizzate come le normalizza il catalogo (`_slug`). `None` se il
    catalogo non si legge.
    """
    try:
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True,
                               timeout=CATALOG_TIMEOUT_S)
    except (sqlite3.Error, ValueError, OSError):
        return None
    try:
        ck, tk = _slug(car), _slug(track)
        defect = None
        for (data,) in conn.execute(
                "SELECT data_json FROM advice WHERE car_key=? AND track_key=? "
                "ORDER BY accepted_utc, defect", (ck, tk)):
            try:
                d = json.loads(data)
            except ValueError:
                continue
            if d.get("status") == "active":
                defect = d.get("defect")
                break
        rows = conn.execute(
            "SELECT recorded_utc, lap_time_ms, valid FROM lap "
            "WHERE car_key=? AND track_key=? AND source='own' AND recorded_utc >= ? "
            "ORDER BY recorded_utc", (ck, tk, since_utc)).fetchall()
        total = len(rows)
        valid = sum(1 for r in rows if r[2] == 1)
        duration = None
        if rows:
            try:
                first = datetime.fromisoformat(rows[0][0]).timestamp()
                last = datetime.fromisoformat(rows[-1][0]).timestamp()
                # Dalla partenza del primo giro salvato alla fine dell'ultimo.
                duration = max(0.0, last - first + rows[0][1] / 1000.0)
            except (TypeError, ValueError):
                duration = None
        return {"defect": defect, "total": total, "valid": valid,
                "duration_s": duration}
    except sqlite3.Error:
        return None
    finally:
        conn.close()


class _Bridge(QObject):
    """Riporta il risultato di un thread sul thread dell'interfaccia."""

    done = Signal(object)


class _PortProbe(QObject):
    """Risponde qualcuno su 127.0.0.1:`port`? Senza aspettare: il risultato
    arriva a `cb(bool)` dal giro di eventi di Qt."""

    def __init__(self, parent: QObject, port: int, cb) -> None:
        super().__init__(parent)
        self._cb = cb
        self._done = False
        self._sock = QTcpSocket(self)
        self._sock.connected.connect(lambda: self._finish(True))
        self._sock.errorOccurred.connect(lambda _err: self._finish(False))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._finish(False))
        self._timer.start(PROBE_TIMEOUT_MS)
        self._sock.connectToHost("127.0.0.1", port)

    def _finish(self, up: bool) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._sock.abort()
        self.deleteLater()
        self._cb(up)


class LivePanel(QWidget):
    """La pagina «In pista». Con Coach Live spento: i bottoni di sempre e, sotto,
    i tre passi in anteprima. Acceso: il pannello del momento."""

    def __init__(self, hub) -> None:
        super().__init__()
        self._hub = hub
        self._tracker = LiveTracker()
        self.state = PanelState("idle")
        self._running = False
        self._run_started = time.time()
        # Cose che `PanelState` non porta: chi ha premuto «Salta» e se il
        # tablet si e' mai visto in questa corsa (per dire «si e' scollegato»
        # invece di «nessun tablet»).
        self._skipped = False
        self._tablet_seen = False
        # La LAN com'era quando la corsa e' partita: Coach Live apre la rete solo
        # allora, quindi accenderla dopo non rende raggiungibile il QR. `None`
        # fuori da una corsa (vale la configurazione di adesso).
        self._run_lan: bool | None = None
        # Le note sono chiavi, non testi: un cambio di lingua le ridice.
        self._notes: list[str] = []
        self._reply = None
        self._sig = None
        # Il processo `web`: chi aspetta che risponda, e se si sa che non c'e'.
        self._web_failed = False
        self._web_checking = False
        self._web_waiters: list = []
        self._web_deadline = 0.0
        self._probing = False
        # «Ho finito» in corso: l'indirizzo da aprire alla fine.
        self._finish_url: str | None = None
        self._stop_deadline = 0.0
        # Il catalogo letto in un thread: la chiave chiesta, quella in volo e
        # l'ultimo risultato (per quale chiave).
        self._cat_job = None
        self._cat_key = None
        self._cat_info: dict | None = None

        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._on_catalog)
        self._nam = QNetworkAccessManager(self)
        # /health e' sempre su 127.0.0.1: un proxy di sistema non c'entra.
        self._nam.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self._poll = QTimer(self)
        self._poll.setInterval(int(POLL_S * 1000))
        self._poll.timeout.connect(lambda: self._poll_once())
        self._web_timer = QTimer(self)
        self._web_timer.setInterval(_WEB_TICK_MS)
        self._web_timer.timeout.connect(self._web_tick)
        self._stop_timer = QTimer(self)
        self._stop_timer.setInterval(_STOP_TICK_MS)
        self._stop_timer.timeout.connect(self._stop_tick)

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
        self._note_lbl.setObjectName("liveNote")
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
            # L'orologio dell'avvio parte adesso, non al primo poll.
            self._tracker.begin(time.monotonic())
            self._run_started = time.time()
            self._skipped = self._tablet_seen = self._web_failed = False
            if self._finish_url is None:
                self._notes = []
            self._cat_key = self._cat_info = None
            self._run_lan = load_config().lan
            if self._run_lan:
                # Il QR punta alla pagina Ingegnere del processo `web`.
                self._ensure_web(lambda _up: None)
            self._poll.start()
            self.render_state(PanelState("starting"))
        else:
            self._poll.stop()
            self._run_lan = None
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
    def _probe(self, port: int, cb) -> None:
        _PortProbe(self, port, cb)

    def _web_child_alive(self) -> bool:
        return any(a and a[0] == "web" and p.poll() is None
                   for p, a in list(self._hub._children))

    def _ensure_web(self, then) -> None:
        """Fa in modo che il report risponda, poi chiama `then(su)`.

        Se la porta risponde gia' si usa com'e' (anche la `web --engineer` del
        pilota). Altrimenti si accende `web` — **una volta**: chi arriva mentre
        si aspetta si mette in coda, e un `web` nostro ancora vivo non si
        raddoppia — e si riprova fino a WEB_WAIT_S."""
        self._web_waiters.append(then)
        if self._web_checking:
            return
        self._web_checking = True
        port = load_config().web.port

        def first(up: bool) -> None:
            if up:
                self._web_resolve(True)
                return
            if not self._web_child_alive():
                # Senza browser: la scheda giusta (Pagella, Ingegnere) la apre
                # il pannello quando serve; quella di `web` sarebbe in piu'.
                self._hub._spawn(["web", "--no-browser"], False)
            self._web_deadline = time.monotonic() + WEB_WAIT_S
            self._web_timer.start()

        self._probe(port, first)

    def _web_tick(self) -> None:
        if self._probing:
            return
        self._probing = True

        def got(up: bool) -> None:
            self._probing = False
            if not self._web_checking:
                return
            if up:
                self._web_resolve(True)
            elif time.monotonic() >= self._web_deadline:
                self._web_resolve(False)

        self._probe(load_config().web.port, got)

    def _web_resolve(self, up: bool) -> None:
        self._web_timer.stop()
        self._web_checking = False
        self._web_failed = not up
        waiters, self._web_waiters = self._web_waiters, []
        for w in waiters:
            w(up)
        self._rerender()

    # --- i clic ---------------------------------------------------------------
    def _finish(self) -> None:
        """«Ho finito»: chiede l'arresto del coach, aspetta (con un timer) che
        sia morto, poi apre la Pagella della combo guidata. Senza auto, pista o
        giri salvati apre il report cosi' com'e'."""
        if self._finish_url is not None:
            return
        st = self.state
        base = f"http://127.0.0.1:{load_config().web.port}/"
        self._finish_url = (report_url(base, st.car, st.track)
                            if self._has_laps(st) else base)
        self._notes = []
        self._hub._stop_live()
        self._stop_deadline = time.monotonic() + STOP_WAIT_S
        self._stop_timer.start()
        self._rerender()

    def _stop_tick(self) -> None:
        if self._hub._live_running():
            if time.monotonic() < self._stop_deadline:
                return
            self._notes.append("live.stop_late")
        self._stop_timer.stop()
        self._ensure_web(self._open_report)

    def _open_report(self, up: bool) -> None:
        url, self._finish_url = self._finish_url, None
        # Si apre lo stesso: una pagina che non carica si ricarica, un bottone
        # che non fa niente no.
        if not up:
            self._notes.append("live.report_late")
        if url:
            webbrowser.open(url)
        self._rerender()

    def _open_here(self) -> None:
        url = f"http://127.0.0.1:{load_config().web.port}/engineer"
        self._ensure_web(lambda _up: webbrowser.open(url))

    def _skip(self) -> None:
        self._skipped = True
        self._tracker.skip_tablet()
        self.render_state(replace(self.state, tablet_done=True))

    def _stay(self) -> None:
        self._tracker.dismiss_finished()
        self.render_state(replace(self.state, phase="driving"))

    def _to_devices(self) -> None:
        self._hub._nav.setCurrentRow(self._hub._NAV.index("nav.devices"))

    # --- il catalogo, in un thread ------------------------------------------
    def _catalog(self, st: PanelState) -> dict | None:
        """L'ultima lettura del catalogo per questa combo (o None), e una nuova
        lettura in un thread se i file del catalogo sono cambiati.

        Il controllo e' uno `stat` (mtime e dimensione di `catalog.db` e del
        suo `-wal`): un giro salvato o un consiglio accettato lo cambiano, una
        risposta di /health no."""
        if not st.car or not st.track:
            return None
        db = _catalog_path(laps_root())
        key = [st.car, st.track, self._run_started]
        for p in (db, db.with_name(db.name + "-wal")):
            try:
                s = p.stat()
                key += [s.st_mtime_ns, s.st_size]
            except OSError:
                key += [None, None]
        if key[3] is None:              # nessun catalogo: non lo si crea
            return None
        if key != self._cat_key and self._cat_job is None:
            self._cat_job = key
            since = _utc_iso(self._run_started)
            threading.Thread(
                target=self._catalog_worker,
                args=(key, db, st.car, st.track, since),
                name="hone-livepanel-catalog", daemon=True).start()
        if self._cat_key is not None and self._cat_key[:3] == key[:3]:
            return self._cat_info
        return None

    def _catalog_worker(self, key, db, car, track, since) -> None:
        try:
            info = read_catalog(db, car, track, since)
        except Exception:   # noqa: BLE001 - un catalogo illeggibile = niente
            info = None
        try:
            self._bridge.done.emit((key, info))
        except RuntimeError:
            # L'hub si e' chiuso mentre il thread leggeva: il ponte e' gia'
            # distrutto e non c'e' piu' nessuno a cui consegnare.
            pass

    def _on_catalog(self, result) -> None:
        key, info = result
        self._cat_job = None
        self._cat_key, self._cat_info = key, info
        self._rerender()

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
        info = (self._catalog(state) if state.phase in ("driving", "finished")
                else None)
        cfg = load_config()
        sig = (state, info, self._skipped, self._tablet_seen, self._web_failed,
               self._finish_url, tuple(self._notes), cfg.lan, self._run_lan,
               cfg.web.port, current_language())
        if sig == self._sig:
            return
        self._sig = sig

        self._idle.setVisible(state.phase == "idle")
        self._clear_body()
        draw = getattr(self, f"_draw_{state.phase}", self._draw_idle)
        draw(state, info)
        # Durante «Ho finito» il pannello torna ai bottoni (il coach e' fermo),
        # ma la riga resta: il report sta arrivando.
        lines = [t(k) for k in self._notes]
        if self._finish_url is not None:
            lines.append(t("live.report_wait"))
        self._note_lbl.setText(" ".join(lines))
        self._note_lbl.setVisible(bool(lines))

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
            return _role(QLabel(t("live.tablet_on")), "good")
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
        if self._finish_url is not None:
            btn.setEnabled(False)
        elif sub:
            self._add(_hint(t(sub)))

    def _draw_idle(self, st: PanelState, _info) -> None:
        self._body_lay.addSpacing(8)
        self._add(_hint(t("live.preview")))
        for i, key in enumerate(("live.s1", "live.s2", "live.s3"), 1):
            self._add(self._step(str(i), t(key), dim=True))

    def _draw_before(self, st: PanelState, _info,
                     coach: QWidget | None = None) -> None:
        """I tre passi. `coach` e' la riga del passo 1 quando il coach non ha
        ancora risposto (in avvio, o acceso ma muto da sempre): allora il passo
        non si spunta."""
        self._header("live.before")
        if coach is None:
            self._add(self._step("✓", t("live.s1"), _hint(t("live.s1_sub")),
                                 done=True))
        else:
            self._add(self._step("1", t("live.s1"), coach))
        if st.tablet_done:
            self._add(self._step("✓", t("live.s2"), self._tablet_line(st),
                                 done=True))
        else:
            self._add(self._step("2", t("live.s2"), *self._tablet_how()))
        self._add(self._step("3", t("live.s3"), _hint(t("live.s3_sub"))))

    def _draw_starting(self, st: PanelState, info) -> None:
        self._draw_before(st, info, _hint(t("live.starting")))

    def _draw_unreachable(self, st: PanelState, info) -> None:
        self._draw_before(st, info, _role(_hint(t("live.unreachable")), "bad"))

    def _tablet_how(self) -> list[QWidget]:
        """Come si collega il tablet: il QR se la corsa e' partita con la rete
        locale attiva, altrimenti la strada per attivarla (e riavviare).
        «Apri su questo PC» c'e' in tutti i casi."""
        cfg = load_config()
        lan = cfg.lan if self._run_lan is None else self._run_lan
        out: list[QWidget] = []
        buttons = [self._button("live.open_here", "liveOpenHere", self._open_here)]
        if not lan and cfg.lan:
            # Accesa a corsa iniziata: Coach Live non ascolta la rete finche'
            # non riparte, e un QR porterebbe a una pagina muta.
            out.append(_hint(t("live.s2_lan_restart")))
        elif not lan:
            out.append(_hint(t("live.s2_lan_off")))
            buttons.insert(0, self._button("live.s2_to_devices", "liveToDevices",
                                           self._to_devices))
        else:
            # Con la chiave del Wi-Fi, come i QR della pagina Dispositivi.
            urls = device_urls(cfg.web.port, key=lan_key())
            if not urls:
                out.append(_hint(t("live.s2_no_ip")))
            else:
                url = urls["tablet"]
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
            # Il tempo sul giro resta come lo scrive il gioco («1:41.882»),
            # anche in italiano: è la regola dei tempi del 21/10.
            laps += " · " + t("live.best", time=st.best)
        self._add(_hint(laps))

    def _draw_driving(self, st: PanelState, info) -> None:
        self._header("live.driving")
        if st.tablet_done:
            self._add(self._tablet_line(st))
        else:
            # La telemetria e' arrivata prima del tablet: il passo resta finche'
            # il tablet non si collega o il pilota non lo salta.
            self._add(self._step("2", t("live.s2"), *self._tablet_how()))
        self._combo(st)
        defect = (info or {}).get("defect")
        if defect:
            from .coaching.howto import defect_name
            try:
                name = defect_name(defect, current_language())
            except KeyError:
                name = None
            if name:
                self._add(_bold(t("live.following", name=name)))
                self._add(_hint(t("live.following_sub")))
        self._finish_block(st, "live.finish", "liveFinish", "live.finish_sub")

    @staticmethod
    def _minutes(seconds: float) -> str:
        n = max(1, round(seconds / 60.0))
        return t("live.minute_one") if n == 1 else t("live.minutes", n=n)

    def _draw_finished(self, st: PanelState, info) -> None:
        self._header("live.finished")
        # Il catalogo sa validi e durata; se non risponde (o non ha ancora
        # indicizzato i giri) resta il conto di /health, senza inventare il resto.
        cat_total = (info or {}).get("total") or 0
        total = cat_total or st.saved_laps or 0
        if total:
            saved = (t("live.saved_one") if total == 1
                     else t("live.saved", n=total))
            if cat_total:
                v = info.get("valid", 0)
                saved += ", " + (t("live.valid_one") if v == 1
                                 else t("live.valid", n=v))
            self._add(_role(QLabel(saved), "good"))
            where = [x for x in (st.track, st.car) if x]
            if cat_total and info.get("duration_s") is not None:
                where.append(self._minutes(info["duration_s"]))
            self._add(_hint(" · ".join(where)))
        self._add(_hint(t("live.closed")))
        self._finish_block(st, "live.show", "liveShow")
        self._add(self._button("live.stay", "liveStay", self._stay))

    def _draw_silent(self, st: PanelState, _info) -> None:
        # Al posto dei dati, che sono quelli dell'ultima risposta e non di
        # adesso: anche la riga del tablet, che direbbe «collegato» a vuoto.
        self._header("live.driving")
        self._add(_role(_hint(t("live.silent")), "bad"))
        self._finish_block(st, "live.finish", "liveFinish", "live.finish_sub")
