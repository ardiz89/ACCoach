"""Shared building blocks for the per-class engineer profiles.

Symptom/phase aliases, the remedy-builder factory, and a generic tyre-pressure
phase parameterised by the class's hot-pressure window.
"""

from __future__ import annotations

from ..core import (
    ALL,
    FRONT,
    REAR,
    _SYMPTOM_THRESH,
    _median_score,
    AtomicChange,
    Balance,
    LapStats,
    Phase,
    ProposedChange,
    Speed,
    Symptom,
    WorkPhase,
)

# Short aliases used throughout the remedy tables.
U, O = Balance.UNDERSTEER, Balance.OVERSTEER
EN, AP, EX = Phase.ENTRY, Phase.APEX, Phase.EXIT
LO, HI = Speed.LOW, Speed.HIGH

_PSI_PER_CLICK = 0.1
_SEG_LIMIT = 3                 # lock/spin segments that count as "recurring"

_SLOTS = {"front": FRONT, "rear": REAR, "all": ALL, None: (None,)}


def all_symptoms(window: list[LapStats]) -> set[Symptom]:
    out: set[Symptom] = set()
    for s in window:
        out.update(s.symptom_scores.keys())
    return out


def none_present(window: list[LapStats], owns) -> bool:
    """True if no symptom this phase owns is present across the window."""
    for sym in all_symptoms(window):
        if owns(sym) and _median_score(window, sym) >= _SYMPTOM_THRESH:
            return False
    return True


def remedy(param: str, target, step: int, why: str, tag: str = "BOX"):
    """Factory: returns a builder(symptom, phase) -> ProposedChange."""
    def build(symptom: Symptom, phase: WorkPhase) -> ProposedChange:
        slots = _SLOTS[target]
        atomics = tuple(AtomicChange(param, s, step) for s in slots)
        return ProposedChange(atomics, why, phase.label, tag, symptom)
    return build


class PressurePhase(WorkPhase):
    """Tyre-pressure phase, parameterised by the class's hot-pressure window.

    Owns no symptom (it gates on the pressures themselves); proposes a click
    nudge on whichever axle is out of the window.
    """

    def __init__(self, target_psi: float, tol: float,
                 key: str = "pressures", label: str = "Pressures",
                 tag: str = "BOX") -> None:
        super().__init__(key, label, tag)
        self.target = target_psi
        self.tol = tol

    def reconfigure(self, **kw) -> "PressurePhase":
        pw = kw.get("pressure_window")
        if not pw:
            return self
        return PressurePhase(pw[0], pw[1], self.key, self.label, self.tag)

    def owns(self, symptom: Symptom) -> bool:
        return False

    def gate(self, window: list[LapStats]) -> bool:
        recent = [s for s in window if s.pressures_hot]
        if not recent:
            return True                       # no pressure data → can't act, move on
        last = recent[-1].pressures_hot
        return all(abs(last.get(ax, self.target) - self.target) <= self.tol
                   for ax in ("front", "rear"))

    def pressure_remedy(self, stats: LapStats) -> ProposedChange | None:
        if not stats.pressures_hot:
            return None
        for ax, slots in (("front", FRONT), ("rear", REAR)):
            cur = stats.pressures_hot.get(ax)
            if cur is None or abs(cur - self.target) <= self.tol:
                continue
            clicks = round((self.target - cur) / _PSI_PER_CLICK)
            clicks = max(-8, min(8, clicks)) or (1 if cur < self.target else -1)
            atomics = tuple(AtomicChange("tyrePressure", s, clicks) for s in slots)
            why = (f"{ax.capitalize()} pressure out of window "
                   f"({cur:.1f}→~{self.target} psi): "
                   f"{'+' if clicks > 0 else ''}{clicks} clicks")
            return ProposedChange(atomics, why, self.label, "BOX")
        return None
