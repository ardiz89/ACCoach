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
* ``--pedals`` (or ``overlay.pedals = true`` in the config) adds a live
  throttle/brake trace strip under the HUD — a calibration aid that makes
  trail-braking (the two traces overlapping) and coasting / "tempo morto" (both
  at zero) readable at a glance.

The drawing uses ``QWebSocket`` so the socket lives on Qt's event loop — no extra
threads — and reconnects automatically if the backend isn't up yet.
"""

from __future__ import annotations

import json
import signal
import sys
import time

from .i18n import t
from .theme import DISPLAY, MONO, load_fonts

try:
    from PySide6.QtCore import QPointF, Qt, QTimer, QUrl
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
    from PySide6.QtWebSockets import QWebSocket
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:  # pragma: no cover - optional dependency
    print("This overlay needs PySide6.  Install it with:  pip install PySide6")
    raise SystemExit(1)

DEFAULT_URL = "ws://127.0.0.1:8777/ws"
RECONNECT_MS = 2000
CUE_HOLD_S = 1.8          # how long a cue stays on screen before fading out
_GREEN_HOLD_S = 2.5       # how long "green — flying lap" stays up at the line
DELTA_CLAMP_S = 1.0       # bar is full at ±1.0 s
_BASE_W, _BASE_H = 560, 210   # design size; the window is this × the config scale

# --- live pedal trace (opt-in: --pedals / config overlay.pedals) --------------
# A rolling throttle/brake strip drawn under the HUD. It's a calibration aid:
# trail-braking shows as the two traces overlapping (brake decaying while
# throttle rises), and "tempo morto" (coasting) shows as a gap where both sit at
# zero — the ribbon under the plot colours those states so they read at a glance.
_PEDAL_PANEL_H = 128          # extra window height (base coords) when pedals on
_PEDAL_WINDOW_S = 6.0         # seconds of history the strip shows
_PEDAL_EPS = 0.04             # below this a pedal counts as released (coasting)

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
    def __init__(self, url: str | None = None, interactive: bool = False,
                 pedals: bool = False) -> None:
        super().__init__()
        self._state: dict = {}
        self._cue: dict | None = None
        self._cue_at: float = -1e9
        # Edge detection for the "green — flying lap" flash.
        self._prev_quiet: str = ""
        self._green_at: float = 0.0
        # Rolling (t, throttle, brake) samples for the optional pedal strip.
        self._show_pedals = pedals
        self._pedal_hist: list[tuple[float, float, float]] = []

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
        self._base_h = _BASE_H + (_PEDAL_PANEL_H if pedals else 0)
        self.resize(int(_BASE_W * self._scale), int(self._base_h * self._scale))
        # A pinned position (dragged in --interactive) wins and is never moved for
        # the driver; otherwise we place it ourselves — and keep placing it, see
        # _watch_screens().
        self._auto_place = not (ov.x >= 0 and ov.y >= 0)
        if self._auto_place:
            self._place_top_center()
        else:
            self.move(ov.x, ov.y)
            if not self._on_a_screen():      # saved on a monitor that's now gone
                self._place_top_center()
        self._watch_screens()

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
        # Catch the gate opening here, not in paintEvent: the overlay repaints at
        # 30 fps regardless of new state, so an edge detected there would be read
        # off whatever frame happened to be drawing.
        quiet = data.get("quiet") or ""
        if self._prev_quiet and not quiet:
            self._green_at = time.monotonic()
        elif quiet:
            self._green_at = 0.0
        self._prev_quiet = quiet

        self._state = data
        cue = data.get("cue")
        if cue:
            self._cue = cue
            self._cue_at = time.monotonic()
        if self._show_pedals:
            self._record_pedals(data)

    def _record_pedals(self, data: dict) -> None:
        thr, brk = data.get("throttle"), data.get("brake")
        if thr is None or brk is None:
            return
        now = time.monotonic()
        self._pedal_hist.append((now, float(thr), float(brk)))
        # Drop samples older than the visible window (they scroll off the left).
        cutoff = now - _PEDAL_WINDOW_S
        drop = 0
        for t0, _, _ in self._pedal_hist:
            if t0 >= cutoff:
                break
            drop += 1
        if drop:
            del self._pedal_hist[:drop]

    # --- placement ---------------------------------------------------------
    def _watch_screens(self) -> None:
        """Re-place when the desktop is rearranged under us.

        Placing once at startup is not enough on a triple rig, because turning
        AMD Eyefinity on *moves the origin*. Measured on this machine:

            Eyefinity off → three screens at x = -2560 / 0 / +2560,
                            virtual desktop starts at -2560, centre 1279
            Eyefinity on  → one 7680-wide screen at x = 0, centre 3840

        The overlay placed at x≈959 (dead centre of the middle panel with
        Eyefinity off) keeps that absolute coordinate, and once the origin shifts
        by 2560 the same x lands in the *left* third of the span. Which is exactly
        where the driver found it. Nothing was wrong with the maths — it was
        computed against a desktop that no longer existed.
        """
        app = QApplication.instance()
        if app is None:
            return
        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)
        app.primaryScreenChanged.connect(self._on_screens_changed)
        for screen in app.screens():
            screen.geometryChanged.connect(self._on_screens_changed)

    def _on_screens_changed(self, *_args) -> None:
        # New screens need watching too, or a later rearrangement goes unseen.
        for screen in QApplication.screens():
            try:
                screen.geometryChanged.disconnect(self._on_screens_changed)
            except (RuntimeError, TypeError):
                pass
            screen.geometryChanged.connect(self._on_screens_changed)
        if self._auto_place:
            self._place_top_center()
        elif not self._on_a_screen():
            # Even a pinned position has to stay reachable: a saved x of 5000 on a
            # desktop that just shrank is an overlay the driver reports as "gone".
            self._place_top_center()

    def _on_a_screen(self) -> bool:
        """Is any part of the overlay actually on a physical screen?"""
        return any(s.geometry().intersects(self.frameGeometry())
                   for s in QApplication.screens())

    def _place_top_center(self) -> None:
        # Center on the middle of the whole desktop, not the primary screen's:
        # on a triple / AMD Eyefinity rig the "center" the driver looks at is the
        # middle panel. This lands there whether the driver merges the three into
        # one wide screen (Eyefinity) or Windows keeps them as separate displays.
        prim = QApplication.primaryScreen()
        vg = prim.virtualGeometry()
        center = vg.center()
        # Use the top edge of the screen under that center point (handles panels
        # that aren't all the same height / vertically aligned).
        under = QApplication.screenAt(center) or prim
        self.move(center.x() - self.width() // 2, under.geometry().top() + 24)

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

        if self._show_pedals:
            self._draw_pedals(p, w)

        if not st or not st.get("connected"):
            self._draw_mark(p, 22, 22, 18)
            self._set_font(p, 14, bold=True)
            p.setPen(_GREY)
            p.drawText(52, 14, 200, 24, Qt.AlignVCenter, "HONE")
            self._draw_pill(p, t("overlay.waiting"), _GREY, y=78)
            return

        self._draw_brand_header(p, w)
        delta = st.get("delta")
        quiet = st.get("quiet") or ""
        if delta is None:
            # Say WHY there's nothing to compare against. The old text assumed the
            # only reason was "still learning the reference", which was wrong on an
            # out-lap and read as a stuck app.
            self._draw_pill(p, t(f"quiet.{quiet}") if quiet else t("overlay.rec"),
                            _AMBER, y=78)
        else:
            self._draw_delta(p, delta, w)
            if quiet:
                # The delta is still worth seeing (you can read how far off you
                # are), but the coach isn't advising — say so under the number.
                self._set_font(p, 11)
                p.setPen(_GREY)
                p.drawText(0, 108, w, 16, Qt.AlignHCenter, t(f"quiet.{quiet}"))
        self._draw_green_flag(p, w, quiet)
        self._draw_cue(p, w)
        self._draw_focus(p, w)

    def _draw_green_flag(self, p: QPainter, w: int, quiet: str) -> None:
        """Flash "green — flying lap" the moment the coach starts working.

        Without it the driver never learns when the silence ended and keeps
        suspecting the app is broken well after it resumed. Cheapest half of the
        fix, and the half that's usually forgotten. The edge itself is caught in
        :meth:`apply_state`; this only draws it.
        """
        if quiet or not self._green_at:
            return
        if time.monotonic() - self._green_at > _GREEN_HOLD_S:
            return
        self._set_font(p, 12, bold=True)
        p.setPen(_GREEN)
        p.drawText(0, 108, w, 16, Qt.AlignHCenter, t("quiet.green"))

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
        self._set_font(p, 28, bold=True, mono=True)
        p.setPen(colour)
        p.drawText(0, y + bar_h + 2, w, 34, Qt.AlignHCenter,
                   f"{delta.get('text', '0.000')}")

        # Local delta: gaining/losing RIGHT NOW (this micro-sector) — the
        # predictive signal a cumulative number can't give. Small, under it.
        local = delta.get("local_s", 0.0)
        if abs(local) >= 0.01:
            losing = delta.get("local_losing", local > 0)
            self._set_font(p, 11, bold=True, mono=True)
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

    # --- live pedal trace --------------------------------------------------
    def _draw_pedals(self, p: QPainter, w: int) -> None:
        """Rolling throttle (green) / brake (red) strip under the HUD.

        Reads the trail-brake overlap and the coasting gaps ("tempo morto") at a
        glance: the ribbon below the plot is amber while both pedals are pressed
        (trailing) and grey while neither is (coasting)."""
        top = _BASE_H
        px, pw = 28, w - 56
        plot_top, plot_h = top + 30, 64
        ribbon_y, ribbon_h = plot_top + plot_h + 4, 6

        # backing pill
        p.setPen(Qt.NoPen)
        p.setBrush(_DARK)
        p.drawRoundedRect(12, top + 2, w - 24, _PEDAL_PANEL_H - 10, 8, 8)

        # grid: 0 / 50 / 100 %
        grid = QColor(_LINE)
        p.setPen(QPen(grid, 1))
        for frac in (0.0, 0.5, 1.0):
            gy = int(plot_top + plot_h * (1.0 - frac))
            p.drawLine(px, gy, px + pw, gy)

        hist = self._pedal_hist
        now = time.monotonic()

        def xy(t0: float, v: float) -> QPointF:
            age = now - t0
            x = px + pw * (1.0 - age / _PEDAL_WINDOW_S)
            y = plot_top + plot_h * (1.0 - max(0.0, min(1.0, v)))
            return QPointF(x, y)

        # ribbon: colour each time-span by pedal state (uses the left sample)
        for i in range(len(hist) - 1):
            t0, thr, brk = hist[i]
            x0 = xy(t0, 0.0).x()
            x1 = xy(hist[i + 1][0], 0.0).x()
            col = None
            if thr > _PEDAL_EPS and brk > _PEDAL_EPS:
                col = _AMBER                       # trail-braking overlap
            elif thr <= _PEDAL_EPS and brk <= _PEDAL_EPS:
                col = _GREY                        # coasting / tempo morto
            if col is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRect(int(x0), ribbon_y, max(1, int(x1 - x0) + 1), ribbon_h)

        # traces
        if len(hist) >= 2:
            brake_line = QPolygonF([xy(t0, brk) for t0, _, brk in hist])
            thr_line = QPolygonF([xy(t0, thr) for t0, thr, _ in hist])
            pen = QPen(_RED, 2)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(brake_line)
            pen = QPen(_GREEN, 2)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawPolyline(thr_line)

        # header: live readouts + current state tag
        thr = brk = 0.0
        if hist:
            _, thr, brk = hist[-1]
        self._set_font(p, 11, bold=True, mono=True)
        p.setPen(Qt.NoPen)
        p.setBrush(_GREEN)
        p.drawEllipse(px, top + 10, 7, 7)
        p.setPen(_GREEN)
        p.drawText(px + 12, top + 6, 96, 16, Qt.AlignVCenter,
                   f"{t('overlay.throttle_pedal')} {thr * 100:3.0f}%")
        p.setPen(Qt.NoPen)
        p.setBrush(_RED)
        p.drawEllipse(px + 116, top + 10, 7, 7)
        p.setPen(_RED)
        p.drawText(px + 128, top + 6, 96, 16, Qt.AlignVCenter,
                   f"{t('overlay.brake_pedal')} {brk * 100:3.0f}%")

        tag, tag_col = self._pedal_tag(now)
        if tag:
            p.setPen(tag_col)
            self._set_font(p, 11, bold=True)
            p.drawText(px, top + 6, pw, 16, Qt.AlignRight | Qt.AlignVCenter, tag)

    def _pedal_tag(self, now: float) -> tuple[str, QColor]:
        """Current-state chip: TRAIL while overlapping, COAST + how long while
        coasting, else nothing."""
        hist = self._pedal_hist
        if not hist:
            return "", _GREY
        _, thr, brk = hist[-1]
        if thr > _PEDAL_EPS and brk > _PEDAL_EPS:
            return t("overlay.trail"), _AMBER
        if thr <= _PEDAL_EPS and brk <= _PEDAL_EPS:
            start = hist[-1][0]
            for t0, th, bk in reversed(hist):
                if th <= _PEDAL_EPS and bk <= _PEDAL_EPS:
                    start = t0
                else:
                    break
            return f"{t('overlay.coast')} {now - start:.1f}s", _GREY
        return "", _GREY

    # --- helpers -----------------------------------------------------------
    def _set_font(self, p: QPainter, size: int, bold: bool = False,
                  mono: bool = False) -> None:
        """The brand display face, or the mono one for numbers that refresh in place.

        Both ship with the app (theme.load_fonts); the style hint covers the case
        where a bundle is missing them. Mono matters here: the delta is centred and
        redrawn every frame, and proportional digits make it breathe sideways in
        the corner of your eye while you're driving.
        """
        f = QFont(MONO if mono else DISPLAY, size)
        f.setStyleHint(QFont.Monospace if mono else QFont.SansSerif)
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

    # Pedal strip: CLI flag wins, else the persisted config toggle.
    from .config import load_config
    pedals = "--pedals" in argv or load_config().overlay.pedals

    app = QApplication(sys.argv)
    load_fonts()                     # the overlay paints in the brand face too
    # Let Ctrl+C in the launching terminal close the overlay.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)

    overlay = Overlay(url, interactive, pedals=pedals)
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
