"""Tyre-temperature advisor — the overdriving signal.

Tyre core temperature is the cleanest read on whether the driver is *overdriving*.
A tyre has an optimal temperature window; push past the limit of grip — sliding
the car, scrubbing in understeer, lighting up the rears — and the carcass heats
beyond that window and grip falls away. So persistently **hot** tyres across a lap
mean "you're forcing it, be smoother", while persistently **cold** tyres mean
there's grip left on the table.

Like the pressure advisor this is judged once per lap over the lap's average and
spoken at the line, with a long cooldown — it's a stint-level tendency, not a
corner cue. It deliberately leans on a wide tolerance so only a clear excursion
talks.

Scope / calibration
-------------------
The default window is dry **ACC GT3** territory (~80 °C core, ±12). Compound,
weather and ambient move it a lot, so ``target_c`` / ``tol_c`` are constructor
parameters to be set per condition later.
"""

from __future__ import annotations

from ..engineer import CarClass
from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory
from .tuning import tuning_for_class

_DEFAULT_TARGET_C = 80.0
_DEFAULT_TOL_C = 12.0       # wide on purpose: only a clear excursion speaks

_MIN_SPEED_KMH = 60.0
_TEMP_PLAUSIBLE = (20.0, 140.0)
_MIN_SAMPLES = 30

_COOLDOWN_LAPS = 5
_MIN_LAP_SPAN = 0.7
_PRIORITY = 235.0           # informational, just under the pressure advisor


class TyreTempAdvisor:
    """Stateful: fed (snapshot, now) each frame; yields overdriving/temp advice."""

    def __init__(
        self,
        target_c: float = _DEFAULT_TARGET_C,
        tol_c: float = _DEFAULT_TOL_C,
        car_class: CarClass | None = None,
    ) -> None:
        self.target_c = target_c
        self.tol_c = tol_c
        #: Sappiamo qual è la finestra di QUESTA auto? Vedi `set_car_class`.
        self._known = True
        if car_class is not None:
            self.set_car_class(car_class)
        self._reset_lap()
        self._cooldown = 0

    def set_car_class(self, car_class: CarClass) -> None:
        """Prendi la finestra della classe, o **taci** se non la conosciamo.

        80 °C è la GT3 ACC all'asciutto. Misurato sui giri veri: **tutti e 18** i
        cue di temperatura dell'archivio escono da giri AC, zero da ACC — cioè
        il detector parlava solo dove la sua finestra non vale. Una SF25 gira a
        90 °C («stai forzando») e una stradale su semislick a 66 («gomme
        fredde», detto sui suoi giri più veloci). Su ACC, dove il numero è nato,
        legge 79-81 e sta correttamente zitto. Vedi il blocco in `tuning.py`.
        """
        window = tuning_for_class(car_class).tyre_c
        self._known = window is not None
        if window is not None:
            self.target_c, self.tol_c = window

    def reset(self) -> None:
        self._reset_lap()
        self._cooldown = 0

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self._reset_lap()
            return []
        # La classe non basta: serve anche il titolo. Il M4 GT3 *mod su AC* è
        # classe GT3 e legge 63 °C — il modello gomme del mod non è quello di
        # ACC, ed è su ACC che 80 °C è stato misurato.
        if not (self._known and s.is_acc):
            self._reset_lap()
            return []

        pos = s.lap_position
        cues = self._maybe_advise(pos)

        if s.speed_kmh >= _MIN_SPEED_KMH and self._plausible(s.tyre_core_temp):
            self._temp_sum += sum(s.tyre_core_temp) / 4
            self._samples += 1

        self._pos_min = min(self._pos_min, pos)
        self._pos_max = max(self._pos_max, pos)
        self._prev_pos = pos
        return cues

    # --- lap boundary -----------------------------------------------------
    def _maybe_advise(self, pos: float) -> list[Cue]:
        crossed = self._prev_pos > 0.7 and pos < 0.3
        if not crossed:
            return []

        cue = self._evaluate()
        cues = [cue] if cue is not None else []
        if self._cooldown > 0:
            self._cooldown -= 1
        self._reset_lap()
        return cues

    def _evaluate(self) -> Cue | None:
        full_lap = (self._pos_max - self._pos_min) >= _MIN_LAP_SPAN
        if not full_lap or self._samples < _MIN_SAMPLES or self._cooldown > 0:
            return None

        avg = self._temp_sum / self._samples
        if avg > self.target_c + self.tol_c:
            msg = (f"Gomme troppo calde ({avg:.0f}°C): stai forzando, "
                   f"cerca di essere più fluido.")
        elif avg < self.target_c - self.tol_c:
            msg = (f"Gomme fredde ({avg:.0f}°C): puoi spingere di più "
                   f"per portarle in temperatura.")
        else:
            return None

        self._cooldown = _COOLDOWN_LAPS
        return Cue(category=CueCategory.TYRE_TEMP, message=msg,
                   priority=_PRIORITY, segment=0, pos=0.0)

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _plausible(temps: tuple[float, float, float, float]) -> bool:
        lo, hi = _TEMP_PLAUSIBLE
        return all(lo <= t <= hi for t in temps)

    def _reset_lap(self) -> None:
        self._temp_sum = 0.0
        self._samples = 0
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._prev_pos = -1.0
