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
"""

from __future__ import annotations

from dataclasses import dataclass

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory

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

_EVENT_SEGMENTS = 20
_PRIORITY = 270.0           # useful entry advice, below acute slides/locks


@dataclass(slots=True)
class _Episode:
    active: bool = False
    since: float = 0.0
    fired: bool = False


class BrakingDetector:
    """Stateful: fed (snapshot, now) each frame, yields braking-technique cues."""

    def __init__(self) -> None:
        self._coast = _Episode()
        self._last_hard_brake_t = -1e9
        self._in_turn = False

    def reset(self) -> None:
        self._coast = _Episode()
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

        if self._step(self._coast, self._is_coasting(s), now):
            cues.append(self._make(s, CueCategory.COASTING,
                                   "Stai veleggiando: riduci il tempo morto fra freno e gas"))

        if self._trail_fault(s, now):
            cues.append(self._make(s, CueCategory.TRAIL_BRAKE,
                                   "Rilasci il freno troppo presto: portane un filo fino all'inserimento"))
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

    # --- debounce ---------------------------------------------------------
    @staticmethod
    def _step(ep: _Episode, cond: bool, now: float) -> bool:
        if cond:
            if not ep.active:
                ep.active = True
                ep.since = now
                ep.fired = False
            elif not ep.fired and now - ep.since >= _COAST_HOLD_S:
                ep.fired = True
                return True
        else:
            ep.active = False
        return False

    @staticmethod
    def _make(s: TelemetrySnapshot, category: CueCategory, message: str) -> Cue:
        seg = min(_EVENT_SEGMENTS - 1, max(0, int(s.lap_position * _EVENT_SEGMENTS)))
        return Cue(category=category, message=message,
                   priority=_PRIORITY, segment=seg, pos=s.lap_position)
