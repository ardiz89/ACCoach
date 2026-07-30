"""Benzina registrata (schema v11): la misura, e i casi in cui si rifiuta.

Il coach live la benzina la misurava da sempre e la buttava via: finita la
sessione, «quanto mi costa un giro» non aveva risposta. Ora il canale si scrive.

Quello che va tenuto fermo qui non è la sottrazione — è **quando non rispondere**:
un giro che ha rifornito non ha un consumo, e un giro registrato prima che il
canale esistesse non ha consumo *zero*, ha consumo *ignoto*. Sono due None
diversi da uno 0.0 che qualcuno leggerebbe come "non hai consumato".
"""
from fastapi.testclient import TestClient

from accoach.api import _fuel_mean, _fuel_of, create_api
from accoach.coaching.fuel import burned
from accoach.recording.catalog import LapCatalog, _fuel_used
from accoach.recording.lap import SAMPLE_FIELDS, SCHEMA_VERSION
from accoach.recording.storage import load_lap, save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _fuelled(lap, start=52.0, per_sample=0.005):
    for i, s in enumerate(lap.samples):
        s.fuel = start - i * per_sample
    return lap


# --- il canale ---------------------------------------------------------------

def test_the_channel_is_written_and_read_back(tmp_path):
    """Andata e ritorno su disco: le colonne si rileggono per nome, quindi un
    canale nuovo o si scrive *e* si rilegge, o non serve a niente."""
    assert "fuel" in SAMPLE_FIELDS and SCHEMA_VERSION >= 11
    path = save_lap(_fuelled(synth.build_lap()), tmp_path)
    back = load_lap(path)
    assert back.schema_version == SCHEMA_VERSION
    assert back.samples[0].fuel == 52.0
    assert back.samples[-1].fuel < back.samples[0].fuel


def test_a_lap_recorded_before_the_channel_reads_unknown_not_empty():
    """Il difetto che questo evita: un giro vecchio che dichiara di aver
    consumato 0 litri."""
    assert burned(synth.build_lap()) is None


# --- la misura ---------------------------------------------------------------

def test_the_burn_is_the_difference_between_the_two_ends():
    lap = _fuelled(synth.build_lap(), start=52.0, per_sample=0.005)
    used = 0.005 * (len(lap.samples) - 1)
    assert burned(lap) == round(used, 2)


def test_a_lap_that_refuelled_has_no_burn_rate():
    """Il serbatoio è salito: fra i due estremi c'è un rifornimento, non un
    consumo. Stessa regola dell'ingegnere live, che quei giri li scarta."""
    lap = _fuelled(synth.build_lap())
    for s in lap.samples[len(lap.samples) // 2:]:
        s.fuel += 30.0
    assert burned(lap) is None


def test_the_catalog_and_the_module_agree(tmp_path):
    """Due strade allo stesso numero — la scheda Sessione lo legge dall'indice, un
    giro aperto a mano lo ricalcola. Se divergessero, la pagina si
    contraddirebbe da sola."""
    lap = _fuelled(synth.build_lap())
    path = save_lap(lap, tmp_path)
    import gzip
    import json
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    assert _fuel_used(d) == burned(lap)


# --- quello che arriva alla pagina ------------------------------------------

def _client(tmp_path, fuel: bool):
    for i, (name, kw) in enumerate((("fast", {}), ("slow", {"slow_corner": 0, "amt": 30}))):
        lap = synth.build_lap(**kw)
        if fuel:
            _fuelled(lap, start=52.0 - i * 3.0)
        lap.recorded_utc = f"2026-06-2{i}T18:0{i}:00+00:00"
        save_lap(lap, tmp_path)
    return TestClient(create_api(tmp_path))


def _session(tmp_path, fuel: bool):
    r = _client(tmp_path, fuel).get("/api/sessions", params={"car": CAR, "track": TRACK})
    assert r.status_code == 200, r.text
    return r.json()["current"]


def test_the_session_reports_litres_per_lap(tmp_path):
    cur = _session(tmp_path, fuel=True)
    assert cur["fuel_per_lap"] > 0
    assert all(l["fuel_used"] > 0 for l in cur["laps_detail"])


def test_a_session_without_the_channel_says_nothing_at_all(tmp_path):
    """None, non 0.0: la vista nasconde la voce invece di stampare un numero che
    nessuno ha bruciato."""
    cur = _session(tmp_path, fuel=False)
    assert cur["fuel_per_lap"] is None
    assert all(l["fuel_used"] is None for l in cur["laps_detail"])


def test_the_average_ignores_the_laps_that_never_measured():
    """Un out-lap dai box rifornisce e resta senza numero: mediarlo come zero
    porterebbe il consumo della sessione verso il basso, cioè verso una bugia
    comoda."""
    rows = [{"fuel_used": 3.0}, {"fuel_used": None}, {"fuel_used": 3.4}]
    assert _fuel_mean(rows) == 3.2
    assert _fuel_of({"fuel_used": None}) is None
    assert _fuel_mean([{"fuel_used": None}]) is None
