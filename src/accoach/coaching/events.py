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
reliable on ACC GT3s. Per-wheel ``wheel_slip`` is a secondary corroborator for
cars/sessions running without aids; its absolute scale varies, so its thresholds
are deliberately conservative and easy to recalibrate (see ``_FRONT_SLIP_LOCK`` /
``_REAR_SLIP_SPIN``) — primary detection does not depend on them.

Debounce
--------
A condition must hold briefly before it fires (filters single-frame noise and
kerb rattles), and fires only once per episode — re-arming only after it clears.
The scheduler's repeat-suppression then stops the same call repeating every lap
at the same corner. Time is injected (``now``, monotonic seconds) for testability.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory

# Braking / lock-up
_BRAKE_MIN = 0.30          # must be meaningfully on the brakes
_ABS_LEVEL = 0.35          # ABS intervention that counts as locking
_LOCK_RATIO = -0.15        # front slip ratio: wheel ≥15% slower than ground

# Throttle / wheelspin
_THROTTLE_MIN = 0.50       # must be meaningfully on the throttle
_TC_LEVEL = 0.35           # TC intervention that counts as wheelspin
_SPIN_RATIO = 0.10         # rear slip ratio: wheel ≥10% faster than ground

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

_MIN_HOLD_S = 0.12         # sustain time before an event fires
_EVENT_SEGMENTS = 20       # granularity for de-duplicating by location
_PRIORITY_BASE = 300.0     # ranks above most segment time-loss cues


@dataclass(slots=True)
class _Episode:
    active: bool = False
    since: float = 0.0
    fired: bool = False


class EventDetector:
    """Stateful: fed (snapshot, now) each frame, yields lock-up/wheelspin cues."""

    def __init__(self) -> None:
        self._lock = _Episode()
        self._spin = _Episode()

    def reset(self) -> None:
        self._lock = _Episode()
        self._spin = _Episode()

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self.reset()
            return []

        cues: list[Cue] = []
        if self._step(self._lock, self._is_lockup(s), now):
            cues.append(self._make(s, CueCategory.LOCKED,
                                   "Bloccaggio, alleggerisci il freno"))
        if self._step(self._spin, self._is_wheelspin(s), now):
            cues.append(self._make(s, CueCategory.WHEELSPIN,
                                   "Pattini in uscita, meno gas"))
        return cues

    # --- conditions -------------------------------------------------------
    @staticmethod
    def _is_lockup(s: TelemetrySnapshot) -> bool:
        if s.brake < _BRAKE_MIN:
            return False
        # Most-negative front wheel (the one biting into a lock).
        front_ratio = min(s.slip_ratio[0], s.slip_ratio[1])
        return s.abs_active >= _ABS_LEVEL or front_ratio <= _LOCK_RATIO

    @staticmethod
    def _is_wheelspin(s: TelemetrySnapshot) -> bool:
        if s.throttle < _THROTTLE_MIN or s.gear in ("R", "N"):
            return False
        # Fastest-spinning rear wheel.
        rear_ratio = max(s.slip_ratio[2], s.slip_ratio[3])
        return s.tc_active >= _TC_LEVEL or rear_ratio >= _SPIN_RATIO

    # --- debounce ---------------------------------------------------------
    @staticmethod
    def _step(ep: _Episode, cond: bool, now: float) -> bool:
        """Advance an episode; return True exactly once when it fires."""
        if cond:
            if not ep.active:
                ep.active = True
                ep.since = now
                ep.fired = False
            elif not ep.fired and now - ep.since >= _MIN_HOLD_S:
                ep.fired = True
                return True
        else:
            ep.active = False
        return False

    @staticmethod
    def _make(s: TelemetrySnapshot, category: CueCategory, message: str) -> Cue:
        seg = min(_EVENT_SEGMENTS - 1, max(0, int(s.lap_position * _EVENT_SEGMENTS)))
        return Cue(category=category, message=message,
                   priority=_PRIORITY_BASE, segment=seg, pos=s.lap_position)
