"""End-to-end: CoachEngine drives all detectors with a stub reader."""
from dataclasses import replace

from accoach.engine import CoachEngine
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="ferrari_488_gt3", track="monza",
    max_rpm=8000, rpm=6000, fuel=30.0,
)


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


def _frame(pos, **kw):
    return replace(_LIVE, lap_position=pos, **kw)


def _build_frames():
    frames = []
    for i in range(60):
        pos = i / 60
        if 0.20 <= pos < 0.26:
            frames.append(_frame(pos, steer_angle=0.25, yaw_rate=0.05, speed_kmh=120))
        elif 0.40 <= pos < 0.45:
            frames.append(_frame(pos, throttle=0.0, brake=0.0, speed_kmh=150))
        elif 0.60 <= pos < 0.63:
            frames.append(_frame(pos, brake=0.9, abs_active=0.6, speed_kmh=110))
        else:
            frames.append(_frame(pos, throttle=0.8, speed_kmh=180))
    for i in range(60):
        pos = i / 60
        frames.append(_frame(pos, throttle=0.8, speed_kmh=180, fuel=27.0,
                             tyre_core_temp=(99.0,) * 4,
                             tyre_pressure=(29.5, 29.5, 29.5, 29.5)))
    return frames


def test_engine_tick_runs_clean_and_speaks():
    frames = _build_frames()
    eng = CoachEngine(reader=_StubReader(frames), voice=None)
    spoken = []
    now = 0.0
    for _ in range(len(frames) + 5):
        st = eng.tick(now)          # must never raise
        if st.spoken is not None:
            spoken.append(st.spoken)
        now += 0.05
    eng.close()
    # The chain wired up and produced at least one coaching cue.
    assert spoken, "engine produced no cues over two synthetic laps"


def test_disconnected_tick_is_safe():
    eng = CoachEngine(reader=_StubReader([TelemetrySnapshot.disconnected()]), voice=None)
    st = eng.tick(0.0)
    assert st.spoken is None and not st.snapshot.connected
    eng.close()
