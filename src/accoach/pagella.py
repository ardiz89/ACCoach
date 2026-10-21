"""Lo storico della Pagella: un riferimento solo, le sessioni rigiocate contro di lui.

Il debrief di un giro dice quanto ha perso *rispetto a un altro giro*. Se ogni
sessione si misurasse contro il proprio giro migliore, il difetto «frena troppo
presto» di martedi' e quello di giovedi' sarebbero numeri su righelli diversi e
la storia non direbbe niente. Qui si elegge **un** riferimento per auto/pista
(e per asciutto/bagnato, perche' un giro sul bagnato non e' un metro per
l'asciutto) e tutte le sessioni si rigiocano contro quello.

Rigiocare costa: ogni giro e' un file da leggere e un debrief da calcolare.
Il risultato per giro non cambia finche' non cambia il riferimento, quindi sta
in una cache chiave `(riferimento, giro)`.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone

from . import cornernames
from .braking_points import brake_points_of_lap
from .coaching.advice import (
    ACTIVE, DECLINED, DROPPED, MAX_ADVICE, MAX_CORNERS, PROPOSED, REACHED,
    Advice, AdviceCorner, lap_value, measure_advice, propose_advice, rebase)
from .coaching.debrief import build_lap_debrief
from .coaching.defects import (
    DEFECTS, DefectSummary, LapDefects, lap_defects, summarize, worst_corners)
from .coaching.errors import lap_errors, session_errors
from .coaching.trends import clock_covers_lap
from .coaching.howto import (
    defect_name, error_name, excluded as excluded_text, howto, problem,
    reached as reached_text, reached_by_pilot as reached_by_pilot_text, verdict)
from .comparison import Reference
from .recording import load_lap
from .sessions import Session, group_sessions, parse_utc
from .telemetry.snapshot import format_lap_time
from .track import detect_corners
from .trackdata import name_corners
from .trajectory import has_line, line_points, path_length

#: (percorso del riferimento, percorso del giro) -> (difetti, errori). Vive per
#: tutto il processo: un giro salvato non cambia, e se cambia il riferimento
#: cambia la chiave. I `LapDefects` e i dizionari degli errori sono condivisi
#: fra le chiamate: chi li riceve li legge soltanto, non li modifica.
_CACHE: dict[tuple[str, str], tuple[LapDefects, dict]] = {}


#: percorso del riferimento -> (giro, Reference, curve). Il riferimento si
#: rilegge e si ri-analizza a ogni apertura della Pagella altrimenti: e' il
#: costo fisso piu' grosso di una pagina che per il resto vive di cache.
_REFS: dict[str, tuple] = {}


def clear_cache() -> None:
    _CACHE.clear()
    _REFS.clear()


def is_wet_row(row: dict) -> bool | None:
    """Gomme da bagnato? Stessa regola di `diagnosis._is_wet`, su una riga del
    catalogo. ``None`` quando il giro non dice la mescola."""
    name = (row.get("tyre_compound") or "").strip().lower()
    if not name:
        return None
    return "wet" in name or "rain" in name


def history_candidates(rows: list[dict], wet: bool) -> list[dict]:
    """I giri validi e puliti delle condizioni date, dal piu' veloce.

    Senza mescola si conta come asciutto: e' il caso di tanti giri vecchi, e
    scartarli lascerebbe l'asciutto senza metro.
    """
    ok = [r for r in rows
          if r.get("valid") and r.get("clean") != 0
          and (r.get("lap_time_ms") or 0) > 0
          and bool(is_wet_row(r)) == wet]
    return sorted(ok, key=lambda r: r["lap_time_ms"])


def history_reference(rows: list[dict], wet: bool) -> dict | None:
    """Il giro piu' veloce valido e pulito delle condizioni date, o ``None``."""
    ok = history_candidates(rows, wet)
    return ok[0] if ok else None


@dataclass
class SessionReplay:
    session: Session
    wet: bool
    laps: list[LapDefects] = field(default_factory=list)
    errors: list[dict[str, int]] = field(default_factory=list)
    mean_gap_ms: float | None = None
    #: Le righe del catalogo dei giri rigiocati, allineate a `laps`: servono a
    #: sapere *quale* giro e *quando* (il «Come si fa» e la misura dei consigli).
    rows: list[dict] = field(default_factory=list)


def replay(session: Session, reference_row: dict, corners, ref: Reference,
           cache: dict | None = None) -> SessionReplay:
    """Rigioca i giri validi della sessione contro il riferimento unico.

    Il riferimento stesso si salta (contro se' stesso perde zero e falserebbe la
    media); i file illeggibili pure, come in `api._history`: una sessione con un
    giro rotto si mostra con quelli che ci sono. E si salta un giro il cui
    orologio non copre il giro (`trends.clock_covers_lap`, la regola del
    riepilogo di sessione): il debrief stirerebbe il buco sulle curve e ne
    uscirebbero perdite di decine di secondi che nessuno ha guidato.
    """
    if cache is None:
        cache = _CACHE
    ref_path = reference_row["path"]
    ref_ms = reference_row["lap_time_ms"]

    laps: list[LapDefects] = []
    errors: list[dict[str, int]] = []
    gaps: list[int] = []
    rows: list[dict] = []
    for row in session.valid_laps:
        if row["path"] == ref_path:
            continue
        key = (ref_path, row["path"])
        if key in cache:
            hit = cache[key]
        else:
            try:
                lap = load_lap(row["path"])
            except (OSError, ValueError):
                continue
            # Anche il «no» va in cache: il verdetto sull'orologio non cambia,
            # e rileggere il file a ogni apertura costerebbe quanto il debrief.
            hit = None
            if clock_covers_lap(lap):
                try:
                    hit = (lap_defects(build_lap_debrief(lap, ref, corners)),
                           lap_errors(lap, corners))
                except (OSError, ValueError):
                    continue
            cache[key] = hit
        if hit is None:
            continue
        laps.append(hit[0])
        errors.append(hit[1])
        gaps.append(row["lap_time_ms"] - ref_ms)
        rows.append(row)

    return SessionReplay(session=session, wet=_wet_vote(rows), laps=laps,
                         errors=errors, rows=rows,
                         mean_gap_ms=sum(gaps) / len(gaps) if gaps else None)


def _wet_vote(rows: list[dict]) -> bool:
    """Bagnato se la maggioranza dei giri che dicono la mescola e' bagnata.

    Una regola sola per due domande: di che classe e' una sessione rigiocata e
    di che classe e' una sessione prima di sapere contro quale giro rigiocarla.
    """
    known = [f for f in (is_wet_row(r) for r in rows) if f is not None]
    return sum(known) * 2 > len(known)


# --- i payload --------------------------------------------------------------
#
# La Pagella e il «Come si fa» si costruiscono qui e non in `api.py`: le route
# restano parsing dei parametri e catalogo, e la stessa lettura dello storico
# serve tre endpoint che altrimenti la rifarebbero ognuno a modo suo.

#: Sessioni del mini-andamento (la spec dice «fino a 6»).
_SERIES = 6
#: Un difetto «scende» o «sale» solo se cambia di almeno il 10% **e** di una
#: quantita' che si sente: 20 ms per i difetti in tempo, 0,1 s di veleggio.
#: Il 10% da solo chiamerebbe «in calo» un difetto che passa da 30 a 25 ms.
_TREND_FRAC = 0.10
_TREND_MIN = {"ms": 20.0, "s": 0.1}

_ACTIONS = ("follow", "drop", "reached", "decline", "undecline")


class AdviceConflict(Exception):
    """L'azione chiesta non vale nello stato attuale del consiglio (-> 409)."""


class NoSuchSession(LookupError):
    """Un indice di sessione che non esiste (-> 404): niente ritaglio muto, una
    Pagella di un'altra sessione con l'indice sbagliato sarebbe una bugia."""


class NotProposed(LookupError):
    """«Lo seguo» su un difetto che la Pagella non propone (-> 404)."""


class BadAction(ValueError):
    """Azione o difetto sconosciuti nel POST (-> 422)."""


class UnknownDefect(LookupError):
    """Un difetto che non esiste (-> 404). Distinto da un KeyError qualunque,
    che sarebbe un difetto nostro e non va spacciato per «non trovato»."""


def trend_of(now: float, before: float | None, unit: str) -> str | None:
    """«down» / «same» / «up» rispetto alla sessione prima; ``None`` senza."""
    if before is None:
        return None
    d = now - before
    if abs(d) >= _TREND_MIN[unit] and abs(d) >= _TREND_FRAC * before:
        return "down" if d < 0 else "up"
    return "same"


def _r(v: float, unit: str) -> float:
    return round(v, 2) if unit == "s" else round(v, 1)


def _unit(defect: str) -> str:
    return "s" if defect == "coasting" else "ms"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class _Context:
    """Quello che serve a giudicare la sessione `index`: classe, metro, curve.

    `same` sono gli indici (dal piu' recente) delle sessioni della stessa classe
    di gomma **fino a quella mostrata compresa**: la Pagella di martedi' non sa
    niente di giovedi'. `same_all` le comprende tutte e serve solo al rebase,
    che riguarda il consiglio e non la sessione mostrata.
    """
    runs: list[Session]
    index: int = 0
    cur: Session | None = None
    wet: bool = False
    excluded: str | None = None
    ref_row: dict | None = None
    ref_lap: object = None
    reference: Reference | None = None
    corners: list = field(default_factory=list)
    names: dict[int, str] = field(default_factory=dict)
    apex: dict[int, float] = field(default_factory=dict)
    same: list[int] = field(default_factory=list)
    same_all: list[int] = field(default_factory=list)
    _replays: dict[int, SessionReplay] = field(default_factory=dict)

    def replay_of(self, i: int) -> SessionReplay:
        if i not in self._replays:
            self._replays[i] = replay(self.runs[i], self.ref_row, self.corners,
                                      self.reference)
        return self._replays[i]

    def measured(self, limit: int | None = None) -> list[SessionReplay]:
        """Le sessioni della classe fino a quella mostrata che hanno giri
        misurati, dalla piu' recente. Una sessione fatta del solo riferimento
        non ha un valore: si salta invece di contare come zero."""
        out = []
        for i in self.same:
            rep = self.replay_of(i)
            if rep.laps:
                out.append(rep)
                if limit and len(out) >= limit:
                    break
        return out

    def corner(self, i: int):
        return next((c for c in self.corners if c.index == i), None)


def _context(cat, car: str, track: str, index: int, lang: str) -> _Context:
    rows = cat.laps_for(car, track)
    runs = group_sessions(rows)
    ctx = _Context(runs=runs)
    if index < 0 or (index > 0 and index >= len(runs)):
        raise NoSuchSession(index)
    if not runs:
        ctx.excluded = "no_laps"
        return ctx
    ctx.index = index
    ctx.cur = cur = runs[index]
    if not cur.valid_laps:
        ctx.excluded = "no_laps"
        return ctx
    ctx.wet = wet = _wet_vote(cur.valid_laps)
    klass = {i: _wet_vote(s.valid_laps) for i, s in enumerate(runs) if s.valid_laps}
    ctx.same_all = [i for i, w in klass.items() if w == wet]
    ctx.same = [i for i in ctx.same_all if i >= index]
    # Fuori dall'andamento: l'unica sessione della sua classe, con uno storico
    # (fino a qui) tutto dell'altra. Due sessioni sul bagnato fanno invece il
    # loro storico, contro il loro riferimento.
    if len(ctx.same) == 1 and any(i > index and w != wet for i, w in klass.items()):
        ctx.excluded = "wet" if wet else "dry"
        return ctx

    # Il riferimento e' uno per classe e per tutto l'archivio, non «fino alla
    # sessione mostrata»: se cambiasse sfogliando le sessioni, i consigli si
    # ricalcolerebbero avanti e indietro a ogni clic (e la cache con loro).
    # Dal piu' veloce, il primo che si legge e il cui orologio copre il giro:
    # un riferimento con un buco nell'orologio storcerebbe ogni confronto.
    ctx.ref_row = next((r for r in history_candidates(rows, wet)
                        if _reference(r["path"]) is not None), None)
    if ctx.ref_row is None:
        ctx.excluded = "no_reference"
        return ctx
    ctx.ref_lap, ctx.reference, ctx.corners = _REFS[ctx.ref_row["path"]]
    # I nomi come in `api._history`: `name_corners` sulle curve del riferimento,
    # con la mappa imparata (letta dal catalogo, dove `_history` la salva: qui
    # non si caricano tutti i giri per reimpararla) e i nomi scritti dal pilota.
    ctx.names = {c.index: n for c, n in zip(
        ctx.corners, name_corners(track, ctx.corners, lang,
                                  cat.load_corner_map(car, track),
                                  cornernames.for_track(track)))}
    ctx.apex = {c.index: c.apex_pos for c in ctx.corners}
    # Il solo riferimento non e' un confronto. Se la sessione contiene il giro
    # di riferimento e altri giri dello storico esistono, lo si dice cosi':
    # «non c'e' un altro giro» sarebbe falso.
    if not ctx.replay_of(index).laps:
        holds_ref = any(r["path"] == ctx.ref_row["path"] for r in cur.valid_laps)
        others = any(i != index and runs[i].valid_laps for i in ctx.same_all)
        ctx.excluded = "reference_session" if holds_ref and others else "no_reference"
    return ctx


def _reference(path: str):
    """(giro, Reference, curve) del riferimento, o ``None`` se non fa da metro
    (illeggibile, o col suo orologio che non copre il giro). In cache anche il no."""
    if path not in _REFS:
        try:
            lap = load_lap(path)
        except (OSError, ValueError):
            lap = None
        _REFS[path] = ((lap, Reference(lap), detect_corners(lap.samples))
                       if lap is not None and clock_covers_lap(lap) else None)
    return _REFS[path]


def _session_info(ctx: _Context) -> dict | None:
    s = ctx.cur
    if s is None:
        return None
    return {"started_utc": s.started.isoformat() if s.started else None,
            "laps": len(s.laps), "valid": len(s.valid_laps), "wet": ctx.wet}


def _reference_info(ctx: _Context) -> dict | None:
    r = ctx.ref_row
    if r is None:
        return None
    return {"lap_time": format_lap_time(r["lap_time_ms"]),
            "recorded_utc": r.get("recorded_utc"), "path": r["path"]}


# --- i consigli salvati -----------------------------------------------------

def _advice_of(d: dict) -> Advice | None:
    """Un consiglio dal suo `data_json`; ``None`` se e' malformato."""
    try:
        if d["defect"] not in DEFECTS:
            return None
        return Advice(
            defect=d["defect"],
            corners=[AdviceCorner(int(c["index"]), str(c.get("name") or ""),
                                  float(c.get("apex_pos") or 0.0),
                                  float(c.get("mean") or 0.0))
                     for c in d.get("corners") or []],
            baseline=float(d.get("baseline") or 0.0),
            target=float(d.get("target") or 0.0),
            status=str(d.get("status") or PROPOSED),
            accepted_utc=str(d.get("accepted_utc") or ""),
            closed_utc=str(d.get("closed_utc") or ""))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _load(cat, car: str, track: str) -> dict[str, tuple[Advice, str | None]]:
    out = {}
    for d in cat.load_advice(car, track):
        a = _advice_of(d)
        if a is not None:
            out[a.defect] = (a, d.get("reference_path"))
    return out


def _save(cat, car: str, track: str, a: Advice, ref_path: str | None,
          by_pilot: bool = False) -> None:
    d = asdict(a)
    if ref_path:
        d["reference_path"] = ref_path
    if by_pilot:
        d["closed_by"] = "pilot"
    cat.save_advice(car, track, d)


def _closed_by_pilot(cat, car: str, track: str) -> set[str]:
    """I consigli chiusi a mano dal pilota: un «raggiunto» dichiarato non e' un
    «raggiunto» misurato, e la frase del verdetto non deve dire il contrario."""
    return {d.get("defect") for d in cat.load_advice(car, track)
            if d.get("closed_by") == "pilot"}


def _since(ctx: _Context, stamp: str) -> list[tuple[dict, LapDefects]]:
    """I giri misurati dopo `stamp`, fino alla sessione mostrata, in ordine."""
    t0 = parse_utc(stamp)
    if t0 is None:
        return []
    out = []
    for i in reversed(ctx.same):
        s = ctx.runs[i]
        if s.ended is not None and s.ended <= t0:
            continue
        rep = ctx.replay_of(i)
        out += [(r, ld) for r, ld in zip(rep.rows, rep.laps)
                if (t := parse_utc(r.get("recorded_utc"))) and t > t0]
    return out


def _before(ctx: _Context, stamp: str) -> list[LapDefects]:
    """I giri della sessione in cui il consiglio e' stato accettato, fino a quel
    momento: la partenza del consiglio, da rimisurare se cambia il metro."""
    t0 = parse_utc(stamp)
    if t0 is None:
        return []
    for i in ctx.same_all:
        s = ctx.runs[i]
        if s.started is None or s.started > t0:
            continue
        rep = ctx.replay_of(i)
        laps = [ld for r, ld in zip(rep.rows, rep.laps)
                if (t := parse_utc(r.get("recorded_utc"))) and t <= t0]
        if laps:
            return laps
    return []


def _progress(p) -> dict:
    return {"laps": p.laps, "hits": p.hits, "needed": p.needed,
            "median": round(p.median, 2), "done": p.done}


def _reached_at(a: Advice, since: list[tuple[dict, LapDefects]]):
    """Il primo giro in cui la misura dice «fatto», con la misura fino a li'.

    Si chiude su quel giro e non sull'ora in cui si apre la pagina: cosi' il
    consiglio risulta raggiunto nella sessione in cui lo e' stato, e la
    Pagella di quella sessione lo dice a ogni lettura.
    """
    for k in range(1, len(since) + 1):
        p = measure_advice(a, [ld for _, ld in since[:k]])
        if p.done:
            return since[k - 1][0].get("recorded_utc") or "", p
    return None, measure_advice(a, [ld for _, ld in since])


def _update_active(cat, car: str, track: str, ctx: _Context,
                   stored: dict[str, tuple[Advice, str | None]]) -> None:
    """Rebase sul metro nuovo, poi «raggiunto» se la misura lo dice. Scrive."""
    ref_path = ctx.ref_row["path"]
    for key, (a, rp) in list(stored.items()):
        if a.status != ACTIVE:
            continue
        if rp != ref_path:
            laps = _before(ctx, a.accepted_utc)
            if laps:
                summary = next((s for s in summarize(laps) if s.key == key),
                               DefectSummary(key, 0.0, _unit(key), 0, len(laps)))
                a = rebase(a, summary)
            rp = ref_path
            _save(cat, car, track, a, rp)
        closed, _ = _reached_at(a, _since(ctx, a.accepted_utc))
        if closed is not None:
            a = replace(a, status=REACHED, closed_utc=closed)
            _save(cat, car, track, a, rp)
        stored[key] = (a, rp)


def _in_window(ctx: _Context, stamp: str) -> bool:
    """`stamp` cade nella sessione mostrata (fino all'inizio della successiva)?"""
    t = parse_utc(stamp)
    start = ctx.cur.started if ctx.cur else None
    if t is None or start is None or t < start:
        return False
    nxt = ctx.runs[ctx.index - 1].started if ctx.index > 0 else None
    return nxt is None or t < nxt


# --- la Pagella -------------------------------------------------------------

def build_pagella(cat, car: str, track: str, index: int, lang: str) -> dict:
    """La prima pagina del report per la sessione `index` (0 = la piu' recente).

    Ha effetti, come dice la spec: migra il piano vecchio, ricalcola i consigli
    quando cambia il riferimento e chiude quelli raggiunti.
    """
    cat.migrate_plan_to_advice(car, track)
    ctx = _context(cat, car, track, index, lang)
    out = {"session": _session_info(ctx), "excluded": ctx.excluded,
           "verdict": "", "defects": [], "worst_corners": [], "errors": [],
           "advice": [], "declined": [], "reference": _reference_info(ctx)}
    if ctx.excluded:
        out["verdict"] = excluded_text(ctx.excluded, lang)
        return out

    measured = ctx.measured(_SERIES)
    cur = measured[0]
    prev = measured[1] if len(measured) > 1 else None
    sums = [summarize(rep.laps) for rep in measured]
    summaries = sums[0]
    values = [_means(ss) for ss in sums]
    main = [s for s in summaries if s.main]

    for s in main:
        out["defects"].append({
            "key": s.key, "name": defect_name(s.key, lang),
            "value": _r(s.mean, s.unit), "unit": s.unit,
            "laps_with": s.laps_with, "laps": s.laps,
            "corners": [{"name": ctx.names.get(i, ""), "value": _r(v, s.unit)}
                        for i, v in s.corners],
            "series": _series(sums, s.key),
            "trend": _trend_at(sums, s.key),
        })
    out["worst_corners"] = [{"name": ctx.names.get(i, ""),
                             "value_s": round(v / 1000.0, 3)}
                            for i, v in worst_corners(cur.laps)]
    out["errors"] = [{"key": k, "name": error_name(k, lang), "count": n}
                     for k, n in session_errors(cur.errors)]

    # Il verdetto. «Meglio» e «peggio» guardano anche i difetti usciti dalla
    # lista: un difetto che sparisce e' la notizia migliore, non un'assenza.
    gap = max(0.0, cur.mean_gap_ms or 0.0)
    top = main[0] if main else None
    share = top.mean / gap if top and top.unit == "ms" and gap > 0 else 0.0
    cmp_ = None
    if prev:
        keys = [k for k in DEFECTS if k in values[0] or k in values[1]]
        trends = {k: _trend_at(sums, k) for k in keys}
        cmp_ = {"gap_delta_s": (gap - max(0.0, prev.mean_gap_ms or 0.0)) / 1000.0,
                "better": [k for k in keys if trends[k] == "down"],
                "worse": [k for k in keys if trends[k] == "up"]}
    text = verdict(gap / 1000.0, top, share, cmp_, lang)

    # Il piano.
    stored = _load(cat, car, track)
    _update_active(cat, car, track, ctx, stored)
    advice: list[dict] = []
    manual = _closed_by_pilot(cat, car, track)
    for a, _ in stored.values():
        if a.status == REACHED and _in_window(ctx, a.closed_utc):
            _, p = _reached_at(a, _since(ctx, a.accepted_utc))
            advice.append(_advice_item(ctx, a, p, lang))
            text += " " + (reached_by_pilot_text(a.defect, lang) if a.defect in manual
                           else reached_text(a.defect, p.hits, p.laps, lang))
    for a in propose_advice(summaries, [a for a, _ in stored.values()],
                            ctx.names, ctx.apex):
        p = (measure_advice(a, [ld for _, ld in _since(ctx, a.accepted_utc)])
             if a.status == ACTIVE else None)
        advice.append(_advice_item(ctx, a, p, lang))
    out["advice"] = advice[:MAX_ADVICE]
    # I consigli messi da parte con «Non lo seguo»: fuori dal piano, ma la
    # pagina li elenca per poterli riprendere, altrimenti la scelta non si
    # disfa piu'.
    out["declined"] = [{"defect": a.defect, "name": defect_name(a.defect, lang)}
                       for a, _ in stored.values() if a.status == DECLINED]
    out["verdict"] = text
    return out


def _means(sums: list[DefectSummary]) -> dict[str, float]:
    return {s.key: s.mean for s in sums}


def _series(sums: list[list[DefectSummary]], key: str) -> list[float]:
    """Il valore di `key` sessione per sessione, la piu' vecchia prima.

    `sums` sono i `summarize` delle sessioni misurate, dalla piu' recente. Il
    valore e' la media sui giri della sessione, zero dove il difetto non c'e'.
    Una regola sola per il mini-andamento della Pagella e per la storia lunga
    di Andamento: due conti fatti a parte prima o poi direbbero due numeri.
    """
    unit = _unit(key)
    return [_r(_means(ss).get(key, 0.0), unit) for ss in reversed(sums)]


def _trend_at(sums: list[list[DefectSummary]], key: str) -> str | None:
    """La freccia di `key`: l'ultima sessione misurata contro quella prima, sulle
    medie non arrotondate. Accanto a `_series` per lo stesso motivo: la freccia
    della Pagella e quella di Andamento non devono poter divergere."""
    if len(sums) < 2:
        return None
    return trend_of(_means(sums[0]).get(key, 0.0), _means(sums[1]).get(key, 0.0),
                    _unit(key))


# --- la storia dei difetti (Andamento) ---------------------------------------

#: Sessioni della storia lunga in Andamento.
_HISTORY = 20


def _history_context(cat, car: str, track: str,
                     lang: str) -> tuple[_Context, str | None]:
    """Il contesto della sessione piu' recente che fa parte dell'andamento, e
    la classe saltata («wet»/«dry») se per arrivarci se n'e' saltata una.

    Si salta una sessione senza giri validi, e quella che la Pagella lascia
    fuori perche' e' l'unica della sua classe di gomma con uno storico tutto
    dell'altra: la storia di chi ha fatto un'uscita sul bagnato resta quella
    dell'asciutto, invece di sparire. Ma la pagina lo dice: una sessione che
    non compare senza una parola sembrerebbe persa.
    """
    i, skipped = 0, None
    while True:
        ctx = _context(cat, car, track, i, lang)
        if ctx.excluded not in ("no_laps", "wet", "dry") or i + 1 >= len(ctx.runs):
            return ctx, skipped
        if ctx.excluded in ("wet", "dry") and skipped is None:
            skipped = ctx.excluded
        i += 1


def build_defect_history(cat, car: str, track: str, lang: str) -> dict:
    """I difetti sessione per sessione, contro il riferimento della Pagella.

    Le sessioni sono quelle della classe di gomma della piu' recente, fino a
    `_HISTORY`, la piu' vecchia prima. I difetti sono quelli principali in
    almeno una di loro: uno che sparisce resta in lista col suo zero, perche'
    vederlo calare e' il motivo della scheda. Sola lettura: niente migrazioni
    ne' consigli, che sono affare della Pagella.
    """
    ctx, skipped = _history_context(cat, car, track, lang)
    out = {"reference": _reference_info(ctx), "sessions": [], "defects": [],
           "excluded": None, "skipped": skipped}
    measured = ctx.measured(_HISTORY) if ctx.ref_row is not None else []
    if not measured:
        out["excluded"] = "no_laps" if ctx.excluded == "no_laps" else "no_reference"
        return out
    sums = [summarize(rep.laps) for rep in measured]
    out["sessions"] = [
        {"started_utc": rep.session.started.isoformat() if rep.session.started else None,
         "valid": len(rep.session.valid_laps)}
        for rep in reversed(measured)]
    main = {s.key for ss in sums for s in ss if s.main}
    # L'ordine e' quello di `summarize` sull'ultima sessione; chi li' non c'e'
    # (sparito) viene dopo, nell'ordine dei difetti.
    latest = [s.key for s in sums[0]]
    keys = sorted(main, key=lambda k: (k not in latest,
                                       latest.index(k) if k in latest else 0,
                                       _unit(k) == "s", DEFECTS.index(k)))
    now = {s.key for s in sums[0] if s.main}
    for key in keys:
        out["defects"].append({
            "key": key, "name": defect_name(key, lang), "unit": _unit(key),
            "values": _series(sums, key), "trend": _trend_at(sums, key),
            # Ancora principale nell'ultima sessione? Se no, l'ultimo valore
            # non e' piu' un difetto da segnare in rosso.
            "main": key in now,
        })
    return out


def _advice_item(ctx: _Context, a: Advice, p, lang: str) -> dict:
    unit = _unit(a.defect)
    return {"defect": a.defect, "name": defect_name(a.defect, lang),
            "status": a.status,
            "corners": [ctx.names.get(c.index) or c.name for c in a.corners],
            "target": _r(a.target, unit), "unit": unit,
            "progress": _progress(p) if p is not None else None}


# --- il «Come si fa» ----------------------------------------------------------

def build_howto(cat, car: str, track: str, defect: str, index: int,
                lang: str) -> dict:
    """La vista di un difetto: il problema coi suoi numeri, le figure per curva,
    l'esercizio e l'andamento da quando lo segui. Sola lettura."""
    if defect not in DEFECTS:
        raise UnknownDefect(defect)
    out = {"defect": defect, "name": defect_name(defect, lang), "problem": None,
           "howto": asdict(howto(defect, lang)), "figures": [], "progress": [],
           "reference_lap": None, "target": None, "unit": _unit(defect)}
    ctx = _context(cat, car, track, index, lang)
    out["reference_lap"] = _reference_info(ctx)
    if ctx.excluded:
        return out
    cur = ctx.replay_of(ctx.index)
    summaries = summarize(cur.laps)
    summary = next((s for s in summaries if s.key == defect), None)
    adv = _advice_for(cat, car, track, ctx, defect, summaries)
    # L'esercizio dice l'obiettivo in numeri (spec): quello del consiglio, lo
    # stesso che la riga del piano mostra in Pagella.
    if adv is not None:
        out["target"] = _r(adv.target, out["unit"])

    if adv is not None and adv.corners:
        idxs = [c.index for c in adv.corners]
    elif summary is not None:
        idxs = [i for i, _ in summary.corners[:MAX_CORNERS]]
    else:
        idxs = []
    out["figures"] = [f for f in (_figure(ctx, cur, defect, i) for i in idxs) if f]

    if summary is not None:
        if idxs:
            value = dict(summary.corners).get(idxs[0], 0.0)
            name = ctx.names.get(idxs[0], "")
        else:
            value, name = summary.mean, ""
        metres = None
        if idxs and defect in ("brake_early", "brake_late"):
            off = _mean_brake_offset_m(ctx, cur, ctx.corner(idxs[0]))
            # «In media N metri prima/dopo» si dice solo se la media va nel
            # verso del difetto: una staccata «presto» con la media dopo il
            # migliore e' un numero che smentisce la frase.
            if off is not None and (off < 0 if defect == "brake_early" else off > 0):
                metres = off
        if value > 0:
            out["problem"] = problem(defect, name, value, summary.unit, lang, metres)

    if adv is not None and adv.accepted_utc and adv.status != PROPOSED:
        out["progress"] = _progress_by_session(ctx, adv)
    return out


def _advice_for(cat, car, track, ctx: _Context, defect: str,
                summaries: list[DefectSummary]) -> Advice | None:
    """Il consiglio di questo difetto: quello seguito se c'e', se no la proposta."""
    stored = _load(cat, car, track)
    mine = stored.get(defect)
    if mine and mine[0].status in (ACTIVE, REACHED, DROPPED):
        return mine[0]
    others = [a for k, (a, _) in stored.items() if k != defect]
    return next((a for a in propose_advice(summaries, others, ctx.names, ctx.apex)
                 if a.defect == defect), None)


def _figure(ctx: _Context, rep: SessionReplay, defect: str, i: int) -> dict | None:
    c = ctx.corner(i)
    if c is None or not rep.laps:
        return None
    # «Il suo solito e il suo migliore» (spec): il solito e' il giro valido della
    # sessione mostrata il cui valore del difetto in questa curva e' il piu'
    # vicino alla mediana della sessione; il migliore e' il riferimento dello
    # storico, lo stesso metro di tutti i numeri della Pagella.
    vals = [ld.corners.get(defect, {}).get(i, 0.0) for ld in rep.laps]
    med = statistics.median(vals)
    j = min(range(len(vals)), key=lambda k: abs(vals[k] - med))
    typical = rep.rows[j]["path"]
    return {"corner": i, "name": ctx.names.get(i, ""),
            "entry_pos": c.entry_pos, "exit_pos": c.exit_pos,
            "typical_path": typical, "best_path": ctx.ref_row["path"],
            "brake_points_m": _brake_points_m(ctx, typical, c)}


def _brake_points_m(ctx: _Context, typical_path: str, corner) -> dict | None:
    """Dove frenano il solito e il migliore, in metri dal traguardo.

    Il punto e' quello del foglio frenate (`brake_points_of_lap`); i metri si
    misurano per entrambi sulla linea del riferimento, un righello solo, cosi'
    la differenza e' lo spostamento del punto e non della traiettoria. Senza
    coordinate non c'e' righello: ``None``.
    """
    pts = line_points(ctx.ref_lap)
    if not has_line(pts):
        return None
    try:
        lap = load_lap(typical_path)
    except (OSError, ValueError):
        return None
    t = _onset_m(pts, lap, corner)
    b = _onset_m(pts, ctx.ref_lap, corner)
    if t is None or b is None:
        return None
    return {"typical": round(t), "best": round(b)}


def _onset_m(pts, lap, corner) -> float | None:
    """Il punto di frenata del foglio frenate, in metri sulla linea `pts`."""
    bp = brake_points_of_lap(lap, [corner]) if corner is not None else []
    return path_length(pts, 0.0, bp[0].onset_pos) if bp else None


def _mean_brake_offset_m(ctx: _Context, rep: SessionReplay, corner) -> float | None:
    """Di quanto, in media sui giri della sessione, stacchi rispetto al migliore.

    Negativo = prima. Stessa misura e stesso righello delle figure (punto del
    foglio frenate, metri sulla linea del riferimento); i giri che in quella
    curva non frenano non entrano nella media.
    """
    pts = line_points(ctx.ref_lap)
    if not has_line(pts):
        return None
    best = _onset_m(pts, ctx.ref_lap, corner)
    if best is None:
        return None
    offs = []
    for row in rep.rows:
        try:
            lap = load_lap(row["path"])
        except (OSError, ValueError):
            continue
        m = _onset_m(pts, lap, corner)
        if m is not None:
            offs.append(m - best)
    return sum(offs) / len(offs) if offs else None


def _progress_by_session(ctx: _Context, a: Advice) -> list[float]:
    """Il valore del consiglio sessione per sessione dall'accettazione, la piu'
    vecchia prima: la media dei giri dopo l'accettazione, come il numero della
    Pagella e' una media."""
    t0 = parse_utc(a.accepted_utc)
    out = []
    for i in reversed(ctx.same):
        s = ctx.runs[i]
        if t0 is None or (s.ended is not None and s.ended <= t0):
            continue
        rep = ctx.replay_of(i)
        vals = [lap_value(a, ld) for r, ld in zip(rep.rows, rep.laps)
                if (t := parse_utc(r.get("recorded_utc"))) and t > t0]
        if vals:
            out.append(_r(sum(vals) / len(vals), _unit(a.defect)))
    return out


# --- le scelte del pilota ---------------------------------------------------

def advice_action(cat, car: str, track: str, defect: str, action: str,
                  index: int = 0, lang: str = "en") -> dict:
    """«Lo seguo», «Lascio stare», «Raggiunto», «Non lo seguo» e il suo inverso.

    `follow` ricalcola la proposta della sessione `index` invece di prenderla
    dal client: si segue il consiglio che la Pagella propone, con le curve e
    l'obiettivo misurati qui.
    """
    if action not in _ACTIONS or defect not in DEFECTS:
        raise BadAction(f"{action} / {defect}")
    cat.migrate_plan_to_advice(car, track)
    stored = _load(cat, car, track)
    a, ref_path = stored.get(defect, (None, None))
    now = _now()
    by_pilot = False
    if action == "follow":
        if any(x.status == ACTIVE and k != defect for k, (x, _) in stored.items()):
            raise AdviceConflict("un altro consiglio e' in corso")
        if a is not None and a.status == ACTIVE:
            return {"ok": True, "defect": defect, "status": ACTIVE}
        if a is not None and a.status == DECLINED:
            raise AdviceConflict("rifiutato: prima si riprende")
        ctx = _context(cat, car, track, index, lang)
        if ctx.excluded:
            raise NotProposed(defect)
        summaries = summarize(ctx.replay_of(ctx.index).laps)
        new = next((p for p in propose_advice(
            summaries, [x for x, _ in stored.values()], ctx.names, ctx.apex)
            if p.defect == defect), None)
        if new is None:
            raise NotProposed(defect)
        new = replace(new, status=ACTIVE, accepted_utc=now, closed_utc="")
        ref_path = ctx.ref_row["path"]
    elif action in ("drop", "reached"):
        if a is None or a.status != ACTIVE:
            raise AdviceConflict("nessun consiglio in corso su questo difetto")
        new = replace(a, status=DROPPED if action == "drop" else REACHED,
                      closed_utc=now)
        by_pilot = True
    elif action == "decline":
        if a is not None and a.status == ACTIVE:
            raise AdviceConflict("in corso: si lascia stare, non si rifiuta")
        new = (replace(a, status=DECLINED, closed_utc=now) if a is not None
               else Advice(defect=defect, status=DECLINED, closed_utc=now))
    else:  # undecline
        if a is None or a.status != DECLINED:
            raise AdviceConflict("non era rifiutato")
        new = replace(a, status=PROPOSED, closed_utc="")
    _save(cat, car, track, new, ref_path, by_pilot)
    return {"ok": True, "defect": defect, "status": new.status}
