"""Un giro sa con che setup è stato guidato.

L'ingegnere giudicava una modifica ACCEPT/REVERT sul tempo mediano di una
finestra di giri **senza poter verificare su quale setup fossero** quei giri: il
verdetto poggiava su un'assunzione mai registrata. E chi confronta due giri nel
report leggeva un gap senza sapere se era una staccata sbagliata o un click di
brake bias. Questi campi (schema v9) chiudono entrambe le cose.

Solo ACC: su AC i livelli aiuti non esistono e restano a -1.
"""
from dataclasses import replace

import pytest

from accoach.recording.lap import SCHEMA_VERSION, Lap
from accoach.recording.recorder import LapRecorder
from accoach.recording.storage import load_lap, save_lap
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

import synth

_ACC = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="ferrari_488_gt3_evo", track="monza", speed_kmh=180.0,
    last_lap_ms=123_000, is_acc=True, lap_valid=True,
    tc_level=3, abs_level=2, engine_map=1, brake_bias=0.54,
)


def _record_one_lap(**setup):
    rec = LapRecorder()
    base = replace(_ACC, **setup)
    frames = [replace(base, lap_position=0.9, completed_laps=0)]
    frames += [replace(base, lap_position=p / 100, completed_laps=1)
               for p in range(0, 100, 2)]
    frames += [replace(base, lap_position=0.0, completed_laps=2)]
    laps = [lap for f in frames if (lap := rec.update(f)) is not None and lap.valid]
    return laps[-1]


def test_the_recorded_lap_carries_its_setup():
    lap = _record_one_lap()
    assert (lap.tc_level, lap.abs_level, lap.engine_map) == (3, 2, 1)
    assert lap.brake_bias == pytest.approx(0.54)


def test_the_setup_is_the_value_at_the_line():
    """Gli aiuti si cambiano in corsa: conta il setup su cui il giro CHIUDE,
    perché è quello che il giro successivo eredita."""
    rec = LapRecorder()
    early = replace(_ACC, brake_bias=0.54)
    late = replace(_ACC, brake_bias=0.53)      # spostato a metà giro
    frames = [replace(early, lap_position=0.9, completed_laps=0)]
    frames += [replace(early, lap_position=p / 100, completed_laps=1)
               for p in range(0, 50, 2)]
    frames += [replace(late, lap_position=p / 100, completed_laps=1)
               for p in range(50, 100, 2)]
    frames += [replace(late, lap_position=0.0, completed_laps=2)]
    laps = [lap for f in frames if (lap := rec.update(f)) is not None and lap.valid]
    assert laps[-1].brake_bias == pytest.approx(0.53)


def test_it_survives_the_round_trip(tmp_path):
    lap = _record_one_lap()
    back = load_lap(save_lap(lap, tmp_path))
    assert (back.tc_level, back.abs_level) == (3, 2)
    assert back.brake_bias == pytest.approx(0.54)
    assert back.schema_version == SCHEMA_VERSION


def test_an_ac_lap_has_no_setup(tmp_path):
    """AC non espone i livelli: -1, non 0, che sarebbe un valore reale."""
    lap = synth.build_lap()          # sintetico = AC, nessun aiuto
    back = load_lap(save_lap(lap, tmp_path))
    assert back.tc_level == -1 and back.brake_bias == -1.0


def test_a_pre_v9_file_loads_as_unknown():
    d = _record_one_lap().to_dict()
    for k in ("tc_level", "abs_level", "engine_map", "brake_bias"):
        del d[k]
    lap = Lap.from_dict(d)
    assert lap.tc_level == -1 and lap.brake_bias == -1.0


def test_brake_bias_zero_is_not_confused_with_missing():
    """null = sconosciuto, 0.0 = un valore (per quanto irreale): non confonderli."""
    d = _record_one_lap().to_dict()
    d["brake_bias"] = 0.0
    assert Lap.from_dict(d).brake_bias == 0.0


# --- the API surfaces the difference, only when it matters -----------------

def test_the_api_reports_a_setup_when_present():
    from accoach.api import _setup_of

    assert _setup_of(_record_one_lap()) == {
        "tc": 3, "abs": 2, "engine_map": 1, "brake_bias": 54.0}


def test_the_api_reports_no_setup_on_an_ac_lap():
    from accoach.api import _setup_of

    assert _setup_of(synth.build_lap()) is None
