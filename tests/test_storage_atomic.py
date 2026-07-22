"""Lap writes are atomic, and half-written laps left by older builds still load.

Writing straight to the destination left a corrupt file behind when a write was
interrupted or when two recorders closed a lap at the same instant. One such
file exists on disk: valid gzip header, then 79 bytes of a second write.
"""
import gzip
import json

import pytest
import synth

from accoach.recording.lap import Lap
from accoach.recording.storage import load_lap, save_lap


def _lap() -> Lap:
    return synth.build_lap(car="bmw_m4_gt3_acc", track="ks_zandvoort")


def test_no_temp_files_left_behind(tmp_path):
    save_lap(_lap(), tmp_path)
    assert not list(tmp_path.glob("*.tmp")), "a temp file survived a successful write"


def test_roundtrip_still_works(tmp_path):
    path = save_lap(_lap(), tmp_path)
    back = load_lap(path)
    assert back.car_model == "bmw_m4_gt3_acc"
    assert back.lap_time_ms == 100_000
    assert len(back.samples) == 401


def test_failed_rename_leaves_no_debris_and_no_partial_lap(tmp_path, monkeypatch):
    """If the swap into place fails, neither a temp file nor a half lap survives.

    The rename is the last step and the one that can realistically fail (target
    locked by another process, permissions). Everything before it happened on a
    temp file, so the store must come out of it exactly as it went in.
    """
    import accoach.recording.storage as storage

    def boom(src, dst):
        raise OSError("target locked")

    monkeypatch.setattr(storage.os, "replace", boom)
    with pytest.raises(OSError):
        save_lap(_lap(), tmp_path)

    assert not list(tmp_path.glob("*.tmp")), "temp file left behind after a failure"
    assert not list(tmp_path.glob("*.lap.json.gz")), "a partial lap became visible"


def test_interrupted_write_never_becomes_visible(tmp_path, monkeypatch):
    """A write that dies mid-payload must not publish anything under the real name."""
    import accoach.recording.storage as storage

    class HalfWriter:
        def __init__(self, fh):
            self._fh = fh

        def write(self, data):
            self._fh.write(data[:20])            # only part of the lap lands...
            raise OSError("disk full")           # ...then the write dies

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()                     # the real `with` closes it too
            return False

    real_open = gzip.open
    monkeypatch.setattr(storage.gzip, "open",
                        lambda *a, **kw: HalfWriter(real_open(*a, **kw)))
    with pytest.raises(OSError):
        save_lap(_lap(), tmp_path)

    assert not list(tmp_path.glob("*.lap.json.gz")), "a partial lap became visible"
    assert not list(tmp_path.glob("*.tmp")), "temp file left behind after a failure"


def test_lap_with_trailing_garbage_is_recovered(tmp_path):
    """The exact shape of the damaged file on disk: good member + junk tail."""
    path = save_lap(_lap(), tmp_path)
    with path.open("ab") as fh:
        fh.write(b"\x36\xbb" + b"\x00" * 77)      # 79 bytes, as in the real file

    # Plain gzip gives up on it...
    with pytest.raises(gzip.BadGzipFile):
        with gzip.open(path, "rb") as fh:
            fh.read()

    # ...but the lap inside is intact and must still load.
    back = load_lap(path)
    assert back.lap_time_ms == 100_000
    assert len(back.samples) == 401


def test_truly_corrupt_file_still_raises(tmp_path):
    """Salvaging must not turn unreadable bytes into a silent empty lap."""
    bad = tmp_path / "broken.lap.json.gz"
    bad.write_bytes(b"this is not gzip at all")
    with pytest.raises(Exception):
        load_lap(bad)


def test_recovered_payload_matches_the_intact_one(tmp_path):
    # Both copies carry the SAME timestamp on purpose. `save_lap` stamps
    # `recorded_utc` to the second at write time, so saving two laps compared the
    # clock as well as the payload — and failed whenever the two writes straddled
    # a second boundary. It did, on CI, once. The question here is whether
    # salvaging recovers the content, not what time it is.
    lap = _lap()
    lap.recorded_utc = "2026-07-22T09:00:00+00:00"
    intact = save_lap(lap, tmp_path / "a")
    damaged = save_lap(lap, tmp_path / "b")
    with damaged.open("ab") as fh:
        fh.write(b"\x1f\x8b\x08\x00garbage")      # looks like a second member

    assert json.loads(json.dumps(load_lap(damaged).to_dict())) == \
           json.loads(json.dumps(load_lap(intact).to_dict()))
