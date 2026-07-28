"""The lap explained one step at a time, instead of five dashboards at once.

The debrief already knows everything this module says: which corner cost what,
the numbers that prove the cause, and the correction. What it doesn't do is
*decide what to say first and what to leave out* — it hands over a ranked list
and five charts, and the driver does the editing. That works for someone who
already reads telemetry; the whole external evidence in ``ROADMAP.md`` says it
does not work for everyone else, and it's the one thing the tool this was
modelled on does better than us.

So this is an editor, not an analyser. It re-orders and truncates
:class:`~accoach.coaching.debrief.LapDebrief` into a short sequence of steps,
each carrying the one chart that shows its point and the stretch of lap to zoom
it to. Every rule here is a decision about the driver's attention, and each one
is written down with its reason, because a rule about attention that nobody can
argue with is a rule nobody will fix.

Nothing here re-derives a number. If a step states a fact, that fact came from
the debrief — this module can drop a finding, never invent one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cue import CueCategory as _C
from .debrief import LapDebrief

# --- the editing rules -----------------------------------------------------

#: How many steps a flow may hold. Three is not a round number: it is the point
#: past which "one thing at a time" stops being true. A driver who is given
#: eight things to fix has been given a list, which is what the corner table
#: already is.
MAX_STEPS = 3

#: A flow that opens with the lap-wide theme is capped here instead. The theme
#: exists precisely because the gap is too big for corner-by-corner to be the
#: right lens (see ``debrief._headline``); following it with three corners would
#: contradict the sentence that was just said.
MAX_STEPS_WITH_HEADLINE = 2

#: Below this, a step is not worth a driver's attention. Four hundredths spread
#: over a corner is inside the noise of two laps driven by the same person, and
#: a step that says so teaches nothing while costing the reader a page.
MIN_STEP_MS = 60.0

#: How much lap to show around a corner, as a fraction of the lap. Asymmetric on
#: purpose: the debrief attributes the following straight's time to the corner
#: that caused it, so the exit is where the money is and it needs more room.
_PAD_BEFORE = 0.02
_PAD_AFTER = 0.05

#: Which trace actually shows the point being made. A step about the brake
#: release that opens a speed chart makes the reader do the translation.
_CHART = {
    _C.BRAKE_LATER: "inputs",
    _C.BRAKE_EARLIER: "inputs",
    _C.LESS_BRAKE: "inputs",
    _C.MORE_THROTTLE: "inputs",
    _C.CARRY_SPEED: "speed",
    _C.TIME_LOSS: "delta",
}
_NOTE_CHART = {"lift": "inputs", "top_speed": "speed"}

_STRINGS = {
    "it": {
        "headline": "Prima di tutto",
        "lapwide": "Sul giro intero",
        "clean": "Niente di grosso da correggere",
        "clean_body": "Su questo giro non c'è una perdita che valga una "
                      "correzione: le differenze col riferimento stanno dentro "
                      "la variazione fra due giri della stessa persona.",
        "reference_body": "Questo è il tuo giro di riferimento: non c'è niente "
                          "di più veloce con cui confrontarlo.",
    },
    "en": {
        "headline": "First, the big picture",
        "lapwide": "Across the whole lap",
        "clean": "Nothing big to fix",
        "clean_body": "There's no loss on this lap worth a correction: the "
                      "differences against the reference sit inside the spread "
                      "between two laps by the same driver.",
        "reference_body": "This is your reference lap — there's nothing faster "
                          "to compare it against.",
    },
}


@dataclass(slots=True)
class FlowStep:
    """One thing to understand, with the picture that shows it."""

    kind: str            # "headline" | "lapwide" | "corner" | "clean"
    title: str
    body: str            # what happened, in prose
    detail: str = ""     # the numbers that prove it
    fix: str = ""        # what to do about it
    lost_ms: float = 0.0
    where: str = ""      # corner name; "" when the finding is lap-wide
    chart: str = "delta"
    from_pos: float = 0.0
    to_pos: float = 1.0


def _window(entry: float, exit_: float) -> tuple[float, float]:
    return max(0.0, entry - _PAD_BEFORE), min(1.0, exit_ + _PAD_AFTER)


def _corner_step(loss) -> FlowStep:
    """Split the debrief's detail back into the *why* and the *numbers*.

    ``build_lap_debrief`` prepends the handling cause to ``detail`` because the
    text debrief prints one paragraph. Here they are two things — the sentence
    that explains, and the figures that prove it — and leaving the cause in both
    would say it twice on the same card.
    """
    detail = loss.detail.strip()
    if loss.cause and detail.startswith(loss.cause):
        detail = detail[len(loss.cause):].strip()

    lo, hi = _window(loss.entry_pos, loss.exit_pos)
    return FlowStep(
        kind="corner", title=loss.message, body=loss.cause, detail=detail,
        fix=loss.fix, lost_ms=loss.lost_ms, where=loss.label,
        chart=_CHART.get(loss.category, "delta"), from_pos=lo, to_pos=hi,
    )


def _note_step(note, s: dict) -> FlowStep:
    lo, hi = _window(note.pos, note.pos) if note.pos else (0.0, 1.0)
    return FlowStep(
        kind="lapwide", title=note.message, body="", detail=note.detail.strip(),
        lost_ms=note.lost_ms, where=note.where or s["lapwide"],
        chart=_NOTE_CHART.get(note.kind, "speed"), from_pos=lo, to_pos=hi,
    )


def build_flow(debrief: LapDebrief, lang: str = "it",
               max_steps: int = MAX_STEPS) -> list[FlowStep]:
    """Order and truncate a debrief into what to say, in what order.

    The order is not "biggest number first" throughout. Lap-wide findings come
    before corners even when a corner cost more, because a lift where the
    reference is flat and a top-speed deficit are facts the per-corner list
    structurally cannot express — the driver who fixes a corner while lifting on
    the back straight has fixed the smaller thing. That ordering is the one real
    coaches use, and the debrief's own code already says so.
    """
    s = _STRINGS.get(lang, _STRINGS["en"])

    if debrief.is_reference:
        return [FlowStep(kind="clean", title=s["clean"],
                         body=s["reference_body"])]

    steps: list[FlowStep] = []
    if debrief.headline:
        steps.append(FlowStep(kind="headline", title=s["headline"],
                              body=debrief.headline, chart="delta"))
        max_steps = min(max_steps, MAX_STEPS_WITH_HEADLINE)

    # Sorted here rather than trusted from the caller. `build_lap_debrief` does
    # sort its losses, but this module is the one that decides what the driver
    # reads first — inheriting that from an invariant maintained somewhere else
    # means a caller who builds a debrief by hand silently gets the wrong order.
    candidates = [_note_step(n, s) for n in
                  sorted(debrief.notes, key=lambda n: n.lost_ms, reverse=True)]
    candidates += [_corner_step(x) for x in
                   sorted(debrief.losses, key=lambda x: x.lost_ms, reverse=True)]

    worth_it = [c for c in candidates if c.lost_ms >= MIN_STEP_MS]
    if not worth_it and candidates:
        # Everything is small. Say the largest one anyway rather than claiming
        # the lap is clean: the driver asked what happened, and "nothing above
        # my threshold" is a different answer from "nothing".
        worth_it = [max(candidates, key=lambda c: c.lost_ms)]

    steps += worth_it
    if not steps:
        return [FlowStep(kind="clean", title=s["clean"], body=s["clean_body"])]
    return steps[:max_steps]
