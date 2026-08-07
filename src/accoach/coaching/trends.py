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
    # Position of this lap in the `laps` list the caller passed to
    # `session_recap` — NOT a position in `laps`, since this list has already
    # had unreadable laps dropped. A caller that wants to know which of ITS
    # laps this row is about reads `original_laps[source_index]`, where
    # `original_laps` is the exact list it handed to `session_recap`. This is
    # what makes the pairing correct by construction rather than by the
    # caller re-deriving (and hoping to match) the drop rule itself: whatever
    # reason a future version of this function has for dropping a lap, the
    # index of whatever survives is still exactly where it was.
    source_index: int


@dataclass(slots=True)
class SessionRecap:
    """Where a run's time went, averaged over its laps."""

    gain_avg_ms: float                 # average gap to the run's own best lap
    by_phase: dict[str, float]         # entry / apex / exit / after, averaged
    launch_ms: float                   # start line to the first braking zone
    laps: list[RecapLap]
    reference_ms: int                  # the run's best lap, the yardstick


@dataclass(slots=True)
class RecapOutcome:
    """A recap, or the absence of one — with the single cause worth naming.

    ``session_recap`` comes back empty for seven different reasons and a screen
    that picks one of them at random is worse than a screen that stays vague,
    so the message it shows is deliberately generic. Exactly one of those seven
    is *verified* rather than guessed: the yardstick lap's own clock does not
    account for the lap it claims to have driven (see :func:`clock_covers_lap`),
    which makes every gap measured against it wrong by that much. That one may
    be named on screen, and this flag is the only way it travels.

    It is a flag and not a reason string on purpose. A caller cannot spell a
    *different* cause with a boolean, cannot invent one, and cannot re-derive
    this one by re-running the check on its own copy of the laps (the Task 3
    lesson: two callers of one criterion, no contract, silent divergence). And
    a caller that forgets the field entirely falls back to the generic text —
    the failure mode of forgetting is vagueness, never a confident wrong claim.
    """

    recap: SessionRecap | None
    reference_clock_broken: bool = False


# --- does a lap's own clock account for the lap? -----------------------------

#: How far a lap's sample clock may sit from the stretch of lap those samples
#: cover before the lap stops being a measurement at all. The residual is
#: ``|span - lap_time_ms * (pos[-1] - pos[0])|`` with
#: ``span = samples[-1].t_ms - samples[0].t_ms``, and it is compared against
#: ``max(_CLOCK_TOL_MS, lap_time_ms * _CLOCK_TOL_FRAC)`` — the same shape as
#: ``recording.lap._TIME_TOL_MS`` / ``_TIME_TOL_FRAC``, but read the reason
#: carefully, because it is not the obvious one. The residual as a whole does
#: NOT grow with the lap: by duration band the real archive gives medians of
#: 34.3 ms (80-110 s), 31.0 ms (110-160 s) and 86.5 ms (over 160 s) — flat,
#: then a jump on a handful of long laps. What grows with the lap is the
#: *coverage* half of it, ``lap_time_ms * (1 - coverage)``, which is
#: proportional to the lap by construction and is the half this correction
#: fabricates itself. That is what the fraction is sized against, and it is
#: argued in full two paragraphs down: a flat number of milliseconds is a much
#: harsher rule on an eight-minute circuit than on a one-minute one *for the
#: part of the residual we put there ourselves*.
#:
#: Measured over the whole real archive (59 laps, 07/08/2026), percentiles by
#: ``statistics.quantiles(n=10)`` so they can be reproduced:
#:
#:     residual, ms      median 34 · p90 86.5 · the three worst 326, 694, 1140
#:     1 - coverage      median 0.00088 · p90 0.00244 · max 0.00462
#:
#: THE FRACTION is chosen against the second row, not the first. A lap whose
#: declared time has already been replaced by ``trusted_lap_ms`` has ``span ==
#: lap_time_ms`` exactly, so its residual is ``lap_time_ms * (1 - coverage)``
#: with no clock error in it at all — pure coverage, fabricated by this very
#: correction. Two of the 59 are already like that. At the median coverage a
#: 285-second lap clears 250 ms on coverage alone, and an eight-minute lap
#: (Nordschleife on AC) clears it at 1 - coverage = 0.00052, i.e. BELOW the
#: median: a flat 250 ms would void a healthy run on a long circuit and then
#: name a cause that isn't there, which is the worst way this guard can be
#: wrong. 0.007 sits 1.5x above the worst coverage in the archive (0.00462) and
#: 1.45x below the defect it exists to catch — the Red Bull Ring yardstick,
#: 694 ms on 68.369 s = 0.0102, and the lap beside it, 1140 ms on 70.849 s =
#: 0.0161.
#:
#: THE FLOOR only binds below 250/0.007 = 36 s of lap, where the fraction gets
#: tighter than the plain noise: on a lap that short coverage cannot fabricate
#: more than ~165 ms, and 56 of the 59 real laps sit at 155 ms of total residual
#: or below, then nothing at all up to 326 — more than double.
#:
#: Correcting for the fraction of the lap the samples cover is not a nicety
#: either. In the plain form (``|span - lap_time_ms|``) the same archive gives
#: median 102 ms and p90 168 ms against a first broken lap at 212 — healthy and
#: broken overlap, and there is nowhere left to put a threshold at all.
#:
#: The two fixtures that hold this pair still are ``_healthy_long_lap`` (built
#: at 1 - coverage = 0.00462, the archive max above) and ``_broken_lap`` (built
#: at 0.0102, the Red Bull Ring defect) in ``tests/test_trends.py``. They sit on
#: the two edges quoted here on purpose: move either one inwards and the suite
#: goes on passing at fractions the archive already says are wrong.
_CLOCK_TOL_MS = 250.0
_CLOCK_TOL_FRAC = 0.007


def clock_covers_lap(lap, *, tol_ms: float = _CLOCK_TOL_MS,
                     tol_frac: float = _CLOCK_TOL_FRAC) -> bool:
    """Whether ``lap``'s own clock accounts for the lap it says it drove.

    A lap whose samples span noticeably less (or more) time than the stretch of
    track they cover is not a slow lap or a fast one: it is a recording with a
    hole in it. The hole lands squarely on the number a recap hangs from —
    ``lap_time_split`` reads ``gap_ms`` at the first and last sample against
    :class:`Reference`, which pins t=0 at pos 0.0 and t=lap_time_ms at pos 1.0,
    so a clock that does not cover the lap gets stretched over it. Measured on
    a real pair (Red Bull Ring, 02/08): a reference whose clock runs 694 ms
    LONG (it accounts for more time than the fraction of lap it covers) and a
    lap whose clock falls 1140 ms SHORT, whose errors add, put ``−0.641s`` on
    screen next to two lap times 2.480 s apart. The check is symmetric because
    neither direction is a lap time: both are a recording that doesn't line up
    with the lap it claims.

    This is stricter and differently shaped than
    :func:`accoach.recording.lap.trusted_lap_ms`, and does not replace it: that
    one catches a lap stamped with a *different lap's* time (errors of a hundred
    seconds, tolerance 5 s) and repairs it. This one asks whether what survived
    is fine enough to subtract two laps with.

    Laps too short to have a span are left alone: ``lap_time_split`` already
    refuses them for its own reason, and a second rule pointed at the same laps
    is how two rules start disagreeing.
    """
    samples = getattr(lap, "samples", None) or []
    if len(samples) < 2:
        return True
    span = samples[-1].t_ms - samples[0].t_ms
    covered = lap.lap_time_ms * (samples[-1].pos - samples[0].pos)
    return abs(span - covered) <= max(tol_ms, lap.lap_time_ms * tol_frac)


def session_recap(laps, reference, corners) -> RecapOutcome:
    """How a run went, measured against its own best lap.

    The yardstick is deliberately the best lap of THIS run, not the reference
    elected for the conditions: the question is "how much was I leaving out
    there today", and a lap from a colder evening would answer it with weather.
    The best lap itself is not in ``laps`` — it would be a row of zeros.

    Returns a :class:`RecapOutcome` whose ``recap`` is None when nothing can be
    measured. A lap the split cannot read is dropped rather than counted as a
    zero: a row that says "no time lost here" where we simply could not look is
    the easiest lie on the screen.

    A lap whose own clock does not cover it (:func:`clock_covers_lap`) is
    dropped the same way — it is a broken recording, not a slow lap. When the
    lap that fails that check is the **reference**, nothing is dropped: the
    whole run is, because the yardstick is the one thing every row is measured
    against. That is the single cause a caller may name on screen, and it comes
    back on ``RecapOutcome.reference_clock_broken`` rather than being left for
    the caller to re-derive with a second copy of the same check.

    A dropped lap is not merely absent from ``.laps`` — a caller that needs to
    know which of ITS laps a returned row is about cannot re-derive that from
    position alone once laps are missing. So every :class:`RecapLap` carries
    ``source_index``, its index in the exact ``laps`` list passed in here,
    captured at the moment of filtering rather than reconstructed afterwards.
    That is what lets a caller pair a row back to its file without knowing —
    or guessing, or reimplementing — why any other lap was left out.

    Nothing here is rounded: full floats throughout, same discipline as
    ``lap_time_split`` itself, because an average of exact sums is only an
    exact sum when nothing in between has been rounded off. Rounding, if
    wanted, belongs where the caller renders this on screen.
    """
    from .phases import PHASES, lap_time_split

    # The yardstick first: a run measured against a broken clock has no correct
    # row in it, so there is nothing to salvage lap by lap.
    if not clock_covers_lap(reference.lap):
        return RecapOutcome(None, reference_clock_broken=True)

    # One criterion, two branches, written once — the reference above and every
    # lap here call the same function, so they cannot drift apart.
    splits = [(i, lap, s) for i, lap in enumerate(laps)
              if clock_covers_lap(lap)
              and (s := lap_time_split(lap, reference, corners)) is not None]
    if not splits:
        return RecapOutcome(None)

    n = len(splits)
    by_phase = {p: 0.0 for p in PHASES}
    launch = 0.0
    rows: list[RecapLap] = []
    for i, lap, s in splits:
        for phase, value in s.by_phase().items():
            by_phase[phase] += value
        launch += s.launch_ms
        worst = max(s.corners, key=lambda c: c.lost_ms, default=None)
        rows.append(RecapLap(
            lap_time_ms=lap.lap_time_ms,
            gap_ms=s.gap_ms,
            worst_index=worst.index if worst and worst.lost_ms > 0 else -1,
            worst_ms=worst.lost_ms if worst and worst.lost_ms > 0 else 0.0,
            source_index=i,
        ))

    return RecapOutcome(SessionRecap(
        gain_avg_ms=sum(r.gap_ms for r in rows) / n,
        by_phase={k: v / n for k, v in by_phase.items()},
        launch_ms=launch / n,
        laps=rows,
        reference_ms=reference.lap_time_ms,
    ))
