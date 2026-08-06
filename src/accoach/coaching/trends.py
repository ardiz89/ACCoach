"""Cross-lap analysis: systematic vs sporadic losses, and benchmark levels.

The per-lap debrief answers "where did *this* lap lose time?". Over a handful of
laps a more useful question emerges: which losses are **systematic** (you give
the time away in the same corner nearly every lap — a real weakness to train, the
thing the Focus coach acts on) versus **sporadic** (a one-off mistake that won't
repay practice). Telling them apart is what turns a pile of debriefs into a plan.

The **benchmark levels** put a number on the gap between where you are and three
honest targets, in order of reachability:

* *rolling best* — your fastest clean lap (the reference you chase);
* *ideale teorico* — your best sector stitched together: the lap you've already
  driven in pieces, so the gap to it is pure consistency, freely available;
* *PRO* — an imported benchmark lap (:func:`import-reference`): the skill ceiling
  beyond your own pace.

Both are pure functions over already-built debriefs / lap times — no telemetry,
no I/O — so the API layer and tests can call them directly.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass

from .cue import CueCategory
from .debrief import LapDebrief
from .thresholds import RECUR_FRAC as _RECUR_FRAC
from .thresholds import SIGNIF_LOSS_MS as _SIGNIF_MS

# _RECUR_FRAC / _SIGNIF_MS are shared with focus.py (coaching/thresholds.py): the
# Focus coach (live, rolling window) and this tab (whole session) must agree on
# what counts as a recurring, significant weakness. The window size differs by
# design — live vs full-history — but the thresholds do not.


@dataclass(slots=True)
class LossTrend:
    """How one corner behaves across several laps."""

    corner_index: int
    name: str                 # friendly label ("Curva 4") — overridable by the API
    category: CueCategory     # the dominant loss type for this corner
    occurrences: int          # laps (of those seen) where it cost significant time
    laps: int                 # laps considered
    median_ms: float          # typical loss when it happens
    total_ms: float           # total time bled here across all laps
    systematic: bool          # recurring weakness (vs a one-off)

    @property
    def kind(self) -> str:
        return "systematic" if self.systematic else "sporadic"


def classify_losses(
    debriefs: list[LapDebrief],
    *,
    recur_frac: float = _RECUR_FRAC,
    signif_ms: float = _SIGNIF_MS,
) -> list[LossTrend]:
    """Per-corner trend across ``debriefs``, worst total first.

    A corner is *systematic* when a significant loss recurs in ≥ ``recur_frac`` of
    the laps **and** its median loss clears ``signif_ms``; otherwise *sporadic*.
    """
    n = len(debriefs)
    if n == 0:
        return []
    # ceil, not round: round() is banker's rounding, so round(0.5 * 5) == 2 and the
    # promised "at least half the laps" silently became 2/5 = 40% (and 4/9 = 44%).
    # A corner that shows up in fewer than half the laps must not read "systematic".
    recur_min = max(2, math.ceil(recur_frac * n))

    losses: dict[int, list[float]] = {}
    names: dict[int, str] = {}
    cats: dict[int, Counter] = {}
    for d in debriefs:
        for loss in d.losses:
            i = loss.index
            losses.setdefault(i, []).append(loss.lost_ms)
            names.setdefault(i, loss.label)
            cats.setdefault(i, Counter())[loss.category] += 1

    out: list[LossTrend] = []
    for i, vals in losses.items():
        occ = sum(1 for v in vals if v >= signif_ms)
        med = statistics.median(vals)
        out.append(LossTrend(
            corner_index=i,
            name=names[i],
            category=cats[i].most_common(1)[0][0],
            occurrences=occ,
            laps=n,
            median_ms=med,
            total_ms=sum(vals),
            systematic=occ >= recur_min and med >= signif_ms,
        ))
    out.sort(key=lambda t: t.total_ms, reverse=True)
    return out


@dataclass(slots=True)
class BenchmarkLevel:
    """One rung of the benchmark ladder: a target time and the gap to it."""

    key: str            # "best" / "ideal" / "pro"
    label: str          # human label (Italian)
    lap_time_ms: int
    gain_ms: int        # best_ms - lap_time_ms (positive = time available vs you)


_LEVEL_LABEL = {
    "en": {"best": "Your best lap", "ideal": "Theoretical ideal", "pro": "PRO reference"},
    "it": {"best": "Tuo miglior giro", "ideal": "Ideale teorico", "pro": "Riferimento PRO"},
}


def benchmark_levels(
    best_ms: int,
    *,
    ideal_ms: int | None = None,
    pro_ms: int | None = None,
    lang: str | None = None,
) -> list[BenchmarkLevel]:
    """The benchmark ladder for a car+track. ``best_ms`` is your rolling best;
    the ideal/PRO rungs are added only when available. ``gain_ms`` is how much
    faster each rung is than your best (negative = you're already ahead of it)."""
    if best_ms <= 0:
        return []
    from ..i18n import current_language
    lab = _LEVEL_LABEL.get(lang or current_language(), _LEVEL_LABEL["en"])
    levels = [BenchmarkLevel("best", lab["best"], best_ms, 0)]
    if ideal_ms and ideal_ms > 0:
        levels.append(BenchmarkLevel("ideal", lab["ideal"], ideal_ms,
                                     best_ms - ideal_ms))
    if pro_ms and pro_ms > 0:
        levels.append(BenchmarkLevel("pro", lab["pro"], pro_ms,
                                     best_ms - pro_ms))
    return levels


@dataclass(slots=True)
class SessionPoint:
    """How that corner went in one session."""

    started: str        # ISO UTC of the session's first lap
    laps: int           # laps in this session that carried a debrief
    median_ms: float    # typical loss there, counting laps taken well as 0.0


#: Below this many laps a median isn't a median, it's the last lap with a
#: fancier name. Same minimum the Trends tab already uses for per-corner
#: consistency (`/api/progress`, `len(vmins) >= 3`).
_MIN_SESSION_LAPS = 3


def session_series(dated: list[tuple[str, LapDebrief]], corner_index: int, *,
                   min_laps: int = _MIN_SESSION_LAPS) -> list[SessionPoint]:
    """The typical loss at a corner, session by session, oldest first.

    The session is the unit you actually train in, and two runs in the same
    afternoon stay two points: if you change something between them, you get
    to see it. The grouping **is not reimplemented here**: it goes through
    :func:`accoach.sessions.group_sessions`, the one place that knows what a
    session is (and treats the 20-minute rule as the heuristic it is).

    A session where that corner doesn't have enough laps does not produce a
    point at zero: it disappears. A zero means "taken well", and drawing it
    where the data is missing is the easiest lie on the whole chart.
    """
    from ..sessions import group_sessions
    from .debrief import loss_at

    # group_sessions only reads `recorded_utc`: we pass it fake rows that carry
    # the debrief alongside the timestamp. Reusing the function instead of
    # copying its loop is the point — a second `if gap > 20 min` would be a
    # second definition of "session" that will one day disagree with the first.
    rows = [{"recorded_utc": ts, "debrief": deb} for ts, deb in dated]
    out: list[SessionPoint] = []
    for ses in reversed(group_sessions(rows)):     # group_sessions returns newest first
        vals = [loss_at(r["debrief"], corner_index) for r in ses.laps]
        if len(vals) < min_laps:
            continue
        started = ses.laps[0]["recorded_utc"]
        out.append(SessionPoint(started=started, laps=len(vals),
                                median_ms=statistics.median(vals)))
    return out


# --- the recap of one session ------------------------------------------------

# The whole-lap split (Task 1, ``phases.lap_time_split``) gives one lap's gap
# in parts that add back up to it, exactly. A recap is the same question asked
# of a whole run: not "where did this lap lose time" but "where did the seconds
# of this outing go, on average" — measured in tenths that sum, not a score.


@dataclass(slots=True)
class RecapLap:
    """One lap of the run, as the recap shows it."""

    lap_time_ms: int
    gap_ms: float
    worst_index: int          # -1 when no corner cost anything
    worst_ms: float


@dataclass(slots=True)
class SessionRecap:
    """Where a run's time went, averaged over its laps."""

    gain_avg_ms: float                 # average gap to the run's own best lap
    by_phase: dict[str, float]         # entry / apex / exit / after, averaged
    launch_ms: float                   # start line to the first braking zone
    laps: list[RecapLap]
    reference_ms: int                  # the run's best lap, the yardstick


def session_recap(laps, reference, corners) -> SessionRecap | None:
    """How a run went, measured against its own best lap.

    The yardstick is deliberately the best lap of THIS run, not the reference
    elected for the conditions: the question is "how much was I leaving out
    there today", and a lap from a colder evening would answer it with weather.
    The best lap itself is not in ``laps`` — it would be a row of zeros.

    Returns None when nothing can be measured. A lap the split cannot read is
    dropped rather than counted as a zero: a row that says "no time lost here"
    where we simply could not look is the easiest lie on the screen.

    Nothing here is rounded: full floats throughout, same discipline as
    ``lap_time_split`` itself, because an average of exact sums is only an
    exact sum when nothing in between has been rounded off. Rounding, if
    wanted, belongs where the caller renders this on screen.
    """
    from .phases import PHASES, lap_time_split

    splits = [(lap, s) for lap in laps
              if (s := lap_time_split(lap, reference, corners)) is not None]
    if not splits:
        return None

    n = len(splits)
    by_phase = {p: 0.0 for p in PHASES}
    launch = 0.0
    rows: list[RecapLap] = []
    for lap, s in splits:
        for phase, value in s.by_phase().items():
            by_phase[phase] += value
        launch += s.launch_ms
        worst = max(s.corners, key=lambda c: c.lost_ms, default=None)
        rows.append(RecapLap(
            lap_time_ms=lap.lap_time_ms,
            gap_ms=s.gap_ms,
            worst_index=worst.index if worst and worst.lost_ms > 0 else -1,
            worst_ms=worst.lost_ms if worst and worst.lost_ms > 0 else 0.0,
        ))

    return SessionRecap(
        gain_avg_ms=sum(r.gap_ms for r in rows) / n,
        by_phase={k: v / n for k, v in by_phase.items()},
        launch_ms=launch / n,
        laps=rows,
        reference_ms=reference.lap_time_ms,
    )
