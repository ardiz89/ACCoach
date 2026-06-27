"""storage: save/load laps and find the reference (fastest valid) lap."""
from accoach.recording import storage
from accoach.recording.storage import (
    describe_lap,
    find_reference_lap,
    list_lap_files,
    load_lap,
    save_lap,
)

import synth


def test_save_then_load_roundtrip(tmp_path):
    lap = synth.build_lap(n=40)
    path = save_lap(lap, tmp_path)
    assert path.exists() and path.name.endswith(".lap.json.gz")
    back = load_lap(path)
    assert back.lap_time_ms == lap.lap_time_ms
    assert len(back.samples) == len(lap.samples)


def test_save_sets_recorded_utc_and_sortable_name(tmp_path):
    lap = synth.build_lap(n=5)
    assert lap.recorded_utc == ""
    path = save_lap(lap, tmp_path)
    assert lap.recorded_utc != ""               # filled in on save
    # Slugged track + car appear in the filename.
    assert path.name.startswith("monza__ferrari-488-gt3__")


def test_list_lap_files(tmp_path):
    assert list_lap_files(tmp_path) == []
    # Distinct timestamps so the two files don't collide on name (same second).
    a, b = synth.build_lap(n=5), synth.build_lap(n=5)
    a.recorded_utc = "2026-06-20T18:00:00+00:00"
    b.recorded_utc = "2026-06-20T18:00:01+00:00"
    save_lap(a, tmp_path)
    save_lap(b, tmp_path)
    assert len(list_lap_files(tmp_path)) == 2


def test_find_reference_picks_fastest_valid(tmp_path):
    slow = synth.build_lap(slow_corner=0, amt=30, n=60)    # ~100582 ms
    fast = synth.build_lap(n=60)                           # 100000 ms
    save_lap(slow, tmp_path)
    save_lap(fast, tmp_path)
    ref = find_reference_lap("ferrari_488_gt3", "monza", tmp_path)
    assert ref is not None
    assert ref.lap_time_ms == fast.lap_time_ms


def test_find_reference_ignores_invalid_and_other_combos(tmp_path):
    save_lap(synth.build_lap(n=40, valid=False), tmp_path)              # invalid
    save_lap(synth.build_lap(n=40, car="other_car"), tmp_path)         # other car
    assert find_reference_lap("ferrari_488_gt3", "monza", tmp_path) is None


def test_find_reference_none_for_empty_dir(tmp_path):
    assert find_reference_lap("x", "y", tmp_path) is None


def test_find_reference_excludes_dirty_lap(tmp_path):
    # A fast but dirty lap must never beat a slower clean one as the reference.
    dirty = synth.build_lap(n=40, clean=False)                       # fast, dirty
    dirty.recorded_utc = "2026-06-20T18:00:00+00:00"
    clean = synth.build_lap(slow_corner=0, amt=30, n=40, clean=True)   # slower, clean
    clean.recorded_utc = "2026-06-20T18:00:01+00:00"
    save_lap(dirty, tmp_path)
    save_lap(clean, tmp_path)
    ref = find_reference_lap("ferrari_488_gt3", "monza", tmp_path)
    assert ref is not None and ref.clean is True


def test_find_reference_none_when_only_dirty(tmp_path):
    save_lap(synth.build_lap(n=40, clean=False), tmp_path)
    assert find_reference_lap("ferrari_488_gt3", "monza", tmp_path) is None


def test_scan_fallback_excludes_dirty_and_prefers_clean(tmp_path):
    from accoach.recording.storage import _find_reference_by_scan
    dirty = synth.build_lap(n=40, clean=False)
    dirty.recorded_utc = "2026-06-20T18:00:00+00:00"
    clean = synth.build_lap(slow_corner=0, amt=30, n=40, clean=True)
    clean.recorded_utc = "2026-06-20T18:00:01+00:00"
    save_lap(dirty, tmp_path)
    save_lap(clean, tmp_path)
    ref = _find_reference_by_scan("ferrari_488_gt3", "monza", tmp_path)
    assert ref is not None and ref.clean is True


def test_slug_handles_empty_and_specials():
    assert storage._slug("") == "unknown"
    assert storage._slug("Ferrari 488 GT3!") == "ferrari-488-gt3"


def test_describe_lap_marks_partial():
    assert "partial" in describe_lap(synth.build_lap(n=3, valid=False))
    assert "partial" not in describe_lap(synth.build_lap(n=3, valid=True))
