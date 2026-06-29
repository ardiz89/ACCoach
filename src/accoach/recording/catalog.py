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

# v2: added clean (-1 unknown / 0 dirty / 1 clean) + track-condition columns,
# so the reference query can exclude dirty laps and prefer confirmed-clean ones.
# v3: added `source` ("own"/"pro") so a PRO benchmark lap can be found cheaply.
_DB_VERSION = 3

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
    clean          INTEGER NOT NULL DEFAULT -1,
    air_temp       REAL,
    road_temp      REAL,
    grip           REAL,
    tyre_compound  TEXT,
    source         TEXT NOT NULL DEFAULT 'own',
    recorded_utc   TEXT,
    sample_count   INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lap_ref
    ON lap (car_key, track_key, valid, clean, lap_time_ms);
CREATE INDEX IF NOT EXISTS ix_lap_recent
    ON lap (car_key, track_key, recorded_utc);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _clean_to_int(value: object) -> int:
    """Lap JSON ``clean`` (true/false/null/absent) -> -1 unknown / 0 dirty / 1 clean."""
    if value is None:
        return -1
    return 1 if value else 0


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
        "clean": _clean_to_int(d.get("clean")),
        "air_temp": float(d.get("air_temp", 0.0) or 0.0),
        "road_temp": float(d.get("road_temp", 0.0) or 0.0),
        "grip": float(d.get("grip", 0.0) or 0.0),
        "tyre_compound": str(d.get("tyre_compound", "")),
        "source": str(d.get("source") or "own"),
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
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """The catalog is a rebuildable cache: on an older schema, drop the lap
        table and recreate it (``sync`` re-indexes from the files). Cheap and
        avoids fragile ALTER TABLE chains."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'db_version'"
        ).fetchone()
        version = int(row["value"]) if row else None
        if version is not None and version < _DB_VERSION:
            self._conn.execute("DROP TABLE IF EXISTS lap")
            self._conn.executescript(_SCHEMA)   # recreate lap + indexes
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('db_version', ?)",
            (str(_DB_VERSION),),
        )

    def upsert(self, path: Path | str, meta: dict | None = None) -> bool:
        """Index a single lap file (reads its header if ``meta`` not given)."""
        path = Path(path)
        meta = meta or _read_meta(path)
        if meta is None:
            return False
        self._conn.execute(
            """INSERT INTO lap
                 (path, car_key, track_key, car_model, track, session,
                  lap_time_ms, valid, clean, air_temp, road_temp, grip,
                  tyre_compound, source, recorded_utc, sample_count, schema_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET
                  car_key=excluded.car_key, track_key=excluded.track_key,
                  car_model=excluded.car_model, track=excluded.track,
                  session=excluded.session, lap_time_ms=excluded.lap_time_ms,
                  valid=excluded.valid, clean=excluded.clean,
                  air_temp=excluded.air_temp, road_temp=excluded.road_temp,
                  grip=excluded.grip, tyre_compound=excluded.tyre_compound,
                  source=excluded.source, recorded_utc=excluded.recorded_utc,
                  sample_count=excluded.sample_count,
                  schema_version=excluded.schema_version""",
            (
                str(path), self._slug(meta["car_model"]),
                self._slug(meta["track"]), meta["car_model"], meta["track"],
                meta["session"], meta["lap_time_ms"], meta["valid"],
                meta.get("clean", -1), meta.get("air_temp", 0.0),
                meta.get("road_temp", 0.0), meta.get("grip", 0.0),
                meta.get("tyre_compound", ""), meta.get("source", "own"),
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
        """Path of the fastest valid lap for this car+track, or ``None``.

        NOTE: ignores cleanliness — kept for callers that just want the fastest
        complete lap. For coaching use :meth:`best_reference_path`.
        """
        row = self._conn.execute(
            """SELECT path FROM lap
               WHERE car_key = ? AND track_key = ? AND valid = 1 AND lap_time_ms > 0
               ORDER BY lap_time_ms ASC LIMIT 1""",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        return row["path"] if row else None

    def best_reference_path(self, car_model: str, track: str) -> str | None:
        """Path of the best *trustworthy* reference lap for this car+track.

        Excludes dirty laps (clean = 0) entirely, and prefers a confirmed-clean
        lap (clean = 1) over an unknown/legacy one (clean = -1); ties break on
        lap time. Returns ``None`` if there is no usable lap — the caller then
        honestly reports "no reference" instead of coaching against a cut lap.
        """
        row = self._conn.execute(
            """SELECT path FROM lap
               WHERE car_key = ? AND track_key = ? AND valid = 1
                     AND lap_time_ms > 0 AND clean <> 0
               ORDER BY (clean = 1) DESC, lap_time_ms ASC LIMIT 1""",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        return row["path"] if row else None

    def fastest_pro_path(self, car_model: str, track: str) -> str | None:
        """Path of the fastest imported PRO benchmark lap, or ``None`` if none."""
        row = self._conn.execute(
            """SELECT path FROM lap
               WHERE car_key = ? AND track_key = ? AND valid = 1
                     AND lap_time_ms > 0 AND source = 'pro'
               ORDER BY lap_time_ms ASC LIMIT 1""",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        return row["path"] if row else None

    def laps_for(self, car_model: str, track: str) -> list[dict]:
        """All indexed laps for a car+track, most recently recorded first."""
        rows = self._conn.execute(
            """SELECT path, lap_time_ms, valid, source, recorded_utc, sample_count
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
