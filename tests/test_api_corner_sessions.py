"""/api/progress: la mediana per sessione, per le curve su cui stai lavorando."""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _lap(tmp_path, when, *, amt=0):
    lap = synth.build_lap(slow_corner=0, amt=amt) if amt else synth.build_lap()
    lap.recorded_utc = when
    save_lap(lap, tmp_path)


def _progress(tmp_path):
    c = TestClient(create_api(tmp_path))
    return c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()


def _evening(tmp_path, day, amt):
    for i in range(4):
        _lap(tmp_path, f"2026-08-0{day}T18:{2 * i:02d}:00+00:00", amt=amt)


def test_the_key_is_always_there_even_with_no_laps(tmp_path):
    """Chi deve controllare se una chiave esiste, un giorno se lo dimentica."""
    assert _progress(tmp_path)["corner_sessions"] == []


def test_a_corner_that_improves_gives_a_falling_series(tmp_path):
    _lap(tmp_path, "2026-07-31T18:00:00+00:00")      # il riferimento (il più veloce)
    _evening(tmp_path, 1, 40)                        # 4 giri, −0,680 s alla curva 0
    _evening(tmp_path, 2, 20)                        # 4 giri, −0,340 s
    j = _progress(tmp_path)
    series = j["corner_sessions"]
    assert series, "una curva sistematica deve avere la sua serie"
    assert series[0]["corner_index"] == 0
    assert series[0]["name"]
    pts = series[0]["points"]
    assert len(pts) == 2
    assert pts[0]["median_s"] == 0.68 and pts[1]["median_s"] == 0.34
    assert pts[0]["laps"] == 4


def test_only_systematic_corners_get_a_series(tmp_path):
    """Un errore episodico non è una cosa su cui misurare un andamento."""
    _lap(tmp_path, "2026-07-31T18:00:00+00:00")
    _evening(tmp_path, 1, 40)
    _evening(tmp_path, 2, 20)
    j = _progress(tmp_path)
    systematic = {t["corner_index"] for t in j["trends"] if t["systematic"]}
    assert systematic, "il test non vale niente se nessuna curva è sistematica"
    assert {s["corner_index"] for s in j["corner_sessions"]} <= systematic
