"""LapRecorder: turn a snapshot stream into completed laps."""
from accoach.recording.recorder import LapRecorder

import synth


def _drive_lap(rec, completed, n=30, current_base=0):
    """Feed one lap's worth of frames at the given completed-laps count.

    Returns the finished lap emitted on the *first* frame (the crossing), if any.
    """
    finished = None
    for i in range(n):
        pos = i / n
        out = rec.update(synth.snap(
            pos=pos, completed_laps=completed,
            current_lap_ms=current_base + i * 100,
            last_lap_ms=89000, speed_kmh=150.0,
        ))
        if out is not None:
            finished = out
    return finished


def test_first_lap_flagged_partial_then_full_laps():
    rec = LapRecorder()
    # Lap A: counter 0, no crossing yet -> nothing emitted.
    assert _drive_lap(rec, completed=0) is None
    # Counter ticks to 1 -> the buffer we filled is emitted, flagged partial.
    lapA = _drive_lap(rec, completed=1)
    assert lapA is not None and lapA.valid is False
    # Counter ticks to 2 -> a full lap (it started at the crossing).
    lapB = _drive_lap(rec, completed=2)
    assert lapB is not None and lapB.valid is True


def test_finished_lap_carries_last_lap_time_and_samples():
    rec = LapRecorder()
    _drive_lap(rec, completed=0)
    lap = _drive_lap(rec, completed=1)
    assert lap.lap_time_ms == 89000
    assert lap.car_model == "ferrari_488_gt3" and lap.track == "monza"
    assert len(lap.samples) > 1


def test_pit_resets_recording():
    rec = LapRecorder()
    _drive_lap(rec, completed=0)
    # Enter the pits: recording resets, so no lap is emitted at the next crossing.
    rec.update(synth.snap(pos=0.5, completed_laps=0, in_pit=True))
    assert rec._buf is None
    assert _drive_lap(rec, completed=1) is None   # prev_completed was reset


def test_car_change_resets_buffer():
    rec = LapRecorder()
    _drive_lap(rec, completed=0, n=10)
    before = rec._buf
    rec.update(synth.snap(pos=0.4, completed_laps=0, car_model="other_car"))
    # The in-progress buffer was dropped when the car changed.
    assert rec._buf is not before or rec._buf is None or len(rec._buf.samples) <= 1


def test_disconnected_emits_nothing():
    rec = LapRecorder()
    from accoach.telemetry.snapshot import TelemetrySnapshot
    assert rec.update(TelemetrySnapshot.disconnected()) is None


def test_full_lap_with_no_offtrack_is_clean():
    rec = LapRecorder()
    _drive_lap(rec, completed=0)            # partial
    _drive_lap(rec, completed=1)            # opens the full-lap buffer
    full = _drive_lap(rec, completed=2)     # emits the full lap
    assert full is not None and full.valid is True
    assert full.clean is True               # tyres_out stayed 0 all lap


def test_full_lap_with_offtrack_is_dirty():
    rec = LapRecorder()
    _drive_lap(rec, completed=0)
    # Fill the full-lap buffer (completed=1) with a 4-wheels-off excursion.
    for i in range(30):
        rec.update(synth.snap(
            pos=i / 30, completed_laps=1, current_lap_ms=i * 100,
            last_lap_ms=89000, tyres_out=(4 if i == 15 else 0),
        ))
    full = _drive_lap(rec, completed=2)
    assert full is not None and full.valid is True
    assert full.clean is False              # the off-track marked it dirty


def test_partial_lap_clean_is_unknown():
    rec = LapRecorder()
    partial = _drive_lap(rec, completed=0) or _drive_lap(rec, completed=1)
    # The first emitted lap is partial; cleanliness wasn't watched from the line.
    assert partial is not None and partial.valid is False
    assert partial.clean is None


def test_full_lap_drops_leading_prewrap_frame():
    # Regression: the sim bumps completed_laps one frame before pos wraps ~1.0->0,
    # so the frame that opens a full lap can still read ~1.0. Recorded as the
    # lap's first sample it collapses every position-indexed consumer. The opening
    # pre-wrap frame must be dropped so the lap starts near pos 0.
    rec = LapRecorder()
    _drive_lap(rec, completed=0)                  # partial
    # Cross into the full lap on a frame whose pos hasn't wrapped yet (0.998).
    rec.update(synth.snap(pos=0.998, completed_laps=1, current_lap_ms=0,
                          last_lap_ms=89000, speed_kmh=150.0))
    # The next frame has wrapped; fill the rest of the lap.
    for i in range(1, 30):
        rec.update(synth.snap(pos=i / 30, completed_laps=1,
                              current_lap_ms=i * 100, last_lap_ms=89000,
                              speed_kmh=150.0))
    assert rec._buf is not None and rec._buf.samples
    assert rec._buf.samples[0].pos < 0.5          # no leading ~1.0 poison frame


def test_decimation_thins_dense_samples():
    rec = LapRecorder()
    # Many frames at the same position and time should not all be stored.
    for _ in range(20):
        rec.update(synth.snap(pos=0.5, completed_laps=0,
                              current_lap_ms=1000, speed_kmh=100.0))
    assert rec._buf is not None
    assert len(rec._buf.samples) <= 2
