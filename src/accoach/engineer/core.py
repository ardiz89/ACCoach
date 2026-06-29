"""The class-agnostic race-engineer state machine.

Drives one evaluation per completed lap. The contract is turn-based and
side-effect free, which makes it deterministic and easy to test:

    eng = RaceEngineer(GT3_PROFILE)
    decision = eng.observe(lap_stats)        # feed a lap, get the next move
    if decision.kind is DecisionKind.PROPOSE:
        # show decision.change to the driver; when they WRITE that setup:
        eng.mark_applied()                   # start the re-test window

The engine proposes a change, the driver applies it (via the setup editor /
file), then drives a few laps; the engine measures the effect and decides to
**keep** it (continue) or **revert** it (try the next remedy). It works through
ordered phases (pressures → aero → mechanical → … per the profile), advancing
only when a phase's gate is satisfied.

Safety guards (it moves real setup, so a false positive is costly):

* a symptom drives a change only when it is **both** spread across ≥3 distinct
  corners (setup, not a one-corner driving error) **and** persistent across the
  recent stable laps;
* on a *plateau* (a symptom change that neither helps nor hurts) the change is
  **reverted**, not kept, so the setup can't drift under a blind meter;
* a per-parameter **click budget** caps how far any one lever is pushed in a
  session.

It consumes :class:`LapStats` (the diagnosis) and never touches telemetry.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum


# --- diagnosis vocabulary (the discilli taxonomy) --------------------------

class Balance(Enum):
    UNDERSTEER = "understeer"
    OVERSTEER = "oversteer"


class Phase(Enum):
    ENTRY = "entry"
    APEX = "apex"
    EXIT = "exit"


class Speed(Enum):
    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True)
class Symptom:
    """One handling problem: balance × corner-phase × speed band."""

    balance: Balance
    phase: Phase
    speed: Speed

    def __str__(self) -> str:
        return f"{self.balance.value} {self.phase.value} {self.speed.value}"


# Wheel-indexed setup arrays are FL, FR, RL, RR.
FRONT = (0, 1)
REAR = (2, 3)
ALL = (0, 1, 2, 3)


@dataclass
class LapStats:
    """The diagnosis for a single completed lap (produced by the coaching layer).

    ``symptom_scores`` maps a :class:`Symptom` to an intensity in roughly 0..1
    (0 == absent). ``symptom_corners`` maps a :class:`Symptom` to the number of
    **distinct corners** that showed it this lap — the engine only acts on a
    symptom seen in several corners (setup), not one (driving). ``pressures_hot``
    is per-axle hot pressure in psi (``{"front": .., "rear": ..}``) when known.
    ``stable`` flags a clean lap (no off/pit, lap time within the recent band) —
    only stable laps count.
    """

    lap_time_ms: int
    stable: bool = True
    warmed_up: bool = True
    symptom_scores: dict = field(default_factory=dict)
    symptom_corners: dict = field(default_factory=dict)
    pressures_hot: dict | None = None
    lock_segments: int = 0
    spin_segments: int = 0


# --- recommendations -------------------------------------------------------

@dataclass(frozen=True)
class AtomicChange:
    param: str          # a SETUP_PARAMS key, e.g. "aRBFront", "tyrePressure"
    slot: int | None    # wheel/axle index, or None for a scalar
    delta_clicks: int


@dataclass(frozen=True)
class ProposedChange:
    """A concrete, ready-to-apply setup change with its rationale."""

    changes: tuple[AtomicChange, ...]
    rationale: str
    phase_label: str
    tag: str            # "AV" (al volo) or "BOX" (garage)
    symptom: Symptom | None = None

    @property
    def param(self) -> str:
        return self.changes[0].param if self.changes else ""

    def reversed(self) -> "ProposedChange":
        """The change that undoes this one (used to revert a rejected remedy)."""
        return ProposedChange(
            changes=tuple(AtomicChange(c.param, c.slot, -c.delta_clicks)
                          for c in self.changes),
            rationale="Ripristino: " + self.rationale,
            phase_label=self.phase_label, tag=self.tag, symptom=self.symptom)

    def as_setup_payload(self) -> list[dict]:
        """Shape accepted by ``/api/setup/preview|apply``."""
        return [{"param": c.param, "slot": c.slot, "delta_clicks": c.delta_clicks}
                for c in self.changes]


class DecisionKind(Enum):
    COLLECT = "collect"          # not enough stable laps yet — keep driving
    EVALUATING = "evaluating"    # a change is applied; gathering re-test laps
    PROPOSE = "propose"          # apply this change next
    ACCEPTED = "accepted"        # the last change helped — kept
    REVERTED = "reverted"        # the last change didn't help — undo proposed
    PHASE_DONE = "phase_done"    # this phase's gate is satisfied
    DONE = "done"                # nothing left to improve


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    message: str
    change: ProposedChange | None = None
    confidence: str = ""         # "alta" / "media" on a PROPOSE, else ""


# --- the profile contract --------------------------------------------------

class WorkPhase:
    """A phase of setup work: which symptoms it owns and when it's complete.

    A plain class (not a dataclass) so profile-specific phases can subclass it
    and carry extra state (e.g. a pressure window) without dataclass ceremony.
    """

    def __init__(self, key: str, label: str, tag: str) -> None:
        self.key = key
        self.label = label
        self.tag = tag                    # default tag for this phase's advice

    def owns(self, symptom: Symptom) -> bool:    # pragma: no cover - overridden
        raise NotImplementedError

    def gate(self, window: list[LapStats]) -> bool:  # pragma: no cover
        raise NotImplementedError

    def reconfigure(self, **kw) -> "WorkPhase":
        """Return a variant tuned by ``kw`` (default: unchanged)."""
        return self


@dataclass
class Profile:
    name: str
    phases: list[WorkPhase]
    # symptom -> ordered remedies; each remedy is a callable(symptom)->ProposedChange
    remedy_table: dict
    # knobs the driver can change at the wheel (shown by the class-specific UI)
    al_volo: list[str] = field(default_factory=list)


# --- tuning constants ------------------------------------------------------

_MIN_STABLE = 3                  # laps needed for a baseline / a re-test verdict
_WINDOW = 6                      # rolling stable-lap buffer
_SYMPTOM_THRESH = 0.30           # a symptom counts as "present" above this
_MIN_CORNERS = 3                 # a symptom must span ≥ this many corners to be setup
_EPS_SCORE = 0.10                # min symptom-score drop to call it an improvement
_TIME_BAND_FRAC = 0.0015         # lap-time noise band (0.15%)
_REMEDY_CAP = 5                  # max remedies tried per symptom before giving up
_CLICK_BUDGET = 6                # max net clicks a single parameter may accumulate


def _median_time(window: list[LapStats]) -> float:
    return statistics.median([s.lap_time_ms for s in window]) if window else 0.0


def _median_score(window: list[LapStats], symptom: Symptom) -> float:
    if not window:
        return 0.0
    return statistics.median([s.symptom_scores.get(symptom, 0.0) for s in window])


# --- the engine ------------------------------------------------------------

@dataclass
class _Active:
    change: ProposedChange
    symptom: Symptom
    base_time: float
    base_score: float
    laps_seen: int = 0


class RaceEngineer:
    """Deterministic convergence engine for one car-class :class:`Profile`."""

    def __init__(self, profile: Profile, *, min_stable: int = _MIN_STABLE,
                 pressure_window: tuple[float, float] | None = None) -> None:
        self.profile = profile
        self.min_stable = min_stable
        # Engine-local phase list, so a car/track-specific pressure window can be
        # applied without mutating the shared profile singleton.
        self.phases = [
            p.reconfigure(pressure_window=pressure_window) if pressure_window else p
            for p in profile.phases
        ]
        self.phase_idx = 0
        self.window: list[LapStats] = []
        self.active: _Active | None = None
        self.remedy_idx: dict[Symptom, int] = {}     # next remedy to try
        self.exhausted: set[Symptom] = set()         # no remedy helped
        self.history: list[ProposedChange] = []      # accepted changes
        self.applied_clicks: dict[str, int] = {}     # net clicks per parameter
        self._pending: ProposedChange | None = None  # proposed, awaiting mark_applied
        self._pending_is_revert = False              # the pending change is a restore

    # -- public API --------------------------------------------------------
    @property
    def phase(self) -> WorkPhase | None:
        return self.phases[self.phase_idx] if self.phase_idx < len(self.phases) else None

    def observe(self, stats: LapStats) -> Decision:
        """Feed one completed lap; return the next recommendation."""
        if stats.stable and stats.warmed_up:
            self.window.append(stats)
            self.window = self.window[-_WINDOW:]
            if self.active is not None:
                self.active.laps_seen += 1

        # An applied change under evaluation takes priority.
        if self.active is not None:
            return self._evaluate_active()

        if len(self.window) < self.min_stable:
            return Decision(DecisionKind.COLLECT,
                            f"Servono {self.min_stable} giri puliti per una base "
                            f"(ne ho {len(self.window)}).")
        return self._advance()

    def mark_applied(self) -> None:
        """Tell the engine the last PROPOSE (or revert) was written to the setup."""
        if self._pending is None:
            return
        if self._pending_is_revert:
            # The driver restored the previous setup. Don't evaluate the revert or
            # bank it: the bad change was never recorded, so undoing it must not
            # touch the click budget. Just resume collecting fresh laps so the next
            # remedy's baseline is measured on the restored setup, not the bad one.
            self.active = None
            self.window = []
            self._pending = None
            self._pending_is_revert = False
            return
        sym = self._pending.symptom
        self.active = _Active(
            change=self._pending,
            symptom=sym,
            base_time=_median_time(self.window),
            base_score=_median_score(self.window, sym) if sym else 0.0,
        )
        # The reference shifts when the setup changes — restart the window so the
        # verdict is measured only on post-change laps.
        self.window = []
        self._pending = None

    def _revert(self, change: ProposedChange, message: str) -> Decision:
        """Reject a change: propose its reversal AND hold it as a *pending revert*.

        Resets the window so the engine returns to COLLECT — it won't propose the
        next remedy until the driver has applied the restore and driven fresh laps,
        and the next baseline is measured on the restored setup, not on the
        rejected one. :meth:`mark_applied` recognises the revert and just
        acknowledges it (no re-test cycle, no click-budget change)."""
        rev = change.reversed()
        self._pending = rev
        self._pending_is_revert = True
        self.window = []
        return Decision(DecisionKind.REVERTED, message, rev)

    # -- internals ---------------------------------------------------------
    def _advance(self) -> Decision:
        """No active change: check the gate, else propose the next remedy."""
        phase = self.phase
        if phase is None:
            return Decision(DecisionKind.DONE,
                            "Setup a posto: nessun guadagno residuo. Buona base.")
        if phase.gate(self.window):
            self.phase_idx += 1
            nxt = self.phase
            tail = f" → passo a: {nxt.label}" if nxt else " → setup completo"
            return Decision(DecisionKind.PHASE_DONE,
                            f"Fase '{phase.label}' completata{tail}.")

        symptom = self._dominant_symptom(phase)
        if symptom is None:
            # Gate not met but no symptom we can act on (e.g. pressures out of
            # window is handled by the gate's own remedy path below).
            change = self._pressure_remedy(phase)
            if change is not None:
                self._pending = change
                self._pending_is_revert = False
                return Decision(DecisionKind.PROPOSE, change.rationale, change, "alta")
            # Nothing actionable here; treat the phase as done to avoid a stall.
            self.phase_idx += 1
            return Decision(DecisionKind.PHASE_DONE,
                            f"Fase '{phase.label}': nulla da correggere.")

        change = self._remedy_for(symptom, phase)
        if change is None:
            self.exhausted.add(symptom)
            return Decision(DecisionKind.PHASE_DONE,
                            f"'{symptom}': rimedi di setup esauriti — probabile "
                            f"questione di guida.")
        self._pending = change
        self._pending_is_revert = False
        return Decision(DecisionKind.PROPOSE, change.rationale, change,
                        self._confidence(symptom))

    def _evaluate_active(self) -> Decision:
        a = self.active
        if a.laps_seen < self.min_stable:
            need = self.min_stable - a.laps_seen
            return Decision(DecisionKind.EVALUATING,
                            f"Valuto la modifica: {need} giri puliti ancora.")

        new_time = _median_time(self.window)
        new_score = _median_score(self.window, a.symptom)
        d_time = new_time - a.base_time
        d_score = new_score - a.base_score
        band = max(a.base_time * _TIME_BAND_FRAC, 1.0)

        self.active = None
        band_ok = d_time <= band

        # Structural changes (e.g. tyre pressures) carry no symptom: judge them on
        # lap time alone and let the phase gate re-check the real target.
        if a.symptom is None:
            if not band_ok:
                return self._revert(a.change,
                                    "La modifica ha peggiorato il tempo: ripristino.")
            self._record(a.change)
            return Decision(DecisionKind.ACCEPTED, "Modifica applicata, proseguo.")

        improved = d_score <= -_EPS_SCORE and band_ok

        if improved:
            self._record(a.change)
            if new_score < _SYMPTOM_THRESH:
                return Decision(DecisionKind.ACCEPTED,
                                f"Tenuta: '{a.symptom}' risolto "
                                f"({a.base_score:.2f}→{new_score:.2f}).")
            return Decision(DecisionKind.ACCEPTED,
                            f"Tenuta: '{a.symptom}' migliora, continuo "
                            f"({a.base_score:.2f}→{new_score:.2f}).")

        # Not an improvement (worse OR plateau): revert and try the next lever.
        # Reverting on a plateau too is deliberate — keeping changes a blind meter
        # reads as "harmless" is exactly how setup drift creeps in.
        self.remedy_idx[a.symptom] = self.remedy_idx.get(a.symptom, 0) + 1
        reason = ("Modifica peggiorativa" if not band_ok or d_score > _EPS_SCORE
                  else "Nessun effetto misurabile")
        return self._revert(a.change,
                            f"{reason}: ripristino e provo un'altra leva per "
                            f"'{a.symptom}'.")

    # -- symptom selection with safety gates -------------------------------
    def _corners(self, sym: Symptom) -> int:
        return max((s.symptom_corners.get(sym, 0) for s in self.window), default=0)

    def _persistence(self, sym: Symptom) -> int:
        return sum(1 for s in self.window
                   if s.symptom_scores.get(sym, 0.0) >= _SYMPTOM_THRESH)

    def _confidence(self, sym: Symptom) -> str:
        return ("alta" if self._corners(sym) >= 4
                and _median_score(self.window, sym) >= 0.5 else "media")

    def _dominant_symptom(self, phase: WorkPhase) -> Symptom | None:
        seen: set[Symptom] = set()
        for s in self.window:
            seen.update(s.symptom_scores.keys())
        best, best_score = None, _SYMPTOM_THRESH
        for sym in seen:
            if sym in self.exhausted or not phase.owns(sym):
                continue
            score = _median_score(self.window, sym)
            if score < best_score:
                continue
            # Setup, not driving: must span several corners AND persist over laps.
            if self._corners(sym) < _MIN_CORNERS:
                continue
            if self._persistence(sym) < self.min_stable:
                continue
            best, best_score = sym, score
        return best

    def _remedy_for(self, symptom: Symptom, phase: WorkPhase) -> ProposedChange | None:
        remedies = self.profile.remedy_table.get(symptom)
        if not remedies:
            return None
        idx = self.remedy_idx.get(symptom, 0)
        while idx < len(remedies) and idx < _REMEDY_CAP:
            change = remedies[idx](symptom, phase)
            if self._over_budget(change):
                idx += 1
                continue
            self.remedy_idx[symptom] = idx
            return change
        self.remedy_idx[symptom] = idx
        return None

    def _over_budget(self, change: ProposedChange) -> bool:
        param = change.param
        projected = self.applied_clicks.get(param, 0) + change.changes[0].delta_clicks
        return abs(projected) > _CLICK_BUDGET

    def _record(self, change: ProposedChange) -> None:
        """Bank an accepted change: history + per-parameter click budget."""
        self.history.append(change)
        if change.changes:
            param = change.param
            self.applied_clicks[param] = (
                self.applied_clicks.get(param, 0) + change.changes[0].delta_clicks)

    def _pressure_remedy(self, phase: WorkPhase) -> ProposedChange | None:
        """If this phase gates on tyre pressure, nudge the off-target axle."""
        builder = getattr(phase, "pressure_remedy", None)
        if builder is None or not self.window:
            return None
        return builder(self.window[-1])
