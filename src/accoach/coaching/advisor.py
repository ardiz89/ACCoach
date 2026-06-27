"""In-car aid advisor — suggest TC / ABS / brake-bias knob changes.

This sits one level above :class:`EventDetector`. A single lock-up or wheelspin
is a *technique* mistake the driver fixes with their foot, and the event
detector already calls those out in the moment. But when the **same** symptom
keeps happening **all around the lap** — locking the fronts into many different
corners, spinning up on exit after exit — the problem is no longer where you
brake or how you squeeze the throttle: the car is set too aggressively for the
grip, and the cheap fix is a dashboard knob the driver can turn on the straight.

So the advisor does three things the event detector deliberately does not:

* **Aggregate over a whole lap**, not a single frame, and require the symptom at
  several *distinct* places (``_MIN_DISTINCT_SEGMENTS``). One brutal braking zone
  that always locks is a corner to learn, not a setup to change; the same fault
  in five corners is a setting.
* **Recommend an adjustment**, naming the current level when we can read it
  ("raise TC from 4 to 5") and falling back to a direction when we can't.
* **Speak it at the right moment** — at the start/finish line, where the driver
  has a straight to reach down and change the knob — and then go quiet for a few
  laps (``_COOLDOWN_LAPS``) so they can feel the effect before being nagged again.

It is fed the same debounced event cues the detector already produced, so there
is exactly one place that decides "this was a real lock-up", and the advisor just
counts them. Time is injected for testability, as elsewhere in the coach.
"""

from __future__ import annotations

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory

# How many distinct lap segments must show the symptom before it's "everywhere"
# rather than "that one corner". The event cues are bucketed into 20 segments
# (see events._EVENT_SEGMENTS), so 3 means three different parts of the track.
_MIN_DISTINCT_SEGMENTS = 3

# After advising a change, stay silent on that topic for this many laps so the
# driver can make the change and feel it before we re-evaluate.
_COOLDOWN_LAPS = 3

# A lap only counts as "complete enough" to judge if we actually watched most of
# it go by (filters out-laps, pit exits and the partial lap when coaching starts
# mid-track). Measured as the span between the min and max position we saw.
_MIN_LAP_SPAN = 0.7

# If ABS is already cranked up this high, telling the driver to raise it further
# is useless — the better remedy for persistent front locking is brake bias.
_ABS_ALREADY_HIGH = 8

# Ranks below the in-the-moment events (events._PRIORITY_BASE = 300) but above
# ordinary segment time-loss: useful, not urgent, and there's no contention at
# the line anyway.
_PRIORITY = 260.0


class SetupAdvisor:
    """Stateful: fed (snapshot, event cues, now) each frame; yields aid advice."""

    def __init__(self) -> None:
        self._lock_segments: set[int] = set()
        self._spin_segments: set[int] = set()
        self._prev_pos: float = -1.0
        self._pos_min: float = 1.0
        self._pos_max: float = 0.0
        # Per-category laps-of-silence remaining.
        self._cooldown: dict[CueCategory, int] = {}

    def reset(self) -> None:
        self._lock_segments.clear()
        self._spin_segments.clear()
        self._prev_pos = -1.0
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._cooldown.clear()

    def update(self, s: TelemetrySnapshot, event_cues: list[Cue], now: float) -> list[Cue]:
        # Only judge clean, live, on-track laps; anything else discards the
        # partial lap so an out-lap or a pit visit never triggers advice.
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self._reset_lap()
            return []

        pos = s.lap_position
        cues = self._maybe_advise(s, pos)

        # Accumulate this frame's confirmed symptoms by where they happened.
        for cue in event_cues:
            if cue.category is CueCategory.LOCKED:
                self._lock_segments.add(cue.segment)
            elif cue.category is CueCategory.WHEELSPIN:
                self._spin_segments.add(cue.segment)

        self._pos_min = min(self._pos_min, pos)
        self._pos_max = max(self._pos_max, pos)
        self._prev_pos = pos
        return cues

    # --- lap boundary -----------------------------------------------------
    def _maybe_advise(self, s: TelemetrySnapshot, pos: float) -> list[Cue]:
        """At the start/finish wrap, evaluate the lap just finished."""
        crossed = self._prev_pos > 0.7 and pos < 0.3
        if not crossed:
            return []

        full_lap = (self._pos_max - self._pos_min) >= _MIN_LAP_SPAN
        lock = len(self._lock_segments)
        spin = len(self._spin_segments)
        cues: list[Cue] = []
        if full_lap:
            cue = self._evaluate(s, lock, spin)
            if cue is not None:
                cues.append(cue)

        self._tick_cooldown()
        self._reset_lap()
        return cues

    def _evaluate(self, s: TelemetrySnapshot, lock: int, spin: int) -> Cue | None:
        """Pick at most one advice for the finished lap — the worse symptom."""
        lock_bad = lock >= _MIN_DISTINCT_SEGMENTS
        spin_bad = spin >= _MIN_DISTINCT_SEGMENTS
        if not (lock_bad or spin_bad):
            return None

        # Worse symptom wins; ties go to locking (it's the bigger lap-time and
        # safety cost). Each remedy still surfaces on a later lap if it persists.
        prefer_lock = lock_bad and (not spin_bad or lock >= spin)
        if prefer_lock:
            return self._lock_advice(s)
        return self._spin_advice(s)

    # --- remedies ---------------------------------------------------------
    def _lock_advice(self, s: TelemetrySnapshot) -> Cue | None:
        # If ABS is maxed out, raising it won't help — shift brake bias rearward.
        # (abs_level is -1 when unknown, so this stays False and we suggest ABS.)
        if s.abs_level >= _ABS_ALREADY_HIGH:
            return self._make(CueCategory.BRAKE_BIAS,
                              "Blocchi l'anteriore in più curve e l'ABS è già alto: "
                              "prova a spostare il bilanciamento freni verso il posteriore.")
        return self._make(
            CueCategory.ABS_UP,
            "Blocchi l'anteriore in più curve: prova ad alzare l'ABS"
            + self._from_to(s.abs_level))

    def _spin_advice(self, s: TelemetrySnapshot) -> Cue | None:
        return self._make(
            CueCategory.TC_UP,
            "Pattini in uscita in più punti del giro: prova ad alzare il TC"
            + self._from_to(s.tc_level))

    @staticmethod
    def _from_to(level: int) -> str:
        """' (dal 4 al 5).' when the level is known, '.' otherwise."""
        if level < 0:
            return "."
        return f" (dal {level} al {level + 1})."

    def _make(self, category: CueCategory, message: str) -> Cue | None:
        if self._cooldown.get(category, 0) > 0:
            return None
        self._cooldown[category] = _COOLDOWN_LAPS
        # Delivered at the line, so it lands on the straight; segment 0.
        return Cue(category=category, message=message,
                   priority=_PRIORITY, segment=0, pos=0.0)

    # --- bookkeeping ------------------------------------------------------
    def _tick_cooldown(self) -> None:
        for cat in list(self._cooldown):
            self._cooldown[cat] -= 1
            if self._cooldown[cat] <= 0:
                del self._cooldown[cat]

    def _reset_lap(self) -> None:
        self._lock_segments.clear()
        self._spin_segments.clear()
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._prev_pos = -1.0
