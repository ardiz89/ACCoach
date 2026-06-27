"""Build a ready-to-run :class:`RaceEngineer` for a given car (and track).

Picks the class profile (GT3 / Formula / Road) and the car's hot-pressure window
in one call — the normal entry point for callers (live engine or debrief).
"""

from __future__ import annotations

from .classmap import profile_for_car
from .core import RaceEngineer
from .pressures import pressure_window


def engineer_for(car_model: str, track: str | None = None, **kw) -> RaceEngineer:
    return RaceEngineer(
        profile_for_car(car_model),
        pressure_window=pressure_window(car_model, track),
        **kw,
    )
