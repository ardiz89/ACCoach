"""Una fase che non passa e non ha un rimedio dice cosa ha visto.

Rigiocata Imola del 24/09 (16/11): la fase Elettronica si chiudeva con «non ho
trovato nulla da correggere». Il cancello non era passato perche' aveva visto
pattinamento in uscita, e la tabella non ha una leva per quello: la frase diceva
il contrario di quello che era successo. E' il difetto 6 della pagina del 15/11.
"""
import copy

import pytest

from accoach import config
from accoach.engineer import DecisionKind, LapStats, RaceEngineer
from accoach.engineer.profiles import FORMULA_PROFILE, GT3_PROFILE, ROAD_PROFILE
from accoach.engineer.profiles._common import _SEG_LIMIT

PRESS_OK = {"front": 26.5, "rear": 26.5}
ELECTRONICS, BRAKES = 4, 3


@pytest.fixture(autouse=True)
def _italiano():
    # conftest rimette la configurazione predefinita a ogni test.
    config.set_language("it")


def _lap(spin=0, lock=0):
    return LapStats(lap_time_ms=100000, stable=True, symptom_scores={},
                    symptom_corners={}, pressures_hot=dict(PRESS_OK),
                    lock_segments=lock, spin_segments=spin)


def _run(phase_idx, **lap):
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng.phase_idx = phase_idx
    for _ in range(3):
        d = eng.observe(_lap(**lap))
    return eng, d


def test_wheelspin_with_no_lever_is_said_not_hidden():
    eng, d = _run(ELECTRONICS, spin=4)
    assert d.kind is DecisionKind.PHASE_DONE
    assert "nulla da correggere" not in d.message
    assert "pattinamento" in d.message
    assert "3 giri su 3" in d.message
    assert ELECTRONICS in eng.progress()["skipped"]


def test_lockups_with_no_lever_are_said_not_hidden():
    eng, d = _run(BRAKES, lock=_SEG_LIMIT)
    assert d.kind is DecisionKind.PHASE_DONE
    assert "nulla da correggere" not in d.message
    assert "bloccaggi" in d.message
    assert BRAKES in eng.progress()["skipped"]


def test_a_shut_gate_with_nothing_to_name_still_does_not_say_nothing_was_found():
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng.phase_idx = 1
    ph = copy.copy(eng.phases[1])
    ph.gate = lambda window: False
    eng.phases[1] = ph
    for _ in range(3):
        d = eng.observe(_lap())
    assert d.kind is DecisionKind.PHASE_DONE
    assert "nulla da correggere" not in d.message
    assert "non ho una modifica da proporti" in d.message


@pytest.mark.parametrize("profile", [GT3_PROFILE, FORMULA_PROFILE, ROAD_PROFILE],
                         ids=lambda p: p.name)
def test_every_segment_gate_reports_the_counter_it_shuts_on(profile):
    """Il contatore che la fase nomina e' quello su cui il suo cancello si
    chiude: una sola fonte, non due copie che possono divergere."""
    phases = [ph for ph in profile.phases if getattr(ph, "segments", "")]
    assert phases, "ogni profilo ha almeno una fase a tratti"
    for ph in phases:
        field = ph.segments
        assert field in ("spin", "lock")
        under = [_lap(**{field: _SEG_LIMIT - 1})] * 3
        over = [_lap(**{field: _SEG_LIMIT})] * 3
        assert ph.gate(under) is True
        assert ph.gate(over) is False
        assert ph.unfixed(under) is None
        assert ph.unfixed(over) == (field, 3, 3)
