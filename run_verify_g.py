"""Convenience launcher: `python run_verify_g.py` from the project root.

Validates the G-force axis mapping against the live game. Adds ./src to the path
so you can run without installing the package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.diagnostics import run_gaxis  # noqa: E402

if __name__ == "__main__":
    run_gaxis()
