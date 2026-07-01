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
from ..i18n import current_language

_C = CueCategory
# Handling-cause vocabulary, per language.
_CAUSE_BALANCE = {
    "en": {Balance.UNDERSTEER: "the car understeers", Balance.OVERSTEER: "the car oversteers"},
    "it": {Balance.UNDERSTEER: "l'auto sottosterza", Balance.OVERSTEER: "l'auto sovrasterza"},
}
_CAUSE_PHASE = {
    "en": {Phase.ENTRY: "on entry", Phase.APEX: "at the apex", Phase.EXIT: "on exit"},
    "it": {Phase.ENTRY: "in ingresso", Phase.APEX: "all'apex", Phase.EXIT: "in uscita"},
}
_CAUSE_SPEED = {
    "en": {Speed.LOW: "slow corner", Speed.HIGH: "fast corner"},
    "it": {Speed.LOW: "curva lenta", Speed.HIGH: "curva veloce"},
}
# Title shown in the debrief per loss category (the live cue's own message follows
# the voice; the debrief titles each corner loss by category, per language).
_CATEGORY_TITLE = {
    "en": {_C.BRAKE_LATER: "Brake later", _C.BRAKE_EARLIER: "Brake earlier",
           _C.MORE_THROTTLE: "More throttle on exit", _C.LESS_BRAKE: "Trail off the brake",
           _C.CARRY_SPEED: "Carry more entry speed", _C.TIME_LOSS: "Time lost here"},
    "it": {_C.BRAKE_LATER: "Frena più tardi", _C.BRAKE_EARLIER: "Frena prima",
           _C.MORE_THROTTLE: "Più gas in uscita", _C.LESS_BRAKE: "Rilascia prima il freno",
           _C.CARRY_SPEED: "Porta più velocità in ingresso", _C.TIME_LOSS: "Tempo perso qui"},
}
# (detail-template, fix) per category, per language. The detail is .format()-ed
# with the named values below; the fix is a fixed sentence.
_LOSS = {
    "en": {
        _C.BRAKE_LATER: ("You start braking before the reference.",
                         "Delay your braking: move the braking point later, "
                         "so you carry more speed into the corner."),
        _C.MORE_THROTTLE: ("Average throttle {tl:.0f}% vs {tr:.0f}% of the reference.",
                           "Get back on the throttle earlier and harder on exit, "
                           "without spinning up."),
        _C.LESS_BRAKE: ("Average brake {bl:.0f}% vs {br:.0f}% of the reference.",
                        "You're braking too long: release earlier and let the car "
                        "flow toward the apex."),
        _C.CARRY_SPEED: ("Minimum speed at apex {vl:.0f} km/h vs {vr:.0f} km/h ({diff:+.0f}).",
                         "Carry more entry speed: less brake and a wider, smoother line."),
        _C.TIME_LOSS: ("You lose ~{tenths:.0f} tenths with no dominant cause.",
                       "Clean up your line and aim for consistency: review your line "
                       "and pedal timing."),
    },
    "it": {
        _C.BRAKE_LATER: ("Inizi a frenare prima del riferimento.",
                         "Ritarda la staccata: porta il punto di frenata più avanti, "
                         "così entri con più velocità."),
        _C.MORE_THROTTLE: ("Gas medio {tl:.0f}% contro {tr:.0f}% del riferimento.",
                           "Riapri il gas prima e più deciso in uscita, senza pattinare."),
        _C.LESS_BRAKE: ("Freno medio {bl:.0f}% contro {br:.0f}% del riferimento.",
                        "Stai frenando troppo a lungo: rilascia prima e lascia scorrere "
                        "la vettura verso l'apex."),
        _C.CARRY_SPEED: ("Minima all'apex {vl:.0f} km/h contro {vr:.0f} km/h ({diff:+.0f}).",
                         "Porta più velocità in ingresso: meno freno e una traiettoria "
                         "più larga e fluida."),
        _C.TIME_LOSS: ("Perdi ~{tenths:.0f} decimi senza una causa dominante.",
                       "Pulisci la traiettoria e cerca costanza: rivedi linea e "
                       "tempi di pedale."),
    },
}


def _lang(lang: str | None) -> str:
    return lang or current_language()


def explain_cause(sym: Symptom, lang: str | None = None) -> str:
    """The handling reason for a corner's loss — the 'why' the live coach can't
    spell out mid-corner: e.g. 'The car oversteers on exit (slow corner).'"""
    lg = _lang(lang)
    bal = _CAUSE_BALANCE.get(lg, _CAUSE_BALANCE["en"])
    pha = _CAUSE_PHASE.get(lg, _CAUSE_PHASE["en"])
    spd = _CAUSE_SPEED.get(lg, _CAUSE_SPEED["en"])
    return f"{bal[sym.balance].capitalize()} {pha[sym.phase]} ({spd[sym.speed]})."


def explain_loss(category: CueCategory, st: CornerStats,
                 lang: str | None = None) -> tuple[str, str]:
    """Turn a corner's cause into (detail, fix): the numbers that prove it and a
    concrete, actionable correction — the 'mini-lesson' a race engineer gives."""
    table = _LOSS.get(_lang(lang), _LOSS["en"])
    detail, fix = table.get(category, table[_C.TIME_LOSS])
    kw = dict(tl=st.throttle_live * 100, tr=st.throttle_ref * 100,
              bl=st.brake_live * 100, br=st.brake_ref * 100,
              vl=st.min_speed_live, vr=st.min_speed_ref,
              diff=st.min_speed_ref - st.min_speed_live, tenths=st.lost_ms / 100)
    return detail.format(**kw), fix


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
        return self.name or f"Corner {self.index + 1}"


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
        if self.reference_lap_ms > self.lap_time_ms:
            return True   # a new best — genuinely reference-grade
        if self.reference_lap_ms < self.lap_time_ms:
            return False  # slower than the reference
        # Exact tie on total time: it's the reference only if there's nothing to
        # learn. A lap that ties overall but bleeds time in some corners (offset
        # by gains elsewhere) still has lessons — don't mislabel it as clean.
        return not self.losses


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


_BRAKE_EARLY = {"en": " You brake ~{m:.0f} m too early.",
                "it": " Anticipi la staccata di ~{m:.0f} m."}
_BRAKE_PEAK = {"en": " Peak brake {pl:.0f}% vs {pr:.0f}%: press harder.",
               "it": " Picco freno {pl:.0f}% contro {pr:.0f}%: premi più deciso."}


def _braking_detail(lap: Lap, reference: Reference, inside: list,
                    refs: list, category: CueCategory, lang: str | None = None) -> str:
    """Decompose the braking phase: how much earlier you brake (m, interpolated)
    and whether you reach the reference's peak pressure."""
    lg = _lang(lang)
    extra = ""
    if category == CueCategory.BRAKE_LATER:
        live = _onset(inside, lambda s: s.brake)
        ref = _onset(inside, lambda s: reference.point_at(s.pos).brake)
        if live is not None and ref is not None and live < ref:
            m = _metres_between(lap, live, ref)
            if m >= 2.0:
                extra += _BRAKE_EARLY.get(lg, _BRAKE_EARLY["en"]).format(m=m)
    if category in (CueCategory.BRAKE_LATER, CueCategory.LESS_BRAKE):
        peak_live = max((s.brake for s in inside), default=0.0)
        peak_ref = max((r.brake for r in refs), default=0.0)
        if peak_ref - peak_live >= 0.05:
            extra += _BRAKE_PEAK.get(lg, _BRAKE_PEAK["en"]).format(
                pl=peak_live * 100, pr=peak_ref * 100)
    return extra


def build_lap_debrief(lap: Lap, reference: Reference, corners: list[Corner],
                      lang: str | None = None) -> LapDebrief:
    """Break ``lap`` down against ``reference`` over the given ``corners``."""
    lg = _lang(lang)
    titles = _CATEGORY_TITLE.get(lg, _CATEGORY_TITLE["en"])
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
        detail, fix = explain_loss(cue.category, stats, lg)

        # The handling "why": if the car was clearly under/oversteering somewhere
        # in this corner, lead the detail with it — the causal explanation the
        # live coach can't give mid-corner ("dice il cosa, non il perché").
        cause = ""
        dom = dominant_symptom(corner_symptoms(lap.samples, c))
        if dom is not None:
            cause = explain_cause(dom, lg)
            detail = f"{cause} {detail}"

        # Braking decomposition (earliness in metres + peak pressure).
        detail += _braking_detail(lap, reference, inside, refs, cue.category, lg)

        losses.append(CornerLoss(
            index=c.index, entry_pos=c.entry_pos, apex_pos=c.apex_pos,
            exit_pos=c.exit_pos, lost_ms=lost,
            category=cue.category,
            message=titles.get(cue.category, cue.message),
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


_FMT = {
    "en": {"lap": "Lap:", "ref": "Reference:", "is_ref":
           "This is your reference lap (no faster lap to compare against).",
           "gap": "Gap:", "worst": "Worst corners (of {n}):",
           "clean": "No significant time loss per corner — clean lap.",
           "cons": "Consistency ({n} laps): best {best}, spread {spread:.3f}s, σ {sd:.3f}s"},
    "it": {"lap": "Giro:", "ref": "Riferimento:", "is_ref":
           "Questo è il tuo giro di riferimento (nessuno più veloce da confrontare).",
           "gap": "Distacco:", "worst": "Curve peggiori (su {n}):",
           "clean": "Nessuna perdita di tempo significativa per curva — giro pulito.",
           "cons": "Costanza ({n} giri): migliore {best}, spread {spread:.3f}s, σ {sd:.3f}s"},
}


def format_debrief(d: LapDebrief, top: int = 3, consistency: dict | None = None,
                   lang: str | None = None) -> str:
    """Render a debrief as a human-readable block (terminal / log)."""
    f = _FMT.get(_lang(lang), _FMT["en"])
    lines = [
        f"Debrief — {d.car_model or '?'} @ {d.track or '?'}",
        f"  {f['lap']:11} {format_lap_time(d.lap_time_ms)}",
        f"  {f['ref']:11} {format_lap_time(d.reference_lap_ms)}",
    ]
    if d.is_reference:
        lines.append(f"  {f['is_ref']}")
    else:
        lines.append(f"  {f['gap']:11} +{d.total_gap_ms / 1000.0:.3f}s")

    if d.losses:
        lines.append("  " + f["worst"].format(n=len(d.losses)))
        for loss in d.losses[:top]:
            line = f"    {loss.label:9} −{loss.lost_ms / 1000.0:.3f}s  {loss.message}"
            if loss.cause:
                line += f"  · {loss.cause}"   # the handling "why"
            lines.append(line)
    elif not d.is_reference:
        lines.append(f"  {f['clean']}")

    if consistency and consistency.get("n", 0) >= 2:
        c = consistency
        lines.append("  " + f["cons"].format(
            n=c["n"], best=format_lap_time(c["best_ms"]),
            spread=c["spread_ms"] / 1000.0, sd=c["std_ms"] / 1000.0))
    return "\n".join(lines)
