"""TelemetryFeed: fixed-rate background acquisition, decoupled from the UI loop.

The per-frame work is exercised synchronously via ``_pump`` so the tests are
deterministic (no sleeping on a real thread); one light smoke test covers the
thread lifecycle.
"""
from accoach.engine import CoachEngine
from accoach.recording.storage import list_lap_files
from accoach.telemetry.feed import TelemetryFeed
from accoach.telemetry.snapshot import TelemetrySnapshot

import synth


class _ScriptedReader:
    """Returns the given snapshots one per read(), then disconnected."""

    def __init__(self, frames):
        self._frames = list(frames)
        self._i = 0
        self.closed = False

    def read(self):
        if self._i < len(self._frames):
            f = self._frames[self._i]
            self._i += 1
            return f
        return TelemetrySnapshot.disconnected()

    def close(self):
        self.closed = True


class _BoomReader:
    def read(self):
        raise RuntimeError("boom")

    def close(self):
        pass


def _full_lap_frames():
    """Frames that drive the recorder through a full lap (counter 0->1->2)."""
    frames = []
    for completed in (0, 1, 2):
        for i in range(30):
            frames.append(synth.snap(
                pos=i / 30, completed_laps=completed,
                current_lap_ms=i * 100, last_lap_ms=89000, speed_kmh=150.0,
            ))
    return frames


def test_latest_starts_disconnected(tmp_path):
    feed = TelemetryFeed(_ScriptedReader([]), hz=60, laps_dir=tmp_path)
    assert feed.latest().connected is False


def test_pump_updates_latest(tmp_path):
    feed = TelemetryFeed(_ScriptedReader([synth.snap(pos=0.5)]), laps_dir=tmp_path)
    feed._pump()
    assert feed.latest().connected is True
    assert feed.latest().car_model == "ferrari_488_gt3"


def test_pump_records_and_saves_a_full_lap(tmp_path):
    feed = TelemetryFeed(_ScriptedReader(_full_lap_frames()), laps_dir=tmp_path)
    for _ in range(90):
        feed._pump()
    saved = feed.drain_saved()
    assert saved and saved[0].car_model == "ferrari_488_gt3"
    assert saved[0].track == "monza" and saved[0].valid
    assert feed.drain_saved() == []          # draining clears it
    assert len(list_lap_files(tmp_path)) >= 1  # a lap file was written off-thread


def test_pump_swallows_reader_errors(tmp_path):
    feed = TelemetryFeed(_BoomReader(), laps_dir=tmp_path)
    feed._pump()                              # must not raise
    assert feed.latest().connected is False


def test_thread_start_is_idempotent_and_stops(tmp_path):
    feed = TelemetryFeed(_ScriptedReader([]), hz=120, laps_dir=tmp_path)
    feed.start()
    feed.start()                              # second start is a no-op
    feed.stop()
    assert feed._thread is None


def test_engine_consumes_injected_feed(tmp_path):
    feed = TelemetryFeed(_ScriptedReader(_full_lap_frames()), laps_dir=tmp_path)
    for _ in range(90):                       # record + save a lap up front
        feed._pump()
    eng = CoachEngine(reader=_ScriptedReader([]), feed=feed, laps_dir=tmp_path)
    state = eng.tick(0.0)
    # tick read the latest frame from the feed and counted the saved lap,
    # without calling its own reader or recorder.
    assert state.snapshot.car_model == "ferrari_488_gt3"
    assert eng.saved_laps == 1
    eng.close()
