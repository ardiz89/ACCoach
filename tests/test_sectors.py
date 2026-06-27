"""sectors: real sim-sector boundaries, position fallback, and the ideal lap."""
from dataclasses import replace

from accoach.sectors import (
    ideal_lap,
    real_boundaries,
    sector_bounds,
    sector_spans,
    sector_times,
)

import synth


def test_real_boundaries_from_current_sector():
    # synth assigns unequal sectors at 0.30 / 0.65.
    lap = synth.build_lap()
    bs = real_boundaries(lap)
    assert len(bs) == 2
    assert abs(bs[0] - 0.30) < 0.02
    assert abs(bs[1] - 0.65) < 0.02


def test_real_boundaries_ignore_trailing_wrap_sample():
    # A real lap usually ends a few samples past start/finish still reporting the
    # LAST sector (a sample at pos~0 with the highest index). Earliest-position
    # logic would put that sector's boundary near 0; the forward-step logic must
    # ignore it and keep the true split.
    lap = synth.build_lap()
    last = lap.samples[-1]
    lap.samples.append(replace(last, pos=0.0008, current_sector=2))
    bs = real_boundaries(lap)
    assert len(bs) == 2
    assert abs(bs[0] - 0.30) < 0.02
    assert abs(bs[1] - 0.65) < 0.02      # not dragged down to ~0


def test_real_spans_used_when_available():
    lap = synth.build_lap()
    spans, real = sector_spans(lap)
    assert real is True
    assert len(spans) == 3
    assert spans[0][0] == 0.0 and spans[-1][1] == 1.0
    # Unequal, so not plain thirds.
    assert abs((spans[0][1] - spans[0][0]) - 1 / 3) > 0.01


def test_falls_back_to_thirds_without_sector_data():
    lap = synth.build_lap()
    for smp in lap.samples:           # wipe the sim sector channel
        smp.current_sector = -1
    spans, real = sector_spans(lap)
    assert real is False
    assert spans == sector_bounds(3)


def test_sector_times_sum_to_lap_time():
    lap = synth.build_lap()
    spans, _ = sector_spans(lap)
    times = sector_times(lap, spans)
    assert len(times) == 3
    assert sum(times) == lap.lap_time_ms


def test_ideal_lap_picks_best_per_sector():
    fast = synth.build_lap()                       # clean reference
    slow0 = synth.build_lap(slow_corner=0, amt=30)  # loses in sector 0/1
    spans, _ = sector_spans(fast)
    ideal = ideal_lap([fast, slow0], ["fast", "slow0"], spans)
    assert ideal is not None
    assert ideal.ideal_ms == sum(ideal.best_ms)
    # The clean lap is best everywhere here, so ideal == its time.
    assert ideal.ideal_ms <= fast.lap_time_ms
    assert all(src == "fast" for src in ideal.best_from)
