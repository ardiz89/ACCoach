"""La sessione, curva per curva: i tuoi giri aggregati per curva.

Nessun I/O. Prende per ogni giro le righe gia' calcolate (perdite, frenate,
traiettoria) e per ogni curva dice quanto hai perso in tutto, dove, perche'
«di solito» e come sono fatte la frenata e la linea tipiche.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from ..braking_points import BrakePoint
from ..trajectory import CornerLine
from .debrief import CornerLoss

NOISE_MS = 50.0   # un giro «perde» in una curva sopra questa soglia


@dataclass
class LapCorners:
    path: str
    losses: list[CornerLoss]
    brakes: list[BrakePoint]
    lines: list[CornerLine]


@dataclass
class CornerSummary:
    index: int
    laps: int
    lost_total_ms: float
    laps_losing: int
    phases_ms: dict[str, float] = field(default_factory=dict)
    cause: str | None = None
    cause_message: str = ""
    cause_laps: int = 0
    brake_m: float | None = None
    brake_spread_m: float | None = None
    brake_kmh: float | None = None
    gear_min: str | None = None
    line_m: dict[str, float] | None = None
    apex_shift_m: float | None = None
    sided: bool = True
    best_path: str | None = None
    typical_path: str | None = None


def _cause(rows):
    """(valore, giri, messaggio del giro piu' recente) fra i giri che perdono."""
    losing = [x for _, x in rows if x.lost_ms > NOISE_MS]
    if not losing:
        return None, 0, ""
    count = Counter(x.category for x in losing)
    last = {x.category: i for i, x in enumerate(losing)}
    cat = max(count, key=lambda c: (count[c], last[c]))
    msg = next(x.message for x in reversed(losing) if x.category is cat)
    return cat.value, count[cat], msg


def _summarize(index, rows, brakes, lines) -> CornerSummary:
    lost = [x.lost_ms for _, x in rows]
    n_losing = sum(1 for v in lost if v > NOISE_MS)
    s = CornerSummary(index=index, laps=len(rows), lost_total_ms=sum(lost),
                      laps_losing=n_losing)

    per_phase: dict[str, list[float]] = {}
    for _, x in rows:
        for p in x.phases:
            per_phase.setdefault(p.phase, []).append(p.lost_ms)
    s.phases_ms = {k: median(v) for k, v in per_phase.items()}

    cause, cause_laps, msg = _cause(rows)
    if n_losing > 0 and cause_laps * 2 >= n_losing:
        s.cause, s.cause_laps, s.cause_message = cause, cause_laps, msg

    dist = [b.distance_m for b in brakes if b.distance_m > 0]
    if dist:
        s.brake_m = median(dist)
        s.brake_spread_m = max(dist) - min(dist)
    if brakes:
        s.brake_kmh = median(b.speed_kmh for b in brakes)
        gears = Counter(b.gear_min for b in brakes if b.gear_min)
        if gears:
            top = max(gears.values())
            s.gear_min = min((g for g, c in gears.items() if c == top),
                             key=lambda g: (not g.isdigit(), g))

    used = [ln for ln in lines if not ln.off_here]
    if used:
        s.line_m = {"entry": median(ln.entry_m for ln in used),
                    "apex": median(ln.apex_m for ln in used),
                    "exit": median(ln.exit_m for ln in used)}
        s.apex_shift_m = median(ln.apex_shift_m for ln in used)
        s.sided = all(ln.sided for ln in used)

    s.best_path = min(rows, key=lambda r: r[1].lost_ms)[0]
    med = median(lost)
    s.typical_path = min(rows, key=lambda r: abs(r[1].lost_ms - med))[0]
    return s


def aggregate(laps: list[LapCorners]) -> list[CornerSummary]:
    rows: dict[int, list] = {}
    brakes: dict[int, list] = {}
    lines: dict[int, list] = {}
    for lp in laps:
        for x in lp.losses:
            rows.setdefault(x.index, []).append((lp.path, x))
        for b in lp.brakes:
            brakes.setdefault(b.index, []).append(b)
        for ln in lp.lines:
            lines.setdefault(ln.index, []).append(ln)
    out = [_summarize(i, r, brakes.get(i, []), lines.get(i, []))
           for i, r in rows.items()]
    out.sort(key=lambda s: (-s.lost_total_ms, s.index))
    return out
