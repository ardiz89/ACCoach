"""Il lavoro degli agenti: la coda dei lavori, le istruzioni, l'ingest congelato.

Gli agenti (subagenti Claude) leggono un `*.job.json` e rispondono con un JSON dello
schema del loro `kind`. La risposta si accetta intera o si rifiuta intera. Per
`extract` ogni fatto passa poi per il verificatore e quelli che non reggono finiscono
negli scarti; per `rate` e `factcheck` basta una citazione che non regge e la risposta
intera si rifiuta. Un risultato si congela per (sha256, kind, prompt_version, model, track):
un secondo ingest della stessa chiave si rifiuta.

L'ordine è extract, poi rate, poi consenso, poi factcheck:

- `extract` si propone solo per i testi che nominano almeno una curva della pista;
- `rate` solo per i testi il cui autore ha già un fatto: la valutazione serve solo a
  pesare un fatto. Il testo può non nominare curve: un coach si presenta anche altrove;
- `factcheck` solo per una voce `verificato` con almeno un testo indipendente. Ogni
  testo del lavoro è tagliato alle frasi che nominano la curva, più una prima e una
  dopo. Un `confermato` deve citare un testo indipendente dal fatto; un `respinto`
  può citare qualsiasi testo del lavoro, anche quelli del fatto stesso. Il lavoro porta
  anche gli alias della curva, numeri compresi, e in `other_values` i pezzi dove il
  codice legge un altro valore vicino al nome della curva: il controllo li deve leggere tutti
  (deciso dal pilota l'11/11, dopo la Stirling's di Brands Hatch).

Ogni lavoro proposto da `pending` si ricorda nella tabella `jobs`, per pista. La
risposta ripete `prompt_version` e `track` del lavoro; l'ingest accetta solo la
versione più alta proposta per (kind, key, track) e la congela con quella pista.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from tools.fonti import db, verify, vocab

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES = {"extract": "estrai.md", "rate": "valuta.md", "factcheck": "factcheck.md"}
KINDS = tuple(PROMPT_FILES)
ROLES = ("pilota", "coach", "anonimo")
VERDICTS = ("confermato", "respinto", "non_confermato")
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
# Un solo recinto Markdown attorno alla risposta si toglie; il resto deve essere JSON.
_FENCE = re.compile(r"\A\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n?```\s*\Z", re.DOTALL)
GAP = "\n[…]\n"  # fra due pezzi di un testo tagliato per il factcheck


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


def _own_sources(conn, track: str, entry: dict) -> tuple[list[str], list[str]]:
    """Sha256 dei testi e autori da cui viene il fatto: una verifica non si conferma su questi."""
    values = [v.get("value") for v in entry.get("values") or []
              if isinstance(v, dict) and isinstance(v.get("value"), str)]
    if not values:
        return [], []
    marks = ",".join("?" * len(values))
    rows = conn.execute(
        "SELECT r.sha256, s.platform, f.author FROM facts f JOIN results r ON r.id = f.result_id"
        " LEFT JOIN sources s ON s.id = f.source_id"
        f" WHERE f.track=? AND f.corner=? AND f.type=? AND f.value IN ({marks})",
        (track, entry.get("corner"), entry.get("type"), *values)).fetchall()
    return (sorted({r[0] for r in rows}), sorted({db.author_id(r[1], r[2]) for r in rows}))


def _mentions(track: str, corner: str, body: str) -> bool:
    text = vocab.fold(body)
    return any(vocab.alias_regex(a).search(text) for a in vocab.CORNERS.get(track, {}).get(corner, []))


def _mentions_any(track: str, body: str) -> bool:
    return any(_mentions(track, c, body) for c in vocab.CORNERS.get(track, {}))


def _authors_with_facts(conn, track: str) -> set[str]:
    return {db.author_id(p, a) for p, a in conn.execute(
        "SELECT s.platform, f.author FROM facts f JOIN sources s ON s.id = f.source_id"
        " WHERE f.track=? AND s.game='acc' AND s.track=?", (track, track))}


DISSENT_CHARS = 400  # quanto testo dopo il nome della curva guarda la ricerca degli altri valori
DISSENT_BEFORE = 25  # e quanto prima: «down to first for the bus stop», non la curva di prima


def other_values(track: str, corner: str, entry: dict, body: str) -> list[tuple[str, list[str]]]:
    """I pezzi dove il codice legge, vicino al nome della curva, un valore diverso dal fatto.

    Da ogni volta che il testo nomina la curva fino alla curva seguente, al più
    DISSENT_CHARS caratteri: «for turn eight break before the board… get into third»
    (TraxionGG a Spa dice la marcia della Bus Stop 330 caratteri dopo il nome).
    E prima del nome, fino alla curva precedente, al più DISSENT_BEFORE caratteri.
    Il codice legge i valori senza i controlli di senso: è un indizio per il controllo,
    che deve leggere ogni pezzo e decidere. `(pezzo del testo, valori diversi)`.
    """
    value = (entry.get("values") or [{}])[0].get("value")
    type_ = entry.get("type")
    if type_ in ("line", "mistake") or value is None:  # i descrittivi non hanno un valore
        return []
    nbody, idx = vocab.norm_map(body)
    if not nbody:
        return []
    masked = vocab.mask_numbers(track, nbody)
    names = vocab.CORNERS.get(track, {})
    here = sorted((m.start(), m.end()) for a in names.get(corner, [])
                  for m in vocab.alias_regex(a).finditer(nbody))
    elsewhere = sorted((m.start(), m.end()) for c, aliases in names.items() if c != corner
                       for a in aliases for m in vocab.alias_regex(a).finditer(nbody))
    spans: list[list[int]] = []
    for at, end in here:
        start = max([e for b, e in elsewhere if e <= at] + [at - DISSENT_BEFORE, 0])
        stop = min([b for b, _ in elsewhere if b >= end] + [end + DISSENT_CHARS, len(nbody)])
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], stop)
        else:
            spans.append([start, stop])
    out = []
    for start, stop in spans:
        got = vocab.values_in(type_, masked[start:stop]) - {value}
        if got:
            out.append((body[idx[start]:idx[stop - 1] + 1].strip(), sorted(got)))
    return out


def excerpt(track: str, corner: str, body: str) -> str:
    """Le frasi che nominano la curva, più una prima e una dopo; i pezzi staccati con GAP.

    Se restano tutte le frasi, il testo torna intero e identico.
    """
    frasi = verify.sentences(body)
    keep: set[int] = set()
    for i, (a, b) in enumerate(frasi):
        if _mentions(track, corner, body[a:b]):
            keep.update(k for k in (i - 1, i, i + 1) if 0 <= k < len(frasi))
    if len(keep) == len(frasi):
        return body
    pezzi, run = [], []
    for i in sorted(keep):
        if run and i != run[-1] + 1:
            pezzi.append(run)
            run = []
        run.append(i)
    if run:
        pezzi.append(run)
    return GAP.join(body[frasi[r[0]][0]:frasi[r[-1]][1]].strip() for r in pezzi)


def _clean_out_dir(out_dir: Path, kind: str, track: str, keep: set[Path]) -> None:
    """Toglie i `.job.json` di quel kind e di quella pista che non sono più da fare."""
    for p in sorted(out_dir.glob(f"{kind}-*.job.json")):
        if p in keep:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(d, dict) and d.get("kind") == kind and d.get("track") == track:
            p.unlink()


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
        with_facts = _authors_with_facts(conn, track) if kind == "rate" else set()
        for sha in sorted(texts):
            t = texts[sha]
            if kind == "extract" and not _mentions_any(track, t["body"]):
                continue  # senza una curva il verificatore non accetterà mai niente
            if kind == "rate" and not {db.author_id(m["platform"], m["author"])
                                       for m in t["meta"]} & with_facts:
                continue  # nessun fatto da pesare. Il ruolo può stare in un testo senza curve.
            if _frozen_any_model(conn, sha, kind, version, track):
                continue
            jobs.append((sha, {"kind": kind, "sha256": sha, "track": track,
                               "prompt_version": version, "body": t["body"],
                               "segments": t["segments"], "meta": t["meta"],
                               "corners": corners,
                               "aliases": {c: [a for a in vocab.CORNERS[track][c]
                                               if a != c.lower()] for c in corners},
                               "turns": {c: list(n) for c, n in
                                         vocab.TURNS.get(track, {}).items()}}))
    else:
        from tools.fonti import consensus

        for entry in consensus.build(conn, track):
            key = entry.get("fact_key")
            if (entry.get("state") != "verificato" or not key
                    or _frozen_any_model(conn, key, kind, version, track)):
                continue
            corner = entry["corner"]
            own_shas, own_authors = _own_sources(conn, track, entry)
            if not own_shas:
                # Senza le fonti del fatto non si può escludere l'autoconferma: meglio fermarsi.
                raise RuntimeError(f"pending factcheck: non trovo le fonti del fatto {key[:12]} "
                                   f"({corner}, {entry.get('type')}); la voce del consenso ha "
                                   "una forma inattesa?")
            others, independent = [], 0
            for sha, t in sorted(texts.items()):
                if not _mentions(track, corner, t["body"]):
                    continue
                authors = {db.author_id(m["platform"], m["author"]) for m in t["meta"]}
                independent += int(sha not in own_shas and not authors & set(own_authors))
                others.append({"sha256": sha, "body": excerpt(track, corner, t["body"]),
                               "segments": None, "meta": t["meta"]})
            dissent = [{"sha256": o["sha256"], "passage": s, "values": v}
                       for o in others
                       for s, v in other_values(track, corner, entry, o["body"])]
            if not independent:
                print(f"Factcheck saltato: {corner}, {entry.get('type')} ({key[:12]}) non ha "
                      "nessun testo indipendente da citare.", file=sys.stderr)
                continue
            jobs.append((key, {"kind": kind, "sha256": key, "track": track,
                               "prompt_version": version, "body": None, "segments": None,
                               "meta": [], "corners": [corner], "fact": entry,
                               "fact_sha256s": own_shas, "fact_authors": own_authors,
                               "aliases": list(vocab.CORNERS[track][corner]),
                               "other_values": dissent, "texts": others}))
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
    _clean_out_dir(out_dir, kind, track, set(paths))
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
    newest, payload = max(rows, key=lambda r: db.version_order(r[0]))
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


def _vocab_hits(text: str, track: str | None = None) -> str:
    """Il testo, normalizzato, con ogni parola del vocabolario dei fatti tolta."""
    t = vocab.fold(text)
    for term in sorted(vocab.vocab_terms(track), key=len, reverse=True):
        t = vocab.alias_regex(term).sub(" ", t)
    return t


def _is_vocab_name(name: str, track: str | None = None) -> bool:
    """Il nome è, o contiene, una curva della pista o una parola del vocabolario."""
    return _vocab_hits(name, track) != vocab.fold(name)


def _is_vocab_only(car: str, track: str | None = None) -> bool:
    """L'auto è fatta solo di parole del vocabolario (e di riempitivi)."""
    rest = [w for w in re.findall(r"[\w']+", _vocab_hits(car, track)) if w not in _FILLERS]
    return not rest


def _names_in(quote: str, name: str) -> bool:
    """Il nome sta nella citazione subito dopo una presentazione («my name is», «sono»...)."""
    leads = "|".join(re.escape(x) for x in vocab.NAME_LEADS)
    return re.search(rf"(?<![\w'])(?:{leads})\s+{re.escape(vocab.fold(name))}(?!\w)",
                     vocab.fold(quote)) is not None


def _check_rate(d: dict, body: str, authors: set[str], track: str | None = None) -> None:
    """Ogni citazione regge e ogni affermazione non vuota ha la sua; altrimenti si rifiuta tutto.

    `authors` sono solo gli autori delle righe di quel testo (`texts.author`), mai
    l'autore della fonte: in un thread l'autore del post non è chi ha scritto il commento.
    """
    by_field: dict[str, list[str]] = {f: [] for f in FIELDS}
    before: dict[str, str] = {}   # citazione del ruolo -> testo che la precede
    for r in d["reasons"]:
        bad, start = verify.locate_quote(r["quote"], body, r["offset"])
        if bad:
            raise AnswerRejected(bad)
        by_field[r["field"]].append(r["quote"])
        if r["field"] == "role":
            before[r["quote"]] = body[:start]
    name = d["speaker"]["name"].strip()
    if name:
        if _is_vocab_name(name, track):
            raise AnswerRejected("nome_non_citato")
        if name not in authors and not any(_names_in(q, name) for q in by_field["name"]):
            raise AnswerRejected("nome_non_citato")
    role = d["speaker"]["role"]
    if role != "anonimo" and not any(vocab.proves_role(role, q, before[q])
                                    for q in by_field["role"]):
        raise AnswerRejected("ruolo_non_citato")
    if d["lap_time"] is not None and (
            not vocab.LAP_TIME.fullmatch(d["lap_time"])
            or not any(verify.contains(q, d["lap_time"]) for q in by_field["lap_time"])):
        raise AnswerRejected("tempo_non_citato")
    if d["car"] is not None and (_is_vocab_only(d["car"], track)
                                 or not any(verify.contains(q, d["car"]) for q in by_field["car"])):
        raise AnswerRejected("auto_non_citata")


def _check_factcheck(d: dict, payload: dict) -> None:
    """La citazione deve stare in un testo del lavoro.

    Un `respinto` può citare qualsiasi testo del lavoro, anche uno da cui viene il fatto:
    l'ironia o la correzione dello stesso autore stanno proprio lì. Un `confermato` deve
    citare un testo indipendente: né lo stesso testo (sha256) né un altro testo dello
    stesso autore. Senza l'elenco delle fonti del fatto non si può escludere
    l'autoconferma, e il confermato si rifiuta.
    """
    texts = [t for t in payload.get("texts") or [] if isinstance(t, dict)]
    # Il taglio non è testo della fonte: una citazione che lo contiene o lo scavalca non regge.
    if GAP.strip() in d["quote"] or any(
            GAP.strip() in (t.get("body") or "")[a:b]
            for t in texts
            for _, a, b in [verify.quote_span(d["quote"], t.get("body") or "", d["offset"])]
            if a is not None):
        raise AnswerRejected("citazione_oltre_taglio")
    if d["verdict"] in ("respinto", "non_confermato"):
        reasons = [verify.check_quote(d["quote"], t.get("body") or "", d["offset"]) for t in texts]
        if None in reasons:
            return
    else:
        own = payload.get("fact_sha256s")
        if not isinstance(own, list) or not own:
            raise AnswerRejected("fonti_del_fatto_ignote")
        own = set(own)
        own_authors = set(payload.get("fact_authors") or [])
        reasons = []
        for t in texts:
            bad = verify.check_quote(d["quote"], t.get("body") or "", d["offset"])
            authors = {db.author_id(m.get("platform"), m.get("author"))
                       for m in t.get("meta") or [] if isinstance(m, dict)}
            if bad is None and t.get("sha256") not in own and not (authors & own_authors):
                return
            reasons.append("autoconferma" if bad is None else bad)
    for r in ("autoconferma", "offset_errato", "citazione_corta"):
        if r in reasons:
            raise AnswerRejected(r)
    raise AnswerRejected("citazione_assente")


def read_answer(answer_path: Path) -> dict:
    """Il JSON della risposta; un solo recinto ```json attorno si toglie."""
    try:
        raw = Path(answer_path).read_text(encoding="utf-8-sig")
        m = _FENCE.match(raw)
        return json.loads(m.group(1) if m else raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise AnswerRejected("json_malformato") from None


def summary(answer_path: Path, result: dict) -> str:
    """Una riga per l'uscita di ingest: i fatti per extract, il ruolo o il verdetto per gli altri."""
    d = read_answer(answer_path)
    if d.get("kind") == "rate":
        sp = d.get("speaker") or {}
        nome = f", nome {sp['name']}" if sp.get("name") else ""
        return f"ruolo {sp.get('role')}{nome}."
    if d.get("kind") == "factcheck":
        return f"verdetto {d.get('verdict')}."
    return f"fatti {result['facts']}, scarti {result['rejects']}."


def _verify_extract(track: str, d: dict, rows: list, segments) -> tuple[list[tuple], list]:
    """I fatti e gli scarti di una risposta di estrazione, col verificatore di adesso."""
    body = rows[0][1]
    facts: list[tuple] = []
    rejects: list[tuple[str, dict]] = []
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
        _, at, end = verify.quote_span(f["quote"], body, f["offset"])
        start_s = _start_s(body, segments, at)
        quote = body[at:end]  # il pezzo del testo, non la stringa dell'agente
        for r in rows:
            if verify.counted_otherwise(track, db.author_id(r[5], r[4]), f, body):
                rejects.append(("numerazione_diversa", f))  # il suo «turn N» è un'altra curva
                continue
            facts.append((track, f["corner"], f["type"], f["value"], quote, f["offset"],
                          start_s, r[4], r[9]))
    return facts, rejects


def reverify(conn: sqlite3.Connection, track: str) -> dict:
    """Rifà fatti e scarti delle estrazioni congelate di `track` col verificatore di adesso.

    Le risposte degli agenti non cambiano: cambia solo il controllo, che è codice. Serve
    quando si correggono il verificatore o gli alias. Un testo che non è più di quella
    pista perde i suoi fatti. `{"facts": n, "rejects": m}` dopo.
    """
    out = {"facts": 0, "rejects": 0}
    results = conn.execute("SELECT id, sha256, payload_json FROM results"
                           " WHERE kind='extract' AND track=? ORDER BY id", (track,)).fetchall()
    with _atomic(conn):
        for rid, sha, payload in results:
            conn.execute("DELETE FROM facts WHERE result_id=?", (rid,))
            conn.execute("DELETE FROM rejects WHERE result_id=?", (rid,))
            rows = _acc_rows(conn, track, sha)
            if not rows:
                continue
            try:
                segments = next((s for s in (_segments(r[2]) for r in rows) if s), None)
            except _BadSegments:
                continue
            facts, rejects = _verify_extract(track, json.loads(payload), rows, segments)
            conn.executemany(
                "INSERT INTO facts(result_id, track, corner, type, value, quote, offset, start_s,"
                " author, source_id) VALUES (?,?,?,?,?,?,?,?,?,?)", [(rid, *f) for f in facts])
            conn.executemany("INSERT INTO rejects(result_id, reason, item_json) VALUES (?,?,?)",
                             [(rid, reason, json.dumps(it, sort_keys=True, ensure_ascii=False))
                              for reason, it in rejects])
            out["facts"] += len(facts)
            out["rejects"] += len(rejects)
    return out


def ingest(conn: sqlite3.Connection, answer_path: Path, model: str) -> dict:
    """Congela una risposta e ne verifica ogni fatto; `{"facts": n, "rejects": m}`."""
    if not isinstance(model, str) or not model.strip():
        raise AnswerRejected("modello_mancante")
    d = read_answer(answer_path)
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
            _check_rate(d, body, authors, track)
        else:
            facts, rejects = _verify_extract(track, d, rows, segments)

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
