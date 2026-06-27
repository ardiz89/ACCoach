"""Formula race-engineer profile (open-wheel, high downforce — Assetto Corsa).

Differs from GT3 in three ways that matter to the state machine:

* **aero-first** — wings and rake dominate the balance, so the aero phase runs
  *before* the mechanical phase (tuning springs to mask an aero problem is
  backwards on a formula car);
* **no ABS / no TC** (historics) — locking and wheelspin are handled by brake
  bias, the differential and driving, never by electronic aids;
* **lower, tighter tyre window** than slick GT3 rubber.

Steps are in clicks. Parameter keys (frontWing, diffPower, …) match the AC
formula setup format added in F5.
"""

from __future__ import annotations

from ..core import LapStats, Profile, Symptom, WorkPhase
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

REMEDY_TABLE: dict[Symptom, list] = {
    # ---- Understeer ----
    Symptom(U, EN, LO): [
        remedy("brakeBias", None, -1, "Sottosterzo in entrata: bias freni un filo indietro (−1)", "AV"),
        remedy("aRBFront", None, -1, "Sottosterzo in entrata: barra anteriore più morbida (−1)"),
        remedy("toe", "front", +1, "Sottosterzo in entrata: più toe-out anteriore (+1)"),
    ],
    Symptom(U, EN, HI): [
        remedy("frontWing", None, +1, "Sottosterzo in entrata veloce: più ala anteriore (+1)"),
        remedy("rideHeight", "rear", +2, "Sottosterzo in entrata veloce: più rake, alza il posteriore (+2)"),
        remedy("rearWing", None, -1, "Sottosterzo in entrata veloce: meno ala posteriore (−1)"),
    ],
    Symptom(U, AP, LO): [
        remedy("preload", None, -1, "Sottosterzo all'apex lento: meno precarico differenziale (−1)"),
        remedy("aRBFront", None, -1, "Sottosterzo all'apex: barra anteriore più morbida (−1)"),
    ],
    Symptom(U, AP, HI): [
        remedy("frontWing", None, +1, "Sottosterzo all'apex veloce: più ala anteriore (+1)"),
        remedy("rearWing", None, -1, "Sottosterzo all'apex veloce: meno ala posteriore (−1)"),
        remedy("rideHeight", "rear", +1, "Sottosterzo all'apex veloce: più rake (+1)"),
    ],
    Symptom(U, EX, LO): [
        remedy("diffPower", None, -1, "Sottosterzo in uscita (power): differenziale meno bloccato (−1)"),
        remedy("aRBRear", None, -1, "Sottosterzo in uscita: barra posteriore più morbida (−1)"),
    ],
    Symptom(U, EX, HI): [
        remedy("rearWing", None, -1, "Sottosterzo in uscita veloce: meno ala posteriore (−1)"),
        remedy("frontWing", None, +1, "Sottosterzo in uscita veloce: più ala anteriore (+1)"),
    ],
    # ---- Oversteer ----
    Symptom(O, EN, LO): [
        remedy("brakeBias", None, +1, "Sovrasterzo in entrata: bias freni più avanti (+1)", "AV"),
        remedy("diffCoast", None, +1, "Sovrasterzo in rilascio: differenziale più chiuso in coast (+1)"),
        remedy("aRBRear", None, -1, "Sovrasterzo in entrata: barra posteriore più morbida (−1)"),
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
        remedy("diffPower", None, -1, "Sovrasterzo in uscita (trazione, no TC): differenziale più dolce in power (−1)"),
        remedy("wheelRate", "rear", -1, "Sovrasterzo in uscita: molle posteriori più morbide (−1)"),
        remedy("aRBRear", None, -1, "Sovrasterzo in uscita: barra posteriore più morbida (−1)"),
    ],
    Symptom(O, EX, HI): [
        remedy("rearWing", None, +1, "Sovrasterzo in uscita veloce: più ala posteriore (+1)"),
        remedy("diffPower", None, -1, "Sovrasterzo in uscita veloce: differenziale più dolce in power (−1)"),
    ],
}


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
        return symptom.phase == EN and symptom.balance == U

    def gate(self, window: list[LapStats]) -> bool:
        return none_present(window, self.owns)


class _DiffPhase(WorkPhase):
    """Owns power/traction at corner exit (the differential's domain)."""

    def owns(self, symptom: Symptom) -> bool:
        return symptom.speed == LO and symptom.phase == EX

    def gate(self, window: list[LapStats]) -> bool:
        if not none_present(window, self.owns):
            return False
        return all(s.spin_segments < _SEG_LIMIT for s in window)


class _BrakeBiasPhase(WorkPhase):
    """No ABS: locking and entry oversteer are bias + brake migration + driving."""

    def owns(self, symptom: Symptom) -> bool:
        return symptom.balance == O and symptom.phase == EN

    def gate(self, window: list[LapStats]) -> bool:
        if not none_present(window, self.owns):
            return False
        return all(s.lock_segments < _SEG_LIMIT for s in window)


FORMULA_PROFILE = Profile(
    name="Formula",
    phases=[
        PressurePhase(22.0, 0.4),                       # lower, tighter window
        _AeroPhase("aero", "Aero / rake", "BOX"),       # before mechanical
        _MechanicalPhase("mechanical", "Grip meccanico", "BOX"),
        _DiffPhase("diff", "Differenziale", "BOX"),
        _BrakeBiasPhase("brake_bias", "Bilanciamento freni", "AV"),
    ],
    remedy_table=REMEDY_TABLE,
    al_volo=["Bilanciamento freni", "Brake migration", "Mappa motore / ERS", "Freno motore"],
)
