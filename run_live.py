"""Convenience launcher: `python run_live.py [--silent] [--demo]`.

Live coaching with the on-screen overlay in one window. Adds ./src to the path
so you can run without installing the package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.app import main  # noqa: E402

if __name__ == "__main__":
    main()
