"""One crossing per pass, not one per signal.

The two crossing signals are a frame apart: the sim bumps the lap counter *before*
``normalizedCarPosition`` wraps. OR'ing them therefore fired twice at every normal
crossing — the counter closed the lap and opened the next buffer, and one frame
later the wrap closed that buffer too. A second lap, same lap time, zero samples,
one frame long.

Straight out of the user's log, four minutes apart::

    10:59:35  discarding a 123.732s lap with only 0 samples
    11:03:09  discarding a 121.220s lap with only 0 samples

The 20-sample floor caught them. It is a backstop, not a design: two zero-sample
files with a real lap time were already sitting in the archive with no known
cause, and this is that cause.
"""
from dataclasses import replace

from accoach.recording.recorder import StartLineWatcher, LapRecorder
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="ferrari_488_gt3_evo", track="monza", speed_kmh=180.0,
    last_lap_ms=123_732,
)


def test_the_counter_then_the_wrap_is_one_crossing():
    """The exact frame sequence a real crossing produces."""
    w = StartLineWatcher()
    w.crossed(0.98, 1)                       # approaching
    hits = [w.crossed(0.995, 2),             # counter bumps, still pre-wrap
            w.crossed(0.002, 2)]             # position wraps one frame later
    assert hits == [True, False]


def test_the_wrap_alone_still_fires():
    """ACC's out lap: the counter never moves, so the wrap is all there is."""
    w = StartLineWatcher()
    w.crossed(0.98, 0)
    assert w.crossed(0.002, 0) is True


def test_it_re_arms_once_the_car_is_clearly_mid_lap():
    w = StartLineWatcher()
    w.crossed(0.98, 1)
    assert w.crossed(0.002, 2) is True
    for p in (0.05, 0.2, 0.5, 0.8, 0.95):    # round we go
        w.crossed(p, 2)
    assert w.crossed(0.001, 3) is True, "the next lap must close too"


def test_it_does_not_re_arm_while_still_near_the_line():
    """The ends of the lap are exactly where the two signals disagree."""
    w = StartLineWatcher()
    w.crossed(0.98, 1)
    assert w.crossed(0.002, 2) is True
    assert w.crossed(0.05, 2) is False       # just past the line
    assert w.crossed(0.06, 3) is False, "a counter bump here is the same crossing"


def test_a_lap_is_not_finished_twice():
    """End to end, through the recorder: one lap in, one lap out.

    Before the latch this produced two — the real one and a zero-sample twin
    carrying the same lap time, which only the sample floor kept out of a file.
    """
    rec = LapRecorder()
    frames = [replace(_LIVE, lap_position=p / 100, completed_laps=1)
              for p in range(0, 100, 2)]
    frames += [replace(_LIVE, lap_position=0.995, completed_laps=2),  # counter
               replace(_LIVE, lap_position=0.002, completed_laps=2)]  # then wrap
    laps = [lap for f in frames if (lap := rec.update(f)) is not None]
    assert len(laps) == 1
    assert laps[0].samples, "and it's the one with the telemetry in it"
