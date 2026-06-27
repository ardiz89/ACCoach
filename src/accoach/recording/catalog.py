"""SQLite index over the recorded laps.

The lap files stay exactly as they are (gzipped JSON in ``laps/``); this adds a
lightweight catalog *beside* them so the common queries stop scanning and
decompressing the whole directory. Finding the reference lap becomes a single
indexed lookup that touches one file (the winner) instead of every file.

The catalog is a cache, not the source of truth — it can be deleted and rebuilt
from the files at any time via :meth:`LapCatalog.sync`. Metadata is read from
each file's JSON header without materializing its samples, so indexing is cheap.

This is the P0 step from the data-architecture review: index first, no on-disk
format change, no migration. Sessions / Parquet samples / sector tables come
later on top of the same DB.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

_DB_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lap (
    lap_id         INTEGER PRIMARY KEY,
    path           TEXT NOT NULL UNIQUE,
    car_key        TEXT NOT NULL,
    track_key      TEXT NOT NULL,
    car_model      TEXT NOT NULL,
    track          TEXT NOT NULL,
    session        INTEGER NOT NULL,
    lap_time_ms    INTEGER NOT NULL,
    valid          INTEGER NOT NULL,
    recorded_utc   TEXT,
    sample_count   INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lap_ref
    ON lap (car_key, track_key, valid, lap_time_ms);
CREATE INDEX IF NOT EXISTS ix_lap_recent
    ON lap (car_key, track_key, recorded_utc);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _read_meta(path: Path) -> dict | None:
    """Read a lap file's metadata + sample count without building samples."""
    try:
        with gzip.open(path, "rb") as fh:
            d = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return {
        "car_model": str(d.get("car_model", "")),
        "track": str(d.get("track", "")),
        "session": int(d.get("session", -1)),
        "lap_time_ms": int(d.get("lap_time_ms", 0)),
        "valid": 1 if d.get("valid") else 0,
        "recorded_utc": str(d.get("recorded_utc", "")),
        "sample_count": len(d.get("samples", [])),
        "schema_version": int(d.get("schema", 1)),
    }


class LapCatalog:
    """A SQLite index of lap files. Best-effort; safe to rebuild from disk."""

    def __init__(self, db_path: Path | str, slug=None) -> None:
        # slug is injected to stay consistent with storage's filename slugging.
        from .storage import _slug as _default_slug  # local import avoids cycle

        self._slug = slug or _default_slug
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('db_version', ?)",
            (str(_DB_VERSION),),
        )
        self._conn.commit()

    def upsert(self, path: Path | str, meta: dict | None = None) -> bool:
        """Index a single lap file (reads its header if ``meta`` not given)."""
        path = Path(path)
        meta = meta or _read_meta(path)
        if meta is None:
            return False
        self._conn.execute(
            """INSERT INTO lap
                 (path, car_key, track_key, car_model, track, session,
                  lap_time_ms, valid, recorded_utc, sample_count, schema_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET
                  car_key=excluded.car_key, track_key=excluded.track_key,
                  car_model=excluded.car_model, track=excluded.track,
                  session=excluded.session, lap_time_ms=excluded.lap_time_ms,
                  valid=excluded.valid, recorded_utc=excluded.recorded_utc,
                  sample_count=excluded.sample_count,
                  schema_version=excluded.schema_version""",
            (
                str(path), self._slug(meta["car_model"]),
                self._slug(meta["track"]), meta["car_model"], meta["track"],
                meta["session"], meta["lap_time_ms"], meta["valid"],
                meta["recorded_utc"], meta["sample_count"], meta["schema_version"],
            ),
        )
        self._conn.commit()
        return True

    def sync(self, lap_files: list[Path]) -> int:
        """Index any files not already in the catalog, and drop missing ones.

        Returns the number of newly indexed files.
        """
        known = {row["path"] for row in self._conn.execute("SELECT path FROM lap")}
        present = {str(p) for p in lap_files}

        added = 0
        for p in lap_files:
            if str(p) not in known and self.upsert(p):
                added += 1

        stale = known - present
        if stale:
            self._conn.executemany(
                "DELETE FROM lap WHERE path = ?", [(s,) for s in stale]
            )
            self._conn.commit()
        return added

    def fastest_valid_path(self, car_model: str, track: str) -> str | None:
        """Path of the fastest valid lap for this car+track, or ``None``."""
        row = self._conn.execute(
            """SELECT path FROM lap
               WHERE car_key = ? AND track_key = ? AND valid = 1 AND lap_time_ms > 0
               ORDER BY lap_time_ms ASC LIMIT 1""",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        return row["path"] if row else None

    def laps_for(self, car_model: str, track: str) -> list[dict]:
        """All indexed laps for a car+track, most recently recorded first."""
        rows = self._conn.execute(
            """SELECT path, lap_time_ms, valid, recorded_utc, sample_count
               FROM lap WHERE car_key = ? AND track_key = ?
               ORDER BY recorded_utc DESC""",
            (self._slug(car_model), self._slug(track)),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM lap").fetchone()["n"]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "LapCatalog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
