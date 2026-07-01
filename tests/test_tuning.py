"""Per-class detector tuning resolver."""
from accoach.coaching.tuning import (
    DEFAULT_TUNING,
    tuning_for_car,
    tuning_for_class,
)
from accoach.engineer import CarClass


def test_class_table_is_ordered_by_stiffness():
    # Wheelspin tolerance and the low/high corner band both rise with grip.
    road = tuning_for_class(CarClass.ROAD)
    gt3 = tuning_for_class(CarClass.GT3)
    formula = tuning_for_class(CarClass.FORMULA)
    assert road.spin_ratio < gt3.spin_ratio < formula.spin_ratio
    assert road.speed_split_kmh < gt3.speed_split_kmh < formula.speed_split_kmh


def test_unknown_or_empty_car_falls_back_to_default():
    assert tuning_for_car("") is DEFAULT_TUNING
    assert tuning_for_car(None) is DEFAULT_TUNING
    assert DEFAULT_TUNING is tuning_for_class(CarClass.GT3)


def test_car_model_resolves_by_class():
    assert tuning_for_car("porsche_991_gt3_r").spin_ratio == 0.13     # GT3
    assert tuning_for_car("bmw_m3_e30").spin_ratio == 0.12            # road
    assert tuning_for_car("rss_formula_hybrid_2022").spin_ratio == 0.15  # formula
