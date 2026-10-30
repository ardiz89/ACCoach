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

import math
import statistics

from ..telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot
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
_MARGIN_LAPS = 1           # un giro di scorta: il rientro non e' un giro di passo
_LITRES_STEP = 5           # la voce dice multipli di 5, sempre per eccesso
LITRES_SAID = range(_LITRES_STEP, 125, _LITRES_STEP)   # le frasi registrate
_LOW_LAPS = 3              # in prova i litri si dicono solo sotto questi giri


def litres_to_add(fuel: float, per_lap: float, lap_ms: float, time_left_ms: float,
                  max_fuel: float = 0.0) -> float | None:
    """Litri da aggiungere per finire la sessione, o None se non si puo' dire.

    Allo scadere del tempo il giro in corso si finisce: per questo si arrotonda
    per eccesso, piu' un giro di scorta. Negativo o zero vuol dire che basta.
    """
    if per_lap <= 0.0 or lap_ms <= 0.0 or time_left_ms <= 0.0:
        return None
    laps = math.ceil(time_left_ms / lap_ms) + _MARGIN_LAPS
    add = laps * per_lap - fuel
    if max_fuel > 0.0:
        add = min(add, max_fuel - fuel)
    return add


class FuelEngineer:
    """Stateful: fed (snapshot, now) each frame; yields fuel warnings at the line."""

    def __init__(self) -> None:
        self._burns: list[float] = []          # recent per-lap burn, newest last
        self._laps_ms: list[int] = []          # e il tempo degli stessi giri
        self._was_in_lane = False
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

        # Touching the pit lane at all disqualifies the lap: the question here is
        # not "am I stopped in the box" but "did this lap go through the pits",
        # and a lap spent behind the limiter — in-lap, out-lap, drive-through —
        # burns nothing like a racing lap. `in_pit` stays because AC1 may well
        # set it; on ACC, in everything we have been able to observe, `isInPit`
        # never comes on and only `isInPitLane` does (measured on track 07/08
        # with the car stationary in the box: in_pit=False, in_pit_lane=True).
        if s.in_pit or s.in_pit_lane:
            self._pit_this_lap = True
        if s.in_pit_lane and not self._was_in_lane:
            cues += self._litres_call(s)
        self._was_in_lane = s.in_pit_lane
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
                if s.last_lap_ms > 0:
                    self._laps_ms.append(s.last_lap_ms)
                    del self._laps_ms[:-_AVG_WINDOW]
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
                # Una soglia piu' stretta vale anche per quelle piu' larghe. Prima
                # si segnava solo la sua: dopo «Ultimo giro di benzina» il 2 o il
                # 3 rimasti liberi scattavano al giro dopo con int(remaining) = 0,
                # e la voce diceva «Benzina per circa 0 giri».
                self._warned.update(t for t in _WARN_LAPS if t >= thresh)
                if thresh <= 1:
                    msg = "Ultimo giro di benzina, rientra ai box"
                else:
                    # Report whole laps you can actually finish (floor), not the
                    # threshold band's upper bound: at 2.5 laps left the tank is
                    # good for ~2 laps, not 3 — overstating risks running dry.
                    laps_left = int(remaining)
                    if laps_left == 1:
                        msg = f"Benzina per circa {laps_left} giro."
                    else:
                        msg = f"Benzina per circa {laps_left} giri."
                return [Cue(category=CueCategory.FUEL, message=msg,
                            priority=_PRIORITY, segment=0, pos=0.0)]
        return []

    def _litres_call(self, s: TelemetrySnapshot) -> list[Cue]:
        """Entrando in corsia box, i litri da mettere nel menu del gioco.

        In gara sempre. In prova solo col serbatoio quasi vuoto: lo stop per una
        modifica d'assetto non deve riempire, o il carico falsa la prova.
        """
        if not self._burns or not self._laps_ms:
            return []
        per_lap = sum(self._burns) / len(self._burns)
        if s.session is not SessionType.RACE and s.fuel / per_lap > _LOW_LAPS:
            return []
        add = litres_to_add(s.fuel, per_lap, statistics.median(self._laps_ms),
                            s.session_time_left_ms, s.max_fuel)
        if add is None:
            return []
        if add <= 0.0:
            return [Cue(CueCategory.FUEL, "Benzina sufficiente fino a fine sessione.",
                        _PRIORITY, 1, s.lap_position)]
        n = math.ceil(add / _LITRES_STEP) * _LITRES_STEP
        if s.max_fuel > 0.0 and n > s.max_fuel - s.fuel:
            n = math.floor((s.max_fuel - s.fuel) / _LITRES_STEP) * _LITRES_STEP
        if n not in LITRES_SAID:
            return []
        return [Cue(category=CueCategory.FUEL, message=f"Aggiungi {n} litri.",
                    priority=_PRIORITY, segment=1, pos=s.lap_position)]

    def _reset_lap_window(self) -> None:
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._prev_pos = -1.0
        self._pit_this_lap = False


def burned(lap) -> float | None:
    """Litres this lap burned, measured from the recorded tank level.

    The live engineer above works this out frame by frame and then forgets it;
    this is the same subtraction done offline, so a lap you drove last week can
    still answer "what does a lap cost me". Only from v11 files — older laps
    never recorded the channel and come back None, which is not zero.

    None (rather than a number) when the tank *rose* during the lap: that is a
    refuel or a pit stop, and the difference between the two ends of it is not a
    burn rate. Same reason the live engineer drops those laps from its average.
    """
    samples = getattr(lap, "samples", lap)
    fuels = [s.fuel for s in samples if s.fuel > 0.0]
    if len(fuels) < 2:
        return None
    used = fuels[0] - fuels[-1]
    if used <= 0.0 or used > _PLAUSIBLE_BURN_L[1]:
        return None
    return round(used, 2)
