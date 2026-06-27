"""Central logging configuration for ACCoach.

Call :func:`setup_logging` once at process start (done by every entry point).
It installs a rotating file handler at ``~/Documents/ACCoach/logs/accoach.log``
(always DEBUG, so a user can send us a full log) plus an optional console
handler at the requested level. Idempotent — safe to call more than once.

Modules get their logger with :func:`get_logger("module")`; everything hangs
off the ``accoach`` logger so a single ``setup_logging`` configures them all.
"""

from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
import threading
import traceback
from datetime import datetime

from . import __version__
from .paths import logs_dir

_ROOT_NAME = "accoach"
_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured = False


def _coerce_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    return logging.getLevelName(str(level).upper())  # name -> int


def setup_logging(level: int | str = logging.INFO, *, console: bool = True) -> logging.Logger:
    """Configure the ``accoach`` logger tree. Returns the root ACCoach logger."""
    global _configured
    root = logging.getLogger(_ROOT_NAME)
    if _configured:
        return root

    root.setLevel(logging.DEBUG)   # handlers decide what actually gets emitted
    root.propagate = False

    # File handler — full DEBUG detail for support. Must never crash the app.
    try:
        d = logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            d / "accoach.log", maxBytes=1_000_000, backupCount=7, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(_FMT))
        root.addHandler(fh)
    except Exception:   # noqa: BLE001 - logging setup must be best-effort
        pass

    # Console handler — at the requested level. Guard against a None stream
    # (PyInstaller windowed builds set sys.stderr = None).
    if console and sys.stderr is not None:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(_coerce_level(level))
        ch.setFormatter(logging.Formatter(_FMT))
        root.addHandler(ch)

    _configured = True
    root.info(
        "=== ACCoach %s starting === python=%s os=%s",
        __version__, platform.python_version(), platform.platform(),
    )
    install_crash_handlers()
    return root


def get_logger(name: str) -> logging.Logger:
    """Logger for a submodule, e.g. ``get_logger("server")``."""
    return logging.getLogger(_ROOT_NAME).getChild(name)


_crash_installed = False


def _write_crash_file(exc_type, exc_value, exc_tb, *, where: str) -> None:
    """Best-effort dedicated crash report; never raises."""
    try:
        d = logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = d / f"crash-{stamp}.log"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(f"ACCoach {__version__} crash\n")
            fh.write(f"when:   {datetime.now().isoformat(timespec='seconds')}\n")
            fh.write(f"where:  {where}\n")
            fh.write(f"python: {platform.python_version()}\n")
            fh.write(f"os:     {platform.platform()}\n")
            fh.write("-" * 60 + "\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=fh)
        logging.getLogger(_ROOT_NAME).error("crash report written to %s", path)
    except Exception:   # noqa: BLE001 - the crash handler must not crash
        pass


def install_crash_handlers() -> None:
    """Route uncaught exceptions (main thread + worker threads) to the log and a
    dedicated crash file, instead of vanishing on a windowed build. Idempotent."""
    global _crash_installed
    if _crash_installed:
        return
    log = logging.getLogger(_ROOT_NAME)
    prev_hook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        # Ctrl+C is a normal exit, not a crash — defer to the default handler.
        if issubclass(exc_type, KeyboardInterrupt):
            prev_hook(exc_type, exc_value, exc_tb)
            return
        log.critical("uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        _write_crash_file(exc_type, exc_value, exc_tb, where="main thread")

    def _threadhook(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        name = getattr(args.thread, "name", "?")
        log.critical("uncaught exception in thread %s", name,
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        _write_crash_file(args.exc_type, args.exc_value, args.exc_traceback,
                          where=f"thread {name}")

    sys.excepthook = _excepthook
    threading.excepthook = _threadhook
    _crash_installed = True
