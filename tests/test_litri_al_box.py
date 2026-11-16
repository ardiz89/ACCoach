"""Entrando in corsia box, quanti litri mettere nel menu del gioco."""
import struct

import pytest

from accoach.coaching.cue import CueCategory
from accoach.coaching.fuel import FuelEngineer, litres_to_add
from accoach.coaching.spoken import spoken_phrases
from accoach.diagnostics import box_fields
from accoach.i18n import cue_text
from accoach.telemetry.snapshot import SessionType

import synth

MIN = 60_000.0


def test_it_counts_the_laps_left_plus_a_spare():
    # 10 minuti a 1:40 sono 6 giri, piu' uno: 7 x 3 l = 21, con 6 a bordo 15.
    assert litres_to_add(6.0, 3.0, 100_000, 10 * MIN) == 15.0


def test_a_started_lap_has_to_be_finished():
    assert litres_to_add(0.0, 3.0, 100_000, 10 * MIN + 1) == 24.0


def test_the_tank_is_the_limit():
    assert litres_to_add(10.0, 3.0, 100_000, 100 * MIN, max_fuel=50.0) == 40.0


@pytest.mark.parametrize("kw", [dict(per_lap=0.0), dict(lap_ms=0.0), dict(time_left_ms=0.0)])
def test_without_the_numbers_it_says_nothing(kw):
    args = dict(fuel=6.0, per_lap=3.0, lap_ms=100_000, time_left_ms=10 * MIN)
    assert litres_to_add(**{**args, **kw}) is None


def _engine_after_laps():
    f = FuelEngineer()
    f._burns, f._laps_ms = [3.0, 3.0], [100_000, 100_000]
    return f


def _enter_lane(f, **kw):
    base = dict(session=SessionType.RACE, fuel=6.0, session_time_left_ms=10 * MIN,
                max_fuel=120.0)
    f.update(synth.snap(0.97, **{**base, **kw}), 0.0)
    return f.update(synth.snap(0.98, in_pit_lane=True, **{**base, **kw}), 0.1)


def test_in_a_race_it_is_said_on_entering_the_pit_lane():
    cues = _enter_lane(_engine_after_laps())
    assert [c.message for c in cues] == ["Aggiungi 15 litri."]
    assert cues[0].category is CueCategory.FUEL


def test_only_once_per_stop():
    f = _engine_after_laps()
    _enter_lane(f)
    assert f.update(synth.snap(0.99, in_pit_lane=True, session=SessionType.RACE,
                               fuel=6.0, session_time_left_ms=10 * MIN), 0.2) == []


def test_it_rounds_up_to_what_is_recorded():
    cues = _enter_lane(_engine_after_laps(), fuel=4.0)     # 17 litri
    assert [c.message for c in cues] == ["Aggiungi 20 litri."]


def test_never_more_than_the_tank_holds():
    cues = _enter_lane(_engine_after_laps(), fuel=4.0, max_fuel=23.0)   # posto per 19
    assert [c.message for c in cues] == ["Aggiungi 15 litri."]


def test_enough_fuel_is_said_as_such():
    cues = _enter_lane(_engine_after_laps(), fuel=30.0)
    assert [c.message for c in cues] == ["Benzina sufficiente fino a fine sessione."]


def test_a_practice_stop_for_the_setup_does_not_ask_to_fill_up():
    assert _enter_lane(_engine_after_laps(), session=SessionType.PRACTICE, fuel=40.0) == []


def test_in_practice_it_speaks_when_the_tank_is_nearly_empty():
    cues = _enter_lane(_engine_after_laps(), session=SessionType.PRACTICE, fuel=6.0)
    assert [c.message for c in cues] == ["Aggiungi 15 litri."]


def test_a_session_without_a_clock_says_nothing():
    assert _enter_lane(_engine_after_laps(), session_time_left_ms=0.0) == []


def test_no_measured_lap_no_number():
    assert _enter_lane(FuelEngineer()) == []


def test_every_number_said_is_recorded_and_translated():
    phrases = spoken_phrases()
    assert "Aggiungi 5 litri." in phrases and "Aggiungi 120 litri." in phrases
    assert "Benzina sufficiente fino a fine sessione." in phrases
    assert cue_text("Aggiungi 15 litri.", "en") == "Add 15 litres."


def test_the_box_fields_are_counted_from_the_measured_offset():
    raw = bytearray(1580)
    struct.pack_into("<i", raw, 1532, 3)
    struct.pack_into("<f", raw, 1536, 42.5)
    struct.pack_into("<i", raw, 1572, 2)
    got = box_fields(bytes(raw))
    assert got["treno nel menu"] == 3 and got["litri nel menu"] == 42.5
    assert got["treno montato"] == 2
