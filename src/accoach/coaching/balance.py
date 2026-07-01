"""Live handling-balance coaching — understeer and oversteer.

The event detector calls out lock-ups and wheelspin; this is its cornering
sibling. It reads how the car is *rotating* relative to how much the driver is
asking with the wheel, and names the two faults that cost the most mid-corner:

* **Understeer (push)** — lots of steering lock and real cornering speed, but the
  car isn't rotating: ``yaw_rate`` stays low while ``steer_angle`` is large. The
  nose is washing out; you carried too much speed in or you're on the power too
  early. Judged only once the steering has **settled**: during turn-in the yaw
  naturally lags the wheel, so a still-winding-on transient is not a push (see
  ``_winding_on`` / ``_TURNIN_RATE``).
* **Oversteer (loose)** — the rear is coming round faster than you steered for.
  The giveaway is **opposite lock**: the front wheels point one way while the car
  yaws the other (``steer_angle`` and ``yaw_rate`` have opposite signs). That's
  the driver already catching a slide, so it's a high-credibility signal.

Like :class:`~accoach.coaching.events.EventDetector` this needs **no reference
lap** — understeer and oversteer are wrong in absolute terms — so it works from
the first corner of the first lap. Same debounce/one-shot/dedup machinery.

⚠ Calibration (do this once, live, like the g-axis and lock-up checks)
---------------------------------------------------------------------
The oversteer test assumes ``steer_angle`` (+left) and ``yaw_rate`` share a sign
convention: a steady left-hand corner should give *same-sign* steer and yaw, so
the opposite-sign test only trips on genuine countersteer. If a clean corner ever
fires OVERSTEER constantly, the yaw sign is inverted on this title — flip
``_YAW_SIGN`` to -1. The magnitude thresholds (``_STEER_*``, ``_YAW_*``) are
deliberately conservative first guesses; tighten them against a real session.
"""

from __future__ import annotations

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from ._detector import Episode, make_cue, step
from .cue import Cue, CueCategory

# Calibrated against live AC (2026-06-26): in clean corners steer*yaw_rate was
# ~70% NEGATIVE, i.e. the game's yaw_rate is signed opposite to steer_angle, so
# we negate it to restore the "clean corner => same sign" convention the logic
# below expects (otherwise clean corners false-fire as oversteer).
_YAW_SIGN = -1.0

# Only judge balance when actually cornering at speed; slow manoeuvring and
# straight-line running have meaningless steer/yaw ratios.
_MIN_SPEED_KMH = 60.0

# Understeer: the car rotating far less than the steering asks for. Measured as
# the yaw/steer ratio — on AC1 GT3 (Imola) clean fast corners sat at a median
# ratio of ~1.9 (yaw rad/s per steer rad); a push drops it well below that.
_STEER_HARD = 0.15         # rad of steering — genuinely cornering, not noise
_UNDERSTEER_RATIO = 0.9    # yaw/steer below this (vs ~1.9 normal) = pushing

# Oversteer: meaningful rotation while the driver is applying opposite lock.
_STEER_CATCH = 0.04        # rad of (opposite) lock that counts as a correction
_YAW_LOOSE = 0.30          # rad/s of rotation that counts as the rear stepping out

_MIN_HOLD_S = 0.15         # sustain time before a balance fault fires
_PRIORITY_BASE = 280.0     # just below lock-up/wheelspin, above segment time-loss

# Turn-in guard: yaw_rate always LAGS the steering input — when the driver is
# still winding lock ON, the car hasn't started rotating yet, so yaw/steer dips
# low on a perfectly balanced car too. That transient is the classic understeer
# false positive. Suppress the push test while lock is being added faster than
# this (rad/s of |steer|); a genuine mid-corner push has settled steering.
_TURNIN_RATE = 0.6


class BalanceDetector:
    """Stateful: fed (snapshot, now) each frame, yields understeer/oversteer cues."""

    def __init__(self) -> None:
        self._push = Episode()
        self._loose = Episode()
        self._prev_steer: float | None = None
        self._prev_t: float | None = None

    def reset(self) -> None:
        self._push = Episode()
        self._loose = Episode()
        self._prev_steer = None
        self._prev_t = None

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self.reset()
            return []

        cues: list[Cue] = []
        # Oversteer takes precedence: if the rear is genuinely loose, that's the
        # story, not a push, and the two conditions are mutually exclusive anyway.
        loose = self._is_oversteer(s)
        # A push only counts once the steering has settled — while lock is still
        # being wound on (turn-in), low yaw/steer is just the rotation lagging.
        winding_on = self._winding_on(s.steer_angle, now)
        push = self._is_understeer(s) and not loose and not winding_on
        if step(self._loose, loose, now, _MIN_HOLD_S):
            cues.append(make_cue(s, CueCategory.OVERSTEER,
                                 "Sovrasterzo, sii più dolce col gas in uscita", _PRIORITY_BASE))
        if step(self._push, push, now, _MIN_HOLD_S):
            cues.append(make_cue(s, CueCategory.UNDERSTEER,
                                 "L'anteriore scivola, entra più piano", _PRIORITY_BASE))
        return cues

    # --- conditions -------------------------------------------------------
    def _winding_on(self, steer: float, now: float) -> bool:
        """True while the driver is adding lock quickly (the turn-in transient),
        where yaw naturally lags. Stateful: compares |steer| against the previous
        frame. The first frame of a corner has no rate yet → treated as transient
        so a push never fires on the very first sample."""
        prev_s, prev_t = self._prev_steer, self._prev_t
        self._prev_steer, self._prev_t = steer, now
        if prev_s is None or prev_t is None:
            return True
        dt = now - prev_t
        if dt <= 0.0:
            return False
        return (abs(steer) - abs(prev_s)) / dt > _TURNIN_RATE

    @staticmethod
    def _is_understeer(s: TelemetrySnapshot) -> bool:
        if s.speed_kmh < _MIN_SPEED_KMH:
            return False
        steer = abs(s.steer_angle)
        if steer < _STEER_HARD:
            return False
        # Rotating far less than the steering asks: yaw/steer well below normal.
        # (Magnitude only — the sign convention doesn't matter for a ratio.)
        return (abs(s.yaw_rate) / steer) < _UNDERSTEER_RATIO

    @staticmethod
    def _is_oversteer(s: TelemetrySnapshot) -> bool:
        if s.speed_kmh < _MIN_SPEED_KMH:
            return False
        yaw = s.yaw_rate * _YAW_SIGN
        # Car is rotating hard AND the driver is on opposite lock to catch it:
        # steer and yaw point opposite ways (negative product).
        applying_opposite_lock = (
            abs(s.steer_angle) >= _STEER_CATCH and s.steer_angle * yaw < 0.0
        )
        return abs(yaw) >= _YAW_LOOSE and applying_opposite_lock
