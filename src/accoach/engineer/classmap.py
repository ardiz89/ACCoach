"""Map a car model id to its engineer class (and thus its :class:`Profile`).

The class drives which engineer profile (GT3 / Formula / Road) and which
dedicated UI the driver gets. Detection is by substring against the AC/ACC car
model id (e.g. ``mclaren_720s_gt3_evo`` → GT3, ``f1_1990_mclaren`` → Formula,
``dodge_char_police`` → Road), with an explicit override table for the cars
whose id doesn't carry an obvious marker.
"""

from __future__ import annotations

from enum import Enum

from .core import Profile
from .profiles import FORMULA_PROFILE, GT3_PROFILE, ROAD_PROFILE


class CarClass(Enum):
    GT3 = "GT3"
    FORMULA = "Formula"
    ROAD = "Stradale"


# Substring markers (matched against the lowercased model id), most specific
# first. GT racing classes (gt4/gt2/gte) ride along with the GT3 profile as the
# closest fit until they get their own.
_FORMULA_MARKERS = (
    "formula", "f1_", "_f1", "f2_", "f3_", "f3000", "312t", "_98t", "indycar",
    "open_wheel", "tatuus", "dallara_f", "rss_formula", "lotus_98t", "lotus_exos",
    "gp_2025", "gp_2024", "gp_2023",  # modern F1 season-pack mods (e.g. gp_2025_sf25)
)
_GT_MARKERS = ("gt3", "gt4", "gt2", "gte", "gt_")

# Cars whose id gives no hint — set the class explicitly.
_OVERRIDES: dict[str, CarClass] = {
    "ferrari_312t": CarClass.FORMULA,
    "lotus_98t": CarClass.FORMULA,
}

_PROFILES: dict[CarClass, Profile] = {
    CarClass.GT3: GT3_PROFILE,
    CarClass.FORMULA: FORMULA_PROFILE,
    CarClass.ROAD: ROAD_PROFILE,
}


def classify(car_model: str) -> CarClass:
    """Best-effort engineer class for a car model id."""
    key = (car_model or "").strip().lower()
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    if any(m in key for m in _FORMULA_MARKERS):
        return CarClass.FORMULA
    if any(m in key for m in _GT_MARKERS):
        return CarClass.GT3
    return CarClass.ROAD


def profile_for(car_class: CarClass) -> Profile:
    return _PROFILES[car_class]


def profile_for_car(car_model: str) -> Profile:
    """Convenience: model id → its engineer Profile."""
    return profile_for(classify(car_model))
