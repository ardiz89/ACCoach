"""LapCatalog: the SQLite index over lap files."""
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import _catalog_path, list_lap_files, save_lap

import synth


def _seed(tmp_path):
    """Two valid laps (fast + slow) and one invalid one on disk.

    ``save_lap`` best-effort indexes into the catalog as a side effect; drop that
    db so each test rebuilds the index from the files (the catalog is a cache).
    """
    # Distinct timestamps so files don't collide on name (fast & invalid share a
    # lap time of 100000 and would otherwise overwrite each other).
    laps = [
        (synth.build_lap(n=30), "2026-06-20T18:00:00+00:00"),                # fast
        (synth.build_lap(slow_corner=0, amt=30, n=30), "2026-06-20T18:00:01+00:00"),
        (synth.build_lap(n=30, valid=False), "2026-06-20T18:00:02+00:00"),   # invalid
    ]
    for lap, utc in laps:
        lap.recorded_utc = utc
        save_lap(lap, tmp_path)
    db = _catalog_path(tmp_path)
    if db.exists():
        db.unlink()


def test_sync_indexes_all_files(tmp_path):
    _seed(tmp_path)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        added = cat.sync(list_lap_files(tmp_path))
        assert added == 3
        assert cat.count() == 3
        # Re-syncing the same files adds nothing.
        assert cat.sync(list_lap_files(tmp_path)) == 0


def test_fastest_valid_path_skips_invalid_and_slow(tmp_path):
    _seed(tmp_path)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        path = cat.fastest_valid_path("ferrari_488_gt3", "monza")
        assert path is not None
        # The winner is the 100000 ms lap (token "1m40s000" in the filename).
        assert "1m40s000" in path


def test_fastest_valid_none_for_unknown_combo(tmp_path):
    _seed(tmp_path)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        assert cat.fastest_valid_path("nope", "nowhere") is None


def test_laps_for_returns_all_including_invalid(tmp_path):
    _seed(tmp_path)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        rows = cat.laps_for("ferrari_488_gt3", "monza")
        assert len(rows) == 3
        assert all("path" in r and "lap_time_ms" in r for r in rows)


def test_sync_drops_files_removed_from_disk(tmp_path):
    _seed(tmp_path)
    db = _catalog_path(tmp_path)
    with LapCatalog(db) as cat:
        cat.sync(list_lap_files(tmp_path))
        assert cat.count() == 3
    # Delete one file, re-sync: catalog drops the stale row.
    files = list_lap_files(tmp_path)
    files[0].unlink()
    with LapCatalog(db) as cat:
        cat.sync(list_lap_files(tmp_path))
        assert cat.count() == 2


def test_best_reference_excludes_dirty_and_prefers_clean(tmp_path):
    dirty = synth.build_lap(n=30, clean=False)                      # fast, dirty
    dirty.recorded_utc = "2026-06-20T18:00:00+00:00"
    clean = synth.build_lap(slow_corner=0, amt=30, n=30, clean=True)  # slower, clean
    clean.recorded_utc = "2026-06-20T18:00:01+00:00"
    save_lap(dirty, tmp_path)
    cpath = save_lap(clean, tmp_path)
    _catalog_path(tmp_path).unlink(missing_ok=True)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        best = cat.best_reference_path("ferrari_488_gt3", "monza")
        # The clean lap wins even though it's slower; the fast dirty one is out.
        assert best == str(cpath)


def test_best_reference_prefers_clean_over_unknown(tmp_path):
    unknown = synth.build_lap(n=30)                                 # fast, clean=None
    unknown.recorded_utc = "2026-06-20T18:00:00+00:00"
    clean = synth.build_lap(slow_corner=0, amt=30, n=30, clean=True)  # slower, clean
    clean.recorded_utc = "2026-06-20T18:00:01+00:00"
    save_lap(unknown, tmp_path)
    cpath = save_lap(clean, tmp_path)
    _catalog_path(tmp_path).unlink(missing_ok=True)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        assert cat.best_reference_path("ferrari_488_gt3", "monza") == str(cpath)


def test_best_reference_none_when_all_dirty(tmp_path):
    save_lap(synth.build_lap(n=30, clean=False), tmp_path)
    _catalog_path(tmp_path).unlink(missing_ok=True)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        assert cat.best_reference_path("ferrari_488_gt3", "monza") is None


def test_migration_from_old_version_rebuilds(tmp_path):
    import sqlite3
    db = _catalog_path(tmp_path)
    with LapCatalog(db):
        pass
    # Stamp an older db_version; reopening must migrate (drop+rebuild) to current.
    con = sqlite3.connect(str(db))
    con.execute("UPDATE meta SET value='1' WHERE key='db_version'")
    con.commit()
    con.close()
    with LapCatalog(db) as cat:
        from accoach.recording.catalog import _DB_VERSION
        row = cat._conn.execute(
            "SELECT value FROM meta WHERE key='db_version'"
        ).fetchone()
        assert row["value"] == str(_DB_VERSION)


def test_fastest_pro_path_finds_imported_benchmark(tmp_path):
    from dataclasses import replace
    # Your own laps, plus one imported PRO lap (slower here, but a PRO benchmark).
    save_lap(synth.build_lap(n=30), tmp_path)
    pro = replace(synth.build_lap(slow_corner=0, amt=10, n=30), source="pro")
    pro.recorded_utc = "2026-06-21T00:00:00+00:00"
    save_lap(pro, tmp_path)
    _catalog_path(tmp_path).unlink(missing_ok=True)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        path = cat.fastest_pro_path("ferrari_488_gt3", "monza")
        assert path is not None
        from accoach.recording.storage import load_lap
        assert load_lap(path).source == "pro"               # the PRO one, not yours


def test_no_pro_lap_returns_none(tmp_path):
    save_lap(synth.build_lap(n=30), tmp_path)               # only your own
    _catalog_path(tmp_path).unlink(missing_ok=True)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        assert cat.fastest_pro_path("ferrari_488_gt3", "monza") is None


def test_busy_timeout_is_set(tmp_path):
    # C3: a busy_timeout must be set so two writers (feed + reader) wait instead of
    # failing immediately with "database is locked".
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        bt = cat._conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert bt >= 1000


def test_migration_rebuilds_unversioned_legacy_table(tmp_path):
    # C4: a legacy catalog with a lap table but no db_version must be rebuilt, or
    # every upsert fails forever on the missing newer columns (source/clean).
    import sqlite3
    save_lap(synth.build_lap(n=10), tmp_path)            # a real lap to index
    db = _catalog_path(tmp_path)
    for suffix in ("", "-wal", "-shm"):
        p = db.parent / (db.name + suffix)
        p.unlink(missing_ok=True)
    con = sqlite3.connect(str(db))                       # forge a legacy catalog
    con.execute(
        "CREATE TABLE lap (lap_id INTEGER PRIMARY KEY, path TEXT UNIQUE, "
        "car_key TEXT, track_key TEXT, car_model TEXT, track TEXT, session INTEGER, "
        "lap_time_ms INTEGER, valid INTEGER, recorded_utc TEXT, "
        "sample_count INTEGER, schema_version INTEGER)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()
    con.close()
    with LapCatalog(db) as cat:
        cols = {r["name"] for r in cat._conn.execute("PRAGMA table_info(lap)")}
        assert {"source", "clean"}.issubset(cols)        # table was rebuilt
        cat.sync(list_lap_files(tmp_path))               # upsert now succeeds
        assert cat.fastest_valid_path("ferrari_488_gt3", "monza") is not None


def test_upsert_is_idempotent(tmp_path):
    save_lap(synth.build_lap(n=10), tmp_path)
    path = list_lap_files(tmp_path)[0]
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        assert cat.upsert(path) is True
        assert cat.upsert(path) is True       # ON CONFLICT update, no duplicate
        assert cat.count() == 1


def test_a_lap_with_trailing_garbage_is_still_indexed(tmp_path):
    """It used to be readable by every analysis path and invisible here.

    ``load_lap`` salvages a file with junk after the gzip member (it warns and
    reads the first one); the catalogue used a plain ``gzip.open`` and returned
    "unreadable", so the lap appeared in no list, no session, and could never be
    elected as a reference — with nothing said. Found on a real lap in
    ``~/Documents/ACCoach/laps``: a 1:50.460 at Imola, on disk since 18 July and
    indexed by nothing.
    """
    save_lap(synth.build_lap(n=10), tmp_path)
    path = list_lap_files(tmp_path)[0]
    with path.open("ab") as fh:
        fh.write(b"\x00" * 79)                # what the real file had after it

    from accoach.recording import load_lap
    assert load_lap(path).lap_time_ms > 0     # the analysis path was always fine
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        assert cat.upsert(path) is True
        assert cat.count() == 1


def test_a_file_that_is_not_a_lap_at_all_is_still_refused(tmp_path):
    """Salvaging trailing junk must not turn into accepting anything.

    Written under a name that was never indexed: overwriting a saved lap would
    leave the row ``save_lap`` already wrote, and the test would be measuring
    that instead of this.
    """
    junk = tmp_path / "junk.lap.json.gz"
    junk.write_bytes(b"not gzip, not json, not a lap")
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        assert cat.upsert(junk) is False
        assert cat.count() == 0
