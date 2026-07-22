"""Coaching cues — the discrete pieces of advice the coach can give.

A :class:`Cue` is one spoken suggestion ("brake later here", "more throttle on
exit"), carrying a ``priority`` (how much time the underlying mistake costs, in
ms) so the scheduler can speak the most valuable one when several pile up.

Messages are in Italian — that's the language spoken to the driver. The code and
comments stay English; only the user-facing phrases are localized. (A language
switch can live here later if needed.)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CueCategory(Enum):
    BRAKE_LATER = "brake_later"
    BRAKE_EARLIER = "brake_earlier"
    MORE_THROTTLE = "more_throttle"
    LESS_BRAKE = "less_brake"
    CARRY_SPEED = "carry_speed"
    TIME_LOSS = "time_loss"
    GOOD = "good"
    # Live events — detected from the current frame, no reference needed.
    LOCKED = "locked"
    WHEELSPIN = "wheelspin"
    UNDERSTEER = "understeer"
    OVERSTEER = "oversteer"
    COASTING = "coasting"
    TRAIL_BRAKE = "trail_brake"
    PARTIAL_THROTTLE = "partial_throttle"
    # In-car aid adjustments — suggested at lap end when a symptom recurs across
    # the lap (a knob to change on the straight, not a per-corner technique fix).
    TC_UP = "tc_up"
    ABS_UP = "abs_up"
    BRAKE_BIAS = "brake_bias"
    TYRE_PRESSURE = "tyre_pressure"
    TYRE_TEMP = "tyre_temp"
    LIMITER = "limiter"
    GEAR_TOO_TALL = "gear_too_tall"
    FUEL = "fuel"


class CueTier:
    """Coarse urgency bands. The scheduler sorts by ``(tier, priority)`` so a big
    computed time-loss can't outrank an acute safety call: ``priority`` only ever
    breaks ties *within* a tier, never across them.

    Mixing scales was the bug this fixes — corner cues carry ``priority`` in raw
    ms (0..1000+) while the live detectors use small fixed importances (~235-300),
    so without tiers a 0.4 s corner loss outranked a lock-up.
    """

    ADVISORY = 0      # between-laps setup / strategy info: pressures, temps, aids
    TECHNIQUE = 1     # how to drive: corner deltas, gears, braking technique
    ACUTE = 2         # fix-it-now faults + time-critical warnings


# Categories not listed default to TECHNIQUE (the safe middle).
_TIER: dict["CueCategory", int] = {}


def _init_tiers() -> None:
    acute = {
        CueCategory.LOCKED, CueCategory.WHEELSPIN,
        CueCategory.UNDERSTEER, CueCategory.OVERSTEER,
        CueCategory.FUEL,
    }
    advisory = {
        CueCategory.TC_UP, CueCategory.ABS_UP, CueCategory.BRAKE_BIAS,
        CueCategory.TYRE_PRESSURE, CueCategory.TYRE_TEMP,
    }
    for c in acute:
        _TIER[c] = CueTier.ACUTE
    for c in advisory:
        _TIER[c] = CueTier.ADVISORY


_init_tiers()


def tier_of(category: "CueCategory") -> int:
    return _TIER.get(category, CueTier.TECHNIQUE)


@dataclass(slots=True)
class Cue:
    """One coaching suggestion tied to a place on the track."""

    category: CueCategory
    message: str
    priority: float       # ms of time loss this addresses (higher = more urgent)
    segment: int          # which track segment it refers to
    pos: float            # normalized position where it was generated

    @property
    def tier(self) -> int:
        """Urgency band used as the primary scheduling sort key."""
        return tier_of(self.category)

    def rank(self) -> tuple[int, float]:
        """Scheduling key: tier first, then priority within the tier."""
        return (self.tier, self.priority)

    def dedup_key(self) -> tuple:
        """Same category in the same segment is 'the same advice'."""
        return (self.category, self.segment)
