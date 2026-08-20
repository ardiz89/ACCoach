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

import json
import zlib
import sqlite3
from pathlib import Path

# v2: added clean (-1 unknown / 0 dirty / 1 clean) + track-condition columns,
# so the reference query can exclude dirty laps and prefer confirmed-clean ones.
# v3: added `source` ("own"/"pro") so a PRO benchmark lap can be found cheaply.
# v5: `clean` is re-derived on index — a pre-v8 ACC lap's "clean" is demoted to
# unknown (see `_clean_to_int`). The bump matters: without it, every catalog
# already on disk keeps the old verdict and the fix ships to nobody.
# v6: added `fuel_start`/`fuel_end` — the tank level at the two ends of the lap.
# `fuel_used` alone cannot find a stint boundary: a refuel that happens *between*
# two laps leaves both of their burns perfectly normal. Measured on the archive
# (720S/Monza): inside one stint the gap between one lap's end and the next
# lap's start is ±0.01 L, and the one real refuel on disk is +3.18 L.
_DB_VERSION = 6

# How far the track temperature may differ before a lap stops being a fair
# benchmark. Wide on purpose: the point is to rule out the morning-vs-evening
# gap, not to demand a twin of today's session — too narrow a band and the
# preference never finds anything, which is the same as not having it.
_TEMP_BAND_C = 8.0
# How far apart two laps' track grip can be and still count as the same
# conditions. A FIRST BAND, and it is worth knowing why it can't be better than
# that yet: the archive it was written against carries grip on 5 laps out of 39
# — ACC reports 0 by design (see the reader) and the AC laps all read a flat 1.0
# — so nothing here was measured against a real spread. 0.05 is a twentieth of
# the whole scale, which on ACC's own numbers is about the distance between a
# green track and a rubbered-in one.
_GRIP_BAND = 0.05

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
    schema_version INTEGER NOT NULL,
    -- Litres this lap burned (v11 files). NULL on every lap recorded before
    -- the channel existed, and on laps that refuelled: 'not measured' and
    -- 'burned nothing' are different answers.
    fuel_used      REAL,
    -- The tank at the two ends of the lap, in litres (v11 files, NULL before).
    -- Deliberately kept alongside `fuel_used` rather than replacing it: the two
    -- answer different questions. `fuel_used` is a *verdict* ("is this a burn
    -- rate?") and refuses laps that refuelled; these two are raw readings, and
    -- it is precisely a lap that refuelled which starts a new stint.
    fuel_start     REAL,
    fuel_end       REAL
);
CREATE INDEX IF NOT EXISTS ix_lap_ref
    ON lap (car_key, track_key, valid, clean, lap_time_ms);
CREATE INDEX IF NOT EXISTS ix_lap_recent
    ON lap (car_key, track_key, recorded_utc);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
-- The Focus coach's memory across sessions: which corners a driver has mastered
-- (or parked as won't-improve) on a given car+track. Without this, closing HONE
-- reset the lesson plan and the coach re-worked corners already conquered,
-- three laps of ASSESS every time. Survives a lap-table rebuild because
-- `_migrate` only drops `lap`.
CREATE TABLE IF NOT EXISTS focus_state (
    car_key    TEXT NOT NULL,
    track_key  TEXT NOT NULL,
    mastered   TEXT NOT NULL DEFAULT '',   -- comma-separated corner indices
    parked     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (car_key, track_key)
);
-- The training plan you accepted for a car+track: what you're working on and,
-- crucially, *since when* — progress is measured only on laps recorded after
-- that moment. Stored here rather than as a file of its own because it is the
-- same kind of thing as the Focus coach's memory right above it: small,
-- per-combo, and worthless without the laps it refers to. Survives a lap-table
-- rebuild for the same reason (`_migrate` only drops `lap`).
CREATE TABLE IF NOT EXISTS plan (
    car_key     TEXT NOT NULL,
    track_key   TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    goals_json  TEXT NOT NULL,
    PRIMARY KEY (car_key, track_key)
);
-- The race engineer's memory across sessions, per car+track: which phase it had
-- reached, which remedy is next for each symptom, which symptoms ran out of
-- remedies, and the clicks already spent on each lever. Without it, reopening
-- HONE re-proposes a remedy already measured and thrown away, at three laps of
-- baseline plus three of re-test each. The lap window is deliberately NOT in
-- here: those are measurements, and two sessions are not comparable.
-- Same place and same reasons as `focus_state` above; survives a lap-table
-- rebuild because `_migrate` only drops `lap`.
CREATE TABLE IF NOT EXISTS engineer_state (
    car_key    TEXT NOT NULL,
    track_key  TEXT NOT NULL,
    state_json TEXT NOT NULL,
    PRIMARY KEY (car_key, track_key)
);
-- Where a track's pit lane begins, as a normalized lap position. No telemetry
-- field publishes it, so it is MEASURED: the last on-track position before the
-- car enters the lane, one sample per visit (see coaching/pitcall.py). Keyed on
-- the track alone — the pit entry belongs to the circuit, not to the car — and
-- kept as several samples rather than one number so a rejoin or an aborted
-- entry can be outvoted instead of overwriting the truth. Survives a lap-table
-- rebuild for the same reason as the two above (`_migrate` only drops `lap`).
CREATE TABLE IF NOT EXISTS pit_entry (
    track_key  TEXT PRIMARY KEY,
    samples    TEXT NOT NULL DEFAULT ''    -- comma-separated positions, 0..1
);
-- Which corners a circuit really has, learned from the driver's own laps, so a
-- corner keeps its number between them. The detector reads each lap on its own
-- merits and returns five to nine corners for the same Monza depending on the
-- lap, which slides every number after the one it missed; this is the reference
-- to number against (see accoach/cornermap.py).
--
-- Keyed on car AND track, unlike the pit entry above, and the difference is
-- measured: the Formula car finds seven corners at the Nürburgring where the
-- circuit has fifteen, because it never turns the steering far enough in the
-- others. Merging the cars would answer "corner 8" on a lap whose screen has no
-- corners 3 to 7. Survives a lap-table rebuild like its neighbours.
CREATE TABLE IF NOT EXISTS corner_map (
    car_key    TEXT NOT NULL,
    track_key  TEXT NOT NULL,
    corners    TEXT NOT NULL DEFAULT '',   -- pos:direction:seen, semicolon separated
    laps       INTEGER NOT NULL DEFAULT 0, -- laps it was learned from
    PRIMARY KEY (car_key, track_key)
);
"""


def _parse_indices(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


def _join_indices(idx: set[int]) -> str:
    return ",".join(str(i) for i in sorted(idx))


def _clean_to_int(value: object, schema: int = 0, compound: str = "",
                  recorded_utc: str = "") -> int:
    """Lap JSON ``clean`` -> -1 unknown / 0 dirty / 1 clean.

    A thin seam over :func:`accoach.recording.lap.clean_verdict`, which holds the
    rule (and the measurement behind it). Kept as a name because the catalog's
    three-state encoding is a catalog concern; the *policy* is shared with the
    catalog-less fallback scan, and having it in two places is how the two once
    disagreed.
    """
    from .lap import clean_verdict

    return clean_verdict(value, schema, compound, recorded_utc)



def _fuel_levels(d: dict) -> tuple[float, float] | None:
    """The tank at the first and last sample that reported it, in litres.

    Straight off the stored rows — no LapSample objects built. The catalog is
    read on every page load, so it stays a header reader: the rows are already
    parsed JSON here, and finding one column by name costs a lookup.

    ``None`` when the lap predates the channel (v11) or never read a positive
    level. No judgement is applied here on purpose; see ``_fuel_used``.
    """
    fields = d.get("fields")
    rows = d.get("samples") or []
    if not fields or "fuel" not in fields or not rows:
        return None
    i = list(fields).index("fuel")
    try:
        vals = [float(r[i]) for r in rows if len(r) > i and r[i] not in (None, "")]
    except (TypeError, ValueError):
        return None
    vals = [v for v in vals if v > 0.0]
    return (vals[0], vals[-1]) if len(vals) >= 2 else None


def _fuel_used(d: dict) -> float | None:
    """Litres burned this lap, or ``None`` when that question has no answer.

    Mirrors :func:`accoach.coaching.fuel.burned` — including its refusals, so the
    session view and a lap opened by hand can't disagree about a lap's burn.
    """
    levels = _fuel_levels(d)
    if levels is None:
        return None
    used = levels[0] - levels[1]
    # Rose (a refuel or a pit stop) or absurd: not a burn rate.
    if used <= 0.0 or used > 20.0:
        return None
    return round(used, 2)


def _read_meta(path: Path) -> dict | None:
    """Read a lap file's metadata + sample count without building samples.

    Reads it the same way ``load_lap`` does, salvaging a file with trailing
    garbage after the gzip member. It used to use a plain ``gzip.open``, which
    meant a lap could be perfectly readable by every analysis path and yet
    invisible to the catalogue — so it appeared in no list, no session, and
    could never be elected as a reference, silently. Measured on a real lap:
    ``imola__mclaren-720s-gt3-evo__1m50s460``, 110 460 ms, on disk since 18 July
    and indexed by nothing.

    The import is local because ``storage`` imports this module.
    """
    from .storage import _read_gzip_salvaging

    try:
        d = json.loads(_read_gzip_salvaging(path).decode("utf-8"))
    except (OSError, ValueError, EOFError, zlib.error):
        return None
    levels = _fuel_levels(d)
    return {
        "car_model": str(d.get("car_model", "")),
        "track": str(d.get("track", "")),
        "session": int(d.get("session", -1)),
        "lap_time_ms": int(d.get("lap_time_ms", 0)),
        "valid": 1 if d.get("valid") else 0,
        "clean": _clean_to_int(d.get("clean"), int(d.get("schema", 1)),
                               str(d.get("tyre_compound", "") or ""),
                               str(d.get("recorded_utc", "") or "")),
        "air_temp": float(d.get("air_temp", 0.0) or 0.0),
        "road_temp": float(d.get("road_temp", 0.0) or 0.0),
        "grip": float(d.get("grip", 0.0) or 0.0),
        "tyre_compound": str(d.get("tyre_compound", "")),
        "source": str(d.get("source") or "own"),
        "recorded_utc": str(d.get("recorded_utc", "")),
        "sample_count": len(d.get("samples", [])),
        "schema_version": int(d.get("schema", 1)),
        "fuel_used": _fuel_used(d),
        "fuel_start": levels[0] if levels else None,
        "fuel_end": levels[1] if levels else None,
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
        try:
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            # WAL allows one writer at a time; the feed thread (save_lap→upsert) and
            # a reader thread (find_reference→sync) can collide. Wait instead of
            # failing immediately with "database is locked".
            self._conn.execute("PRAGMA busy_timeout=3000")
            # Migrate BEFORE creating the schema: a stale/legacy lap table must be
            # dropped first, otherwise the indexes in _SCHEMA fail referencing
            # columns the old table lacks (e.g. clean/source).
            self._migrate()
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except Exception:
            # Don't leak the connection (and its -wal/-shm locks on Windows) if
            # setup fails before __enter__ — the caller's `with` never runs __exit__.
            self._conn.close()
            raise

    def _migrate(self) -> None:
        """The catalog is a rebuildable cache: drop a stale/legacy lap table so the
        schema can be (re)created cleanly. Runs BEFORE _SCHEMA, so indexes that
        reference newer columns never hit an old table. ``sync`` re-indexes the
        files afterwards. Cheap and avoids fragile ALTER TABLE chains."""
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'db_version'"
        ).fetchone()
        version = int(row["value"]) if row else None
        # A legacy lap table that exists but is missing newer columns (no
        # db_version recorded) must be rebuilt too — otherwise every upsert fails
        # forever. A brand-new DB has no lap table yet (cols empty → not stale).
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(lap)")}
        stale = bool(cols) and not {"source", "clean"}.issubset(cols)
        if (version is not None and version < _DB_VERSION) or stale:
            self._conn.execute("DROP TABLE IF EXISTS lap")
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
                  tyre_compound, source, recorded_utc, sample_count, schema_version,
                  fuel_used, fuel_start, fuel_end)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET
                  car_key=excluded.car_key, track_key=excluded.track_key,
                  car_model=excluded.car_model, track=excluded.track,
                  session=excluded.session, lap_time_ms=excluded.lap_time_ms,
                  valid=excluded.valid, clean=excluded.clean,
                  air_temp=excluded.air_temp, road_temp=excluded.road_temp,
                  grip=excluded.grip, tyre_compound=excluded.tyre_compound,
                  source=excluded.source, recorded_utc=excluded.recorded_utc,
                  sample_count=excluded.sample_count,
                  schema_version=excluded.schema_version,
                  fuel_used=excluded.fuel_used,
                  fuel_start=excluded.fuel_start, fuel_end=excluded.fuel_end""",
            (
                str(path), self._slug(meta["car_model"]),
                self._slug(meta["track"]), meta["car_model"], meta["track"],
                meta["session"], meta["lap_time_ms"], meta["valid"],
                meta.get("clean", -1), meta.get("air_temp", 0.0),
                meta.get("road_temp", 0.0), meta.get("grip", 0.0),
                meta.get("tyre_compound", ""), meta.get("source", "own"),
                meta["recorded_utc"], meta["sample_count"], meta["schema_version"],
                meta.get("fuel_used"), meta.get("fuel_start"), meta.get("fuel_end"),
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

    def best_reference_path(self, car_model: str, track: str,
                            road_temp: float | None = None,
                            grip: float | None = None,
                            compound: str | None = None) -> str | None:
        """Path of the best *trustworthy* reference lap for this car+track.

        Excludes dirty laps (clean = 0) entirely, and prefers a confirmed-clean
        lap (clean = 1) over an unknown/legacy one (clean = -1); ties break on
        lap time. Returns ``None`` if there is no usable lap — the caller then
        honestly reports "no reference" instead of coaching against a cut lap.

        With ``road_temp``, a lap driven in comparable track conditions wins over
        a faster one driven in different ones. Braking points move 10-20 m
        between a cold track and a hot one, on the same car — a driver's own
        published comparison, and the reason a personal best set on a rubbered-in
        evening track is the wrong target for a cold morning session: every
        tenth in the debrief is then weather, not driving.

        ``compound`` is compared, never interpreted. On ACC it is canonical
        ("dry_compound" / "wet_compound"); on AC it is whatever string the mod
        chose ("Soft (S)", "Semislicks (SM)"), which is useless for deciding
        *what* the tyre is and perfectly good for deciding whether two laps were
        driven on the *same* one — which is the only question asked here. A
        different tyre is a different car, so this is the criterion held onto
        longest.

        ``grip`` is the sim's 0..1 track grip. Measured caveat: **ACC leaves it
        at 0 by design** (it reports condition through ``trackGripStatus``, a
        tail the reader doesn't declare yet), so on ACC this argument is inert
        and the election falls back to the criteria below it. Its band is a first
        guess — unlike the temperature one, no published comparison stands behind
        it, and the archive it was written against holds a single value.

        Deliberately a preference and not a filter. If nothing matches the
        conditions we return the plain best rather than "no reference": a
        slightly wrong benchmark still beats silence, and the conditions of the
        elected lap are shown to the driver anyway.

        With several conditions, they are relaxed one at a time, **least
        evidenced first**: grip (no measured spread behind its band), then track
        temperature (10-20 m of braking point, a published comparison), and the
        tyre last of all.
        """
        base = """SELECT path FROM lap
                  WHERE car_key = ? AND track_key = ? AND valid = 1
                        AND lap_time_ms > 0 AND clean <> 0"""
        order = " ORDER BY (clean = 1) DESC, lap_time_ms ASC LIMIT 1"
        keys = (self._slug(car_model), self._slug(track))

        # Only conditions we actually know about. A zero or an empty string is
        # "never recorded" — most archives predate these fields — and unknown
        # conditions can't be called similar, on either side of the comparison.
        known: dict[str, tuple[str, tuple]] = {}
        if compound:
            known["compound"] = (" AND tyre_compound = ?", (str(compound),))
        if road_temp is not None and road_temp > 0:
            known["temp"] = (" AND road_temp > 0 AND ABS(road_temp - ?) <= ?",
                             (float(road_temp), _TEMP_BAND_C))
        if grip is not None and grip > 0:
            known["grip"] = (" AND grip > 0 AND ABS(grip - ?) <= ?",
                             (float(grip), _GRIP_BAND))

        tried: set[tuple[str, ...]] = set()
        for wanted in (("compound", "temp", "grip"), ("compound", "temp"),
                       ("compound",), ("temp",), ()):
            use = tuple(c for c in wanted if c in known)
            if use in tried:
                continue                     # same query as a stricter attempt
            tried.add(use)
            row = self._conn.execute(
                base + "".join(known[c][0] for c in use) + order,
                (*keys, *(p for c in use for p in known[c][1])),
            ).fetchone()
            if row:
                return row["path"]
        return None

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
            """SELECT path, lap_time_ms, valid, clean, source, recorded_utc,
                      sample_count, air_temp, road_temp, grip, tyre_compound,
                      fuel_used, fuel_start, fuel_end
               FROM lap WHERE car_key = ? AND track_key = ?
               ORDER BY recorded_utc DESC""",
            (self._slug(car_model), self._slug(track)),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM lap").fetchone()["n"]

    # --- Focus coach memory (per car+track) -------------------------------

    def load_focus_state(self, car_model: str, track: str) -> tuple[set[int], set[int]]:
        """(mastered, parked) corner indices for this car+track; empty if none."""
        row = self._conn.execute(
            "SELECT mastered, parked FROM focus_state WHERE car_key=? AND track_key=?",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        if row is None:
            return set(), set()
        return _parse_indices(row["mastered"]), _parse_indices(row["parked"])

    def save_focus_state(self, car_model: str, track: str,
                         mastered: set[int], parked: set[int]) -> None:
        self._conn.execute(
            """INSERT INTO focus_state(car_key, track_key, mastered, parked)
               VALUES(?,?,?,?)
               ON CONFLICT(car_key, track_key)
               DO UPDATE SET mastered=excluded.mastered, parked=excluded.parked""",
            (self._slug(car_model), self._slug(track),
             _join_indices(mastered), _join_indices(parked)),
        )
        self._conn.commit()

    # --- Race engineer memory (per car+track) -----------------------------

    def load_engineer_state(self, car_model: str, track: str) -> dict | None:
        """What the engineer had already tried on this car+track, or None.

        None for "no memory", including when the stored JSON is unreadable: a
        broken row must cost the driver nothing more than a fresh start.
        """
        row = self._conn.execute(
            "SELECT state_json FROM engineer_state WHERE car_key=? AND track_key=?",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        if row is None:
            return None
        try:
            state = json.loads(row["state_json"])
        except (ValueError, TypeError):
            return None
        return state if isinstance(state, dict) else None

    def save_engineer_state(self, car_model: str, track: str, state: dict) -> None:
        self._conn.execute(
            """INSERT INTO engineer_state(car_key, track_key, state_json)
               VALUES(?,?,?)
               ON CONFLICT(car_key, track_key)
               DO UPDATE SET state_json=excluded.state_json""",
            (self._slug(car_model), self._slug(track),
             json.dumps(state, ensure_ascii=False)),
        )
        self._conn.commit()

    # --- Learned pit entry (per track) ------------------------------------

    def load_pit_entry(self, track: str) -> list[float]:
        """The measured pit-entry positions for this track, oldest first.

        A list and not an average on purpose: the caller takes the median, and a
        median needs the samples. Anything unparseable is dropped rather than
        raising — this is a convenience memory, and a corrupt row must cost at
        most one silent pit call, never a session.
        """
        row = self._conn.execute(
            "SELECT samples FROM pit_entry WHERE track_key=?", (self._slug(track),)
        ).fetchone()
        if row is None:
            return []
        out: list[float] = []
        for part in (row["samples"] or "").split(","):
            try:
                v = float(part)
            except ValueError:
                continue
            if 0.0 < v < 1.0:
                out.append(v)
        return out

    def save_pit_entry(self, track: str, samples: list[float]) -> None:
        self._conn.execute(
            """INSERT INTO pit_entry(track_key, samples) VALUES(?,?)
               ON CONFLICT(track_key) DO UPDATE SET samples=excluded.samples""",
            (self._slug(track), ",".join(f"{v:.5f}" for v in samples)),
        )
        self._conn.commit()

    # --- the corner map learned from the driver's laps --------------------

    def load_corner_map(self, car_model: str, track: str):
        """The learned corner map for this car+track, empty when never built."""
        from ..cornermap import CornerMap, deserialize

        row = self._conn.execute(
            "SELECT corners, laps FROM corner_map WHERE car_key=? AND track_key=?",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        if row is None:
            return CornerMap([], 0)
        return deserialize(row["corners"], int(row["laps"] or 0))

    def save_corner_map(self, car_model: str, track: str, cmap) -> None:
        from ..cornermap import serialize

        self._conn.execute(
            """INSERT INTO corner_map(car_key, track_key, corners, laps)
               VALUES(?,?,?,?)
               ON CONFLICT(car_key, track_key) DO UPDATE SET
                  corners=excluded.corners, laps=excluded.laps""",
            (self._slug(car_model), self._slug(track), serialize(cmap), cmap.laps),
        )
        self._conn.commit()

    def load_plan(self, car_model: str, track: str) -> dict | None:
        """The accepted training plan for this car+track, or None.

        Returns the stored dict as-is (``coaching.plan.TrainingPlan.from_dict``
        turns it back into objects): the catalog stores plans, it doesn't have
        opinions about what a goal is.
        """
        row = self._conn.execute(
            "SELECT created_utc, goals_json FROM plan WHERE car_key=? AND track_key=?",
            (self._slug(car_model), self._slug(track)),
        ).fetchone()
        if row is None:
            return None
        import json

        try:
            goals = json.loads(row["goals_json"])
        except ValueError:
            return None
        return {"car": car_model, "track": track,
                "created_utc": row["created_utc"], "goals": goals}

    def save_plan(self, car_model: str, track: str, created_utc: str,
                  goals: list[dict]) -> None:
        """Accept a plan for this car+track, replacing any previous one."""
        import json

        self._conn.execute(
            """INSERT INTO plan(car_key, track_key, created_utc, goals_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(car_key, track_key) DO UPDATE SET
                 created_utc=excluded.created_utc, goals_json=excluded.goals_json""",
            (self._slug(car_model), self._slug(track), created_utc,
             json.dumps(goals, ensure_ascii=False)),
        )
        self._conn.commit()

    def clear_plan(self, car_model: str, track: str) -> None:
        self._conn.execute("DELETE FROM plan WHERE car_key=? AND track_key=?",
                           (self._slug(car_model), self._slug(track)))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "LapCatalog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
