"""Convenience launcher: `python run_overlay.py [--interactive] [ws://...]`.

Starts the on-screen overlay (a WebSocket client of the backend). Run the
backend first with `python run_server.py`. Needs PySide6.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.overlay import main  # noqa: E402

if __name__ == "__main__":
    main()
