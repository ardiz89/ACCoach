"""Il riferimento tiene conto della temperatura della pista.

I punti di frenata si spostano di 10-20 m fra pista fredda e pista calda, sulla
stessa auto — è il confronto pubblicato da un pilota, non una nostra stima. Il
primato personale segnato di sera su asfalto gommato è quindi il bersaglio
sbagliato per una sessione fredda del mattino: ogni decimo del debrief diventa
meteo invece che guida.

Preferenza, non filtro: se niente corrisponde alle condizioni si torna al miglior
giro e basta. Un riferimento un po' storto batte comunque il silenzio.
"""
from dataclasses import replace

import pytest

from accoach.recording.catalog import LapCatalog, _TEMP_BAND_C
from accoach.recording.storage import find_reference_lap, save_lap

import synth


def _lap(ms: int, road_temp: float, clean: bool | None = True):
    lap = synth.build_lap()
    lap.lap_time_ms = ms
    lap.road_temp = road_temp
    lap.clean = clean
    return lap


def _catalog(tmp_path, laps):
    for i, lap in enumerate(laps):
        # distinct timestamps so save_lap doesn't collide on the filename
        lap.recorded_utc = f"2026-07-2{i}T09:00:00+00:00"
        save_lap(lap, tmp_path)
    return tmp_path


def _elect(tmp_path, road_temp):
    lap = find_reference_lap("ferrari_488_gt3", "monza", tmp_path, road_temp)
    return None if lap is None else lap.lap_time_ms


def test_a_comparable_lap_beats_a_faster_one_in_other_conditions(tmp_path):
    _catalog(tmp_path, [_lap(100_000, 40.0), _lap(103_000, 20.0)])
    assert _elect(tmp_path, 22.0) == 103_000


def test_without_a_temperature_the_fastest_still_wins(tmp_path):
    """Gli strumenti di analisi offline non hanno una sessione in corso: lì
    "il giro migliore" vuol dire il giro migliore."""
    _catalog(tmp_path, [_lap(100_000, 40.0), _lap(103_000, 20.0)])
    assert _elect(tmp_path, None) == 100_000


def test_it_falls_back_rather_than_reporting_no_reference(tmp_path):
    """Nessun giro nella banda: meglio un bersaglio storto che il silenzio."""
    _catalog(tmp_path, [_lap(100_000, 40.0), _lap(103_000, 41.0)])
    assert _elect(tmp_path, 15.0) == 100_000


def test_inside_the_band_the_faster_lap_still_wins(tmp_path):
    """La preferenza non deve diventare un ordinamento per temperatura."""
    _catalog(tmp_path, [_lap(100_000, 25.0), _lap(103_000, 24.0)])
    assert _elect(tmp_path, 24.5) == 100_000


def test_a_lap_with_no_recorded_temperature_is_not_called_similar(tmp_path):
    """0 significa "mai registrata", non "zero gradi"."""
    _catalog(tmp_path, [_lap(100_000, 0.0), _lap(103_000, 25.0)])
    assert _elect(tmp_path, 25.0) == 103_000


def test_a_dirty_lap_is_still_excluded_whatever_the_weather(tmp_path):
    """La condizione non deve riaprire la porta ai giri fuori pista."""
    _catalog(tmp_path, [_lap(100_000, 25.0, clean=False), _lap(103_000, 40.0)])
    assert _elect(tmp_path, 25.0) == 103_000


def test_the_band_is_wide_enough_to_ever_match(tmp_path):
    """Troppo stretta e la preferenza non trova mai niente: come non averla."""
    assert 5.0 <= _TEMP_BAND_C <= 12.0


def test_the_catalog_reports_the_conditions_it_stores(tmp_path):
    """Erano indicizzate da v5 e non le leggeva nessuna query né nessuna UI."""
    _catalog(tmp_path, [_lap(100_000, 31.5)])
    with LapCatalog(tmp_path / "catalog.db") as cat:
        from accoach.recording.storage import list_lap_files
        cat.sync(list_lap_files(tmp_path))
        rows = cat.laps_for("ferrari_488_gt3", "monza")
    assert rows and rows[0]["road_temp"] == pytest.approx(31.5, abs=0.1)
