"""The coach waits for the flying lap, and says that it's waiting.

Two bugs in one. First, the delta gate never covered the out lap: ``abs(delta) <=
3000`` is a *two-sided* band, and leaving the box the delta starts far negative
(your lap clock is ~0 while the reference is already seconds in) and climbs
through the band — so the gate sat open for tens of seconds in the middle of the
out lap, coaching technique on cold tyres and a full tank.

Second, every gate was silent. The driver's own report after a calibration session
was "I drove and nothing happened" — that IS a silent gate, arrived at by accident.
So each one now names itself, and the moment coaching resumes is announced.
"""
from dataclasses import replace

import pytest

from accoach.engine import CoachEngine
from accoach.i18n import t
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="car", track="track", speed_kmh=120.0,
)


class _Delta:
    def __init__(self, ms: float) -> None:
        self.delta_ms = ms


@pytest.fixture
def engine():
    eng = CoachEngine(feed=object())      # non-None: keeps the inline recorder out
    yield eng


def _drive(eng, *frames):
    for f in frames:
        eng._track_flying_lap(f)
    return eng


def test_out_of_the_box_is_an_out_lap(engine):
    _drive(engine, replace(_LIVE, completed_laps=3, lap_position=0.4))
    assert engine._quiet_reason(_LIVE, _Delta(0.0)) == "out_lap"


def test_crossing_the_line_opens_the_gate(engine):
    _drive(engine,
           replace(_LIVE, completed_laps=3, lap_position=0.8),
           replace(_LIVE, completed_laps=4, lap_position=0.01))   # the crossing
    assert engine._quiet_reason(_LIVE, _Delta(0.0)) == ""


def test_the_gate_opens_on_the_crossing_frame_itself(engine):
    """Not one tick later: the tyre-temp and pressure advisors emit right here,
    and they're the one thing an out lap is good for."""
    crossing = replace(_LIVE, completed_laps=4, lap_position=0.01)
    _drive(engine, replace(_LIVE, completed_laps=3, lap_position=0.9))
    engine._track_flying_lap(crossing)
    assert engine._quiet_reason(crossing, _Delta(0.0)) == ""


def test_the_bilateral_band_no_longer_leaks(engine):
    """The measured hole: mid out-lap the delta swings through the band."""
    _drive(engine, replace(_LIVE, completed_laps=3, lap_position=0.5))
    for ms in (-6000.0, -2000.0, 0.0, 2000.0):     # crossing the band
        assert engine._quiet_reason(_LIVE, _Delta(ms)) == "out_lap"


def test_the_pit_lane_beats_everything(engine):
    _drive(engine, replace(_LIVE, completed_laps=4, lap_position=0.9),
           replace(_LIVE, completed_laps=5, lap_position=0.01))
    assert engine._quiet_reason(replace(_LIVE, in_pit_lane=True), _Delta(0.0)) == "pit"


def test_entering_the_pits_cancels_the_flying_lap(engine):
    _drive(engine,
           replace(_LIVE, completed_laps=4, lap_position=0.9),
           replace(_LIVE, completed_laps=5, lap_position=0.01),
           replace(_LIVE, completed_laps=5, in_pit_lane=True))
    # Back on track mid-lap: still an out lap until the next crossing.
    assert engine._quiet_reason(_LIVE, _Delta(0.0)) == "out_lap"


def test_reasons_are_ordered_most_specific_first(engine):
    """On an out lap there is also no delta — saying "no reference" would lie."""
    _drive(engine, replace(_LIVE, completed_laps=3, lap_position=0.5))
    assert engine._quiet_reason(_LIVE, None) == "out_lap"


def test_no_reference_and_off_pace_still_reported(engine):
    _drive(engine, replace(_LIVE, completed_laps=3, lap_position=0.9),
           replace(_LIVE, completed_laps=4, lap_position=0.01))
    assert engine._quiet_reason(_LIVE, None) == "no_reference"
    assert engine._quiet_reason(_LIVE, _Delta(4000.0)) == "off_pace"
    assert engine._quiet_reason(_LIVE, _Delta(-4000.0)) == "off_pace"


def test_every_reason_has_words_in_both_languages():
    for reason in ("pit", "out_lap", "no_reference", "off_pace", "green"):
        for lang in ("en", "it"):
            msg = t(f"quiet.{reason}", lang)
            assert msg and msg != f"quiet.{reason}", f"{reason}/{lang} unwritten"
