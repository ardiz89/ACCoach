"""Unified entry point:  python -m accoach <command> [args]

One front door instead of a pile of run_*.py scripts. Each command lazily imports
its module so an optional dependency (e.g. PySide6 for the GUI bits) only matters
when you actually use that command.
"""

from __future__ import annotations

import sys

_HELP = """HONE — know why you're slow. Real-time driving coach for Assetto Corsa / ACC

Usage:  python -m accoach <command> [options]

Live coaching:
  live [--silent] [--demo]   coach + on-screen overlay in one window  (default)
  coach [--silent]           voice coach in the terminal
  launcher                   small GUI with buttons for everything

Frontend (multi-client / second screen):
  server [--demo]            headless backend, broadcasts over WebSocket
  overlay [--interactive]    on-screen HUD (connects to the backend)
  web [--demo]               analysis web app (review saved laps in the browser)

Review & tools:
  debrief [car] [track]      post-session lap breakdown
  monitor                    raw telemetry dashboard
  recorder                   record laps only
  compare                    live delta dashboard
  verify-g                   validate the G-force axes against the game
  verify-yaw                 validate the yaw-rate sign (oversteer detection)
  verify-aids                validate the ACC aid-level mapping (live)
  verify-sectors             validate the sim's real sector data (live)
  verify-diag [car] [track]  offline FP-rate check of the lap diagnosis
  import-reference <file>    import a lap as a clean reference (cold-start seed)
  logs                       open the folder with logs and crash reports
"""


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0].lower() if args else ""
    rest = args[1:]

    if cmd in ("", "-h", "--help", "help"):
        print(_HELP)
        return

    from .logging_setup import setup_logging
    setup_logging()

    if cmd == "live":
        from .app import main as run
        run(rest)
    elif cmd == "coach":
        from .coach_app import main as run
        run(rest)
    elif cmd == "launcher" or cmd == "gui":
        from .launcher import main as run
        run(rest)
    elif cmd == "server":
        from .server import main as run
        run(rest)
    elif cmd == "web":
        from .api import main as run
        run(rest)
    elif cmd == "overlay":
        from .overlay import main as run
        run(rest)
    elif cmd == "debrief":
        from .debrief_app import main as run
        run(rest)
    elif cmd == "monitor":
        from .monitor import main as run
        run()
    elif cmd == "recorder":
        from .recorder_app import main as run
        run()
    elif cmd == "compare":
        from .compare_app import main as run
        run()
    elif cmd in ("verify-g", "gaxis"):
        from .diagnostics import run_gaxis
        run_gaxis()
    elif cmd in ("verify-yaw", "yaw"):
        from .diagnostics import run_yaw
        run_yaw()
    elif cmd in ("verify-aids", "aids"):
        from .diagnostics import run_aids
        run_aids()
    elif cmd in ("verify-sectors", "sectors"):
        from .diagnostics import run_sectors
        run_sectors()
    elif cmd in ("verify-diag", "diag"):
        from .diagnostics import run_diag
        run_diag(rest)
    elif cmd in ("import-reference", "import-ref"):
        from .diagnostics import run_import_reference
        run_import_reference(rest)
    elif cmd == "selftest":
        from .diagnostics import run_selftest
        run_selftest()
    elif cmd == "logs":
        import os
        from .paths import logs_dir
        d = logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        print(f"Logs: {d}")
        try:
            os.startfile(d)   # noqa: S606 - Windows: open in Explorer
        except Exception:
            pass
    else:
        print(f"Unknown command: {cmd!r}\n")
        print(_HELP)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
