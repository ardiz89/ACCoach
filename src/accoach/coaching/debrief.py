"""Post-lap debrief — the cold-blooded half of coaching.

Live coaching can only say one thing at a time and must stay terse. The debrief
is the opposite: once the lap is done, look at the *whole* lap against the
reference and rank where the time actually went, with the cause of each loss.
That's where the rich per-corner data pays off and where a driver, no longer
busy driving, can absorb detail.

:func:`build_lap_debrief` replays a recorded lap against a :class:`Reference`
corner by corner, reusing the exact cause attribution the live analyzer uses
(:func:`~accoach.coaching.analyzer.classify_corner`), so live and debrief never
disagree. :func:`lap_time_consistency` summarizes how repeatable a set of laps
is — the other thing a coach harps on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..comparison.reference import Reference
from ..engineer import Balance, Phase, Speed, Symptom
from ..recording.lap import Lap
from ..telemetry.snapshot import format_lap_time
from ..track import Corner
from .analyzer import _BRAKE_ON, _LOSS_MS, CornerStats, classify_corner
from .cue import CueCategory
from .diagnosis import corner_symptoms, dominant_symptom

_CAUSE_BALANCE = {Balance.UNDERSTEER: "l'auto sottosterza",
                  Balance.OVERSTEER: "l'auto sovrasterza"}
_CAUSE_PHASE = {Phase.ENTRY: "in ingresso", Phase.APEX: "all'apex", Phase.EXIT: "in uscita"}
_CAUSE_SPEED = {Speed.LOW: "curva lenta", Speed.HIGH: "curva veloce"}


def explain_cause(sym: Symptom) -> str:
    """The handling reason for a corner's loss, in Italian — the 'why' the live
    coach can't spell out mid-corner: e.g. 'L'auto sovrasterza in uscita (curva lenta).'"""
    return (f"{_CAUSE_BALANCE[sym.balance].capitalize()} "
            f"{_CAUSE_PHASE[sym.phase]} ({_CAUSE_SPEED[sym.speed]}).")


def explain_loss(category: CueCategory, st: CornerStats) -> tuple[str, str]:
    """Turn a corner's cause into (detail, fix): the numbers that prove it and a
    concrete, actionable correction — the 'mini-lesson' a race engineer gives."""
    if category == CueCategory.BRAKE_LATER:
        return ("Inizi a frenare prima del riferimento.",
                "Ritarda la staccata: porta il punto di frenata più avanti, "
                "così entri con più velocità.")
    if category == CueCategory.MORE_THROTTLE:
        return (f"Gas medio {st.throttle_live * 100:.0f}% contro "
                f"{st.throttle_ref * 100:.0f}% del riferimento.",
                "Riapri il gas prima e più deciso in uscita, senza pattinare.")
    if category == CueCategory.LESS_BRAKE:
        return (f"Freno medio {st.brake_live * 100:.0f}% contro "
                f"{st.brake_ref * 100:.0f}% del riferimento.",
                "Stai frenando troppo a lungo: rilascia prima e lascia scorrere "
                "la vettura verso l'apex.")
    if category == CueCategory.CARRY_SPEED:
        diff = st.min_speed_ref - st.min_speed_live
        return (f"Minima all'apex {st.min_speed_live:.0f} km/h contro "
                f"{st.min_speed_ref:.0f} km/h ({diff:+.0f}).",
                "Porta più velocità in ingresso: meno freno e una traiettoria "
                "più larga e fluida.")
    # TIME_LOSS / anything else
    return (f"Perdi ~{st.lost_ms / 100:.0f} decimi senza una causa dominante.",
            "Pulisci la traiettoria e cerca costanza: rivedi linea e tempi di pedale.")


@dataclass(slots=True)
class CornerLoss:
    """One corner's contribution to the lap's time loss."""

    index: int                 # 0-based corner index
    entry_pos: float
    apex_pos: float
    exit_pos: float
    lost_ms: float
    category: CueCategory
    message: str
    detail: str = ""           # the numbers that prove the cause
    fix: str = ""              # the actionable correction
    cause: str = ""            # handling "why": understeer/oversteer × phase × speed
    min_speed_live: float = 0.0
    min_speed_ref: float = 0.0
    name: str = ""             # friendly corner name (set by the API layer)

    @property
    def label(self) -> str:
        return self.name or f"Curva {self.index + 1}"


@dataclass(slots=True)
class LapDebrief:
    """Ranked breakdown of where a lap lost time vs the reference."""

    car_model: str
    track: str
    lap_time_ms: int
    reference_lap_ms: int
    losses: list[CornerLoss] = field(default_factory=list)  # worst first

    @property
    def total_gap_ms(self) -> int:
        return self.lap_time_ms - self.reference_lap_ms

    @property
    def is_reference(self) -> bool:
        return self.reference_lap_ms >= self.lap_time_ms


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _next_entry(c: Corner, corners: list[Corner]) -> float:
    """Entry of the next corner after ``c`` — the loss window's end, so the
    straight that follows ``c`` is credited to ``c`` (where the exit speed that
    sets the straight was won or lost). 1.01 (lap end) if ``c`` is the last."""
    later = sorted(x.entry_pos for x in corners if x.entry_pos > c.exit_pos)
    return later[0] if later else 1.01


def _onset(samples, getval) -> float | None:
    """Interpolated normalized position where ``getval`` first crosses _BRAKE_ON."""
    prev = None
    for s in samples:
        v = getval(s)
        if v >= _BRAKE_ON:
            if prev is None:
                return s.pos
            pv = getval(prev)
            if pv < _BRAKE_ON and v != pv:        # sub-sample crossing
                frac = (_BRAKE_ON - pv) / (v - pv)
                return prev.pos + frac * (s.pos - prev.pos)
            return s.pos
        prev = s
    return None


def _coords_at(lap: Lap, pos: float) -> tuple[float, float] | None:
    s = lap.samples
    if not s:
        return None
    if pos <= s[0].pos:
        return (s[0].car_x, s[0].car_z)
    for i in range(1, len(s)):
        if s[i].pos >= pos:
            a, b = s[i - 1], s[i]
            span = b.pos - a.pos
            f = 0.0 if span <= 0 else (pos - a.pos) / span
            return (a.car_x + f * (b.car_x - a.car_x), a.car_z + f * (b.car_z - a.car_z))
    return (s[-1].car_x, s[-1].car_z)


def _metres_between(lap: Lap, a: float, b: float) -> float:
    """Chord distance (m) between two track positions via world coords (0 if no
    coords on this lap — pre-v3)."""
    pa, pb = _coords_at(lap, a), _coords_at(lap, b)
    if pa is None or pb is None:
        return 0.0
    return math.hypot(pa[0] - pb[0], pa[1] - pb[1])


def _braking_detail(lap: Lap, reference: Reference, inside: list,
                    refs: list, category: CueCategory) -> str:
    """Decompose the braking phase: how much earlier you brake (m, interpolated)
    and whether you reach the reference's peak pressure."""
    extra = ""
    if category == CueCategory.BRAKE_LATER:
        live = _onset(inside, lambda s: s.brake)
        ref = _onset(inside, lambda s: reference.point_at(s.pos).brake)
        if live is not None and ref is not None and live < ref:
            m = _metres_between(lap, live, ref)
            if m >= 2.0:
                extra += f" Anticipi la staccata di ~{m:.0f} m."
    if category in (CueCategory.BRAKE_LATER, CueCategory.LESS_BRAKE):
        peak_live = max((s.brake for s in inside), default=0.0)
        peak_ref = max((r.brake for r in refs), default=0.0)
        if peak_ref - peak_live >= 0.05:
            extra += (f" Picco freno {peak_live * 100:.0f}% contro "
                      f"{peak_ref * 100:.0f}%: premi più deciso.")
    return extra


def build_lap_debrief(lap: Lap, reference: Reference, corners: list[Corner]) -> LapDebrief:
    """Break ``lap`` down against ``reference`` over the given ``corners``."""
    losses: list[CornerLoss] = []

    for c in corners:
        inside = [s for s in lap.samples if c.entry_pos <= s.pos <= c.exit_pos]
        if len(inside) < 2:
            continue

        # Loss is measured from this corner's entry to the NEXT corner's entry, so
        # the following straight is credited here — a poor exit shows up as time
        # bled down the straight, attributed to the corner that caused it. The
        # input/balance analysis below still uses only the corner region (inside).
        end = _next_entry(c, corners)
        window = [s for s in lap.samples if c.entry_pos <= s.pos < end] or inside
        first, last = window[0], window[-1]
        delta_entry = first.t_ms - reference.time_at(first.pos)
        delta_exit = last.t_ms - reference.time_at(last.pos)
        lost = delta_exit - delta_entry

        thr_live = _mean([s.throttle for s in inside])
        brk_live = _mean([s.brake for s in inside])
        vmin_live = min(s.speed_kmh for s in inside)
        refs = [reference.point_at(s.pos) for s in inside]
        thr_ref = _mean([r.throttle for r in refs])
        brk_ref = _mean([r.brake for r in refs])
        vmin_ref = min(r.speed_kmh for r in refs)

        # Did you brake where the reference wasn't braking yet?
        braking_early = False
        for s in inside:
            if s.brake >= _BRAKE_ON:
                braking_early = reference.point_at(s.pos).brake < _BRAKE_ON
                break

        stats = CornerStats(
            lost_ms=lost, throttle_live=thr_live, throttle_ref=thr_ref,
            brake_live=brk_live, brake_ref=brk_ref,
            min_speed_live=vmin_live, min_speed_ref=vmin_ref,
            braking_early=braking_early,
        )
        cue = classify_corner(stats, c.index, c.apex_pos)
        if cue is None or cue.category == CueCategory.GOOD:
            continue  # corner not a meaningful loss
        detail, fix = explain_loss(cue.category, stats)

        # The handling "why": if the car was clearly under/oversteering somewhere
        # in this corner, lead the detail with it — the causal explanation the
        # live coach can't give mid-corner ("dice il cosa, non il perché").
        cause = ""
        dom = dominant_symptom(corner_symptoms(lap.samples, c))
        if dom is not None:
            cause = explain_cause(dom)
            detail = f"{cause} {detail}"

        # Braking decomposition (earliness in metres + peak pressure).
        detail += _braking_detail(lap, reference, inside, refs, cue.category)

        losses.append(CornerLoss(
            index=c.index, entry_pos=c.entry_pos, apex_pos=c.apex_pos,
            exit_pos=c.exit_pos, lost_ms=lost,
            category=cue.category, message=cue.message,
            detail=detail, fix=fix, cause=cause,
            min_speed_live=vmin_live, min_speed_ref=vmin_ref,
        ))

    losses.sort(key=lambda x: x.lost_ms, reverse=True)
    return LapDebrief(
        car_model=lap.car_model, track=lap.track,
        lap_time_ms=lap.lap_time_ms, reference_lap_ms=reference.lap_time_ms,
        losses=losses,
    )


def lap_time_consistency(lap_times_ms: list[int]) -> dict:
    """Spread of a set of lap times — how repeatable the driver is."""
    times = [t for t in lap_times_ms if t > 0]
    if not times:
        return {"n": 0, "best_ms": 0, "mean_ms": 0, "spread_ms": 0, "std_ms": 0.0}
    n = len(times)
    best = min(times)
    mean = sum(times) / n
    spread = max(times) - best
    var = sum((t - mean) ** 2 for t in times) / n
    return {"n": n, "best_ms": best, "mean_ms": int(mean),
            "spread_ms": spread, "std_ms": var ** 0.5}


def format_debrief(d: LapDebrief, top: int = 3, consistency: dict | None = None) -> str:
    """Render a debrief as a human-readable block (terminal / log)."""
    lines = [
        f"Debrief — {d.car_model or '?'} @ {d.track or '?'}",
        f"  Giro:       {format_lap_time(d.lap_time_ms)}",
        f"  Riferimento:{format_lap_time(d.reference_lap_ms)}",
    ]
    if d.is_reference:
        lines.append("  Questo è il tuo giro di riferimento (nessuno più veloce da confrontare).")
    else:
        lines.append(f"  Distacco:   +{d.total_gap_ms / 1000.0:.3f}s")

    if d.losses:
        lines.append(f"  Curve peggiori (su {len(d.losses)}):")
        for loss in d.losses[:top]:
            line = f"    {loss.label:9} −{loss.lost_ms / 1000.0:.3f}s  {loss.message}"
            if loss.cause:
                line += f"  · {loss.cause}"   # the handling "why"
            lines.append(line)
    elif not d.is_reference:
        lines.append("  Nessuna perdita di tempo significativa per curva — giro pulito.")

    if consistency and consistency.get("n", 0) >= 2:
        c = consistency
        lines.append(
            f"  Costanza ({c['n']} giri): migliore {format_lap_time(c['best_ms'])}, "
            f"spread {c['spread_ms'] / 1000.0:.3f}s, σ {c['std_ms'] / 1000.0:.3f}s"
        )
    return "\n".join(lines)
