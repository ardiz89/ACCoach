"""Lo storico della Pagella: un riferimento solo e le sessioni rigiocate.

Giri veri salvati in `tmp_path` e letti dal catalogo, come fa il resto della
suite: i test controllano la scelta del riferimento e la cache, non la
matematica dei difetti (quella e' in test_defects).
"""
import pytest

from accoach import pagella
from accoach.comparison import Reference
from accoach.pagella import history_reference, is_wet_row, replay
from accoach.recording import load_lap
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import _catalog_path, save_lap
from accoach.sessions import group_sessions
from accoach.track import detect_corners

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


@pytest.fixture(autouse=True)
def _cache_vuota():
    pagella.clear_cache()
    yield
    pagella.clear_cache()


def _put(tmp_path, ms, stamp, slow=None, amt=0, **kw):
    lap = synth.build_lap(slow_corner=slow, amt=amt, **kw)
    synth.retime(lap, ms)
    lap.lap_time_ms = ms
    lap.recorded_utc = stamp
    save_lap(lap, tmp_path)


def _rows(tmp_path):
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        return cat.laps_for(CAR, TRACK)


def _two_sessions(tmp_path):
    # sessione A (30 minuti prima) e sessione B
    _put(tmp_path, 101_000, "2026-10-20T10:00:00+00:00", clean=True)
    _put(tmp_path, 100_500, "2026-10-20T10:02:00+00:00", clean=True)
    _put(tmp_path, 102_000, "2026-10-20T10:04:00+00:00", slow=0, amt=20, clean=True)
    _put(tmp_path, 100_000, "2026-10-20T10:34:00+00:00", clean=True)
    _put(tmp_path, 103_000, "2026-10-20T10:36:00+00:00", slow=1, amt=20, clean=True)
    _put(tmp_path, 104_000, "2026-10-20T10:38:00+00:00", slow=0, amt=30, clean=True)
    return _rows(tmp_path)


# --- is_wet_row ---------------------------------------------------------------

def test_is_wet_row_mirrors_the_lap_rule():
    assert is_wet_row({"tyre_compound": "wet_compound"}) is True
    assert is_wet_row({"tyre_compound": "Rain"}) is True
    assert is_wet_row({"tyre_compound": "dry_compound"}) is False
    assert is_wet_row({"tyre_compound": "  "}) is None
    assert is_wet_row({}) is None
    assert is_wet_row({"tyre_compound": None}) is None


# --- history_reference --------------------------------------------------------

def test_reference_is_the_fastest_clean_valid_lap():
    rows = [
        {"path": "a", "lap_time_ms": 101_000, "valid": True, "clean": True},
        {"path": "b", "lap_time_ms": 99_000, "valid": True, "clean": False},
        {"path": "c", "lap_time_ms": 98_000, "valid": False, "clean": True},
        {"path": "d", "lap_time_ms": 0, "valid": True, "clean": True},
        {"path": "e", "lap_time_ms": 100_000, "valid": True, "clean": None},
    ]
    assert history_reference(rows, wet=False)["path"] == "e"


def test_reference_follows_the_wet_flag():
    rows = [
        {"path": "w", "lap_time_ms": 90_000, "valid": True, "clean": True,
         "tyre_compound": "wet_compound"},
        {"path": "d", "lap_time_ms": 100_000, "valid": True, "clean": True,
         "tyre_compound": "dry_compound"},
        {"path": "n", "lap_time_ms": 101_000, "valid": True, "clean": True,
         "tyre_compound": ""},
    ]
    assert history_reference(rows, wet=False)["path"] == "d"
    assert history_reference(rows, wet=True)["path"] == "w"


def test_missing_compound_counts_as_dry_and_none_when_nothing_fits():
    rows = [{"path": "n", "lap_time_ms": 101_000, "valid": True, "clean": True}]
    assert history_reference(rows, wet=False)["path"] == "n"
    assert history_reference(rows, wet=True) is None
    assert history_reference([], wet=False) is None


def test_reference_from_the_real_catalog(tmp_path):
    rows = _two_sessions(tmp_path)
    assert history_reference(rows, wet=False)["lap_time_ms"] == 100_000


# --- replay -------------------------------------------------------------------

def _setup(tmp_path):
    rows = _two_sessions(tmp_path)
    ref_row = history_reference(rows, wet=False)
    ref_lap = load_lap(ref_row["path"])
    return rows, ref_row, Reference(ref_lap), detect_corners(ref_lap.samples)


def test_replay_skips_the_reference_itself(tmp_path):
    rows, ref_row, ref, corners = _setup(tmp_path)
    sessions = group_sessions(rows)
    assert len(sessions) == 2
    newest, oldest = sessions
    r_new = replay(newest, ref_row, corners, ref, {})
    assert len(newest.valid_laps) == 3 and len(r_new.laps) == 2
    assert len(r_new.errors) == 2
    r_old = replay(oldest, ref_row, corners, ref, {})
    assert len(r_old.laps) == 3 and r_old.wet is False


def test_mean_gap_is_against_the_reference_time(tmp_path):
    rows, ref_row, ref, corners = _setup(tmp_path)
    old = group_sessions(rows)[1]
    r = replay(old, ref_row, corners, ref, {})
    assert r.mean_gap_ms == pytest.approx((1000 + 500 + 2000) / 3)


def test_session_with_only_the_reference_has_no_gap(tmp_path):
    rows, ref_row, ref, corners = _setup(tmp_path)
    only = group_sessions([ref_row])[0]
    r = replay(only, ref_row, corners, ref, {})
    assert r.laps == [] and r.mean_gap_ms is None


def test_second_replay_does_not_debrief_again(tmp_path, monkeypatch):
    rows, ref_row, ref, corners = _setup(tmp_path)
    old = group_sessions(rows)[1]
    calls = []
    real = pagella.build_lap_debrief
    monkeypatch.setattr(pagella, "build_lap_debrief",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    first = replay(old, ref_row, corners, ref, pagella._CACHE)
    n = len(calls)
    assert n == 3
    second = replay(old, ref_row, corners, ref, pagella._CACHE)
    assert len(calls) == n
    assert [l.total_gap_ms for l in second.laps] == [l.total_gap_ms for l in first.laps]


def test_cache_is_keyed_by_reference_too(tmp_path, monkeypatch):
    rows, ref_row, ref, corners = _setup(tmp_path)
    old = group_sessions(rows)[1]
    replay(old, ref_row, corners, ref, pagella._CACHE)
    assert all(k[0] == ref_row["path"] for k in pagella._CACHE)
    other = dict(ref_row, path="altro")
    calls = []
    real = pagella.build_lap_debrief
    monkeypatch.setattr(pagella, "build_lap_debrief",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    replay(old, other, corners, ref, pagella._CACHE)
    assert len(calls) == 3


def test_unreadable_lap_is_skipped_not_raised(tmp_path):
    rows, ref_row, ref, corners = _setup(tmp_path)
    old = group_sessions(rows)[1]
    old.laps.append(dict(old.laps[0], path=str(tmp_path / "non-esiste.json.gz"),
                         recorded_utc="2026-10-20T10:05:00+00:00"))
    r = replay(old, ref_row, corners, ref, {})
    assert len(r.laps) == 3 and len(r.errors) == 3


def test_clear_cache_empties_it(tmp_path):
    rows, ref_row, ref, corners = _setup(tmp_path)
    replay(group_sessions(rows)[1], ref_row, corners, ref)
    assert pagella._CACHE
    pagella.clear_cache()
    assert not pagella._CACHE


# --- SessionReplay.wet: il voto fra i giri che dicono la mescola ---------------

def _wet_vote(tmp_path, compounds):
    """Sessione di giri con le mescole date, rigiocata contro un riferimento
    asciutto fuori dalla sessione (un'ora prima)."""
    _put(tmp_path, 100_000, "2026-10-20T08:00:00+00:00", clean=True,
         compound="dry_compound")
    for i, c in enumerate(compounds):
        _put(tmp_path, 101_000 + i * 100, f"2026-10-20T10:0{i}:00+00:00",
             clean=True, compound=c)
    rows = _rows(tmp_path)
    ref_row = history_reference(rows, wet=False)
    ref_lap = load_lap(ref_row["path"])
    session = group_sessions(rows)[0]
    assert len(session.valid_laps) == len(compounds)
    return replay(session, ref_row, detect_corners(ref_lap.samples),
                  Reference(ref_lap), {})


def test_wet_session_is_decided_by_the_majority(tmp_path):
    assert _wet_vote(tmp_path, ["wet_compound", "wet_compound", "dry_compound"]).wet is True


def test_dry_majority_is_dry(tmp_path):
    assert _wet_vote(tmp_path, ["wet_compound", "dry_compound", "dry_compound"]).wet is False


def test_unknown_compound_does_not_vote(tmp_path):
    assert _wet_vote(tmp_path, ["wet_compound", "", ""]).wet is True


def test_a_tie_is_dry(tmp_path):
    assert _wet_vote(tmp_path, ["wet_compound", "dry_compound"]).wet is False
