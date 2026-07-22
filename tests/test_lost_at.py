"""Where the lap stopped counting, not just that it did.

`clean=False` told the driver a lap had been thrown away and never said at which
corner — the only part of it they can do anything about. `lost_at` is the track
position of the FIRST moment the lap stopped counting: after that the lap was
already gone, so a later, bigger excursion is a consequence, not the cause.

Whichever signal the title actually publishes wins. AC counts wheels off, ACC
latches a flag, and neither is live on the other — see the offset work in the
2026-07-21 sessions.
"""
from dataclasses import replace

import pytest

from accoach.recording.lap import SCHEMA_VERSION, Lap
from accoach.recording.recorder import LapRecorder
from accoach.recording.storage import load_lap, save_lap
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="ferrari_488_gt3_evo", track="monza", speed_kmh=180.0,
    last_lap_ms=123_732,
)


def _drive(at: dict | None = None):
    """One lap, with per-position snapshot overrides applied on the way round."""
    at = at or {}
    rec = LapRecorder()
    # Approach the line first: a buffer that didn't open AT a crossing is a
    # partial, and a partial's verdict is deliberately unknown.
    frames = [replace(_LIVE, lap_position=0.9, completed_laps=0)]
    for p in range(0, 100, 2):
        pos = p / 100
        frames.append(replace(_LIVE, lap_position=pos, completed_laps=1,
                              **at.get(p, {})))
    frames += [replace(_LIVE, lap_position=0.995, completed_laps=2),
               replace(_LIVE, lap_position=0.002, completed_laps=2)]
    laps = [lap for f in frames if (lap := rec.update(f)) is not None]
    return laps[-1]


def test_acc_records_where_the_flag_dropped():
    lap = _drive({70: {"lap_valid": False}, 72: {"lap_valid": False}})
    assert lap.clean is False
    assert lap.lost_at == pytest.approx(0.70)


def test_ac_records_where_the_wheels_went_out():
    lap = _drive({16: {"tyres_out": 4}})
    assert lap.clean is False
    assert lap.lost_at == pytest.approx(0.16)


def test_the_first_place_wins_not_the_worst():
    """Run wide, then spin recovering. The corner that started it is the finding."""
    lap = _drive({16: {"tyres_out": 3}, 50: {"tyres_out": 4}})
    assert lap.lost_at == pytest.approx(0.16)


def test_a_clean_lap_has_nowhere_to_point_at():
    lap = _drive()
    assert lap.clean is True and lap.lost_at is None


def test_a_brush_of_a_kerb_is_not_losing_the_lap():
    """Two wheels out is within track limits; the dirty threshold is three."""
    lap = _drive({30: {"tyres_out": 2}})
    assert lap.clean is True and lap.lost_at is None


def test_it_survives_the_round_trip_to_disk(tmp_path):
    lap = _drive({70: {"lap_valid": False}})
    back = load_lap(save_lap(lap, tmp_path))
    assert back.lost_at == pytest.approx(0.70)
    assert back.schema_version == SCHEMA_VERSION


def test_a_lap_recorded_before_the_field_existed_says_nothing(tmp_path):
    """Never recorded is not the same as nowhere, so it must not become a position."""
    d = _drive({70: {"lap_valid": False}}).to_dict()
    del d["lost_at"]
    assert Lap.from_dict(d).lost_at is None


# --- naming: which corner is that? ---------------------------------------

def test_a_position_inside_a_corner_gets_its_name():
    from accoach.api import _corner_at
    from accoach.track import detect_corners
    import synth

    corners = detect_corners(synth.build_lap().samples)
    assert corners, "the synthetic track has two corners by construction"
    c = corners[0]
    assert _corner_at(c.apex_pos, corners, {c.index: "Prima Variante"}) \
        == "Prima Variante"


def test_a_position_on_a_straight_gets_no_name():
    """No nearest-corner fallback: a confident wrong corner is worse than none."""
    from accoach.api import _corner_at
    from accoach.track import detect_corners
    import synth

    corners = detect_corners(synth.build_lap().samples)
    straight = min(corners, key=lambda c: c.entry_pos).entry_pos / 2
    assert _corner_at(straight, corners, {}) is None
