"""Database SQLite delle fonti pubbliche. Il percorso lo passa sempre chi chiama."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

TABLES = ("sources", "texts", "results", "facts", "rejects", "spend", "collect_runs")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
    id INTEGER PRIMARY KEY,
    platform TEXT CHECK (platform IN ('youtube','reddit')),
    url TEXT UNIQUE,
    author TEXT, title TEXT, published TEXT, game TEXT, track TEXT, meta_json TEXT
);
CREATE TABLE IF NOT EXISTS texts(
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL,
    source_id INTEGER,
    kind TEXT CHECK (kind IN ('transcript','post','comment')),
    author TEXT, body TEXT, segments_json TEXT, collected_at TEXT,
    UNIQUE(sha256, source_id, author)
);
CREATE TABLE IF NOT EXISTS results(
    id INTEGER PRIMARY KEY,
    sha256 TEXT,
    kind TEXT CHECK (kind IN ('extract','rate','factcheck')),
    prompt_version TEXT, model TEXT, payload_json TEXT, frozen_at TEXT,
    UNIQUE(sha256, kind, prompt_version, model)
);
CREATE TABLE IF NOT EXISTS facts(
    id INTEGER PRIMARY KEY,
    result_id INTEGER, track TEXT, corner TEXT, type TEXT, value TEXT, quote TEXT,
    offset INTEGER, start_s REAL, author TEXT, source_id INTEGER
);
CREATE TABLE IF NOT EXISTS rejects(
    id INTEGER PRIMARY KEY,
    result_id INTEGER, reason TEXT, item_json TEXT
);
CREATE TABLE IF NOT EXISTS spend(
    track TEXT PRIMARY KEY,
    baseline_usd REAL, last_usd REAL, cap_usd REAL
);
CREATE TABLE IF NOT EXISTS collect_runs(
    track TEXT, entry_key TEXT, finished_at TEXT, items INTEGER, spent_usd REAL,
    PRIMARY KEY(track, entry_key)
);
"""


def open_db(path: Path) -> sqlite3.Connection:
    """Apre (e crea se manca) il database; `user_version` = 1."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def add_text(conn: sqlite3.Connection, source_id: int, kind: str, author: str,
             body: str, segments: list | None = None) -> tuple[str, bool]:
    """Salva un testo; `(sha256, nuovo)`. Stesso testo, fonte e autore non si duplica."""
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    seg = json.dumps(segments, ensure_ascii=False) if segments is not None else None
    cur = conn.execute(
        "INSERT OR IGNORE INTO texts(sha256, source_id, kind, author, body, segments_json, collected_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (sha, source_id, kind, author, body, seg,
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    return sha, cur.rowcount == 1


def count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
