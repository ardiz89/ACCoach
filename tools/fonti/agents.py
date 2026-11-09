"""Il lavoro degli agenti: la coda dei lavori, le istruzioni, l'ingest congelato.

Gli agenti (subagenti Claude) leggono un `*.job.json` e rispondono con un JSON dello
schema del loro `kind`. Qui la risposta si accetta intera o si rifiuta intera; poi ogni
fatto passa per il verificatore. Un risultato si congela per (sha256, kind,
prompt_version, model): un secondo ingest della stessa chiave si rifiuta.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tools.fonti import verify, vocab

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES = {"extract": "estrai.md", "rate": "valuta.md", "factcheck": "factcheck.md"}
KINDS = tuple(PROMPT_FILES)
ROLES = ("pilota", "coach", "anonimo")
VERDICTS = ("confermato", "respinto")

_KEYS = {
    "extract": {"sha256", "kind", "facts"},
    "rate": {"sha256", "kind", "speaker", "lap_time", "car", "reasons"},
    "factcheck": {"fact_key", "kind", "verdict", "reason", "quote", "offset"},
}
_FACT_KEYS = {"corner", "type", "value", "quote", "offset"}
_SPEAKER_KEYS = {"name", "role"}
_REASON_KEYS = {"claim", "quote", "offset"}
_VERSION = re.compile(r"^prompt_version:\s*(\S+)\s*$")


class AnswerRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def prompt_version(kind: str) -> str:
    """La versione scritta nella prima riga del prompt di quel `kind`."""
    path = PROMPTS_DIR / PROMPT_FILES[kind]
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.exists() else ""
    m = _VERSION.match(first.lstrip("﻿"))
    if not m:
        raise ValueError(f"{path.name}: la prima riga deve essere «prompt_version: N»")
    return m.group(1)


# --- la coda ------------------------------------------------------------------

def _acc_rows(conn: sqlite3.Connection, track: str | None) -> list[tuple]:
    sql = ("SELECT t.sha256, t.body, t.segments_json, t.kind, t.author, s.platform, s.url,"
           " s.title, s.published FROM texts t JOIN sources s ON s.id = t.source_id"
           " WHERE s.game = 'acc'")
    args: tuple = ()
    if track is not None:
        sql += " AND s.track = ?"
        args = (track,)
    return conn.execute(sql + " ORDER BY t.sha256, s.url, t.author, t.id", args).fetchall()


def _texts_by_sha(rows: list[tuple]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sha, body, seg, kind, author, platform, url, title, published in rows:
        t = out.setdefault(sha, {"body": body, "segments": None, "meta": []})
        if t["segments"] is None and seg:
            t["segments"] = json.loads(seg)
        t["meta"].append({"author": author, "platform": platform, "published": published,
                          "text_kind": kind, "title": title, "url": url})
    return out


def _frozen(conn, key: str, kind: str, version: str) -> bool:
    return conn.execute("SELECT 1 FROM results WHERE sha256=? AND kind=? AND prompt_version=?",
                        (key, kind, version)).fetchone() is not None


def _mentions(track: str, corner: str, body: str) -> bool:
    text = vocab.fold(body)
    return any(vocab.alias_regex(a).search(text) for a in vocab.CORNERS.get(track, {}).get(corner, []))


def pending(conn: sqlite3.Connection, kind: str, track: str, out_dir: Path) -> list[Path]:
    """Scrive un `<kind>-<sha256[:12]>.job.json` per ogni lavoro ancora da fare."""
    if kind not in KINDS:
        raise ValueError(f"kind sconosciuto: {kind}")
    version = prompt_version(kind)
    corners = list(vocab.CORNERS.get(track, {}))
    texts = _texts_by_sha(_acc_rows(conn, track))
    jobs: list[tuple[str, dict]] = []
    if kind in ("extract", "rate"):
        for sha in sorted(texts):
            if _frozen(conn, sha, kind, version):
                continue
            t = texts[sha]
            jobs.append((sha, {"kind": kind, "sha256": sha, "track": track,
                               "prompt_version": version, "body": t["body"],
                               "segments": t["segments"], "meta": t["meta"],
                               "corners": corners}))
    else:
        try:
            from tools.fonti import consensus
        except ImportError as e:
            raise RuntimeError("pending factcheck: serve tools/fonti/consensus.py "
                               "(consensus.build), che non c'è ancora") from e
        for entry in consensus.build(conn, track):
            key = entry.get("fact_key")
            if entry.get("state") != "verificato" or not key or _frozen(conn, key, kind, version):
                continue
            corner = entry["corner"]
            others = [{"sha256": sha, "body": t["body"], "segments": t["segments"], "meta": t["meta"]}
                      for sha, t in sorted(texts.items()) if _mentions(track, corner, t["body"])]
            jobs.append((key, {"kind": kind, "sha256": key, "track": track,
                               "prompt_version": version, "body": None, "segments": None,
                               "meta": [], "corners": [corner], "fact": entry,
                               "texts": others}))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for key, job in sorted(jobs, key=lambda x: x[0]):
        p = out_dir / f"{kind}-{key[:12]}.job.json"
        p.write_text(_dumps(job), encoding="utf-8", newline="\n")
        paths.append(p)
    return paths


# --- lo schema ----------------------------------------------------------------

def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _exact(obj, keys: set, where: str) -> None:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise AnswerRejected(f"schema_errato:{where}")


def _str(x, where: str, empty_ok: bool = True) -> None:
    if not isinstance(x, str) or (not empty_ok and not x.strip()):
        raise AnswerRejected(f"schema_errato:{where}")


def _validate(d) -> str:
    if not isinstance(d, dict) or d.get("kind") not in KINDS:
        raise AnswerRejected("schema_errato:kind")
    kind = d["kind"]
    _exact(d, _KEYS[kind], kind)
    if kind == "extract":
        _str(d["sha256"], "sha256", empty_ok=False)
        if not isinstance(d["facts"], list):
            raise AnswerRejected("schema_errato:facts")
        for f in d["facts"]:
            _exact(f, _FACT_KEYS, "facts[]")
            for k in ("corner", "type", "value", "quote"):
                _str(f[k], f"facts[].{k}")
            if not _is_int(f["offset"]):
                raise AnswerRejected("schema_errato:facts[].offset")
    elif kind == "rate":
        _str(d["sha256"], "sha256", empty_ok=False)
        _exact(d["speaker"], _SPEAKER_KEYS, "speaker")
        _str(d["speaker"]["name"], "speaker.name")
        if d["speaker"]["role"] not in ROLES:
            raise AnswerRejected("schema_errato:speaker.role")
        for k in ("lap_time", "car"):
            if d[k] is not None:
                _str(d[k], k)
        if not isinstance(d["reasons"], list):
            raise AnswerRejected("schema_errato:reasons")
        for r in d["reasons"]:
            _exact(r, _REASON_KEYS, "reasons[]")
            _str(r["claim"], "reasons[].claim")
            _str(r["quote"], "reasons[].quote")
            if not _is_int(r["offset"]):
                raise AnswerRejected("schema_errato:reasons[].offset")
    else:
        _str(d["fact_key"], "fact_key", empty_ok=False)
        if d["verdict"] not in VERDICTS:
            raise AnswerRejected("schema_errato:verdict")
        _str(d["reason"], "reason")
        _str(d["quote"], "quote")
        if not _is_int(d["offset"]):
            raise AnswerRejected("schema_errato:offset")
    return kind


# --- l'ingest -----------------------------------------------------------------

def _start_s(body: str, segments, offset: int) -> float | None:
    """L'inizio del sottotitolo in cui cade l'offset; None senza segmenti che tornano."""
    if not segments:
        return None
    cursor, best = 0, None
    for seg in segments:
        text = seg.get("text") if isinstance(seg, dict) else None
        at = body.find(text, cursor) if isinstance(text, str) else -1
        if at < 0:
            return None
        if at <= offset:
            best = seg.get("start_s")
        cursor = at + len(text)
    return best


def ingest(conn: sqlite3.Connection, answer_path: Path, model: str) -> dict:
    """Congela una risposta e ne verifica ogni fatto; `{"facts": n, "rejects": m}`."""
    if not isinstance(model, str) or not model.strip():
        raise AnswerRejected("modello_mancante")
    try:
        d = json.loads(Path(answer_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise AnswerRejected("json_malformato") from None
    kind = _validate(d)
    key = d["fact_key"] if kind == "factcheck" else d["sha256"]
    version = prompt_version(kind)
    if conn.execute("SELECT 1 FROM results WHERE sha256=? AND kind=? AND prompt_version=? AND model=?",
                    (key, kind, version, model)).fetchone():
        raise AnswerRejected("gia_congelato")

    if kind == "factcheck":
        rows, bodies = [], sorted({r[1] for r in _acc_rows(conn, None)})
    else:
        rows = conn.execute(
            "SELECT t.body, t.segments_json, t.author, t.source_id, s.track FROM texts t"
            " LEFT JOIN sources s ON s.id = t.source_id WHERE t.sha256 = ? ORDER BY t.id",
            (key,)).fetchall()
        if not rows:
            raise AnswerRejected("testo_ignoto")
        bodies = [rows[0][0]]

    facts: list[tuple] = []
    rejects: list[tuple[str, dict]] = []
    if kind == "extract":
        body = rows[0][0]
        segments = next((json.loads(r[1]) for r in rows if r[1]), None)
        for f in d["facts"]:
            reasons = {}
            for _b, _s, author, source_id, track in rows:
                if track not in reasons:
                    reasons[track] = verify.check_fact(track, f, body, segments)
            bad = next((r for r in reasons.values() if r), None)
            if bad:
                rejects.append((bad, f))
                continue
            start_s = _start_s(body, segments, f["offset"])
            for _b, _s, author, source_id, track in rows:
                facts.append((track, f["corner"], f["type"], f["value"], f["quote"], f["offset"],
                              start_s, author, source_id))
    else:
        items = d["reasons"] if kind == "rate" else [d]
        for it in items:
            bad = None
            for b in bodies:
                bad = verify.check_quote(it["quote"], b)
                if bad is None:
                    break
            if bad or not bodies:
                rejects.append((bad or "citazione_assente", it))

    with conn:
        cur = conn.execute(
            "INSERT INTO results(sha256, kind, prompt_version, model, payload_json, frozen_at)"
            " VALUES (?,?,?,?,?,?)",
            (key, kind, version, model, json.dumps(d, sort_keys=True, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        rid = cur.lastrowid
        conn.executemany(
            "INSERT INTO facts(result_id, track, corner, type, value, quote, offset, start_s,"
            " author, source_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(rid, *f) for f in facts])
        conn.executemany(
            "INSERT INTO rejects(result_id, reason, item_json) VALUES (?,?,?)",
            [(rid, reason, json.dumps(it, sort_keys=True, ensure_ascii=False))
             for reason, it in rejects])
    return {"facts": len(facts), "rejects": len(rejects)}
