"""LapComparator: live delta vs a reference, lined up by track position."""
from accoach.comparison.delta import LapComparator, format_delta
from accoach.comparison.reference import Reference
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import ACStatus, SessionType

import synth


def _ref():
    return Reference(synth.build_lap())


def test_compare_none_when_reference_unusable():
    bare = Reference(Lap("c", "t", SessionType.PRACTICE, 0, True, samples=[]))
    cmp = LapComparator(bare)
    assert cmp.compare(synth.snap(pos=0.3, current_lap_ms=1000)) is None


def test_compare_none_when_not_live_or_in_pit():
    cmp = LapComparator(_ref())
    assert cmp.compare(synth.snap(pos=0.3, status=ACStatus.PAUSE)) is None
    assert cmp.compare(synth.snap(pos=0.3, in_pit=True)) is None
    assert cmp.compare(synth.snap(pos=0.3, connected=False)) is None


def test_positive_delta_when_slower():
    ref = _ref()
    cmp = LapComparator(ref)
    pos = 0.5
    ref_t = ref.time_at(pos)
    st = cmp.compare(synth.snap(pos=pos, current_lap_ms=int(ref_t) + 800))
    assert st is not None
    assert st.delta_ms > 0            # slower than reference
    assert not st.ahead


def test_negative_delta_when_faster():
    ref = _ref()
    cmp = LapComparator(ref)
    pos = 0.5
    ref_t = ref.time_at(pos)
    st = cmp.compare(synth.snap(pos=pos, current_lap_ms=int(ref_t) - 500))
    assert st is not None
    assert st.delta_ms < 0 and st.ahead


def test_predicted_lap_is_reference_plus_delta():
    ref = _ref()
    cmp = LapComparator(ref)
    pos = 0.4
    st = cmp.compare(synth.snap(pos=pos, current_lap_ms=int(ref.time_at(pos)) + 300))
    assert st is not None
    assert abs(st.predicted_lap_ms - (ref.lap_time_ms + st.delta_ms)) < 1.0
    assert st.reference_lap_ms == ref.lap_time_ms


def test_format_delta_signs():
    assert format_delta(0.0) == "+0.000"
    assert format_delta(1234.0) == "+1.234"
    assert format_delta(-456.0) == "-0.456"
