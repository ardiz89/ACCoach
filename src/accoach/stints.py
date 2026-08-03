"""The stint: the laps between one tank and the next, and how the pace moves.

Everything in HONE up to here has the shape of a **single lap** — study one lap,
compare it to another, find the corner that cost you. That is the right shape for
qualifying and the wrong one for the question a race asks, which is *how does the
pace hold up over twenty-five laps, and when do the tyres go away*.

**A session is not a stint, and the difference is measurable.** Sessions are cut
by :mod:`accoach.sessions` from the gaps between recordings, which is the right
heuristic for "one sitting" and blind to what happened to the car. On the archive
this was written against (720S/Monza) one ten-lap session is a genuine unbroken
run — the tank falls 59.25 → 27.78 L without ever rising — while a six-lap
session in the same evening has a **+3.18 L refuel between its first and second
lap**. Averaging the pace across that boundary averages two fuel loads and calls
the result your consistency.

That boundary cannot be found from ``fuel_used``: a refuel *between* two laps
leaves both of their burns looking perfectly ordinary. It is found by comparing
one lap's **ending** tank to the next lap's **starting** tank, which is why the
catalog indexes both (v6). The margin is not tight: inside a stint that gap
measures ±0.01 L, and the one real refuel on disk is +3.18 L.

**What this module refuses to tell you.** It reports the pace trend as a *net*
number and never attributes it. A stint gets faster because the tank empties and
slower because the tyres give up, and separating the two needs a seconds-per-litre
coefficient that **this archive cannot produce**: measured on 2026-08-03, the
spread of ordinary driving (115 → 221 s over the same fifteen laps) is two orders
of magnitude above the weight of the fuel. Until a constant-pace stint is driven
on purpose, the honest output is the slope with its own error bar — and, more
often than not on real data, the admission that the slope is smaller than the
noise it sits in. See ROADMAP voce 18.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

#: The tank rising by more than this between two laps means somebody refuelled.
#: Not a tuned number — the two populations it separates are ±0.01 L (within a
#: stint) and +3.18 L (the real refuel in the archive), so anything in between
#: would do. Shared value with :data:`accoach.coaching.fuel._REFUEL_EPS`, which
#: makes the same call live.
REFUEL_L = 0.5

#: How far off the stint's median a lap may be and still count as *pace*. A lap
#: with a spin in it is a lap you drove, and it belongs in the list — but it is
#: not the pace you were running, and one of them drags a median by seconds.
#: Chosen on the archive, where the two populations separate cleanly: every lap
#: driven at pace lands within ±4.2% of the median, and the next lap up is at
#: +7.3%, then +14.9%, +74.7%, +84.1%, +171.8%. Anything in the 4–7% gap picks
#: the same laps, so the exact value is not load-bearing.
PACE_BAND = 0.05

#: Below this many laps *at pace*, no trend is reported at all. Not a
#: statistical nicety: on three laps the fit is a line through almost nothing and
#: its error bar is meaningless. The archive shows why — a four-lap Imola session
#: fits −2.18 s/lap with a standard error of 0.097, which reads as a confident
#: two-seconds-a-lap gain and is really a driver still warming up.
MIN_TREND_LAPS = 5

# Two-sided 95% critical values of Student's t, by degrees of freedom (n - 2).
# A flat "twice the standard error" rule is too generous exactly where the data
# is thinnest, which is where this feature will usually be used.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000}


def _t95(dof: int) -> float:
    if dof <= 0:
        return float("inf")
    if dof in _T95:
        return _T95[dof]
    keys = [k for k in sorted(_T95) if k >= dof]
    return _T95[keys[0]] if keys else 1.96


def _level(row: dict, key: str) -> float | None:
    """A catalog row's tank reading, or ``None`` when the lap never recorded one."""
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return None
    return float(v) if v not in (None, "") else None


@dataclass(slots=True)
class Stint:
    """A run of laps on one tank, in the order they were driven."""

    laps: list[dict]
    #: Was the boundary *verified*, or merely not contradicted? False on laps
    #: recorded before the fuel channel existed (schema v11) — the run may well
    #: contain a refuel nobody can see. The distinction is carried all the way to
    #: the screen: a stint nobody could check must not be drawn as a fact.
    fuel_known: bool = False

    @property
    def fuel_start(self) -> float | None:
        return _level(self.laps[0], "fuel_start") if self.laps else None

    @property
    def fuel_end(self) -> float | None:
        return _level(self.laps[-1], "fuel_end") if self.laps else None

    @property
    def fuel_used(self) -> float | None:
        """Litres this stint consumed, end to end. ``None`` without the channel."""
        a, b = self.fuel_start, self.fuel_end
        return round(a - b, 2) if a is not None and b is not None and a > b else None


def split_stints(laps: list[dict], *, refuel_l: float = REFUEL_L) -> list[Stint]:
    """Split laps driven in order into the stints they belong to.

    A new stint starts wherever the tank went **up**: either between two laps
    (somebody refuelled in the pits, or restarted the session from the garage) or
    inside one (a stop mid-lap). Laps with no fuel reading cannot start or end a
    stint on evidence, so they never split one — they only make it unverified.

    ``laps`` must be oldest-first, the order :class:`accoach.sessions.Session`
    stores them in.
    """
    if not laps:
        return []
    out = [Stint([laps[0]], fuel_known=_level(laps[0], "fuel_start") is not None)]
    for row in laps[1:]:
        start = _level(row, "fuel_start")
        end = _level(row, "fuel_end")
        prev_end = None
        for earlier in reversed(out[-1].laps):     # last lap that reported a level
            prev_end = _level(earlier, "fuel_end")
            if prev_end is not None:
                break
        refuelled = (
            (start is not None and prev_end is not None and start > prev_end + refuel_l)
            or (start is not None and end is not None and end > start + refuel_l)
        )
        if refuelled:
            out.append(Stint([row], fuel_known=True))
        else:
            out[-1].laps.append(row)
            if start is None:
                out[-1].fuel_known = False
    return out


@dataclass(slots=True)
class Trend:
    """A per-lap slope with the error bar that decides whether to believe it.

    Units are the caller's: milliseconds per lap for the pace, °C per lap for the
    tread, psi per lap for the pressures. What is shared is the *judgement* —
    a slope smaller than its own 95% interval is reported as flat.
    """

    slope: float              # units per lap driven
    error: float              # standard error of the slope
    significant: bool         # does it clear its own 95% interval?

    @property
    def direction(self) -> str:
        """``"rising"`` / ``"falling"`` / ``"flat"`` — flat whenever not significant."""
        if not self.significant:
            return "flat"
        return "rising" if self.slope > 0 else "falling"


@dataclass(slots=True)
class StintPace:
    """The pace of a stint, and how much of the stint it was measured on."""

    laps: int                 # laps in the stint
    counted: int              # laps that were running pace
    #: Their positions in the stint, so a caller can grey out the rest without
    #: re-deriving the rule. The screen and the median must not be able to
    #: disagree about which laps were your pace.
    counted_at: tuple[int, ...]
    median_ms: float | None
    best_ms: int | None
    spread_ms: float | None   # slowest minus fastest, among the counted laps
    trend: Trend | None       # milliseconds per lap: + is losing pace
    #: Why there is no trend, when there isn't one: ``"few_laps"`` (fewer than
    #: :data:`MIN_TREND_LAPS` at pace) or ``None`` when a trend was computed. A
    #: computed-but-flat trend is *not* a refusal — it is the answer.
    no_trend: str | None = None


def _counted(laps: list[dict], band: float) -> list[tuple[int, int]]:
    """(position in stint, lap time) for the laps that were running pace.

    Position rather than a running index: dropping lap 4 must leave laps 3 and 5
    two apart, or the slope is fitted against a lap count nobody drove.

    The cut is **repeated until it stops moving**, because the median it measures
    against can itself be spoiled. Measured on the archive: one five-lap stint
    holds three ruined laps, so its median lands on a 2:04 and drags that lap
    into a pace whose real value is 1:55.9. A second pass drops it. Every healthy
    stint on disk is untouched by the extra passes and settles on the second, so
    this buys the bad case without costing the good one.
    """
    timed = [(i, int(r["lap_time_ms"])) for i, r in enumerate(laps)
             if r.get("valid") and r.get("clean") != 0 and int(r["lap_time_ms"]) > 0]
    while timed:
        med = statistics.median(t for _, t in timed)
        keep = [(i, t) for i, t in timed if t <= med * (1.0 + band)]
        if keep == timed:
            break
        timed = keep
    return timed


def pace_of(stint: Stint, *, band: float = PACE_BAND,
            min_trend_laps: int = MIN_TREND_LAPS) -> StintPace:
    """The stint's pace, its spread, and its trend when one can be measured."""
    laps = stint.laps
    pace = _counted(laps, band)
    at = tuple(i for i, _ in pace)
    if not pace:
        return StintPace(len(laps), 0, at, None, None, None, None, "few_laps")

    times = [t for _, t in pace]
    median = statistics.median(times)
    spread = float(max(times) - min(times))
    if len(pace) < min_trend_laps:
        return StintPace(len(laps), len(pace), at, median, min(times), spread,
                         None, "few_laps")
    return StintPace(len(laps), len(pace), at, median, min(times), spread,
                     _fit([float(i) for i, _ in pace], [float(t) for _, t in pace]))


def _fit(xs: list[float], ys: list[float]) -> Trend | None:
    """Least-squares slope of ``ys`` on ``xs``, with the error bar that judges it."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0.0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    inter = my - slope * mx
    resid_sq = sum((y - (inter + slope * x)) ** 2 for x, y in zip(xs, ys))
    error = ((resid_sq / (n - 2)) / sxx) ** 0.5
    # A slope smaller than its own confidence interval is not a slow decline you
    # can act on; it is the shape your own inconsistency happens to make.
    return Trend(slope, error, abs(slope) > _t95(n - 2) * error)


# --- what the tyres did while the pace was doing that ----------------------

@dataclass(slots=True)
class TyreTrace:
    """Tread temperature and pressure, one number per lap, plus their drift.

    Deliberately **window-free**: this asks how the tyres moved across a stint,
    not whether they sat where a GT3's tyres belong. That is what makes it valid
    on a Formula car and on a road car, where the absolute window is unknown and
    the detectors correctly stay quiet (see ``coaching/tuning.py``).

    It is also not tyre *wear*: neither sim publishes a wear figure we record, so
    what is on offer is the tread getting hotter and the pressures climbing with
    it — the symptom, not the odometer.
    """

    core_c: list[float | None]      # mean tread temp per lap, stint order
    psi: list[float | None]         # mean pressure per lap, stint order
    core_trend: Trend | None        # °C per lap
    psi_trend: Trend | None         # psi per lap


def _mean_channel(lap, attr: str) -> float | None:
    """Mean over the four corners and the whole lap, ignoring dead readings.

    Zero is what an unpopulated channel reads, and averaging it in would quietly
    halve a real temperature — the same trap `grip` fell into on ACC.
    """
    vals = [v for s in getattr(lap, "samples", []) for v in getattr(s, attr)
            if v > 0.0]
    return sum(vals) / len(vals) if vals else None


def tyre_trace(laps: list) -> TyreTrace:
    """Per-lap tread temperature and pressure for a stint's loaded laps.

    Takes lap objects rather than catalog rows: these are per-sample channels,
    so unlike the pace they cannot be answered from the index. ``laps`` is the
    stint in the order driven.
    """
    core = [_mean_channel(l, "tyre_core_temp") for l in laps]
    psi = [_mean_channel(l, "tyre_pressure") for l in laps]

    def drift(series: list[float | None]) -> Trend | None:
        pts = [(float(i), v) for i, v in enumerate(series) if v is not None]
        if len(pts) < MIN_TREND_LAPS:
            return None
        return _fit([x for x, _ in pts], [y for _, y in pts])

    return TyreTrace(core, psi, drift(core), drift(psi))
