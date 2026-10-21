"""Gli endpoint della Pagella: /api/pagella, /api/howto e POST /api/advice.

Giri sintetici salvati in `tmp_path` e letti dal catalogo, come in
`tests/test_plan.py`. I giri lenti sono di due tipi, uno per difetto: `min`
perde velocita' nella curva 0 (Poca velocita' in curva), `thr` apre il gas
tardi nella curva 1 (Gas tardi in uscita). Un giro ha un solo difetto, quindi
in una sessione con due giri per tipo entrambi i difetti sono «principali»
(sopra soglia in meta' dei giri).
"""
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from accoach import pagella
from accoach.api import create_api
from accoach.coaching.advice import ACTIVE, Advice, AdviceCorner
from accoach.coaching.howto import defect_name
from accoach.braking_points import brake_points_of_lap
from accoach.recording import load_lap
from accoach.recording.catalog import LapCatalog
from accoach.track import detect_corners
from accoach.trajectory import line_points, path_length
from accoach.recording.storage import _catalog_path, save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


@pytest.fixture(autouse=True)
def _cache_vuota():
    pagella.clear_cache()
    yield
    pagella.clear_cache()


def _lap(kind, amt):
    if kind is None:
        return synth.build_lap(clean=True)
    if kind == "late_ref":
        # Il migliore che stacca tardi in curva 0 (dentro la curva, dove il
        # debrief lo vede): i giri normali risultano «Freni troppo presto».
        lap = synth.build_lap(clean=True)
        for s in lap.samples:
            if 0.15 <= s.pos < 0.27:
                s.brake = 0.0
        return lap
    if kind == "min_mid":
        # Lento in curva 0 ma stacca piu' tardi degli altri giri lenti (sempre
        # prima del migliore): la media dei metri non e' quella di un giro solo.
        lap = synth.build_lap(slow_corner=0, amt=amt, clean=True)
        for s in lap.samples:
            if 0.15 <= s.pos < 0.255:
                s.brake = 0.0
        return lap
    if kind == "skewed_ref":
        # Il piu' veloce di tutti, ma col suo orologio che non copre il giro.
        lap = synth.retime(synth.build_lap(clean=True), 99_000)
        return synth.skew_clock(lap, 2000)
    if kind == "skewed_min":
        return synth.skew_clock(synth.build_lap(slow_corner=0, amt=26, clean=True),
                                2000)
    if kind == "extra_ref":
        # Il piu' veloce di tutti, con una curva in piu' prima della curva 0:
        # sul suo metro la curva 0 dei giri vecchi diventa la curva 1.
        lap = synth.retime(synth.build_lap(clean=True), 99_000)
        for s in lap.samples:
            if 0.04 <= s.pos <= 0.14:
                d = max(0.0, 1 - abs(s.pos - 0.09) / 0.05)
                s.steer_angle, s.speed_kmh = 0.28 * d, 255 - 100 * d
                s.throttle = 1.0 if s.pos >= 0.09 else 0.0
                s.brake = 0.85 if 0.05 <= s.pos < 0.09 else 0.0
        return lap
    if kind == "min1":
        return synth.build_lap(slow_corner=1, amt=amt, clean=True)
    if kind == "min":
        return synth.build_lap(slow_corner=0, amt=amt, clean=True)
    lap = synth.build_lap(slow_corner=1, amt=amt, clean=True)
    for s in lap.samples:          # gas tardi all'uscita della curva 1
        if 0.70 <= s.pos <= 0.80:
            s.throttle = 0.2
    return lap


def _put(tmp_path, stamp, kind=None, amt=0, compound="", valid=True, clean=True):
    lap = _lap(kind, amt)
    lap.clean = clean
    lap.recorded_utc = stamp
    lap.tyre_compound = compound
    lap.valid = valid
    save_lap(lap, tmp_path)


def _session(tmp_path, hour, kinds, compound="", minute=0):
    for i, (kind, amt) in enumerate(kinds):
        _put(tmp_path, f"2026-10-20T{hour:02d}:{minute + 2 * i:02d}:00+00:00",
             kind, amt, compound)


_MIXED = [("min", 26), ("thr", 20), ("min", 26), ("thr", 20)]


def _two_sessions(tmp_path, second=_MIXED):
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    _session(tmp_path, 11, second)
    return TestClient(create_api(tmp_path))


def _pagella(c, index=0, lang="it"):
    r = c.get("/api/pagella", params={"car": CAR, "track": TRACK,
                                      "index": index, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


def _advice(c, defect, action, expect=200):
    r = c.post("/api/advice", json={"car": CAR, "track": TRACK,
                                    "defect": defect, "action": action})
    assert r.status_code == expect, r.text
    return r.json()


def _rows(tmp_path):
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        return cat.laps_for(CAR, TRACK)


def _ref_path(tmp_path):
    return min(_rows(tmp_path), key=lambda r: r["lap_time_ms"])["path"]


def _stored(tmp_path):
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        return {a["defect"]: a for a in cat.load_advice(CAR, TRACK)}


def _store(tmp_path, advice: dict):
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.save_advice(CAR, TRACK, advice)


# --- la Pagella -------------------------------------------------------------

def test_two_sessions_give_a_full_pagella(tmp_path):
    p = _pagella(_two_sessions(tmp_path))
    assert p["excluded"] is None
    assert p["verdict"]
    assert p["session"]["laps"] == 4 and p["session"]["valid"] == 4
    assert p["session"]["wet"] is False
    keys = [d["key"] for d in p["defects"]]
    assert keys == ["min_speed", "throttle_late"]
    values = [d["value"] for d in p["defects"]]
    assert values == sorted(values, reverse=True)
    for d in p["defects"]:
        assert len(d["series"]) == 2
        assert d["trend"] == "same"
        assert d["name"] == defect_name(d["key"], "it")
        assert d["corners"] and d["corners"][0]["name"]
    assert p["advice"][0]["status"] == "proposed"
    assert p["advice"][0]["defect"] == "min_speed"
    assert p["advice"][0]["corners"]
    assert p["reference"]["lap_time"] and p["reference"]["recorded_utc"]
    assert p["worst_corners"] and all(w["name"] for w in p["worst_corners"])
    assert p["worst_corners"][0]["value_s"] > 0


def test_the_trend_follows_the_previous_session(tmp_path):
    # Seconda sessione: la curva 0 perde molto di piu', il gas tardi sparisce.
    p = _pagella(_two_sessions(tmp_path, second=[("min", 40), ("min", 40)]))
    by = {d["key"]: d for d in p["defects"]}
    assert by["min_speed"]["trend"] == "up"
    assert by["min_speed"]["series"][0] < by["min_speed"]["series"][1]
    # Il gas tardi non e' piu' principale in questa sessione: non e' in lista.
    assert "throttle_late" not in by


def test_the_series_stops_at_six_sessions(tmp_path):
    _put(tmp_path, "2026-10-20T08:00:00+00:00")
    for h in range(9, 17):          # otto sessioni da due giri lenti
        _session(tmp_path, h, [("min", 26), ("min", 26)])
    p = _pagella(TestClient(create_api(tmp_path)))
    assert len(p["defects"][0]["series"]) == 6


def test_trend_thresholds_are_relative_and_absolute():
    assert pagella.trend_of(200.0, 300.0, "ms") == "down"
    assert pagella.trend_of(300.0, 200.0, "ms") == "up"
    # 10% si', ma meno di 20 ms: uguale.
    assert pagella.trend_of(150.0, 165.0, "ms") == "same"
    # 20 ms si', ma meno del 10%: uguale.
    assert pagella.trend_of(500.0, 530.0, "ms") == "same"
    assert pagella.trend_of(0.5, 0.65, "s") == "down"
    assert pagella.trend_of(0.5, 0.58, "s") == "same"
    assert pagella.trend_of(1.0, None, "ms") is None


def test_an_older_session_never_sees_the_ones_after_it(tmp_path):
    p = _pagella(_two_sessions(tmp_path), index=1)
    assert p["excluded"] is None
    for d in p["defects"]:
        assert len(d["series"]) == 1
        assert d["trend"] is None
    assert "prima sessione" in p["verdict"]


def test_a_single_lap_has_no_reference(tmp_path):
    _put(tmp_path, "2026-10-20T10:00:00+00:00")
    p = _pagella(TestClient(create_api(tmp_path)))
    assert p["excluded"] == "no_reference"
    assert p["defects"] == [] and p["advice"] == []
    assert p["verdict"]


def test_no_laps_at_all(tmp_path):
    p = _pagella(TestClient(create_api(tmp_path)))
    assert p["excluded"] == "no_laps"
    assert p["defects"] == []


def test_a_session_without_valid_laps(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    _put(tmp_path, "2026-10-20T11:00:00+00:00", "min", 26, valid=False)
    p = _pagella(TestClient(create_api(tmp_path)))
    assert p["excluded"] == "no_laps"


def test_a_wet_session_with_a_dry_history_is_left_out(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED, compound="dry_compound")
    _session(tmp_path, 11, [(None, 0)] + _MIXED, compound="wet_compound")
    c = TestClient(create_api(tmp_path))
    p = _pagella(c)
    assert p["excluded"] == "wet"
    assert p["session"]["wet"] is True
    assert p["defects"] == [] and p["advice"] == []
    assert "bagnato" in p["verdict"]
    assert _pagella(c, index=1)["excluded"] is None


def test_a_dry_session_with_a_wet_history_is_left_out(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED, compound="wet_compound")
    _session(tmp_path, 11, [(None, 0)] + _MIXED, compound="dry_compound")
    assert _pagella(TestClient(create_api(tmp_path)))["excluded"] == "dry"


def test_two_wet_sessions_make_their_own_history(tmp_path):
    _session(tmp_path, 9, [(None, 0)] + _MIXED, compound="dry_compound")
    _session(tmp_path, 10, [(None, 0)] + _MIXED, compound="wet_compound")
    _session(tmp_path, 11, _MIXED, compound="wet_compound")
    p = _pagella(TestClient(create_api(tmp_path)))
    assert p["excluded"] is None
    assert all(len(d["series"]) == 2 for d in p["defects"])


def test_errors_are_counted_and_named(tmp_path):
    p = _pagella(_two_sessions(tmp_path))
    assert p["errors"], p["errors"]
    for e in p["errors"]:
        assert e["count"] > 0 and e["name"]


def test_a_cut_lap_is_an_off_and_stays_out_of_the_defects(tmp_path):
    """Un giro tagliato e' un'uscita di pista nel conto degli errori, ma i
    difetti restano la media dei giri puliti: il tagliato e' veloce per un
    motivo che non e' la guida."""
    plain = _pagella(_two_sessions(tmp_path / "a"))
    _session(tmp_path / "b", 10, [(None, 0)] + _MIXED)
    _session(tmp_path / "b", 11, _MIXED)
    for m in (20, 22):     # due giri tagliati, lentissimi in curva 0
        _put(tmp_path / "b", f"2026-10-20T11:{m:02d}:00+00:00", "min", 60,
             clean=False)
    p = _pagella(TestClient(create_api(tmp_path / "b")))
    errors = {e["key"]: e for e in p["errors"]}
    assert errors["off"]["count"] == 2
    assert errors["off"]["name"] == "Uscite di pista"
    assert p["session"]["valid"] == 4
    assert p["defects"] == plain["defects"]


def test_english(tmp_path):
    p = _pagella(_two_sessions(tmp_path), lang="en")
    assert p["defects"][0]["name"] == defect_name("min_speed", "en")
    assert "lap" in p["verdict"]


# --- il piano ---------------------------------------------------------------

def test_one_advice_at_a_time(tmp_path):
    c = _two_sessions(tmp_path)
    _advice(c, "min_speed", "follow")
    _advice(c, "throttle_late", "follow", expect=409)
    _advice(c, "min_speed", "drop")
    _advice(c, "throttle_late", "follow")
    p = _pagella(c)
    assert p["advice"][0]["defect"] == "throttle_late"
    assert p["advice"][0]["status"] == ACTIVE
    stored = _stored(tmp_path)
    assert stored["throttle_late"]["accepted_utc"]
    assert stored["throttle_late"]["reference_path"] == _ref_path(tmp_path)
    assert stored["min_speed"]["status"] == "dropped"


def test_following_stores_what_was_proposed(tmp_path):
    c = _two_sessions(tmp_path)
    shown = _pagella(c)["advice"][0]
    _advice(c, "min_speed", "follow")
    a = _stored(tmp_path)["min_speed"]
    assert a["status"] == ACTIVE
    # Il metro con cui e' stato proposto: senza, la prima lettura lo ricalcola.
    assert a["reference_path"] == _ref_path(tmp_path)
    assert a["target"] == shown["target"]
    assert a["corners"][0]["index"] == 0
    assert a["corners"][0]["apex_pos"] > 0


def test_decline_keeps_the_defect_and_drops_the_advice(tmp_path):
    c = _two_sessions(tmp_path)
    _advice(c, "throttle_late", "decline")
    p = _pagella(c)
    assert "throttle_late" in [d["key"] for d in p["defects"]]
    assert "throttle_late" not in [a["defect"] for a in p["advice"]]
    _advice(c, "throttle_late", "undecline")
    assert "throttle_late" in [a["defect"] for a in _pagella(c)["advice"]]


def test_a_declined_advice_is_listed_so_it_can_be_taken_back(tmp_path):
    """«Non lo seguo» toglie il consiglio dal piano: senza questa lista la
    pagina non saprebbe offrire «Riprendi», e la scelta non si potrebbe
    disfare."""
    c = _two_sessions(tmp_path)
    assert _pagella(c)["declined"] == []
    _advice(c, "throttle_late", "decline")
    assert _pagella(c)["declined"] == [
        {"defect": "throttle_late", "name": "Gas tardi in uscita"}]
    assert _pagella(c, lang="en")["declined"] == [
        {"defect": "throttle_late", "name": "Late on the throttle"}]
    _advice(c, "throttle_late", "undecline")
    p = _pagella(c)
    assert p["declined"] == []
    assert "throttle_late" in [a["defect"] for a in p["advice"]
                               if a["status"] == "proposed"]


def test_bad_requests(tmp_path):
    c = _two_sessions(tmp_path)
    _advice(c, "min_speed", "explode", expect=422)
    _advice(c, "nonsense", "follow", expect=422)
    _advice(c, "min_speed", "drop", expect=409)          # nessuno in corso
    _advice(c, "lift", "follow", expect=404)              # non proposto
    _advice(c, "min_speed", "follow")
    _advice(c, "min_speed", "decline", expect=409)        # in corso: si lascia


def test_an_active_advice_is_reached_and_the_next_one_is_proposed(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    ref = _ref_path(tmp_path)
    # Seguito fra le due sessioni: curva 0, obiettivo 120 ms.
    _store(tmp_path, {**asdict(Advice(
        defect="min_speed", corners=[AdviceCorner(0, "x", 0.31, 212.5)],
        baseline=212.5, target=120.0, status=ACTIVE,
        accepted_utc="2026-10-20T10:30:00+00:00")), "reference_path": ref})
    # Dopo: due giri senza perdita in curva 0 (sotto obiettivo), uno sopra.
    _session(tmp_path, 11, [("thr", 20), ("min", 26), ("thr", 20)])
    c = TestClient(create_api(tmp_path))
    p = _pagella(c)
    by = {a["defect"]: a for a in p["advice"]}
    assert by["min_speed"]["status"] == "reached"
    assert by["min_speed"]["progress"]["hits"] == 2
    assert p["advice"][1]["defect"] == "throttle_late"
    assert p["advice"][1]["status"] == "proposed"
    assert defect_name("min_speed", "it") in p["verdict"]
    stored = _stored(tmp_path)["min_speed"]
    assert stored["status"] == "reached"
    # Chiuso sul giro che l'ha deciso, non sull'ora della lettura.
    assert stored["closed_utc"] == "2026-10-20T11:04:00+00:00"
    # Una seconda lettura lo dice ancora: e' la sessione in cui e' successo.
    assert defect_name("min_speed", "it") in _pagella(c)["verdict"]


def test_an_active_advice_is_rebased_when_the_reference_changes(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    _store(tmp_path, {**asdict(Advice(
        defect="min_speed", corners=[AdviceCorner(0, "x", 0.31, 9999.0)],
        baseline=9999.0, target=4999.5, status=ACTIVE,
        accepted_utc="2026-10-20T10:30:00+00:00")), "reference_path": "vecchio"})
    _session(tmp_path, 11, [("min", 40), ("min", 40)])
    _pagella(TestClient(create_api(tmp_path)))
    a = _stored(tmp_path)["min_speed"]
    assert a["reference_path"] == _ref_path(tmp_path)
    # Partenza misurata sulla sessione dell'accettazione (425+425+0+0)/4, non
    # su quella di oggi (680).
    assert a["baseline"] == pytest.approx(212.5, abs=1.0)
    assert a["corners"][0]["mean"] == pytest.approx(212.5, abs=1.0)
    assert a["status"] == ACTIVE


def test_a_new_reference_with_one_more_corner_keeps_the_advice_on_its_corner(tmp_path):
    """Il riferimento nuovo ha una curva in piu' prima di quella del consiglio:
    i numeri scalano di uno. Il consiglio deve restare sulla stessa curva (per
    posizione dell'apex), col nome e la misura di quella, non della curva che
    adesso ha il suo vecchio numero."""
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    ref = _ref_path(tmp_path)
    _store(tmp_path, {**asdict(Advice(
        defect="min_speed", corners=[AdviceCorner(0, "x", 0.31, 212.5)],
        baseline=212.5, target=120.0, status=ACTIVE,
        accepted_utc="2026-10-20T10:30:00+00:00")), "reference_path": ref})
    # Dopo: il nuovo migliore (con la curva in piu') e tre giri lenti in curva 0.
    _session(tmp_path, 11, [("extra_ref", 0), ("min", 26), ("min", 26),
                            ("min", 26)])
    assert _ref_path(tmp_path) != ref
    c = TestClient(create_api(tmp_path))
    p = _pagella(c)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        ctx = pagella._context(cat, CAR, TRACK, 0, "it")
    assert len(ctx.corners) == 3
    want = next(k for k in ctx.corners if k.entry_pos <= 0.31 <= k.exit_pos)
    assert want.index == 1
    a = _stored(tmp_path)["min_speed"]
    assert [k["index"] for k in a["corners"]] == [1]
    assert a["corners"][0]["name"] == ctx.names[1]
    by = {x["defect"]: x for x in p["advice"]}
    assert by["min_speed"]["corners"] == [ctx.names[1]]
    # Misura la curva giusta: tre giri lenti li', nessuno sotto obiettivo.
    assert by["min_speed"]["status"] == ACTIVE
    assert by["min_speed"]["progress"]["hits"] == 0
    assert by["min_speed"]["progress"]["median"] > 120.0
    h = _howto(c, "min_speed")
    assert [f["corner"] for f in h["figures"]] == [1]
    assert ctx.names[1] in h["problem"]


def test_the_howto_follows_the_new_reference_before_the_pagella_does(tmp_path):
    """Il «Come si fa» e' sola lettura: se si apre prima della Pagella dopo un
    cambio di riferimento, rimappa lui le curve del consiglio (senza scrivere)."""
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    _store(tmp_path, {**asdict(Advice(
        defect="min_speed", corners=[AdviceCorner(0, "x", 0.31, 212.5)],
        baseline=212.5, target=120.0, status=ACTIVE,
        accepted_utc="2026-10-20T10:30:00+00:00")),
        "reference_path": _ref_path(tmp_path)})
    _session(tmp_path, 11, [("extra_ref", 0), ("min", 26), ("min", 26)])
    h = _howto(TestClient(create_api(tmp_path)), "min_speed")
    assert [f["corner"] for f in h["figures"]] == [1]
    assert _stored(tmp_path)["min_speed"]["corners"][0]["index"] == 0


def test_an_old_accepted_plan_becomes_the_active_advice(tmp_path):
    c = _two_sessions(tmp_path)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        # Accettato dopo l'ultima sessione: nessun giro lo ha ancora misurato.
        cat.save_plan(CAR, TRACK, "2026-10-20T12:00:00+00:00", [{
            "corner_index": 0, "name": "x", "category": "carry_speed",
            "what": "w", "fix": "f", "baseline_ms": 300.0, "target_ms": 150.0,
            "laps_seen": 4}])
    p = _pagella(c)
    assert p["advice"][0]["defect"] == "min_speed"
    assert p["advice"][0]["status"] == ACTIVE


# --- il «come si fa» --------------------------------------------------------

def _howto(c, defect, lang="it"):
    r = c.get("/api/howto", params={"car": CAR, "track": TRACK, "defect": defect,
                                    "index": 0, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


def test_howto_is_built_on_the_drivers_laps(tmp_path):
    c = _two_sessions(tmp_path)
    p = _pagella(c)
    corner = p["advice"][0]["corners"][0]
    h = _howto(c, "min_speed")
    assert h["name"] == defect_name("min_speed", "it")
    assert corner in h["problem"]
    assert h["howto"]["drill"] and h["howto"]["laps"] >= 1
    paths = {r["path"] for r in _rows(tmp_path)}
    f = h["figures"][0]
    assert f["typical_path"] in paths and f["best_path"] in paths
    assert f["best_path"] == _ref_path(tmp_path)
    assert f["name"] == corner and f["entry_pos"] < f["exit_pos"]
    assert h["progress"] == []
    assert h["reference_lap"]["lap_time"]


def test_the_typical_lap_is_the_one_closest_to_the_median(tmp_path):
    # Tre giri lenti in curva 0: 10, 26 e 40 km/h. La mediana e' quello da 26.
    _session(tmp_path, 10, [(None, 0), ("min", 10), ("min", 26), ("min", 40)])
    c = TestClient(create_api(tmp_path))
    f = _howto(c, "min_speed")["figures"][0]
    rows = sorted(_rows(tmp_path), key=lambda r: r["lap_time_ms"])
    assert f["typical_path"] == rows[2]["path"]


def _late_ref_session(tmp_path):
    _session(tmp_path, 10, [("late_ref", 0), ("min", 10), ("min_mid", 20),
                            ("min", 26)])
    return TestClient(create_api(tmp_path))


def _onset_on_ref_line(path, ref_path):
    """Il punto del foglio frenate, in metri sulla linea del riferimento."""
    ref = load_lap(ref_path)
    corner = detect_corners(ref.samples)[0]
    bp = brake_points_of_lap(load_lap(path), [corner])[0]
    return path_length(line_points(ref), 0.0, bp.onset_pos)


def test_howto_brake_points_use_the_braking_sheet_measure(tmp_path):
    c = _late_ref_session(tmp_path)
    f = _howto(c, "brake_early")["figures"][0]
    ref = _ref_path(tmp_path)
    assert f["best_path"] == ref and f["typical_path"] != ref
    bp = f["brake_points_m"]
    # Il solito stacca prima del migliore, ed entrambi si misurano sullo
    # stesso righello: la linea del riferimento.
    assert bp["typical"] < bp["best"]
    assert bp["typical"] == round(_onset_on_ref_line(f["typical_path"], ref))
    assert bp["best"] == round(_onset_on_ref_line(ref, ref))
    own = load_lap(f["typical_path"])
    corner = detect_corners(load_lap(ref).samples)[0]
    own_ruler = path_length(line_points(own), 0.0,
                            brake_points_of_lap(own, [corner])[0].onset_pos)
    assert round(own_ruler) != bp["typical"]     # il righello conta


def test_howto_brake_early_says_the_mean_metres_before(tmp_path):
    c = _late_ref_session(tmp_path)
    ref = _ref_path(tmp_path)
    best = _onset_on_ref_line(ref, ref)
    laps = [r["path"] for r in _rows(tmp_path) if r["path"] != ref]
    offs = [_onset_on_ref_line(p, ref) - best for p in laps]
    mean = sum(offs) / len(offs)
    assert mean < 0
    assert len({round(o) for o in offs}) > 1       # un giro solo non basterebbe
    text = _howto(c, "brake_early")["problem"]
    assert f"in media {round(abs(mean))} metri prima" in text, text


def test_howto_progress_after_following(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED)
    _store(tmp_path, {**asdict(Advice(
        defect="min_speed", corners=[AdviceCorner(0, "x", 0.31, 212.5)],
        baseline=212.5, target=120.0, status=ACTIVE,
        accepted_utc="2026-10-20T10:30:00+00:00")),
        "reference_path": _ref_path(tmp_path)})
    _session(tmp_path, 11, [("min", 26), ("min", 26)])
    _session(tmp_path, 12, [("min", 26), ("thr", 20)])
    h = _howto(TestClient(create_api(tmp_path)), "min_speed")
    assert len(h["progress"]) == 2
    assert h["progress"][0] > h["progress"][1] > 0


def test_a_lap_whose_clock_does_not_cover_it_is_never_the_reference(tmp_path):
    _session(tmp_path, 10, [("skewed_ref", 0), (None, 0)] + _MIXED)
    p = _pagella(TestClient(create_api(tmp_path)))
    assert p["excluded"] is None
    assert p["reference"]["lap_time"] == "1:40.000"


def test_a_lap_whose_clock_does_not_cover_it_is_not_replayed(tmp_path):
    _session(tmp_path, 10, [(None, 0)] + _MIXED + [("skewed_min", 0)])
    p = _pagella(TestClient(create_api(tmp_path)))
    assert p["session"]["valid"] == 6
    assert all(d["laps"] == 4 for d in p["defects"])


def test_a_session_holding_only_the_reference_says_so(tmp_path):
    _session(tmp_path, 10, _MIXED)
    _put(tmp_path, "2026-10-20T11:00:00+00:00")
    c = TestClient(create_api(tmp_path))
    p = _pagella(c)
    assert p["excluded"] == "reference_session"
    assert "riferimento" in p["verdict"] and "altro giro valido" not in p["verdict"]


def test_reaching_by_hand_does_not_quote_a_measure(tmp_path):
    c = _two_sessions(tmp_path)
    _advice(c, "min_speed", "follow")
    _advice(c, "min_speed", "reached")
    v = _pagella(c)["verdict"]
    assert defect_name("min_speed", "it") in v
    assert "giri su" not in v and "dichiarato" in v


def test_an_index_out_of_range_is_404(tmp_path):
    c = _two_sessions(tmp_path)
    for i in (2, -1):
        r = c.get("/api/pagella", params={"car": CAR, "track": TRACK, "index": i})
        assert r.status_code == 404
        r = c.get("/api/howto", params={"car": CAR, "track": TRACK,
                                        "defect": "min_speed", "index": i})
        assert r.status_code == 404
    r = c.post("/api/advice", json={"car": CAR, "track": TRACK, "defect": "min_speed",
                                    "action": "follow", "index": 5})
    assert r.status_code == 404
    r = c.post("/api/advice", json={"car": CAR, "track": TRACK, "defect": "min_speed",
                                    "action": "follow", "index": "x"})
    assert r.status_code == 422


def test_howto_of_an_unknown_defect_is_404(tmp_path):
    c = _two_sessions(tmp_path)
    r = c.get("/api/howto", params={"car": CAR, "track": TRACK, "defect": "x"})
    assert r.status_code == 404


def test_howto_without_data_still_explains(tmp_path):
    _put(tmp_path, "2026-10-20T10:00:00+00:00")
    h = _howto(TestClient(create_api(tmp_path)), "lift")
    assert h["howto"]["what"] and h["problem"] is None and h["figures"] == []


def test_howto_carries_the_glossary_of_its_defect(tmp_path):
    _put(tmp_path, "2026-10-20T10:00:00+00:00")
    c = TestClient(create_api(tmp_path))
    h = _howto(c, "brake_early")
    assert {"term": "Punto di frenata",
            "definition": "Il punto della pista in cui il tuo piede tocca il freno "
                          "arrivando in curva."} in h["glossary"]
    en = _howto(c, "brake_early", lang="en")
    assert "Braking point" in [g["term"] for g in en["glossary"]]


def test_howto_carries_the_target_of_its_advice(tmp_path):
    """L'esercizio dice l'obiettivo in numeri (spec, «La vista Come si fa»):
    lo stesso della riga del piano, nella stessa unita'."""
    c = _two_sessions(tmp_path)
    a = next(x for x in _pagella(c)["advice"] if x["defect"] == "min_speed")
    h = _howto(c, "min_speed")
    assert h["target"] == a["target"] and h["target"] > 0
    assert h["unit"] == a["unit"] == "ms"


def test_howto_without_advice_has_no_target(tmp_path):
    _put(tmp_path, "2026-10-20T10:00:00+00:00")
    h = _howto(TestClient(create_api(tmp_path)), "coasting")
    assert h["target"] is None and h["unit"] == "s"


# --- la storia dei difetti (scheda Andamento) -------------------------------

def _history(c, lang="it"):
    r = c.get("/api/defect-history", params={"car": CAR, "track": TRACK, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_history_agrees_with_the_pagella_series(tmp_path):
    # Due sessioni con numeri diversi: con due sessioni uguali una serie
    # rovesciata sarebbe la stessa serie.
    c = _two_sessions(tmp_path, second=[("min", 40), ("thr", 20), ("min", 40), ("thr", 20)])
    h, p = _history(c), _pagella(c)
    assert h["excluded"] is None
    assert h["reference"]["lap_time"] == p["reference"]["lap_time"]
    assert [s["started_utc"][:13] for s in h["sessions"]] == \
        ["2026-10-20T10", "2026-10-20T11"]
    assert [s["valid"] for s in h["sessions"]] == [5, 4]
    by = {d["key"]: d for d in h["defects"]}
    assert [d["key"] for d in h["defects"]] == [d["key"] for d in p["defects"]]
    for d in p["defects"]:
        assert by[d["key"]]["values"] == d["series"]
        assert len(by[d["key"]]["values"]) == 2
        assert by[d["key"]]["trend"] == d["trend"]
        assert by[d["key"]]["name"] == d["name"] and by[d["key"]]["unit"] == d["unit"]
    assert by["min_speed"]["values"][0] < by["min_speed"]["values"][1]


def test_a_defect_that_was_main_once_stays_in_the_history(tmp_path):
    """Il gas tardi sparisce nella seconda sessione: in Pagella non c'e' piu',
    nella storia si' — vederlo andare a zero e' proprio quello che il pilota
    vuole vedere."""
    c = _two_sessions(tmp_path, second=[("min", 40), ("min", 40)])
    h = _history(c)
    assert [d["key"] for d in h["defects"]] == ["min_speed", "throttle_late"]
    thr = h["defects"][1]
    assert thr["values"][0] > 0 and thr["values"][1] == 0.0
    assert thr["trend"] == "down"
    assert h["defects"][0]["trend"] == "up"
    # Principale oggi il primo, non piu' il secondo.
    assert h["defects"][0]["main"] is True and thr["main"] is False
    assert h["skipped"] is None


def test_a_lone_wet_session_stays_out_of_a_dry_history(tmp_path):
    _session(tmp_path, 9, [(None, 0)] + _MIXED, compound="dry_compound")
    _session(tmp_path, 10, [(None, 0)] + _MIXED, compound="wet_compound")
    _session(tmp_path, 11, _MIXED, compound="dry_compound")
    h = _history(TestClient(create_api(tmp_path)))
    assert h["excluded"] is None
    assert [s["started_utc"][:13] for s in h["sessions"]] == \
        ["2026-10-20T09", "2026-10-20T11"]
    assert all(len(d["values"]) == 2 for d in h["defects"])


def test_the_latest_session_alone_in_the_wet_does_not_hide_the_dry_history(tmp_path):
    """La piu' recente e' l'unica sul bagnato: la Pagella la lascia fuori
    dall'andamento, e la storia mostra l'asciutto invece di niente."""
    _session(tmp_path, 10, [(None, 0)] + _MIXED, compound="dry_compound")
    _session(tmp_path, 11, [(None, 0)] + _MIXED, compound="wet_compound")
    h = _history(TestClient(create_api(tmp_path)))
    assert h["excluded"] is None
    assert [s["started_utc"][:13] for s in h["sessions"]] == ["2026-10-20T10"]
    # La pagina dice perche' l'ultima sessione non c'e'.
    assert h["skipped"] == "wet"


def test_the_history_skips_a_latest_session_it_cannot_measure(tmp_path):
    # Una sessione fatta del solo riferimento, e una senza giri validi.
    _session(tmp_path, 10, _MIXED)
    _put(tmp_path, "2026-10-20T11:00:00+00:00")
    _put(tmp_path, "2026-10-20T12:00:00+00:00", "min", 26, valid=False)
    h = _history(TestClient(create_api(tmp_path)))
    assert h["excluded"] is None
    assert [s["started_utc"][:13] for s in h["sessions"]] == ["2026-10-20T10"]
    # Saltate per mancanza di giri, non per la gomma: nessuna frase.
    assert h["skipped"] is None


def test_the_history_of_a_single_lap_has_no_reference(tmp_path):
    _put(tmp_path, "2026-10-20T10:00:00+00:00")
    h = _history(TestClient(create_api(tmp_path)))
    assert h["excluded"] == "no_reference"
    assert h["sessions"] == [] and h["defects"] == []


def test_the_history_without_laps(tmp_path):
    h = _history(TestClient(create_api(tmp_path)))
    assert h["excluded"] == "no_laps"
    assert h["sessions"] == [] and h["defects"] == [] and h["reference"] is None


def test_the_history_stops_at_twenty_sessions(tmp_path):
    _put(tmp_path, "2026-10-20T00:00:00+00:00")
    for h in range(1, 23):          # ventidue sessioni da due giri lenti
        _session(tmp_path, h, [("min", 26), ("min", 26)])
    h = _history(TestClient(create_api(tmp_path)))
    assert len(h["sessions"]) == 20
    assert h["sessions"][-1]["started_utc"][:13] == "2026-10-20T22"
    assert len(h["defects"][0]["values"]) == 20


def test_the_history_names_follow_the_language(tmp_path):
    h = _history(_two_sessions(tmp_path), lang="en")
    assert h["defects"][0]["name"] == defect_name(h["defects"][0]["key"], "en")
