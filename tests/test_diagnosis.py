"""Per-lap diagnosis (build_lap_stats) and the engine's live engineer block.

The synthetic laps inject a realistic yaw signal: the games report yaw_rate with
the OPPOSITE sign to steering (that's why balance.py uses _YAW_SIGN = -1), so a
neutral corner has raw yaw = -(ratio)*steer with ratio ~1.9. Lowering the ratio
below ~0.9 makes the car "push" (understeer); a same-sign raw yaw simulates the
countersteer of oversteer.
"""
from accoach.coaching.diagnosis import build_lap_stats
from accoach.engine import CoachEngine
from accoach.engineer import Balance
from accoach.telemetry.snapshot import TelemetrySnapshot

import synth


def _with_yaw(lap, *, ratio: float, same_sign: bool = False):
    """Set each sample's yaw_rate to model a given yaw/steer ratio.

    Default (same_sign=False) mimics the game convention (yaw opposite to steer),
    i.e. a clean corner; same_sign=True flips it to look like countersteer.
    """
    sign = 1.0 if same_sign else -1.0
    for s in lap.samples:
        s.yaw_rate = sign * ratio * s.steer_angle
    return lap


def test_understeer_lap_is_diagnosed():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=0.3)
    stats = build_lap_stats(lap)
    under = [sym for sym in stats.symptom_scores if sym.balance is Balance.UNDERSTEER]
    assert under                                       # the push is named
    assert max(stats.symptom_scores[s] for s in under) >= 0.30
    assert any(stats.symptom_corners[s] >= 1 for s in under)
    assert stats.stable is True                        # clean lap


def test_neutral_lap_has_no_understeer():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.9)
    stats = build_lap_stats(lap)
    under = [s for s in stats.symptom_scores if s.balance is Balance.UNDERSTEER]
    over = [s for s in stats.symptom_scores if s.balance is Balance.OVERSTEER]
    assert not under and not over                       # a neutral car: nothing flagged


def test_oversteer_lap_is_diagnosed():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.5, same_sign=True)
    stats = build_lap_stats(lap)
    over = [s for s in stats.symptom_scores if s.balance is Balance.OVERSTEER]
    assert over


def test_dirty_lap_is_not_stable():
    lap = _with_yaw(synth.build_lap(n=200, clean=False), ratio=0.3)
    assert build_lap_stats(lap).stable is False         # clean is False -> not stable


# --- engine wiring: the engineer decision appears in the payload --------------

class _ScriptedReader:
    def __init__(self, frames):
        self._frames = list(frames)
        self._i = 0

    def read(self):
        if self._i < len(self._frames):
            f = self._frames[self._i]
            self._i += 1
            return f
        return TelemetrySnapshot.disconnected()

    def close(self):
        pass


def _full_lap_frames():
    frames = []
    for completed in (0, 1, 2):
        for i in range(30):
            frames.append(synth.snap(
                pos=i / 30, completed_laps=completed,
                current_lap_ms=i * 100, last_lap_ms=89000, speed_kmh=150.0,
            ))
    return frames


def test_engine_surfaces_engineer_block(tmp_path):
    frames = _full_lap_frames()
    eng = CoachEngine(reader=_ScriptedReader(frames), laps_dir=tmp_path)
    state = None
    for _ in range(len(frames)):
        state = eng.tick(0.0)
    assert eng.saved_laps >= 1
    assert state.engineer is not None          # the bridge produced a decision
    assert "kind" in state.engineer and state.engineer["message"]
    eng.close()
