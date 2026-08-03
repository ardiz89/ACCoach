"""The report elects its reference the way the live coach does: for the weather.

The coach passes today's track temperature when it picks a reference
(`engine.py`), so a cold morning is measured against a cold lap. The report
didn't pass anything, so it measured every lap against the outright fastest —
and then starred that lap in the dropdown as "the one the coach uses", which it
wasn't. Every tenth of the debrief was then partly weather.

The report has no "today". What it has is the track temperature of the lap you
are *reviewing*, which is the right anchor: the honest benchmark for a lap driven
at 12° is your best lap at about 12°.
"""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _save(tmp_path, ms, road_temp, day, clean=True):
    lap = synth.build_lap(clean=clean)
    synth.retime(lap, ms)
    lap.road_temp = road_temp
    lap.recorded_utc = f"{day}T18:00:00+00:00"
    save_lap(lap, tmp_path)
    return lap


def _archive(tmp_path):
    """A hot personal best, a decent hot lap, and a cold morning's laps."""
    _save(tmp_path, 99_000, 32.0, "2026-06-20")      # PB, rubbered-in evening
    _save(tmp_path, 100_500, 33.0, "2026-06-21")     # another hot one
    _save(tmp_path, 102_000, 12.0, "2026-06-22")     # cold, best of the morning
    _save(tmp_path, 103_500, 12.5, "2026-06-23")     # cold, the lap under review
    return TestClient(create_api(tmp_path))


def _analysis(c, **kw):
    params = {"car": CAR, "track": TRACK}
    params.update(kw)
    r = c.get("/api/analysis", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _paths(c):
    rows = c.get("/api/laps", params={"car": CAR, "track": TRACK}).json()
    return {r["lap_time_ms"]: r["path"] for r in rows}


def test_a_cold_lap_is_measured_against_a_cold_reference(tmp_path):
    c = _archive(tmp_path)
    p = _paths(c)
    a = _analysis(c, lap=p[103_500])
    assert a["reference"]["path"] == p[102_000], "the hot PB is the wrong target"
    assert a["reference"]["lap_time_ms"] == 102_000


def test_a_hot_lap_is_measured_against_the_hot_personal_best(tmp_path):
    c = _archive(tmp_path)
    p = _paths(c)
    a = _analysis(c, lap=p[100_500])
    assert a["reference"]["path"] == p[99_000]


def test_the_star_follows_the_lap_the_page_actually_compares_against(tmp_path):
    """`best_path` is what the dropdown stars. It naming one lap while the page
    compares against another is the bug that made this worth fixing."""
    c = _archive(tmp_path)
    p = _paths(c)
    for review in (p[103_500], p[100_500]):
        a = _analysis(c, lap=review)
        assert a["best_path"] == a["reference"]["path"]


def test_the_page_says_why_the_benchmark_is_slower_than_your_best(tmp_path):
    """A slower lap as the benchmark, unexplained, reads as a broken app."""
    c = _archive(tmp_path)
    p = _paths(c)
    note = _analysis(c, lap=p[103_500])["reference"]["by_conditions"]
    assert note is not None
    assert note["faster_lap_time"] == "1:39.000"
    assert note["faster_road_temp"] == 32.0
    assert note["road_temp"] == 12.0
    assert note["review_road_temp"] == 12.5


def test_no_note_when_the_benchmark_is_your_fastest_lap(tmp_path):
    c = _archive(tmp_path)
    p = _paths(c)
    assert _analysis(c, lap=p[100_500])["reference"]["by_conditions"] is None


def test_no_note_when_you_chose_the_baseline_yourself(tmp_path):
    """The note explains an election. With a hand-picked baseline there wasn't
    one, and the sentence would be about a choice nobody made."""
    c = _archive(tmp_path)
    p = _paths(c)
    a = _analysis(c, lap=p[103_500], baseline=p[99_000])
    assert a["reference"]["path"] == p[99_000]
    assert a["reference"]["by_conditions"] is None


def test_an_archive_with_no_temperatures_behaves_as_it_always_did(tmp_path):
    """Most archives predate the field: the outright fastest, and no note."""
    for ms, day in ((99_000, "2026-06-20"), (101_000, "2026-06-21")):
        lap = synth.build_lap()
        synth.retime(lap, ms)
        lap.recorded_utc = f"{day}T18:00:00+00:00"
        save_lap(lap, tmp_path)
    c = TestClient(create_api(tmp_path))
    a = _analysis(c)
    assert a["reference"]["lap_time_ms"] == 99_000
    assert a["reference"]["by_conditions"] is None
    assert a["review"]["road_temp"] is None


def test_a_faster_lap_passed_over_for_being_dirty_is_not_blamed_on_the_weather(tmp_path):
    """Two reasons a lap isn't the reference; only one of them is conditions,
    and claiming the wrong one is a confident wrong answer."""
    _save(tmp_path, 99_000, 12.0, "2026-06-20", clean=False)   # faster but cut
    _save(tmp_path, 101_000, 12.2, "2026-06-21")
    _save(tmp_path, 102_000, 12.4, "2026-06-22")
    c = TestClient(create_api(tmp_path))
    p = _paths(c)
    a = _analysis(c, lap=p[102_000])
    assert a["reference"]["lap_time_ms"] == 101_000
    assert a["reference"]["by_conditions"] is None


def test_the_page_says_when_your_best_was_simply_never_judged(tmp_path):
    """The other reason a slower lap is the benchmark, and the newest one.

    Since pre-v8 ACC laps stopped being trusted (catalog._clean_to_int) a driver
    can open this page and find their personal best demoted with no explanation
    — the exact "the app looks broken" failure this note exists to prevent. The
    reason is named `unjudged` and not `temp`: the conditions here are
    identical, and blaming the weather would be a confident wrong answer.
    """
    import gzip
    import json

    _save(tmp_path, 99_000, 12.0, "2026-06-20")                # faster, and old
    _save(tmp_path, 101_000, 12.0, "2026-06-21")
    _save(tmp_path, 102_000, 12.0, "2026-06-22")
    # Make the fast one look like what it would be on disk: an ACC lap from
    # before the track-limits rule existed. Patched after saving because
    # `Lap.to_dict` always stamps the current schema.
    old = next(f for f in tmp_path.glob("*.lap.json.gz") if "1m39s000" in f.name)
    d = json.loads(gzip.decompress(old.read_bytes()).decode("utf-8"))
    d["schema"], d["tyre_compound"] = 7, "dry_compound"
    old.write_bytes(gzip.compress(json.dumps(d).encode("utf-8")))
    # Throw the catalog away so it re-reads the patched file: `sync` skips paths
    # it already knows, and `save_lap` indexed this one before the patch. On a
    # real machine the `_DB_VERSION` bump does exactly this.
    for db in tmp_path.glob("catalog.db*"):
        db.unlink()

    c = TestClient(create_api(tmp_path))
    a = _analysis(c, lap=_paths(c)[102_000])
    assert a["reference"]["lap_time_ms"] == 101_000, "the judged lap is the target"
    note = a["reference"]["by_conditions"]
    assert note and note["reason"] == "unjudged"
    assert note["faster_lap_time"] == "1:39.000"


def test_sectors_agree_with_compare_about_the_benchmark(tmp_path):
    """Two tabs of one page must not disagree about which lap is the target."""
    c = _archive(tmp_path)
    p = _paths(c)
    a = _analysis(c, lap=p[103_500])
    s = c.get("/api/sectors",
              params={"car": CAR, "track": TRACK, "lap": p[103_500]}).json()
    assert s["baseline"]["path"] == a["reference"]["path"]


def test_the_lap_dropdown_gets_the_track_temperature_it_is_written_to_show(tmp_path):
    """The page has printed the degrees next to each lap time since the field
    existed — from a list this payload never carried them in, so the badge has
    never appeared once. Two laps 20° apart are two circuits: the picker has to
    say so before you compare them."""
    c = _archive(tmp_path)
    a = _analysis(c)
    temps = {r["lap_time"]: r["road_temp"] for r in a["laps"]}
    assert temps["1:39.000"] == 32.0
    assert temps["1:43.500"] == 12.5


# --- the report honours the tyre and the grip too --------------------------

def _save_full(tmp_path, ms, day, road_temp=0.0, grip=0.0, compound=""):
    lap = synth.build_lap(clean=True, compound=compound)
    synth.retime(lap, ms)
    lap.road_temp = road_temp
    lap.grip = grip
    lap.recorded_utc = f"{day}T18:00:00+00:00"
    save_lap(lap, tmp_path)


def test_a_wet_lap_is_not_measured_against_your_dry_personal_best(tmp_path):
    """The case the tyre criterion exists for. A different compound is a
    different car, and the report used to hand you the dry PB regardless."""
    _save_full(tmp_path, 99_000, "2026-06-20", road_temp=30.0, compound="dry_compound")
    _save_full(tmp_path, 118_000, "2026-06-21", road_temp=18.0, compound="wet_compound")
    _save_full(tmp_path, 121_000, "2026-06-22", road_temp=18.0, compound="wet_compound")
    c = TestClient(create_api(tmp_path))
    p = _paths(c)
    a = _analysis(c, lap=p[121_000])
    assert a["reference"]["lap_time_ms"] == 118_000
    note = a["reference"]["by_conditions"]
    assert note["reason"] == "compound"
    assert note["compound"] == "wet_compound"
    assert note["faster_compound"] == "dry_compound"
    assert note["faster_lap_time"] == "1:39.000"


def test_the_tyre_is_named_before_the_temperature(tmp_path):
    """Both differ; the sentence reports the stronger reason, not the first."""
    _save_full(tmp_path, 99_000, "2026-06-20", road_temp=35.0, compound="dry_compound")
    _save_full(tmp_path, 118_000, "2026-06-21", road_temp=18.0, compound="wet_compound")
    _save_full(tmp_path, 121_000, "2026-06-22", road_temp=18.0, compound="wet_compound")
    c = TestClient(create_api(tmp_path))
    a = _analysis(c, lap=_paths(c)[121_000])
    assert a["reference"]["by_conditions"]["reason"] == "compound"


def test_grip_can_be_the_reason_when_nothing_else_differs(tmp_path):
    _save_full(tmp_path, 99_000, "2026-06-20", grip=0.70)
    _save_full(tmp_path, 104_000, "2026-06-21", grip=1.00)
    _save_full(tmp_path, 106_000, "2026-06-22", grip=1.00)
    c = TestClient(create_api(tmp_path))
    a = _analysis(c, lap=_paths(c)[106_000])
    assert a["reference"]["lap_time_ms"] == 104_000
    note = a["reference"]["by_conditions"]
    assert note["reason"] == "grip"
    assert note["grip"] == 1.0 and note["faster_grip"] == 0.7
