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
