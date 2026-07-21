"""ACC doesn't count the out lap, so the counter alone loses a flying lap.

Measured at Monza with a 720S GT3, watching the shared memory frame by frame:

    pit exit → crossing #1   completedLaps stayed 0, iLastTime = 2147483647
               crossing #2   completedLaps 0 → 1, iLastTime = 128067
               crossing #3   completedLaps 1 → 2, iLastTime = 122937

With the lap counter as the only crossing signal, the buffer opened at pit exit
ran through the out lap *and* the first flying lap, closed at crossing #2 as one
128 s partial, and was thrown away. The first flying lap after every pit exit was
lost, and a two-lap run recorded nothing at all — silently, with no error.

The position wrap catches crossing #1 (measured: 1.000 → 0.000 on one frame). It
can't replace the counter: it needs a sample near each end of the lap.
"""
from dataclasses import replace

from accoach.recording.recorder import LapRecorder
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="mclaren_720s_gt3_evo", track="monza", speed_kmh=180.0,
    last_lap_ms=122_937,
)

_ACC_NO_TIME = 2_147_483_647       # what ACC reports for "no lap time yet"


def _lap_frames(completed: int, **kw):
    """One trip around, sampled every 5% — the shape the recorder sees."""
    return [replace(_LIVE, lap_position=p / 100, completed_laps=completed, **kw)
            for p in range(0, 100, 5)]


def _run(rec, frames):
    return [lap for f in frames if (lap := rec.update(f)) is not None]


def test_the_first_flying_lap_after_the_pits_survives():
    """The whole point: ACC leaves the counter at 0 through the out lap."""
    rec = LapRecorder()
    frames = _lap_frames(0, last_lap_ms=_ACC_NO_TIME)   # out lap, no time yet
    frames += _lap_frames(0)                            # flying lap, counter STILL 0
    frames += [replace(_LIVE, lap_position=0.0, completed_laps=1)]   # crossing #2
    timed = [lap for lap in _run(rec, frames) if lap.valid]
    assert len(timed) == 1, "the first flying lap must not be swallowed"
    assert timed[0].lap_time_ms == 122_937


def test_the_out_lap_itself_is_never_stored():
    rec = LapRecorder()
    frames = _lap_frames(0, last_lap_ms=_ACC_NO_TIME)
    frames += [replace(_LIVE, lap_position=0.0, completed_laps=0,
                       last_lap_ms=_ACC_NO_TIME)]
    assert [lap for lap in _run(rec, frames) if lap.valid] == []


def test_acc_no_time_is_never_stored_as_a_duration():
    """2147483647 ms is 24 days. Storing it would poison every statistic."""
    rec = LapRecorder()
    frames = _lap_frames(0) + _lap_frames(1)
    frames += [replace(_LIVE, lap_position=0.0, completed_laps=2,
                       last_lap_ms=_ACC_NO_TIME)]
    for lap in _run(rec, frames):
        assert lap.lap_time_ms != _ACC_NO_TIME
        if lap.lap_time_ms == 0:
            assert lap.valid is False, "a lap with no time is not a timed lap"


def test_the_counter_still_closes_a_lap_when_the_wrap_is_missed():
    """A dropped frame at speed can straddle the line — the counter covers it."""
    rec = LapRecorder()
    frames = _lap_frames(0)[:-2]                  # …0.85, 0.90 then nothing
    frames += [replace(_LIVE, lap_position=0.30, completed_laps=1)]   # jumped past
    frames += _lap_frames(1)[7:]
    frames += [replace(_LIVE, lap_position=0.0, completed_laps=2)]
    assert any(lap.valid for lap in _run(rec, frames))


def test_a_wrap_and_a_count_on_the_same_frame_close_one_lap():
    """AC does both at once; that must not double-close."""
    rec = LapRecorder()
    frames = _lap_frames(0) + _lap_frames(1) + _lap_frames(2)
    laps = _run(rec, frames)
    # Three trips, two of them closed by a crossing seen at the start of the next.
    assert len(laps) == 2
    assert [lap.valid for lap in laps] == [False, True]


def test_going_backwards_over_the_line_is_not_a_lap():
    """Only a forward wrap counts; reversing 0.05 → 0.95 must close nothing."""
    rec = LapRecorder()
    frames = [replace(_LIVE, lap_position=p, completed_laps=3)
              for p in (0.20, 0.10, 0.05, 0.95, 0.90)]
    assert _run(rec, frames) == []
