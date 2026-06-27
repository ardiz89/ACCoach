"""Post-lap debrief: ranked corner losses, consistency, formatting."""
from accoach.coaching.analyzer import CornerStats
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import (
    build_lap_debrief,
    explain_loss,
    format_debrief,
    lap_time_consistency,
)
from accoach.comparison import Reference
from accoach.track import detect_corners

import synth


def _debrief(slow_corner=0, amt=30):
    ref_lap = synth.build_lap()
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    review = synth.build_lap(slow_corner=slow_corner, amt=amt)
    return build_lap_debrief(review, reference, corners), corners


def test_debrief_ranks_the_slow_corner_first():
    deb, _ = _debrief(slow_corner=0, amt=30)
    assert deb.losses, "expected at least one corner loss"
    assert deb.losses[0].index == 0
    assert deb.losses[0].lost_ms > 0
    assert deb.total_gap_ms > 0


def _stats(**kw):
    base = dict(lost_ms=200.0, throttle_live=0.6, throttle_ref=0.9, brake_live=0.5,
                brake_ref=0.2, min_speed_live=90.0, min_speed_ref=110.0,
                braking_early=False)
    base.update(kw)
    return CornerStats(**base)


def test_explain_loss_has_numbers_and_a_fix():
    for cat in (CueCategory.CARRY_SPEED, CueCategory.MORE_THROTTLE,
                CueCategory.LESS_BRAKE, CueCategory.BRAKE_LATER, CueCategory.TIME_LOSS):
        detail, fix = explain_loss(cat, _stats())
        assert detail and fix, f"{cat} should produce a detail and a fix"
    # Carry-speed detail cites the apex-speed gap.
    detail, _ = explain_loss(CueCategory.CARRY_SPEED, _stats())
    assert "km/h" in detail


def test_debrief_losses_carry_detail_fix_and_speeds():
    deb, _ = _debrief(slow_corner=0, amt=30)
    loss = deb.losses[0]
    assert loss.detail and loss.fix
    assert loss.min_speed_live > 0 and loss.min_speed_ref > 0


def test_losses_sorted_worst_first():
    deb, _ = _debrief()
    lost = [x.lost_ms for x in deb.losses]
    assert lost == sorted(lost, reverse=True)


def test_clean_lap_vs_itself_has_no_losses():
    ref_lap = synth.build_lap()
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    deb = build_lap_debrief(ref_lap, reference, corners)
    assert deb.losses == []
    assert deb.is_reference


def test_corner_loss_label_is_one_based():
    deb, _ = _debrief()
    assert deb.losses[0].label == "Curva 1"


def test_consistency_summary():
    c = lap_time_consistency([100000, 100500, 101000])
    assert c["n"] == 3
    assert c["best_ms"] == 100000
    assert c["spread_ms"] == 1000
    assert c["std_ms"] > 0


def test_consistency_ignores_nonpositive_and_handles_empty():
    assert lap_time_consistency([]) == {
        "n": 0, "best_ms": 0, "mean_ms": 0, "spread_ms": 0, "std_ms": 0.0}
    c = lap_time_consistency([0, -5, 95000])
    assert c["n"] == 1 and c["best_ms"] == 95000


def test_format_debrief_mentions_gap_and_worst_corner():
    deb, _ = _debrief()
    text = format_debrief(deb, consistency=lap_time_consistency([100500, 100600]))
    assert "Debrief" in text
    assert "Distacco" in text
    assert "Curva 1" in text
    assert "Costanza" in text
