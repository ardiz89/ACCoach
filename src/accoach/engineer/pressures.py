"""Hot-pressure target windows per car class / car / track.

The tyre-pressure phase is the gate of the whole convergence, so a single
hardcoded 27.5 psi for every GT3 and every track is wrong (a 911 GT3 R and a 296
GT3 don't share a window, and the same car runs different cold pressures at Monza
vs Zandvoort). This table gives a per-class default with room for car- and
track-specific overrides; until we have measured windows it stays conservative
and is easy to extend.

Returns ``(target_psi, tol_psi)``. ``RaceEngineer(..., pressure_window=...)``
applies it to the pressure phase without mutating the shared profile.
"""

from __future__ import annotations

from .classmap import CarClass, classify

# Per-class hot-pressure window (target, tolerance) in psi.
_CLASS_WINDOW: dict[CarClass, tuple[float, float]] = {
    CarClass.GT3: (27.5, 0.7),       # ACC Pirelli slick
    CarClass.FORMULA: (22.0, 0.4),   # open-wheel slick, tighter
    CarClass.ROAD: (30.0, 1.5),      # street rubber, wider
}

# Car-specific overrides (lowercased model id → window). Empty for now; fill in
# as real windows are measured.
_CAR_WINDOW: dict[str, tuple[float, float]] = {}

# (car_model, track) overrides for the rare case a car wants a different window
# at a specific circuit. Keyed (lower car, lower track).
_CAR_TRACK_WINDOW: dict[tuple[str, str], tuple[float, float]] = {}


def pressure_window(car_model: str, track: str | None = None) -> tuple[float, float]:
    """Best-effort hot-pressure target window for a car (+ optional track)."""
    car = (car_model or "").strip().lower()
    if track:
        key = (car, track.strip().lower())
        if key in _CAR_TRACK_WINDOW:
            return _CAR_TRACK_WINDOW[key]
    if car in _CAR_WINDOW:
        return _CAR_WINDOW[car]
    return _CLASS_WINDOW[classify(car_model)]
