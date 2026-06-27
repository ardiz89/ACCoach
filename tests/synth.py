"""Shared synthetic-data builders for the test suite.

No game is needed: these construct believable snapshots and a 2-corner reference
lap (the same profile the web demo seeds) so comparison/coaching/debrief code can
be exercised deterministically.
"""
from __future__ import annotations

import math
from dataclasses import replace

from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

# A connected, live, practice snapshot to build frames from.
LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="ferrari_488_gt3", track="monza",
    max_rpm=8000, rpm=6000, gear="4",
)


def snap(pos: float = 0.0, **kw) -> TelemetrySnapshot:
    """A live snapshot at ``pos`` with any field overridden via kwargs."""
    return replace(LIVE, lap_position=pos, **kw)


# Two-corner track profile (corner 0 apex 0.31, corner 1 apex 0.71). This is the
# exact shape the analysis web demo uses, so corner detection finds both.
_CORNERS = [(0.22, 0.40, 0.31, 120.0), (0.62, 0.80, 0.71, 95.0)]
_ZONES = {0: (0.16, 0.40), 1: (0.58, 0.80)}


def _track_xz(pos: float):
    """A closed synthetic circuit (same as the web demo); periodic, joins at 0≡1."""
    a = 2 * math.pi * pos
    x = 300.0 * math.sin(a) + 70.0 * math.sin(2 * a)
    z = 210.0 * math.cos(a) - 50.0 * math.sin(3 * a)
    return x, z


def _sector_of(pos: float) -> int:
    """Three deliberately UNEQUAL sim sectors, so tests tell them from thirds."""
    if pos < 0.30:
        return 0
    if pos < 0.65:
        return 1
    return 2


def _profile(pos: float):
    spd, brake, thr, steer = 255.0, 0.0, 1.0, 0.0
    for lo, hi, apex, vmin in _CORNERS:
        if (lo - 0.05) <= pos <= hi:
            half = (hi - lo) / 2
            d = min(1.0, abs(pos - apex) / half)
            spd = vmin + (255.0 - vmin) * d
            brake = 0.85 if (lo - 0.04) <= pos < apex else 0.0
            thr = 1.0 if pos >= apex else 0.0
            steer = 0.28 * ((pos - lo) / (apex - lo) if pos < apex
                            else (hi - pos) / (hi - apex))
            steer = max(0.0, steer)
    return spd, brake, thr, steer


def build_lap(slow_corner: int | None = None, amt: int = 0,
              car: str = "ferrari_488_gt3", track: str = "monza",
              n: int = 401, valid: bool = True,
              clean: bool | None = None, compound: str = "") -> Lap:
    """A 2-corner lap. ``slow_corner`` (0/1) loses ~``amt`` km/h + time there.

    ``clean`` defaults to None (unknown), matching how a legacy lap deserializes.
    """
    samples, off = [], 0
    for i in range(n):
        pos = i / (n - 1)
        spd, brake, thr, steer = _profile(pos)
        cx, cz = _track_xz(pos)
        if slow_corner is not None:
            lo, hi = _ZONES[slow_corner]
            if lo <= pos <= hi:
                off += max(1, amt // 5)
                spd = max(spd - amt, 80.0)
                r = math.hypot(cx, cz) or 1.0   # ran wide: nudge the line outward
                cx += cx / r * amt * 0.18
                cz += cz / r * amt * 0.18
        samples.append(LapSample(int(pos * 100000) + off, pos, spd, thr, brake,
                                 steer, "4", 8000, 0.0, 0.0, car_x=cx, car_z=cz,
                                 current_sector=_sector_of(pos)))
    return Lap(car, track, SessionType.PRACTICE, 100000 + off, valid,
               samples=samples, clean=clean, tyre_compound=compound)
