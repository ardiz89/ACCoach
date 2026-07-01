"""Race-engineer fuel tracking — burn rate and laps remaining.

The driving coaches watch how you drive; this wears the engineer's hat and watches
the fuel load. Each completed lap it measures how much fuel that lap burned,
keeps a short rolling average of the burn rate, and from the fuel still in the
tank works out how many laps are left — calling out a warning as that number
drops to the last few laps, the same information a real engineer gives over the
radio ("two laps of fuel", "last lap, box this lap").

It runs off ``fuel`` plus the lap wrap, ignores laps that involved the pits, and
resets its warnings when it sees the tank go back up (a refuel), so a stop during
a stint doesn't leave it either silent or crying wolf.
"""

from __future__ import annotations

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory

# A per-lap burn outside this band is a glitch (or a refuel/pit lap), not a real
# measurement — don't let it poison the rolling average.
_PLAUSIBLE_BURN_L = (0.3, 20.0)
_AVG_WINDOW = 3             # laps of burn rate to average over
_REFUEL_EPS = 0.5          # tank rising by more than this = a refuel happened

# Warn as the remaining-laps estimate drops past each of these (once each).
_WARN_LAPS = (3, 2, 1)
_MIN_LAP_SPAN = 0.7
_PRIORITY = 290.0          # strategic and time-critical: cuts above most cues


class FuelEngineer:
    """Stateful: fed (snapshot, now) each frame; yields fuel warnings at the line."""

    def __init__(self) -> None:
        self._burns: list[float] = []          # recent per-lap burn, newest last
        self._lap_start_fuel = -1.0
        self._warned: set[int] = set()         # which _WARN_LAPS thresholds spoken
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._prev_pos = -1.0
        self._pit_this_lap = False

    def reset(self) -> None:
        self.__init__()

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE):
            return []

        pos = s.lap_position
        cues = self._maybe_close_lap(s, pos)

        if s.in_pit:
            self._pit_this_lap = True
        self._pos_min = min(self._pos_min, pos)
        self._pos_max = max(self._pos_max, pos)
        self._prev_pos = pos
        return cues

    # --- lap boundary -----------------------------------------------------
    def _maybe_close_lap(self, s: TelemetrySnapshot, pos: float) -> list[Cue]:
        crossed = self._prev_pos > 0.7 and pos < 0.3
        if not crossed:
            return []

        fuel = s.fuel
        cues: list[Cue] = []

        # A refuel (tank went up) invalidates the stint's warnings and baseline.
        if self._lap_start_fuel >= 0.0 and fuel > self._lap_start_fuel + _REFUEL_EPS:
            self._warned.clear()
            self._lap_start_fuel = fuel
        elif self._lap_start_fuel >= 0.0:
            full_lap = (self._pos_max - self._pos_min) >= _MIN_LAP_SPAN
            burn = self._lap_start_fuel - fuel
            if full_lap and not self._pit_this_lap and _PLAUSIBLE_BURN_L[0] <= burn <= _PLAUSIBLE_BURN_L[1]:
                self._burns.append(burn)
                del self._burns[:-_AVG_WINDOW]
                cues = self._check_warnings(fuel)
            self._lap_start_fuel = fuel
        else:
            self._lap_start_fuel = fuel          # first crossing: set baseline

        self._reset_lap_window()
        return cues

    def _check_warnings(self, fuel: float) -> list[Cue]:
        if not self._burns:
            return []
        per_lap = sum(self._burns) / len(self._burns)
        if per_lap <= 0.0:
            return []
        remaining = fuel / per_lap

        # Fire the tightest threshold the estimate has dropped to, once.
        for thresh in sorted(_WARN_LAPS):          # 1, 2, 3
            if remaining <= thresh and thresh not in self._warned:
                self._warned.add(thresh)
                if thresh <= 1:
                    msg = "Ultimo giro di benzina, rientra ai box!"
                else:
                    # Report whole laps you can actually finish (floor), not the
                    # threshold band's upper bound: at 2.5 laps left the tank is
                    # good for ~2 laps, not 3 — overstating risks running dry.
                    laps_left = int(remaining)
                    unit = "giro" if laps_left == 1 else "giri"
                    msg = f"Benzina per circa {laps_left} {unit}."
                return [Cue(category=CueCategory.FUEL, message=msg,
                            priority=_PRIORITY, segment=0, pos=0.0)]
        return []

    def _reset_lap_window(self) -> None:
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._prev_pos = -1.0
        self._pit_this_lap = False
