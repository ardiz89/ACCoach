"""PyInstaller entry point for ACCoach.exe.

The packaged exe behaves like ``python -m accoach``: `ACCoach.exe live`,
`ACCoach.exe web`, etc. With no arguments it opens the GUI launcher.
"""

import os
import sys


def main() -> None:
    # In a windowed (no-console) frozen build, stdout/stderr are None; give them a
    # sink so prints and uvicorn's logging don't crash.
    if getattr(sys, "frozen", False):
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")

    try:
        from accoach.__main__ import main as dispatch
    except ImportError:
        # Running from source (not frozen): make ./src importable.
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
        from accoach.__main__ import main as dispatch

    if len(sys.argv) <= 1:
        sys.argv.append("launcher")
    dispatch()


if __name__ == "__main__":
    main()
