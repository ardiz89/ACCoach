"""Convenience launcher: `python run_launcher.py` — the GUI launcher.

Adds ./src to the path so you can run without installing the package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.launcher import main  # noqa: E402

if __name__ == "__main__":
    main()
