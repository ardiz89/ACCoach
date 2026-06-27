"""Convenience launcher: `python run_web.py [--demo]` — the analysis web app.

Serves a local web page to review saved laps. Adds ./src to the path so you can
run without installing the package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from accoach.api import main  # noqa: E402

if __name__ == "__main__":
    main()
