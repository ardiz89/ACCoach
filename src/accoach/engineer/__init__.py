"""The race-engineer convergence engine.

Turns a per-lap *diagnosis* (the discilli taxonomy: understeer/oversteer ×
entry/apex/exit × low/high speed, plus lock/spin and tyre pressures) into a
deterministic, lap-by-lap sequence of setup changes — one parameter at a time,
re-tested over a few stable laps, kept only if it doesn't make things worse.

Two layers (see ``ENGINEER.md``):

* :mod:`accoach.engineer.core` — the class-agnostic state machine (phases, gates,
  accept/reject, anti-loop). It consumes :class:`~accoach.engineer.core.LapStats`
  and emits :class:`~accoach.engineer.core.Decision` recommendations; it never
  reads telemetry itself.
* :mod:`accoach.engineer.profiles` — per-class profiles (GT3 first) that supply
  the phase order, gates and the symptom→remedy table.

The diagnosis (computing LapStats from telemetry) lives in the coaching layer;
this package only decides *what to change next*.
"""

from .classmap import CarClass, classify, profile_for, profile_for_car
from .factory import engineer_for
from .pressures import pressure_window
from .core import (
    Balance,
    Decision,
    DecisionKind,
    LapStats,
    Phase,
    ProposedChange,
    RaceEngineer,
    Speed,
    Symptom,
)

__all__ = [
    "Balance",
    "Decision",
    "DecisionKind",
    "LapStats",
    "Phase",
    "ProposedChange",
    "RaceEngineer",
    "Speed",
    "Symptom",
    "CarClass",
    "classify",
    "profile_for",
    "profile_for_car",
    "engineer_for",
    "pressure_window",
]
