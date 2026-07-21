"""The pit lane is not the track, and an in-lap is not a timed lap.

``isInPit`` is only true standing in the garage, so driving down the pit lane read
as ordinary running: the lap was recorded to the end and stored as a normal timed
lap. One is still in the archive — Imola 1:57.235 against a 1:46 best, `valid=1`,
`clean=1` — and it alone triples that session's σ (1.164 s → 3.648 s).

The field that does cover the lane, ``isInPitLane``, sits in the region where AC1
and ACC lay the graphics page out differently, so it needs the same split as
``surfaceGrip`` — read ACC-style on AC1 it lands past the end of the page.
"""
import ctypes
from dataclasses import replace

from accoach.recording.recorder import LapRecorder
from accoach.telemetry.reader import SharedMemoryReader
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot
from accoach.telemetry.structs import SPageFileGraphics

_ON_TRACK = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="car", track="track", speed_kmh=120.0,
)


def _frame(pos: float, completed: int, **kw) -> TelemetrySnapshot:
    return replace(_ON_TRACK, lap_position=pos, completed_laps=completed,
                   current_lap_ms=int(pos * 90_000), **kw)


def _timed(rec: LapRecorder, frames) -> list:
    """The laps a session would actually store — the engine keeps only `valid`."""
    return [lap for f in frames
            if (lap := rec.update(f)) is not None and lap.valid]


# --- the reader: same AC1/ACC split as surfaceGrip ------------------------

def _graphics(active_cars: int) -> SPageFileGraphics:
    g = SPageFileGraphics()
    g.activeCars = active_cars
    return g


def test_acc_reads_the_declared_field():
    g = _graphics(20)                       # a real car count => ACC layout
    g.isInPitLane = 1
    assert SharedMemoryReader._in_pit_lane(g) is True
    g.isInPitLane = 0
    assert SharedMemoryReader._in_pit_lane(g) is False


def test_ac1_reads_24_bytes_past_activecars():
    """On AC1 the flag sits between idealLineOn and surfaceGrip, not at 1236."""
    g = _graphics(0)                        # no car count => AC1 layout
    base = ctypes.addressof(g) + SPageFileGraphics.activeCars.offset
    ctypes.c_int.from_address(base + 24).value = 1
    assert SharedMemoryReader._in_pit_lane(g) is True
    # …and the ACC slot must not be what answers.
    g.isInPitLane = 0
    assert SharedMemoryReader._in_pit_lane(g) is True


def test_ac1_garbage_reads_as_on_track():
    g = _graphics(0)
    base = ctypes.addressof(g) + SPageFileGraphics.activeCars.offset
    ctypes.c_int.from_address(base + 24).value = 1078530011   # a float's bit pattern
    assert SharedMemoryReader._in_pit_lane(g) is False


def test_penalty_is_zero_on_ac1():
    """AC1 has no penalty field at all; ACC-style it's an out-of-page read."""
    g = _graphics(0)
    g.penalty = 7
    assert SharedMemoryReader._penalty(g) == 0
    assert SharedMemoryReader._penalty(_graphics(20)) == 0
    acc = _graphics(20)
    acc.penalty = 7
    assert SharedMemoryReader._penalty(acc) == 7


def test_grip_still_reads_where_it_did():
    """The offset constant was extracted; the behaviour must not have moved."""
    g = _graphics(0)
    base = ctypes.addressof(g) + SPageFileGraphics.activeCars.offset
    ctypes.c_float.from_address(base + 28).value = 0.875     # exact in float32
    assert SharedMemoryReader._surface_grip(g) == 0.875


# --- the recorder: the in-lap never becomes a lap -------------------------

def test_a_lap_that_ends_in_the_pit_lane_is_not_stored():
    """The Imola 1:57 case: a real lap right up to the pit entry, then the lane."""
    rec = LapRecorder()
    frames = [_frame(p / 100, 0) for p in range(90, 100, 5)]   # opening, partial
    frames += [_frame(p / 100, 1) for p in range(0, 90, 5)]    # a full lap begins
    frames += [_frame(0.92, 1, in_pit_lane=True),              # …turns into the pits
               _frame(0.97, 1, in_pit_lane=True),
               _frame(0.02, 2, in_pit=True)]
    assert _timed(rec, frames) == []


def test_the_out_lap_after_it_is_partial_and_discarded():
    rec = LapRecorder()
    frames = [_frame(0.60, 5, in_pit_lane=True), _frame(0.70, 5, in_pit_lane=True)]
    frames += [_frame(p / 100, 5) for p in range(75, 100, 5)]  # rejoined mid-lap
    frames += [_frame(p / 100, 6) for p in range(0, 100, 5)]   # first full lap
    frames += [_frame(0.01, 7)]                                # …and closes it
    laps = _timed(rec, frames)
    assert len(laps) == 1, "only the lap opened at the line counts"


def test_a_normal_lap_is_untouched():
    rec = LapRecorder()
    frames = [_frame(p / 100, 0) for p in range(90, 100, 5)]
    frames += [_frame(p / 100, 1) for p in range(0, 100, 5)]
    frames += [_frame(0.01, 2)]
    laps = _timed(rec, frames)
    assert len(laps) == 1
    assert laps[0].clean is True
