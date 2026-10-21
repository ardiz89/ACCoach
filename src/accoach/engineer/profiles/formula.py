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
        remedy("aRBFront", None, -1, "The car understeers on entry, so soften the front anti-roll bar by 1 click."),
        remedy("toe", "front", +1, "The car understeers on entry, so add 1 click of front toe-out."),
        remedy("brakeBias", None, -1, "The car understeers on entry, so move the brake bias 1 click rearward.", "AV"),
    ],
    Symptom(U, EN, HI): [
        remedy("frontWing", None, +1, "The car understeers on entry to fast corners, so add 1 click of front wing."),
        remedy("rideHeight", "rear", +2, "The car understeers on entry to fast corners, so raise the rear by 2 clicks for more rake."),
        remedy("rearWing", None, -1, "The car understeers on entry to fast corners, so take 1 click of rear wing off."),
    ],
    Symptom(U, AP, LO): [
        remedy("preload", None, -1, "The car understeers mid-corner in slow corners, so take 1 click of differential preload off."),
        remedy("aRBFront", None, -1, "The car understeers mid-corner, so soften the front anti-roll bar by 1 click."),
    ],
    Symptom(U, AP, HI): [
        remedy("frontWing", None, +1, "The car understeers mid-corner in fast corners, so add 1 click of front wing."),
        remedy("rearWing", None, -1, "The car understeers mid-corner in fast corners, so take 1 click of rear wing off."),
        remedy("rideHeight", "rear", +1, "The car understeers mid-corner in fast corners, so raise the rear by 1 click for more rake."),
    ],
    Symptom(U, EX, LO): [
        remedy("diffPower", None, -1, "The car understeers on exit under power, so take 1 click of power locking off the differential."),
        remedy("aRBRear", None, -1, "The car understeers on exit, so soften the rear anti-roll bar by 1 click."),
    ],
    Symptom(U, EX, HI): [
        remedy("rearWing", None, -1, "The car understeers on exit from fast corners, so take 1 click of rear wing off."),
        remedy("frontWing", None, +1, "The car understeers on exit from fast corners, so add 1 click of front wing."),
    ],
    # ---- Oversteer ----
    Symptom(O, EN, LO): [
        remedy("brakeBias", None, +1, "The car oversteers on entry, so move the brake bias 1 click forward.", "AV"),
        remedy("diffCoast", None, +1, "The car oversteers when you lift off, so add 1 click of coast locking to the differential."),
        remedy("aRBRear", None, -1, "The car oversteers on entry, so soften the rear anti-roll bar by 1 click."),
    ],
    Symptom(O, EN, HI): [
        remedy("rearWing", None, +1, "The car oversteers on entry to fast corners, so add 1 click of rear wing."),
        remedy("rideHeight", "rear", -2, "The car oversteers on entry to fast corners, so lower the rear by 2 clicks."),
        remedy("aRBRear", None, -1, "The car oversteers on entry to fast corners, so soften the rear anti-roll bar by 1 click."),
    ],
    Symptom(O, AP, LO): [
        remedy("aRBRear", None, -1, "The car oversteers mid-corner in slow corners, so soften the rear anti-roll bar by 1 click."),
        remedy("preload", None, +1, "The car oversteers mid-corner, so add 1 click of differential preload."),
    ],
    Symptom(O, AP, HI): [
        remedy("rearWing", None, +1, "The car oversteers mid-corner in fast corners, so add 1 click of rear wing."),
        remedy("aRBRear", None, -1, "The car oversteers mid-corner in fast corners, so soften the rear anti-roll bar by 1 click."),
    ],
    Symptom(O, EX, LO): [
        remedy("diffPower", None, -1, "With no TC, the car oversteers on exit under power, so take 1 click of power locking off the differential."),
        remedy("wheelRate", "rear", -1, "The car oversteers on exit, so soften the rear springs by 1 click."),
        remedy("aRBRear", None, -1, "The car oversteers on exit, so soften the rear anti-roll bar by 1 click."),
    ],
    Symptom(O, EX, HI): [
        remedy("rearWing", None, +1, "The car oversteers on exit from fast corners, so add 1 click of rear wing."),
        remedy("diffPower", None, -1, "The car oversteers on exit from fast corners, so take 1 click of power locking off the differential."),
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
