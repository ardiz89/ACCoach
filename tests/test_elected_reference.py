"""The analysis page compares against the lap the coach actually elected.

The contradiction this removes was visible on screen: the dropdown starred the
fastest lap, while the reference query (`clean <> 0`, confirmed-clean preferred)
had already rejected it for being driven off track. So the star sat on one lap and
the whole page was comparing against another, with nothing saying why.

Measured on the real archive the day this was written: `spa-1998` had exactly one
lap, dirty, so `best_reference_path` returned None — and the page still has to
work in that case rather than go blank.
"""
from dataclasses import replace

import pytest

from accoach.api import _elected_path
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import save_lap

import synth


def _lap(ms: int, clean: bool | None):
    lap = synth.build_lap()
    return replace(lap, lap_time_ms=ms, clean=clean)


@pytest.fixture
def cat(tmp_path):
    paths = []
    for ms, clean in ((100_000, False), (102_000, True), (103_000, None)):
        paths.append(save_lap(_lap(ms, clean), tmp_path))
    with LapCatalog(tmp_path / "catalog.db") as c:
        c.sync(paths)
        yield c, {p.name: p for p in paths}


def _rows(cat_obj, car, track):
    return [r for r in cat_obj.laps_for(car, track)
            if r["valid"] and r["lap_time_ms"] > 0]


def test_the_fastest_lap_is_not_elected_when_it_is_dirty(cat):
    c, _ = cat
    car, track = synth.build_lap().car_model, synth.build_lap().track
    elected = _elected_path(c, car, track, _rows(c, car, track))
    assert elected is not None
    assert "1m40s000" not in elected, "the 100.0s lap was driven off track"


def test_a_confirmed_clean_lap_beats_an_unknown_one(cat):
    c, _ = cat
    car, track = synth.build_lap().car_model, synth.build_lap().track
    elected = _elected_path(c, car, track, _rows(c, car, track))
    assert "1m42s000" in elected, "clean=True outranks clean=None even if slower"


def test_it_falls_back_to_the_fastest_when_every_lap_is_dirty(tmp_path):
    """The spa-1998 case: one lap on record and it's dirty. Don't go blank."""
    paths = [save_lap(_lap(ms, False), tmp_path) for ms in (105_000, 108_000)]
    with LapCatalog(tmp_path / "catalog.db") as c:
        c.sync(paths)
        car, track = synth.build_lap().car_model, synth.build_lap().track
        assert c.best_reference_path(car, track) is None
        elected = _elected_path(c, car, track, _rows(c, car, track))
        assert elected is not None and "1m45s000" in elected


def test_no_laps_at_all_elects_nothing(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as c:
        c.sync([])
        assert _elected_path(c, "car", "track", []) is None
