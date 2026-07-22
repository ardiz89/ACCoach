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

import math
from collections import deque
from dataclasses import dataclass

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .reference import Reference, ReferencePoint

# "Right now" window for the local delta: how much of the lap back to look when
# answering "am I gaining or losing in THIS corner?" (~4% of the track).
_LOCAL_WINDOW_POS = 0.04

# Braking-point marker: where the reference gets on the brakes, and how far ahead
# to start warning the driver.
_BRAKE_ONSET = 0.5         # ref brake crossing this (rising) = a braking point
_BRAKE_LOOKAHEAD_POS = 0.15  # only look this far ahead (track fraction)
_BRAKE_LOOKAHEAD_M = 160.0   # …and only show the marker within this distance


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
    brake_in_m: int | None = None  # metres to the reference's next braking point

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
        # Precompute the reference's braking points + a (pos, x, z) path for the
        # "brake in N m" marker. Empty if the reference has no world coords.
        self._brake_onsets, self._path = self._index_braking()
        # Position spans where the braking countdown is retired (corners the
        # driver has mastered). The engine fills this as the Focus coach clears
        # corners; empty means the crutch is on everywhere, as before.
        self._muted_spans: list[tuple[float, float]] = []

    def set_muted_spans(self, spans: list[tuple[float, float]]) -> None:
        """Corners whose braking countdown to suppress (lo, hi in track position).

        A braking onset inside any span stops being counted down to — the driver
        has shown they know that braking point and the marker is now clutter, the
        way a track guide's braking boards come off once you've learned them.
        """
        self._muted_spans = spans

    def _index_braking(self) -> tuple[list[float], list[tuple[float, float, float]]]:
        path: list[tuple[float, float, float]] = []
        onsets: list[float] = []
        prev_brake, last_pos = 0.0, -1.0
        for s in self.reference.lap.samples:
            if s.pos <= last_pos:
                continue
            last_pos = s.pos
            path.append((s.pos, s.car_x, s.car_z))
            if prev_brake < _BRAKE_ONSET <= s.brake:
                onsets.append(s.pos)
            prev_brake = s.brake
        has_coords = any(x or z for _, x, z in path)
        return (onsets if has_coords else [], path)

    def _xy_at(self, pos: float) -> tuple[float, float] | None:
        p = self._path
        if not p:
            return None
        if pos <= p[0][0]:
            return (p[0][1], p[0][2])
        for i in range(1, len(p)):
            if p[i][0] >= pos:
                a, b = p[i - 1], p[i]
                span = b[0] - a[0]
                f = 0.0 if span <= 0 else (pos - a[0]) / span
                return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]))
        return (p[-1][1], p[-1][2])

    def _is_muted(self, onset: float) -> bool:
        return any(lo <= onset <= hi for lo, hi in self._muted_spans)

    def _brake_in(self, pos: float) -> int | None:
        """Metres to the reference's next braking point ahead, or None if none is
        within the lookahead (chord distance on the reference's world path)."""
        nxt = next((o for o in self._brake_onsets
                    if o > pos + 0.005 and not self._is_muted(o)), None)
        if nxt is None or nxt - pos > _BRAKE_LOOKAHEAD_POS:
            return None
        a, b = self._xy_at(pos), self._xy_at(nxt)
        if a is None or b is None:
            return None
        m = math.hypot(a[0] - b[0], a[1] - b[1])
        return int(m) if m <= _BRAKE_LOOKAHEAD_M else None

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
            brake_in_m=self._brake_in(pos),
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
