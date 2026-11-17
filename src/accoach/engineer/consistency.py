"""Chi, in un gruppo di giri puliti, e' incostante.

Un giro pulito ma guidato diversamente dagli altri (stessa sessione, stesse
manopole) non dice nulla sull'assetto: ne' il suo tempo ne' i suoi sintomi si
possono attribuire alla macchina. Qui lo si riconosce dalla velocita' minima
nelle stesse curve, confrontata con la mediana degli altri giri del gruppo.

Modulo puro, senza I/O: ``LapStats`` serve solo per i tipi.
"""

from __future__ import annotations

from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # solo per i tipi: nessun import circolare con core
    from .core import LapStats

#: Quanto sotto la mediana (km/h di velocita' minima) per dire «piu' lento».
KMH = 5.0
#: In quante curve almeno, perche' sia il giro e non una curva sbagliata.
CORNERS = 3
#: Distanza massima fra due apici (frazione di giro) per dire «e' la stessa curva».
MATCH = 0.01
#: Mezzo click del ripartitore: sotto questa differenza e' la stessa regolazione.
_BIAS_TOL = 0.001


def same_dials(a: tuple, b: tuple) -> bool:
    """Uguali sui valori letti da entrambi; un valore non letto (< 0) non conta."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x < 0 or y < 0:
            continue
        if i == 3:  # ripartitore: float, si confronta entro mezzo click
            if abs(x - y) > _BIAS_TOL:
                return False
        elif x != y:
            return False
    return True


def _dist(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1.0 - d)  # il traguardo sta sul cerchio: 0,998 e 0,002 sono vicini


def slow_corners(
    lap: "LapStats",
    others: "list[LapStats]",
    *,
    kmh: float = KMH,
    match: float = MATCH,
) -> list[tuple[str, float]]:
    """(nome, scarto) delle curve dove ``lap`` e' piu' lento di oltre ``kmh``.

    Il riferimento e' la mediana della stessa curva negli altri giri, che regge
    a un altro giro storto; con meno di 2 altri non c'e' mediana da fidarsi.
    """
    out: list[tuple[str, float]] = []
    for apex, vmin, name in lap.corner_vmin:
        speeds = []
        for other in others:
            best = None
            for o_apex, o_vmin, _ in other.corner_vmin:
                d = _dist(apex, o_apex)
                if d <= match and (best is None or d < best[0]):
                    best = (d, o_vmin)  # piu' curve vicine: vale la piu' vicina
            if best is not None:
                speeds.append(best[1])
        if len(speeds) < 2:
            continue
        gap = median(speeds) - vmin
        if gap > kmh:
            out.append((name, gap))
    out.sort(key=lambda c: -c[1])
    return out


def inconsistent(
    laps: "list[LapStats]",
    *,
    kmh: float = KMH,
    corners: int = CORNERS,
    match: float = MATCH,
) -> dict[int, list[tuple[str, float]]]:
    """Indice del giro -> curve lente, per i giri con almeno ``corners`` curve lente.

    Ogni giro e' giudicato contro tutti gli altri in un solo passaggio: non si
    tolgono giri a catena, altrimenti il gruppo si svuoterebbe da solo.
    """
    if len(laps) < 3:
        return {}
    result: dict[int, list[tuple[str, float]]] = {}
    for i, lap in enumerate(laps):
        slow = slow_corners(lap, laps[:i] + laps[i + 1:], kmh=kmh, match=match)
        if len(slow) >= corners:
            result[i] = slow
    return result
