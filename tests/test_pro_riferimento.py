"""Il giro di riferimento PRO, rivisto il 27/10.

Tre difetti, tutti dello stesso tipo: il giro PRO trattato come uno dei tuoi.

* Correva nell'elezione del riferimento come un giro tuo. Importato sempre
  ``clean = 1``, uno più lento batteva un tuo giro più veloce mai giudicato. Uno
  più veloce perdeva contro qualunque tuo giro fatto nelle condizioni di oggi.
* Nel report diventava «il tuo miglior giro», costruiva il giro ideale con i
  suoi settori, entrava nella sessione di oggi e apriva la pagina.
* L'import non diceva cosa succedeva dopo, e lo stesso file importato due
  volte diventava due giri.
"""
from fastapi.testclient import TestClient

from accoach.api import _default_review, _own_valid, create_api
from accoach.recording.pro import (DUPLICATE, FIRST, REFERENCE, SLOWER,
                                   describe, import_pro)
from accoach.recording.storage import (_find_reference_by_scan,
                                       find_reference_lap, load_lap, save_lap)

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _mine(laps_dir, ms, day="2026-07-20", **kw):
    lap = synth.build_lap()
    synth.retime(lap, ms)
    lap.recorded_utc = f"{day}T09:00:00+00:00"
    for k, v in kw.items():
        setattr(lap, k, v)
    return save_lap(lap, laps_dir)


def _pro_file(tmp_path, ms, name="pro"):
    """Un file di giro come lo riceve il pilota, fuori dalla cartella dei giri."""
    lap = synth.build_lap()
    synth.retime(lap, ms)
    lap.recorded_utc = "2026-01-01T09:00:00+00:00"
    out = tmp_path / name
    out.mkdir(exist_ok=True)
    return save_lap(lap, out)


# --- l'elezione ------------------------------------------------------------------

def test_a_slower_pro_lap_does_not_beat_an_unjudged_faster_lap_of_yours(tmp_path):
    laps = tmp_path / "laps"
    _mine(laps, 99_000, clean=None)            # giro di AC o vecchio: mai giudicato
    import_pro(_pro_file(tmp_path, 105_000), laps)
    ref = find_reference_lap(CAR, TRACK, laps)
    assert ref is not None and ref.lap_time_ms == 99_000 and ref.source != "pro"


def test_the_scan_without_catalog_follows_the_same_rule(tmp_path):
    laps = tmp_path / "laps"
    _mine(laps, 99_000, clean=None)
    import_pro(_pro_file(tmp_path, 105_000), laps)
    assert _find_reference_by_scan(CAR, TRACK, laps).lap_time_ms == 99_000
    import_pro(_pro_file(tmp_path, 95_000, "pro2"), laps)
    assert _find_reference_by_scan(CAR, TRACK, laps).lap_time_ms == 95_000


def test_a_faster_pro_lap_wins_even_against_a_lap_in_todays_conditions(tmp_path):
    """La guida promette che da quel momento il coach ti misura sul giro PRO."""
    laps = tmp_path / "laps"
    _mine(laps, 101_000, road_temp=31.0, tyre_compound="dry_compound")
    src = _pro_file(tmp_path, 99_000)
    pro = load_lap(src)
    pro.road_temp = 14.0                       # girato con un'altra pista
    save_lap(pro, src.parent)
    import_pro(src, laps)
    ref = find_reference_lap(CAR, TRACK, laps, road_temp=31.0,
                             compound="dry_compound")
    assert ref.source == "pro" and ref.lap_time_ms == 99_000


def test_your_conditions_still_pick_among_your_laps_when_pro_is_slower(tmp_path):
    laps = tmp_path / "laps"
    _mine(laps, 99_000, road_temp=14.0, clean=True)
    _mine(laps, 100_500, day="2026-07-21", road_temp=31.0, clean=True)
    import_pro(_pro_file(tmp_path, 102_000), laps)
    ref = find_reference_lap(CAR, TRACK, laps, road_temp=31.0)
    assert ref.lap_time_ms == 100_500 and ref.source != "pro"


# --- l'import dice cosa succede ---------------------------------------------------

def test_the_import_says_whether_the_pro_lap_takes_over(tmp_path):
    laps = tmp_path / "laps"
    assert import_pro(_pro_file(tmp_path, 104_000, "a"), laps).status == FIRST
    _mine(laps, 100_000, clean=True)
    slower = import_pro(_pro_file(tmp_path, 101_000, "b"), laps)
    assert slower.status == SLOWER and slower.own_ms == 100_000
    assert import_pro(_pro_file(tmp_path, 98_000, "c"), laps).status == REFERENCE


def test_the_same_pro_lap_twice_is_imported_once(tmp_path):
    laps = tmp_path / "laps"
    src = _pro_file(tmp_path, 99_000)
    import_pro(src, laps)
    again = import_pro(src, laps)
    assert again.status == DUPLICATE
    assert len(list(laps.glob("*.lap.json.gz"))) == 1


def test_the_sentence_names_your_best_when_it_stays_the_reference(tmp_path):
    from accoach.i18n import t
    laps = tmp_path / "laps"
    _mine(laps, 100_000, clean=True)
    r = import_pro(_pro_file(tmp_path, 101_000), laps)
    msg = describe(r, lambda k: t(k, lang="it"))
    assert "1:40.000" in msg and "resta lui il riferimento" in msg


def test_a_broken_file_is_refused_with_a_reason(tmp_path):
    bad = tmp_path / "rotto.lap.json.gz"
    bad.write_bytes(b"non e' un giro")
    try:
        import_pro(bad, tmp_path / "laps")
    except Exception as exc:  # noqa: BLE001
        assert str(exc)
    else:
        raise AssertionError("un file rotto deve essere rifiutato")


# --- nel report il giro PRO non e' tuo -------------------------------------------

def _rows():
    return [
        {"path": "pro", "valid": 1, "lap_time_ms": 95_000, "source": "pro"},
        {"path": "mine", "valid": 1, "lap_time_ms": 100_000, "source": "own"},
    ]


def test_the_report_opens_on_your_latest_lap_not_on_the_import():
    assert _default_review(_rows()) == "mine"
    assert [r["path"] for r in _own_valid(_rows())] == ["mine"]


def test_with_only_a_pro_lap_the_report_still_opens():
    only = [_rows()[0]]
    assert _default_review(only) == "pro"
    assert [r["path"] for r in _own_valid(only)] == ["pro"]


def test_progress_counts_your_best_not_the_pro_lap(tmp_path):
    laps = tmp_path / "laps"
    _mine(laps, 100_000, clean=True)
    _mine(laps, 101_000, day="2026-07-21", clean=True)
    import_pro(_pro_file(tmp_path, 95_000), laps)
    data = TestClient(create_api(laps)).get(
        "/api/progress", params={"car": CAR, "track": TRACK}).json()
    assert len(data["laps"]) == 2
    levels = {lv["key"]: lv for lv in data["levels"]}
    assert "pro" in levels and levels["pro"]["gain_ms"] > 0   # non «raggiunto»


def test_the_home_shows_the_session_you_drove(tmp_path):
    from accoach.hub_home import load_home_data
    laps = tmp_path / "laps"
    _mine(laps, 100_000, clean=True)
    other = synth.build_lap()
    other.track = "spa"
    out = tmp_path / "pro"
    out.mkdir()
    import_pro(save_lap(other, out), laps)    # importato dopo, su un'altra pista
    home = load_home_data(laps)
    assert home.track == TRACK
