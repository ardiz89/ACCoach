"""Il consenso: quali fatti reggono su più autori indipendenti.

Tutto è deterministico e si ricalcola dal database a ogni chiamata.

- Un autore è `platform:author` in minuscolo. Due autori sono indipendenti solo se
  sono diversi e i testi che sostengono il fatto sono diversi: lo stesso corpo,
  byte per byte, scritto da due account conta una volta sola.
- Contano solo i risultati `extract` della versione più alta proposta in `jobs` per
  (kind, testo, pista), da qualsiasi modello, e solo le fonti ACC di quella pista.
- Un autore è affidabile se una valutazione `rate` (della versione più alta) di uno
  dei suoi testi su quella pista lo dice `coach` con un nome, oppure `pilota` con un
  nome e un tempo sul giro. Le valutazioni sono già verificate dall'ingest.
- Per i tipi con vocabolario:
  - `conteso`: due valori con almeno 2 autori ciascuno, oppure un valore con almeno
    2 autori e un altro con un autore affidabile;
  - `verificato`: un solo valore con almeno 2 autori (per `brake` almeno uno
    affidabile);
  - `singolo`: tutto il resto.
- `line` e `mistake` sono sempre `descrittivo`.
- Il fact-check non cambia lo stato: lo legge l'esportazione.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from tools.fonti import vocab

DESCRIPTIVE = ("line", "mistake")


def _version_order(v: str):
    return (0, int(v), "") if v.isdigit() else (1, 0, v)


def _author_id(platform, author) -> str:
    return f"{platform or ''}:{author or ''}".lower()


def fact_key(track: str, corner: str, type_: str, value: str) -> str:
    return hashlib.sha256(f"{track}|{corner}|{type_}|{value}".encode("utf-8")).hexdigest()


def _newest(conn: sqlite3.Connection, kind: str, track: str) -> dict[str, str]:
    """Per ogni chiave di quel `kind`, la versione più alta proposta in `jobs`."""
    out: dict[str, str] = {}
    for key, version in conn.execute(
            "SELECT key, prompt_version FROM jobs WHERE kind=? AND track=?", (kind, track)):
        if key not in out or _version_order(version) > _version_order(out[key]):
            out[key] = version
    return out


def _rows(conn: sqlite3.Connection, track: str) -> list[tuple]:
    """I fatti validi: risultato della versione più recente, fonte ACC di quella pista."""
    newest = _newest(conn, "extract", track)
    rows = conn.execute(
        "SELECT r.sha256, r.prompt_version, f.corner, f.type, f.value, f.quote, f.start_s,"
        " f.author, s.platform, s.url FROM facts f JOIN results r ON r.id = f.result_id"
        " JOIN sources s ON s.id = f.source_id"
        " WHERE r.kind='extract' AND r.track=? AND f.track=? AND s.game='acc' AND s.track=?",
        (track, track, track)).fetchall()
    return [r for r in rows if newest.get(r[0]) == r[1]]


def _reliable_authors(conn: sqlite3.Connection, track: str) -> set[str]:
    """Gli autori che una valutazione recente dice coach con nome o pilota con nome e tempo."""
    newest = _newest(conn, "rate", track)
    good: set[str] = set()
    for sha, version, payload in conn.execute(
            "SELECT sha256, prompt_version, payload_json FROM results WHERE kind='rate' AND track=?",
            (track,)):
        if newest.get(sha) != version:
            continue
        try:
            d = json.loads(payload)
            speaker = d.get("speaker") or {}
            role, name, lap = speaker.get("role"), speaker.get("name"), d.get("lap_time")
        except (TypeError, ValueError, AttributeError):
            continue
        named = isinstance(name, str) and bool(name.strip())
        if not (named and (role == "coach" or (role == "pilota" and lap is not None))):
            continue
        for platform, author in conn.execute(
                "SELECT s.platform, t.author FROM texts t JOIN sources s ON s.id = t.source_id"
                " WHERE t.sha256=? AND s.game='acc' AND s.track=?", (sha, track)):
            good.add(_author_id(platform, author))
    return good


def _independent(author_texts: dict[str, set[str]]) -> int:
    """Quanti gruppi di autori: due autori che condividono un testo sono un gruppo solo."""
    parent = {a: a for a in author_texts}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    owner: dict[str, str] = {}
    for a in sorted(author_texts):
        for sha in sorted(author_texts[a]):
            if sha in owner:
                parent[find(a)] = find(owner[sha])
            else:
                owner[sha] = a
    return len({find(a) for a in author_texts})


def _state(type_: str, values: list[dict], reliable: set[str]) -> str:
    if type_ in DESCRIPTIVE:
        return "descrittivo"
    strong = [v for v in values if v["n"] >= 2]
    if len(strong) >= 2:
        return "conteso"
    if len(strong) == 1:
        top = strong[0]
        if any(set(v["authors"]) & reliable for v in values if v is not top):
            return "conteso"
        if type_ == "brake" and not set(top["authors"]) & reliable:
            return "singolo"
        return "verificato"
    return "singolo"


def _source_key(s: dict):
    return (s["url"] or "", s["start_s"] is None, s["start_s"] or 0.0, s["quote"] or "")


def build(conn: sqlite3.Connection, track: str) -> list[dict]:
    """Una voce per (curva, tipo), nell'ordine delle curve della pista e poi dei tipi."""
    groups: dict[tuple[str, str], dict[str, dict]] = {}
    for sha, _v, corner, type_, value, quote, start_s, author, platform, url in _rows(conn, track):
        val = groups.setdefault((corner, type_), {}).setdefault(
            value, {"texts": {}, "sources": set()})
        val["texts"].setdefault(_author_id(platform, author), set()).add(sha)
        val["sources"].add((url, start_s, quote))
    reliable = _reliable_authors(conn, track)

    corner_order = {c: i for i, c in enumerate(vocab.CORNERS.get(track, {}))}
    type_order = {t: i for i, t in enumerate(vocab.TYPES)}
    out = []
    for (corner, type_), by_value in groups.items():
        values = []
        for value, g in by_value.items():
            sources = sorted(({"url": u, "start_s": s, "quote": q} for u, s, q in g["sources"]),
                             key=_source_key)
            values.append({"value": value, "authors": sorted(g["texts"]), "sources": sources,
                           "n": _independent(g["texts"])})
        values.sort(key=lambda v: (-v["n"], v["value"]))
        state = _state(type_, values, reliable)
        key = fact_key(track, corner, type_, values[0]["value"]) if state == "verificato" else None
        out.append({"corner": corner, "type": type_, "state": state, "fact_key": key,
                    "values": [{k: v[k] for k in ("value", "authors", "sources")} for v in values]})
    out.sort(key=lambda e: (corner_order.get(e["corner"], len(corner_order)), e["corner"],
                            type_order.get(e["type"], len(type_order)), e["type"]))
    return out
