"""Il consiglio in corso: cosa le schede del report devono indicare.

Solo lettura del catalogo: nessun replay, nessun giro. I consigli si scrivono
direttamente con `save_advice`, come li scrive la Pagella quando si accetta.
"""
from fastapi.testclient import TestClient

from accoach import pagella
from accoach.api import create_api
from accoach.coaching.advice import ACTIVE, DROPPED, PROPOSED
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import _catalog_path

CAR, TRACK = "ferrari_488_gt3", "monza"


def _advice(defect, status, corners=()):
    return {"defect": defect, "status": status, "baseline": 0.3, "target": 0.1,
            "accepted_utc": "2026-10-20T10:00:00+00:00", "closed_utc": "",
            "corners": [{"index": i, "name": n, "apex_pos": p, "mean": 0.1}
                        for i, n, p in corners]}


def _cat(tmp_path):
    return LapCatalog(_catalog_path(tmp_path))


def test_no_advice_means_null(tmp_path):
    with _cat(tmp_path) as cat:
        assert pagella.build_active_advice(cat, CAR, TRACK, "it") == {"advice": None}


def test_only_the_active_one_is_returned(tmp_path):
    with _cat(tmp_path) as cat:
        cat.save_advice(CAR, TRACK, _advice("brake_early", PROPOSED, [(1, "Curva 1", .1)]))
        cat.save_advice(CAR, TRACK, _advice("throttle_late", ACTIVE, [(2, "Parabolica", .5)]))
        cat.save_advice(CAR, TRACK, _advice("lift", DROPPED, [(3, "Ascari", .7)]))
        it = pagella.build_active_advice(cat, CAR, TRACK, "it")["advice"]
        en = pagella.build_active_advice(cat, CAR, TRACK, "en")["advice"]
    assert it["defect"] == "throttle_late"
    assert it["name"] == "Gas tardi in uscita"
    assert en["name"] == "Late on the throttle"
    assert it["corners"] == [{"name": "Parabolica", "apex_pos": 0.5}]


def test_corners_carry_their_apex_and_skip_migrated_ones(tmp_path):
    with _cat(tmp_path) as cat:
        cat.save_advice(CAR, TRACK, _advice(
            "brake_early", ACTIVE, [(1, "Variante", 0.4321987), (2, "Vecchia", 0.0)]))
        out = pagella.build_active_advice(cat, CAR, TRACK, "it")["advice"]
    assert out["corners"] == [{"name": "Variante", "apex_pos": 0.4322}]


def test_other_car_or_track_sees_nothing(tmp_path):
    with _cat(tmp_path) as cat:
        cat.save_advice(CAR, TRACK, _advice("lift", ACTIVE, [(1, "Curva", .3)]))
        assert pagella.build_active_advice(cat, CAR, "spa", "it") == {"advice": None}
        assert pagella.build_active_advice(cat, "bmw_m4_gt3", TRACK, "it") == {"advice": None}
        assert pagella.build_active_advice(cat, CAR, TRACK, "it")["advice"] is not None


def test_endpoint_answers_null_on_a_catalog_without_advice(tmp_path):
    r = TestClient(create_api(tmp_path)).get(
        "/api/advice/active", params={"car": CAR, "track": TRACK, "lang": "it"})
    assert r.status_code == 200
    assert r.json() == {"advice": None}


def test_endpoint_returns_the_active_advice(tmp_path):
    with _cat(tmp_path) as cat:
        cat.save_advice(CAR, TRACK, _advice("lift", ACTIVE, [(1, "Curva", .3)]))
    r = TestClient(create_api(tmp_path)).get(
        "/api/advice/active", params={"car": CAR, "track": TRACK, "lang": "en"})
    assert r.json()["advice"]["name"] == "Lifting on the straight"


def test_the_corner_order_of_the_advice_is_kept(tmp_path):
    # la Pagella le ordina per costo: le schede nominano le curve in quell'ordine
    with _cat(tmp_path) as cat:
        cat.save_advice(CAR, TRACK, _advice(
            "brake_early", ACTIVE,
            [(5, "Tosa", 0.8), (1, "Variante", 0.2), (3, "Ascari", 0.55)]))
        out = pagella.build_active_advice(cat, CAR, TRACK, "it")["advice"]
    assert [c["name"] for c in out["corners"]] == ["Tosa", "Variante", "Ascari"]
