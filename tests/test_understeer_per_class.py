"""Understeer is judged against what the car's class normally rotates.

An absolute yaw/steer threshold meant different things on different classes: 0.9
asked a Formula car to fall to 36% of its normal rotation before it counted as
pushing, while a GT3 only had to reach 46%. Measured over recorded laps, the
class baselines are ~2.50 (Formula SF25) against ~1.95 (GT3 and road).
"""
from dataclasses import replace

import pytest

from accoach.coaching.balance import (
    _MIN_SPEED_KMH,
    _STEER_HARD,
    BalanceDetector,
    understeer_ratio_for,
)
from accoach.coaching.tuning import (
    UNDERSTEER_FRAC,
    tuning_for_car,
    tuning_for_class,
)
from accoach.engineer import CarClass
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=_MIN_SPEED_KMH + 40.0,
)


def _frame(yaw: float, steer: float = 0.30) -> TelemetrySnapshot:
    return replace(_BASE, steer_angle=steer, yaw_rate=yaw)


def test_formula_tolerates_less_push_than_gt3():
    formula = understeer_ratio_for(tuning_for_class(CarClass.FORMULA))
    gt3 = understeer_ratio_for(tuning_for_class(CarClass.GT3))
    assert formula > gt3, "a Formula car rotates more, so its push threshold sits higher"


def test_threshold_is_a_fraction_of_the_class_baseline():
    for cls in (CarClass.ROAD, CarClass.GT3, CarClass.FORMULA):
        t = tuning_for_class(cls)
        assert understeer_ratio_for(t) == pytest.approx(t.yaw_baseline * UNDERSTEER_FRAC)


def test_same_frame_reads_differently_by_class():
    """The frame that motivated the change: pushing for a Formula car, fine for a GT3.

    yaw/steer here is 1.0 — comfortably above the old absolute 0.9, so it used to
    be silence on every class, including the Formula car that was clearly pushing.
    """
    s = _frame(yaw=0.30, steer=0.30)          # ratio = 1.0

    formula = BalanceDetector(CarClass.FORMULA)
    gt3 = BalanceDetector(CarClass.GT3)
    assert formula._is_understeer(s) is True
    assert gt3._is_understeer(s) is False


def test_set_car_class_retunes_a_running_detector():
    d = BalanceDetector(CarClass.GT3)
    s = _frame(yaw=0.30, steer=0.30)
    assert d._is_understeer(s) is False
    d.set_car_class(CarClass.FORMULA)         # driver switched to a Formula car
    assert d._is_understeer(s) is True


def test_unknown_car_falls_back_to_gt3():
    unknown = BalanceDetector()
    gt3 = BalanceDetector(CarClass.GT3)
    assert unknown._understeer_ratio == gt3._understeer_ratio


def test_gt3_threshold_barely_moved():
    """The classes that were already working must not shift underneath the driver.

    Formula is what this change is for; GT3 and road cars sat right where the old
    absolute 0.9 put them, so their threshold should stay within a few percent.
    """
    for cls in (CarClass.GT3, CarClass.ROAD):
        assert understeer_ratio_for(tuning_for_class(cls)) == pytest.approx(0.9, abs=0.05)


def test_below_the_steering_gate_is_never_understeer():
    d = BalanceDetector(CarClass.FORMULA)
    assert d._is_understeer(_frame(yaw=0.0, steer=_STEER_HARD - 0.01)) is False


def test_the_f1_mods_resolve_to_formula():
    """gp_2025 & co. must reach the Formula tuning, or none of this applies to them."""
    assert tuning_for_car("gp_2025_sf25").yaw_baseline == \
           tuning_for_class(CarClass.FORMULA).yaw_baseline
