"""Locate, back up and safely write ACC setup files on disk.

Setups live under ``Documents/Assetto Corsa Competizione/Setups/<car>/<track>/``.
Writing rules (see ``ENGINEER.md`` §2 "Sicurezza"):

* **never** clobber without a backup — copy the original under ``.accoach_backup/``;
* write **atomically** (temp file + ``os.replace``) so a crash can't leave a
  half-written, unparseable setup;
* default to a **new file name**, so the driver's own setup stays intact and the
  garage reliably reloads the new one (ACC may not re-read a same-name file);
* offer **undo** from the most recent backup.

The game applies a written setup only when the driver reloads it in the garage —
this layer just puts a correct file in the right place.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

SETUPS_ROOT = (
    Path.home() / "Documents" / "Assetto Corsa Competizione" / "Setups"
)
AC_SETUPS_ROOT = Path.home() / "Documents" / "Assetto Corsa" / "setups"

# Both games, in display order. ACC first (the richer format we lead with).
DEFAULT_ROOTS = (SETUPS_ROOT, AC_SETUPS_ROOT)

_BACKUP_DIR = ".accoach_backup"
_SETUP_GLOBS = ("*.json", "*.ini")


def car_track_dir(car: str, track: str, root: Path | str = SETUPS_ROOT) -> Path:
    return Path(root) / car / track


def list_setups(
    car: str, track: str, root: Path | str = SETUPS_ROOT,
) -> list[Path]:
    """All setup files (``.json`` and ``.ini``) for a car+track, sorted by name."""
    d = car_track_dir(car, track, root)
    if not d.is_dir():
        return []
    found: list[Path] = []
    for pat in _SETUP_GLOBS:
        found += [p for p in d.glob(pat) if p.is_file()]
    return sorted(found)


def backup(path: Path | str) -> Path:
    """Copy ``path`` into a sibling ``.accoach_backup/`` folder; return the copy."""
    path = Path(path)
    bdir = path.parent / _BACKUP_DIR
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = bdir / f"{path.stem}.{stamp}{path.suffix}"
    dest.write_bytes(path.read_bytes())
    return dest


def latest_backup(path: Path | str) -> Path | None:
    """Most recent backup for a setup file, or ``None``."""
    path = Path(path)
    bdir = path.parent / _BACKUP_DIR
    if not bdir.is_dir():
        return None
    candidates = sorted(bdir.glob(f"{path.stem}.*{path.suffix}"))
    return candidates[-1] if candidates else None


def write_atomic(path: Path | str, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file + atomic replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)            # atomic on Windows and POSIX


def save(
    setup,
    dest_dir: Path | str,
    name: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Write ``setup`` to ``dest_dir/<name>.<ext>`` (backing up if it exists).

    The extension comes from the setup's native format (``.json`` for ACC,
    ``.ini`` for AC). Refuses to overwrite unless ``overwrite=True``; when
    overwriting, the previous file is backed up first.
    """
    dest_dir = Path(dest_dir)
    ext = "." + getattr(setup, "ext", "json")
    if not name.endswith(ext):
        name += ext
    dest = dest_dir / name
    if dest.exists():
        if not overwrite:
            raise FileExistsError(
                f"{dest.name} esiste già (usa overwrite=True o un nome nuovo)"
            )
        backup(dest)
    write_atomic(dest, setup.to_text())
    return dest


def undo(path: Path | str) -> Path:
    """Restore a setup file from its most recent backup; returns the path."""
    path = Path(path)
    bak = latest_backup(path)
    if bak is None:
        raise FileNotFoundError(f"nessun backup per {path.name}")
    write_atomic(path, bak.read_text(encoding="utf-8"))
    return path


def load_setup(path: Path | str):
    """Load a setup of either format (ACC ``.json`` or AC ``.ini``)."""
    from .loader import load_any
    return load_any(path)
