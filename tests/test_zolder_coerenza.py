"""Quattro numeri che a Zolder (29/10) non tornavano.

* L'ideale prendeva un settore da un giro con un'uscita di pista: 1:32.078 con
  un taglio di chicane, mentre sui giri puliti era 1:33.438.
* La costanza contava anche i giri da 1:51 con la fermata, e la Sessione no.
* La scheda frenate nominava il riferimento col tempo di un altro giro.
* Il registro dell'ingegnere non diceva quale modifica aveva tenuto.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.engine import CoachEngine
from accoach.engineer import ledger
from accoach.engineer.core import DecisionKind, RaceEngineer
from accoach.engineer.profiles.gt3 import GT3_PROFILE
from accoach.recording.storage import save_lap
from test_engineer_ledger import _lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"
P = {"car": CAR, "track": TRACK}


def _mine(laps, ms, day, **kw):
    lap = synth.build_lap()
    synth.retime(lap, ms)
    lap.recorded_utc = f"2026-07-{day:02d}T09:00:00+00:00"
    for k, v in kw.items():
        setattr(lap, k, v)
    return save_lap(lap, laps)


def _client(laps):
    return TestClient(create_api(laps))


def _with_a_cut(tmp_path):
    """Il giro piu' veloce di tutti ha un'uscita di pista."""
    laps = tmp_path / "laps"
    _mine(laps, 100_000, 20, clean=True)
    _mine(laps, 101_000, 21, clean=True)
    cut = _mine(laps, 95_000, 22, clean=False)
    return laps, str(cut)


def test_the_ideal_lap_takes_no_sector_from_a_lap_that_went_off(tmp_path):
    laps, cut = _with_a_cut(tmp_path)
    ideal = _client(laps).get("/api/sectors", params=P).json()["ideal"]
    assert cut not in ideal["best_from"]
    assert abs(ideal["ideal_ms"] - 100_000) < 100
    assert ideal["gain_ms"] >= 0


def test_the_training_gap_is_measured_on_the_same_laps(tmp_path):
    laps, _ = _with_a_cut(tmp_path)
    for day, ms in ((23, 102_000), (24, 103_000), (25, 104_000)):
        _mine(laps, ms, day, clean=True)       # il piano vuole almeno 6 giri
    gap = _client(laps).get("/api/training", params=P).json()["gap"]
    assert abs(gap["ideal_ms"] - 100_000) < 100


def test_the_ideal_rung_of_the_ladder_is_never_past_your_best(tmp_path):
    laps, _ = _with_a_cut(tmp_path)
    levels = _client(laps).get("/api/progress", params=P).json()["levels"]
    ideal = next(lv for lv in levels if lv["key"] == "ideal")
    assert abs(ideal["lap_time_ms"] - 100_000) < 100 and ideal["gain_ms"] >= 0


def test_consistency_counts_the_same_laps_on_every_page(tmp_path):
    laps = tmp_path / "laps"
    _mine(laps, 100_000, 20, clean=True)
    _mine(laps, 101_000, 21, clean=True)
    _mine(laps, 120_000, 22, clean=False)      # la fermata in mezzo alla pista
    c = _client(laps)
    assert c.get("/api/progress", params=P).json()["consistency"]["n"] == 2
    assert c.get("/api/analysis", params=P).json()["consistency"]["n"] == 2


def test_the_braking_sheet_names_the_reference_with_its_own_time(tmp_path):
    laps = tmp_path / "laps"
    _mine(laps, 101_000, 20, clean=True)
    _mine(laps, 100_000, 21, clean=True)
    _mine(laps, 102_000, 22, clean=True)
    ref = _client(laps).get("/api/braking", params=P).json()["reference"]
    assert ref["lap_time"] == "1:40.000" and "1m40s000" in ref["path"]


def test_the_ledger_says_which_pressure_change_was_kept(monkeypatch):
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    cold = {"front": 24.0, "rear": 24.0}
    for _ in range(6):
        d = eng.observe(_lap(scores={}, press=cold))
        if d.kind is DecisionKind.PROPOSE:
            break
    tested = d.change.changes[0]
    eng.mark_applied()
    for _ in range(3):
        d = eng.observe(_lap(scores={}, press=cold))
    assert d.kind is DecisionKind.ACCEPTED
    assert d.change is None      # la pagina non deve rileggerla come da scrivere

    written = []
    monkeypatch.setattr(ledger, "append", lambda rec, *a: written.append(rec))
    CoachEngine._log_engineer_outcome(
        None, SimpleNamespace(car_model=CAR, track=TRACK), d)
    assert written[0].param == tested.param
    assert written[0].delta_clicks == tested.delta_clicks
    assert written[0].phase
