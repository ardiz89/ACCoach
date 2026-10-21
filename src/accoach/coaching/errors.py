"""Gli errori frequenti di un giro e di una sessione.

Solo un conteggio, nessuna regola nuova: bloccaggi e pattinamenti sono i
segmenti di :func:`diagnosis._lock_spin_segments` (la stessa regola del
rilevatore dal vivo), sotto e sovrasterzo sono le curve in cui
:func:`diagnosis.corner_symptoms` vede un sintomo di quel bilanciamento. Con
l'ABS acceso su ACC il bloccaggio fisico non avviene e il conto resta 0: e' la
verita', non va forzato.
"""
from __future__ import annotations

from ..engineer import Balance
from ..recording.lap import Lap
from ..track import Corner
from .diagnosis import _lock_spin_segments, corner_symptoms
from .tuning import tuning_for_car

ERRORS: tuple[str, ...] = ("lock", "spin", "understeer", "oversteer", "off")


def lap_errors(lap: Lap, corners: list[Corner]) -> dict[str, int]:
    """Quanti errori di ogni tipo in un giro (sempre tutte le chiavi di ERRORS).

    Sotto e sovrasterzo contano **curve**, non sintomi: una curva con sintomi in
    due fasi e' una curva sola. ``off`` e' 1 solo se il giro e' *noto* come
    tagliato (``clean is False``): ``None`` e' «non lo so», non «tagliato».
    """
    tuning = tuning_for_car(lap.car_model)
    lock, spin = _lock_spin_segments(lap.samples, tuning.spin_ratio)
    under = over = 0
    for c in corners:
        balances = {sym.balance for sym in corner_symptoms(lap.samples, c, tuning)}
        under += Balance.UNDERSTEER in balances
        over += Balance.OVERSTEER in balances
    return {"lock": lock, "spin": spin, "understeer": under, "oversteer": over,
            "off": 1 if lap.clean is False else 0}


def session_errors(per_lap: list[dict[str, int]]) -> list[tuple[str, int]]:
    """Somma per tipo sui giri: solo i tipi con almeno un errore, dal piu' frequente.

    A parita' di conteggio resta l'ordine di ERRORS (sort stabile)."""
    totals = {k: sum(d.get(k, 0) for d in per_lap) for k in ERRORS}
    return sorted(((k, n) for k, n in totals.items() if n > 0), key=lambda kn: -kn[1])
