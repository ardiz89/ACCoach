"""Gear-selection coaching — bouncing the limiter and lugging too tall a gear.

Two absolute, reference-free shift faults, read from ``rpm`` / ``max_rpm`` /
``gear`` / ``throttle``:

* **Limiter bounce** — sitting pinned on the rev limiter under power when a taller
  gear is available, i.e. shifting up too late. The trap is that running flat-out
  in *top* gear also sits near the limiter and is perfectly correct, so we only
  flag it when the current gear is **below the tallest gear we've seen** this
  session — there's an upshift left to take.

* **Too tall a gear** — hard on the throttle at very low revs, the engine
  lugging out of a corner: you should be a gear lower for the drive. Gated to
  real gears (2nd+) and on-track speeds so standing starts and pit exits don't
  trip it.

Same debounce / one-shot / dedup-by-segment contract as the other live detectors.
The bog threshold (``_BOG_FRAC``) is engine-dependent and conservative — tune it
against a live session if a car's powerband sits unusually low.
"""

from __future__ import annotations

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from ._detector import Episode, make_cue, step
from .cue import Cue, CueCategory

_ON_POWER = 0.85           # throttle that counts as "under power"

# Limiter bounce.
_LIMITER_FRAC = 0.99       # rpm/max_rpm at/above which we're on the limiter

# Lugging too tall a gear.
_BOG_FRAC = 0.42           # rpm/max_rpm below which the engine is bogged
_BOG_MIN_SPEED = 40.0      # above a standing start
_BOG_MAX_SPEED = 170.0     # a corner exit, not a top-gear straight

_MIN_HOLD_S = 0.30
_PRIORITY = 260.0


def _gear_num(gear: str) -> int | None:
    """Numeric drive gear (1..), or None for reverse/neutral."""
    return int(gear) if gear.isdigit() and gear != "0" else None


class GearDetector:
    """Stateful: fed (snapshot, now) each frame, yields gear-selection cues."""

    def __init__(self) -> None:
        self._limiter = Episode()
        self._bog = Episode()
        self._max_gear_seen = 1

    def reset(self) -> None:
        self._limiter = Episode()
        self._bog = Episode()
        # Keep _max_gear_seen: it's a property of the car, not the lap.

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self._limiter.active = False
            self._bog.active = False
            return []

        gear = _gear_num(s.gear)
        if gear is not None:
            self._max_gear_seen = max(self._max_gear_seen, gear)

        cues: list[Cue] = []
        if step(self._limiter, self._is_limiter(s, gear), now, _MIN_HOLD_S):
            cues.append(make_cue(s, CueCategory.LIMITER,
                                 "Sei sul limitatore, cambia prima", _PRIORITY))
        if step(self._bog, self._is_bogged(s, gear), now, _MIN_HOLD_S):
            cues.append(make_cue(s, CueCategory.GEAR_TOO_TALL,
                                 "Marcia troppo lunga, scala per avere più spinta", _PRIORITY))
        return cues

    # --- conditions -------------------------------------------------------
    def _is_limiter(self, s: TelemetrySnapshot, gear: int | None) -> bool:
        if gear is None or s.throttle < _ON_POWER or s.max_rpm <= 0:
            return False
        # Only when a taller gear exists (don't nag flat-out in top gear).
        if gear >= self._max_gear_seen:
            return False
        return s.rpm >= _LIMITER_FRAC * s.max_rpm

    @staticmethod
    def _is_bogged(s: TelemetrySnapshot, gear: int | None) -> bool:
        if gear is None or gear < 2 or s.throttle < _ON_POWER or s.max_rpm <= 0:
            return False
        if not (_BOG_MIN_SPEED <= s.speed_kmh <= _BOG_MAX_SPEED):
            return False
        return s.rpm <= _BOG_FRAC * s.max_rpm
