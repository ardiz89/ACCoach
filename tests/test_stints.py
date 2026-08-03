"""The stint: where one tank ends, and what the pace did inside it.

Two things are being defended here. The first is that a **session is not a
stint** — the gap heuristic knows when you got up from the wheel and nothing
about when you refuelled. The second is the refusal: this module reports a pace
trend only when the slope clears its own error bar, because on real data it
usually does not, and a confident number over noise is the worst thing a coach
can hand a driver.
"""
import pytest

from accoach.stints import (MIN_TREND_LAPS, PACE_BAND, REFUEL_L, Stint,
                            pace_of, split_stints, tyre_trace)


def _lap(ms=120_000, *, valid=1, clean=1, start=None, end=None):
    row = {"path": f"l{ms}", "lap_time_ms": ms, "valid": valid, "clean": clean}
    if start is not None:
        row["fuel_start"] = start
    if end is not None:
        row["fuel_end"] = end
    return row


def _burning(n, first=60.0, per_lap=3.2, **kw):
    """``n`` laps on one tank, the way the recorder writes them."""
    out, tank = [], first
    for _ in range(n):
        out.append(_lap(start=tank, end=tank - per_lap, **kw))
        tank -= per_lap
    return out


# --- where a stint ends ----------------------------------------------------

def test_a_tank_that_only_falls_is_one_stint():
    stints = split_stints(_burning(10))
    assert len(stints) == 1
    assert len(stints[0].laps) == 10 and stints[0].fuel_known


def test_a_refuel_between_two_laps_starts_a_new_stint():
    """The case ``fuel_used`` cannot see: both laps burned a normal amount, and
    the tank went back up in the gap between them. Measured on the archive at
    720S/Monza — one lap ends at 55.61 L and the next starts at 58.79."""
    laps = _burning(2) + _burning(3, first=58.0)
    assert [len(s.laps) for s in split_stints(laps)] == [2, 3]


def test_a_refuel_inside_a_lap_starts_a_new_stint():
    laps = _burning(2) + [_lap(start=20.0, end=55.0)] + _burning(2, first=52.0)
    assert [len(s.laps) for s in split_stints(laps)] == [2, 3]


def test_the_fuel_falling_a_little_is_not_a_refuel():
    """Inside one stint the gap between one lap's end and the next lap's start
    measures ±0.01 L on the archive. The threshold has to sit far above that
    noise and far below the 3.18 L of the real refuel it has to catch."""
    laps = [_lap(start=60.0, end=56.8), _lap(start=56.81, end=53.6)]
    assert len(split_stints(laps)) == 1


def test_a_rise_smaller_than_the_threshold_does_not_split():
    laps = [_lap(start=60.0, end=56.8),
            _lap(start=56.8 + REFUEL_L * 0.8, end=53.6)]
    assert len(split_stints(laps)) == 1


# --- laps that never recorded fuel ----------------------------------------

def test_laps_without_the_channel_never_split_a_stint():
    """Absence of a reading is not evidence of a refuel."""
    laps = [_lap(), _lap(), _lap()]
    assert len(split_stints(laps)) == 1


def test_a_stint_nobody_could_check_says_so():
    """Pre-v11 laps may hide a refuel. The stint is still offered — it is the
    best available reading — but it must not be drawn as a verified fact."""
    assert split_stints([_lap(), _lap()])[0].fuel_known is False
    assert split_stints(_burning(2))[0].fuel_known is True


def test_one_lap_without_fuel_makes_the_whole_stint_unverified():
    assert split_stints(_burning(2) + [_lap()])[0].fuel_known is False


def test_the_litres_of_a_stint_are_measured_end_to_end():
    st = split_stints(_burning(5, first=60.0, per_lap=3.0))[0]
    assert st.fuel_used == 15.0
    assert st.fuel_start == 60.0 and st.fuel_end == 45.0


def test_a_stint_with_no_fuel_channel_reports_no_consumption():
    assert split_stints([_lap(), _lap()])[0].fuel_used is None


def test_no_laps_is_no_stints():
    assert split_stints([]) == []


# --- which laps count as pace ---------------------------------------------

def test_a_lap_off_the_pace_is_still_a_lap_you_drove_but_not_your_pace():
    """The 205 s lap in the archive is a spin, not a stint's pace: leaving it in
    moves the median by seconds and invents a collapse that never happened."""
    laps = [_lap(120_000)] * 5 + [_lap(206_000)]
    p = pace_of(Stint(laps))
    assert p.laps == 6 and p.counted == 5
    assert p.median_ms == 120_000


def test_a_cut_lap_cannot_set_the_pace():
    """Same rule the session view already applies: a cut lap is faster for a
    reason, so it can neither set the median nor bend the trend."""
    laps = [_lap(120_000)] * 4 + [_lap(110_000, clean=0)]
    assert pace_of(Stint(laps)).counted == 4


def test_an_incomplete_lap_cannot_set_the_pace():
    laps = [_lap(120_000)] * 4 + [_lap(90_000, valid=0)]
    assert pace_of(Stint(laps)).counted == 4


def test_the_band_is_measured_against_the_stint_median():
    inside = int(120_000 * (1 + PACE_BAND * 0.9))
    outside = int(120_000 * (1 + PACE_BAND * 1.5))
    p = pace_of(Stint([_lap(120_000)] * 5 + [_lap(inside), _lap(outside)]))
    assert p.counted == 6


def test_a_spoiled_median_does_not_drag_a_bad_lap_into_the_pace():
    """The five-lap stint on the archive: three of its laps are messes, so the
    median lands on one of them and pulls a 2:04 into a pace whose real value is
    1:55.9. The cut has to be repeated until it stops moving."""
    ms = [221_662, 124_952, 138_370, 115_902, 115_902]
    p = pace_of(Stint([_lap(v) for v in ms]))
    assert p.counted == 2
    assert p.median_ms == 115_902


def test_repeating_the_cut_leaves_a_healthy_stint_alone():
    """It buys the contaminated case only if it costs nothing on the ordinary
    one — every sound stint on disk keeps exactly the laps one pass kept."""
    ms = [118_980, 116_107, 205_907, 116_905, 117_930, 117_315, 116_682,
          118_450, 122_232]
    assert pace_of(Stint([_lap(v) for v in ms])).counted == 8


def test_a_stint_of_only_ruined_laps_reports_no_pace():
    p = pace_of(Stint([_lap(120_000, valid=0), _lap(130_000, valid=0)]))
    assert p.counted == 0 and p.median_ms is None and p.no_trend == "few_laps"


# --- the trend, and the refusal to state one ------------------------------

def test_a_handful_of_laps_gets_no_trend_at_all():
    """A line through three points has an error bar that means nothing. The
    archive shows the damage: a four-lap Imola run fits −2.18 s/lap ± 0.097,
    which reads as a confident gain and is a driver still warming up."""
    p = pace_of(Stint(_burning(MIN_TREND_LAPS - 1)))
    assert p.trend is None and p.no_trend == "few_laps"


def test_a_clean_decline_is_reported_with_its_direction():
    laps = [_lap(120_000 + i * 400) for i in range(8)]
    t = pace_of(Stint(laps)).trend
    assert t is not None and t.significant
    assert t.direction == "rising" and t.slope == pytest.approx(400, abs=1)


def test_a_clean_improvement_is_reported_as_such():
    laps = [_lap(124_000 - i * 400) for i in range(8)]
    t = pace_of(Stint(laps)).trend
    assert t.significant and t.direction == "falling"


def test_a_slope_smaller_than_its_own_noise_is_reported_as_flat():
    """The real 720S/Monza stint: +0.26 s/lap with a standard error of 0.22. It
    is a number, and it is not a finding — saying "your pace is dropping a
    quarter of a second a lap" here would be inventing a cause for scatter."""
    ms = [118_980, 116_107, 116_905, 117_930, 117_315, 116_682, 118_450, 122_232]
    t = pace_of(Stint([_lap(v) for v in ms])).trend
    assert t is not None, "a trend was computed"
    assert not t.significant and t.direction == "flat"
    assert abs(t.slope) < 500


def test_the_trend_is_fitted_against_laps_driven_not_laps_counted():
    """Dropping the spin in the middle must leave a hole in the x axis. Squashing
    it shortens the stint by a lap and steepens every slope through it."""
    laps = [_lap(120_000), _lap(120_400), _lap(206_000),
            _lap(121_200), _lap(121_600), _lap(122_000), _lap(122_400)]
    t = pace_of(Stint(laps)).trend
    assert t.slope == pytest.approx(400, abs=5)


def test_a_stint_run_at_one_pace_is_flat_not_silent():
    """"No measurable drift" is an answer, and a different one from "not enough
    laps" — the first says the tyres held, the second says come back with more."""
    p = pace_of(Stint([_lap(120_000 + (i % 2) * 60) for i in range(8)]))
    assert p.no_trend is None and p.trend is not None
    assert p.trend.direction == "flat"


# --- the tyres -------------------------------------------------------------

class _Sample:
    def __init__(self, c, p):
        self.tyre_core_temp = (c, c, c, c)
        self.tyre_pressure = (p, p, p, p)


class _Lap:
    def __init__(self, c, p):
        self.samples = [_Sample(c, p), _Sample(c, p)]


def test_the_tread_warming_across_a_stint_is_reported_per_lap():
    tr = tyre_trace([_Lap(70 + i * 2, 26.0) for i in range(6)])
    assert tr.core_c[0] == 70 and tr.core_c[-1] == 80
    assert tr.core_trend.significant and tr.core_trend.direction == "rising"


def test_a_dead_channel_is_missing_not_zero():
    """Formula laps on AC carry no pressures at all. Averaging the zeros in
    would print a tyre at 0 psi, which is the trap `grip` already fell into."""
    tr = tyre_trace([_Lap(80, 0.0) for _ in range(6)])
    assert tr.psi == [None] * 6 and tr.psi_trend is None
    assert tr.core_c == [80.0] * 6


def test_a_short_stint_gets_the_series_without_a_drift():
    tr = tyre_trace([_Lap(80, 26.0) for _ in range(MIN_TREND_LAPS - 1)])
    assert len(tr.core_c) == MIN_TREND_LAPS - 1
    assert tr.core_trend is None
