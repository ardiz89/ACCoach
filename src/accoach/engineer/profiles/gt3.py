"""GT3 race-engineer profile (ACC).

Encodes the GT3 method as data the :class:`~accoach.engineer.core.RaceEngineer`
can drive:

* **phase order** — pressures → aero → mechanical → brake bias → electronics,
  each with a quantitative completion gate;
* **symptom → remedy table** — for every cell of the taxonomy (balance × corner
  phase × speed) an ordered list of setup changes (parameter, direction, step),
  most effective first.

Steps are in *clicks* (the setup's native unit), matching the setup editor.
"""

from __future__ import annotations

from ..core import FRONT, REAR, LapStats, Profile, Symptom, WorkPhase
from ._common import (
    AP,
    EN,
    EX,
    HI,
    LO,
    O,
    U,
    PressurePhase,
    _SEG_LIMIT,
    none_present,
    remedy,
)

# The 12-cell GT3 table. Each entry: ordered remedies (most effective first).
REMEDY_TABLE: dict[Symptom, list] = {
    # ---- Understeer ----
    Symptom(U, EN, LO): [
        remedy("aRBFront", None, -1, "Sottosterzo in entrata lenta: barra anteriore più morbida (−1)"),
        remedy("toe", "front", +1, "Sottosterzo in entrata: più toe-out anteriore (+1)"),
        remedy("brakeBias", None, -1, "Sottosterzo in entrata: bias freni un filo indietro (−1)", "AV"),
    ],
    Symptom(U, EN, HI): [
        remedy("rideHeight", "rear", +2, "Sottosterzo in entrata veloce: alza il posteriore, più rake (+2)"),
        remedy("splitter", None, +1, "Sottosterzo in entrata veloce: più splitter anteriore (+1)"),
        remedy("aRBFront", None, -1, "Sottosterzo in entrata veloce: barra anteriore più morbida (−1)"),
    ],
    Symptom(U, AP, LO): [
        remedy("preload", None, -1, "Sottosterzo all'apex lento: meno precarico differenziale (−1)"),
        remedy("aRBFront", None, -1, "Sottosterzo all'apex: barra anteriore più morbida (−1)"),
        remedy("wheelRate", "front", -1, "Sottosterzo all'apex: molle anteriori più morbide (−1)"),
    ],
    Symptom(U, AP, HI): [
        remedy("rearWing", None, -1, "Sottosterzo all'apex veloce: meno ala posteriore (−1)"),
        remedy("splitter", None, +1, "Sottosterzo all'apex veloce: più splitter anteriore (+1)"),
        remedy("rideHeight", "rear", +1, "Sottosterzo all'apex veloce: più rake (+1)"),
    ],
    Symptom(U, EX, LO): [
        remedy("preload", None, -1, "Sottosterzo in uscita lenta (trazione): meno precarico diff (−1)"),
        remedy("aRBRear", None, -1, "Sottosterzo in uscita: barra posteriore più morbida (−1)"),
    ],
    Symptom(U, EX, HI): [
        remedy("rearWing", None, -1, "Sottosterzo in uscita veloce: meno ala posteriore (−1)"),
        remedy("splitter", None, +1, "Sottosterzo in uscita veloce: più splitter (+1)"),
    ],
    # ---- Oversteer ----
    Symptom(O, EN, LO): [
        remedy("brakeBias", None, +1, "Sovrasterzo in entrata lenta: bias freni più avanti (+1)", "AV"),
        remedy("aRBRear", None, -1, "Sovrasterzo in entrata: barra posteriore più morbida (−1)"),
        remedy("toe", "rear", +1, "Sovrasterzo in entrata: più toe-in posteriore (+1)"),
    ],
    Symptom(O, EN, HI): [
        remedy("rearWing", None, +1, "Sovrasterzo in entrata veloce: più ala posteriore (+1)"),
        remedy("rideHeight", "rear", -2, "Sovrasterzo in entrata veloce: abbassa il posteriore (−2)"),
        remedy("aRBRear", None, -1, "Sovrasterzo in entrata veloce: barra posteriore più morbida (−1)"),
    ],
    Symptom(O, AP, LO): [
        remedy("aRBRear", None, -1, "Sovrasterzo all'apex lento: barra posteriore più morbida (−1)"),
        remedy("preload", None, +1, "Sovrasterzo all'apex: più precarico differenziale (+1)"),
    ],
    Symptom(O, AP, HI): [
        remedy("rearWing", None, +1, "Sovrasterzo all'apex veloce: più ala posteriore (+1)"),
        remedy("aRBRear", None, -1, "Sovrasterzo all'apex veloce: barra posteriore più morbida (−1)"),
    ],
    Symptom(O, EX, LO): [
        remedy("tC1", None, +1, "Sovrasterzo in uscita (trazione): più controllo di trazione (+1)", "AV"),
        remedy("aRBRear", None, -1, "Sovrasterzo in uscita: barra posteriore più morbida (−1)"),
        remedy("wheelRate", "rear", -1, "Sovrasterzo in uscita: molle posteriori più morbide (−1)"),
    ],
    Symptom(O, EX, HI): [
        remedy("rearWing", None, +1, "Sovrasterzo in uscita veloce: più ala posteriore (+1)"),
        remedy("tC1", None, +1, "Sovrasterzo in uscita veloce: più controllo di trazione (+1)", "AV"),
    ],
}


# --- phases ----------------------------------------------------------------

class _AeroPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        return symptom.speed == HI

    def gate(self, window: list[LapStats]) -> bool:
        return none_present(window, self.owns)


class _MechanicalPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        if symptom.speed != LO:
            return False
        if symptom.phase == AP:
            return True
        return symptom.balance == U          # entry/exit understeer (not braking/traction oversteer)

    def gate(self, window: list[LapStats]) -> bool:
        return none_present(window, self.owns)


class _BrakeBiasPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        return symptom.balance == O and symptom.phase == EN

    def gate(self, window: list[LapStats]) -> bool:
        if not none_present(window, self.owns):
            return False
        return all(s.lock_segments < _SEG_LIMIT for s in window)


class _ElectronicsPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        return symptom.balance == O and symptom.phase == EX

    def gate(self, window: list[LapStats]) -> bool:
        if not none_present(window, self.owns):
            return False
        return all(s.spin_segments < _SEG_LIMIT for s in window)


GT3_PROFILE = Profile(
    name="GT3",
    phases=[
        PressurePhase(27.5, 0.7),
        _AeroPhase("aero", "Aero / rake", "BOX"),
        _MechanicalPhase("mechanical", "Grip meccanico", "BOX"),
        _BrakeBiasPhase("brake_bias", "Bilanciamento freni", "AV"),
        _ElectronicsPhase("electronics", "Elettronica", "AV"),
    ],
    remedy_table=REMEDY_TABLE,
    al_volo=["Bilanciamento freni", "TC", "ABS", "Mappa motore"],
)
