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

from dataclasses import dataclass, field

from .coaching.debrief import build_lap_debrief
from .coaching.defects import LapDefects, lap_defects
from .coaching.errors import lap_errors
from .comparison import Reference
from .recording import load_lap
from .sessions import Session

#: (percorso del riferimento, percorso del giro) -> (difetti, errori). Vive per
#: tutto il processo: un giro salvato non cambia, e se cambia il riferimento
#: cambia la chiave.
_CACHE: dict[tuple[str, str], tuple[LapDefects, dict]] = {}


def clear_cache() -> None:
    _CACHE.clear()


def is_wet_row(row: dict) -> bool | None:
    """Gomme da bagnato? Stessa regola di `diagnosis._is_wet`, su una riga del
    catalogo. ``None`` quando il giro non dice la mescola."""
    name = (row.get("tyre_compound") or "").strip().lower()
    if not name:
        return None
    return "wet" in name or "rain" in name


def history_reference(rows: list[dict], wet: bool) -> dict | None:
    """Il giro piu' veloce valido e pulito delle condizioni date, o ``None``.

    Senza mescola si conta come asciutto: e' il caso di tanti giri vecchi, e
    scartarli lascerebbe l'asciutto senza metro.
    """
    ok = [r for r in rows
          if r.get("valid") and r.get("clean") != 0
          and (r.get("lap_time_ms") or 0) > 0
          and bool(is_wet_row(r)) == wet]
    return min(ok, key=lambda r: r["lap_time_ms"]) if ok else None


@dataclass
class SessionReplay:
    session: Session
    wet: bool
    laps: list[LapDefects] = field(default_factory=list)
    errors: list[dict[str, int]] = field(default_factory=list)
    mean_gap_ms: float | None = None


def replay(session: Session, reference_row: dict, corners, ref: Reference,
           cache: dict | None = None) -> SessionReplay:
    """Rigioca i giri validi della sessione contro il riferimento unico.

    Il riferimento stesso si salta (contro se' stesso perde zero e falserebbe la
    media); i file illeggibili pure, come in `api._history`: una sessione con un
    giro rotto si mostra con quelli che ci sono.
    """
    if cache is None:
        cache = _CACHE
    ref_path = reference_row["path"]
    ref_ms = reference_row["lap_time_ms"]

    laps: list[LapDefects] = []
    errors: list[dict[str, int]] = []
    gaps: list[int] = []
    flags: list[bool | None] = []
    for row in session.valid_laps:
        if row["path"] == ref_path:
            continue
        key = (ref_path, row["path"])
        hit = cache.get(key)
        if hit is None:
            try:
                lap = load_lap(row["path"])
                hit = (lap_defects(build_lap_debrief(lap, ref, corners)),
                       lap_errors(lap, corners))
            except (OSError, ValueError):
                continue
            cache[key] = hit
        laps.append(hit[0])
        errors.append(hit[1])
        gaps.append(row["lap_time_ms"] - ref_ms)
        flags.append(is_wet_row(row))

    # Bagnato se la maggioranza dei giri che dicono la mescola e' bagnata.
    known = [f for f in flags if f is not None]
    wet = sum(known) * 2 > len(known)
    return SessionReplay(session=session, wet=wet, laps=laps, errors=errors,
                         mean_gap_ms=sum(gaps) / len(gaps) if gaps else None)
