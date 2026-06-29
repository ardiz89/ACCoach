"""api: REST endpoints over the saved-lap store."""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _seed(tmp_path):
    """A fast reference + a couple of slower laps recorded on later days."""
    fast = synth.build_lap()
    fast.recorded_utc = "2026-06-20T18:00:00+00:00"
    save_lap(fast, tmp_path)
    for day, amt in (("2026-06-21", 30), ("2026-06-22", 16)):
        lap = synth.build_lap(slow_corner=0, amt=amt)
        lap.recorded_utc = f"{day}T18:00:00+00:00"
        save_lap(lap, tmp_path)


def _client(tmp_path):
    _seed(tmp_path)
    return TestClient(create_api(tmp_path))


def test_combos_lists_the_car_track(tmp_path):
    c = _client(tmp_path)
    rows = c.get("/api/combos").json()
    assert len(rows) == 1
    assert rows[0]["car"] == CAR and rows[0]["track"] == TRACK
    assert rows[0]["laps"] == 3
    assert rows[0]["best_ms"] == 100000


def test_laps_lists_all_for_combo(tmp_path):
    c = _client(tmp_path)
    rows = c.get("/api/laps", params={"car": CAR, "track": TRACK}).json()
    assert len(rows) == 3
    assert all("lap_time" in r for r in rows)


def test_analysis_default_baseline_is_fastest(tmp_path):
    c = _client(tmp_path)
    data = c.get("/api/analysis", params={"car": CAR, "track": TRACK}).json()
    assert data["reference"]["lap_time_ms"] == 100000
    assert data["corners"], "corners should be detected from the baseline"
    assert "channels" in data["reference"] and "delta" in data["review"]
    # corners carry a name (numbered fallback for an unknown track)
    assert all("name" in cc for cc in data["corners"])


def test_analysis_lang_it_translates_levels_and_debrief(tmp_path):
    c = _client(tmp_path)
    en = c.get("/api/progress", params={"car": CAR, "track": TRACK, "lang": "en"}).json()
    it = c.get("/api/progress", params={"car": CAR, "track": TRACK, "lang": "it"}).json()
    en_best = next(lv for lv in en["levels"] if lv["key"] == "best")["label"]
    it_best = next(lv for lv in it["levels"] if lv["key"] == "best")["label"]
    assert en_best == "Your best lap" and it_best == "Tuo miglior giro"


def test_analysis_has_corner_speeds(tmp_path):
    c = _client(tmp_path)
    data = c.get("/api/analysis", params={"car": CAR, "track": TRACK}).json()
    cs = data["corner_speeds"]
    assert cs, "expected per-corner minimum speeds"
    row = cs[0]
    assert {"index", "name", "vmin_live", "vmin_ref", "delta"} <= set(row)
    assert row["delta"] == round(row["vmin_live"] - row["vmin_ref"], 0)


def test_analysis_losses_have_minilesson_fields(tmp_path):
    c = _client(tmp_path)
    data = c.get("/api/analysis", params={"car": CAR, "track": TRACK}).json()
    assert data["losses"], "expected at least one corner loss"
    loss = data["losses"][0]
    assert loss["label"]                      # corner name / number
    assert loss["detail"] and loss["fix"]     # the mini-lesson
    assert "vmin_live" in loss and "vmin_ref" in loss


def test_analysis_exposes_track_map(tmp_path):
    c = _client(tmp_path)
    data = c.get("/api/analysis", params={"car": CAR, "track": TRACK}).json()
    assert data["has_map"] is True
    for side in ("reference", "review"):
        ch = data[side]["channels"]
        assert ch["x"] and ch["z"]
        assert len(ch["x"]) == len(ch["z"]) == len(ch["pos"])
        assert any(v != 0.0 for v in ch["x"])   # real coordinates, not all-zero
    # delta is aligned point-for-point with the review path (so it can colour it)
    assert len(data["review"]["delta"]["delta_s"]) == len(data["review"]["channels"]["x"])


def test_sectors_breakdown_and_ideal(tmp_path):
    c = _client(tmp_path)
    # Review the slowest lap against the fastest baseline.
    laps = c.get("/api/laps", params={"car": CAR, "track": TRACK}).json()
    slow = max(laps, key=lambda l: l["lap_time_ms"])["path"]
    data = c.get("/api/sectors",
                 params={"car": CAR, "track": TRACK, "lap": slow}).json()
    assert data["n"] == 3 and len(data["sectors"]) == 3
    # Real sim sectors (unequal), not equal thirds: boundaries near 0.30 / 0.65.
    assert data["real"] is True
    assert abs(data["sectors"][1]["start"] - 0.30) < 0.02
    assert abs(data["sectors"][2]["start"] - 0.65) < 0.02
    # Sector times sum to the lap time (sectors close on the clock).
    assert sum(s["review_ms"] for s in data["sectors"]) == data["review"]["lap_time_ms"]
    # The slow lap lost time vs the fast baseline somewhere.
    assert any(s["delta_ms"] > 0 for s in data["sectors"])
    # Ideal lap is no slower than the real best, and sums its best sectors.
    ideal = data["ideal"]
    assert ideal["ideal_ms"] == sum(ideal["best_ms"])
    assert ideal["ideal_ms"] <= data["baseline"]["lap_time_ms"]
    assert ideal["gain_ms"] >= 0


def test_analysis_404_for_unknown_combo(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/analysis", params={"car": "nope", "track": "nowhere"})
    assert r.status_code == 404


def test_progress_returns_trend_and_consistency(tmp_path):
    c = _client(tmp_path)
    data = c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()
    assert data["consistency"]["n"] == 3
    assert len(data["laps"]) == 3
    assert data["pb_trend"], "expected a per-day best trend"


def test_progress_levels_and_trends(tmp_path):
    c = _client(tmp_path)
    data = c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()
    # Benchmark ladder: at least your best + the theoretical ideal.
    keys = {lv["key"] for lv in data["levels"]}
    assert "best" in keys and "ideal" in keys
    best = next(lv for lv in data["levels"] if lv["key"] == "best")
    assert best["gain_ms"] == 0
    # The slow laps lose time in corner 0 every time → a systematic trend.
    assert any(t["systematic"] for t in data["trends"])


def test_progress_pro_level_appears_after_import(tmp_path):
    from dataclasses import replace
    _seed(tmp_path)
    pro = replace(synth.build_lap(), source="pro")           # an imported PRO lap
    pro.recorded_utc = "2026-06-19T18:00:00+00:00"
    save_lap(pro, tmp_path)
    data = TestClient(create_api(tmp_path)).get(
        "/api/progress", params={"car": CAR, "track": TRACK}).json()
    assert "pro" in {lv["key"] for lv in data["levels"]}


def test_export_csv_has_header_and_rows(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/export", params={"car": CAR, "track": TRACK, "fmt": "csv"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("t_ms,pos,speed_kmh")
    assert len(lines) > 2


def test_export_json(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/export", params={"car": CAR, "track": TRACK, "fmt": "json"})
    assert r.status_code == 200
    body = r.json()
    assert "samples" in body and "fields" in body
