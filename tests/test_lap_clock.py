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
    """The Monza twin: samples spanning 224.4 s, filed as a 1:55.902."""
    got = trusted_lap_ms(115_902, _lap((30, 0.000), (224_385, 0.999)))
    assert got == 224_355


def test_a_lap_with_no_usable_clock_keeps_what_the_sim_said():
    """One sample, or a span that came out negative: nothing to appeal to, so
    the sim's answer stands rather than being replaced by a worse guess."""
    assert trusted_lap_ms(104_598, _lap((33, 0.0008))) == 104_598
    assert trusted_lap_ms(104_598, _lap((33, 0.0008), (9, 0.0005))) == 104_598


def test_the_tolerance_scales_with_the_lap():
    """5 s of slack on a one-minute lap is generous; on a three-minute lap it
    would be mean. Same fraction either way."""
    assert trusted_lap_ms(200_000, _lap((0, 0.0), (185_000, 0.999))) == 200_000
    assert trusted_lap_ms(200_000, _lap((0, 0.0), (100_000, 0.999))) == 100_000


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
