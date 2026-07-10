"""The hub Home: last-session diagnosis assembly + the shell builds headless."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from accoach import hub_home
from accoach.recording.storage import save_lap

import synth


def _save(lap, laps_dir, utc):
    """Save a synthetic lap at a controlled recorded time (drives 'latest')."""
    lap.recorded_utc = utc
    return save_lap(lap, laps_dir)


def test_empty_dir_reports_empty(tmp_path):
    d = hub_home.load_home_data(tmp_path)
    assert d.status == "empty"
    assert d.top is None and d.debrief_text == ""


def test_headline_from_saved_laps(tmp_path):
    # A fast reference plus a later, slower lap that loses time in corner 0.
    _save(synth.build_lap(clean=True), tmp_path, "2026-07-10T10:00:00+00:00")
    _save(synth.build_lap(slow_corner=0, amt=30, clean=True), tmp_path,
          "2026-07-10T10:05:00+00:00")   # the most recent lap → the one reviewed

    d = hub_home.load_home_data(tmp_path, lang="en")

    assert d.status == "ok"
    assert d.car == "ferrari_488_gt3" and d.track == "monza"
    assert d.top is not None and d.top.lost_ms > 0
    assert d.top.fix                       # the mini-lesson is populated
    assert d.total_gap_ms > 0
    assert d.laps_count == 2
    assert "Debrief" in d.debrief_text     # full text available for the CTA


def test_single_lap_is_reference(tmp_path):
    _save(synth.build_lap(clean=True), tmp_path, "2026-07-10T10:00:00+00:00")
    d = hub_home.load_home_data(tmp_path)
    assert d.status == "is_reference"
    assert d.top is None


def test_mainwindow_builds_headless(monkeypatch):
    # Keep the Home worker instant + deterministic (don't touch the real laps dir).
    monkeypatch.setattr(hub_home, "load_home_data",
                        lambda *a, **k: hub_home.HomeData(status="empty"))
    from PySide6.QtWidgets import QApplication
    from accoach import launcher

    app = QApplication.instance() or QApplication([])
    win = launcher.MainWindow()
    try:
        worker = win._home._worker
        if worker is not None:
            worker.wait(3000)
        assert win._nav.count() == 6
        assert win._stack.count() == 6
        assert win._actions                       # action buttons registered
        win._on_language()                        # retranslate must not raise
        win._refresh_buttons()                    # gating must not raise
    finally:
        win.close()
