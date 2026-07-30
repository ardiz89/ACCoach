"""api: /api/braking — the braking sheet, and which laps get pooled into it.

The maths is pinned in test_braking_points.py. What belongs here is the choice
this endpoint makes and the module deliberately doesn't: *which* laps belong on
the same sheet. Two laps 20° of asphalt apart are two circuits, and pooling them
would produce a braking point that belongs to neither.
"""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _save(tmp_path, day, road_temp=None, clean=True, amt=0):
    lap = synth.build_lap(slow_corner=0 if amt else None, amt=amt, clean=clean)
    lap.recorded_utc = f"{day}T18:00:00+00:00"
    if road_temp is not None:
        lap.road_temp = road_temp
    save_lap(lap, tmp_path)
    return lap


def _sheet(client, **kw):
    params = {"car": CAR, "track": TRACK}
    params.update(kw)
    r = client.get("/api/braking", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_sheet_has_a_row_per_braking_corner(tmp_path):
    for i, day in enumerate(("2026-06-20", "2026-06-21", "2026-06-22")):
        _save(tmp_path, day, amt=i * 4)
    j = _sheet(TestClient(create_api(tmp_path)))
    assert len(j["rows"]) == 2
    for r in j["rows"]:
        assert r["speed_kmh"] > r["vmin_kmh"]
        assert r["gear"] and r["laps"] >= 1
    assert j["laps"] == 3


def test_only_laps_in_the_same_temperature_band_are_pooled(tmp_path):
    """The 10-20 m a braking point moves between a cold and a hot track is the
    reason the static sheet everyone shares doesn't work. Ours must not repeat
    it by averaging across the same gap."""
    _save(tmp_path, "2026-06-20", road_temp=32.0)
    _save(tmp_path, "2026-06-21", road_temp=33.5)
    _save(tmp_path, "2026-06-22", road_temp=12.0)     # a cold morning
    j = _sheet(TestClient(create_api(tmp_path)))
    assert j["laps"] == 2
    assert j["road_temp_from"] == 32.0 and j["road_temp_to"] == 33.5


def test_with_no_temperatures_recorded_it_pools_everything_rather_than_nothing(tmp_path):
    """Most archives predate the field. A sheet is better than a blank page —
    it just can't claim conditions it doesn't have."""
    for day in ("2026-06-20", "2026-06-21"):
        _save(tmp_path, day)
    j = _sheet(TestClient(create_api(tmp_path)))
    assert j["laps"] == 2
    assert j["road_temp_from"] is None and j["road_temp_to"] is None
    assert j["rows"]


def test_a_lap_driven_off_track_is_not_a_braking_reference(tmp_path):
    """Same rule as the reference election: time you can't repeat doesn't teach
    a braking point either."""
    _save(tmp_path, "2026-06-20", clean=True)
    _save(tmp_path, "2026-06-21", clean=False)
    j = _sheet(TestClient(create_api(tmp_path)))
    assert j["laps"] == 1


def test_the_rows_carry_the_same_corner_names_as_the_rest_of_the_page(tmp_path):
    """Curated names are proper nouns and stay put in both languages; only the
    numbered fallback is translated. A corner called two things on two tabs is
    the bug this shares its naming with the rest of the report to avoid."""
    _save(tmp_path, "2026-06-20")
    c = TestClient(create_api(tmp_path))
    en = [r["name"] for r in _sheet(c, lang="en")["rows"]]
    it = [r["name"] for r in _sheet(c, lang="it")["rows"]]
    assert en == ["Corner 1", "Variante Ascari"]
    assert it == ["Curva 1", "Variante Ascari"]


def test_csv_is_the_same_sheet_as_a_file(tmp_path):
    """The artefact people print and tape to the desk — the whole reason the
    static version got 332 votes."""
    _save(tmp_path, "2026-06-20")
    c = TestClient(create_api(tmp_path))
    rows = _sheet(c)["rows"]
    r = c.get("/api/braking", params={"car": CAR, "track": TRACK, "fmt": "csv"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    lines = [l for l in r.text.splitlines() if l.strip()]
    assert len(lines) == len(rows) + 1
    assert lines[0].startswith("index,name,speed_kmh,gear")


def test_a_combo_with_no_valid_lap_is_a_404_not_an_empty_sheet(tmp_path):
    c = TestClient(create_api(tmp_path))
    assert c.get("/api/braking",
                 params={"car": CAR, "track": "spa"}).status_code == 404
