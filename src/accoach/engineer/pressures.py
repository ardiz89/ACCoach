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

from .classmap import CarClass, known_class

# Per-class hot-pressure window (target, tolerance) in psi.
#
# ``ROAD`` qui non c'e' piu', e non per dimenticanza. Nessun nome dice «questa e'
# una stradale»: ci si arrivava per esclusione, e per esclusione ci arrivavano
# anche le F1 senza «f1» nel nome, le LMP1 e la Huracan ST di ACC. La finestra
# di una categoria applicata a un'altra non e' una stima approssimativa, e'
# un'altra auto — lo dice gia' `coaching/tuning.py`, dove la voce tace fuori
# dalla GT3. E sull'unica stradale in quella tabella (M3 E92, 34.7 psi di media,
# «che e' la sua pressione di progetto») 30.0 ±1.5 avrebbe chiesto di toglierne
# quasi cinque. Quel numero resta nel profilo Road come valore di partenza per chi lo
# costruisce a mano; `pressure_window` non lo assegna piu' a nessuno.
_CLASS_WINDOW: dict[CarClass, tuple[float, float]] = {
    CarClass.GT3: (27.5, 0.7),       # ACC Pirelli slick
    CarClass.FORMULA: (22.0, 0.4),   # open-wheel slick, tighter
}

# Wet windows, per class. Only where a number can be sourced: ACC's wet Pirelli
# is documented at an optimum of 30.0 psi hot with a 29.5–31.0 band, and several
# independent guides agree on it (simracingsetup, Coach Dave, the ACC wiki). The
# open-wheel and road classes have no equivalent published figure and no wet lap
# in our archive, so they are absent — and absent means the engineer stands down
# rather than reaching for the dry number, which is 2.5 psi away and would be
# advice pointing the wrong way.
_CLASS_WET_WINDOW: dict[CarClass, tuple[float, float]] = {
    CarClass.GT3: (30.0, 0.75),
}

# Car-specific overrides (lowercased model id → window). Empty for now; fill in
# as real windows are measured.
_CAR_WINDOW: dict[str, tuple[float, float]] = {}

# (car_model, track) overrides for the rare case a car wants a different window
# at a specific circuit. Keyed (lower car, lower track).
_CAR_TRACK_WINDOW: dict[tuple[str, str], tuple[float, float]] = {}


def pressure_window(car_model: str,
                    track: str | None = None) -> tuple[float, float] | None:
    """Hot-pressure target window for a car (+ optional track), or ``None``.

    ``None`` vuol dire che non sappiamo che auto e', e chi chiama deve tacere
    sulle pressioni invece di prendere la finestra di un'altra categoria. Usa
    `known_class` e non `classify` apposta: `classify` risponde sempre, ed e'
    il motivo per cui una LMP1 riceveva la finestra di una stradale.
    """
    car = (car_model or "").strip().lower()
    if track:
        key = (car, track.strip().lower())
        if key in _CAR_TRACK_WINDOW:
            return _CAR_TRACK_WINDOW[key]
    if car in _CAR_WINDOW:
        return _CAR_WINDOW[car]
    return _CLASS_WINDOW.get(known_class(car_model))


def wet_pressure_window(car_model: str) -> tuple[float, float] | None:
    """The wet window for this car, or ``None`` when we don't have one.

    ``None`` is a real answer and the caller must treat it as one: the dry
    target is 2.5 psi below the wet one on a GT3, so falling back to it in the
    rain would not be a degraded answer, it would be a wrong one.
    """
    return _CLASS_WET_WINDOW.get(known_class(car_model))
