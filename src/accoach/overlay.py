"""On-screen overlay — a glanceable HUD drawn over the game.

A thin WebSocket client of :mod:`accoach.server`: it draws the HONE mark, a delta
bar, the predicted/reference lap times and the current coaching cue, and the focus
you're working on. While braking at 200 km/h you read it as colour and motion.

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

from .i18n import t

try:
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    from PySide6.QtWebSockets import QWebSocket
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:  # pragma: no cover - optional dependency
    print("This overlay needs PySide6.  Install it with:  pip install PySide6")
    raise SystemExit(1)

DEFAULT_URL = "ws://127.0.0.1:8777/ws"
RECONNECT_MS = 2000
CUE_HOLD_S = 1.8          # how long a cue stays on screen before fading out
DELTA_CLAMP_S = 1.0       # bar is full at ±1.0 s
_BASE_W, _BASE_H = 560, 210   # design size; the window is this × the config scale

# HONE palette (see accoach.brand). QColor wants ints, so they're spelled here.
_CYAN = QColor(0x22, 0xD3, 0xCE)     # brand mark / cue accent
_GREEN = QColor(0x34, 0xE0, 0x8A)    # delta: faster
_RED = QColor(0xFF, 0x4D, 0x5E)      # delta: slower / acute lock
_AMBER = QColor(0xFF, 0xB0, 0x20)    # focus / advisory
_WHITE = QColor(0xE8, 0xED, 0xF2)    # text
_GREY = QColor(0x8A, 0x95, 0xA3)     # muted text
_LINE = QColor(0x23, 0x2B, 0x35)     # bar track / hairlines
_DARK = QColor(0x0B, 0x0E, 0x12, 165)  # Ink, semi-transparent backing pill


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

        # Honor the configured scale + position (drag-to-move persists them).
        from .config import load_config
        ov = load_config().overlay
        self._scale = ov.scale if (ov.scale and ov.scale > 0) else 1.0
        self._interactive = interactive
        self._drag_off = None
        self.resize(int(_BASE_W * self._scale), int(_BASE_H * self._scale))
        if ov.x >= 0 and ov.y >= 0:
            self.move(ov.x, ov.y)
        else:
            self._place_top_center()

        # WebSocket client on the Qt event loop — only when a URL is given.
        # In-process callers feed it via apply_state() instead.
        self._ws: QWebSocket | None = None
        if url:
            self._ws = QWebSocket()
            self._ws.textMessageReceived.connect(self._on_message)
            self._ws.disconnected.connect(self._on_disconnect)
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

    def _on_disconnect(self) -> None:
        # Clear the state so a dead backend falls back to the "waiting" pill
        # instead of freezing the last delta/cue on screen as if it were live.
        self._state = {}
        self._cue = None
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
        if self._scale != 1.0:
            p.scale(self._scale, self._scale)   # everything below uses base coords
        st = self._state
        w = _BASE_W

        if not st or not st.get("connected"):
            self._draw_mark(p, 22, 22, 18)
            self._set_font(p, 14, bold=True)
            p.setPen(_GREY)
            p.drawText(52, 14, 200, 24, Qt.AlignVCenter, "HONE")
            self._draw_pill(p, t("overlay.waiting"), _GREY, y=78)
            return

        self._draw_brand_header(p, w)
        delta = st.get("delta")
        if delta is None:
            self._draw_pill(p, t("overlay.rec"), _AMBER, y=78)
        else:
            self._draw_delta(p, delta, w)
        self._draw_cue(p, w)
        self._draw_focus(p, w)

    # --- the HONE mark: a cyan chevron with a green apex dot ----------------
    def _draw_mark(self, p: QPainter, x: int, y: int, h: int) -> None:
        pen = QPen(_CYAN)
        pen.setWidth(max(3, h // 4))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        tip_x = x + h * 0.9
        mid_y = y + h / 2
        p.drawLine(int(x), int(y), int(tip_x), int(mid_y))
        p.drawLine(int(x), int(y + h), int(tip_x), int(mid_y))
        r = max(2, h // 5)
        p.setPen(Qt.NoPen)
        p.setBrush(_GREEN)
        p.drawEllipse(int(x + h * 0.45 - r), int(mid_y - r), 2 * r, 2 * r)

    def _draw_brand_header(self, p: QPainter, w: int) -> None:
        self._draw_mark(p, 22, 18, 16)
        self._set_font(p, 13, bold=True)
        p.setPen(_WHITE)
        p.drawText(50, 12, 220, 22, Qt.AlignVCenter, "HONE")
        delta = self._state.get("delta") or {}
        # When a braking point is coming up, the countdown takes the header's right
        # slot (it's time-critical); otherwise show the reference lap time (PB).
        brake_m = delta.get("brake_in_m")
        self._set_font(p, 13, bold=True)
        if brake_m is not None:
            p.setPen(_AMBER)
            p.drawText(w - 240, 12, 220, 22, Qt.AlignRight | Qt.AlignVCenter,
                       f"▼ {t('overlay.brake')}  {brake_m} m")
        else:
            p.setPen(_GREY)
            pb = delta.get("reference") or "--:--.---"
            p.drawText(w - 240, 12, 220, 22, Qt.AlignRight | Qt.AlignVCenter, f"PB {pb}")

    def _draw_delta(self, p: QPainter, delta: dict, w: int) -> None:
        ahead = delta.get("ahead", False)
        colour = _GREEN if ahead else _RED

        bar_w, bar_h, y = 380, 14, 50
        x0 = (w - bar_w) // 2
        cx = x0 + bar_w // 2
        p.setPen(Qt.NoPen)
        p.setBrush(_LINE)
        p.drawRoundedRect(x0, y, bar_w, bar_h, 7, 7)

        frac = max(-1.0, min(1.0, delta.get("s", 0.0) / DELTA_CLAMP_S))
        fill = int(abs(frac) * (bar_w // 2))
        p.setBrush(colour)
        if frac >= 0:  # slower -> fill right
            p.drawRoundedRect(cx, y, fill, bar_h, 7, 7)
        else:          # faster -> fill left
            p.drawRoundedRect(cx - fill, y, fill, bar_h, 7, 7)
        p.setPen(_GREY)
        p.drawLine(cx, y - 2, cx, y + bar_h + 2)

        # Big delta number. The text already carries the sign (+slower / -faster),
        # which is the colour-blind-safe redundancy alongside the red/green.
        self._set_font(p, 28, bold=True)
        p.setPen(colour)
        p.drawText(0, y + bar_h + 2, w, 34, Qt.AlignHCenter,
                   f"{delta.get('text', '0.000')}")

        # Local delta: gaining/losing RIGHT NOW (this micro-sector) — the
        # predictive signal a cumulative number can't give. Small, under it.
        local = delta.get("local_s", 0.0)
        if abs(local) >= 0.01:
            losing = delta.get("local_losing", local > 0)
            self._set_font(p, 11, bold=True)
            p.setPen(_RED if losing else _GREEN)
            arrow = "▲" if losing else "▼"
            p.drawText(0, y + bar_h + 38, w, 16, Qt.AlignHCenter,
                       f"now {arrow} {local:+.2f}")

    def _draw_cue(self, p: QPainter, w: int) -> None:
        if self._cue is None:
            return
        age = time.monotonic() - self._cue_at
        if age > CUE_HOLD_S:
            return
        # Fade out over the last 0.6 s.
        alpha = 255 if age < CUE_HOLD_S - 0.6 else int(255 * (CUE_HOLD_S - age) / 0.6)
        alpha = max(0, alpha)
        cat = self._cue.get("category", "")
        accent = QColor(_RED if cat in ("locked", "wheelspin") else _CYAN)
        accent.setAlpha(alpha)

        x, y, h = 20, 126, 36
        bg = QColor(_DARK)
        bg.setAlpha(min(_DARK.alpha(), alpha))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(x, y, w - 2 * x, h, 8, 8)
        # cyan (or red) left accent bar
        p.setBrush(accent)
        p.drawRoundedRect(x, y, 4, h, 2, 2)

        text = QColor(_WHITE)
        text.setAlpha(alpha)
        p.setPen(text)
        self._set_font(p, 14, bold=True)
        p.drawText(x + 16, y, w - 2 * x - 28, h, Qt.AlignVCenter,
                   self._cue.get("message", ""))

    def _draw_focus(self, p: QPainter, w: int) -> None:
        """A slim, persistent reminder of the one weakness being coached. Low
        priority by design: small and quiet so it never fights the delta or an
        acute cue, but always there to answer 'what am I working on?'."""
        # Declutter: don't compete with an acute cue while it's on screen.
        if self._cue is not None and (time.monotonic() - self._cue_at) < CUE_HOLD_S:
            return
        focus = self._state.get("focus")
        if not focus:
            return
        target = focus.get("focus")
        if not target:                       # no active focus (assessing / clean)
            return
        name = (target.get("name") or "").upper()
        theme = (target.get("theme") or "").upper()
        base = target.get("baseline_ms", 0) or 0
        gap = f"  −{base / 1000.0:.2f}s" if base else ""
        y = 170
        p.setPen(Qt.NoPen)
        p.setBrush(_AMBER)
        p.drawEllipse(26, y + 6, 7, 7)       # amber focus dot
        self._set_font(p, 11, bold=True)
        p.setPen(_GREY)
        p.drawText(42, y, w - 60, 20, Qt.AlignVCenter,
                   f"{t('overlay.focus')} · {theme} · {name}{gap}")

    # --- helpers -----------------------------------------------------------
    def _set_font(self, p: QPainter, size: int, bold: bool = False) -> None:
        # Space Grotesk is the brand display face; fall back to Segoe UI offline.
        f = QFont("Space Grotesk", size)
        f.setStyleHint(QFont.SansSerif)
        f.setBold(bold)
        p.setFont(f)

    def _draw_pill(self, p: QPainter, text: str, colour: QColor,
                   y: int, alpha: int = 255) -> None:
        self._set_font(p, 15, bold=True)
        w = _BASE_W
        back = QColor(_DARK)
        back.setAlpha(min(_DARK.alpha(), alpha))
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(20, y - 4, w - 40, 30, 8, 8)
        p.setPen(colour)
        p.drawText(20, y - 4, w - 40, 30, Qt.AlignCenter, text)

    # --- drag to reposition (only in --interactive); persists to config --------
    def mousePressEvent(self, e) -> None:  # noqa: N802 (Qt naming)
        if self._interactive and e.button() == Qt.LeftButton:
            self._drag_off = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._interactive and self._drag_off is not None:
            self.move(e.globalPosition().toPoint() - self._drag_off)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if not (self._interactive and self._drag_off is not None):
            return
        self._drag_off = None
        try:
            from .config import load_config, save_config
            cfg = load_config()
            cfg.overlay.x, cfg.overlay.y = self.x(), self.y()
            save_config(cfg)
        except Exception:  # pragma: no cover - best-effort persistence
            pass


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
