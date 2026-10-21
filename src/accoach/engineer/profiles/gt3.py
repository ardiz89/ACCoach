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
    GT3_DRY_WINDOW,
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
        remedy("aRBFront", None, -1, "The car understeers on entry to slow corners, so soften the front anti-roll bar by 1 click."),
        remedy("toe", "front", +1, "The car understeers on entry, so add 1 click of front toe-out."),
        remedy("brakeBias", None, -1, "The car understeers on entry, so move the brake bias 1 click rearward.", "AV"),
    ],
    Symptom(U, EN, HI): [
        remedy("rideHeight", "rear", +2, "The car understeers on entry to fast corners, so raise the rear by 2 clicks for more rake."),
        remedy("splitter", None, +1, "The car understeers on entry to fast corners, so add 1 click of front splitter."),
        remedy("aRBFront", None, -1, "The car understeers on entry to fast corners, so soften the front anti-roll bar by 1 click."),
    ],
    Symptom(U, AP, LO): [
        remedy("preload", None, -1, "The car understeers mid-corner in slow corners, so take 1 click of differential preload off."),
        remedy("aRBFront", None, -1, "The car understeers mid-corner, so soften the front anti-roll bar by 1 click."),
        remedy("wheelRate", "front", -1, "The car understeers mid-corner, so soften the front springs by 1 click."),
    ],
    Symptom(U, AP, HI): [
        remedy("rearWing", None, -1, "The car understeers mid-corner in fast corners, so take 1 click of rear wing off."),
        remedy("splitter", None, +1, "The car understeers mid-corner in fast corners, so add 1 click of front splitter."),
        remedy("rideHeight", "rear", +1, "The car understeers mid-corner in fast corners, so raise the rear by 1 click for more rake."),
    ],
    Symptom(U, EX, LO): [
        remedy("preload", None, -1, "The car understeers on exit from slow corners under power, so take 1 click of differential preload off."),
        remedy("aRBRear", None, -1, "The car understeers on exit, so soften the rear anti-roll bar by 1 click."),
    ],
    Symptom(U, EX, HI): [
        remedy("rearWing", None, -1, "The car understeers on exit from fast corners, so take 1 click of rear wing off."),
        remedy("splitter", None, +1, "The car understeers on exit from fast corners, so add 1 click of splitter."),
    ],
    # ---- Oversteer ----
    Symptom(O, EN, LO): [
        remedy("brakeBias", None, +1, "The car oversteers on entry to slow corners, so move the brake bias 1 click forward.", "AV"),
        remedy("aRBRear", None, -1, "The car oversteers on entry, so soften the rear anti-roll bar by 1 click."),
        remedy("toe", "rear", +1, "The car oversteers on entry, so add 1 click of rear toe-in."),
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
        remedy("tC1", None, +1, "The car oversteers on exit under power, so add 1 click of traction control.", "AV"),
        remedy("aRBRear", None, -1, "The car oversteers on exit, so soften the rear anti-roll bar by 1 click."),
        remedy("wheelRate", "rear", -1, "The car oversteers on exit, so soften the rear springs by 1 click."),
    ],
    Symptom(O, EX, HI): [
        remedy("rearWing", None, +1, "The car oversteers on exit from fast corners, so add 1 click of rear wing."),
        remedy("tC1", None, +1, "The car oversteers on exit from fast corners, so add 1 click of traction control.", "AV"),
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
        PressurePhase(*GT3_DRY_WINDOW),
        # Mechanical grip BEFORE aero on a GT3: the car lives on mechanical grip,
        # so fix springs/bars/diff first; masking a mechanical issue with rake/wing
        # is backwards (aero-first is the Formula order, not GT3).
        _MechanicalPhase("mechanical", "Mechanical grip", "BOX"),
        _AeroPhase("aero", "Aero / rake", "BOX"),
        _BrakeBiasPhase("brake_bias", "Brake bias", "AV"),
        _ElectronicsPhase("electronics", "Electronics", "AV"),
    ],
    remedy_table=REMEDY_TABLE,
    al_volo=["Brake bias", "TC", "ABS", "Engine map"],
)
