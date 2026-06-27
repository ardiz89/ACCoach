"""CoachEngine: lap recording -> save -> reference rebuild, with a stub reader."""
from accoach.engine import CoachEngine
from accoach.recording.storage import list_lap_files
from accoach.telemetry.snapshot import TelemetrySnapshot

import synth


class _StubReader:
    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


def _lap_frames(completed, n=40, last_lap_ms=95000):
    """One lap's frames at a given completed-laps counter."""
    frames = []
    for i in range(n):
        pos = i / n
        spd, brake, thr, steer = synth._profile(pos)
        frames.append(synth.snap(
            pos=pos, completed_laps=completed, current_lap_ms=i * 100,
            last_lap_ms=last_lap_ms, speed_kmh=spd, throttle=thr,
            brake=brake, steer_angle=steer,
        ))
    return frames


def test_engine_saves_valid_lap_and_builds_reference(tmp_path):
    # 3 laps: counter 0 (partial), 1 (partial emitted, not saved), 2 (full -> saved).
    frames = _lap_frames(0) + _lap_frames(1) + _lap_frames(2) + _lap_frames(3)
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)

    final = None
    for _ in range(len(frames)):
        final = eng.tick(0.0)
    eng.close()

    assert eng.saved_laps >= 1, "a full lap should have been saved"
    assert len(list_lap_files(tmp_path)) >= 1
    assert final.reference_ms > 0, "reference should be built from the saved lap"


def test_disconnected_tick_is_safe(tmp_path):
    eng = CoachEngine(reader=_StubReader([TelemetrySnapshot.disconnected()]),
                      voice=None, laps_dir=tmp_path)
    st = eng.tick(0.0)
    assert st.spoken is None
    assert not st.snapshot.connected
    assert st.reference_ms == 0
    eng.close()
