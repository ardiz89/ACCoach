"""Convenience launcher: `python run_verify_sectors.py` from the project root.

Validates the sim's real sector data (currentSectorIndex / sectorCount) against
the live game — drive a lap and confirm the Settori view's splits are correct.
Adds ./src to the path so you can run without installing the package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.diagnostics import run_sectors  # noqa: E402

if __name__ == "__main__":
    run_sectors()
