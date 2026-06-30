"""Shared debounce + cue-emission helpers for the live detectors.

``events`` / ``balance`` / ``braking`` / ``gears`` each watch one or two
conditions per frame and must (a) only fire once a condition has held for a
short, detector-specific time, and (b) emit a Cue tagged with where on the lap
it happened (so the scheduler can de-duplicate by location). That episode
bookkeeping was copied verbatim into all four detectors; it lives here once so
the contract can't quietly drift between them.

Each detector keeps its OWN tuning (hold time, priority) and passes it in — only
the mechanism is shared.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..telemetry.snapshot import TelemetrySnapshot
from .cue import Cue, CueCategory

_SEGMENTS = 20   # granularity for de-duplicating a cue by track location


@dataclass(slots=True)
class Episode:
    """One watched condition: whether we're in it, since when, and if we fired."""

    active: bool = False
    since: float = 0.0
    fired: bool = False


def step(ep: Episode, cond: bool, now: float, hold_s: float) -> bool:
    """Advance an episode; return True exactly once, when ``cond`` has held for
    ``hold_s`` seconds. Re-arms as soon as the condition clears."""
    if cond:
        if not ep.active:
            ep.active = True
            ep.since = now
            ep.fired = False
        elif not ep.fired and now - ep.since >= hold_s:
            ep.fired = True
            return True
    else:
        ep.active = False
    return False


def make_cue(s: TelemetrySnapshot, category: CueCategory, message: str,
             priority: float, segments: int = _SEGMENTS) -> Cue:
    """A Cue tagged with the track segment it occurred in (for de-duplication)."""
    seg = min(segments - 1, max(0, int(s.lap_position * segments)))
    return Cue(category=category, message=message,
               priority=priority, segment=seg, pos=s.lap_position)
