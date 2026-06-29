"""Live delta against a reference lap.

Feed each snapshot to :meth:`LapComparator.compare` and it returns where you
stand versus the reference, lined up by track position:

* ``delta_ms`` — your elapsed lap time minus the reference's at the same point.
  Positive means you're **slower** (losing time), negative means **faster**.
* ``predicted_lap_ms`` — reference lap time plus the current delta, i.e. what
  you'd finish on if you held this gap.

The comparison is purely positional, so it's valid even when your lap time and
the reference's differ — that's the whole point of keying samples by position.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .reference import Reference, ReferencePoint

# "Right now" window for the local delta: how much of the lap back to look when
# answering "am I gaining or losing in THIS corner?" (~4% of the track).
_LOCAL_WINDOW_POS = 0.04


@dataclass(slots=True)
class DeltaState:
    """One instant of live-vs-reference standing."""

    pos: float
    delta_ms: float            # + slower than reference, - faster (cumulative)
    predicted_lap_ms: float
    reference_lap_ms: int
    live_speed_kmh: float
    reference_point: ReferencePoint
    local_delta_ms: float = 0.0  # gained(+)/lost(-)… see local_losing: time made up
    #                              or given away over the last _LOCAL_WINDOW_POS

    @property
    def ahead(self) -> bool:
        return self.delta_ms < 0.0

    @property
    def local_losing(self) -> bool:
        """True if you're losing time *right now* (this micro-sector)."""
        return self.local_delta_ms > 0.0


class LapComparator:
    """Stateful comparator bound to one reference lap."""

    def __init__(self, reference: Reference) -> None:
        self.reference = reference
        # Rolling (pos, cumulative-delta) history for the local delta. Bounded so a
        # long lap can't grow it without limit; cleared at each lap wrap.
        self._hist: deque[tuple[float, float]] = deque(maxlen=600)
        self._last_pos = -1.0

    def compare(self, s: TelemetrySnapshot) -> DeltaState | None:
        """Return the live delta, or ``None`` when no meaningful comparison exists."""
        if not self.reference.usable:
            return None
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            return None

        # At the start/finish line the sim resets the position and the lap timer on
        # slightly different frames; for that one frame they disagree and the delta
        # would spike by ~a full lap (and with it predicted_lap_ms). Skip it.
        ref_lap = self.reference.lap_time_ms
        if ref_lap > 0:
            half = ref_lap * 0.5
            wrapped = ((s.lap_position < 0.05 and s.current_lap_ms > half) or
                       (s.lap_position > 0.95 and s.current_lap_ms < half))
            if wrapped:
                return None

        ref_t = self.reference.time_at(s.lap_position)
        delta = float(s.current_lap_ms) - ref_t

        pos = s.lap_position
        if pos < self._last_pos:          # new lap → the rolling window restarts
            self._hist.clear()
        self._last_pos = pos
        local = self._local_delta(pos, delta)
        self._hist.append((pos, delta))

        return DeltaState(
            pos=pos,
            delta_ms=delta,
            predicted_lap_ms=self.reference.lap_time_ms + delta,
            reference_lap_ms=self.reference.lap_time_ms,
            live_speed_kmh=s.speed_kmh,
            reference_point=self.reference.point_at(pos),
            local_delta_ms=local,
        )

    def _local_delta(self, pos: float, delta: float) -> float:
        """Cumulative delta now minus what it was ~one window of track back, i.e.
        the time gained/lost *in this stretch*. 0 until the window has filled."""
        target = pos - _LOCAL_WINDOW_POS
        if not self._hist or self._hist[0][0] > target:
            return 0.0
        past = None
        for p, d in self._hist:
            if p <= target:
                past = d
            else:
                break
        return delta - past if past is not None else 0.0


def format_delta(delta_ms: float) -> str:
    """Render a delta as ``+0.123`` / ``-0.456`` seconds."""
    return f"{delta_ms / 1000.0:+.3f}"
