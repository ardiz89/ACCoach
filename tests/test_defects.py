"""I difetti di guida: lo stesso reperto contato per giro e per sessione.

Il numero di sessione e' la media sui giri validi **contando gli zeri**: un
difetto che compare in un giro su due pesa la meta' di uno che compare sempre,
ed e' quello che la pagella deve dire.
"""
import pytest

from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, GripState, LapDebrief, LapNote
from accoach.coaching.defects import (
    CATEGORY_OF,
    DEFECTS,
    lap_defects,
    summarize,
    worst_corners,
)

BRAKE_LATER = CueCategory.BRAKE_LATER
CARRY_SPEED = CueCategory.CARRY_SPEED
TIME_LOSS = CueCategory.TIME_LOSS


def _loss(index, lost_ms, category=CARRY_SPEED, coast_s=0.0):
    return CornerLoss(index=index, entry_pos=0.1, apex_pos=0.2, exit_pos=0.3,
                      lost_ms=lost_ms, category=category, message="m",
                      grip=GripState(coast_s=coast_s))


def _debrief(*losses, notes=()):
    return LapDebrief(car_model="c", track="t", lap_time_ms=100_000,
                      reference_lap_ms=99_000, losses=list(losses),
                      notes=list(notes))


def test_a_lap_sums_each_defect_over_its_corners():
    d = _debrief(_loss(0, 200, BRAKE_LATER), _loss(3, 150, BRAKE_LATER),
                 _loss(5, 300, CARRY_SPEED), _loss(6, 90, TIME_LOSS))
    ld = lap_defects(d)
    assert ld.ms["brake_early"] == 350 and ld.ms["min_speed"] == 300
    assert ld.corners["brake_early"] == {0: 200, 3: 150}
    assert "time_loss" not in ld.ms              # non e' un difetto
    assert ld.corner_loss[6] == 90               # ma conta per «dove sbagli»
    assert ld.total_gap_ms == 1000


def test_lift_comes_from_the_lap_notes_and_coasting_from_the_grip():
    d = _debrief(_loss(0, 200, BRAKE_LATER, coast_s=0.4),
                 notes=[LapNote(kind="lift", message="", lost_ms=80)])
    ld = lap_defects(d)
    assert ld.ms["lift"] == 80 and ld.coast_s == pytest.approx(0.4)


def test_the_category_map_covers_the_five_corner_defects_only():
    assert set(CATEGORY_OF) == {"brake_early", "brake_late", "over_brake",
                                "throttle_late", "min_speed"}
    assert set(CATEGORY_OF) <= set(DEFECTS)


def test_the_session_number_is_the_mean_over_valid_laps_counting_zeros():
    laps = [lap_defects(_debrief(_loss(0, 300, BRAKE_LATER))),
            lap_defects(_debrief())]
    s = {x.key: x for x in summarize(laps)}["brake_early"]
    assert s.mean == 150 and s.laps_with == 1 and s.laps == 2
    assert s.corners == [(0, 150.0)]


def test_main_means_over_the_threshold_in_at_least_half_the_laps():
    hit = lap_defects(_debrief(_loss(0, 130, BRAKE_LATER)))
    miss = lap_defects(_debrief(_loss(0, 110, BRAKE_LATER)))
    assert {x.key: x for x in summarize([hit, miss])}["brake_early"].main
    assert not {x.key: x for x in summarize([hit, miss, miss])}["brake_early"].main


def test_ms_defects_by_mean_then_coasting_last_and_never_more_than_four():
    cats = [BRAKE_LATER, CueCategory.BRAKE_EARLIER, CueCategory.LESS_BRAKE,
            CueCategory.MORE_THROTTLE, CARRY_SPEED]
    laps = []
    for _ in range(4):
        losses = [_loss(i, 1000 - 100 * i, c, coast_s=5.0)
                  for i, c in enumerate(cats)]
        laps.append(lap_defects(_debrief(
            *losses, notes=[LapNote(kind="lift", message="", lost_ms=150)])))
    out = summarize(laps)
    assert [x.unit for x in out][-1] == "s" and out[-1].key == "coasting"
    assert len([x for x in out if x.main]) <= 4
    ms = [x.mean for x in out if x.unit == "ms"]
    assert ms == sorted(ms, reverse=True) and len(ms) == 6
    # il quinto in ordine non e' principale, nemmeno se supera la soglia
    assert not out[4].main and not out[-1].main


def test_zero_defects_are_left_out():
    assert summarize([lap_defects(_debrief())]) == []


def test_worst_corners_ranks_total_loss_per_lap():
    laps = [lap_defects(_debrief(_loss(2, 400, CARRY_SPEED), _loss(7, 100, TIME_LOSS)))]
    assert worst_corners(laps) == [(2, 400.0), (7, 100.0)]
    assert worst_corners(laps, n=1) == [(2, 400.0)]
