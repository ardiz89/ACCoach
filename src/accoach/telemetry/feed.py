"""Fixed-rate background telemetry acquisition, decoupled from the UI loop.

Why this exists
---------------
Until now telemetry was read inside the UI/engine tick (15–20 Hz, and *variable*:
the websocket server ran 15 Hz, the live overlay 20 Hz). So the same lap recorded
at a different fidelity depending on which front-end drove it, and a braking point
was only located to ±1 tick (~50–66 ms ≈ 10 m at speed).

:class:`TelemetryFeed` runs a dedicated thread that polls the shared memory at a
*constant* rate (default 60 Hz) and feeds **every** frame to the lap recorder, so
a recorded lap always has the same high fidelity regardless of how fast the
overlay/server happens to render. The UI just calls :meth:`latest` at its own
pace. Saving (file + catalog) also happens on this thread, off the render loop,
so crossing the start/finish line no longer hitches the overlay.

Threading contract
------------------
Only this thread ever touches the reader and the recorder. The engine (tick
thread) reads :meth:`latest` (a single atomic reference swap) and drains
:meth:`drain_saved` (lock-protected), and does all coaching-state mutation
itself — so coaching stays single-threaded on the tick thread.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from ..logging_setup import get_logger
from ..recording import DEFAULT_LAPS_DIR, LapRecorder, save_lap
from ..recording.lap import Lap
from .reader import SharedMemoryReader
from .snapshot import TelemetrySnapshot

_log = get_logger("feed")


# Backstop: if the engine stops draining (a stuck tick), don't let saved laps —
# each holding a full sample list — pile up unbounded in RAM. Far above any normal
# backlog (tick drains every frame), so it only fires on a real stall.
_MAX_PENDING = 20


class TelemetryFeed:
    """Polls a reader at a fixed rate on its own thread and records laps."""

    def __init__(
        self,
        reader: SharedMemoryReader,
        hz: float = 60.0,
        laps_dir: Path | str = DEFAULT_LAPS_DIR,
    ) -> None:
        self._reader = reader
        self._interval = 1.0 / hz if hz > 0 else 1.0 / 60.0
        self._target_hz = hz if hz > 0 else 60.0
        self._laps_dir = laps_dir
        self._recorder = LapRecorder()

        self._latest: TelemetrySnapshot = TelemetrySnapshot.disconnected()
        self._saved: list[Lap] = []          # laps saved since the engine last drained
        self._lock = threading.Lock()

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._measured_hz = 0.0

    # --- consumed by the engine / UI (other threads) ---------------------

    def latest(self) -> TelemetrySnapshot:
        """The most recent snapshot. Atomic reference read; never blocks."""
        return self._latest

    def drain_saved(self) -> list[Lap]:
        """Return (and clear) the laps saved since the last call."""
        with self._lock:
            if not self._saved:
                return []
            out = self._saved
            self._saved = []
            return out

    @property
    def measured_hz(self) -> float:
        return self._measured_hz

    # --- the work, one frame; extracted so tests can drive it synchronously --

    def _pump(self) -> None:
        try:
            snap = self._reader.read()
        except Exception:
            _log.error("reader.read failed", exc_info=True)
            snap = TelemetrySnapshot.disconnected()
        self._latest = snap   # single attribute assignment is atomic under the GIL
        try:
            lap = self._recorder.update(snap)
            if lap is not None and lap.valid:
                save_lap(lap, self._laps_dir)
                with self._lock:
                    self._saved.append(lap)
                    if len(self._saved) > _MAX_PENDING:
                        drop = len(self._saved) - _MAX_PENDING
                        del self._saved[:drop]
                        _log.warning(
                            "feed: dropped %d undrained lap(s) — is the engine ticking?",
                            drop)
        except Exception:
            _log.error("recording failed", exc_info=True)

    # --- thread lifecycle -------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="telemetry-feed", daemon=True
        )
        self._thread.start()
        _log.info("telemetry feed started at %.0f Hz", self._target_hz)

    def _run(self) -> None:
        next_t = time.perf_counter()
        win_start = next_t
        win_frames = 0
        low_warned = False
        low_since = next_t
        while not self._stop.is_set():
            self._pump()

            win_frames += 1
            now = time.perf_counter()
            if now - win_start >= 1.0:
                self._measured_hz = win_frames / (now - win_start)
                win_frames = 0
                win_start = now
                # Report the START and the END of every slow stretch. Warning only
                # on the way down turned out to be worse than not warning at all:
                # the log kept one line per session naming the worst single second
                # ("13 Hz"), never said it recovered, and that line got read as the
                # steady state twice — including in a written-up finding. The laps
                # themselves said ~60 Hz all along.
                if self._measured_hz < 0.7 * self._target_hz:
                    if not low_warned:
                        _log.warning(
                            "acquisition under target: %.0f Hz (want %.0f)",
                            self._measured_hz, self._target_hz,
                        )
                        low_warned = True
                        low_since = now
                elif low_warned:
                    _log.info(
                        "acquisition back to %.0f Hz after %.0f s",
                        self._measured_hz, now - low_since,
                    )
                    low_warned = False

            # Fixed-rate pacing with drift correction; interruptible by stop().
            next_t += self._interval
            delay = next_t - time.perf_counter()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = time.perf_counter()   # fell behind — resync, don't spiral

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        _log.info("telemetry feed stopped")
