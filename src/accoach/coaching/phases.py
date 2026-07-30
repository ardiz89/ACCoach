"""Where *inside* a corner the time went.

The debrief says "Turn 4 cost you three tenths" and names what the car was doing
(understeer at the apex, in a slow corner). What it never said is *which part of
the corner the clock ran in* — and those are different questions with different
answers: you can push at the apex because you arrived too fast and threw the
entry away, and the fix is a hundred metres before the place the symptom shows.

The split is a **decomposition, not an estimate**. Time lost across a stretch is
how the gap to the reference grew from one end of it to the other, so cutting the
corner's window into four contiguous stretches and measuring each the same way
gives four numbers that add back up to the corner's own loss, exactly. That is
the property worth having, and it is what the tests pin.

The four stretches, and why the boundaries are those:

* **entry** — from where the corner's window opens (which already reaches back
  over the braking zone) to the apex window;
* **apex** — the same ±0.02 of track either side of the apex that the symptom
  diagnosis calls "at the apex", imported from there so one word means one place;
* **exit** — from the apex window to where the corner ends;
* **after** — from the corner's end to the next corner's entry. Not padding: the
  debrief deliberately credits the following straight to the corner that set the
  exit speed, so that time is already inside the number being split, and leaving
  it unnamed would make the other three fail to add up. A poor exit shows up
  here, which is exactly where a driver feels it.

Signs are kept. A phase where you were *quicker* than the reference reads as a
negative loss, because "you lose four tenths on entry and take one back on exit"
is a truer sentence than "you lose three tenths somewhere".
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from .diagnosis import _APEX_HALF
from .thresholds import SIGNIF_LOSS_MS

#: A phase has to hold this much of the corner's loss before the report will
#: name it. Below it nothing dominates: the time is spread around the corner,
#: and pointing at one part would send the driver to a place that isn't the
#: place.
_DOMINANT_SHARE = 0.4

#: Time taken back in one phase worth mentioning alongside the loss. Half a
#: tenth is the smallest gain that survives one driver's own lap-to-lap spread.
_GAIN_MS = 50.0

PHASES = ("entry", "apex", "exit", "after")

_WORDS = {
    "it": {"entry": "in ingresso", "apex": "all'apex", "exit": "in uscita",
           "after": "nel tratto dopo",
           "most": "Di questi, {s}s {phase}.",
           "gain": " Ne recuperi {s}s {phase}."},
    "en": {"entry": "on entry", "apex": "at the apex", "exit": "on exit",
           "after": "on the run after",
           "most": "Of that, {s}s {phase}.",
           "gain": " You take {s}s back {phase}."},
}


@dataclass(slots=True)
class PhaseLoss:
    """One stretch of a corner and the time the clock ran there."""

    phase: str          # one of PHASES
    lost_ms: float      # + = lost here, - = gained here


def _delta_at(sample, reference) -> float:
    """How far behind the reference this lap was at one sample."""
    return sample.t_ms - reference.time_at(sample.pos)


def split_loss(window, reference, corner) -> list[PhaseLoss]:
    """Cut a corner's loss into its four stretches.

    ``window`` is the corner's own loss window — entry to the next corner's
    entry — as the debrief built it, so the parts add up to the number the
    debrief published. Returns [] when the window is too short to cut.
    """
    if len(window) < 4:
        return []
    positions = [s.pos for s in window]
    first, last = window[0], window[-1]

    cuts = [first.pos,
            corner.apex_pos - _APEX_HALF,
            corner.apex_pos + _APEX_HALF,
            corner.exit_pos,
            last.pos]
    # Monotonic and inside the window: a corner whose apex sits at the very edge
    # (or a window that ends before the corner does) must not produce a stretch
    # that runs backwards.
    edges: list[int] = []
    for c in cuts:
        c = min(max(c, first.pos), last.pos)
        i = bisect.bisect_left(positions, c)
        i = min(len(window) - 1, max(0, i))
        edges.append(i if not edges else max(i, edges[-1]))

    out: list[PhaseLoss] = []
    for name, a, b in zip(PHASES, edges, edges[1:]):
        # Zero-length stretches stay in the list on purpose: a corner where you
        # never reached the apex window is a corner with a 0.0 apex phase, not a
        # corner with three phases and a reader left to wonder which is missing.
        lost = 0.0 if a == b else (_delta_at(window[b], reference)
                                   - _delta_at(window[a], reference))
        out.append(PhaseLoss(phase=name, lost_ms=round(lost, 1)))
    return out


def phase_note(phases: list[PhaseLoss], lost_ms: float,
               lang: str = "it") -> str:
    """One sentence naming where in the corner the time actually went.

    Empty when the corner didn't cost enough to talk about, or when no single
    stretch dominates — a corner that leaks a little everywhere is a corner
    whose answer is "everywhere", and dressing that up as a location would be a
    confident wrong answer.
    """
    if not phases or lost_ms < SIGNIF_LOSS_MS:
        return ""
    w = _WORDS.get(lang, _WORDS["en"])
    worst = max(phases, key=lambda p: p.lost_ms)
    if worst.lost_ms <= 0 or worst.lost_ms < _DOMINANT_SHARE * lost_ms:
        return ""
    text = w["most"].format(s=f"{worst.lost_ms / 1000.0:.2f}", phase=w[worst.phase])

    best = min(phases, key=lambda p: p.lost_ms)
    if best.lost_ms <= -_GAIN_MS:
        text += w["gain"].format(s=f"{abs(best.lost_ms) / 1000.0:.2f}",
                                 phase=w[best.phase])
    return text
