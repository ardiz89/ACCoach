"""Post-lap debrief: ranked corner losses, consistency, formatting."""
import pytest

from accoach.coaching.analyzer import CornerStats
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import (
    build_lap_debrief,
    explain_cause,
    explain_loss,
    format_debrief,
    lap_time_consistency,
)
from accoach.comparison import Reference
from accoach.engineer import Balance, Phase, Speed, Symptom
from accoach.track import detect_corners

import synth


def test_debrief_content_translates_to_italian():
    sym = Symptom(Balance.UNDERSTEER, Phase.ENTRY, Speed.LOW)
    assert explain_cause(sym, "en") == "The car understeers on entry (slow corner)."
    assert explain_cause(sym, "it") == "L'auto sottosterza in ingresso (curva lenta)."
    st = CornerStats(lost_ms=300, throttle_live=0.5, throttle_ref=0.5,
                     brake_live=0.0, brake_ref=0.0, min_speed_live=120.0,
                     min_speed_ref=128.0, braking_early=False)
    detail_it, _ = explain_loss(CueCategory.CARRY_SPEED, st, "it")
    assert "Minima all'apex" in detail_it
    detail_en, _ = explain_loss(CueCategory.CARRY_SPEED, st, "en")
    assert "Minimum speed at apex" in detail_en


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
    assert deb.losses[0].label == "Corner 1"


def test_consistency_summary():
    c = lap_time_consistency([100000, 100500, 101000])
    assert c["n"] == 3
    assert c["best_ms"] == 100000
    assert c["spread_ms"] == 1000
    assert c["std_ms"] > 0


def test_consistency_uses_sample_stdev():
    """σ is the sample stdev (÷n-1), not the population one (÷n).

    These laps are a sample of how you drive, and ÷n understates the spread on
    exactly the small sets we deal with — ~11% at n=5. Here: deviations from the
    100500 mean are -500/0/+500, so ÷(n-1) gives sqrt(500000/2) ≈ 500.0 where
    ÷n gave ≈ 408.2.
    """
    c = lap_time_consistency([100000, 100500, 101000])
    assert c["std_ms"] == pytest.approx(500.0, abs=0.1)


def test_consistency_single_lap_has_no_spread():
    # One lap can't have a sample stdev — must be 0.0, not a ZeroDivisionError.
    c = lap_time_consistency([100000])
    assert c["n"] == 1
    assert c["std_ms"] == 0.0
    assert c["spread_ms"] == 0


def test_consistency_ignores_nonpositive_and_handles_empty():
    assert lap_time_consistency([]) == {
        "n": 0, "best_ms": 0, "mean_ms": 0, "spread_ms": 0, "std_ms": 0.0}
    c = lap_time_consistency([0, -5, 95000])
    assert c["n"] == 1 and c["best_ms"] == 95000


def test_format_debrief_mentions_gap_and_worst_corner():
    deb, _ = _debrief()
    text = format_debrief(deb, consistency=lap_time_consistency([100500, 100600]))
    assert "Debrief" in text
    assert "Gap" in text
    assert "Corner 1" in text
    assert "Consistency" in text


# --- visual braking landmark in the braking detail --------------------------
from types import SimpleNamespace

from accoach import trackdata
from accoach.coaching import debrief as _D


class _StepRef:
    """Reference that gets on the brakes at ``onset`` (step), for _braking_detail."""

    def __init__(self, onset):
        self._onset = onset

    def point_at(self, pos):
        return SimpleNamespace(brake=1.0 if pos >= self._onset else 0.0)


def _early_braking_case():
    # Driver brakes at 0.46; reference not until 0.50. World coords spread the two
    # onsets far enough apart that the earliness is >= 2 m (so the note fires).
    inside = [SimpleNamespace(pos=0.46, brake=0.6, car_x=0.0, car_z=0.0),
              SimpleNamespace(pos=0.50, brake=0.9, car_x=40.0, car_z=0.0)]
    lap = SimpleNamespace(track="monza", samples=inside)
    ref = _StepRef(0.50)
    refs = [SimpleNamespace(brake=0.95)]
    return lap, ref, inside, refs


def test_braking_detail_appends_landmark(monkeypatch):
    lap, ref, inside, refs = _early_braking_case()
    # Anchor the landmark exactly where the code computes the reference's onset,
    # so the test proves the wiring, not a hand-tuned position.
    ref_onset = _D._onset(inside, lambda s: ref.point_at(s.pos).brake)
    monkeypatch.setitem(trackdata._LANDMARKS, "monza",
                        [("al cordolo bianco-rosso", "at the white-and-red kerb", ref_onset)])
    txt = _D._braking_detail(lap, ref, inside, refs, CueCategory.BRAKE_LATER, "it")
    assert "al cordolo bianco-rosso" in txt      # visual reference present
    assert "m." in txt                            # …and the metres stay as anchor


def test_braking_detail_without_landmark_is_just_metres(monkeypatch):
    # Empty table (the shipped state) -> metres only, no landmark phrase.
    lap, ref, inside, refs = _early_braking_case()
    monkeypatch.setitem(trackdata._LANDMARKS, "monza", [])
    txt = _D._braking_detail(lap, ref, inside, refs, CueCategory.BRAKE_LATER, "it")
    assert "Anticipi la staccata" in txt
    assert "cordolo" not in txt
