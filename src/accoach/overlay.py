"""On-screen overlay — a glanceable HUD drawn over the game.

A thin WebSocket client of :mod:`accoach.server`: it draws a delta bar, the
predicted/reference lap times and the current coaching cue, and nothing else.
While braking at 200 km/h you read it as colour and motion, not text.

    python -m accoach.overlay                 # connects to ws://127.0.0.1:8777/ws

Requirements / caveats
----------------------
* Needs PySide6 (``pip install PySide6``) — it's an optional frontend dep.
* A transparent always-on-top window only draws over the game in **borderless /
  windowed-fullscreen** mode, never over exclusive fullscreen (set the game to
  Borderless). This is how SimHub / CrewChief overlays work too.
* The window is click-through by default so it never steals input from the game;
  pass ``--interactive`` to make it clickable/movable, or just close the terminal
  that launched it (Ctrl+C) to quit.

The drawing uses ``QWebSocket`` so the socket lives on Qt's event loop — no extra
threads — and reconnects automatically if the backend isn't up yet.
"""

from __future__ import annotations

import json
import signal
import sys
import time

try:
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QColor, QFont, QPainter
    from PySide6.QtWebSockets import QWebSocket
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:  # pragma: no cover - optional dependency
    print("This overlay needs PySide6.  Install it with:  pip install PySide6")
    raise SystemExit(1)

DEFAULT_URL = "ws://127.0.0.1:8777/ws"
RECONNECT_MS = 2000
CUE_HOLD_S = 1.8          # how long a cue stays on screen before fading out
DELTA_CLAMP_S = 1.0       # bar is full at ±1.0 s

_GREEN = QColor(0x22, 0xDD, 0x66)
_RED = QColor(0xFF, 0x3B, 0x30)
_AMBER = QColor(0xFF, 0xB0, 0x20)
_WHITE = QColor(0xF0, 0xF0, 0xF0)
_GREY = QColor(0xAA, 0xAA, 0xAA)
_DARK = QColor(0, 0, 0, 130)         # semi-transparent backing pill


class Overlay(QWidget):
    def __init__(self, url: str | None = None, interactive: bool = False) -> None:
        super().__init__()
        self._state: dict = {}
        self._cue: dict | None = None
        self._cue_at: float = -1e9

        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if not interactive:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if not interactive:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.resize(560, 232)
        self._place_top_center()

        # WebSocket client on the Qt event loop — only when a URL is given.
        # In-process callers feed it via apply_state() instead.
        self._ws: QWebSocket | None = None
        if url:
            self._ws = QWebSocket()
            self._ws.textMessageReceived.connect(self._on_message)
            self._ws.disconnected.connect(self._schedule_reconnect)
            self._url = QUrl(url)
            self._connect()

        # Repaint steadily so the cue fade is smooth even between messages.
        self._repaint = QTimer(self)
        self._repaint.timeout.connect(self.update)
        self._repaint.start(33)  # ~30 fps

    def apply_state(self, data: dict) -> None:
        """Feed a state dict directly (in-process) — same path as a WS message."""
        self._state = data
        cue = data.get("cue")
        if cue:
            self._cue = cue
            self._cue_at = time.monotonic()

    # --- placement ---------------------------------------------------------
    def _place_top_center(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 24)

    # --- websocket ---------------------------------------------------------
    def _connect(self) -> None:
        self._ws.open(self._url)

    def _schedule_reconnect(self) -> None:
        QTimer.singleShot(RECONNECT_MS, self._connect)

    def _on_message(self, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        self.apply_state(data)

    # --- painting ----------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        st = self._state
        w = self.width()

        if not st or not st.get("connected"):
            self._draw_pill(p, "ACCoach · in attesa del gioco…", _GREY, y=40)
            return

        delta = st.get("delta")
        if delta is None:
            self._draw_pill(p, "REC ● sto imparando il giro di riferimento…",
                            _AMBER, y=40)
        else:
            self._draw_delta(p, delta, w)

        self._draw_cue(p, w)
        self._draw_focus(p, w)

    def _draw_delta(self, p: QPainter, delta: dict, w: int) -> None:
        ahead = delta.get("ahead", False)
        colour = _GREEN if ahead else _RED

        # Header: reference + predicted lap.
        self._set_font(p, 12)
        p.setPen(_GREY)
        header = f"PB {delta.get('reference', '--')}    PRED ▸ {delta.get('predicted', '--')}"
        p.drawText(0, 18, w, 18, Qt.AlignHCenter, header)

        # Delta bar, centred on zero.
        bar_w, bar_h, y = 380, 18, 60
        x0 = (w - bar_w) // 2
        cx = x0 + bar_w // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(60, 60, 60, 160))
        p.drawRoundedRect(x0, y, bar_w, bar_h, 4, 4)

        frac = max(-1.0, min(1.0, delta.get("s", 0.0) / DELTA_CLAMP_S))
        fill = int(abs(frac) * (bar_w // 2))
        p.setBrush(colour)
        if frac >= 0:  # slower -> fill right
            p.drawRoundedRect(cx, y, fill, bar_h, 4, 4)
        else:          # faster -> fill left
            p.drawRoundedRect(cx - fill, y, fill, bar_h, 4, 4)
        p.setPen(_WHITE)
        p.drawLine(cx, y - 3, cx, y + bar_h + 3)

        # Big delta number, with room so it never clips into the cue pill.
        self._set_font(p, 34, bold=True)
        p.setPen(colour)
        p.drawText(0, y + bar_h + 12, w, 56, Qt.AlignHCenter,
                   f"{delta.get('text', '0.000')} s")

    def _draw_cue(self, p: QPainter, w: int) -> None:
        if self._cue is None:
            return
        age = time.monotonic() - self._cue_at
        if age > CUE_HOLD_S:
            return
        # Fade out over the last 0.6 s.
        alpha = 255 if age < CUE_HOLD_S - 0.6 else int(255 * (CUE_HOLD_S - age) / 0.6)
        cat = self._cue.get("category", "")
        colour = QColor(_RED if cat in ("locked", "brake_later") else _AMBER)
        colour.setAlpha(max(0, alpha))
        self._draw_pill(p, self._cue.get("message", ""), colour, y=178, alpha=alpha)

    def _draw_focus(self, p: QPainter, w: int) -> None:
        """A slim, persistent reminder of the one weakness being coached. Low
        priority by design: drawn small and grey so it never fights the delta or
        an acute cue, but always there to answer 'what am I working on?'."""
        focus = self._state.get("focus")
        if not focus:
            return
        target = focus.get("focus")
        if not target:                       # no active focus (assessing/clean)
            return
        name = target.get("name", "")
        theme = target.get("theme", "")
        base = target.get("baseline_ms", 0) or 0
        gap = f"  −{base / 1000.0:.2f}s" if base else ""
        self._set_font(p, 12, bold=True)
        p.setPen(_AMBER)
        p.drawText(0, 206, w, 20, Qt.AlignHCenter,
                   f"◎ Focus · {name} · {theme}{gap}")

    # --- helpers -----------------------------------------------------------
    def _set_font(self, p: QPainter, size: int, bold: bool = False) -> None:
        f = QFont("Segoe UI", size)
        f.setBold(bold)
        p.setFont(f)

    def _draw_pill(self, p: QPainter, text: str, colour: QColor,
                   y: int, alpha: int = 255) -> None:
        self._set_font(p, 15, bold=True)
        w = self.width()
        back = QColor(_DARK)
        back.setAlpha(min(_DARK.alpha(), alpha))
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(20, y - 4, w - 40, 30, 8, 8)
        p.setPen(colour)
        p.drawText(20, y - 4, w - 40, 30, Qt.AlignCenter, text)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    url = DEFAULT_URL
    interactive = "--interactive" in argv or "-i" in argv
    for a in argv:
        if a.startswith("ws://") or a.startswith("wss://"):
            url = a

    app = QApplication(sys.argv)
    # Let Ctrl+C in the launching terminal close the overlay.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)

    overlay = Overlay(url, interactive)
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
