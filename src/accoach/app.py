"""Live coaching in a single window — engine + voice + overlay together.

The everyday way to use ACCoach: one process, no second terminal, no WebSocket.
A PySide6 timer drives the :class:`~accoach.engine.CoachEngine`, speaks cues, and
feeds the same :class:`~accoach.overlay.Overlay` widget directly (via
``apply_state``) instead of over a socket.

    python -m accoach live            # coach + on-screen overlay (voice on)
    python -m accoach live --silent   # overlay only, no audio
    python -m accoach live --demo     # synthetic lap, no game needed

For multi-client / second-screen setups use the websocket backend instead
(``python -m accoach server`` + ``python -m accoach overlay``).
"""

from __future__ import annotations

import signal
import sys
import time

from .coaching import Voice
from .engine import CoachEngine
from .serialize import state_to_dict

TICK_MS = 50  # 20 Hz engine tick


def main(argv: list[str] | None = None) -> None:
    from .logging_setup import setup_logging
    setup_logging()
    argv = sys.argv[1:] if argv is None else argv
    silent = "--silent" in argv or "-s" in argv
    demo = "--demo" in argv
    interactive = "--interactive" in argv or "-i" in argv

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("Live mode needs PySide6.  Install it with:  pip install PySide6")
        raise SystemExit(1)

    from .overlay import Overlay

    from .config import load_config
    cfg = load_config()
    lang = cfg.language
    voice_on = (not silent) and cfg.voice.enabled
    if demo:
        from .demo import make_demo_engine

        engine = make_demo_engine()
        if voice_on:
            engine.voice = Voice(enabled=True, rate=cfg.voice.rate, language=lang)
    else:
        engine = CoachEngine(
            voice=Voice(enabled=voice_on, rate=cfg.voice.rate, language=lang),
            acquire_hz=cfg.acquire.hz)

    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    overlay = Overlay(url=None, interactive=interactive)  # fed in-process
    overlay.show()

    def step() -> None:
        state = engine.tick(time.monotonic())
        overlay.apply_state(state_to_dict(state))

    timer = QTimer()
    timer.timeout.connect(step)
    timer.start(TICK_MS)

    try:
        app.exec()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
