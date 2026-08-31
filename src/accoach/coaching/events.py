"""Instant coaching events — lock-ups and wheelspin — from the live frame.

Unlike the segment analyzer, :class:`EventDetector` needs **no reference lap**:
locking a wheel or spinning up on exit is wrong in absolute terms, so it can be
called out the moment it happens. That makes it the highest-credibility, lowest-
cost coaching you can give ("you locked the fronts there") and it works from the
very first lap.

Signals
-------
The primary trigger is the car's own electronics telling us the driver asked for
more than the grip allows: ``abs_active`` (braking past lock) and ``tc_active``
(throttle past traction). Those are normalized 0..1 intervention levels and are
reliable on ACC GT3s. The secondary corroborator, for cars/sessions running
without aids, is the physical ``slip_ratio`` (see ``_LOCK_RATIO`` and the
class-dependent rear-spin threshold in ``coaching.tuning``) — primary detection
does not depend on it. It is *not* the sim's raw ``wheel_slip``: that channel's
scale is car-dependent, which is why it was replaced here and, at schema v10,
dropped from what a lap stores.

Debounce
--------
A condition must hold briefly before it fires (filters single-frame noise and
kerb rattles), and fires only once per episode — re-arming only after it clears.
The scheduler's repeat-suppression then stops the same call repeating every lap
at the same corner. Time is injected (``now``, monotonic seconds) for testability.
"""

from __future__ import annotations

from ..engineer import CarClass
from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from ._detector import Episode, make_cue, step
from .cue import Cue, CueCategory
from .tuning import DEFAULT_TUNING, tuning_for_class

# Braking / lock-up
_BRAKE_MIN = 0.30          # must be meaningfully on the brakes
_ABS_LEVEL = 0.35          # ABS intervention that counts as locking
_LOCK_RATIO = -0.15        # front slip ratio: wheel ≥15% slower than ground

# Throttle / wheelspin
_THROTTLE_MIN = 0.50       # must be meaningfully on the throttle
_TC_LEVEL = 0.35           # TC intervention that counts as wheelspin
# The rear slip ratio that counts as wheelspin is class-dependent (see
# coaching.tuning): stiffer/more-powerful classes tolerate more slip. Set per
# car via the constructor / set_car_class; DEFAULT_TUNING (GT3) until known.

# The slip-ratio fallback is a PHYSICAL ratio (see reader._slip_ratio), so unlike
# the raw wheel_slip channel it doesn't need per-car calibration — a locked or
# spinning wheel reads the same on any car. On ABS/TC cars the intervention
# signal leads; the ratio covers cars whose aid channels don't report live.
#
# Validated live 2026-06-26 (F1 1990 McLaren, no aids, at speed):
#   * sign/units CONFIRMED — front ratio goes negative under braking, rear
#     positive under throttle.
#
# Re-calibrated 2026-06-26 against AC1 GT3 (McLaren MP4-12C, Imola), where the
# abs/tc intervention channels read a constant garbage value (~0.12/0.10) and so
# never trip the _ABS_LEVEL/_TC_LEVEL primary — the slip ratio does ALL the work:
#   * braking: typical hard braking sat at front-lock slip med -0.073 / p99 -0.031;
#     the hardest deliberate lock only reached -0.225. The old -0.25 missed every
#     real lock → lowered to -0.15 (≈2× typical hard braking, well clear of it).
#   * throttle: traction sat at rear-spin med +0.020 / p99 +0.071; the biggest
#     deliberate wheelspin reached +0.138. The old +0.15 missed it → lowered to
#     +0.10 (clear of the +0.071 traction ceiling).

# Below this the slip-ratio fallback is unreliable: the ratio is (ω·r − v)/v, so a
# small v blows the denominator up and noise reads as a lock/spin. The abs/tc
# primary (reliable at any speed) is NOT gated; only the ratio branch is.
_RATIO_MIN_SPEED = 40.0    # km/h

_MIN_HOLD_S = 0.12         # sustain time before an event fires
_PRIORITY_BASE = 300.0     # ranks above most segment time-loss cues


# --- the one rule -----------------------------------------------------------
# These two live at module level, and not inside EventDetector, because the
# post-lap diagnosis (`coaching.diagnosis._lock_spin_segments`, which is what the
# race engineer sees) has to answer the same question about a recorded
# `LapSample`. It used to answer it with its own copy of the rule, and the copy
# drifted: the live rule was tightened on 2026-07-19 and nobody came back here,
# so for three weeks "lock-up" meant two different things depending on who was
# asking. Both callers now go through this function; there is nowhere left for
# the two to disagree.
#
# The argument is duck-typed on purpose: a live `TelemetrySnapshot` and a
# recorded `LapSample` both carry the fields read here, and requiring one to be
# converted into the other would put a translation step between the two callers —
# which is where a divergence would grow back.

def is_lockup(s) -> bool:
    """Is this frame a genuine front lock-up?

    The aid flag (ABS ≥ level) **gates** but no longer **triggers** on its own:
    on ACC it goes high during normal braking-into-ABS, so the flag alone nagged
    on correct technique (audit 2026-07-19: 3 false locks on one clean GT3 lap).
    Now the flag only says "the ABS is modulating"; the physical slip ratio has
    to corroborate a genuine lock before this is true.

    Validated live (McLaren 720S GT3, Imola): ABS-managed braking sits at front
    slip -0.05..-0.09, inside the -0.15 threshold, while a real lock blows well
    past it — measured at -1.00 (wheel stopped) on 2026-08-12 at Monza. With the
    flag present the speed gate is skipped: the ACC native slip ratio is
    trustworthy even at low v, unlike the formula that gate protects.
    """
    if s.brake < _BRAKE_MIN:
        return False
    front_ratio = min(s.slip_ratio[0], s.slip_ratio[1])  # most-negative front wheel
    locked = front_ratio <= _LOCK_RATIO
    if s.abs_active >= _ABS_LEVEL:               # aid modulating: slip must confirm
        return locked
    return s.speed_kmh >= _RATIO_MIN_SPEED and locked


def is_wheelspin(s, spin_ratio: float) -> bool:
    """Is this frame a genuine rear wheelspin? (Same shape as :func:`is_lockup`.)

    ``spin_ratio`` is class-dependent — see :mod:`accoach.coaching.tuning`. The
    2026-07-19 audit counted 8 false wheelspin calls on one clean lap from the
    TC flag alone; TC-managed traction measured rear slip +0.05..+0.07.
    """
    if s.throttle < _THROTTLE_MIN or s.gear in ("R", "N"):
        return False
    rear_ratio = max(s.slip_ratio[2], s.slip_ratio[3])   # fastest-spinning rear
    spinning = rear_ratio >= spin_ratio
    if s.tc_active >= _TC_LEVEL:                 # aid modulating: slip must confirm
        return spinning
    return s.speed_kmh >= _RATIO_MIN_SPEED and spinning


class EventDetector:
    """Stateful: fed (snapshot, now) each frame, yields lock-up/wheelspin cues."""

    def __init__(self, car_class: CarClass | None = None) -> None:
        self._lock = Episode()
        self._spin = Episode()
        self._spin_ratio = (tuning_for_class(car_class).spin_ratio
                            if car_class is not None else DEFAULT_TUNING.spin_ratio)

    def set_car_class(self, car_class: CarClass) -> None:
        """Retune the wheelspin threshold when the car (class) changes."""
        self._spin_ratio = tuning_for_class(car_class).spin_ratio

    def reset(self) -> None:
        self._lock = Episode()
        self._spin = Episode()

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        # The whole lane, not just the box. These two cues are in the engine's
        # safety set, so they are the only driving advice that survives
        # `quiet == "pit"` — this gate is the only thing standing between the
        # driver and a lock-up call while they park. `in_pit` alone could not do
        # it: ACC reads it as 0 with the car stationary in its garage (measured
        # 2026-08-07), and the low-speed gate in `_is_lockup` is skipped exactly
        # when an aid is modulating, which braking into a box always is.
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit or s.in_pit_lane:
            self.reset()
            return []

        cues: list[Cue] = []
        if step(self._lock, self._is_lockup(s), now, _MIN_HOLD_S):
            cues.append(make_cue(s, CueCategory.LOCKED,
                                 "Bloccaggio, alleggerisci il freno", _PRIORITY_BASE))
        if step(self._spin, self._is_wheelspin(s), now, _MIN_HOLD_S):
            cues.append(make_cue(s, CueCategory.WHEELSPIN,
                                 "Pattini in uscita, meno gas", _PRIORITY_BASE))
        return cues

    # --- conditions -------------------------------------------------------
    # Thin wrappers over the module-level rule (see `is_lockup` / `is_wheelspin`),
    # kept as methods only because the wheelspin threshold is per-car state that
    # lives on the detector. The rule itself is deliberately NOT duplicated here.
    @staticmethod
    def _is_lockup(s: TelemetrySnapshot) -> bool:
        return is_lockup(s)

    def _is_wheelspin(self, s: TelemetrySnapshot) -> bool:
        return is_wheelspin(s, self._spin_ratio)
