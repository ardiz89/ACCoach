"""Turn a stream of telemetry snapshots into completed laps.

Feed every snapshot to :meth:`LapRecorder.update`. The recorder buffers samples
and, each time the car crosses the start/finish line, returns the lap that just
finished (or ``None`` mid-lap). Drive it straight from a poll loop::

    recorder = LapRecorder()
    while True:
        lap = recorder.update(reader.read())
        if lap:
            storage.save_lap(lap)

Lap-boundary detection
----------------------
The sim's ``completed_laps`` counter increments exactly at the start/finish
line, and at that instant ``last_lap_ms`` holds the just-finished lap's time.
We watch that counter: when it goes up, the buffer we've been filling *is* that
lap. We never infer the boundary from a ``lap_position`` wrap alone, because the
position signal jitters around 0.0/1.0 and would double-trigger.

The very first buffer is almost always a partial lap — recording usually starts
somewhere mid-track — so the first completed lap is flagged ``is_full = False``
and the recorder hands it back but the caller can discard it. Subsequent laps,
which were buffered from the line, are full.

Recording pauses outside LIVE, in the pits, and on disconnect; any of those, or
a car/track change, resets the buffer so a lap never spans two sessions.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..logging_setup import get_logger
from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .lap import Lap, LapSample

_log = get_logger("recorder")

# Decimation: keep a sample when the car has moved this far around the track
# (~0.2% ≈ 10 m on a 5 km circuit) or this much time has passed. Dense enough
# for braking-point comparison, sparse enough to gzip a lap to a few KB.
_MIN_POS_DELTA = 0.002
_MIN_DT_MS = 100


# A lap is dirty once this many wheels leave the track (a real excursion). 1-2
# wheels clipping a kerb is legal; 3+ off is the track-limits / cut threshold.
_TYRES_OUT_DIRTY = 3

# Refusing to record while the car is clearly lapping means one of our flags is
# wrong. Warn once per stretch, after long enough that pit-lane speed limiters and
# formation laps don't trip it (~10-30 s depending on the acquisition rate).
_DRIVING_KMH = 60.0
_REFUSAL_WARN_FRAMES = 600

# Position wrap that marks the start/finish line. Wide margins on purpose: at
# 270 km/h a 13 Hz acquisition moves ~0.006 of a lap between frames, so the pair
# straddling the line can sit well inside these bounds.
_WRAP_FROM = 0.9
_WRAP_TO = 0.1

# A lap time we're willing to store. ACC reports 2147483647 (INT_MAX) for "no
# lap time yet", which is what the out lap carries at its own crossing; storing
# that as a duration would poison every statistic downstream.
_LAP_MS_MIN = 1_000
_LAP_MS_MAX = 3_600_000


def _clean_verdict(buf: "_Buffer") -> bool:
    """Did this lap stay inside the track limits?

    The two sims answer through different fields, and each leaves the other's at
    a constant — so this picks the one that's actually alive rather than merging
    them. ACC publishes its own verdict (``isValidLap``) and never fills
    ``numberOfTyresOut``: measured live at Monza with all four wheels off the
    tarmac, that counter read 0 on every frame. AC is the mirror image — it fills
    the counter and has no verdict to give.

    Trusting the sim where it speaks also means inheriting its rules, which is
    the right outcome: ACC's own track-limits geometry decides, not our guess at
    it from a wheel count.
    """
    if buf.saw_valid_flag:
        return not buf.saw_invalid
    return buf.max_tyres_out < _TYRES_OUT_DIRTY


@dataclass(slots=True)
class _Buffer:
    samples: list[LapSample]
    is_full: bool          # True if it started at a start/finish crossing
    last_pos: float
    last_t_ms: int
    max_tyres_out: int = 0  # worst off-track excursion seen during the lap
    saw_invalid: bool = False   # the sim dropped its lap-valid flag at some point
    saw_valid_flag: bool = False  # …and it was telling us about it at all


class LapRecorder:
    """Stateful: accumulates samples and emits a :class:`Lap` per completed lap."""

    def __init__(self) -> None:
        self._buf: _Buffer | None = None
        self._prev_completed: int | None = None
        self._car: str = ""
        self._track: str = ""
        self._prev_pos: float | None = None
        self._blocked_frames = 0        # consecutive frames refused while driving

    def reset(self) -> None:
        self._buf = None
        self._prev_completed = None
        self._prev_pos = None
        self._car = ""
        self._track = ""

    def _recording_allowed(self, s: TelemetrySnapshot) -> bool:
        # The whole pit lane, not just the box. `in_pit` is only true standing in
        # the garage, so an in-lap used to be recorded to the end and stored as an
        # ordinary timed lap — a real one (Imola 1:57.235 against a 1:46 best) sat
        # in the archive inflating the session's spread by 11 s. Resetting here
        # drops the in-lap and leaves the following out-lap partial, which is what
        # both of them are.
        return (s.connected and s.status == ACStatus.LIVE
                and not s.in_pit and not s.in_pit_lane)

    def _note_refusal(self, s: TelemetrySnapshot) -> None:
        """Say so in the log when we refuse to record a car that's plainly driving.

        Every gate in this codebase that stayed quiet turned into a bug report of
        the form "I drove and nothing happened" — and the recorder is the gate
        where that costs the most, because the session is unrepeatable. If one of
        the flags it trusts is ever misread on some title or content, this is what
        turns a silent lost session into one line naming the culprit.
        """
        if not (s.connected and s.speed_kmh > _DRIVING_KMH):
            self._blocked_frames = 0
            return
        self._blocked_frames += 1
        if self._blocked_frames == _REFUSAL_WARN_FRAMES:
            _log.warning(
                "not recording though the car is at %.0f km/h — status=%s "
                "in_pit=%s in_pit_lane=%s", s.speed_kmh, s.status.name,
                s.in_pit, s.in_pit_lane)

    def update(self, s: TelemetrySnapshot) -> Lap | None:
        """Consume one snapshot; return a finished lap or ``None``."""
        if not self._recording_allowed(s):
            self._note_refusal(s)
            self.reset()
            return None
        # Recording again: the stretch is over, so two separate near-misses can't
        # add up into a warning about a problem that isn't there.
        self._blocked_frames = 0

        # A car or track change means a different session entirely.
        if (self._car and s.car_model != self._car) or (
            self._track and s.track != self._track
        ):
            self.reset()
        self._car, self._track = s.car_model, s.track

        completed = s.completed_laps
        finished: Lap | None = None

        # Detect the start/finish crossing two ways, because neither is enough.
        #
        # The lap counter is the authoritative signal — except ACC does not count
        # the out lap. Measured at Monza: leaving the box and crossing the line
        # left completedLaps at 0, and it only reached 1 at the *second* crossing.
        # With the counter alone the buffer therefore ran straight through the out
        # lap AND the first flying lap, closed as one 128 s partial, and got
        # thrown away — so on ACC the first flying lap after every pit exit was
        # silently lost, and a two-lap run recorded nothing at all.
        #
        # The position wrap catches that crossing (measured: 1.000 -> 0.000 on the
        # same frame). It can't be the only signal either: it needs a frame near
        # each end, and a dropped frame at speed could straddle the line.
        wrapped = (self._prev_pos is not None
                   and self._prev_pos > _WRAP_FROM and s.lap_position < _WRAP_TO)
        counted = self._prev_completed is not None and completed > self._prev_completed
        crossed = counted or wrapped
        self._prev_completed = completed
        self._prev_pos = s.lap_position

        if crossed and self._buf is not None:
            finished = self._finalize(self._buf, s)
            self._buf = None  # the incoming sample opens the next (full) lap below

        if self._buf is None:
            # A buffer opened by a crossing is a full lap; the first ever is not.
            self._buf = _Buffer(
                samples=[], is_full=crossed, last_pos=-1.0, last_t_ms=-_MIN_DT_MS,
            )

        # Track the worst excursion on EVERY frame (not just decimated samples),
        # so a brief off between stored samples still marks the lap dirty.
        if s.tyres_out > self._buf.max_tyres_out:
            self._buf.max_tyres_out = s.tyres_out
        # …and the same for the sim's own verdict, which is what ACC gives us
        # instead. Latched: the flag resets at the line, so a lap is dirty if it
        # was ever dropped, not if it happens to be down at the closing frame.
        if s.lap_valid is not None:
            self._buf.saw_valid_flag = True
            if not s.lap_valid:
                self._buf.saw_invalid = True

        self._maybe_append(self._buf, s)
        return finished

    def _maybe_append(self, buf: _Buffer, s: TelemetrySnapshot) -> None:
        # A full lap opens exactly at the line, but the sim bumps completed_laps
        # one frame before it wraps normalizedCarPosition from ~1.0 back to 0.0,
        # so the opening frame can still read ~1.0. That pre-wrap frame belongs to
        # the lap that just closed; kept as this lap's first sample it poisons
        # every position-indexed consumer (Reference/detect_corners/sectors seed
        # their strictly-forward filter at ~1.0 and reject every later sample,
        # collapsing the lap to one point). Drop it — the next frame has wrapped.
        if not buf.samples and buf.is_full and s.lap_position > 0.5:
            return
        t = int(s.current_lap_ms)
        moved = abs(s.lap_position - buf.last_pos) >= _MIN_POS_DELTA
        waited = (t - buf.last_t_ms) >= _MIN_DT_MS
        if buf.samples and not (moved or waited):
            return
        buf.samples.append(LapSample.from_snapshot(s))
        buf.last_pos = s.lap_position
        buf.last_t_ms = t

    def _finalize(self, buf: _Buffer, s: TelemetrySnapshot) -> Lap:
        # At the crossing, last_lap_ms holds the time of the lap we just closed.
        # `clean` is known only for a full lap (we watched it from the line); a
        # partial lap stays unknown (None). Conditions are ~constant over a lap,
        # so the crossing frame is a fine snapshot of them.
        clean = _clean_verdict(buf) if buf.is_full else None
        # ACC reports 2147483647 for "no lap time yet" — which is exactly what the
        # out lap carries at its own crossing, now that the position wrap closes
        # laps the counter never counted. A lap we can't put a time on isn't a
        # timed lap, whatever the buffer thinks.
        lap_ms = int(s.last_lap_ms)
        timed = _LAP_MS_MIN <= lap_ms <= _LAP_MS_MAX
        return Lap(
            car_model=self._car,
            track=self._track,
            session=s.session,
            lap_time_ms=lap_ms if timed else 0,
            valid=buf.is_full and timed,
            samples=buf.samples,
            clean=clean,
            air_temp=s.air_temp,
            road_temp=s.road_temp,
            grip=s.surface_grip,
            tyre_compound=s.tyre_compound,
        )
