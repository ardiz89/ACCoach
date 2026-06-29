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
from .coaching.cue import CueTier
from .coaching.debrief import build_lap_debrief
from .coaching.diagnosis import build_lap_stats
from .coaching.focus import FocusCoach, FocusReport
from .comparison import DeltaState, LapComparator, Reference
from .engineer import RaceEngineer, engineer_for
from .recording import DEFAULT_LAPS_DIR, Lap, LapRecorder, find_reference_lap, save_lap
from .telemetry import SharedMemoryReader, TelemetrySnapshot
from .telemetry.feed import TelemetryFeed
from .track import Corner, detect_corners

# When you're not on a representative flying lap — delta has ballooned because
# you're crawling, recovering from an off, or parked — only acute safety cues
# (lock-up, wheelspin, slides, fuel) are worth speaking. Technique and setup
# advice on a throw-away lap is noise (live validation 2026-06-26: the coach
# machine-gunned coasting/trail cues and even praised a +12 s disaster lap).
_GATE_DELTA_MS = 3000.0


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


def _load_reference(car: str, track: str, laps_dir: Path | str) -> Reference | None:
    lap = find_reference_lap(car, track, laps_dir)
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
        laps_dir: Path | str = DEFAULT_LAPS_DIR,
        feed: TelemetryFeed | None = None,
        acquire_hz: float | None = None,
    ) -> None:
        self.reader = reader if reader is not None else SharedMemoryReader()
        self.voice = voice
        self.laps_dir = laps_dir
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
        self.scheduler = CueScheduler()

        self._comparator: LapComparator | None = None
        self._reference: Reference | None = None
        self._corners: list[Corner] = []
        self._key: tuple[str, str] = ("", "")
        self.saved_laps = 0
        self.history: list[str] = []

        # Race engineer: rebuilt per car/track; fed a per-lap diagnosis (LapStats)
        # at each completed lap, surfaces its latest decision in the payload.
        self._engineer: RaceEngineer | None = None
        self._engineer_decision = None

        # Focus/Lesson coach: the driver's twin of the engineer. Fed a per-lap
        # debrief (vs the reference), it picks one recurring weakness at a time and
        # coaches it. Rebuilt per car/track; needs a reference to produce debriefs.
        self._focus: FocusCoach | None = None
        self._focus_report: FocusReport | None = None

        # Commands from other threads (e.g. the server's POST /engineer/applied,
        # which runs on the asyncio loop while tick() runs in an executor) are
        # queued here and drained on the tick thread — never applied inline — so
        # they can't race _observe_lap, which also mutates the engineer.
        self._cmd_lock = threading.Lock()
        self._applied_pending = False

    def _rebuild_reference(self, car: str, track: str) -> None:
        self._reference = _load_reference(car, track, self.laps_dir)
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

        # The Focus coach needs a reference to know where time was lost.
        if self._focus is not None and self._reference is not None and self._corners:
            debrief = build_lap_debrief(lap, self._reference, self._corners)
            stable = lap.valid and lap.clean is not False
            self._focus_report = self._focus.observe(debrief, stable=stable)

    def _engineer_block(self) -> dict | None:
        """The latest engineer decision, in the shape the setup UI consumes."""
        d = self._engineer_decision
        if d is None:
            return None
        return {
            "kind": d.kind.value,
            "message": d.message,
            "change": d.change.as_setup_payload() if d.change else None,
            "rationale": d.change.rationale if d.change else None,
            "tag": d.change.tag if d.change else None,
            "confidence": d.confidence,
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
            self._rebuild_reference(snap.car_model, snap.track)
            # A new car/track is a new setup problem: start a fresh engineer.
            self._engineer = engineer_for(snap.car_model, snap.track)
            self._engineer_decision = None
            # …and a fresh lesson plan for the driver.
            self._focus = FocusCoach()
            self._focus_report = None

        # Drain cross-thread commands on this (the engine's) thread.
        with self._cmd_lock:
            apply_setup = self._applied_pending
            self._applied_pending = False
        if apply_setup and self._engineer is not None:
            self._engineer.mark_applied()

        if self._feed is None:
            lap = self.recorder.update(snap)
            if lap is not None and lap.valid:
                save_lap(lap, self.laps_dir)
                saved = [lap]

        for lap in saved:
            self.saved_laps += 1
            self._observe_lap(lap)
            self._rebuild_reference(snap.car_model, snap.track)      # chase the new best

        delta = self._comparator.compare(snap) if self._comparator else None
        # On an abnormal lap (no comparison, or delta blown out) gate everything
        # except acute safety cues — detectors still run so their state advances,
        # we just don't speak technique/setup advice that isn't worth hearing.
        flying = delta is not None and abs(delta.delta_ms) <= _GATE_DELTA_MS

        def _submit(cues: list[Cue]) -> None:
            kept = cues if flying else [c for c in cues if c.tier == CueTier.ACUTE]
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
        spoken = self.scheduler.poll(now)
        if spoken is not None:
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
        )

    def close(self) -> None:
        if self.voice is not None:
            self.voice.close()
        # Stop the feed before closing the reader it polls.
        if self._feed is not None and self._owns_feed:
            self._feed.stop()
        self.reader.close()
