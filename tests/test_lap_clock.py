"""A lap must not contradict its own clock.

At the start/finish line the sim resets `normalizedCarPosition`, `iCurrentTime`
and `iLastTime` on **different frames**. The codebase already knew this about
position (`crossed_start_line`, `strip_leading_wrap`); it did not know it about
the two clocks, and the archive shows what that cost:

* four laps opening with the previous lap's elapsed time at pos≈0.000 — one of
  them producing a *negative* measured duration;
* a Monza lap whose samples span 224.4 s filed as a 1:55.902, which is the
  previous lap's time. It sits in the catalogue as an identical twin of the real
  1:55.902 — two laps, one time, one of them a fiction.

The driver's report: numbers on screen that didn't match the game.
"""
from accoach.recording.lap import (
    LapSample,
    strip_stale_open,
    strip_trailing_wrap,
    trusted_lap_ms,
)
from accoach.recording.recorder import LapRecorder

import synth


def _s(t_ms, pos):
    return LapSample(t_ms, pos, 200.0, 1.0, 0.0, 0.0, "5", 8000, 0.0, 0.0)


def _lap(*pairs):
    return [_s(t, p) for t, p in pairs]


# --- the opening frame that still holds the previous lap's clock -----------

def test_a_lap_opening_with_the_previous_clock_is_trimmed():
    """Measured: laps opening at 69.6 s and 189.2 s, at pos 0.000."""
    samples = _lap((69639, 0.000), (120, 0.003), (2000, 0.02))
    assert [s.t_ms for s in strip_stale_open(samples)] == [120, 2000]


def test_an_inlap_that_really_starts_mid_lap_is_left_alone():
    """A partial lap legitimately opens with a big clock — but it RISES. That
    is the whole discriminator, exactly as `strip_leading_wrap` uses a falling
    position."""
    samples = _lap((40000, 0.40), (41000, 0.42), (42000, 0.44))
    assert len(strip_stale_open(samples)) == 3


def test_an_ordinary_lap_is_untouched():
    samples = _lap((30, 0.001), (140, 0.004), (250, 0.008))
    assert len(strip_stale_open(samples)) == 3


def test_the_recorder_does_not_write_that_frame_in_the_first_place():
    """The load-side guard exists for the archive; new laps shouldn't need it."""
    rec = LapRecorder()
    for i in range(30):                     # a partial lap, to prime the counter
        rec.update(synth.snap(pos=i / 30, completed_laps=0,
                              current_lap_ms=i * 2900, last_lap_ms=89000))
    # The crossing: position has wrapped, the lap timer hasn't.
    rec.update(synth.snap(pos=0.0004, completed_laps=1, current_lap_ms=88980,
                          last_lap_ms=89000, speed_kmh=150.0))
    rec.update(synth.snap(pos=0.004, completed_laps=1, current_lap_ms=120,
                          last_lap_ms=89000, speed_kmh=150.0))
    assert rec._buf is not None and rec._buf.samples
    assert rec._buf.samples[0].t_ms < 1000, "the stale clock never got in"


# --- the closing frame that already belongs to the next lap ---------------

def test_a_trailing_frame_past_the_line_is_trimmed():
    samples = _lap((100, 0.01), (99000, 0.998), (9, 0.0005))
    assert [round(s.pos, 4) for s in strip_trailing_wrap(samples)] == [0.01, 0.998]


def test_trailing_trim_does_not_eat_a_normal_ending():
    samples = _lap((100, 0.01), (50000, 0.5), (99000, 0.998))
    assert len(strip_trailing_wrap(samples)) == 3


# --- the declared lap time vs the lap's own clock -------------------------

def test_a_time_that_matches_the_samples_is_believed():
    assert trusted_lap_ms(100_000, _lap((0, 0.0), (99_940, 0.999))) == 100_000


def test_the_usual_shortfall_is_not_a_contradiction():
    """The last sample lands just before the line, so the measured span always
    runs a little short. Across 59 real laps that shortfall is at most 1.36 s;
    the failures this catches are 104, 108 and 118 s."""
    assert trusted_lap_ms(70_849, _lap((108, 0.002), (69_597, 0.999))) == 70_849


def test_a_time_belonging_to_another_lap_is_replaced_by_the_measured_one():
    """The Monza twin: samples spanning 224.4 s, filed as a 1:55.902.

    The replacement is the lap's clock projected to the line, not the samples'
    raw span: the span drops the sliver at BOTH ends and so understates by more.
    Same defect, same answer, whichever half of it we caught."""
    got = trusted_lap_ms(115_902, _lap((30, 0.000), (224_385, 0.999)))
    assert got == 224_610


def test_a_lap_with_no_usable_clock_keeps_what_the_sim_said():
    """One sample, or a span that came out negative: nothing to appeal to, so
    the sim's answer stands rather than being replaced by a worse guess."""
    assert trusted_lap_ms(104_598, _lap((33, 0.0008))) == 104_598
    assert trusted_lap_ms(104_598, _lap((33, 0.0008), (9, 0.0005))) == 104_598


def test_the_tolerance_scales_with_the_lap():
    """5 s of slack on a one-minute lap is generous; on a three-minute lap it
    would be mean. Same fraction either way."""
    assert trusted_lap_ms(200_000, _lap((0, 0.0), (185_000, 0.999))) == 200_000
    assert trusted_lap_ms(200_000, _lap((0, 0.0), (100_000, 0.999))) == 100_100


# --- what it buys, end to end --------------------------------------------

def test_the_reference_no_longer_thinks_it_took_a_minute_to_reach_the_line():
    """The cost of the stale opening frame, in the place the driver sees it: a
    reference indexed at pos≈0 with t≈70 s puts every live delta out by that
    much, for the whole lap."""
    from accoach.comparison import Reference
    from accoach.recording.lap import Lap
    from accoach.telemetry.snapshot import SessionType

    good = synth.build_lap()
    poisoned = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE,
                   good.lap_time_ms, True,
                   samples=[_s(69_639, 0.0)] + list(good.samples[1:]))
    # Straight through the same sanitiser the loader runs.
    poisoned.samples = strip_stale_open(poisoned.samples)
    assert Reference(poisoned).time_at(0.001) < 1000


# --- the same defect, the size of the gap between two laps ----------------
#
# The Monza twin above is the loud version: an error of a hundred seconds, which
# a tolerance of 5 s or 10 % of the lap cannot miss. The quiet version is the
# common one, and it went unnoticed for a month. When you are lapping on the pace
# two consecutive laps differ by tenths, so the SAME stale read puts the lap out
# by tenths — and 5 s of slack sails straight past it.
#
# Measured over the whole real archive on 20/08/2026 (99 laps). Comparing each
# declared time against the lap's own clock projected to the line:
#
#     91 healthy laps          -68 .. +113 ms
#     7 laps whose declared time repeats the previous lap's
#                              -108546, -654, -266, -232, -175, +440, +2734 ms
#
# Every duplicate is outside the healthy band and no healthy lap is inside the
# defect's — but the two nearest neighbours are 113 and 175, so magnitude alone
# is not enough to separate them, and a second family (a lap whose SAMPLES have
# the hole, not its declared time — `clock_covers_lap` in coaching/trends.py)
# lives in the same range with the opposite repair. So the discriminator is the
# defect's own signature: the sim is still publishing the number it was already
# publishing before the crossing.

def test_a_time_the_sim_never_republished_is_replaced():
    """Monza 14/08, the lap that cost the least and mattered the most: filed as
    a 1:55.185 — to the millisecond the lap before — while its own clock reads
    115.360 s at the line. 175 ms, against an engineer that accepts or reverts a
    setup change on a band of 173."""
    got = trusted_lap_ms(115_185, _lap((32, 0.0), (115_130, 0.998), (115_360, 1.0)),
                         previous=115_185)
    assert got == 115_360


def test_and_the_loud_one_from_the_same_night():
    """The other of the two, 2.75 s out: the previous lap was simply slower."""
    got = trusted_lap_ms(117_855, _lap((20, 0.0), (115_000, 0.9989), (115_105, 0.9998)),
                         previous=117_855)
    # The samples' own answer, plus the sliver of track left to the line.
    assert 115_100 <= got <= 115_200


def test_two_laps_that_really_took_the_same_time_are_both_believed():
    """Repeating a lap time to the millisecond is rare, not impossible, and the
    signature alone cannot tell it from the defect. The lap's own clock can: here
    it agrees, so the sim's answer stands."""
    got = trusted_lap_ms(115_185, _lap((20, 0.0), (115_120, 0.9995), (115_150, 0.9999)),
                         previous=115_185)
    assert got == 115_185


def test_a_lap_whose_time_the_sim_did_republish_is_left_alone():
    """The shortfall of a healthy lap is the same size as the defect. What tells
    them apart is that the sim answered with a different number than before."""
    got = trusted_lap_ms(115_185, _lap((32, 0.0), (115_130, 0.998), (115_360, 1.0)),
                         previous=117_855)
    assert got == 115_185


def test_without_the_sim_s_previous_answer_the_quiet_version_is_invisible():
    """Which is the honest limit of the load path: a file on disk carries no
    record of what the sim was saying a frame earlier, so an archived lap is
    still judged by the loud rule alone."""
    got = trusted_lap_ms(115_185, _lap((32, 0.0), (115_130, 0.998), (115_360, 1.0)))
    assert got == 115_185


def _drive_lap(rec, *, completed, dur_ms, last_ms, n=400):
    """One lap's worth of frames; returns the lap emitted at its crossing.

    Dense on purpose (n=400): the projection to the line only speaks for the
    sliver of track past the last sample, and a 40-frame lap leaves 2.5 % of the
    circuit there — a fixture coarser than anything the recorder ever sees.
    """
    finished = None
    for i in range(n):
        out = rec.update(synth.snap(
            pos=i / n, completed_laps=completed, current_lap_ms=int(i / n * dur_ms),
            last_lap_ms=last_ms, speed_kmh=150.0,
        ))
        if out is not None:
            finished = out
    return finished


def test_the_recorder_does_not_stamp_a_lap_with_the_time_of_the_one_before():
    """End to end, the shape of the two Monza laps of 14/08: the sim is still
    publishing 1:57.855 when the next lap closes, and that lap took 1:55.1."""
    rec = LapRecorder()
    _drive_lap(rec, completed=0, dur_ms=117_855, last_ms=117_855)   # partial
    _drive_lap(rec, completed=1, dur_ms=115_100, last_ms=117_855)
    lap = _drive_lap(rec, completed=2, dur_ms=115_000, last_ms=117_855)
    assert lap is not None
    assert lap.lap_time_ms != 117_855, "the previous lap's time, read again"
    assert 115_000 <= lap.lap_time_ms <= 115_200


def test_and_believes_the_sim_the_moment_it_answers_with_a_new_number():
    rec = LapRecorder()
    _drive_lap(rec, completed=0, dur_ms=117_855, last_ms=117_855)
    _drive_lap(rec, completed=1, dur_ms=115_100, last_ms=117_855)
    lap = _drive_lap(rec, completed=2, dur_ms=115_000, last_ms=115_100)
    assert lap.lap_time_ms == 115_100
