"""Build a ready-to-run :class:`RaceEngineer` for a given car (and track).

Picks the class profile (GT3 / Formula / Road), the car's hot-pressure window
and what one click is worth on it, in one call — the normal entry point for
callers (live engine or debrief).
"""

from __future__ import annotations

from .classmap import profile_for_car
from .core import NO_WINDOW, RaceEngineer
from .pressures import pressure_window
from .steps import steps_for


def engineer_for(car_model: str, track: str | None = None, *,
                 is_acc: bool | None = None, **kw) -> RaceEngineer:
    """``is_acc`` dice che gioco e', e non ha un valore di comodo.

    Lasciato a ``None`` l'Ingegnere misura e consiglia ma **non scrive**: fino
    al 13/10 questa funzione non chiedeva il gioco e trattava ogni auto come
    una di ACC, cioe' scriveva psi interi su Assetto Corsa credendoli decimi.
    Un chiamante che si dimentica di dirlo deve ottenere un Ingegnere prudente,
    non uno che indovina.
    """
    kw.setdefault("steps", steps_for(car_model, is_acc))
    # Lo scarto del ripartitore misurato sull'archivio: sono click di un file
    # di ACC, quindi solo se il gioco e' detto, ed e' ACC. Importato qui:
    # `fingerprint` tira dentro i box e i setup, che importano l'Ingegnere.
    if is_acc is True:
        from .fingerprint import MEASURED_BIAS_OFFSET
        kw.setdefault("bias_offset", MEASURED_BIAS_OFFSET.get(car_model))
    # Senza finestra — un'auto che non sappiamo classificare — la fase pressioni
    # non prende quella del profilo: lo dice e passa oltre. `None` al motore
    # vorrebbe dire «tieni quella del profilo», che e' il contrario.
    window = pressure_window(car_model, track)
    return RaceEngineer(
        profile_for_car(car_model),
        pressure_window=window if window is not None else NO_WINDOW,
        **kw,
    )
