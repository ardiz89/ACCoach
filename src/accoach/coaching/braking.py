"""Braking-technique coaching — coasting and trail braking.

Two faults that cost time on entry and that the throttle/brake/steer traces show
plainly, no reference lap required:

* **Coasting** — a stretch with *neither* pedal applied at speed. Every metre
  spent off the brakes and off the throttle is time thrown away: you braked too
  early/too much and are now waiting for the corner. We flag a sustained dead
  patch (both pedals released) the way the event detector flags a lock-up.

* **No trail braking** — releasing the brake fully *before* turning in, so the
  whole stop happens in a straight line and the car turns with no front load.
  We catch the moment the wheel passes turn-in and check whether a hard stop had
  just finished with the brake already dropped — the classic "brake, then steer"
  amateur pattern instead of bleeding the brake to the apex.

Both reuse the established debounce / dedup-by-segment conventions. Thresholds are
conservative first guesses; the trail-brake one in particular is heuristic and
worth tightening against a live session (it should stay silent through fast
corners you don't brake for and through normal corner exits).

Whether the trail-brake fault is coached at all is class-dependent — see
``trail_brake_cue`` in :mod:`accoach.coaching.tuning` for why road cars get
silence. Coasting is class-agnostic: dead pedal time costs metres on anything.
"""

from __future__ import annotations

from ..engineer import CarClass
from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from ._detector import Episode, make_cue, step
from .cue import Cue, CueCategory
from .tuning import DEFAULT_TUNING, tuning_for_class

_MIN_SPEED_KMH = 80.0       # technique only matters at pace

# Coasting: both pedals essentially off, held long enough to be a real coast
# rather than the brief brake-to-throttle handover.
_PEDAL_OFF = 0.05
_COAST_HOLD_S = 0.6

# Trail braking: a hard stop that finished with the brake already released right
# as the car is turned in (and not on the way out of a corner).
_BRAKE_HARD = 0.50          # peak brake that marks a real braking zone
_BRAKE_RELEASED = 0.12      # brake this low at turn-in = nothing left to trail
_STEER_TURNIN = 0.10        # rad of steering that marks turn-in
_STEER_BACK = 0.05          # steering must drop below this to re-arm turn-in
_RECENT_BRAKE_S = 0.8       # how recently the hard stop must have been
_EXIT_THROTTLE = 0.20       # above this we're on exit, not entry — ignore

_PRIORITY = 270.0           # useful entry advice, below acute slides/locks


class BrakingDetector:
    """Stateful: fed (snapshot, now) each frame, yields braking-technique cues."""

    def __init__(self, car_class: CarClass | None = None) -> None:
        self._coast = Episode()
        self._last_hard_brake_t = -1e9
        self._in_turn = False
        self._trail_cue = (tuning_for_class(car_class).trail_brake_cue
                           if car_class is not None else DEFAULT_TUNING.trail_brake_cue)

    def set_car_class(self, car_class: CarClass) -> None:
        """Enable/disable the trail-brake cue when the car (class) changes."""
        self._trail_cue = tuning_for_class(car_class).trail_brake_cue

    def reset(self) -> None:
        self._coast = Episode()
        self._last_hard_brake_t = -1e9
        self._in_turn = False

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self.reset()
            return []

        cues: list[Cue] = []
        if s.speed_kmh < _MIN_SPEED_KMH:
            # Keep timers sane but don't coach at low speed.
            self._coast.active = False
            self._in_turn = abs(s.steer_angle) >= _STEER_TURNIN
            return cues

        if s.brake >= _BRAKE_HARD:
            self._last_hard_brake_t = now

        if step(self._coast, self._is_coasting(s), now, _COAST_HOLD_S):
            cues.append(make_cue(s, CueCategory.COASTING,
                                 "Stai veleggiando: riduci il tempo morto fra freno e gas", _PRIORITY))

        # Always step the turn-in state machine, even when the cue is off for this
        # class: set_car_class can flip it mid-session, and a state machine that
        # only ran while enabled would come back with a stale _in_turn.
        trail_fault = self._trail_fault(s, now)
        if trail_fault and self._trail_cue:
            cues.append(make_cue(s, CueCategory.TRAIL_BRAKE,
                                 "Rilasci il freno troppo presto: portane un filo fino all'inserimento", _PRIORITY))
        return cues

    # --- conditions -------------------------------------------------------
    @staticmethod
    def _is_coasting(s: TelemetrySnapshot) -> bool:
        return s.brake < _PEDAL_OFF and s.throttle < _PEDAL_OFF

    def _trail_fault(self, s: TelemetrySnapshot, now: float) -> bool:
        """Fire once on the turn-in edge when a straight-line stop just ended."""
        turning = abs(s.steer_angle) >= _STEER_TURNIN
        rising_edge = turning and not self._in_turn
        # Re-arm only once the wheel comes back roughly straight.
        if abs(s.steer_angle) < _STEER_BACK:
            self._in_turn = False
        elif turning:
            self._in_turn = True

        if not rising_edge:
            return False
        just_braked_hard = now - self._last_hard_brake_t <= _RECENT_BRAKE_S
        return (
            just_braked_hard
            and s.brake < _BRAKE_RELEASED
            and s.throttle < _EXIT_THROTTLE
        )
