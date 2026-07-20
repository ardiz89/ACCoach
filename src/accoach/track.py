"""Detect the corners of a track from a reference lap.

The coaching analyzer reasons far better about *corners* than about equal-length
slices: a corner has a braking zone, an apex and an exit, and a mistake belongs
to one of those phases. Equal `pos` bins blur all of that together. So we derive
the real corners once, from the reference lap, and let the analyzer accumulate
per corner.

Detection is deliberately dependency-light (no numpy):

1. A **corner** is a stretch where the car is steering — a contiguous run where
   smoothed ``|steer_angle|`` stays above a threshold (with hysteresis so it
   doesn't flicker). Nearby runs are merged (chicanes / steering wobble).
2. Its **apex** is the speed minimum inside that run.
3. The boundary is then **extended back over the braking zone** (so "brake
   later" can be judged) and **forward over the exit** (so "more throttle on
   exit" can be judged), within small caps.

Corners straddling the start/finish line are uncommon (the line is normally on a
straight). We don't model a corner as wrapping across the line (its position
span stays within [0,1]); instead the trailing half is kept as a normal corner
(its exit just truncates at the line) and the spurious exit-only stub that the
*next* lap's start would add is suppressed, so it can't inject a phantom corner
and shift every corner's number by one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .recording.lap import strip_leading_wrap

# Tuning (all in normalized-position / steering-radian units).
_STEER_ON = 0.08        # |steer| (rad) that starts a corner
_STEER_OFF = 0.05       # drop below this to end it (hysteresis)
_MIN_GAP = 0.012        # merge corners closer than this in pos
_MIN_LEN = 0.006        # discard corners shorter than this in pos
_SMOOTH = 5             # moving-average window (samples)
_BRAKE_TRAIL = 0.12     # brake fraction that still counts as "braking into it"
_MAX_ENTRY_EXT = 0.06   # cap how far back the braking zone extends (pos)
_MAX_EXIT_EXT = 0.04    # cap how far forward the exit extends (pos)


@dataclass(slots=True)
class Corner:
    """One detected corner as a span of normalized track position."""

    index: int
    entry_pos: float    # start of braking / turn-in
    apex_pos: float     # speed minimum
    exit_pos: float     # throttle restored / steering unwound
    name: str = ""

    @property
    def mid(self) -> float:
        return self.apex_pos

    def contains(self, pos: float) -> bool:
        return self.entry_pos <= pos <= self.exit_pos


def _smooth(xs: list[float], w: int) -> list[float]:
    if w <= 1 or len(xs) < w:
        return list(xs)
    half = w // 2
    n = len(xs)
    out = []
    for i in range(n):
        a = max(0, i - half)
        b = min(n, i + half + 1)
        out.append(sum(xs[a:b]) / (b - a))
    return out


def detect_corners(samples) -> list[Corner]:
    """Find the corners in a reference lap's samples (ordered by position)."""
    pos: list[float] = []
    spd: list[float] = []
    steer: list[float] = []
    brake: list[float] = []
    thr: list[float] = []
    last = -1.0
    for s in strip_leading_wrap(samples):
        if s.pos <= last:
            continue
        last = s.pos
        pos.append(s.pos)
        spd.append(s.speed_kmh)
        steer.append(abs(s.steer_angle))
        brake.append(s.brake)
        thr.append(s.throttle)

    n = len(pos)
    if n < 10:
        return []

    asteer = _smooth(steer, _SMOOTH)
    aspd = _smooth(spd, _SMOOTH)

    # 1) cornering runs via |steer| with hysteresis
    runs: list[list[int]] = []
    in_run = False
    start = 0
    for i in range(n):
        if not in_run and asteer[i] >= _STEER_ON:
            in_run = True
            start = i
        elif in_run and asteer[i] < _STEER_OFF:
            in_run = False
            runs.append([start, i - 1])
    if in_run:
        runs.append([start, n - 1])

    # 2) merge runs separated by a small gap
    merged: list[list[int]] = []
    for r in runs:
        if merged and pos[r[0]] - pos[merged[-1][1]] < _MIN_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    corners: list[Corner] = []
    for a, b in merged:
        if pos[b] - pos[a] < _MIN_LEN:
            continue

        # apex = speed minimum within the run
        apex = a
        for k in range(a, b + 1):
            if aspd[k] < aspd[apex]:
                apex = k

        # A run pinned to the lap start (a==0) whose speed only rises (apex at the
        # very first sample) and that carries no braking is not a corner of its
        # own: it's the exit tail of a corner straddling start/finish, whose entry
        # and apex live at the END of the lap (kept as the final corner). Keeping
        # it would inject a phantom "corner 0" and renumber every corner. Drop it.
        # No-op when s/f is on a straight (no cornering run at pos≈0).
        if a == 0 and apex == a and max(brake[a:b + 1]) < _BRAKE_TRAIL:
            continue

        # 3) extend entry back over the braking zone
        e = a
        while e > 0 and brake[e - 1] >= _BRAKE_TRAIL and \
                pos[a] - pos[e - 1] <= _MAX_ENTRY_EXT:
            e -= 1
        # extend exit forward until throttle is restored
        x = b
        while x < n - 1 and thr[x + 1] < 0.95 and \
                pos[x + 1] - pos[b] <= _MAX_EXIT_EXT:
            x += 1

        corners.append(Corner(
            index=len(corners),
            entry_pos=pos[e],
            apex_pos=pos[apex],
            exit_pos=pos[x],
        ))

    return corners
