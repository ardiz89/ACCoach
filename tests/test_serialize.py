"""serialize: EngineState -> JSON-able dict for frontends."""
import json

from accoach.comparison import LapComparator, Reference
from accoach.engine import EngineState
from accoach.serialize import (
    cue_to_dict,
    delta_to_dict,
    snapshot_to_dict,
    state_to_dict,
)
from accoach.coaching.cue import Cue, CueCategory
from accoach.telemetry.snapshot import TelemetrySnapshot

import synth


def test_snapshot_to_dict_shape_and_rounding():
    s = synth.snap(pos=0.123456, speed_kmh=180.49, throttle=0.6667,
                   tc_level=4, abs_level=2, current_lap_ms=61234)
    d = snapshot_to_dict(s)
    assert d["connected"] is True
    assert d["status"] == "LIVE"
    assert d["speed_kmh"] == 180.5
    assert d["lap_position"] == 0.1235
    assert d["aids"] == {"tc": 4, "abs": 2, "engine_map": -1}
    assert d["lap"]["current"] == "1:01.234"


def test_delta_to_dict_none_passthrough():
    assert delta_to_dict(None) is None


def test_delta_to_dict_values():
    ref = Reference(synth.build_lap())
    cmp = LapComparator(ref)
    st = cmp.compare(synth.snap(pos=0.5, current_lap_ms=int(ref.time_at(0.5)) + 500))
    d = delta_to_dict(st)
    assert d["ms"] == round(st.delta_ms, 1)
    assert d["ahead"] is False
    assert d["reference"] == "1:40.000"


def test_cue_to_dict():
    assert cue_to_dict(None) is None
    d = cue_to_dict(Cue(CueCategory.CARRY_SPEED, "Porta più velocità", 150.0, 2, 0.3))
    assert d["category"] == "carry_speed"
    assert d["message"] == "Porta più velocità"
    assert d["segment"] == 2


def test_state_to_dict_is_json_serializable():
    st = EngineState(
        snapshot=TelemetrySnapshot.disconnected(),
        delta=None, spoken=None, saved_laps=3, reference_ms=99000,
        history=["a", "b"],
    )
    payload = state_to_dict(st)
    # Round-trips through JSON without error and keeps the frontend fields.
    back = json.loads(json.dumps(payload))
    assert back["connected"] is False
    assert back["saved_laps"] == 3
    assert back["reference_ms"] == 99000
    assert back["history"] == ["a", "b"]
    assert back["delta"] is None and back["cue"] is None
