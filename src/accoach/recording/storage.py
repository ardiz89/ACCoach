"""Persist recorded laps and find a reference lap to coach against.

Laps are written as gzipped JSON under a ``laps/`` directory (one file per lap),
named so they're sortable and self-explanatory::

    laps/<track>__<car>__<laptime>__<utc>.lap.json.gz

The reference lap for a given car+track is simply the fastest *valid* lap on
disk for that combination — that's what the comparison layer will line the live
lap up against.
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..telemetry.snapshot import format_lap_time
from .lap import Lap

def _default_laps_dir() -> Path:
    # A stable, user-writable store used identically from source and from the
    # packaged exe (a path relative to __file__ is meaningless once frozen, and
    # may be read-only). Lives where the user can find it.
    return Path.home() / "Documents" / "ACCoach" / "laps"


DEFAULT_LAPS_DIR = _default_laps_dir()

_SUFFIX = ".lap.json.gz"
_DB_NAME = "catalog.db"


def _catalog_path(laps_dir: Path) -> Path:
    return laps_dir / _DB_NAME


def _slug(text: str) -> str:
    """Filesystem-safe token; empty input becomes ``unknown``."""
    text = (text or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def _laptime_token(ms: int) -> str:
    # 1:23.456 -> "1m23s456", padded so lexical sort == chronological sort.
    if ms <= 0 or ms >= 1_000_000_000:
        return "0m00s000"
    minutes, rem = divmod(ms, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes}m{seconds:02d}s{millis:03d}"


def save_lap(lap: Lap, laps_dir: Path | str = DEFAULT_LAPS_DIR) -> Path:
    """Write ``lap`` to the store and return the file path."""
    laps_dir = Path(laps_dir)
    laps_dir.mkdir(parents=True, exist_ok=True)

    if not lap.recorded_utc:
        lap.recorded_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    stamp = lap.recorded_utc.replace(":", "").replace("-", "").replace("+", "z")
    name = (
        f"{_slug(lap.track)}__{_slug(lap.car_model)}__"
        f"{_laptime_token(lap.lap_time_ms)}__{stamp}{_SUFFIX}"
    )
    path = laps_dir / name
    payload = json.dumps(lap.to_dict(), separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(payload)

    # Keep the index in step (best-effort; the catalog is a rebuildable cache).
    try:
        from .catalog import LapCatalog

        with LapCatalog(_catalog_path(laps_dir)) as cat:
            cat.upsert(path)
    except Exception:
        pass
    return path


def load_lap(path: Path | str) -> Lap:
    with gzip.open(path, "rb") as fh:
        data = json.loads(fh.read().decode("utf-8"))
    return Lap.from_dict(data)


def list_lap_files(laps_dir: Path | str = DEFAULT_LAPS_DIR) -> list[Path]:
    laps_dir = Path(laps_dir)
    if not laps_dir.is_dir():
        return []
    return sorted(laps_dir.glob(f"*{_SUFFIX}"))


def find_reference_lap(
    car_model: str,
    track: str,
    laps_dir: Path | str = DEFAULT_LAPS_DIR,
) -> Lap | None:
    """Fastest valid lap on disk for this car+track, or ``None`` if there is none.

    Uses the SQLite catalog (one indexed lookup, loads only the winning file) and
    falls back to a full directory scan if the catalog can't be used.
    """
    laps_dir = Path(laps_dir)

    # Fast path: indexed lookup via the catalog.
    try:
        from .catalog import LapCatalog

        with LapCatalog(_catalog_path(laps_dir)) as cat:
            cat.sync(list_lap_files(laps_dir))   # pick up any new/removed files
            path = cat.fastest_valid_path(car_model, track)
            if path is None:
                return None
            lap = load_lap(path)
            # Confirm against the file in case it was renamed/edited out of band.
            if (lap.valid and lap.lap_time_ms > 0
                    and _slug(lap.car_model) == _slug(car_model)
                    and _slug(lap.track) == _slug(track)):
                return lap
    except Exception:
        pass  # fall through to the scan

    return _find_reference_by_scan(car_model, track, laps_dir)


def _find_reference_by_scan(
    car_model: str, track: str, laps_dir: Path,
) -> Lap | None:
    """Reference lookup without the catalog: scan + confirm every candidate."""
    want_car, want_track = _slug(car_model), _slug(track)
    best: Lap | None = None
    for path in list_lap_files(laps_dir):
        if not path.name.startswith(f"{want_track}__{want_car}__"):
            continue
        try:
            lap = load_lap(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not lap.valid or lap.lap_time_ms <= 0:
            continue
        if _slug(lap.car_model) != want_car or _slug(lap.track) != want_track:
            continue
        if best is None or lap.lap_time_ms < best.lap_time_ms:
            best = lap
    return best


def describe_lap(lap: Lap) -> str:
    """One-line human summary, handy for CLIs and logs."""
    flag = "" if lap.valid else "  (partial/invalid)"
    return (
        f"{lap.track or '?'} · {lap.car_model or '?'} · "
        f"{format_lap_time(lap.lap_time_ms)} · {len(lap.samples)} samples{flag}"
    )
