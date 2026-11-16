"""Il gesto migliore di ogni curva, dai tuoi giri nelle stesse condizioni.

Il riferimento principale è il tuo giro più veloce. Quasi mai è il più veloce
in ogni curva: il giro del record ha spesso una curva sbagliata, e un giro più
lento l'ha fatta meglio. Confrontare quella curva col record dice «perdi poco»
dove in realtà sai già fare di meglio, e lo hai fatto.

Qui ogni curva tiene il giro che l'ha percorsa più in fretta. È una **misura**,
non una simulazione: il tempo della finestra è letto dall'orologio di un giro
che hai guidato davvero, fra due posizioni. Non si incollano pezzi di giri
diversi per costruire un giro ideale, e non si stima niente.

Le regole vengono dal piano (2026-11-03, Decisioni 3-6).

- **La finestra** (Decisione 3) va dall'``entry_pos`` della curva all'``entry_pos``
  della curva dopo, come nel debrief (:func:`~accoach.coaching.debrief._next_entry`):
  il rettilineo dopo una curva è di quella curva, perché la velocità di uscita
  lo decide. L'ultima curva arriva al traguardo e non gira oltre (``_next_entry``
  dà 1,01): il tratto prima della prima ``entry`` non è di nessuna curva, quindi
  :meth:`CornerBests.at` lì non risponde.
- **Chi può entrare** (Decisione 4) è un giro tuo della stessa auto e pista,
  completo, non tagliato, nella stessa mescola e con l'asfalto entro
  ``_TEMP_BAND_C`` se entrambi i giri li conoscono, e con campioni che coprono
  tutta la finestra. Un buco nei campioni lascerebbe l'interpolazione inventare
  proprio il tratto che si vuole misurare.
- **Quanto deve guadagnare**: almeno ``MIN_GAIN_MS`` sul principale. È lo stesso
  mezzo decimo di ``phases._GAIN_MS``, il guadagno più piccolo che regge la
  dispersione di un pilota fra un giro e l'altro. Sotto, è rumore.
- **Spento** (Decisione 5) quando il principale è un giro PRO o non ci sono
  curve. Un PRO non si mescola coi tuoi giri, e senza curve non c'è finestra.
- **Dove vale** (Decisione 6) lo decide chi lo usa, non questo modulo.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..comparison.reference import Reference
from ..recording.catalog import _TEMP_BAND_C
from ..recording.lap import Lap, clean_verdict, strip_leading_wrap
from .phases import _GAIN_MS

if TYPE_CHECKING:
    from ..track import Corner

#: Il guadagno minimo sul riferimento principale perché una curva cambi giro.
MIN_GAIN_MS = _GAIN_MS
#: Quanti dei tuoi giri più veloci entrano nel bacino (Decisione 7).
POOL_SIZE = 20

#: Copertura della finestra (Decisione 4). Il primo campione entro mezzo
#: centesimo dall'inizio, l'ultimo entro mezzo centesimo dalla fine, e nessun
#: buco oltre un centesimo. Sui 193 giri dell'archivio il buco più largo fra due
#: campioni è 0,0028 al 95° percentile e l'ultimo campione sta sempre oltre
#: 0,9955, quindi anche l'ultima curva, che finisce al traguardo, è coperta.
_EDGE = 0.005
_MAX_GAP = 0.01


@dataclass(slots=True)
class CornerRef:
    """Il giro che ha percorso più in fretta la finestra di una curva."""

    reference: Reference
    window_ms: float        # il suo tempo nella finestra
    gain_ms: float          # quanto batte il riferimento principale lì
    lap_time_ms: int        # il tempo del suo giro intero, per dirlo a parole


def _forward_pos(lap: Lap) -> list[float]:
    """Le posizioni dei campioni veri, filtrate come fa :class:`Reference`.

    Non si usano quelle del ``Reference``: lui aggiunge due ancore a 0 e 1 che
    non sono campioni, e farebbero sembrare coperto un giro che non lo è."""
    out: list[float] = []
    last = -1.0
    for s in strip_leading_wrap(lap.samples):
        if s.pos <= last:
            continue
        last = s.pos
        out.append(s.pos)
    return out


def _covered(pos: list[float], lo: float, hi: float) -> bool:
    if len(pos) < 2 or pos[0] > lo + _EDGE or pos[-1] < hi - _EDGE:
        return False
    for a, b in zip(pos, pos[1:]):
        if b > lo and a < hi and b - a > _MAX_GAP:
            return False
    return True


def _window_ms(ref: Reference, pos: list[float], lo: float,
               hi: float) -> float | None:
    hi = min(hi, 1.0)
    if not ref.usable or hi <= lo or not _covered(pos, lo, hi):
        return None
    return ref.time_at(hi) - ref.time_at(lo)


def window_ms(ref: Reference, lo: float, hi: float) -> float | None:
    """Il tempo del giro di ``ref`` fra ``lo`` e ``hi``.

    ``None`` se i campioni non coprono la finestra (Decisione 4). ``hi`` oltre
    il traguardo vale il traguardo."""
    return _window_ms(ref, _forward_pos(ref.lap), lo, hi)


def eligible(lap: Lap, main: Lap) -> bool:
    """Se ``lap`` può prendere una curva al riferimento principale ``main``."""
    if lap is main:
        return False
    if lap.recorded_utc and lap.recorded_utc == main.recorded_utc \
            and lap.lap_time_ms == main.lap_time_ms:
        return False                     # lo stesso giro, letto un'altra volta
    if lap.car_model != main.car_model or lap.track != main.track:
        return False
    if not lap.valid or lap.lap_time_ms <= 0:
        return False
    if clean_verdict(lap.clean, lap.schema_version, lap.tyre_compound,
                     lap.recorded_utc) == 0:
        return False
    if lap.source == "pro":
        return False
    if lap.tyre_compound and main.tyre_compound \
            and lap.tyre_compound != main.tyre_compound:
        return False
    if lap.road_temp > 0 and main.road_temp > 0 \
            and abs(lap.road_temp - main.road_temp) > _TEMP_BAND_C:
        return False
    return True


class CornerBests:
    """Per ogni curva, il tuo giro più veloce nella sua finestra.

    Parte vuoto: finché nessun giro batte il principale di ``MIN_GAIN_MS``,
    :meth:`at` risponde ``None`` e vale il riferimento principale."""

    def __init__(self, main: Reference, corners: list[Corner]) -> None:
        # Importato qui: il debrief importa l'analizzatore, che userà questo
        # modulo, e un import in cima chiuderebbe il cerchio.
        from .debrief import _next_entry

        self.main = main
        self._off = main.lap.source == "pro" or not corners
        self._lo: list[float] = []
        self._hi: list[float] = []
        self._main_ms: list[float | None] = []
        self._best: list[CornerRef | None] = []
        if self._off:
            return
        pos = _forward_pos(main.lap)
        for c in sorted(corners, key=lambda c: c.entry_pos):
            hi = _next_entry(c, corners)
            self._lo.append(c.entry_pos)
            self._hi.append(hi)
            self._main_ms.append(_window_ms(main, pos, c.entry_pos, hi))
            self._best.append(None)

    def offer(self, lap: Lap) -> bool:
        """Propone ``lap``; ``True`` se ha preso almeno una curva."""
        if self._off or not eligible(lap, self.main.lap):
            return False
        ref = Reference(lap)
        if not ref.usable:
            return False
        pos = _forward_pos(lap)
        changed = False
        for i, (lo, hi) in enumerate(zip(self._lo, self._hi)):
            main_ms = self._main_ms[i]
            if main_ms is None:
                continue                 # il principale stesso non la copre
            ms = _window_ms(ref, pos, lo, hi)
            if ms is None:
                continue
            held = self._best[i]
            current = held.window_ms if held is not None else main_ms
            gain = main_ms - ms
            if ms < current and gain >= MIN_GAIN_MS:
                self._best[i] = CornerRef(ref, ms, gain, lap.lap_time_ms)
                changed = True
        return changed

    def at(self, pos: float) -> CornerRef | None:
        """Il riferimento della curva la cui finestra contiene ``pos``.

        ``None`` dove vale il principale, o fuori da ogni finestra."""
        i = bisect.bisect_right(self._lo, pos) - 1
        if i < 0 or pos >= self._hi[i]:
            return None
        return self._best[i]
