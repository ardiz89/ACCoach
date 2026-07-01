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


# --- path-traversal guard: a lap/baseline must be a catalog-known path --------
# These endpoints can be exposed on the LAN, so a crafted `lap`/`baseline` must
# never read an arbitrary file off disk; it falls through to 404 instead.
_EVIL = ["C:/Windows/win.ini", "../../../../etc/passwd", "/etc/passwd"]


def test_analysis_rejects_unknown_lap_path(tmp_path):
    c = _client(tmp_path)
    for p in _EVIL:
        assert c.get("/api/analysis", params={"car": CAR, "track": TRACK, "lap": p}
                     ).status_code == 404
        assert c.get("/api/analysis", params={"car": CAR, "track": TRACK, "baseline": p}
                     ).status_code == 404


def test_sectors_rejects_unknown_lap_path(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/sectors", params={"car": CAR, "track": TRACK, "lap": _EVIL[0]}
                 ).status_code == 404


def test_export_rejects_unknown_lap_path(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/export", params={"car": CAR, "track": TRACK, "lap": _EVIL[0]}
                 ).status_code == 404


def test_analysis_accepts_known_lap_path(tmp_path):
    """The guard must not reject a legitimate catalog path the UI sends back."""
    c = _client(tmp_path)
    rows = c.get("/api/laps", params={"car": CAR, "track": TRACK}).json()
    path = rows[0]["path"]
    r = c.get("/api/analysis",
              params={"car": CAR, "track": TRACK, "lap": path, "baseline": path})
    assert r.status_code == 200


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


def test_progress_tyres_empty_without_channel(tmp_path):
    # Synth laps carry no per-wheel temps/pressures → the trend is empty but the
    # key is always present so the frontend can hide the section cleanly.
    c = _client(tmp_path)
    data = c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()
    assert data["tyres"] == []


def test_progress_tyres_trend_when_recorded(tmp_path):
    for k, day in enumerate(("2026-06-20", "2026-06-21", "2026-06-22"), start=1):
        lap = synth.build_lap()
        for s in lap.samples:
            s.tyre_core_temp = (80.0 + k, 81.0 + k, 85.0 + k, 86.0 + k)
            s.tyre_pressure = (26.0 + 0.1 * k, 26.1 + 0.1 * k,
                               26.5 + 0.1 * k, 26.6 + 0.1 * k)
        lap.recorded_utc = f"{day}T18:00:00+00:00"
        save_lap(lap, tmp_path)
    data = TestClient(create_api(tmp_path)).get(
        "/api/progress", params={"car": CAR, "track": TRACK}).json()
    tyres = data["tyres"]
    assert len(tyres) == 3
    assert tyres[0]["temp"] == [81.0, 82.0, 86.0, 87.0]        # k=1, per wheel
    assert len(tyres[0]["press"]) == 4
    # Chronological: rears heat up across the stint (last lap hotter than first).
    assert tyres[-1]["temp"][2] > tyres[0]["temp"][2]


def test_tyre_means_ignores_unrecorded_channel():
    from accoach.api import _tyre_means
    lap = synth.build_lap()                                    # all-zero tyres
    assert _tyre_means(lap.samples, "tyre_core_temp", 1) is None
    for s in lap.samples:
        s.tyre_pressure = (26.0, 27.0, 28.0, 29.0)
    assert _tyre_means(lap.samples, "tyre_pressure", 2) == [26.0, 27.0, 28.0, 29.0]


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


def test_demo_banner_only_in_demo_mode(tmp_path):
    # A demo server bound to the analysis port must announce itself so synthetic
    # laps can't be mistaken for real data; a normal server must not.
    _seed(tmp_path)
    demo = TestClient(create_api(tmp_path, demo=True))
    real = TestClient(create_api(tmp_path, demo=False))
    for page in ("/", "/engineer"):
        d = demo.get(page).text
        assert 'class="demo-banner"' in d and 'class="demo-mode"' in d
        assert "demo-banner" not in real.get(page).text
