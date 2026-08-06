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


@dataclass(slots=True)
class CornerSplit:
    """One corner's loss and the four stretches it is made of."""

    index: int
    lost_ms: float
    phases: list[PhaseLoss]


@dataclass(slots=True)
class LapSplit:
    """Where a whole lap's gap went, in parts that add back up to it."""

    # From the first sample (a hair after the line, ~pos 0.003 on a real lap)
    # to the first corner's entry_pos (which already reaches back over that
    # corner's braking zone) — the stretch no corner claims.
    launch_ms: float
    corners: list[CornerSplit]
    # delta at the last sample minus delta at the first, NOT the gap the
    # cockpit clock publishes (lap_time - reference_time): first and last
    # sample don't sit on the start/finish line, so on real laps the two
    # differ by more than a tenth (measured: from -123 ms to +100 ms across a
    # small sample of real laps). This is the number the parts of this split
    # add back up to; the published lap-time gap is a different, looser
    # question and callers must not conflate the two labels on screen.
    #
    # A note for whoever next needs a fixture with a genuinely fractional
    # value to catch a reintroduced round(): unlike the internal cuts (entry /
    # apex- / apex+ / exit), gap_ms is read at samples[0] and samples[-1]
    # against Reference.time_at(pos=0.0) / time_at(pos=1.0) — and Reference
    # pins those two positions EXACTLY (t=0 and t=lap_time_ms, see
    # ``Reference._anchor_endpoints``), regardless of the reference's own
    # sampling grid. Mismatching the reference's ``n`` against the lap's (the
    # trick that makes the interior cuts fractional) does nothing here: the
    # endpoints never interpolate, so gap_ms — and any average taken over
    # several gap_ms values — stays suspiciously round-number-friendly even
    # off-grid. A fixture meant to defeat rounding on gap_ms (or on an
    # average of it) needs sample counts/offsets that make the underlying lap
    # times themselves not divide evenly, not a grid mismatch.
    gap_ms: float

    def by_phase(self) -> dict[str, float]:
        """Totals per phase across every corner of the lap."""
        out = {p: 0.0 for p in PHASES}
        for c in self.corners:
            for p in c.phases:
                out[p.phase] += p.lost_ms
        return out


def lap_time_split(lap, reference, corners) -> LapSplit | None:
    """Cut a whole lap into stretches whose losses add back up to its gap.

    The debrief measures a corner over ``entry <= pos < next entry``, so two
    consecutive windows do NOT share a sample: telescoping across them leaves
    one sampling interval out per corner. Close enough to look right and not
    close enough to be true, which is the worst kind of number.

    So the cuts are computed once for the whole lap — start, then entry /
    apex- / apex+ / exit for every corner, then the lap's end — mapped to
    sample indices that only ever move forward, and every stretch ENDS on the
    index the next one STARTS from. Then the sum telescopes to
    ``delta(last) - delta(first)`` by construction, and that is what ``gap_ms``
    is: measured the same way as its own parts, not borrowed from the lap time.

    Unlike the debrief this keeps **every** corner, including the ones taken
    well. A corner that cost nothing contributes 0.0 — leaving it out is what
    would make the sum stop adding up.
    """
    samples = lap.samples
    if len(samples) < 4 or not corners:
        return None
    positions = [s.pos for s in samples]
    ordered = sorted(corners, key=lambda c: (c.entry_pos, c.exit_pos, c.apex_pos))

    cuts = [positions[0]]
    for c in ordered:
        cuts += [c.entry_pos, c.apex_pos - _APEX_HALF,
                 c.apex_pos + _APEX_HALF, c.exit_pos]
    cuts.append(positions[-1])

    edges: list[int] = []
    for p in cuts:
        p = min(max(p, positions[0]), positions[-1])
        i = min(len(samples) - 1, max(0, bisect.bisect_left(positions, p)))
        edges.append(i if not edges else max(i, edges[-1]))

    delta = [samples[i].t_ms - reference.time_at(samples[i].pos) for i in edges]

    out: list[CornerSplit] = []
    for k, c in enumerate(ordered):
        base = 1 + 4 * k                     # entry / apex- / apex+ / exit
        # "after" runs to the NEXT corner's entry, or to the lap's end for the
        # last one — the same rule the debrief uses, so a poor exit is charged
        # to the corner that caused it.
        end = base + 4 if k + 1 < len(ordered) else len(edges) - 1
        bounds = [base, base + 1, base + 2, base + 3, end]
        phases = [PhaseLoss(phase=name, lost_ms=delta[b] - delta[a])
                  for name, a, b in zip(PHASES, bounds, bounds[1:])]
        out.append(CornerSplit(index=c.index,
                               lost_ms=delta[end] - delta[base],
                               phases=phases))

    # Not rounded: rounding each part independently (and gap_ms separately)
    # would let the sum drift off gap_ms by up to 0.05 ms per rounded value —
    # measured up to ~0.3 ms on a real 10-corner lap. Full floats keep the
    # telescope exact; rounding is a presentation decision for whoever
    # serializes this at the boundary.
    return LapSplit(launch_ms=delta[1] - delta[0],
                    corners=out,
                    gap_ms=delta[-1] - delta[0])
