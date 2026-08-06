"""A training plan you can read between sessions.

The live coach already works one weakness at a time and remembers, per car and
track, which corners you've mastered (``focus.py`` + the ``focus_state`` table).
What it can't do is answer the question you have on a Tuesday, away from the
wheel: *what am I working on at the moment, and is it working?*

So this is not a second coach. It is the same weaknesses the Trends tab already
computes, turned into something with three properties a list of weak points
doesn't have:

* **it stays put.** A plan that is recomputed every time you open the page is
  not a plan — you can't work on a target that moves while you look away. It is
  proposed, you accept it, and from then on it is a fixed thing with a date on
  it;
* **it has a target you can check.** Not "improve turn 4" but "get the loss at
  turn 4 under 0.16 s" — a number measured the same way the debrief measures
  everything else;
* **it knows whether you did it**, by replaying only the laps recorded *after*
  the plan was accepted against that same target.

Nothing here invents content. What to work on comes from the trend analysis, the
words come from the debrief's own message and fix, and the corners the live coach
has already cleared are skipped — one notion of "you've got this corner", not
two.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field

from .debrief import LapDebrief, loss_at
from .thresholds import RECUR_FRAC, SIGNIF_LOSS_MS
from .trends import LossTrend

#: How many goals a plan carries. Two, and the first is *the* one: this project
#: already decided that a driver's attention is the scarce resource (the guided
#: flow caps itself at three cards, the live coach works one weakness at a
#: time). A plan with five goals is a list of weaknesses with a nicer heading.
MAX_GOALS = 2

#: How much of the loss a goal asks you to take back. Asking for all of it means
#: asking to match your own reference lap in that corner, every lap — that is a
#: definition of perfection, not a training target. Half is a step you can see
#: on the page, and it can be asked twice.
_TAKE_BACK = 0.5

#: Laps needed after accepting a plan before "done" means anything. Under three
#: you are reading one good lap as a habit.
_MIN_LAPS_TO_JUDGE = 3


@dataclass(slots=True)
class Goal:
    """One thing to work on, with the number that says when it's done."""

    corner_index: int
    name: str
    category: str            # CueCategory value, for the UI to colour/group by
    what: str                # the debrief's own message ("Carry more speed")
    fix: str                 # the debrief's own fix line
    baseline_ms: float       # the typical loss here when the plan was accepted
    target_ms: float         # get under this
    laps_seen: int           # how many laps the baseline was measured over


@dataclass(slots=True)
class GoalProgress:
    """How a goal is going, measured only on laps driven since the plan began."""

    corner_index: int
    laps: int                # laps since, that reached this corner
    hits: int                # of those, how many came in under target
    needed: int              # hits required before we call it done
    median_ms: float         # the typical loss now
    best_ms: float           # the best single lap since
    done: bool


@dataclass(slots=True)
class TrainingPlan:
    """The plan itself: what, since when, measured against what."""

    car: str = ""
    track: str = ""
    created_utc: str = ""
    goals: list[Goal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"car": self.car, "track": self.track,
                "created_utc": self.created_utc,
                "goals": [asdict(g) for g in self.goals]}

    @staticmethod
    def from_dict(d: dict) -> "TrainingPlan":
        return TrainingPlan(
            car=str(d.get("car", "")), track=str(d.get("track", "")),
            created_utc=str(d.get("created_utc", "")),
            goals=[Goal(**g) for g in d.get("goals", [])],
        )


def _target(baseline_ms: float) -> float:
    """The loss a goal asks you to get under.

    Floored at the significance threshold the whole app uses: below it we say a
    loss isn't worth coaching, so setting a target under it would be asking for
    something we'd refuse to talk about if you achieved it.
    """
    return round(max(SIGNIF_LOSS_MS, baseline_ms * _TAKE_BACK), 1)


def propose(trends: list[LossTrend], debriefs: list[LapDebrief],
            mastered: set[int] | None = None,
            car: str = "", track: str = "",
            created_utc: str = "") -> TrainingPlan:
    """Pick the goals for a new plan from the weaknesses already computed.

    ``mastered`` are the corners the live Focus coach has cleared: they are
    skipped, because two surfaces disagreeing about whether you've got a corner
    is worse than either answer alone. Systematic weaknesses come first and
    sporadic ones are never chosen — a plan is for what you do every lap, and a
    one-off is not something you can practise.
    """
    mastered = mastered or set()
    by_index = _representative_losses(debriefs)

    goals: list[Goal] = []
    for t in trends:
        if len(goals) >= MAX_GOALS:
            break
        if not t.systematic or t.corner_index in mastered:
            continue
        loss = by_index.get(t.corner_index)
        if loss is None:
            continue
        goals.append(Goal(
            corner_index=t.corner_index,
            name=t.name or loss.label,
            category=t.category.value,
            what=loss.message,
            fix=loss.fix,
            baseline_ms=round(t.median_ms, 1),
            target_ms=_target(t.median_ms),
            laps_seen=t.laps,
        ))
    return TrainingPlan(car=car, track=track, created_utc=created_utc, goals=goals)


def _representative_losses(debriefs: list[LapDebrief]) -> dict:
    """The worst instance of each corner's loss — the one with the fullest words.

    The message and the fix are per-lap: taking them from the worst example gives
    the plan the version the debrief itself considered most worth explaining,
    rather than whichever lap happened to be last.
    """
    out: dict = {}
    for d in debriefs:
        for loss in d.losses:
            best = out.get(loss.index)
            if best is None or loss.lost_ms > best.lost_ms:
                out[loss.index] = loss
    return out


def measure(plan: TrainingPlan, debriefs_since: list[LapDebrief]) -> list[GoalProgress]:
    """How each goal is going, over the laps driven since the plan was accepted.

    "Done" mirrors how a weakness became systematic in the first place: it was a
    weakness when a significant loss recurred in half the laps, so it is beaten
    when the target is met in half of them. Same fraction, same module — a
    corner can't be a weakness and beaten at the same time.
    """
    n = len(debriefs_since)
    out: list[GoalProgress] = []
    for g in plan.goals:
        losses = [loss_at(d, g.corner_index) for d in debriefs_since]
        hits = sum(1 for v in losses if v <= g.target_ms)
        needed = max(2, math.ceil(RECUR_FRAC * n)) if n else 0
        out.append(GoalProgress(
            corner_index=g.corner_index,
            laps=n, hits=hits, needed=needed,
            median_ms=round(statistics.median(losses), 1) if losses else 0.0,
            best_ms=round(min(losses), 1) if losses else 0.0,
            done=n >= _MIN_LAPS_TO_JUDGE and hits >= needed,
        ))
    return out
