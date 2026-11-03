"""Il gesto migliore di ogni curva per chi rivede un giro: report e Home.

Il report (``api.py``) e la Home dell'hub (``hub_home.py``) mostrano lo stesso
giro, e prima la Home lo misurava col solo principale mentre il report usava il
gesto migliore di ogni curva: la stessa curva aveva due cause e due perdite. Il
bacino, la sua cache e la regola su quando vale stanno qui, una volta sola, e
li importano tutti e due. Il motore dal vivo no: carica il suo bacino in un
thread (``engine.py``) e lo tiene aggiornato coi giri che salvi.

Le guardie sono quelle del report: solo contro il riferimento eletto, mai
contro un giro PRO, il giro rivisto escluso dalle offerte, e un errore vuol
dire None (vale il principale), mai una pagina che non si apre.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path

from .coaching.corner_refs import POOL_SIZE, CornerBests
from .comparison import Reference
from .recording import load_lap
from .recording.lap import Lap
from .recording.storage import pool_lap_ok, reference_pool_paths

_log = logging.getLogger(__name__)

#: Quanti giri del bacino si tengono in memoria. Due bacini pieni: basta per
#: passare da un giro all'altro della stessa pista senza ricaricare niente.
POOL_CACHE_SIZE = 2 * POOL_SIZE


def conditions_of(row: dict | None) -> dict:
    """The conditions a lap was driven in, with "never recorded" as absence.

    A zero temperature, a zero grip and an empty compound all mean the same
    thing — the field wasn't there when this lap was saved — and every rule
    downstream treats unknown as "can't be called similar".
    """
    row = row or {}
    return {
        "road_temp": row.get("road_temp") or None,
        "grip": row.get("grip") or None,
        "compound": row.get("tyre_compound") or None,
    }


class PoolCache:
    """I giri del bacino già caricati, per file e data di modifica.

    Il report costruisce il bacino a ogni ``/api/analysis``, e la vista «Come
    si fa» ne chiede diverse insieme: ricaricare venti file ogni volta è il
    tempo che il pilota aspetta. Un file riscritto ha un'altra data e si
    ricarica. FastAPI serve le chiamate su più thread, quindi un lucchetto; il
    caricamento sta fuori dal lucchetto, così un file lento non ferma gli altri.
    I giri si leggono e basta: nessuno li modifica.
    """

    def __init__(self, size: int = POOL_CACHE_SIZE) -> None:
        self._size = size
        self._laps: OrderedDict[tuple[str, int], Lap] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, path: str) -> Lap | None:
        try:
            key = (str(path), os.stat(path).st_mtime_ns)
        except OSError:
            return None
        with self._lock:
            lap = self._laps.get(key)
            if lap is not None:
                self._laps.move_to_end(key)
                return lap
        try:
            lap = load_lap(path)
        except Exception:  # noqa: BLE001 - un file rotto si salta, come nel bacino
            _log.debug("pool lap %s does not load; skipped", path, exc_info=True)
            return None
        with self._lock:
            self._laps[key] = lap
            self._laps.move_to_end(key)
            while len(self._laps) > self._size:
                self._laps.popitem(last=False)
        return lap


POOL_CACHE = PoolCache()


def elected_own_reference(cat, car: str, track: str, rows: list[dict],
                          review_row: dict | None, reference_path: str | None) -> bool:
    """Il riferimento usato è quello eletto per il giro rivisto, ed è tuo?

    La regola del report (``baseline_path == elected and not is_pro``) per chi
    non ha già fatto l'elezione, come la Home. Un giro scelto a mano si
    confronta così com'è, e un PRO non si mescola coi tuoi giri.
    """
    if reference_path is None:
        return False
    mine = conditions_of(review_row)
    elected = cat.best_reference_path(car, track, mine["road_temp"],
                                      mine["grip"], mine["compound"])
    if elected is None or elected != reference_path:
        return False
    row = next((r for r in rows if r["path"] == elected), None) or {}
    return (row.get("source") or "own") != "pro"


def corner_bests_for(reference: Reference, corners: list, review: Lap,
                     car: str, track: str, laps_dir: Path,
                     conditions: dict,
                     review_path: str | None = None) -> CornerBests | None:
    """Il gesto migliore di ogni curva per il debrief del giro rivisto.

    Il bacino si filtra con le condizioni che hanno eletto il riferimento
    (``conditions`` = :func:`conditions_of` del giro rivisto), come fa il motore
    dal vivo. Il giro rivisto può stare nel bacino ed essere il migliore in una
    curva: lì confrontarlo con sé stesso darebbe zero, cioè «niente da
    imparare», e la curva sparirebbe. Si salta, riconosciuto dal file
    (``review_path``); senza il file, da tempo, ora e campioni. Quella curva
    resta sul principale.

    Il catalogo non si risincronizza: chi chiama (l'endpoint, la Home) l'ha
    appena fatto.

    Un bonus, non un requisito: se il bacino non si costruisce resta il solo
    principale, mai un errore.
    """
    try:
        bests = CornerBests(reference, corners)
        for path in reference_pool_paths(car, track, laps_dir,
                                         conditions["road_temp"],
                                         conditions["grip"],
                                         conditions["compound"], POOL_SIZE,
                                         sync=False):
            if review_path is not None and str(path) == str(review_path):
                continue                 # il giro rivisto, letto dal bacino
            other = POOL_CACHE.get(path)
            if other is None or not pool_lap_ok(other, car, track):
                continue
            if (review_path is None
                    and other.lap_time_ms == review.lap_time_ms
                    and other.recorded_utc == review.recorded_utc
                    and (review.recorded_utc or other.samples == review.samples)):
                continue                 # lo stesso, senza il file per dirlo
            bests.offer(other)
        return bests
    except Exception:  # noqa: BLE001 - senza bacino vale il principale
        _log.warning("corner bests failed; main reference only", exc_info=True)
        return None
