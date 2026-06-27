"""Load a setup file in whichever format it is (ACC ``.json`` or AC ``.ini``).

Both loaders return objects with the same access surface (``specs()``,
``present``/``slots``/``click``/``set_click``/``adjust``/``physical``,
``copy``/``to_text``/``car_name``/``ext``), so the diff, store, REST and UI
layers stay format-agnostic.
"""

from __future__ import annotations

from pathlib import Path

from . import ac_format, acc_format


def load_any(path: Path | str):
    """Load a setup by file extension. Raises ValueError on an unknown type."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return acc_format.load(path)
    if suffix == ".ini":
        return ac_format.load(path)
    raise ValueError(f"formato setup non riconosciuto: {path.suffix}")
