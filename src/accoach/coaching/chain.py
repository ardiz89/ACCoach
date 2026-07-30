"""When a corner's loss was not made in that corner.

The per-corner list answers "where did the time go" and, read literally, sends
the driver to work on the corner with the biggest number. Sometimes that is the
wrong place: you are three tenths down through turn 4 because you arrived there
six km/h slow, and you arrived slow because of turn 3. Fix turn 4 and you fix
nothing; fix turn 3 and turn 4 comes with it.

This module names that link — and, much more importantly, refuses to name it
when the evidence isn't there. **An invented chain is worse than no chain**: it
sends the driver to work on a corner that was fine, and it does it in the
confident voice of a diagnosis. So the rule is written as a set of reasons to
stay quiet:

* the arrival deficit is small — under a few km/h we are inside one driver's own
  lap-to-lap repeatability, which we measure elsewhere and know is not zero;
* the previous corner handed you nothing — you left it on the reference's pace;
* the deficit was created *between* the two corners (a lift, a bad shift on the
  straight): then the previous corner is not the cause, and the debrief's own
  lap-wide findings already own that case;
* either corner's time loss is below the floor the whole debrief uses — a chain
  between two non-events is a sentence about nothing;
* you left the previous corner *faster* than the reference: whatever happened
  next, it wasn't inherited.

Only speed is followed from one corner to the next, because speed is the thing
that physically carries: leave slower, arrive slower, all the way down whatever
sits in between. Nothing here estimates how many tenths were "transferred" — a
number like that needs a model of the straight we don't have, and the honest
statement doesn't need it. The km/h and where they came from are the finding.

Report-only for now, deliberately: the live coach speaks before a corner, and
"the fix is in the previous one" is advice that has to survive a session on
track before it is spoken out loud (ROADMAP: no new cue on unvalidated rules).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from .analyzer import _LOSS_MS

# Below this the arrival is not meaningfully slower. Corner speeds are reported
# to the whole km/h, and the spread of one driver's own min speed across a
# handful of laps — which the report measures per corner — runs to several km/h
# on a normal corner. Linking under that would be linking noise.
_MIN_ARRIVAL_DV = 3.0
# The previous corner has to have actually handed something over.
_MIN_CARRIED_DV = 2.0
# How much of the arrival deficit must already have existed at the previous
# corner's exit. Under this, most of it was made in between — on the straight,
# not in the corner — and blaming the corner would be a confident wrong answer.
_MIN_SHARE = 0.6


@dataclass(slots=True)
class ChainLink:
    """One corner's loss, traced back to the corner before it."""

    index: int              # the corner that shows the loss
    from_index: int         # the corner it was inherited from
    arrival_dv: float       # km/h down at this corner's entry (positive number)
    carried_dv: float       # km/h down already at the previous corner's exit
    share: float            # 0..1 — how much of the arrival deficit was inherited
    message: str = ""


_STRINGS = {
    "it": {
        "all": "Ci arrivi già {dv} km/h sotto, e li avevi tutti all'uscita di "
               "{prev}: qui il tempo lo perdi prima di arrivarci.",
        "most": "Ci arrivi già {dv} km/h sotto, e quasi tutti li avevi "
                "all'uscita di {prev}: lavora prima su quella.",
        "corner": "Curva {n}",
    },
    "en": {
        "all": "You arrive {dv} km/h down, and all of it was already there at "
               "{prev}'s exit — the time here is lost before you get here.",
        "most": "You arrive {dv} km/h down, and most of it was already there at "
                "{prev}'s exit — work on that one first.",
        "corner": "Corner {n}",
    },
}


def _label(loss, lang: str) -> str:
    """The previous corner's name, taken from its own finding.

    Not looked up again: ``build_lap_debrief`` already resolved every corner's
    curated name onto its loss, and a second lookup here is a second chance to
    call the same corner two different things on one page.
    """
    label = getattr(loss, "label", "") or ""
    if label:
        return label
    s = _STRINGS.get(lang, _STRINGS["en"])
    return s["corner"].format(n=loss.index + 1)


def _speed_at(samples, positions: list[float], pos: float) -> float | None:
    """Speed (km/h) of a lap at a track position, or None if it never got there."""
    if not positions:
        return None
    i = bisect.bisect_left(positions, pos)
    if i >= len(positions):
        i = len(positions) - 1
    if i > 0 and abs(positions[i - 1] - pos) < abs(positions[i] - pos):
        i -= 1
    return samples[i].speed_kmh


def link_corners(lap, reference, corners, losses, lang: str = "it") -> list[ChainLink]:
    """Which corner losses were inherited from the corner before them.

    ``losses`` are the debrief's own, so the floors and the windowing rule stay
    in one place. Returns at most one link per corner, and none at all for the
    first corner of the lap: its predecessor is on the previous lap, which we did
    not measure and will not guess at.
    """
    by_index = {l.index: l for l in losses}
    if not by_index or len(corners) < 2:
        return []

    samples = [s for s in lap.samples]
    positions = [s.pos for s in samples]
    out: list[ChainLink] = []

    for prev, cur in zip(corners, corners[1:]):
        loss = by_index.get(cur.index)
        prev_loss = by_index.get(prev.index)
        # Both ends have to be real: a chain drawn between two corners that each
        # cost nothing is a sentence about nothing.
        if loss is None or prev_loss is None:
            continue
        if loss.lost_ms < _LOSS_MS or prev_loss.lost_ms < _LOSS_MS:
            continue

        you_entry = _speed_at(samples, positions, cur.entry_pos)
        you_exit = _speed_at(samples, positions, prev.exit_pos)
        if you_entry is None or you_exit is None:
            continue
        ref_entry = reference.point_at(cur.entry_pos).speed_kmh
        ref_exit = reference.point_at(prev.exit_pos).speed_kmh

        arrival = ref_entry - you_entry          # + = you arrive slower
        carried = ref_exit - you_exit            # + = you left slower
        if arrival < _MIN_ARRIVAL_DV:
            continue                             # you don't arrive meaningfully down
        if carried < _MIN_CARRIED_DV:
            continue                             # the corner before handed you nothing
        share = min(carried, arrival) / arrival
        if share < _MIN_SHARE:
            continue                             # made in between, not in the corner

        s = _STRINGS.get(lang, _STRINGS["en"])
        out.append(ChainLink(
            index=cur.index, from_index=prev.index,
            arrival_dv=round(arrival, 1), carried_dv=round(carried, 1),
            share=round(share, 2),
            message=s["all" if share >= 0.9 else "most"].format(
                dv=round(arrival), prev=_label(prev_loss, lang)),
        ))
    return out
