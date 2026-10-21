"""La roadmap dei consigli: uno alla volta, con un numero che si controlla."""
from __future__ import annotations

import pytest

from accoach.coaching.advice import (
    MAX_ADVICE, Advice, AdviceCorner, measure_advice, propose_advice, rebase)
from accoach.coaching.defects import DefectSummary, LapDefects
from accoach.recording.catalog import LapCatalog


def _s(key, corners, main=True, unit="ms", mean=None):
    return DefectSummary(key=key, mean=mean or sum(m for _, m in corners),
                         unit=unit, laps_with=5, laps=6, corners=corners,
                         main=main)


def _adv(defect="brake_early", status="proposed", baseline=180.0, target=120.0,
         corners=((4, 180.0),)):
    return Advice(defect=defect, status=status, baseline=baseline, target=target,
                  corners=[AdviceCorner(i, f"T{i}", 0.5, m) for i, m in corners])


def _lap(key, vals):
    return LapDefects(ms={key: sum(vals.values())}, corners={key: dict(vals)})


def test_only_main_defects_become_advice_and_at_most_three():
    sums = [_s("brake_early", [(1, 300.0)]),
            _s("brake_late", [(2, 250.0)], main=False),
            _s("over_brake", [(3, 240.0)]),
            _s("throttle_late", [(4, 230.0)]),
            _s("min_speed", [(5, 220.0)])]
    out = propose_advice(sums, [], {1: "Curva 1"}, {1: 0.25})
    assert [a.defect for a in out] == ["brake_early", "over_brake", "throttle_late"]
    assert len(out) == MAX_ADVICE
    assert out[0].corners[0].name == "Curva 1"
    assert out[0].corners[0].apex_pos == 0.25


def test_only_the_first_three_corners_over_half_the_threshold_count():
    s = _s("brake_early", [(1, 300.0), (2, 200.0), (3, 100.0), (4, 80.0),
                           (5, 59.0)])
    (a,) = propose_advice([s], [], {}, {})
    assert [c.index for c in a.corners] == [1, 2, 3]
    assert a.baseline == 600.0


def test_a_declined_defect_is_not_proposed_again():
    sums = [_s("brake_early", [(1, 300.0)]), _s("over_brake", [(3, 240.0)]),
            _s("min_speed", [(5, 220.0)])]
    stored = [_adv("brake_early", "declined"), _adv("over_brake", "reached")]
    out = propose_advice(sums, stored, {}, {})
    assert [a.defect for a in out] == ["min_speed"]


def test_the_active_one_comes_first_and_only_one_can_be_active():
    sums = [_s("brake_early", [(1, 300.0)]), _s("over_brake", [(3, 240.0)])]
    stored = [_adv("over_brake", "active")]
    out = propose_advice(sums, stored, {}, {})
    assert [(a.defect, a.status) for a in out] == [
        ("over_brake", "active"), ("brake_early", "proposed")]
    with pytest.raises(ValueError):
        propose_advice(sums, [_adv("over_brake", "active"),
                              _adv("brake_early", "active")], {}, {})


def test_target_is_half_the_baseline_never_under_the_threshold():
    (a,) = propose_advice([_s("brake_early", [(1, 180.0)])], [], {}, {})
    assert a.target == 120.0
    (b,) = propose_advice([_s("brake_early", [(1, 400.0)])], [], {}, {})
    assert b.target == 200.0


def test_coasting_uses_seconds_and_the_lap_total():
    s = _s("coasting", [], unit="s", mean=1.0)
    (a,) = propose_advice([s], [], {}, {})
    assert (a.baseline, a.target, a.corners) == (1.0, 0.5, [])
    (b,) = propose_advice([_s("coasting", [], unit="s", mean=0.5)], [], {}, {})
    assert b.target == 0.4
    laps = [LapDefects(coast_s=v) for v in (0.3, 0.9, 0.2)]
    assert measure_advice(a, laps).hits == 2


def test_reached_needs_three_laps_and_half_of_them_under_target():
    a = _adv()
    under, over = {4: 100.0}, {4: 200.0}
    p = measure_advice(a, [_lap("brake_early", under)] * 2)
    assert (p.laps, p.hits, p.done) == (2, 2, False)
    p = measure_advice(a, [_lap("brake_early", x) for x in (under, under, over)])
    assert (p.hits, p.needed, p.done) == (2, 2, True)
    p = measure_advice(a, [_lap("brake_early", x)
                           for x in (under, over, over, over)])
    assert (p.hits, p.needed, p.done) == (1, 2, False)


def test_progress_sums_only_the_corners_of_the_advice():
    a = _adv(corners=((4, 100.0), (5, 80.0)))
    p = measure_advice(a, [_lap("brake_early", {4: 60.0, 5: 50.0, 9: 900.0})])
    assert p.median == 110.0
    assert measure_advice(a, []).median == 0.0


def test_rebase_remeasures_the_same_corners_against_the_new_history():
    a = _adv(corners=((4, 180.0), (5, 100.0)), baseline=280.0, target=140.0)
    s = _s("brake_early", [(5, 60.0), (4, 400.0), (7, 999.0)])
    r = rebase(a, s)
    assert [c.index for c in r.corners] == [4, 5]
    assert (r.baseline, r.target) == (460.0, 230.0)
    assert r.status == a.status and a.baseline == 280.0


def test_advice_round_trips_through_the_catalog(tmp_path):
    from dataclasses import asdict
    d = asdict(_adv(status="active"))
    d["accepted_utc"] = "2026-10-01T10:00:00Z"
    d["reference_path"] = "laps/ref.json"
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_advice("Ferrari 296", "Monza", d)
        assert cat.load_advice("Ferrari 296", "Monza") == [d]
        d2 = dict(d, status="reached", closed_utc="2026-10-02T10:00:00Z")
        cat.save_advice("Ferrari 296", "Monza", d2)
        assert cat.load_advice("Ferrari 296", "Monza") == [d2]
        assert cat.load_advice("Ferrari 296", "Spa") == []


def test_an_old_accepted_plan_becomes_the_active_advice(tmp_path):
    goal = {"corner_index": 4, "name": "Parabolica", "category": "brake_later",
            "what": "x", "fix": "y", "baseline_ms": 200.0, "target_ms": 120.0,
            "laps_seen": 8}
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_plan("Ferrari 296", "Monza", "2026-09-01T09:00:00Z", [goal])
        cat.migrate_plan_to_advice("Ferrari 296", "Monza")
        (a,) = cat.load_advice("Ferrari 296", "Monza")
        assert a["defect"] == "brake_early" and a["status"] == "active"
        assert a["accepted_utc"] == "2026-09-01T09:00:00Z"
        assert a["baseline"] == 200.0 and a["target"] == 120.0
        assert a["corners"] == [{"index": 4, "name": "Parabolica",
                                 "apex_pos": 0.0, "mean": 200.0}]
        assert cat.load_plan("Ferrari 296", "Monza") is None
        cat.migrate_plan_to_advice("Ferrari 296", "Monza")   # senza piano: nulla
        assert len(cat.load_advice("Ferrari 296", "Monza")) == 1
