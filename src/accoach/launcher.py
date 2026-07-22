"""The HONE desktop hub — one window, a sidebar, and the last session up front.

This replaces the old button-list launcher: a main window with a left sidebar of
six intent-based sections (Home · Drive · Analysis · Setup · Devices · Settings)
and a stacked panel per section. The **Home** shows your last session diagnosed
natively (see :mod:`accoach.hub_home`); the other sections start the matching
mode in its own process, exactly as before.

The hub OWNS the processes it starts: it tracks every child and kills the whole
tree when you close the window. Coach Live stays a *separate* process on purpose
(crash isolation — a coach crash mid-lap must not take the hub down with it), so
there's still a dedicated Stop button and the "one voice at a time" rule.
"""

from __future__ import annotations

import os
import subprocess
import sys
from functools import partial
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QPushButton,
        QSpinBox,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtGui import QPixmap
except ImportError:  # pragma: no cover - optional dependency
    print("The launcher needs PySide6.  Install it with:  pip install PySide6")
    raise SystemExit(1)

from . import brand
from .config import load_config, save_config, set_language
from .hub_home import HomePanel
from .i18n import LANGUAGES, language_name, t
from .netinfo import device_urls, port_open, qr_png
from .paths import base_dir
from .theme import load_fonts, qss, window_icon

_SRC = Path(__file__).resolve().parents[1]   # .../src

# Sentinels: buttons that do something other than spawn an accoach command.
_GUIDE = "__guide__"
_STOP_LIVE = "__stop_live__"
_WIZARD = "__wizard__"

# Commands that run a speaking coach. Only one may run at a time — two voice
# engines talking together sound like an echo — so starting one stops the other.
_VOICE_CMDS = {"live", "coach"}

# While Coach Live is running these action keys stay clickable; all other action
# buttons are disabled so you can't stack a second coach/telemetry reader on top
# of it. (The sidebar itself always stays navigable.)
_LIVE_SAFE_KEYS = {_STOP_LIVE, _GUIDE, _WIZARD,
                   ("web",), ("web", "--engineer"), ("server",)}


# --- first-run "getting started" wizard ------------------------------------
# A marker file (not config) keeps it dead simple: present == already seen.
def _wizard_marker() -> Path:
    return base_dir() / ".getting_started_seen"


def wizard_seen() -> bool:
    return _wizard_marker().exists()


def mark_wizard_seen() -> None:
    try:
        base_dir().mkdir(parents=True, exist_ok=True)
        _wizard_marker().write_text("1", encoding="utf-8")
    except OSError:  # pragma: no cover - best-effort
        pass


_WIZARD_STEPS = [
    "Set your game (AC / ACC) to <b>Borderless</b> so the overlay can draw over it.",
    "Click <b>Coach Live</b> — you get the voice coach and the on-screen overlay "
    "while you drive.",
    "Drive one clean lap: it becomes your <b>reference</b>. Beat it and the next "
    "lap becomes the new one.",
    "After a session, open <b>Analysis &amp; Report</b> for the corner-by-corner "
    "debrief, and <b>Race engineer</b> for setup advice.",
    "No game handy? Try <b>Coach Live — DEMO</b> to see it work on a synthetic lap.",
]


class GettingStarted(QDialog):
    """A small first-run wizard: what HONE is and the 4 steps to get going."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to HONE")
        self.setModal(True)
        self.resize(460, 460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(12)

        title = QLabel("Welcome to HONE")
        title.setProperty("role", "title")
        sub = QLabel("Know why you're slow. Here's how to get going:")
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)

        steps = "".join(
            f"<p style='margin:0 0 12px 0;'><b>{i}.</b> {text}</p>"
            for i, text in enumerate(_WIZARD_STEPS, 1)
        )
        body = QLabel(steps)
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        lay.addWidget(body)
        lay.addStretch(1)

        self._dont_show = QCheckBox("Don't show this again")
        self._dont_show.setChecked(True)
        lay.addWidget(self._dont_show)

        row = QHBoxLayout()
        guide = QPushButton("Open full guide")
        guide.clicked.connect(_open_guide)
        ok = QPushButton("Get started")
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(guide)
        row.addStretch(1)
        row.addWidget(ok)
        lay.addLayout(row)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._dont_show.isChecked():
            mark_wizard_seen()
        super().closeEvent(event)

    def accept(self) -> None:  # noqa: D102
        if self._dont_show.isChecked():
            mark_wizard_seen()
        super().accept()


def _guide_path() -> Path:
    """Locate GUIDA.md from source or from a frozen build."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        candidates = []
        if base:
            candidates.append(Path(base) / "GUIDA.md")
        candidates.append(Path(sys.executable).parent / "GUIDA.md")
    else:
        candidates = [_SRC.parent / "GUIDA.md"]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[-1]


def _open_guide() -> None:
    """Open the user guide in Notepad (plain, predictable — not the .md handler)."""
    path = _guide_path()
    try:
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-e", str(path)])   # TextEdit
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:  # pragma: no cover - best-effort
        print(f"Cannot open the guide ({path}): {exc}")


def _section(title_key: str) -> tuple[QWidget, QVBoxLayout]:
    """A section page shell: padded column with a title. Returns (page, body)."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(24, 24, 24, 24)
    lay.setSpacing(12)
    title = QLabel(t(title_key))
    title.setProperty("role", "title")
    title.setProperty("i18nKey", title_key)   # swept on language change
    lay.addWidget(title)
    return page, lay


def _hint(text: str, key: str | None = None) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "muted")
    lbl.setWordWrap(True)
    if key:
        lbl.setProperty("i18nKey", key)   # swept on language change
    return lbl


class SettingsPanel(QWidget):
    """Voice + overlay preferences, persisted to config.toml (no hand-editing).

    The old Settings *dialog* becomes an embedded panel: a Save button persists and
    a small note confirms it, instead of modal accept/cancel.
    """

    def __init__(self, hub: "MainWindow") -> None:
        super().__init__()
        self._hub = hub
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self._title = QLabel(t("nav.settings").strip())
        self._title.setProperty("role", "title")
        root.addWidget(self._title)

        cfg = load_config()
        form = QFormLayout()
        form.setSpacing(10)
        self._labels: dict[str, QLabel] = {}

        self._helps: dict[str, QLabel] = {}

        def row(key: str, widget: QWidget) -> None:
            """Label + a "?" whose tooltip explains the setting.

            Reported by the user: a field called "Overlay scale" or "Reading
            speed" means nothing to someone who didn't build the app, and this
            panel had no help of any kind. A tooltip alone isn't enough — with
            nothing visible to hover, nobody hovers. Hence a "?" you can see.
            """
            lbl = QLabel(t(key))
            self._labels[key] = lbl
            mark = QLabel("?")
            mark.setProperty("role", "help")
            mark.setToolTip(t(f"{key}.help"))
            mark.setCursor(Qt.WhatsThisCursor)
            self._helps[key] = mark
            box = QWidget()
            line = QHBoxLayout(box)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            line.addWidget(lbl)
            line.addWidget(mark)
            line.addStretch(1)
            form.addRow(box, widget)

        self._voice = QCheckBox()
        self._voice.setChecked(cfg.voice.enabled)
        row("set.voice", self._voice)

        self._engineer_voice = QCheckBox()
        self._engineer_voice.setChecked(cfg.voice.engineer)
        row("set.engineer_voice", self._engineer_voice)

        self._male = QCheckBox()
        self._male.setChecked(cfg.voice.male)
        row("set.male_voice", self._male)

        self._radio = QCheckBox()
        self._radio.setChecked(cfg.voice.radio)
        row("set.radio", self._radio)

        self._rate = QSpinBox()
        self._rate.setRange(80, 300)
        self._rate.setValue(cfg.voice.rate)
        row("set.rate", self._rate)

        self._scale = QDoubleSpinBox()
        self._scale.setRange(0.5, 2.5)
        self._scale.setSingleStep(0.1)
        self._scale.setValue(cfg.overlay.scale or 1.0)
        row("set.scale", self._scale)
        root.addLayout(form)

        self._scale_hint = _hint(t("set.scale_hint"))
        root.addWidget(self._scale_hint)

        save_row = QHBoxLayout()
        self._save = QPushButton(t("btn.save"))
        self._save.setProperty("accent", True)
        self._save.clicked.connect(self._do_save)
        self._saved_note = _hint("")
        save_row.addWidget(self._save)
        save_row.addWidget(self._saved_note)
        save_row.addStretch(1)
        root.addLayout(save_row)

        # Divider + advanced/dev tools + guide/wizard.
        line = QFrame()
        line.setProperty("role", "hline")
        line.setFixedHeight(1)
        root.addWidget(line)
        self._devtools = QLabel(t("sec.devtools"))
        self._devtools.setProperty("role", "muted")
        root.addWidget(self._devtools)

        tools = QHBoxLayout()
        tools.setSpacing(10)
        tools.addWidget(hub.action_button("btn.monitor", ["monitor"], console=True))
        tools.addWidget(hub.action_button("btn.coach_term", ["coach"], console=True))
        tools.addWidget(hub.action_button("btn.verify_g", ["verify-g"], console=True))
        tools.addStretch(1)
        root.addLayout(tools)

        extras = QHBoxLayout()
        extras.setSpacing(10)
        extras.addWidget(hub.special_button("btn.get_started", _WIZARD, hub._show_wizard))
        extras.addWidget(hub.special_button("btn.guide", _GUIDE, _open_guide))
        extras.addStretch(1)
        root.addLayout(extras)
        root.addStretch(1)

    def _do_save(self) -> None:
        cfg = load_config()
        cfg.voice.enabled = self._voice.isChecked()
        cfg.voice.engineer = self._engineer_voice.isChecked()
        cfg.voice.male = self._male.isChecked()
        cfg.voice.radio = self._radio.isChecked()
        cfg.voice.rate = self._rate.value()
        cfg.overlay.scale = round(self._scale.value(), 2)
        save_config(cfg)
        self._saved_note.setText("✓ " + t("btn.save"))

    def retranslate(self) -> None:
        self._title.setText(t("nav.settings").strip())
        for key, lbl in self._labels.items():
            lbl.setText(t(key))
        for key, mark in self._helps.items():
            mark.setToolTip(t(f"{key}.help"))
        self._scale_hint.setText(t("set.scale_hint"))
        self._save.setText(t("btn.save"))
        self._devtools.setText(t("sec.devtools"))
        if self._saved_note.text():
            self._saved_note.setText("✓ " + t("btn.save"))


class DevicesPanel(QWidget):
    """Phone/tablet LAN access (QR) plus the second-screen server and overlay.

    The LAN block is the old MobileAccess dialog, re-hosted as a panel: toggling
    LAN binds the servers to ``0.0.0.0`` (persisted); it only takes effect when the
    web/live servers (re)start, so the note says so.
    """

    def __init__(self, hub: "MainWindow") -> None:
        super().__init__()
        self._hub = hub
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self._title = QLabel(t("mob.title"))
        self._title.setProperty("role", "title")
        root.addWidget(self._title)

        self._lan = QCheckBox(t("mob.lan"))
        self._lan.setChecked(load_config().lan)
        self._lan.toggled.connect(self._on_toggle)
        root.addWidget(self._lan)

        self._restart = _hint(t("mob.restart"))
        root.addWidget(self._restart)

        # Swappable body: the QR pair when LAN is on, else an explanatory line.
        self._body = QVBoxLayout()
        self._body.setSpacing(8)
        root.addLayout(self._body)

        # The QR codes come from the config, so they render whether or not a
        # server is behind them. Say which it is, rather than let the user find
        # out by scanning and watching a page hang.
        self._status = QLabel()
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self._refresh_status)

        line = QFrame()
        line.setProperty("role", "hline")
        line.setFixedHeight(1)
        root.addWidget(line)

        srv_row = QHBoxLayout()
        srv_row.setSpacing(10)
        srv_row.addWidget(hub.action_button("btn.server", ["server"], console=True))
        srv_row.addWidget(hub.action_button("btn.overlay", ["overlay"]))
        srv_row.addStretch(1)
        root.addLayout(srv_row)
        root.addStretch(1)

        self._render()

    def _on_toggle(self, checked: bool) -> None:
        cfg = load_config()
        cfg.lan = checked
        save_config(cfg)
        self._render()

    def _render(self) -> None:
        """Rebuild the QR body to match the current LAN state."""
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        cfg = load_config()
        # Ahead of the early returns below: the status line reflects the config,
        # so it must be right on every path (LAN off, no IP, or the full QR set).
        self._refresh_status()
        if not cfg.lan:
            self._body.addWidget(_hint(t("mob.off")))
            return
        urls = device_urls(cfg.web.port)
        if not urls:
            self._body.addWidget(_hint(t("mob.no_ip")))
            return
        pair = QWidget()
        cols = QHBoxLayout(pair)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(16)
        cols.addWidget(self._qr_col(t("mob.report"), urls["report"]))
        cols.addWidget(self._qr_col(t("mob.engineer"), urls["engineer"]))
        cols.addWidget(self._qr_col(t("mob.test"), urls["test"]))
        self._body.addWidget(pair)
        self._body.addWidget(_hint(t("mob.scan")))
        self._body.addWidget(_hint(t("mob.test_live")))
        self._body.addWidget(_hint(t("mob.same_net")))
        self._body.addWidget(_hint(t("mob.firewall")))

    def showEvent(self, event) -> None:   # noqa: N802 - Qt naming
        # Poll only while the section is on screen: off it, nobody reads it.
        super().showEvent(event)
        self._refresh_status()
        self._poll.start()

    def hideEvent(self, event) -> None:   # noqa: N802 - Qt naming
        super().hideEvent(event)
        self._poll.stop()

    def _refresh_status(self) -> None:
        """Say whether the server behind the QR codes is actually up."""
        cfg = load_config()
        if not cfg.lan:
            self._status.setVisible(False)
            return
        self._status.setVisible(True)
        up = port_open(cfg.web.port)
        self._status.setText(t("mob.server_on") if up else t("mob.server_off"))
        self._status.setProperty("role", "good" if up else "bad")
        # Qt resolves the stylesheet once per property value; without a re-polish
        # the colour keeps whatever it had when the label was first shown.
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _qr_col(self, title: str, url: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        head = QLabel(title)
        head.setStyleSheet("font-weight: bold;")
        head.setAlignment(Qt.AlignHCenter)
        v.addWidget(head)
        img = QLabel()
        img.setAlignment(Qt.AlignHCenter)
        png = qr_png(url, scale=5)
        if png:
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            img.setPixmap(pix)
        else:
            img.setText(t("mob.no_qr"))
            img.setProperty("role", "muted")
        v.addWidget(img)
        link = QLabel(url)
        link.setAlignment(Qt.AlignHCenter)
        link.setProperty("role", "link")
        link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        link.setWordWrap(True)
        v.addWidget(link)
        return w

    def retranslate(self) -> None:
        self._title.setText(t("mob.title"))
        self._lan.setText(t("mob.lan"))
        self._restart.setText(t("mob.restart"))
        self._render()


class MainWindow(QWidget):
    """The hub shell: sidebar + stacked sections, and process ownership."""

    # Sidebar order → stack pages.
    _NAV = [
        ("nav.home", "🏠"),
        ("nav.live", "▶"),
        ("nav.analysis", "📊"),
        ("nav.setup", "🔧"),
        ("nav.devices", "📱"),
        ("nav.settings", "⚙"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HONE")
        self.setWindowIcon(window_icon())
        self.resize(900, 600)
        # Every process we spawn, so we can stop them on demand / on close.
        self._children: list[tuple[subprocess.Popen, list[str]]] = []
        # Registered action buttons: (gating key, label key, button).
        self._actions: list[tuple[object, str, QPushButton]] = []
        self._panels: list[QWidget] = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())
        self._stack = QStackedWidget()
        outer.addWidget(self._stack, 1)

        # Home first — it's page 0 and the landing section.
        self._home = HomePanel(
            on_analysis=partial(self._spawn, ["web"], False),
            on_setup=partial(self._spawn, ["web", "--engineer"], False),
        )
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._build_live_page())
        self._stack.addWidget(self._build_analysis_page())
        self._stack.addWidget(self._build_setup_page())
        self._devices = DevicesPanel(self)
        self._stack.addWidget(self._devices)
        self._settings = SettingsPanel(self)
        self._stack.addWidget(self._settings)
        self._panels = [self._home, self._settings, self._devices]

        self._nav.setCurrentRow(0)

        # Poll the children so the buttons re-enable themselves when Coach Live
        # ends (stopped, closed, or crashed), not only when you press Stop.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_buttons)
        self._timer.start(1000)
        self._refresh_buttons()

    # --- sidebar ---------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setFixedWidth(210)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(10)

        wordmark = QLabel(f"‹ {brand.NAME} ›")
        wordmark.setProperty("role", "brand")
        lay.addWidget(wordmark)

        self._nav = QListWidget()
        self._nav.setObjectName("sidebar")
        for key, glyph in self._NAV:
            self._nav.addItem(f"{glyph}{t(key)}")
        self._nav.currentRowChanged.connect(self._on_nav)
        lay.addWidget(self._nav, 1)

        # Language selector — switches the interface + coach voice. Applies on the
        # next Coach Live start (the voice picks its language at startup).
        self._lang_lbl = QLabel(t("ui.language"))
        self._lang_lbl.setProperty("role", "muted")
        lay.addWidget(self._lang_lbl)
        self._lang = QComboBox()
        for code in LANGUAGES:
            self._lang.addItem(language_name(code), code)
        i = self._lang.findData(load_config().language)
        if i >= 0:
            self._lang.setCurrentIndex(i)
        self._lang.currentIndexChanged.connect(self._on_language)
        lay.addWidget(self._lang)
        return side

    def _on_nav(self, row: int) -> None:
        self._stack.setCurrentIndex(row)
        if row == 0:                 # returning to Home → re-read the last session
            self._home.refresh()

    # --- section pages ---------------------------------------------------
    def _build_live_page(self) -> QWidget:
        page, lay = _section("nav.live")
        lay.addWidget(self.action_button("btn.coach_live", ["live"], accent=True))
        lay.addWidget(self.action_button("btn.coach_live_demo", ["live", "--demo"]))
        lay.addWidget(self.special_button("btn.stop_live", _STOP_LIVE,
                                          self._stop_live, danger=True))
        lay.addSpacing(8)
        lay.addWidget(_hint(t("ui.tip_borderless"), key="ui.tip_borderless"))
        lay.addStretch(1)
        return page

    def _build_analysis_page(self) -> QWidget:
        page, lay = _section("nav.analysis")
        lay.addWidget(self.action_button("btn.analysis", ["web"], accent=True))
        lay.addWidget(self.action_button("btn.debrief", ["debrief"], console=True))
        lay.addStretch(1)
        return page

    def _build_setup_page(self) -> QWidget:
        page, lay = _section("nav.setup")
        lay.addWidget(self.action_button("btn.engineer", ["web", "--engineer"],
                                         accent=True))
        lay.addStretch(1)
        return page

    # --- button factories ------------------------------------------------
    def action_button(self, label_key: str, args: list[str], *,
                      console: bool = False, accent: bool = False) -> QPushButton:
        """A button that spawns ``args`` and is gated while Coach Live runs."""
        btn = QPushButton(t(label_key))
        btn.setMinimumHeight(40)
        if accent:
            btn.setProperty("accent", True)
        btn.clicked.connect(partial(self._spawn, args, console))
        self._actions.append((tuple(args), label_key, btn))
        return btn

    def special_button(self, label_key: str, key: str, handler, *,
                       danger: bool = False) -> QPushButton:
        """A button wired to a handler (not a spawn), gated by its sentinel key."""
        btn = QPushButton(t(label_key))
        btn.setMinimumHeight(40)
        if danger:
            btn.setProperty("danger", True)
        btn.clicked.connect(lambda: handler())
        self._actions.append((key, label_key, btn))
        return btn

    # --- process management ----------------------------------------------
    def _spawn(self, args: list[str], new_console: bool) -> None:
        # One voice coach at a time: starting live/coach stops any already running,
        # so two TTS engines never speak together (the "echo" you'd otherwise hear).
        if args and args[0] in _VOICE_CMDS:
            for proc, a in list(self._children):
                if a and a[0] in _VOICE_CMDS and proc.poll() is None:
                    self._kill(proc)
            self._prune()

        flags = 0
        if new_console and sys.platform == "win32":
            flags = subprocess.CREATE_NEW_CONSOLE
        if getattr(sys, "frozen", False):
            # Packaged: the exe IS the dispatcher — re-invoke it with the command.
            proc = subprocess.Popen([sys.executable, *args], creationflags=flags)
        else:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(_SRC) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.Popen([sys.executable, "-m", "accoach", *args],
                                    env=env, creationflags=flags)
        self._prune()
        self._children.append((proc, args))
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """Disable every action but the live-safe ones while Coach Live runs."""
        self._prune()
        live = any(a and a[0] == "live" for _p, a in self._children)
        for key, _label, btn in self._actions:
            btn.setEnabled(not live or key in _LIVE_SAFE_KEYS)
            # "Stop Coach Live" is meaningless before there's one to stop, and a
            # disabled Stop sitting next to Start reads as "something is already
            # running" — the opposite of the truth. Hide it instead: the panel
            # then shows exactly the one action that applies right now.
            if key == _STOP_LIVE:
                btn.setVisible(live)

    def _prune(self) -> None:
        """Forget children that have already exited."""
        self._children = [(p, a) for (p, a) in self._children if p.poll() is None]

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                # /T kills the whole process tree (any grandchildren too).
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                proc.terminate()
        except Exception:  # pragma: no cover - best-effort
            pass

    def _on_language(self) -> None:
        """Persist the chosen language and re-label the whole hub right away (the
        coach voice picks it up on the next Coach Live start)."""
        set_language(self._lang.currentData())
        # Sidebar items.
        for i, (key, glyph) in enumerate(self._NAV):
            self._nav.item(i).setText(f"{glyph}{t(key)}")
        # Registered action/special buttons.
        for _key, label_key, btn in self._actions:
            btn.setText(t(label_key))
        # Language label + every static label tagged with an i18n key (section
        # titles, hints), swept in one pass across the whole window.
        self._lang_lbl.setText(t("ui.language"))
        for lbl in self.findChildren(QLabel):
            key = lbl.property("i18nKey")
            if key:
                lbl.setText(t(key))
        # Panels with dynamic/non-label text (checkboxes, QR, saved note, stats).
        for panel in self._panels:
            if hasattr(panel, "retranslate"):
                panel.retranslate()

    def _show_wizard(self) -> None:
        """Open the getting-started wizard (also auto-shown on first run)."""
        GettingStarted(self).exec()

    def _stop_live(self) -> None:
        """Stop any running Coach Live / Live-Demo process."""
        for proc, args in list(self._children):
            if args and args[0] == "live":
                self._kill(proc)
        self._prune()
        self._refresh_buttons()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Kill every process this hub started before exiting."""
        for proc, _args in list(self._children):
            self._kill(proc)
        self._children.clear()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> None:
    from .logging_setup import setup_logging
    setup_logging()
    app = QApplication(sys.argv)
    load_fonts()                     # before the stylesheet: it only names the faces
    app.setStyleSheet(qss())
    win = MainWindow()
    win.show()
    if not wizard_seen():            # first run: greet with the getting-started wizard
        win._show_wizard()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
