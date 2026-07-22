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
import os
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path

from ..logging_setup import get_logger
from ..paths import laps_dir as _default_laps_dir
from ..telemetry.snapshot import format_lap_time
from .lap import Lap

_log = get_logger("storage")


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


def _write_atomic(path: Path, payload: bytes) -> None:
    """Gzip ``payload`` into ``path`` so readers never see a half-written lap.

    Writing straight to the destination leaves a corrupt file behind if the
    process dies mid-write, or if two recorders end a lap at the same instant
    (running ``live`` and ``server`` together does exactly that). We already have
    one on disk: a lap whose gzip header is valid but with 79 bytes of another
    write stuck on the end — readable only by decompressing the first member by
    hand.

    Writing to a temp file in the same directory and renaming closes that door:
    ``os.replace`` is atomic on Windows and POSIX alike, so the destination
    either doesn't exist yet or is a complete lap — never something in between.
    """
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with gzip.open(tmp, "wb") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        # Don't leave debris behind when the write fails or is interrupted.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:      # pragma: no cover - best effort
            pass
        raise


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
    _write_atomic(path, payload)

    # Keep the index in step (best-effort; the catalog is a rebuildable cache).
    try:
        from .catalog import LapCatalog

        with LapCatalog(_catalog_path(laps_dir)) as cat:
            cat.upsert(path)
    except Exception:
        # The catalog is a rebuildable cache; a failure here must not lose the
        # lap we just wrote, but we want to know it happened.
        _log.warning("catalog upsert failed for %s", path.name, exc_info=True)
    return path


def _read_gzip_salvaging(path: Path) -> bytes:
    """Decompress ``path``, falling back to its first gzip member if truncated.

    Laps written before :func:`_write_atomic` can carry trailing bytes from a
    second, interrupted write. ``gzip`` treats those as another member and
    raises, so the whole lap reads as lost — even though the real one sits
    intact in the first member. Decompress that member explicitly and keep it;
    the leftovers are the failed write, and dropping them is the point.
    """
    try:
        with gzip.open(path, "rb") as fh:
            return fh.read()
    except (gzip.BadGzipFile, EOFError, zlib.error):
        obj = zlib.decompressobj(16 + zlib.MAX_WBITS)     # 16 = expect a gzip header
        data = obj.decompress(Path(path).read_bytes())    # raises if even this is junk
        _log.warning("%s: trailing garbage after the lap (%d bytes) — "
                     "recovered the first gzip member",
                     Path(path).name, len(obj.unused_data))
        return data


def load_lap(path: Path | str) -> Lap:
    data = json.loads(_read_gzip_salvaging(Path(path)).decode("utf-8"))
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
    road_temp: float | None = None,
) -> Lap | None:
    """Fastest valid lap on disk for this car+track, or ``None`` if there is none.

    Uses the SQLite catalog (one indexed lookup, loads only the winning file) and
    falls back to a full directory scan if the catalog can't be used.

    ``road_temp`` is today's track temperature: pass it and a lap driven in
    comparable conditions is preferred over a faster one driven in different
    ones (see :meth:`LapCatalog.best_reference_path`). Omitting it keeps the
    old behaviour, which is what the offline analysis tools want — there,
    "the best lap" means the best lap.
    """
    laps_dir = Path(laps_dir)

    # Fast path: indexed lookup via the catalog.
    try:
        from .catalog import LapCatalog

        with LapCatalog(_catalog_path(laps_dir)) as cat:
            cat.sync(list_lap_files(laps_dir))   # pick up any new/removed files
            path = cat.best_reference_path(car_model, track, road_temp)
            if path is None:
                return None
            lap = load_lap(path)
            # Confirm against the file in case it was renamed/edited out of band;
            # a dirty lap (clean is False) is never a reference.
            if (lap.valid and lap.lap_time_ms > 0 and lap.clean is not False
                    and _slug(lap.car_model) == _slug(car_model)
                    and _slug(lap.track) == _slug(track)):
                return lap
    except Exception:
        # Catalog unusable (locked/corrupt/older schema) — fall back to the scan.
        _log.debug("catalog lookup failed; scanning instead", exc_info=True)

    return _find_reference_by_scan(car_model, track, laps_dir)


def _find_reference_by_scan(
    car_model: str, track: str, laps_dir: Path,
) -> Lap | None:
    """Reference lookup without the catalog: scan + confirm every candidate.

    Same policy as the catalog query: drop dirty laps (clean is False) and prefer
    a confirmed-clean lap over an unknown/legacy one, ties broken on lap time.
    """
    want_car, want_track = _slug(car_model), _slug(track)
    best_clean: Lap | None = None      # clean is True
    best_unknown: Lap | None = None    # clean is None (legacy/AC)
    for path in list_lap_files(laps_dir):
        if not path.name.startswith(f"{want_track}__{want_car}__"):
            continue
        try:
            lap = load_lap(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not lap.valid or lap.lap_time_ms <= 0 or lap.clean is False:
            continue
        if _slug(lap.car_model) != want_car or _slug(lap.track) != want_track:
            continue
        if lap.clean is True:
            if best_clean is None or lap.lap_time_ms < best_clean.lap_time_ms:
                best_clean = lap
        elif best_unknown is None or lap.lap_time_ms < best_unknown.lap_time_ms:
            best_unknown = lap
    return best_clean or best_unknown


def describe_lap(lap: Lap) -> str:
    """One-line human summary, handy for CLIs and logs."""
    flag = "" if lap.valid else "  (partial/invalid)"
    return (
        f"{lap.track or '?'} · {lap.car_model or '?'} · "
        f"{format_lap_time(lap.lap_time_ms)} · {len(lap.samples)} samples{flag}"
    )
