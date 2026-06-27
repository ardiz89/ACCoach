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

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .lap import Lap, LapSample

# Decimation: keep a sample when the car has moved this far around the track
# (~0.2% ≈ 10 m on a 5 km circuit) or this much time has passed. Dense enough
# for braking-point comparison, sparse enough to gzip a lap to a few KB.
_MIN_POS_DELTA = 0.002
_MIN_DT_MS = 100


@dataclass(slots=True)
class _Buffer:
    samples: list[LapSample]
    is_full: bool          # True if it started at a start/finish crossing
    last_pos: float
    last_t_ms: int


class LapRecorder:
    """Stateful: accumulates samples and emits a :class:`Lap` per completed lap."""

    def __init__(self) -> None:
        self._buf: _Buffer | None = None
        self._prev_completed: int | None = None
        self._car: str = ""
        self._track: str = ""

    def reset(self) -> None:
        self._buf = None
        self._prev_completed = None
        self._car = ""
        self._track = ""

    def _recording_allowed(self, s: TelemetrySnapshot) -> bool:
        return s.connected and s.status == ACStatus.LIVE and not s.in_pit

    def update(self, s: TelemetrySnapshot) -> Lap | None:
        """Consume one snapshot; return a finished lap or ``None``."""
        if not self._recording_allowed(s):
            self.reset()
            return None

        # A car or track change means a different session entirely.
        if (self._car and s.car_model != self._car) or (
            self._track and s.track != self._track
        ):
            self.reset()
        self._car, self._track = s.car_model, s.track

        completed = s.completed_laps
        finished: Lap | None = None

        # Detect the start/finish crossing via the lap counter.
        crossed = self._prev_completed is not None and completed > self._prev_completed
        self._prev_completed = completed

        if crossed and self._buf is not None:
            finished = self._finalize(self._buf, s)
            self._buf = None  # the incoming sample opens the next (full) lap below

        if self._buf is None:
            # A buffer opened by a crossing is a full lap; the first ever is not.
            self._buf = _Buffer(
                samples=[], is_full=crossed, last_pos=-1.0, last_t_ms=-_MIN_DT_MS,
            )

        self._maybe_append(self._buf, s)
        return finished

    def _maybe_append(self, buf: _Buffer, s: TelemetrySnapshot) -> None:
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
        return Lap(
            car_model=self._car,
            track=self._track,
            session=s.session,
            lap_time_ms=int(s.last_lap_ms),
            valid=buf.is_full,
            samples=buf.samples,
        )
