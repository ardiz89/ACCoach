"""Il lavoro degli agenti: la coda dei lavori, le istruzioni, l'ingest congelato.

Gli agenti (subagenti Claude) leggono un `*.job.json` e rispondono con un JSON dello
schema del loro `kind`. La risposta si accetta intera o si rifiuta intera. Per
`extract` ogni fatto passa poi per il verificatore e quelli che non reggono finiscono
negli scarti; per `rate` e `factcheck` basta una citazione che non regge e la risposta
intera si rifiuta. Un risultato si congela per (sha256, kind, prompt_version, model):
un secondo ingest della stessa chiave si rifiuta.

Ogni lavoro proposto da `pending` si ricorda nella tabella `jobs`, per pista. La
risposta ripete `prompt_version` e `track` del lavoro; l'ingest accetta solo la
versione più alta proposta per (kind, key, track) e la congela con quella pista.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from tools.fonti import verify, vocab

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES = {"extract": "estrai.md", "rate": "valuta.md", "factcheck": "factcheck.md"}
KINDS = tuple(PROMPT_FILES)
ROLES = ("pilota", "coach", "anonimo")
VERDICTS = ("confermato", "respinto")
FIELDS = ("name", "role", "lap_time", "car")

_ECHO = {"prompt_version", "track"}  # ogni risposta ripete versione e pista del lavoro
_KEYS = {
    "extract": {"sha256", "kind", "facts"} | _ECHO,
    "rate": {"sha256", "kind", "speaker", "lap_time", "car", "reasons"} | _ECHO,
    "factcheck": {"fact_key", "kind", "verdict", "reason", "quote", "offset"} | _ECHO,
}
_FILLERS = {"the", "a", "an", "in", "at", "to", "into", "on", "of", "and", "il", "lo", "la", "i",
            "gli", "le", "un", "una", "di", "da", "al", "alla", "allo", "ai", "e"}
_FACT_KEYS = {"corner", "type", "value", "quote", "offset"}
_SPEAKER_KEYS = {"name", "role"}
_REASON_KEYS = {"field", "claim", "quote", "offset"}
_VERSION = re.compile(r"^prompt_version:\s*(\S+)\s*$")


class AnswerRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _atomic(conn: sqlite3.Connection):
    """Tutto o niente, senza toccare una transazione già aperta da chi chiama.

    Con un SAVEPOINT un errore annulla solo le nostre scritture. Se chi chiama non
    aveva una transazione aperta, il RELEASE finale salva; se l'aveva, resta sua.
    """
    conn.execute("SAVEPOINT fonti_agents")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK TO fonti_agents")
        conn.execute("RELEASE fonti_agents")
        raise
    conn.execute("RELEASE fonti_agents")


def prompt_version(kind: str) -> str:
    """La versione scritta nella prima riga del prompt di quel `kind`."""
    path = PROMPTS_DIR / PROMPT_FILES[kind]
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.exists() else ""
    m = _VERSION.match(first.lstrip("﻿"))
    if not m:
        raise ValueError(f"{path.name}: la prima riga deve essere «prompt_version: N»")
    return m.group(1)


def _version_order(v: str):
    return (0, int(v), "") if v.isdigit() else (1, 0, v)


# --- i testi ------------------------------------------------------------------

class _BadSegments(Exception):
    pass


def _segments(raw):
    if raw is None:
        return None
    try:
        segs = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise _BadSegments from None
    if not isinstance(segs, list):
        raise _BadSegments
    return segs


def _acc_rows(conn: sqlite3.Connection, track: str, sha: str | None = None) -> list[tuple]:
    """Le righe di `texts` di fonti ACC di quella pista, in ordine fisso."""
    sql = ("SELECT t.sha256, t.body, t.segments_json, t.kind, t.author, s.platform, s.url,"
           " s.title, s.published, t.source_id, s.author FROM texts t"
           " JOIN sources s ON s.id = t.source_id WHERE s.game = 'acc' AND s.track = ?")
    args: tuple = (track,)
    if sha is not None:
        sql += " AND t.sha256 = ?"
        args += (sha,)
    return conn.execute(sql + " ORDER BY t.sha256, s.url, t.author, t.id", args).fetchall()


def _texts_by_sha(rows: list[tuple]) -> dict[str, dict]:
    """Un testo per sha256. Un testo con segmenti illeggibili si salta."""
    out: dict[str, dict] = {}
    bad: set[str] = set()
    for sha, body, seg, kind, author, platform, url, title, published, *_ in rows:
        try:
            segs = _segments(seg)
        except _BadSegments:
            bad.add(sha)
            continue
        t = out.setdefault(sha, {"body": body, "segments": None, "meta": []})
        if t["segments"] is None and segs:
            t["segments"] = segs
        t["meta"].append({"author": author, "platform": platform, "published": published,
                          "text_kind": kind, "title": title, "url": url})
    return {k: v for k, v in out.items() if k not in bad}


def _frozen_any_model(conn, key: str, kind: str, version: str, track: str) -> bool:
    return conn.execute("SELECT 1 FROM results WHERE sha256=? AND kind=? AND prompt_version=?"
                        " AND track=?", (key, kind, version, track)).fetchone() is not None


def _own_shas(conn, track: str, entry: dict) -> list[str]:
    """Gli sha256 dei testi da cui viene il fatto: una verifica non si conferma su questi."""
    values = [v.get("value") for v in entry.get("values") or [] if isinstance(v, dict)]
    if not values:
        return []
    marks = ",".join("?" * len(values))
    rows = conn.execute(
        "SELECT DISTINCT r.sha256 FROM facts f JOIN results r ON r.id = f.result_id"
        f" WHERE f.track=? AND f.corner=? AND f.type=? AND f.value IN ({marks})",
        (track, entry.get("corner"), entry.get("type"), *values)).fetchall()
    return sorted(r[0] for r in rows)


def _mentions(track: str, corner: str, body: str) -> bool:
    text = vocab.fold(body)
    return any(vocab.alias_regex(a).search(text) for a in vocab.CORNERS.get(track, {}).get(corner, []))


# --- la coda ------------------------------------------------------------------

def pending(conn: sqlite3.Connection, kind: str, track: str, out_dir: Path) -> list[Path]:
    """Scrive un `<kind>-<key[:12]>.job.json` per ogni lavoro ancora da fare e lo ricorda in `jobs`."""
    if kind not in KINDS:
        raise ValueError(f"kind sconosciuto: {kind}")
    version = prompt_version(kind)
    corners = list(vocab.CORNERS.get(track, {}))
    texts = _texts_by_sha(_acc_rows(conn, track))
    jobs: list[tuple[str, dict]] = []
    if kind in ("extract", "rate"):
        for sha in sorted(texts):
            if _frozen_any_model(conn, sha, kind, version, track):
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
            if (entry.get("state") != "verificato" or not key
                    or _frozen_any_model(conn, key, kind, version, track)):
                continue
            corner = entry["corner"]
            others = [{"sha256": sha, "body": t["body"], "segments": t["segments"], "meta": t["meta"]}
                      for sha, t in sorted(texts.items()) if _mentions(track, corner, t["body"])]
            jobs.append((key, {"kind": kind, "sha256": key, "track": track,
                               "prompt_version": version, "body": None, "segments": None,
                               "meta": [], "corners": [corner], "fact": entry,
                               "fact_sha256s": _own_shas(conn, track, entry),
                               "texts": others}))
    jobs.sort(key=lambda x: x[0])
    with _atomic(conn):
        for key, job in jobs:
            conn.execute(
                "INSERT OR REPLACE INTO jobs(kind, key, track, prompt_version, payload_json, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (kind, key, track, version, json.dumps(job, sort_keys=True, ensure_ascii=False), _now()))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for key, job in jobs:
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
    _str(d["prompt_version"], "prompt_version", empty_ok=False)
    _str(d["track"], "track", empty_ok=False)
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
                _str(d[k], k, empty_ok=False)
        if not isinstance(d["reasons"], list):
            raise AnswerRejected("schema_errato:reasons")
        for r in d["reasons"]:
            _exact(r, _REASON_KEYS, "reasons[]")
            if r["field"] not in FIELDS:
                raise AnswerRejected("schema_errato:reasons[].field")
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

def _open_job(conn, kind: str, key: str, track: str, version: str, model: str) -> dict:
    """Il payload del lavoro aperto: la versione più alta proposta per (kind, key, track)."""
    rows = conn.execute("SELECT prompt_version, payload_json FROM jobs WHERE kind=? AND key=? AND track=?",
                        (kind, key, track)).fetchall()
    if not rows:
        raise AnswerRejected("lavoro_ignoto")
    newest, payload = max(rows, key=lambda r: _version_order(r[0]))
    if version != newest:
        raise AnswerRejected("versione_superata")
    if conn.execute("SELECT 1 FROM results WHERE sha256=? AND kind=? AND prompt_version=?"
                    " AND model=? AND track=?", (key, kind, version, model, track)).fetchone():
        raise AnswerRejected("gia_congelato")
    return json.loads(payload)


def _start_s(body: str, segments, at: int | None) -> float | None:
    """L'inizio del sottotitolo in cui cade il carattere `at`; None senza segmenti che tornano."""
    if not segments or at is None:
        return None
    cursor, best = 0, None
    for seg in segments:
        text = seg.get("text") if isinstance(seg, dict) else None
        found = body.find(text, cursor) if isinstance(text, str) else -1
        if found < 0:
            return None
        if found <= at:
            best = seg.get("start_s")
        cursor = found + len(text)
    return best


def _vocab_hits(text: str) -> str:
    """Il testo, normalizzato, con ogni parola del vocabolario dei fatti tolta."""
    t = vocab.fold(text)
    for term in sorted(vocab.VOCAB_TERMS, key=len, reverse=True):
        t = vocab.alias_regex(term).sub(" ", t)
    return t


def _is_vocab_name(name: str) -> bool:
    """Il nome è, o contiene, una curva o una parola del vocabolario."""
    return _vocab_hits(name) != vocab.fold(name)


def _is_vocab_only(car: str) -> bool:
    """L'auto è fatta solo di parole del vocabolario (e di riempitivi)."""
    rest = [w for w in re.findall(r"[\w']+", _vocab_hits(car)) if w not in _FILLERS]
    return not rest


def _proves_role(role: str, quote: str) -> bool:
    return (not vocab.negated(quote)
            and any(verify.contains(quote, cue) for cue in vocab.ROLE_CUES[role]))


def _check_rate(d: dict, body: str, authors: set[str]) -> None:
    """Ogni citazione regge e ogni affermazione non vuota ha la sua; altrimenti si rifiuta tutto.

    `authors` sono solo gli autori delle righe di quel testo (`texts.author`), mai
    l'autore della fonte: in un thread l'autore del post non è chi ha scritto il commento.
    """
    by_field: dict[str, list[str]] = {f: [] for f in FIELDS}
    for r in d["reasons"]:
        bad = verify.check_quote(r["quote"], body, r["offset"])
        if bad:
            raise AnswerRejected(bad)
        by_field[r["field"]].append(r["quote"])
    name = d["speaker"]["name"].strip()
    if name:
        if _is_vocab_name(name):
            raise AnswerRejected("nome_non_citato")
        if name not in authors and not any(verify.contains(q, name) for q in by_field["name"]):
            raise AnswerRejected("nome_non_citato")
    role = d["speaker"]["role"]
    if role != "anonimo" and not any(_proves_role(role, q) for q in by_field["role"]):
        raise AnswerRejected("ruolo_non_citato")
    if d["lap_time"] is not None and not any(verify.contains(q, d["lap_time"]) for q in by_field["lap_time"]):
        raise AnswerRejected("tempo_non_citato")
    if d["car"] is not None and (_is_vocab_only(d["car"])
                                 or not any(verify.contains(q, d["car"]) for q in by_field["car"])):
        raise AnswerRejected("auto_non_citata")


def _check_factcheck(d: dict, payload: dict) -> None:
    """La citazione deve stare in un testo del lavoro che non sia una fonte del fatto stesso."""
    own = set(payload.get("fact_sha256s") or [])
    reasons = []
    for t in payload.get("texts") or []:
        bad = verify.check_quote(d["quote"], t.get("body") or "", d["offset"])
        if bad is None and t.get("sha256") not in own:
            return
        reasons.append("autoconferma" if bad is None else bad)
    for r in ("autoconferma", "offset_errato", "citazione_corta"):
        if r in reasons:
            raise AnswerRejected(r)
    raise AnswerRejected("citazione_assente")


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
    track, version = d["track"], d["prompt_version"]
    payload = _open_job(conn, kind, key, track, version, model)

    facts: list[tuple] = []
    rejects: list[tuple[str, dict]] = []
    if kind == "factcheck":
        _check_factcheck(d, payload)
    else:
        rows = _acc_rows(conn, track, key)
        if not rows:
            raise AnswerRejected("testo_ignoto")
        body = rows[0][1]
        try:
            segments = next((s for s in (_segments(r[2]) for r in rows) if s), None)
        except _BadSegments:
            raise AnswerRejected("segmenti_illeggibili") from None
        if kind == "rate":
            authors = {r[4].strip() for r in rows if isinstance(r[4], str) and r[4].strip()}
            _check_rate(d, body, authors)
        else:
            seen: set[str] = set()
            for f in d["facts"]:
                canon = json.dumps(f, sort_keys=True, ensure_ascii=False)
                if canon in seen:
                    rejects.append(("fatto_duplicato", f))
                    continue
                seen.add(canon)
                bad = verify.check_fact(track, f, body, segments)
                if bad:
                    rejects.append((bad, f))
                    continue
                _, at = verify.locate_quote(f["quote"], body, f["offset"])
                start_s = _start_s(body, segments, at)
                for r in rows:
                    facts.append((track, f["corner"], f["type"], f["value"], f["quote"], f["offset"],
                                  start_s, r[4], r[9]))

    with _atomic(conn):
        cur = conn.execute(
            "INSERT INTO results(sha256, kind, prompt_version, model, payload_json, frozen_at, track)"
            " VALUES (?,?,?,?,?,?,?)",
            (key, kind, version, model, json.dumps(d, sort_keys=True, ensure_ascii=False), _now(),
             track))
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
