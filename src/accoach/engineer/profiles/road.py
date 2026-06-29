"""Road-car race-engineer profile (low/no downforce — Assetto Corsa).

Differs from GT3 in three ways:

* **collapsed speed axis** — without downforce, grip doesn't change with speed,
  so a symptom's remedy is the same at low and high speed (one mechanical
  bucket). The table is keyed by (balance × phase) and expanded over both speeds.
* **no electronic aids** — no TC/ABS remedies ever; oversteer is fixed with the
  differential, springs/dampers, geometry and brake bias.
* **no aero phase** — only pressures, mechanical grip, traction and (if present)
  brake bias.

The signature road problem is **lift-off (entry/release) oversteer**, handled
with rear toe-in, softer rear rebound and a more locked coast differential.
"""

from __future__ import annotations

from ..core import LapStats, Phase, Profile, Speed, Symptom, WorkPhase
from ._common import (
    AP,
    EN,
    EX,
    O,
    U,
    PressurePhase,
    _SEG_LIMIT,
    none_present,
    remedy,
)

# Keyed by (balance, phase) — speed doesn't change the lever on a road car.
_BASE: dict[tuple, list] = {
    (U, EN): [
        remedy("tyrePressure", "front", -2, "Understeer on entry: less front pressure (−2)"),
        remedy("aRBFront", None, -1, "Understeer on entry: softer front anti-roll bar (−1)"),
        remedy("toe", "front", +1, "Understeer on entry: more front toe-out (+1)"),
    ],
    (U, AP): [
        remedy("aRBFront", None, -1, "Understeer at apex: softer front anti-roll bar (−1)"),
        remedy("camber", "front", -1, "Understeer at apex: more front negative camber (−1)"),
        remedy("wheelRate", "front", -1, "Understeer at apex: softer front springs (−1)"),
    ],
    (U, EX): [
        remedy("diffPower", None, -1, "Understeer on exit: less locked differential on power (−1)"),
        remedy("aRBRear", None, -1, "Understeer on exit: softer rear anti-roll bar (−1)"),
    ],
    (O, EN): [   # the lift-off / release oversteer signature
        remedy("toe", "rear", +1, "Lift-off oversteer: more rear toe-in (+1)"),
        remedy("reboundSlow", "rear", -1, "Lift-off oversteer: softer rear rebound (−1)"),
        remedy("aRBRear", None, -1, "Lift-off oversteer: softer rear anti-roll bar (−1)"),
        remedy("brakeBias", None, +1, "Lift-off oversteer: brake bias more forward (+1)", "AV"),
    ],
    (O, AP): [
        remedy("aRBRear", None, -1, "Oversteer at apex: softer rear anti-roll bar (−1)"),
        remedy("toe", "rear", +1, "Oversteer at apex: more rear toe-in (+1)"),
    ],
    (O, EX): [
        remedy("diffPower", None, -1, "Oversteer on exit (traction): softer differential on power (−1)"),
        remedy("wheelRate", "rear", -1, "Oversteer on exit: softer rear springs (−1)"),
        remedy("aRBRear", None, -1, "Oversteer on exit: softer rear anti-roll bar (−1)"),
    ],
}

# Expand over both speed bands (same remedy applies).
REMEDY_TABLE: dict[Symptom, list] = {
    Symptom(bal, ph, spd): remedies
    for (bal, ph), remedies in _BASE.items()
    for spd in Speed
}


class _MechanicalPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        return symptom.phase in (EN, AP)

    def gate(self, window: list[LapStats]) -> bool:
        return none_present(window, self.owns)


class _TractionPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        return symptom.phase == EX

    def gate(self, window: list[LapStats]) -> bool:
        if not none_present(window, self.owns):
            return False
        return all(s.spin_segments < _SEG_LIMIT for s in window)


class _BrakeBiasPhase(WorkPhase):
    def owns(self, symptom: Symptom) -> bool:
        return symptom.balance == O and symptom.phase == EN

    def gate(self, window: list[LapStats]) -> bool:
        if not none_present(window, self.owns):
            return False
        return all(s.lock_segments < _SEG_LIMIT for s in window)


ROAD_PROFILE = Profile(
    name="Road",
    phases=[
        PressurePhase(30.0, 1.5),                       # wider window, street rubber
        _MechanicalPhase("mechanical", "Mechanical grip", "BOX"),
        _TractionPhase("traction", "Traction", "BOX"),
        _BrakeBiasPhase("brake_bias", "Brake bias", "AV"),
    ],
    remedy_table=REMEDY_TABLE,
    al_volo=["Brake bias"],                             # often the only on-the-fly lever
)
