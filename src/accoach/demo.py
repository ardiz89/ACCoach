"""A self-contained demo feed for the overlay / server, with no game running.

`DemoReader` replays a synthetic lap on a loop — a fast reference is seeded on
disk and the "live" lap is a bit slower with a lock-up in the first braking
zone, so a frontend shows a moving delta bar and real cues. Used by
``python -m accoach.server --demo`` to validate the overlay end to end.
"""

from __future__ import annotations

import tempfile

from .engine import CoachEngine
from .recording.lap import Lap, LapSample
from .recording.storage import save_lap
from .telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

CAR = "HONE Demo"
TRACK = "Demo Circuit"
_N = 300
_LAP_MS = 100_000
# Two corners (lo, hi, apex, vmin) by normalized position.
_CORNERS = ((0.20, 0.40, 0.31, 120.0), (0.62, 0.80, 0.71, 95.0))


def _profile(pos: float):
    """(speed, brake, throttle, steer) for the reference at this position."""
    spd, brake, thr, steer = 255.0, 0.0, 1.0, 0.0
    for lo, hi, apex, vmin in _CORNERS:
        if (lo - 0.05) <= pos <= hi:
            half = (hi - lo) / 2
            d = min(1.0, abs(pos - apex) / half)
            spd = vmin + (255.0 - vmin) * d
            brake = 0.85 if (lo - 0.04) <= pos < apex else 0.0
            thr = 1.0 if pos >= apex else 0.0
            if pos < apex:
                steer = 0.28 * (pos - lo) / max(1e-6, apex - lo)
            else:
                steer = 0.28 * (hi - pos) / max(1e-6, hi - apex)
            steer = max(0.0, steer)
    return spd, brake, thr, steer


def _reference_lap() -> Lap:
    samples = []
    for i in range(_N + 1):
        pos = i / _N
        spd, brake, thr, steer = _profile(pos)
        samples.append(LapSample(int(pos * _LAP_MS), pos, spd, thr, brake, steer,
                                 "4", 8000, 0.0, 0.0))
    return Lap(CAR, TRACK, SessionType.PRACTICE, _LAP_MS, True, samples=samples)


def _live_snapshots() -> list[TelemetrySnapshot]:
    """A slower lap: down on speed through corner 1, and a lock-up entering it."""
    snaps = []
    offset = 0
    for i in range(_N + 1):
        pos = i / _N
        spd, brake, thr, steer = _profile(pos)
        slip = (0.0, 0.0, 0.0, 0.0)
        # Through corner 1: carry less speed (accumulate loss) and lock the fronts
        # in its braking zone.
        if 0.16 <= pos <= 0.40:
            offset += 6
            spd = max(spd - 30.0, 90.0)
            if 0.16 <= pos < 0.31 and brake > 0.3:
                slip = (-0.45, -0.40, 0.0, 0.0)   # front lock-up
        s = TelemetrySnapshot.disconnected()
        s.connected = True
        s.status = ACStatus.LIVE
        s.session = SessionType.PRACTICE
        s.car_model = CAR
        s.track = TRACK
        s.lap_position = pos
        s.current_lap_ms = int(pos * _LAP_MS) + offset
        s.last_lap_ms = _LAP_MS + offset
        s.best_lap_ms = _LAP_MS
        s.speed_kmh = spd
        s.throttle = thr
        s.brake = brake
        s.steer_angle = steer
        s.slip_ratio = slip
        s.gear = "4"
        snaps.append(s)
    return snaps


class DemoReader:
    """Replays the synthetic live lap on a loop, like a SharedMemoryReader."""

    def __init__(self) -> None:
        self._snaps = _live_snapshots()
        self._i = 0
        self._laps = 0

    def read(self) -> TelemetrySnapshot:
        s = self._snaps[self._i]
        self._i += 1
        if self._i >= len(self._snaps):
            self._i = 0
            self._laps += 1
        # Stamp the completed-lap counter so the timing/HUD looks alive.
        s.completed_laps = self._laps
        return s

    def close(self) -> None:
        pass


def make_demo_engine() -> CoachEngine:
    """A CoachEngine wired to the demo feed, with the reference seeded on disk."""
    laps_dir = tempfile.mkdtemp(prefix="accoach_demo_")
    save_lap(_reference_lap(), laps_dir)
    return CoachEngine(reader=DemoReader(), voice=None, laps_dir=laps_dir)
