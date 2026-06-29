"""Launcher: the getting-started wizard's 'seen' marker (pure, no Qt window)."""
import accoach.launcher as launcher


def test_wizard_marker_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "base_dir", lambda: tmp_path)
    assert launcher.wizard_seen() is False        # first run
    launcher.mark_wizard_seen()
    assert launcher.wizard_seen() is True          # remembered
    assert (tmp_path / ".getting_started_seen").exists()
