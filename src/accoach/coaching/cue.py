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
    # Pit strategy — not about how you drive, about where you are on the lap.
    PIT_IN = "pit_in"                 # come in: a garage change is waiting
    # Its own category and not a second PIT_IN, which is what it was for half a
    # day. `dedup_key` is (category, segment), so sharing both made the approach
    # a repeat of the call: suppressed for 20 s, then dropped as stale. Measured
    # consequence — on the lead path the two are exactly 15 s apart, so the
    # warning that exists to stop you missing the entry was spoken *at* the
    # entry, or never.
    PIT_APPROACH = "pit_approach"     # the pit entry is right there
    PIT_BRIEFING = "pit_briefing"     # you're stopped: here's what to do with it


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
        # Time-critical rather than a fault: said late, the pit entry is behind
        # you and the change costs another lap. Same band as FUEL, and for the
        # same reason — both are "act now or lose the chance".
        CueCategory.PIT_IN, CueCategory.PIT_APPROACH,
    }
    advisory = {
        CueCategory.TC_UP, CueCategory.ABS_UP, CueCategory.BRAKE_BIAS,
        CueCategory.TYRE_PRESSURE, CueCategory.TYRE_TEMP,
        # Spoken standing still in the garage: nothing competes with it there.
        CueCategory.PIT_BRIEFING,
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


# The theme a cue belongs to — the unit a coaching session is organised around.
# It lives here, next to the category, because two readers need it (the debrief
# headline and the voice gate) and a second copy would be free to disagree.
#
# The English key is the one that travels between modules; the localized label is
# only ever shown. A comparison that changed outcome with the interface language
# would be a defect invisible in Italian and visible only in English.
THEME: dict[CueCategory, dict[str, str]] = {
    CueCategory.BRAKE_LATER: {"en": "braking", "it": "frenata"},
    CueCategory.BRAKE_EARLIER: {"en": "braking", "it": "frenata"},
    CueCategory.LESS_BRAKE: {"en": "braking", "it": "frenata"},
    CueCategory.TRAIL_BRAKE: {"en": "braking", "it": "frenata"},
    CueCategory.MORE_THROTTLE: {"en": "traction", "it": "trazione"},
    CueCategory.PARTIAL_THROTTLE: {"en": "traction", "it": "trazione"},
    CueCategory.COASTING: {"en": "traction", "it": "trazione"},
    CueCategory.CARRY_SPEED: {"en": "cornering", "it": "percorrenza"},
    CueCategory.TIME_LOSS: {"en": "line", "it": "linea"},
    CueCategory.LIMITER: {"en": "gears", "it": "marce"},
    CueCategory.GEAR_TOO_TALL: {"en": "gears", "it": "marce"},
}
THEME_DEFAULT: dict[str, str] = {"en": "driving", "it": "guida"}


def theme_key(category: CueCategory) -> str:
    """The English theme key, for aggregation and comparison across modules."""
    return THEME.get(category, THEME_DEFAULT)["en"]


def theme_label(category: CueCategory, lang: str) -> str:
    """The theme as shown to the driver, in ``lang`` (falls back to English)."""
    entry = THEME.get(category, THEME_DEFAULT)
    return entry.get(lang) or entry["en"]
