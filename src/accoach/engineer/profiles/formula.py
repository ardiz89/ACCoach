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
        # On a formula with no ABS, moving the bias rearward to rotate on entry is
        # the most lock-prone lever — try front bar/geometry first, bias last.
        remedy("aRBFront", None, -1, "Understeer on entry: softer front anti-roll bar (−1)"),
        remedy("toe", "front", +1, "Understeer on entry: more front toe-out (+1)"),
        remedy("brakeBias", None, -1, "Understeer on entry: brake bias slightly rearward (−1)", "AV"),
    ],
    Symptom(U, EN, HI): [
        remedy("frontWing", None, +1, "Understeer on fast entry: more front wing (+1)"),
        remedy("rideHeight", "rear", +2, "Understeer on fast entry: more rake, raise the rear (+2)"),
        remedy("rearWing", None, -1, "Understeer on fast entry: less rear wing (−1)"),
    ],
    Symptom(U, AP, LO): [
        remedy("preload", None, -1, "Understeer at slow apex: less differential preload (−1)"),
        remedy("aRBFront", None, -1, "Understeer at apex: softer front anti-roll bar (−1)"),
    ],
    Symptom(U, AP, HI): [
        remedy("frontWing", None, +1, "Understeer at fast apex: more front wing (+1)"),
        remedy("rearWing", None, -1, "Understeer at fast apex: less rear wing (−1)"),
        remedy("rideHeight", "rear", +1, "Understeer at fast apex: more rake (+1)"),
    ],
    Symptom(U, EX, LO): [
        remedy("diffPower", None, -1, "Understeer on exit (power): less locked differential (−1)"),
        remedy("aRBRear", None, -1, "Understeer on exit: softer rear anti-roll bar (−1)"),
    ],
    Symptom(U, EX, HI): [
        remedy("rearWing", None, -1, "Understeer on fast exit: less rear wing (−1)"),
        remedy("frontWing", None, +1, "Understeer on fast exit: more front wing (+1)"),
    ],
    # ---- Oversteer ----
    Symptom(O, EN, LO): [
        remedy("brakeBias", None, +1, "Oversteer on entry: brake bias more forward (+1)", "AV"),
        remedy("diffCoast", None, +1, "Lift-off oversteer: more locked differential on coast (+1)"),
        remedy("aRBRear", None, -1, "Oversteer on entry: softer rear anti-roll bar (−1)"),
    ],
    Symptom(O, EN, HI): [
        remedy("rearWing", None, +1, "Oversteer on fast entry: more rear wing (+1)"),
        remedy("rideHeight", "rear", -2, "Oversteer on fast entry: lower the rear (−2)"),
        remedy("aRBRear", None, -1, "Oversteer on fast entry: softer rear anti-roll bar (−1)"),
    ],
    Symptom(O, AP, LO): [
        remedy("aRBRear", None, -1, "Oversteer at slow apex: softer rear anti-roll bar (−1)"),
        remedy("preload", None, +1, "Oversteer at apex: more differential preload (+1)"),
    ],
    Symptom(O, AP, HI): [
        remedy("rearWing", None, +1, "Oversteer at fast apex: more rear wing (+1)"),
        remedy("aRBRear", None, -1, "Oversteer at fast apex: softer rear anti-roll bar (−1)"),
    ],
    Symptom(O, EX, LO): [
        remedy("diffPower", None, -1, "Oversteer on exit (traction, no TC): softer differential on power (−1)"),
        remedy("wheelRate", "rear", -1, "Oversteer on exit: softer rear springs (−1)"),
        remedy("aRBRear", None, -1, "Oversteer on exit: softer rear anti-roll bar (−1)"),
    ],
    Symptom(O, EX, HI): [
        remedy("rearWing", None, +1, "Oversteer on fast exit: more rear wing (+1)"),
        remedy("diffPower", None, -1, "Oversteer on fast exit: softer differential on power (−1)"),
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
        _MechanicalPhase("mechanical", "Mechanical grip", "BOX"),
        _DiffPhase("diff", "Differential", "BOX"),
        _BrakeBiasPhase("brake_bias", "Brake bias", "AV"),
    ],
    remedy_table=REMEDY_TABLE,
    al_volo=["Brake bias", "Brake migration", "Engine map / ERS", "Engine braking"],
)
