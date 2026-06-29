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
        remedy("aRBFront", None, -1, "Understeer on slow entry: softer front anti-roll bar (−1)"),
        remedy("toe", "front", +1, "Understeer on entry: more front toe-out (+1)"),
        remedy("brakeBias", None, -1, "Understeer on entry: brake bias slightly rearward (−1)", "AV"),
    ],
    Symptom(U, EN, HI): [
        remedy("rideHeight", "rear", +2, "Understeer on fast entry: raise the rear, more rake (+2)"),
        remedy("splitter", None, +1, "Understeer on fast entry: more front splitter (+1)"),
        remedy("aRBFront", None, -1, "Understeer on fast entry: softer front anti-roll bar (−1)"),
    ],
    Symptom(U, AP, LO): [
        remedy("preload", None, -1, "Understeer at slow apex: less differential preload (−1)"),
        remedy("aRBFront", None, -1, "Understeer at apex: softer front anti-roll bar (−1)"),
        remedy("wheelRate", "front", -1, "Understeer at apex: softer front springs (−1)"),
    ],
    Symptom(U, AP, HI): [
        remedy("rearWing", None, -1, "Understeer at fast apex: less rear wing (−1)"),
        remedy("splitter", None, +1, "Understeer at fast apex: more front splitter (+1)"),
        remedy("rideHeight", "rear", +1, "Understeer at fast apex: more rake (+1)"),
    ],
    Symptom(U, EX, LO): [
        remedy("preload", None, -1, "Understeer on slow exit (traction): less diff preload (−1)"),
        remedy("aRBRear", None, -1, "Understeer on exit: softer rear anti-roll bar (−1)"),
    ],
    Symptom(U, EX, HI): [
        remedy("rearWing", None, -1, "Understeer on fast exit: less rear wing (−1)"),
        remedy("splitter", None, +1, "Understeer on fast exit: more splitter (+1)"),
    ],
    # ---- Oversteer ----
    Symptom(O, EN, LO): [
        remedy("brakeBias", None, +1, "Oversteer on slow entry: brake bias more forward (+1)", "AV"),
        remedy("aRBRear", None, -1, "Oversteer on entry: softer rear anti-roll bar (−1)"),
        remedy("toe", "rear", +1, "Oversteer on entry: more rear toe-in (+1)"),
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
        remedy("tC1", None, +1, "Oversteer on exit (traction): more traction control (+1)", "AV"),
        remedy("aRBRear", None, -1, "Oversteer on exit: softer rear anti-roll bar (−1)"),
        remedy("wheelRate", "rear", -1, "Oversteer on exit: softer rear springs (−1)"),
    ],
    Symptom(O, EX, HI): [
        remedy("rearWing", None, +1, "Oversteer on fast exit: more rear wing (+1)"),
        remedy("tC1", None, +1, "Oversteer on fast exit: more traction control (+1)", "AV"),
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
        _MechanicalPhase("mechanical", "Mechanical grip", "BOX"),
        _BrakeBiasPhase("brake_bias", "Brake bias", "AV"),
        _ElectronicsPhase("electronics", "Electronics", "AV"),
    ],
    remedy_table=REMEDY_TABLE,
    al_volo=["Brake bias", "TC", "ABS", "Engine map"],
)
