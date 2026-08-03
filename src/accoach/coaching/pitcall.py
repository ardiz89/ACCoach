"""Call the driver in when there's a setup change waiting, and brief them there.

The race engineer already proposes a change and already says *what* it is. What
it never said is **when to come in**, and the driver's own words for the gap
were: the coach gives you the change to make but doesn't tell you to box. So the
proposal was announced somewhere on the lap, the driver kept driving, and the
change waited a lap — or three.

Three moments, and the reason each one exists:

* **The call**, at the start of the final sector. Early enough that the pit
  entry is still ahead (on almost every circuit it sits in the last sector or
  just before the line), late enough that it lands on the lap you can act on.
  This is the driver's own request: *before the last sector ends*.
* **The approach**, shortly before the pit entry itself. The call tells you to
  box; this tells you the entry is here. It is emitted **only where the pit
  entry has been measured** (see :meth:`note_pit_entry`) — a guessed entry point
  spoken with confidence is worse than silence, because the driver would lift
  for it.
* **The briefing**, once stopped in the box. The change lives in a browser page
  the driver isn't looking at; without a word here they sit in the garage with
  the app three clicks away and no reason to open it.

Deliberately **only for changes that need the garage** (``tag == "BOX"``).
Something you can dial at the wheel is not a reason to lose a lap, and the
engineer already distinguishes the two.

The pit entry is **learned, never assumed**: no telemetry field publishes it, so
we watch where the car leaves the track for the pit lane and remember that
position per track. Median of the samples we've seen, so one rejoin or one
aborted entry doesn't move it. Until a track has been entered once, the approach
call simply doesn't exist there.

Time is injected (``now``), as everywhere else in the coach.
"""

from __future__ import annotations

import math
import statistics

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory

# Where the final sector starts when the sim doesn't publish sectors (some AC
# content reports `sector_count = 0`). Thirds, matching sectors.DEFAULT_SECTORS —
# the same fallback the rest of the app makes, so the call lands in the same
# place whether or not the game happens to declare its splits.
_FALLBACK_LAST_SECTOR = 2.0 / 3.0

# How much warning each call gives, in seconds of driving. Converted to a slice
# of lap using the position rate measured **right now** rather than the lap
# average: the run to the pit entry is usually quicker than the lap mean, so an
# average-based lead would be short exactly where it matters.
_APPROACH_LEAD_S = 5.0
_CALL_LEAD_S = 20.0

# Guards on each lead: never so small it arrives with the entry (the driver needs
# time to move across), never so large it stops being a warning about a place.
_APPROACH_MIN, _APPROACH_MAX = 0.010, 0.080     # ~1%..8% of the lap
_CALL_MIN, _CALL_MAX = 0.060, 0.300             # ~6%..30%

# A learned entry is worth having after one visit, but keeps improving. Cap the
# memory so an entry that genuinely moves (a track update) isn't outvoted
# forever by history.
_MAX_ENTRY_SAMPLES = 7

# How continuous a "car left the track for the pit lane" has to look before we
# believe it. A real entry is a few metres past where the car was last on track,
# a fraction of a second earlier. ESC → "return to garage" is not: it teleports,
# and the last on-track position can be anywhere on the circuit. Reproduced:
# four such returns after three genuine visits moved the learned entry from
# 0.94 to 0.72 — mid-track — and it is written to disk and reloaded next
# session. `_track_rate` already refuses jumps for the same reason; this is the
# same guard, at the place where the damage is persistent instead of momentary.
_ENTRY_MAX_STEP = 0.05
_ENTRY_MAX_GAP_S = 0.5

# A lap begins where the position wraps. Same thresholds the rest of the app
# uses for the start line, because two notions of "a new lap" is how the call
# ended up firing twice.
_WRAP_FROM, _WRAP_TO = 0.9, 0.1

# How long the briefing waits before saying itself again, while the car is
# stopped and the change is still unwritten. It repeats until it is heard —
# see `mark_briefed`.
_BRIEF_RETRY_S = 8.0

# Time constant of the position-rate smoother, in seconds.
_RATE_TAU_S = 0.5

# Below this the car isn't driving a lap, so the position it reports isn't a
# place on the track — it's wherever it was parked.
_MOVING_KMH = 25.0

# Ranks above ordinary technique advice: missing a pit call costs a whole lap,
# and there is no second chance at the entry. Still below the acute safety
# events, which is what the tier does — this only breaks ties within it.
_PRIORITY = 290.0

_CALL = "Modifica pronta: rientra ai box a fine giro"
_APPROACH = "Ingresso box qui davanti, rientra"
_BRIEFING = ("Sei ai box. Apri la pagina Ingegnere nel browser: applica la "
             "proposta, scrivi il setup e ricaricalo dal garage prima di uscire")


class PitCall:
    """Stateful: fed (snapshot, now) each frame; yields the pit-in calls.

    The engine tells it whether a garage change is waiting via
    :meth:`set_pending`; everything else it works out from telemetry.
    """

    def __init__(self, pit_entry_samples: list[float] | None = None) -> None:
        self._samples: list[float] = list(pit_entry_samples or [])
        self._pending = False
        # Per-lap: each call fires at most once a lap, so a driver who stays out
        # another lap is reminded again — once — instead of nagged every frame.
        # Keyed on OUR lap count, not the sim's: measured on real files, both
        # games bump `completed_laps` a frame or two *before* the position wraps
        # (`pos=0.0001, current_sector=2`), which is the very reason the recorder
        # has `crossed_start_line`. Trusting the counter here fired the call a
        # second time on the finish line, every lap, and latched the next one.
        self._lap = 0
        self._called_lap = -1
        self._approached_lap = -1
        self._briefed_at = -1e9
        self._briefed_spoken = False
        self._prev_pos = -1.0
        self._prev_t = 0.0
        self._rate = 0.0            # lap fractions per second, smoothed
        # The last place we saw the car actually on track, for learning the entry.
        self._last_track_pos: float | None = None
        self._last_track_t = -1e9
        self._was_in_lane = False
        self._entry_dirty = False

    # --- what the engine tells us ----------------------------------------

    def set_pending(self, pending: bool) -> None:
        """Is a garage-only setup change waiting to be written?

        Clearing it resets the briefing latch, so the *next* change gets its own
        briefing at the box rather than being swallowed by the last one's.
        """
        if pending != self._pending:
            self._pending = pending
            self._briefed_at = -1e9
            self._briefed_spoken = False
            self._called_lap = -1
            self._approached_lap = -1

    def mark_briefed(self) -> None:
        """The briefing was actually **spoken** — stop repeating it.

        The latch used to be set when the cue was *emitted*, which is not the
        same event: the scheduler can drop a cue, and this one is emitted once in
        the life of a setup change, so a drop meant the driver sat in the garage
        with nothing said and no second chance. Now the cue repeats until it is
        heard, which is also what a real engineer does — they keep asking until
        you answer.
        """
        self._briefed_spoken = True

    def reset(self) -> None:
        """New car/track: forget the lap latches, keep nothing track-specific."""
        self._pending = False
        self._lap = 0
        self._called_lap = -1
        self._approached_lap = -1
        self._briefed_at = -1e9
        self._briefed_spoken = False
        self._prev_pos = -1.0
        self._rate = 0.0
        self._last_track_pos = None
        self._last_track_t = -1e9
        self._was_in_lane = False
        self._samples = []
        self._entry_dirty = False

    # --- the learned pit entry -------------------------------------------

    @property
    def pit_entry(self) -> float | None:
        """Normalized position where this track's pit lane begins, if measured."""
        return statistics.median(self._samples) if self._samples else None

    @property
    def entry_dirty(self) -> bool:
        """A new sample arrived and hasn't been persisted yet."""
        return self._entry_dirty

    def samples(self) -> list[float]:
        return list(self._samples)

    def mark_entry_saved(self) -> None:
        self._entry_dirty = False

    def note_pit_entry(self, pos: float) -> None:
        self._samples.append(pos)
        del self._samples[:-_MAX_ENTRY_SAMPLES]
        self._entry_dirty = True

    # --- the frame loop ---------------------------------------------------

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE):
            return []

        self._learn_entry(s, now)
        self._track_rate(s, now)

        if not self._pending:
            return []

        # Stopped in the box: the one place the briefing belongs. Note this runs
        # while the engine's `quiet` gate says "pit" — that gate exists to stop
        # *driving* advice being spoken where it can't be used, and this is the
        # opposite: advice that can ONLY be used here. See engine._SAFETY_CATEGORIES.
        if s.in_pit:
            if self._briefed_spoken or now - self._briefed_at < _BRIEF_RETRY_S:
                return []
            self._briefed_at = now
            return [self._cue(CueCategory.PIT_BRIEFING, _BRIEFING, s.lap_position)]

        if s.in_pit_lane:
            return []                      # on the way in: nothing left to say

        out: list[Cue] = []
        lap = self._lap
        entry = self.pit_entry
        # How far ahead the entry is, going forwards round the lap. Modular, so
        # a pit entry sitting just after the start line (rare, but real) is
        # "0.99 away" from mid-lap rather than a negative number that quietly
        # disables both calls.
        gap = None if entry is None else (entry - s.lap_position) % 1.0
        approach_lead = self._lead(_APPROACH_LEAD_S, _APPROACH_MIN, _APPROACH_MAX)

        if self._called_lap != lap and self._due_to_call(s, gap):
            self._called_lap = lap
            out.append(self._cue(CueCategory.PIT_IN, _CALL, s.lap_position))
            # The call landed inside the approach window — on a circuit whose
            # pit entry sits early in the last sector, the two moments are the
            # same moment. Saying both would be two sentences for one event.
            # The epsilon is a float boundary, not a fudge: the call fires *at*
            # the edge of the window often enough (the last sector starting a
            # hair before the entry) that landing exactly on it must count as
            # inside. A thousandth of a lap is a few metres.
            if gap is not None and gap <= approach_lead + 1e-3:
                self._approached_lap = lap

        if gap is not None and self._approached_lap != lap and gap <= approach_lead:
            self._approached_lap = lap
            out.append(self._cue(CueCategory.PIT_APPROACH, _APPROACH, s.lap_position))
        return out

    # --- internals --------------------------------------------------------

    def _cue(self, cat: CueCategory, message: str, pos: float) -> Cue:
        # segment -1: these belong to the lap, not to a place on it, and giving
        # them a real segment would let the scheduler's dedup confuse the call
        # with the approach.
        return Cue(category=cat, message=message, priority=_PRIORITY,
                   segment=-1, pos=pos)

    def _lead(self, seconds: float, lo: float, hi: float) -> float:
        """``seconds`` of driving as a slice of lap, clamped to [lo, hi]."""
        return min(max(self._rate * seconds, lo), hi)

    def _due_to_call(self, s: TelemetrySnapshot, gap: float | None) -> bool:
        """Time to say "box this lap"?

        The last sector *or* a lead before the measured entry, whichever comes
        first — and the second half is not belt-and-braces. On a circuit whose
        pit entry sits **before** the final sector (they exist: the lane peels
        off the preceding corner), a call tied to the last sector arrives with
        the entry already behind the car, and the driver loses the lap the call
        was for. That is the exact failure this feature was built to end, so it
        cannot be left to track layout.
        """
        if self._in_last_sector(s):
            return True
        return gap is not None and gap <= self._lead(_CALL_LEAD_S,
                                                     _CALL_MIN, _CALL_MAX)

    def _in_last_sector(self, s: TelemetrySnapshot) -> bool:
        if s.sector_count > 0 and s.current_sector >= 0:
            return s.current_sector >= s.sector_count - 1
        return s.lap_position >= _FALLBACK_LAST_SECTOR

    def _track_rate(self, s: TelemetrySnapshot, now: float) -> None:
        """How fast the lap position is advancing, in fractions per second.

        Also where our own lap count lives, because a lap begins where the
        position wraps and not where the sim says so (see ``self._lap``).
        """
        pos, prev, dt = s.lap_position, self._prev_pos, now - self._prev_t
        self._prev_pos, self._prev_t = pos, now
        if prev < 0 or dt <= 0 or dt > 1.0:
            return
        if prev > _WRAP_FROM and pos < _WRAP_TO:
            self._lap += 1
        step = pos - prev
        if step <= 0 or step > 0.1:         # lap wrap, or a jump (teleport/reset)
            return
        rate = step / dt
        # Smoothing with a time constant, not a per-frame weight. A fixed 0.8/0.2
        # is five *frames*, which is 0.08 s at 60 Hz and 0.25 s at 20 — so the
        # same corner produced a different lead depending on the tick rate, and
        # the tests (20 Hz) never saw what the game (60 Hz) does.
        a = 1.0 - math.exp(-dt / _RATE_TAU_S)
        self._rate = rate if self._rate <= 0 else (1 - a) * self._rate + a * rate

    def _learn_entry(self, s: TelemetrySnapshot, now: float) -> None:
        """Remember where the car left the track for the pit lane.

        The sample is the last position seen **on track**, not the first one in
        the lane: the lane flag turns on some metres in, and the point we want to
        warn about is where the driver has to commit.

        Believed only when the car got there by **driving**. Two conditions,
        both physical: the lane frame is a few metres further round the lap than
        the last on-track frame, and it arrived within a fraction of a second.
        A teleport back to the garage fails both — and a poisoned sample here is
        persistent (it goes to disk) and produces the worst thing this module can
        do, which is say "pit entry just ahead" in the middle of a straight.
        """
        in_lane = bool(s.in_pit_lane or s.in_pit)
        if not in_lane:
            if s.speed_kmh >= _MOVING_KMH and 0.0 < s.lap_position < 1.0:
                self._last_track_pos = s.lap_position
                self._last_track_t = now
            self._was_in_lane = False
            return
        if not self._was_in_lane:
            self._was_in_lane = True
            prev = self._last_track_pos
            # Only if we actually watched it arrive. Starting a session parked in
            # the garage also reads as "in the lane", and there the last on-track
            # position is either missing or left over from another session.
            if (prev is not None
                    and (s.lap_position - prev) % 1.0 <= _ENTRY_MAX_STEP
                    and now - self._last_track_t <= _ENTRY_MAX_GAP_S):
                self.note_pit_entry(prev)
            self._last_track_pos = None
