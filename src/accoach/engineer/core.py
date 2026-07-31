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

from ..i18n import current_language


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
    # Symptom -> list of corner indices where it showed (so a proposal can be
    # anchored to "Corners 7, 9" instead of a faceless symptom).
    symptom_corner_idx: dict = field(default_factory=dict)
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
        lang = current_language()
        prefix = _REVERT_PREFIX.get(lang) or _REVERT_PREFIX["en"]
        return ProposedChange(
            changes=tuple(AtomicChange(c.param, c.slot, -c.delta_clicks)
                          for c in self.changes),
            rationale=prefix + self.rationale,
            phase_label=self.phase_label, tag=self.tag, symptom=self.symptom)

    def as_setup_payload(self) -> list[dict]:
        """Shape accepted by ``/api/setup/preview|apply``."""
        return [{"param": c.param, "slot": c.slot, "delta_clicks": c.delta_clicks}
                for c in self.changes]


@dataclass(frozen=True)
class Prediction:
    """What this change is expected to do, said *before* the laps are driven.

    Be clear about what this is and isn't. The bar below is the engine's own
    acceptance rule — the symptom has to drop by at least ``_EPS_SCORE`` and the
    lap time must not fall outside the noise band — so a prediction that "hits"
    is, by construction, a change that was kept. It is **not** a second,
    independent test, and this docstring exists so nobody later reads it as one.

    Its value is the order in which the driver learns things. Until now the loop
    said "try this", took the car away for three laps and came back with a
    verdict; the driver had no way to disagree, because they never knew what was
    being measured. Stating the bar first turns that into something checkable
    from the cockpit: you are told the number to beat, and afterwards you are
    told whether you beat it.

    Where a *real* prediction can eventually come from is the ledger
    (``ledger.py``): what a lever does to the symptoms nobody was aiming at is
    measured there and asserted nowhere, until there is enough of it to mean
    something.
    """

    symptom: Symptom | None
    score_now: float          # the symptom's typical score before the change
    score_below: float        # the bar it has to get under for this to count
    time_band_ms: float       # how much lap time it may cost and still count
    text: str = ""            # the sentence the driver reads before driving


@dataclass(frozen=True)
class Outcome:
    """What actually happened, next to what was said would happen."""

    prediction: Prediction
    score_after: float
    time_before_ms: float
    time_after_ms: float
    laps: int
    kept: bool
    remedy_rank: int = 0
    #: {Symptom: score change} for symptoms this change was *not* aiming at, and
    #: which the verdict therefore never looked at. Measured, never predicted.
    side_effects: tuple = ()


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
    confidence: str = ""         # "high" / "medium" on a PROPOSE, else ""
    #: On a PROPOSE: the bar this change will be judged against, so the driver
    #: reads it before driving instead of after.
    prediction: Prediction | None = None
    #: On an ACCEPTED / REVERTED: what happened, with the numbers on both sides.
    #: This is what `ledger.py` writes down.
    outcome: Outcome | None = None


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


# Decision messages, per language; resolved with the active app language at the
# moment a Decision is built (the engine runs in the engine = config.language).
# The Symptom string ({sym}) is a technical identifier and stays as-is; the phase
# label is translated via the profiles' EN→IT map (see profiles/_common.tr).
_DECISION_MSG = {
    "collect": {
        "en": "Need {n} clean laps for a baseline (have {have}).",
        "it": "Servono {n} giri puliti per una base (ne ho {have}).",
    },
    "done": {
        "en": "Setup is solid: no further gains. Good baseline.",
        "it": "Setup a posto: nessun guadagno residuo. Buona base.",
    },
    "phase_done": {
        "en": "Phase '{label}' complete{tail}.",
        "it": "Fase '{label}' completata{tail}.",
    },
    "phase_tail_next": {
        "en": " → moving to: {nxt}",
        "it": " → passo a: {nxt}",
    },
    "phase_tail_complete": {
        "en": " → setup complete",
        "it": " → setup completo",
    },
    "phase_nothing": {
        "en": "Phase '{label}': nothing to correct.",
        "it": "Fase '{label}': nulla da correggere.",
    },
    "remedies_exhausted": {
        "en": "'{sym}': setup remedies exhausted — likely a driving issue.",
        "it": "'{sym}': rimedi di setup esauriti — probabile questione di guida.",
    },
    "evaluating": {
        "en": "Evaluating the change: {need} more clean laps.",
        "it": "Valuto la modifica: {need} giri puliti ancora.",
    },
    "accepted_structural": {
        "en": "Change applied, moving on.",
        "it": "Modifica applicata, proseguo.",
    },
    "revert_structural": {
        "en": "The change worsened the lap time: reverting.",
        "it": "La modifica ha peggiorato il tempo: ripristino.",
    },
    "accepted_resolved": {
        "en": "Handling: '{sym}' resolved ({a:.2f}→{b:.2f}).",
        "it": "Tenuta: '{sym}' risolto ({a:.2f}→{b:.2f}).",
    },
    "accepted_improving": {
        "en": "Handling: '{sym}' improving, continuing ({a:.2f}→{b:.2f}).",
        "it": "Tenuta: '{sym}' migliora, continuo ({a:.2f}→{b:.2f}).",
    },
    "revert_reason": {
        "en": "{reason}: reverting and trying another lever for '{sym}'.",
        "it": "{reason}: ripristino e provo un'altra leva per '{sym}'.",
    },
    "reason_worse": {
        "en": "Change made it worse",
        "it": "Modifica peggiorativa",
    },
    "predict": {
        "en": "How you'll know: '{sym}' has to come down from {a:.2f} to under "
              "{b:.2f} over {n} clean laps, without the lap time getting worse "
              "by more than {ms:.0f} ms. If it doesn't, I put it back.",
        "it": "Come lo capiremo: «{sym}» deve scendere da {a:.2f} sotto {b:.2f} "
              "in {n} giri puliti, senza che il tempo peggiori di più di "
              "{ms:.0f} ms. Se non succede, la rimetto com'era.",
    },
    "predict_structural": {
        "en": "How you'll know: over {n} clean laps the lap time must not get "
              "worse by more than {ms:.0f} ms. If it does, I put it back.",
        "it": "Come lo capiremo: in {n} giri puliti il tempo non deve peggiorare "
              "di più di {ms:.0f} ms. Se peggiora, la rimetto com'era.",
    },
    "side_effect": {
        "en": " Also moved, and nobody was aiming at it: {items}.",
        "it": " Si è mosso anche questo, e non lo stavamo cercando: {items}.",
    },
    "reason_noeffect": {
        "en": "No measurable effect",
        "it": "Nessun effetto misurabile",
    },
}

_REVERT_PREFIX = {"en": "Revert: ", "it": "Ripristino: "}


def _msg(key: str, lang: str | None = None, **kw) -> str:
    lang = lang or current_language()
    entry = _DECISION_MSG[key]
    return (entry.get(lang) or entry["en"]).format(**kw)


def _side_effect_tail(outcome: "Outcome", lang: str) -> str:
    """Name what moved that nobody was aiming at — after the verdict, never before.

    The engine judged one symptom; this is the rest of the car answering. It is
    appended to the message rather than replacing it because it does not change
    the verdict: a change is kept or reverted on its target, and a side effect
    the driver isn't told about is one they'll meet in the next corner instead.
    """
    if not outcome.side_effects:
        return ""
    items = ", ".join(f"{sym} {delta:+.2f}" for sym, delta in outcome.side_effects)
    return _msg("side_effect", lang, items=items)


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
    prediction: "Prediction | None" = None
    remedy_rank: int = 0
    #: Every symptom's score at the moment the change was applied, so the
    #: verdict can also report what moved that nobody was aiming at.
    base_scores: dict = field(default_factory=dict)


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
        self._pending_prediction: Prediction | None = None
        #: Symptoms whose remedies all failed — the engine's own "this is you,
        #: not the car" call. Recorded because it is a claim we make and have
        #: never checked (see ledger.py).
        self.exhausted_calls: list[Symptom] = []

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
                            _msg("collect", n=self.min_stable,
                                 have=len(self.window)))
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
            self._pending_prediction = None
            return
        sym = self._pending.symptom
        self.active = _Active(
            change=self._pending,
            symptom=sym,
            base_time=_median_time(self.window),
            base_score=_median_score(self.window, sym) if sym else 0.0,
            prediction=self._pending_prediction,
            remedy_rank=self.remedy_idx.get(sym, 0) if sym else 0,
            # Every symptom on the books, not just the target: the verdict is
            # about one of them, the ledger is about all of them.
            base_scores=self._all_scores(),
        )
        # The reference shifts when the setup changes — restart the window so the
        # verdict is measured only on post-change laps.
        self.window = []
        self._pending = None
        self._pending_prediction = None

    # -- the prediction ----------------------------------------------------
    def _all_scores(self) -> dict:
        """Every symptom's typical score over the current window."""
        seen: set[Symptom] = set()
        for s in self.window:
            seen.update(s.symptom_scores.keys())
        return {sym: _median_score(self.window, sym) for sym in seen}

    def _predict(self, change: ProposedChange) -> Prediction:
        """The bar this change will be judged against, stated in advance.

        Nothing here is a guess: every number is the rule ``_evaluate_active``
        is about to apply. That is the point — the driver is told the test
        before sitting the exam, not the grade afterwards.
        """
        lang = current_language()
        sym = change.symptom
        base_time = _median_time(self.window)
        band = max(base_time * _TIME_BAND_FRAC, 1.0)
        if sym is None:
            return Prediction(
                symptom=None, score_now=0.0, score_below=0.0, time_band_ms=band,
                text=_msg("predict_structural", lang, n=self.min_stable, ms=band))
        now = _median_score(self.window, sym)
        bar = round(now - _EPS_SCORE, 3)
        return Prediction(
            symptom=sym, score_now=round(now, 3), score_below=bar,
            time_band_ms=band,
            text=_msg("predict", lang, sym=str(sym), a=now, b=bar,
                      n=self.min_stable, ms=band))

    def _propose(self, change: ProposedChange, confidence: str) -> Decision:
        """Hold a change as pending and hand it over with its acceptance bar."""
        self._pending = change
        self._pending_is_revert = False
        self._pending_prediction = self._predict(change)
        return Decision(DecisionKind.PROPOSE, change.rationale, change,
                        confidence, prediction=self._pending_prediction)

    def _side_effects(self, a: "_Active") -> tuple:
        """Symptoms that moved and weren't the target, worst first.

        Only what cleared the same bar the verdict uses for the target: below it
        the engine already refuses to call a change an improvement, so calling
        it a side effect would be a stricter claim made on weaker evidence.
        """
        after = self._all_scores()
        out = []
        for sym, before in a.base_scores.items():
            if sym == a.symptom:
                continue
            delta = after.get(sym, 0.0) - before
            if abs(delta) >= _EPS_SCORE:
                out.append((sym, round(delta, 3)))
        out.sort(key=lambda kv: abs(kv[1]), reverse=True)
        return tuple(out)

    def _outcome(self, a: "_Active", *, kept: bool, score_after: float) -> Outcome:
        return Outcome(
            prediction=a.prediction or self._predict(a.change),
            score_after=round(score_after, 3),
            time_before_ms=round(a.base_time, 1),
            time_after_ms=round(_median_time(self.window), 1),
            laps=a.laps_seen, kept=kept, remedy_rank=a.remedy_rank,
            side_effects=self._side_effects(a),
        )

    def _revert(self, change: ProposedChange, message: str,
                outcome: "Outcome | None" = None) -> Decision:
        """Reject a change: propose its reversal AND hold it as a *pending revert*.

        Resets the window so the engine returns to COLLECT — it won't propose the
        next remedy until the driver has applied the restore and driven fresh laps,
        and the next baseline is measured on the restored setup, not on the
        rejected one. :meth:`mark_applied` recognises the revert and just
        acknowledges it (no re-test cycle, no click-budget change)."""
        rev = change.reversed()
        self._pending = rev
        self._pending_is_revert = True
        # The outcome has to be built by the caller, before this line: the window
        # it is measured from is cleared right here.
        self.window = []
        return Decision(DecisionKind.REVERTED, message, rev, outcome=outcome)

    # -- internals ---------------------------------------------------------
    def _advance(self) -> Decision:
        """No active change: check the gate, else propose the next remedy."""
        # Lazy import avoids a module-level cycle (profiles import from core).
        from .profiles._common import tr
        lang = current_language()
        phase = self.phase
        if phase is None:
            return Decision(DecisionKind.DONE, _msg("done", lang))
        if phase.gate(self.window):
            self.phase_idx += 1
            nxt = self.phase
            tail = (_msg("phase_tail_next", lang, nxt=tr(nxt.label)) if nxt
                    else _msg("phase_tail_complete", lang))
            return Decision(DecisionKind.PHASE_DONE,
                            _msg("phase_done", lang, label=tr(phase.label),
                                 tail=tail))

        symptom = self._dominant_symptom(phase)
        if symptom is None:
            # Gate not met but no symptom we can act on (e.g. pressures out of
            # window is handled by the gate's own remedy path below).
            change = self._pressure_remedy(phase)
            if change is not None:
                return self._propose(change, "high")
            # Nothing actionable here; treat the phase as done to avoid a stall.
            self.phase_idx += 1
            return Decision(DecisionKind.PHASE_DONE,
                            _msg("phase_nothing", lang, label=tr(phase.label)))

        change = self._remedy_for(symptom, phase)
        if change is None:
            self.exhausted.add(symptom)
            # "Setup can't fix this, so it's you" is a claim, and one we have
            # never checked. Kept so the ledger can count how often we make it.
            self.exhausted_calls.append(symptom)
            return Decision(DecisionKind.PHASE_DONE,
                            _msg("remedies_exhausted", lang, sym=str(symptom)))
        return self._propose(change, self._confidence(symptom))

    def _evaluate_active(self) -> Decision:
        a = self.active
        lang = current_language()
        if a.laps_seen < self.min_stable:
            need = self.min_stable - a.laps_seen
            return Decision(DecisionKind.EVALUATING,
                            _msg("evaluating", lang, need=need))

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
                out = self._outcome(a, kept=False, score_after=0.0)
                return self._revert(a.change, _msg("revert_structural", lang), out)
            out = self._outcome(a, kept=True, score_after=0.0)
            self._record(a.change)
            return Decision(DecisionKind.ACCEPTED,
                            _msg("accepted_structural", lang), outcome=out)

        improved = d_score <= -_EPS_SCORE and band_ok

        if improved:
            out = self._outcome(a, kept=True, score_after=new_score)
            self._record(a.change)
            key = ("accepted_resolved" if new_score < _SYMPTOM_THRESH
                   else "accepted_improving")
            msg = _msg(key, lang, sym=str(a.symptom), a=a.base_score, b=new_score)
            return Decision(DecisionKind.ACCEPTED, msg + _side_effect_tail(out, lang),
                            outcome=out)

        # Not an improvement (worse OR plateau): revert and try the next lever.
        # Reverting on a plateau too is deliberate — keeping changes a blind meter
        # reads as "harmless" is exactly how setup drift creeps in.
        out = self._outcome(a, kept=False, score_after=new_score)
        self.remedy_idx[a.symptom] = self.remedy_idx.get(a.symptom, 0) + 1
        reason = (_msg("reason_worse", lang) if not band_ok or d_score > _EPS_SCORE
                  else _msg("reason_noeffect", lang))
        return self._revert(a.change,
                            _msg("revert_reason", lang, reason=reason,
                                 sym=str(a.symptom)), out)

    # -- symptom selection with safety gates -------------------------------
    def _corners(self, sym: Symptom) -> int:
        return max((s.symptom_corners.get(sym, 0) for s in self.window), default=0)

    def corners_for(self, sym: Symptom | None) -> list[int]:
        """Distinct corner indices where ``sym`` showed across the window — the
        evidence to anchor a proposal to (e.g. 'Corners 7, 9')."""
        if sym is None:
            return []
        out: set[int] = set()
        for s in self.window:
            out.update(s.symptom_corner_idx.get(sym, []))
        return sorted(out)

    def _persistence(self, sym: Symptom) -> int:
        return sum(1 for s in self.window
                   if s.symptom_scores.get(sym, 0.0) >= _SYMPTOM_THRESH)

    def _confidence(self, sym: Symptom) -> str:
        return ("high" if self._corners(sym) >= 4
                and _median_score(self.window, sym) >= 0.5 else "medium")

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
        # Budget per (param, slot): toe-front and toe-rear (or front/rear pressure)
        # are different physical levers and must not share — or cancel — one budget.
        for c in change.changes:
            projected = self.applied_clicks.get((c.param, c.slot), 0) + c.delta_clicks
            if abs(projected) > _CLICK_BUDGET:
                return True
        return False

    def _record(self, change: ProposedChange) -> None:
        """Bank an accepted change: history + per-(param, slot) click budget."""
        self.history.append(change)
        for c in change.changes:
            key = (c.param, c.slot)
            self.applied_clicks[key] = self.applied_clicks.get(key, 0) + c.delta_clicks

    def _pressure_remedy(self, phase: WorkPhase) -> ProposedChange | None:
        """If this phase gates on tyre pressure, nudge the off-target axle."""
        builder = getattr(phase, "pressure_remedy", None)
        if builder is None or not self.window:
            return None
        return builder(self.window[-1])
