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
        QFrame,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - optional dependency
    print("The launcher needs PySide6.  Install it with:  pip install PySide6")
    raise SystemExit(1)

_SRC = Path(__file__).resolve().parents[1]   # .../src

# Sentinels: buttons that do something other than spawn an accoach command.
_GUIDE = "__guide__"
_STOP_LIVE = "__stop_live__"

# Commands that run a speaking coach. Only one may run at a time — two voice
# engines talking together sound like an echo — so starting one stops the other.
_VOICE_CMDS = {"live", "coach"}

# While Coach Live is running these buttons stay clickable; all others are
# disabled so you can't stack a second coach/telemetry reader on top of it.
# Keys: command buttons by their args tuple, special buttons by their sentinel.
_LIVE_SAFE_KEYS = {_STOP_LIVE, _GUIDE, ("web",), ("web", "--engineer")}

# (label, command args / sentinel, opens-its-own-console)
_BUTTONS = [
    ("▶  Coach Live  (overlay + voce)", ["live"], False),
    ("▶  Coach Live — DEMO (senza gioco)", ["live", "--demo"], False),
    ("⏹  Ferma Coach Live", _STOP_LIVE, False),
    ("—", None, False),
    ("📊  Analisi & Report (browser)", ["web"], False),
    ("🔧  Ingegnere di pista (browser)", ["web", "--engineer"], False),
    ("📈  Debrief ultimo giro", ["debrief"], True),
    ("📈  Monitor telemetria", ["monitor"], True),
    ("🎙  Coach vocale (terminale)", ["coach"], True),
    ("🔧  Verifica assi G", ["verify-g"], True),
    ("—", None, False),
    ("❓  Guida — come si usa", _GUIDE, False),
]


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
        print(f"Impossibile aprire la guida ({path}): {exc}")


class Launcher(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ACCoach")
        self.resize(380, 560)
        # Every process we spawn, so we can stop them on demand / on close.
        self._children: list[tuple[subprocess.Popen, list[str]]] = []
        # key -> button, so we can enable/disable them while Coach Live runs.
        self._buttons: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("ACCoach")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        subtitle = QLabel("Real-time driving coach · AC / ACC")
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

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
            elif args == _STOP_LIVE:
                btn.clicked.connect(self._stop_live)
            else:
                btn.clicked.connect(partial(self._spawn, args, console))
            key = tuple(args) if isinstance(args, list) else args
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch(1)
        hint = QLabel("Suggerimento: imposta il gioco in modalità Borderless\n"
                      "perché l'overlay si disegni sopra.")
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
    app = QApplication(sys.argv)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
