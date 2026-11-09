"""Database SQLite delle fonti pubbliche. Il percorso lo passa sempre chi chiama."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2

TABLES = ("sources", "texts", "results", "facts", "rejects", "spend", "collect_runs", "jobs",
          "raw_items")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
    id INTEGER PRIMARY KEY,
    platform TEXT CHECK (platform IN ('youtube','reddit')),
    url TEXT UNIQUE,
    author TEXT, title TEXT, published TEXT, game TEXT, track TEXT, meta_json TEXT,
    car_class TEXT
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
    prompt_version TEXT, model TEXT, payload_json TEXT, frozen_at TEXT, track TEXT,
    UNIQUE(sha256, kind, prompt_version, model, track)
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
    baseline_usd REAL, last_usd REAL, cap_usd REAL, runs_usd REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS collect_runs(
    track TEXT, entry_key TEXT, finished_at TEXT, items INTEGER, spent_usd REAL, run_id TEXT,
    PRIMARY KEY(track, entry_key)
);
CREATE TABLE IF NOT EXISTS raw_items(
    id INTEGER PRIMARY KEY,
    track TEXT, entry_key TEXT, item_json TEXT, fetched_at TEXT,
    UNIQUE(track, entry_key, item_json)
);
CREATE TABLE IF NOT EXISTS jobs(
    kind TEXT, key TEXT, track TEXT, prompt_version TEXT, payload_json TEXT, created_at TEXT,
    PRIMARY KEY(kind, key, track, prompt_version)
);
"""


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    """Aggiunge la colonna a un database creato prima di lei; True se l'ha aggiunta."""
    if column in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def open_db(path: Path) -> sqlite3.Connection:
    """Apre (e crea se manca) il database, e porta uno vecchio allo schema di adesso."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    _add_column(conn, "results", "track", "TEXT")
    _add_column(conn, "collect_runs", "run_id", "TEXT")
    _add_column(conn, "spend", "runs_usd", "REAL DEFAULT 0")
    if _add_column(conn, "sources", "car_class", "TEXT"):
        # Le fonti già raccolte prendono la classe dal titolo, la sola cosa salvata.
        from tools.fonti.collect import car_class_of
        for sid, title in conn.execute("SELECT id, title FROM sources").fetchall():
            conn.execute("UPDATE sources SET car_class=? WHERE id=?", (car_class_of(title, "", ""), sid))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


# --- regole condivise ------------------------------------------------------------

def version_order(v: str):
    """L'ordine delle prompt_version: i numeri come numeri, poi il resto in ordine di testo."""
    return (0, int(v), "") if v.isdigit() else (1, 0, v)


def author_id(platform, author) -> str:
    """Un autore si identifica con `platform:author` in minuscolo."""
    return f"{platform or ''}:{author or ''}".lower()


def newest_versions(conn: sqlite3.Connection, kind: str, track: str) -> dict[str, str]:
    """Per ogni chiave di quel `kind`, la versione più alta proposta in `jobs`."""
    out: dict[str, str] = {}
    for key, version in conn.execute(
            "SELECT key, prompt_version FROM jobs WHERE kind=? AND track=?", (kind, track)):
        if key not in out or version_order(version) > version_order(out[key]):
            out[key] = version
    return out


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
