"""A recorded lap turned into a position-indexed lookup.

To show a live delta we need to answer, for any point on the track: *how long
had the reference lap taken to get here, and what was the car doing?* A recorded
:class:`~accoach.recording.lap.Lap` stores discrete samples, so :class:`Reference`
builds clean, strictly increasing position arrays from it and linearly
interpolates between samples on demand.

Sample positions jitter slightly and wrap from ~1.0 back to 0.0 at the line, so
we keep only strictly-forward-progressing samples when building the index; that
yields a monotonic curve that ``bisect`` can search without numpy.

The exposed :class:`ReferencePoint` carries everything the coaching layer needs
to attribute a cause — not just speed/throttle/brake but steering, lateral G,
per-wheel slip, ABS/TC intervention and yaw rate — so the analyzer can tell a
lock-up from a coast from understeer.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from ..recording.lap import Lap, strip_leading_wrap


@dataclass(slots=True)
class ReferencePoint:
    """What the reference lap was doing at a given track position."""

    t_ms: float          # elapsed lap time at this position
    speed_kmh: float
    throttle: float
    brake: float
    g_long: float
    g_lat: float
    steer_angle: float
    gear: str
    wheel_slip: tuple[float, float, float, float]
    abs_active: float
    tc_active: float
    yaw_rate: float


class Reference:
    """Position-indexed view over a reference lap with linear interpolation."""

    def __init__(self, lap: Lap) -> None:
        self.lap = lap
        self.lap_time_ms = lap.lap_time_ms

        # Keep only strictly forward-progressing samples for a monotonic index.
        self._pos: list[float] = []
        self._t: list[float] = []
        self._speed: list[float] = []
        self._throttle: list[float] = []
        self._brake: list[float] = []
        self._glong: list[float] = []
        self._glat: list[float] = []
        self._steer: list[float] = []
        self._gear: list[str] = []
        self._slip: list[tuple[float, float, float, float]] = []
        self._abs: list[float] = []
        self._tc: list[float] = []
        self._yaw: list[float] = []

        last_pos = -1.0
        for s in strip_leading_wrap(lap.samples):
            if s.pos <= last_pos:
                continue
            last_pos = s.pos
            self._pos.append(s.pos)
            self._t.append(float(s.t_ms))
            self._speed.append(s.speed_kmh)
            self._throttle.append(s.throttle)
            self._brake.append(s.brake)
            self._glong.append(s.g_long)
            self._glat.append(s.g_lat)
            self._steer.append(s.steer_angle)
            self._gear.append(s.gear)
            self._slip.append(s.wheel_slip)
            self._abs.append(s.abs_active)
            self._tc.append(s.tc_active)
            self._yaw.append(s.yaw_rate)

        self._anchor_endpoints()

    def _anchor_endpoints(self) -> None:
        """Anchor the index at pos=0 (t=0) and pos=1 (t=lap_time).

        Recorded samples start a hair after the line (pos≈0.003) and end before it
        (pos≈0.98) with t<lap_time. Without endpoints, ``time_at`` clamps to the
        last sample's time for the whole run-in to the line while the live clock
        keeps rising — inflating the delta by a growing bias near the finish.
        Endpoints reuse the nearest sample's channels; only pos and t are set."""
        chans = [self._speed, self._throttle, self._brake, self._glong, self._glat,
                 self._steer, self._gear, self._slip, self._abs, self._tc, self._yaw]
        if len(self._pos) < 2:
            return                       # too few real samples to be a reference

        if self._pos[0] > 0.0 and self._t[0] > 0.0:
            self._pos.insert(0, 0.0)
            self._t.insert(0, 0.0)
            for c in chans:
                c.insert(0, c[0])
        if self._pos[-1] < 1.0 and self.lap_time_ms > self._t[-1]:
            self._pos.append(1.0)
            self._t.append(float(self.lap_time_ms))
            for c in chans:
                c.append(c[-1])

    @property
    def usable(self) -> bool:
        # Need at least two points to interpolate a delta.
        return len(self._pos) >= 2

    def _bracket(self, pos: float) -> tuple[int, int, float]:
        """Return (i, j, frac): indices straddling ``pos`` and the 0..1 blend."""
        pos = min(max(pos, self._pos[0]), self._pos[-1])
        j = bisect.bisect_left(self._pos, pos)
        if j <= 0:
            return 0, 0, 0.0
        if j >= len(self._pos):
            last = len(self._pos) - 1
            return last, last, 0.0
        i = j - 1
        span = self._pos[j] - self._pos[i]
        frac = (pos - self._pos[i]) / span if span > 0 else 0.0
        return i, j, frac

    @staticmethod
    def _lerp(a: float, b: float, f: float) -> float:
        return a + (b - a) * f

    def time_at(self, pos: float) -> float:
        """Interpolated elapsed lap time (ms) the reference had at ``pos``."""
        i, j, f = self._bracket(pos)
        return self._lerp(self._t[i], self._t[j], f)

    def point_at(self, pos: float) -> ReferencePoint:
        i, j, f = self._bracket(pos)
        lerp = self._lerp
        slip = tuple(
            lerp(self._slip[i][w], self._slip[j][w], f) for w in range(4)
        )
        return ReferencePoint(
            t_ms=lerp(self._t[i], self._t[j], f),
            speed_kmh=lerp(self._speed[i], self._speed[j], f),
            throttle=lerp(self._throttle[i], self._throttle[j], f),
            brake=lerp(self._brake[i], self._brake[j], f),
            g_long=lerp(self._glong[i], self._glong[j], f),
            g_lat=lerp(self._glat[i], self._glat[j], f),
            steer_angle=lerp(self._steer[i], self._steer[j], f),
            gear=self._gear[i] if f < 0.5 else self._gear[j],
            wheel_slip=slip,  # type: ignore[arg-type]
            abs_active=lerp(self._abs[i], self._abs[j], f),
            tc_active=lerp(self._tc[i], self._tc[j], f),
            yaw_rate=lerp(self._yaw[i], self._yaw[j], f),
        )
