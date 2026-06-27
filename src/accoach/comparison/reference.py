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

from ..recording.lap import Lap


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
        for s in lap.samples:
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
