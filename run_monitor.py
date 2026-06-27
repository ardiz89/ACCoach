"""Convenience launcher: `python run_monitor.py` from the project root.

Adds ./src to the path so you can run without installing the package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.monitor import main  # noqa: E402

if __name__ == "__main__":
    main()
