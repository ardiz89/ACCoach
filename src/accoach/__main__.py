"""Unified entry point:  python -m accoach <command> [args]

One front door. From a source checkout the same commands go through
``accoach_main.py`` (which puts ``src`` on the path and is also the packaged
exe's entry point), so ``HONE.bat``, ``ACCoach.exe`` and ``python -m accoach``
all dispatch here. Each command lazily imports its module so an optional
dependency (e.g. PySide6 for the GUI bits) only matters when you use it.

The default help lists the three commands a *driver* needs. The rest — headless
backend, standalone overlay, live validation harnesses — are real and supported,
but a driver reading fifteen commands has to decide which of them is their job,
and none of them is. They live behind ``help --all``.
"""

from __future__ import annotations

import sys

_HELP = """HONE — know why you're slow. Real-time driving coach for Assetto Corsa / ACC

Usage:  python -m accoach <command> [options]
        python accoach_main.py <command>       (from a source checkout)

  live [--silent] [--demo]   coach + on-screen overlay while you drive  (default)
  web                        review your saved laps in the browser
  launcher                   the window with buttons for everything

Nothing else is needed to drive.  `help --all` lists the tools.
"""

_HELP_TOOLS = """Tools — development, live validation, second-screen setups.

Coaching, split up:
  coach [--silent]           voice coach in the terminal (no overlay)
  recorder                   record laps only, no coaching
  debrief [car] [track]      post-session lap breakdown in the terminal
  compare                    live delta dashboard
  monitor                    raw telemetry dashboard

Multi-client (backend and clients as separate processes):
  server [--demo]            headless backend, broadcasts over WebSocket
  overlay [--interactive]    on-screen HUD (connects to the backend)
  web [--demo]               analysis web app (--demo: synthetic laps, no game)

Validation — these read the live game, so the sim must be running:
  dryrun [--seconds N]       print every cue the detectors would raise, with the
                             channel values that triggered it (no voice)
  stats [--seconds N]        channel distributions in the regimes the thresholds
                             live in — braking, cornering, throttle-on
  verify-g                   validate the G-force axes against the game
  verify-yaw                 validate the yaw-rate sign (oversteer detection)
  verify-aids                validate the ACC aid-level mapping (live)
  find-rain                  find ACC's rain/grip fields by measuring them (live)
  verify-sectors             validate the sim's real sector data (live)
  verify-diag [car] [track]  offline FP-rate check of the lap diagnosis

  import-reference <file>    import a lap as a clean reference (cold-start seed)
  setup <list|show|bump|undo>  read and edit an ACC setup file, no game running
                             (`setup bump --help` for the arguments)
  selftest                   check the TTS voice, write a report (works windowed)
  logs                       open the folder with logs and crash reports
"""


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0].lower() if args else ""
    rest = args[1:]

    if cmd in ("", "-h", "--help", "help"):
        print(_HELP)
        if any(a.lower() in ("--all", "-a", "all", "tools") for a in rest):
            print(_HELP_TOOLS)
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
    elif cmd in ("dryrun", "dry", "stats", "stat"):
        # The two instruments a calibration session is actually made of (see
        # TARATURE-ACC.md). They were reachable only as `python -m
        # accoach.diagnostics dryrun`, which is not a thing anyone types with a
        # helmet on. Delegated whole so `--seconds` keeps being parsed in one place.
        from .diagnostics import main as diagnose
        diagnose([cmd, *rest])
    elif cmd in ("verify-g", "gaxis"):
        from .diagnostics import run_gaxis
        run_gaxis()
    elif cmd in ("verify-yaw", "yaw"):
        from .diagnostics import run_yaw
        run_yaw()
    elif cmd in ("verify-aids", "aids"):
        from .diagnostics import run_aids
        run_aids()
    elif cmd in ("find-rain", "rain"):
        from .diagnostics import run_rain
        run_rain()
    elif cmd in ("verify-sectors", "sectors"):
        from .diagnostics import run_sectors
        run_sectors()
    elif cmd in ("verify-diag", "diag"):
        from .diagnostics import run_diag
        run_diag(rest)
    elif cmd in ("import-reference", "import-ref"):
        from .diagnostics import run_import_reference
        run_import_reference(rest)
    elif cmd == "setup":
        # Reachable as `python -m accoach.setup.cli` since F0, and therefore by
        # nobody: it was the last second front door left after the wrappers went.
        from .setup.cli import main as setup_cli
        setup_cli(rest)
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
        # Everything on an unknown command: whoever typed one knows what a
        # command is, and the tool they meant is probably in the long list.
        print(f"Unknown command: {cmd!r}\n")
        print(_HELP)
        print(_HELP_TOOLS)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
