"""A small GUI launcher — buttons instead of command lines.

Double-click ``ACCoach.bat`` (or run ``python -m accoach launcher``) to get a
window with one button per mode. Each button starts the matching command in its
own process; terminal modes open in their own console window so you can read
their output.

The launcher OWNS the processes it starts: it tracks every child and kills the
whole tree when you close the window, so nothing is left running in the
background. There's also a dedicated button to stop Coach Live on demand (its
overlay is click-through and has no window of its own).
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
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - optional dependency
    print("The launcher needs PySide6.  Install it with:  pip install PySide6")
    raise SystemExit(1)

from .config import load_config, set_language
from .i18n import LANGUAGES, language_name
from .paths import base_dir

_SRC = Path(__file__).resolve().parents[1]   # .../src

# Sentinels: buttons that do something other than spawn an accoach command.
_GUIDE = "__guide__"
_STOP_LIVE = "__stop_live__"
_WIZARD = "__wizard__"


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

# Commands that run a speaking coach. Only one may run at a time — two voice
# engines talking together sound like an echo — so starting one stops the other.
_VOICE_CMDS = {"live", "coach"}

# While Coach Live is running these buttons stay clickable; all others are
# disabled so you can't stack a second coach/telemetry reader on top of it.
# Keys: command buttons by their args tuple, special buttons by their sentinel.
_LIVE_SAFE_KEYS = {_STOP_LIVE, _GUIDE, _WIZARD, ("web",), ("web", "--engineer")}

# (label, command args / sentinel, opens-its-own-console)
_BUTTONS = [
    ("▶  Coach Live  (overlay + voice)", ["live"], False),
    ("▶  Coach Live — DEMO (no game)", ["live", "--demo"], False),
    ("⏹  Stop Coach Live", _STOP_LIVE, False),
    ("—", None, False),
    ("📊  Analysis & Report (browser)", ["web"], False),
    ("🔧  Race engineer (browser)", ["web", "--engineer"], False),
    ("📈  Last-lap debrief", ["debrief"], True),
    ("📈  Telemetry monitor", ["monitor"], True),
    ("🎙  Voice coach (terminal)", ["coach"], True),
    ("🔧  Verify G axes", ["verify-g"], True),
    ("—", None, False),
    ("✨  Get started", _WIZARD, False),
    ("❓  Guide — how to use", _GUIDE, False),
]


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
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        sub = QLabel("Know why you're slow. Here's how to get going:")
        sub.setStyleSheet("color: #888;")
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)

        steps = "".join(
            f"<p style='margin:0 0 12px 0;'><b>{i}.</b> {t}</p>"
            for i, t in enumerate(_WIZARD_STEPS, 1)
        )
        body = QLabel(steps)
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        body.setStyleSheet("font-size: 13px;")
        lay.addWidget(body)
        lay.addStretch(1)

        self._dont_show = QCheckBox("Don't show this again")
        self._dont_show.setChecked(True)
        lay.addWidget(self._dont_show)

        row = QHBoxLayout()
        guide = QPushButton("Open full guide")
        guide.clicked.connect(_open_guide)
        ok = QPushButton("Get started")
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


class Launcher(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HONE")
        self.resize(380, 560)
        # Every process we spawn, so we can stop them on demand / on close.
        self._children: list[tuple[subprocess.Popen, list[str]]] = []
        # key -> button, so we can enable/disable them while Coach Live runs.
        self._buttons: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("HONE")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        subtitle = QLabel("Know why you're slow. · AC / ACC")
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Language selector — switches the interface + coach voice. Applies on the
        # next Coach Live start (the voice picks its language at startup).
        lang_row = QHBoxLayout()
        lang_lbl = QLabel("Language")
        lang_lbl.setStyleSheet("color: #888;")
        self._lang = QComboBox()
        for code in LANGUAGES:
            self._lang.addItem(language_name(code), code)
        cur = load_config().language
        i = self._lang.findData(cur)
        if i >= 0:
            self._lang.setCurrentIndex(i)
        self._lang.currentIndexChanged.connect(self._on_language)
        lang_row.addWidget(lang_lbl)
        lang_row.addWidget(self._lang, 1)
        layout.addLayout(lang_row)

        for label, args, console in _BUTTONS:
            if args is None:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setStyleSheet("color: #444;")
                layout.addWidget(line)
                continue
            btn = QPushButton(label)
            btn.setMinimumHeight(40)
            btn.setStyleSheet("text-align: left; padding-left: 12px; font-size: 14px;")
            if args == _GUIDE:
                btn.clicked.connect(_open_guide)
            elif args == _WIZARD:
                btn.clicked.connect(self._show_wizard)
            elif args == _STOP_LIVE:
                btn.clicked.connect(self._stop_live)
            else:
                btn.clicked.connect(partial(self._spawn, args, console))
            key = tuple(args) if isinstance(args, list) else args
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch(1)
        hint = QLabel("Tip: set the game to Borderless so the overlay draws over it.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Poll the children so the buttons re-enable themselves when Coach Live
        # ends (stopped, closed, or crashed), not only when you press Stop.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_buttons)
        self._timer.start(1000)
        self._refresh_buttons()

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
        """Disable everything but the live-safe buttons while Coach Live runs."""
        self._prune()
        live = any(a and a[0] == "live" for _p, a in self._children)
        for key, btn in self._buttons.items():
            btn.setEnabled(not live or key in _LIVE_SAFE_KEYS)

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
        """Persist the chosen language (takes effect on the next Coach Live start)."""
        set_language(self._lang.currentData())

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
        """Kill every process this launcher started before exiting."""
        for proc, _args in list(self._children):
            self._kill(proc)
        self._children.clear()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> None:
    from .logging_setup import setup_logging
    setup_logging()
    app = QApplication(sys.argv)
    win = Launcher()
    win.show()
    if not wizard_seen():            # first run: greet with the getting-started wizard
        win._show_wizard()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
