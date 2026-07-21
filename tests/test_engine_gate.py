"""Fix A — engine gates non-acute cues when you're not on a flying lap.

Regression for the 2026-06-26 live finding: on a throw-away/parked lap (delta
blown out) the coach machine-gunned technique cues. Acute safety cues must still
get through; technique cues must be silenced.
"""
from accoach.comparison import Reference
from accoach.engine import CoachEngine, _GATE_DELTA_MS
from accoach.recording.storage import save_lap

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


def _engine_with_reference(tmp_path):
    save_lap(synth.build_lap(), tmp_path)          # reference for ferrari_488_gt3/monza
    ref = Reference(synth.build_lap())
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    return eng, ref


def _crossing():
    """Two frames that take the car over the start/finish line.

    The gate now also asks whether this lap *started* at the line — an out lap is
    never a representative lap — so a test that wants the flying-lap behaviour has
    to actually cross, the way a session does.
    """
    return [synth.snap(pos=0.9, completed_laps=0),
            synth.snap(pos=0.01, completed_laps=1)]


def _run(eng, frames):
    spoken = []
    now = 0.0
    for _ in range(len(frames)):
        st = eng.tick(now)
        if st.spoken is not None:
            spoken.append(st.spoken)
        now += 0.05
    return spoken


def test_technique_cue_suppressed_when_delta_blown_out(tmp_path):
    eng, _ = _engine_with_reference(tmp_path)
    # Coasting frames (both pedals off, at speed) but a huge delta = abnormal lap.
    huge = int(_GATE_DELTA_MS) + 500_000
    frames = [eng.reader._frames[0]]  # first tick builds the reference
    frames += [synth.snap(pos=0.5, current_lap_ms=huge, speed_kmh=150.0,
                          throttle=0.0, brake=0.0) for _ in range(25)]
    eng.reader._frames = frames
    spoken = _run(eng, frames)
    assert all(c.category.value != "coasting" for c in spoken), \
        "coasting (technique) must be gated on a blown-out lap"
    eng.close()


def test_acute_cue_passes_when_delta_blown_out(tmp_path):
    eng, _ = _engine_with_reference(tmp_path)
    huge = int(_GATE_DELTA_MS) + 500_000
    # A real lock-up: brake on, fronts locked. Acute -> must speak despite gate.
    frames = [synth.snap(pos=0.5)]
    frames += [synth.snap(pos=0.5, current_lap_ms=huge, speed_kmh=120.0,
                          brake=0.9, slip_ratio=(-0.4, -0.4, 0.0, 0.0))
               for _ in range(8)]
    eng.reader._frames = frames
    spoken = _run(eng, frames)
    assert any(c.category.value == "locked" for c in spoken), \
        "lock-up (acute) must still be spoken on a blown-out lap"
    eng.close()


def test_technique_cue_allowed_on_a_flying_lap(tmp_path):
    eng, ref = _engine_with_reference(tmp_path)
    # Same coasting, but delta ~0 (current time matches the reference) = flying.
    ontime = int(ref.time_at(0.5))
    frames = [synth.snap(pos=0.5)] + _crossing()
    frames += [synth.snap(pos=0.5, completed_laps=1, current_lap_ms=ontime,
                          speed_kmh=150.0, throttle=0.0, brake=0.0)
               for _ in range(25)]
    eng.reader._frames = frames
    spoken = _run(eng, frames)
    assert any(c.category.value == "coasting" for c in spoken), \
        "coasting should be coached normally on a representative lap"
    eng.close()


def test_technique_cue_suppressed_on_the_out_lap(tmp_path):
    """Same on-pace frames, but the car never crossed the line — it's an out lap.

    This is the hole the delta gate couldn't see: the band is two-sided, so on the
    way out the delta swings *through* it and the gate fell open mid-out-lap.
    """
    eng, ref = _engine_with_reference(tmp_path)
    ontime = int(ref.time_at(0.5))
    frames = [synth.snap(pos=0.5)]
    frames += [synth.snap(pos=0.5, current_lap_ms=ontime, speed_kmh=150.0,
                          throttle=0.0, brake=0.0) for _ in range(25)]
    eng.reader._frames = frames
    spoken = _run(eng, frames)
    assert all(c.category.value != "coasting" for c in spoken), \
        "technique advice on cold tyres and a full tank is exactly the noise"
    eng.close()
