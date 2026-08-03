"""The headless coaching engine.

All the live logic — read telemetry, record laps, compare to the reference,
analyze corners, detect events, schedule and (optionally) speak cues — lives
here, decoupled from any UI. Drive it from a loop:

    engine = CoachEngine(voice=Voice())
    while True:
        state = engine.tick(time.monotonic())
        render(state)              # terminal, overlay, websocket — anything

The terminal coach, the websocket server and any future overlay all consume the
same :class:`EngineState`, so there's exactly one implementation of the coaching
behaviour. The reader and voice are injectable, which makes the engine testable
with scripted snapshots and no audio.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from .coaching import (
    BalanceDetector,
    BrakingDetector,
    CoachAnalyzer,
    Cue,
    CueScheduler,
    EventDetector,
    FuelEngineer,
    GearDetector,
    PressureAdvisor,
    SetupAdvisor,
    TyreTempAdvisor,
    Voice,
)
from .coaching.cue import CueCategory
from .coaching.debrief import build_lap_debrief
from .coaching.diagnosis import build_lap_stats
from .coaching.atwheel import WheelWatch
from .coaching.focus import FocusCoach, FocusReport
from .coaching.pitcall import PitCall
from .i18n import cue_text, current_language
from .comparison import DeltaState, LapComparator, Reference
from .engineer import RaceEngineer, classify, engineer_for
from .recording import Lap, LapRecorder, find_reference_lap, laps_root, save_lap
from .recording.recorder import StartLineWatcher
from .telemetry import SharedMemoryReader, TelemetrySnapshot
from .telemetry.snapshot import ACStatus
from .telemetry.feed import TelemetryFeed
from .track import Corner, detect_corners

# When you're not on a representative flying lap — delta has ballooned because
# you're crawling, recovering from an off, or parked — only acute safety cues
# (lock-up, wheelspin, slides, fuel) are worth speaking. Technique and setup
# advice on a throw-away lap is noise (live validation 2026-06-26: the coach
# machine-gunned coasting/trail cues and even praised a +12 s disaster lap).
_GATE_DELTA_MS = 3000.0

# Only these are spoken on an abnormal lap. Note: under/oversteer cues are ACUTE
# (real-time faults) but NOT here — on a cold/recovery lap the car slides
# everywhere and naming it is the exact spam the gate exists to remove; a genuine
# lock-up or wheelspin still gets called.
_SAFETY_CATEGORIES = {
    CueCategory.LOCKED, CueCategory.WHEELSPIN, CueCategory.FUEL,
    # The pit calls pass every gate by construction. The gate's job is to stop
    # driving advice on a lap it can't apply to; these two are the opposite —
    # PIT_BRIEFING is spoken *because* the car is stopped in the box, which is
    # exactly the state `quiet == "pit"` describes, and gating it would make the
    # one cue that only makes sense there the one cue that never arrives.
    CueCategory.PIT_IN, CueCategory.PIT_APPROACH, CueCategory.PIT_BRIEFING,
}

# A spoken alert prefix for an engineer proposal, by confidence-tone × tag ×
# language. The proposal's rationale (already localized) follows it; the prefix
# tells the driver *whether* it needs the garage (BOX) or can be dialled at the
# wheel (AV). A medium-confidence proposal gets a tentative wording so the tone
# itself signals how much to trust it — the advice still reaches the ear, the
# screen still shows the click count, but the voice doesn't oversell a guess.
_ENG_VOICE_PREFIX = {
    "firm": {
        "BOX": {"it": "Ingegnere: rientra ai box.",
                "en": "Engineer: box this lap."},
        "AV": {"it": "Ingegnere: puoi farlo al volo.",
               "en": "Engineer: you can do this at the wheel."},
    },
    "tentative": {
        "BOX": {"it": "Ingegnere, da valutare ai box:",
                "en": "Engineer, worth trying in the box:"},
        "AV": {"it": "Ingegnere, da valutare al volo:",
               "en": "Engineer, worth trying at the wheel:"},
    },
}


def _decision_sig(decision) -> tuple | None:
    """Identity of an engineer proposal, for "have we already handled this one".

    Same shape the spoken-once latch uses: the kind plus the rationale, which is
    what actually distinguishes two proposals to a driver. ``None`` for anything
    carrying no change (COLLECT / EVALUATING / …) so those can never match a real
    proposal's signature.
    """
    if decision is None or decision.change is None:
        return None
    return (decision.kind.value, decision.change.rationale or "")


def _voice_clean(text: str) -> str:
    """Trim a rationale for speech: drop the trailing click parenthetical (e.g.
    ' (−1)') that SAPI5 reads awkwardly — the direction word ('più morbida',
    'meno') already conveys it; the exact click count stays on screen."""
    import re  # noqa: PLC0415 (local: keeps the hot-path import list lean)
    return re.sub(r"\s*\([+\-−–]?\d+\)\s*$", "", text).strip()


@dataclass(slots=True)
class EngineState:
    """One tick of everything a frontend needs to show."""

    snapshot: TelemetrySnapshot
    delta: DeltaState | None
    spoken: Cue | None           # the cue spoken this tick, if any
    saved_laps: int
    reference_ms: int            # reference lap time, 0 if none
    history: list[str]           # recent spoken cue messages, newest last
    engineer: dict | None = None  # latest race-engineer decision (setup advice)
    focus: dict | None = None     # latest Focus/Lesson report (driver coaching)
    # Why the coach is holding back, "" when it's coaching normally. Every gate
    # has to say so: a silent gate reads as a broken app (the driver's own words
    # after a calibration session were "I drove and nothing happened").
    quiet: str = ""              # "" | "pit" | "out_lap" | "no_reference" | "off_pace"
    # The game says this lap is already invalidated (ACC only; None on AC, where
    # the page ends before the flag). Not a gate: an invalidated lap is a free
    # lap, and everything but the stopwatch still applies. It only tells the
    # frontend to stop showing a delta that compares against a lap that won't
    # count.
    lap_invalid: bool = False


def _load_reference(car: str, track: str, laps_dir: Path | str,
                    road_temp: float | None = None,
                    grip: float | None = None,
                    compound: str | None = None) -> Reference | None:
    lap = find_reference_lap(car, track, laps_dir, road_temp, grip, compound)
    if lap is None:
        return None
    ref = Reference(lap)
    return ref if ref.usable else None


class CoachEngine:
    """Stateful coaching engine; one :meth:`tick` per frame."""

    def __init__(
        self,
        reader: SharedMemoryReader | None = None,
        voice: Voice | None = None,
        num_segments: int = 24,
        laps_dir: Path | str | None = None,
        feed: TelemetryFeed | None = None,
        acquire_hz: float | None = None,
        engineer_voice: bool = True,
    ) -> None:
        self.reader = reader if reader is not None else SharedMemoryReader()
        self.voice = voice
        # Whether to speak the race engineer's proposals (the per-cue coaching
        # voice is governed by ``voice`` itself; this gates only the engineer).
        self.engineer_voice = engineer_voice
        self.laps_dir = Path(laps_dir) if laps_dir else laps_root()
        self.recorder = LapRecorder()   # used only on the legacy inline path

        # High-fidelity acquisition: a background thread reads + records at a
        # fixed rate, decoupled from this engine's tick rate. ``feed`` may be
        # injected (tests drive it manually); ``acquire_hz`` makes the engine
        # own one and run it. With neither, tick() reads+records inline (legacy).
        if feed is not None:
            self._feed: TelemetryFeed | None = feed
            self._owns_feed = False
        elif acquire_hz:
            self._feed = TelemetryFeed(self.reader, hz=acquire_hz, laps_dir=laps_dir)
            self._feed.start()
            self._owns_feed = True
        else:
            self._feed = None
            self._owns_feed = False
        self.analyzer = CoachAnalyzer(num_segments=num_segments)
        self.events = EventDetector()
        self.balance = BalanceDetector()
        self.braking = BrakingDetector()
        self.gears = GearDetector()
        self.fuel = FuelEngineer()
        self.advisor = SetupAdvisor()
        self.pressure = PressureAdvisor()
        self.tyretemp = TyreTempAdvisor()
        self.pitcall = PitCall()
        # Watches the dials so an "al volo" change can finish by being *done*
        # rather than by being clicked on a web page (see coaching/atwheel.py).
        self.wheelwatch = WheelWatch()
        self.scheduler = CueScheduler()

        self._comparator: LapComparator | None = None
        self._reference: Reference | None = None
        self._corners: list[Corner] = []
        self._key: tuple[str, str] = ("", "")
        self.saved_laps = 0
        self.history: list[str] = []
        # Out-lap tracking, mirroring LapRecorder's rule: a lap is "flying" only
        # once we've watched it open at the start/finish line. Kept here rather
        # than read off the recorder because that one lives on the feed thread.
        self._line = StartLineWatcher()
        self._flying_lap = False
        # Today's conditions, for the reference election. Read together when the
        # car or track changes, because they answer one question between them:
        # how much grip the track is giving *today*.
        self._road_temp: float | None = None
        self._grip: float | None = None
        self._compound: str | None = None
        # Whether to retire the braking countdown at mastered corners.
        from .config import load_config
        self._wean = load_config().overlay.wean

        # Race engineer: rebuilt per car/track; fed a per-lap diagnosis (LapStats)
        # at each completed lap, surfaces its latest decision in the payload.
        self._engineer: RaceEngineer | None = None
        self._engineer_decision = None
        # Signature of the last proposal spoken aloud, so a proposal that the
        # engine re-emits every lap (until the driver applies it) is announced
        # once, not on a loop. Reset when the engineer is rebuilt.
        self._engineer_spoken_sig: tuple | None = None
        # …and the proposal the driver has already written at the box, so the pit
        # calls go quiet for it (see _garage_change_pending).
        self._engineer_done_sig: tuple | None = None
        # …and the "al volo" proposal the dial watch is currently armed on.
        self._armed_sig: tuple | None = None

        # Focus/Lesson coach: the driver's twin of the engineer. Fed a per-lap
        # debrief (vs the reference), it picks one recurring weakness at a time and
        # coaches it. Rebuilt per car/track; needs a reference to produce debriefs.
        self._focus: FocusCoach | None = None
        self._focus_key: tuple[str, str] | None = None
        self._focus_report: FocusReport | None = None

        # Commands from other threads (e.g. the server's POST /engineer/applied,
        # which runs on the asyncio loop while tick() runs in an executor) are
        # queued here and drained on the tick thread — never applied inline — so
        # they can't race _observe_lap, which also mutates the engineer.
        self._cmd_lock = threading.Lock()
        self._applied_pending = False

    def _rebuild_reference(self, car: str, track: str) -> None:
        # Today's track temperature decides which past lap is a fair benchmark:
        # a personal best set on a rubbered-in evening track is the wrong target
        # for a cold morning, and every tenth in the debrief would be weather.
        self._reference = _load_reference(car, track, self.laps_dir,
                                          self._road_temp, self._grip,
                                          self._compound)
        self._comparator = LapComparator(self._reference) if self._reference else None
        corners = detect_corners(self._reference.lap.samples) if self._reference else []
        self._corners = corners
        self.analyzer.set_corners(corners)
        self.analyzer.reset()
        self.advisor.reset()
        self.pressure.reset()
        self.tyretemp.reset()
        self.fuel.reset()
        self.scheduler.reset()

    def acquisition_hz(self) -> float | None:
        """Measured acquisition rate when a background feed is running, else None."""
        return self._feed.measured_hz if self._feed is not None else None

    def _observe_lap(self, lap: Lap) -> None:
        """Diagnose a completed lap: feed the engineer (setup) and the Focus
        coach (driving). Both run on the reference that was the target *during*
        this lap — the rebuild to chase a new best happens after, in tick()."""
        if self._engineer is not None:
            stats = build_lap_stats(lap, self._corners or None)
            self._engineer_decision = self._engineer.observe(stats)
            self._announce_engineer(self._engineer_decision)
            self._log_engineer_outcome(lap, self._engineer_decision)

        # The Focus coach needs a reference to know where time was lost.
        if self._focus is not None and self._reference is not None and self._corners:
            debrief = build_lap_debrief(lap, self._reference, self._corners)
            stable = lap.valid and lap.clean is not False
            before = (frozenset(self._focus.mastered), frozenset(self._focus.parked))
            self._focus_report = self._focus.observe(debrief, stable=stable)
            after = (frozenset(self._focus.mastered), frozenset(self._focus.parked))
            if after != before:
                self._save_focus_state()   # a corner just changed status; persist
            self._update_wean()

    def _load_focus_state(self, car: str, track: str) -> tuple[set[int], set[int]]:
        """Last session's mastered/parked corners for this car+track, or empty.

        Best-effort: a missing or locked catalog just means "start fresh", never
        an error that stops coaching.
        """
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                return cat.load_focus_state(car, track)
        except Exception:
            return set(), set()

    def _save_focus_state(self) -> None:
        if self._focus is None or self._focus_key is None:
            return
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            car, track = self._focus_key
            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                cat.save_focus_state(car, track,
                                     self._focus.mastered, self._focus.parked)
        except Exception:
            pass   # persistence is a convenience; never let it break a lap

    def _watch_at_wheel(self, snap: TelemetrySnapshot) -> None:
        """Close the loop on an "al volo" proposal by watching the dial move.

        Without this an ``AV`` change could never be marked applied: the only
        caller of ``mark_applied`` was the setup-file writer, which exists only
        for ``BOX`` changes. So the engineer re-proposed the same click every
        lap and its phase never closed — two phases out of five on the GT3
        profile. See coaching/atwheel.py for why the answer is the car and not
        a button.
        """
        d = self._engineer_decision
        sig = _decision_sig(d)
        if (self._engineer is None or d is None or d.change is None
                or d.change.tag != "AV" or sig == self._engineer_done_sig):
            self.wheelwatch.disarm()
            self._armed_sig = None
            return
        if sig != self._armed_sig:
            self._armed_sig = sig
            atom = d.change.changes[0] if d.change.changes else None
            if atom is not None:
                self.wheelwatch.arm(atom.param, atom.delta_clicks, snap)
        if self.wheelwatch.update(snap):
            self._engineer.mark_applied()
            self._engineer_done_sig = sig

    def _garage_change_pending(self) -> bool:
        """Is there a setup change waiting that can only be made in the garage?

        Only ``BOX`` changes count. Something the driver can dial at the wheel is
        not a reason to give up a lap, and the engineer already separates the two
        — so this reads its answer rather than inventing a second rule.
        """
        d = self._engineer_decision
        if d is None or d.change is None or d.change.tag != "BOX":
            return False
        return _decision_sig(d) != self._engineer_done_sig

    def _load_pit_entry(self, track: str) -> list[float]:
        """This track's measured pit-entry positions; empty if never measured.

        Best-effort like the Focus memory next to it: no catalog means no
        approach call, never a failure.
        """
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                return cat.load_pit_entry(track)
        except Exception:
            return []

    def _save_pit_entry(self, track: str) -> None:
        try:
            from .recording.catalog import LapCatalog
            from .recording.storage import _catalog_path

            with LapCatalog(_catalog_path(Path(self.laps_dir))) as cat:
                cat.save_pit_entry(track, self.pitcall.samples())
        except Exception:
            pass    # a convenience memory; never let it break a lap
        finally:
            # Cleared either way: a catalog we can't write must not make every
            # subsequent frame retry the write.
            self.pitcall.mark_entry_saved()

    def _update_wean(self) -> None:
        """Retire the braking countdown at corners the Focus coach has cleared.

        Reuses the coach's own "mastered" set rather than inventing a second
        notion of "you've got this corner", so the crutch retires exactly where
        the lesson plan says the weakness is gone. Guarded by config so a driver
        who wants every braking board forever can keep them.
        """
        if self._comparator is None:
            return
        if not (self._wean and self._focus is not None):
            self._comparator.set_muted_spans([])
            return
        spans = [(c.entry_pos, c.exit_pos) for c in self._corners
                 if c.index in self._focus.mastered]
        self._comparator.set_muted_spans(spans)

    def _announce_engineer(self, decision) -> None:
        """Speak a brief alert when the engineer wants a setup change.

        Fires on any decision that carries a change to write — a new PROPOSE or a
        REVERTED (restore). Only proposals are spoken (COLLECT / EVALUATING /
        ACCEPTED / PHASE_DONE / DONE carry no change), and each distinct proposal
        is announced once: the engine re-emits the same PROPOSE every lap until the
        driver applies it, but :attr:`_engineer_spoken_sig` suppresses the repeat.
        The detailed parameter + click count stays on the Engineer page; the voice
        gives just the headline so it doesn't step on live driving cues."""
        if (not self.engineer_voice or self.voice is None
                or decision is None or decision.change is None):
            return
        rationale = decision.change.rationale or ""
        sig = (decision.kind.value, rationale)
        if sig == self._engineer_spoken_sig:
            return
        self._engineer_spoken_sig = sig
        lang = current_language()
        # Medium-confidence proposals are voiced tentatively; a high-confidence
        # proposal or a revert (confidence "") gets the firm wording.
        tone = "tentative" if decision.confidence == "medium" else "firm"
        by_tag = _ENG_VOICE_PREFIX[tone]
        prefixes = by_tag.get(decision.change.tag) or by_tag["BOX"]
        prefix = prefixes.get(lang) or prefixes["en"]
        self.voice.say(f"{prefix} {_voice_clean(rationale)}")

    def _log_engineer_outcome(self, lap, decision) -> None:
        """Write a finished test to the engineer's ledger.

        The one thing this app can prove that a setup generator can't is that a
        change was measured after it was made. That verdict used to exist for as
        long as the message was on screen; now it is kept, and after enough laps
        it answers the only question worth asking a setup tool — how many of its
        changes actually worked. Best-effort: a ledger that can't be written must
        never cost the driver a setup change (see engineer/ledger.py).
        """
        out = getattr(decision, "outcome", None)
        if out is None:
            return
        from datetime import datetime, timezone

        from .engineer.ledger import Record, append
        change = decision.change
        # On a REVERTED the decision carries the *reversal*, so its clicks are
        # the opposite of the change that was actually tested.
        atom = change.changes[0] if (change and change.changes) else None
        delta = -atom.delta_clicks if (atom and not out.kept) else (
            atom.delta_clicks if atom else 0)
        try:
            append(Record(
                when_utc=datetime.now(timezone.utc).isoformat(),
                car=getattr(lap, "car_model", "") or "",
                track=getattr(lap, "track", "") or "",
                car_class=classify(getattr(lap, "car_model", "") or "").value,
                phase=change.phase_label if change else "",
                symptom=str(out.prediction.symptom) if out.prediction.symptom else "",
                param=atom.param if atom else "",
                slot=atom.slot if atom else None,
                delta_clicks=delta,
                remedy_rank=out.remedy_rank,
                kept=out.kept,
                laps=out.laps,
                score_before=out.prediction.score_now,
                score_after=out.score_after,
                time_before_ms=out.time_before_ms,
                time_after_ms=out.time_after_ms,
                fuel_before_l=out.fuel_before_l,
                fuel_after_l=out.fuel_after_l,
                time_confounded=out.time_confounded,
                side_effects={str(sym): d for sym, d in out.side_effects},
            ))
        except Exception:  # noqa: BLE001 - evidence for us, never a live failure
            pass

    def _engineer_block(self) -> dict | None:
        """The latest engineer decision, in the shape the setup UI consumes."""
        d = self._engineer_decision
        if d is None:
            return None
        sym = d.change.symptom if d.change else None
        corners = self._engineer.corners_for(sym) if self._engineer else []
        # Current phase (key + localized label) so the UI can tell the driver what
        # THIS phase wants — "phase X done → moving to Y" alone doesn't say what to
        # do next. After a PHASE_DONE the engine has already advanced, so this is
        # the phase now in progress. None once the setup is complete.
        from .engineer.profiles._common import tr
        ph = self._engineer.phase if self._engineer else None
        phase = {"key": ph.key, "label": tr(ph.label)} if ph else None
        return {
            "kind": d.kind.value,
            "message": d.message,
            "phase": phase,
            "change": d.change.as_setup_payload() if d.change else None,
            "rationale": d.change.rationale if d.change else None,
            "tag": d.change.tag if d.change else None,
            # Has this exact proposal already been written to the setup file?
            # The engineer keeps re-emitting it until the next completed lap, so
            # without this the page can't tell "still to do" from "done, go load
            # it" — and both the pit calls and the on-screen reminder need to.
            "applied": _decision_sig(d) == self._engineer_done_sig,
            # Is the engine watching the dial for this one? Answered here rather
            # than worked out again in the browser, so there is one place that
            # knows which parameters are readable on which game. False on an AV
            # proposal means the page has to offer a "done" button, or the change
            # can never be finished (AC reports every aid level as -1).
            "watched": self.wheelwatch.armed,
            "confidence": d.confidence,
            # 1-based corner labels the proposal is anchored to ("Corners 7, 9").
            "corners": [i + 1 for i in corners],
            # The bar the change will be judged against, so the driver reads it
            # *before* the re-test laps instead of only hearing the verdict.
            "prediction": (None if d.prediction is None else {
                "text": d.prediction.text,
                "score_now": d.prediction.score_now,
                "score_below": d.prediction.score_below,
                "time_band_ms": round(d.prediction.time_band_ms, 1),
            }),
            # …and what actually happened, on the lap the verdict lands.
            "outcome": (None if d.outcome is None else {
                "kept": d.outcome.kept,
                "laps": d.outcome.laps,
                "score_before": d.outcome.prediction.score_now,
                "score_after": d.outcome.score_after,
                "time_before_ms": d.outcome.time_before_ms,
                "time_after_ms": d.outcome.time_after_ms,
                "fuel_before_l": d.outcome.fuel_before_l,
                "fuel_after_l": d.outcome.fuel_after_l,
                "time_confounded": d.outcome.time_confounded,
                "side_effects": [{"symptom": str(s), "delta": v}
                                 for s, v in d.outcome.side_effects],
            }),
        }

    def _focus_block(self) -> dict | None:
        """The latest Focus/Lesson report, in the shape a frontend consumes."""
        r = self._focus_report
        if r is None:
            return None
        f = r.focus
        return {
            "kind": r.kind.value,
            "message": r.message,
            "drill": r.drill,
            "progress_ms": round(r.progress_ms, 1),
            "focus": None if f is None else {
                "corner_index": f.corner_index,
                "name": f.name,
                "theme": f.theme,
                "category": f.category.value,
                "baseline_ms": round(f.baseline_ms, 1),
            },
        }

    def mark_setup_applied(self) -> None:
        """Request that the engineer mark its proposal applied. Thread-safe: only
        sets a flag here; the actual mutation runs on the tick thread (drained in
        :meth:`tick`), so it can't race :meth:`_observe_lap`, which also touches
        the engineer."""
        with self._cmd_lock:
            self._applied_pending = True

    def tick(self, now: float) -> EngineState:
        if self._feed is not None:
            # Acquisition + recording happen on the feed thread; here we just
            # read the latest frame and learn which laps it saved.
            snap = self._feed.latest()
            saved = self._feed.drain_saved()
        else:
            snap = self.reader.read()
            saved = []

        if snap.connected and (snap.car_model, snap.track) != self._key:
            self._key = (snap.car_model, snap.track)
            self._road_temp = snap.road_temp or None
            self._grip = snap.surface_grip or None
            self._compound = snap.tyre_compound or None
            self._rebuild_reference(snap.car_model, snap.track)
            # Retune the class-dependent live thresholds (wheelspin, trail-brake
            # coaching) for this car.
            car_class = classify(snap.car_model)
            self.events.set_car_class(car_class)
            self.braking.set_car_class(car_class)
            self.balance.set_car_class(car_class)
            # …e le due finestre gomme, che fuori dalla GT3 non le conosciamo e
            # quindi lì si tace (vedi il blocco in coaching/tuning.py).
            self.pressure.set_car_class(car_class)
            self.tyretemp.set_car_class(car_class)
            # A new car/track is a new setup problem: start a fresh engineer.
            self._engineer = engineer_for(snap.car_model, snap.track)
            self._engineer_decision = None
            self._engineer_spoken_sig = None
            self._engineer_done_sig = None
            self._armed_sig = None
            self.wheelwatch.disarm()
            # The pit calls: fresh latches, and this track's measured pit entry
            # (see coaching/pitcall.py — it's learned, so a track never visited
            # simply has no approach call until the first time you come in).
            self.pitcall.reset()
            for pos in self._load_pit_entry(snap.track):
                self.pitcall.note_pit_entry(pos)
            self.pitcall.mark_entry_saved()
            # …and the lesson plan, restored from last session's memory for this
            # car+track so a mastered corner stays mastered across restarts.
            self._focus_key = (snap.car_model, snap.track)
            mastered, parked = self._load_focus_state(snap.car_model, snap.track)
            self._focus = FocusCoach(mastered=mastered, parked=parked)
            self._focus_report = None

        # Drain cross-thread commands on this (the engine's) thread.
        with self._cmd_lock:
            apply_setup = self._applied_pending
            self._applied_pending = False
        if apply_setup and self._engineer is not None:
            self._engineer.mark_applied()
            # The change has been written: stop calling the driver in for it.
            # Without this the proposal — which the engineer keeps re-emitting
            # until the next completed lap — would call them back to the box on
            # the out-lap they just left it on.
            self._engineer_done_sig = _decision_sig(self._engineer_decision)

        if self._feed is None:
            lap = self.recorder.update(snap)
            if lap is not None and lap.valid:
                save_lap(lap, self.laps_dir)
                saved = [lap]

        for lap in saved:
            self.saved_laps += 1
            # Use the LAP's own car/track, not snap's: between completing the lap
            # and this tick the game may have disconnected (snap blank) or switched
            # car/track, which would diagnose the lap against the wrong reference.
            if lap.car_model and (lap.car_model, lap.track) != self._key:
                continue                                            # not this session
            self._observe_lap(lap)
            self._rebuild_reference(lap.car_model, lap.track)        # chase the new best

        self._watch_at_wheel(snap)

        delta = self._comparator.compare(snap) if self._comparator else None
        # On an abnormal lap (out of the pits, no comparison, or delta blown out)
        # gate everything except acute safety cues — detectors still run so their
        # state advances, we just don't speak advice that isn't worth hearing.
        self._track_flying_lap(snap)
        quiet = self._quiet_reason(snap, delta)

        # "No reference yet" is NOT an abnormal lap — it's a normal lap we can't
        # put a stopwatch on. Lumping it in with pit/out-lap/off-pace silenced
        # every detector that never needed a reference in the first place
        # (under/oversteer, coasting, trail braking, gears, tyres, pressures, all
        # of them absolute by construction), so the first session on a new car or
        # track produced lock-ups, fuel and nothing else. The analyzer is the only
        # consumer that needs the delta, and with no delta it emits nothing
        # anyway, so it needs no gate of its own here.
        unrepresentative = bool(quiet) and quiet != "no_reference"

        def _submit(cues: list[Cue]) -> None:
            kept = cues if not unrepresentative else [
                c for c in cues if c.category in _SAFETY_CATEGORIES]
            self.scheduler.submit_all(kept, now)

        # Corner advice (needs a reference) + acute events (don't) + the aid
        # advisor, which aggregates those same events into setup-knob suggestions.
        event_cues = self.events.update(snap, now)
        balance_cues = self.balance.update(snap, now)
        # Let the analyzer hold feed-forward advice the live data contradicts in
        # the same zone (e.g. don't say "carry more speed" where you understeered).
        self.analyzer.note_faults(event_cues + balance_cues)
        _submit(self.analyzer.update(snap, delta))
        _submit(event_cues)
        _submit(balance_cues)
        _submit(self.braking.update(snap, now))
        _submit(self.gears.update(snap, now))
        _submit(self.advisor.update(snap, event_cues, now))
        _submit(self.pressure.update(snap, now))
        _submit(self.tyretemp.update(snap, now))
        _submit(self.fuel.update(snap, now))
        self.pitcall.set_pending(self._garage_change_pending())
        _submit(self.pitcall.update(snap, now))
        if self.pitcall.entry_dirty and snap.track:
            self._save_pit_entry(snap.track)
        spoken = self.scheduler.poll(now)
        if spoken is not None and spoken.category is CueCategory.PIT_BRIEFING:
            # Latch on the *spoken*, not on the emitted. The scheduler is allowed
            # to drop a cue, and this one used to be emitted once in the life of
            # a setup change — so a drop left the driver sitting in the garage
            # with nothing said and no second chance.
            self.pitcall.mark_briefed()
        if spoken is not None:
            # Cues are authored in Italian (so the neural WAVs match); render them
            # in the active language for both the voice and the on-screen text.
            spoken.message = cue_text(spoken.message)
            if self.voice is not None:
                self.voice.say(spoken.message)
            self.history.append(spoken.message)
            del self.history[:-20]

        return EngineState(
            snapshot=snap,
            delta=delta,
            spoken=spoken,
            saved_laps=self.saved_laps,
            reference_ms=self._reference.lap_time_ms if self._reference else 0,
            history=list(self.history),
            engineer=self._engineer_block(),
            focus=self._focus_block(),
            quiet=quiet,
            # Only on a lap that actually started at the line: on ACC the flag is
            # 0 for the whole out-lap too, and answering "invalidated" there would
            # be technically true and useless — the out-lap has its own message.
            lap_invalid=self._flying_lap and snap.lap_valid is False,
        )

    def _track_flying_lap(self, s: TelemetrySnapshot) -> None:
        """Am I on a lap that started at the line, or still on the way out?

        Exactly the recorder's rule, via the shared :func:`crossed_start_line`.
        This used to trust the lap counter alone, with a comment claiming that was
        the one signal holding on both titles — measurement says otherwise, and on
        ACC the counter skips the out-lap crossing, so the coach stayed silent
        through the whole first flying lap after every pit exit. The driver saw
        "out lap" on the overlay while setting a genuine time.
        """
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit or s.in_pit_lane:
            self._line.reset()
            self._flying_lap = False
            return
        if self._line.crossed(s.lap_position, s.completed_laps):
            # Set on the crossing frame itself, not the next tick: the tyre-temp
            # and pressure advisors emit exactly here, and they're the one thing
            # an out-lap is good for.
            self._flying_lap = True

    def _quiet_reason(self, s: TelemetrySnapshot, delta: DeltaState | None) -> str:
        """Why the coach is holding back this tick, "" if it isn't.

        Ordered most-specific first, because they overlap: an out-lap also has no
        usable delta, and saying "no reference yet" there would be a lie.
        """
        if s.in_pit or s.in_pit_lane:
            return "pit"
        if not self._flying_lap:
            return "out_lap"
        if delta is None:
            return "no_reference"
        if abs(delta.delta_ms) > _GATE_DELTA_MS:
            return "off_pace"
        return ""

    def close(self) -> None:
        if self.voice is not None:
            self.voice.close()
        # Stop the feed before closing the reader it polls.
        if self._feed is not None and self._owns_feed:
            self._feed.stop()
        self.reader.close()
