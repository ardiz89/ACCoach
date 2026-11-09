"""L'esportazione dei fatti confermati nel pacchetto dell'app.

Esce solo una voce `verificato` del consenso che il controllo ha confermato:

- contano i factcheck della versione più alta proposta in `jobs` per quella chiave,
  da qualsiasi modello;
- serve almeno un `confermato` e nessun `respinto`;
- un `verificato` senza controllo non esce: il controllo è un veto e una conferma
  del contesto, non una prova in più.

`line` e `mistake` (descrittivi) non escono mai. `brake` e `gear` escono con
`"car_class": "gt3"`: il consenso li conta solo da fonti GT3. Il file è deterministico:
ordine del consenso, citazioni tagliate a QUOTE_WORDS parole e QUOTE_CHARS caratteri,
`json.dumps(sort_keys=True, ensure_ascii=False, indent=1)` e fine riga `\\n`.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tools.fonti import consensus, db

VERSION = 1
QUOTE_WORDS = 15
QUOTE_CHARS = 300


def cut(text: str | None, words: int = QUOTE_WORDS) -> str:
    """Le prime `words` parole, spazi normalizzati, al massimo QUOTE_CHARS caratteri."""
    return " ".join(str(text or "").split()[:words])[:QUOTE_CHARS]


def factchecks(conn: sqlite3.Connection, track: str) -> dict[str, dict[str, list[dict]]]:
    """Per ogni fact_key, i payload dei controlli validi divisi per verdetto."""
    newest = db.newest_versions(conn, "factcheck", track)
    out: dict[str, dict[str, list[dict]]] = {}
    for key, version, model, payload in conn.execute(
            "SELECT sha256, prompt_version, model, payload_json FROM results"
            " WHERE kind='factcheck' AND track=? ORDER BY sha256, model, id", (track,)):
        if newest.get(key) != version:
            continue
        try:
            d = json.loads(payload)
        except (TypeError, ValueError):
            continue
        verdict = d.get("verdict") if isinstance(d, dict) else None
        if verdict not in ("confermato", "respinto"):
            continue
        d = dict(d, model=model)
        out.setdefault(key, {"confermato": [], "respinto": []})[verdict].append(d)
    return out


def status(entry: dict, checks: dict[str, dict[str, list[dict]]]) -> str | None:
    """`confermato`, `respinto` o None (nessun controllo) per una voce verificata."""
    if entry.get("state") != "verificato" or not entry.get("fact_key"):
        return None
    c = checks.get(entry["fact_key"])
    if not c:
        return None
    if c["respinto"]:
        return "respinto"
    return "confermato" if c["confermato"] else None


def _sources(value: dict) -> list[dict]:
    seen, out = set(), []
    for s in value["sources"]:
        item = {"url": s["url"], "start_s": s["start_s"], "quote": cut(s["quote"])}
        k = (item["url"], item["start_s"], item["quote"])
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def facts(conn: sqlite3.Connection, track: str) -> list[dict]:
    checks = factchecks(conn, track)
    out = []
    for e in consensus.build(conn, track):
        if status(e, checks) != "confermato":
            continue
        top = e["values"][0]
        item = {"corner": e["corner"], "type": e["type"], "value": top["value"],
                "n": top["n"], "sources": _sources(top)}
        if e["type"] in consensus.GT3_ONLY:
            item["car_class"] = "gt3"
        out.append(item)
    return out


def dumps(track: str, items: list[dict]) -> str:
    return json.dumps({"track": track, "version": VERSION, "facts": items},
                      sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def target(out: Path, track: str) -> Path:
    """`out` è la cartella (vi si scrive `<track>.json`) oppure il file `.json`."""
    out = Path(out)
    return out if out.suffix == ".json" else out / f"{track}.json"


def export(conn: sqlite3.Connection, track: str, out: Path) -> int:
    """Scrive i fatti confermati della pista; restituisce quanti sono."""
    items = facts(conn, track)
    path = target(out, track)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(track, items), encoding="utf-8", newline="\n")
    return len(items)
