"""Stop only exists while there's something to stop.

Reported from use: the Drive panel showed "Stop Coach Live" before the driver had
ever pressed Start. A Stop button sitting next to Start reads as "something is
already running", which is the opposite of the truth — and disabling it isn't
enough, because a greyed-out Stop says the same thing a little more quietly.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")


class _FakeProc:
    """A child that is alive until told otherwise."""

    def __init__(self) -> None:
        self._done = None

    def poll(self):
        return self._done

    def exit(self) -> None:
        self._done = 0


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def hub(app, tmp_path, monkeypatch):
    from accoach import config, launcher
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    win = launcher.MainWindow()
    yield win
    win._children.clear()


def _shown(win) -> bool:
    """Is the Stop button asked to show?

    ``isHidden()`` and not ``isVisible()``: a widget only reports visible once
    every ancestor is on screen, and these tests never show the window.
    """
    from accoach.launcher import _STOP_LIVE
    for key, _label, btn in win._actions:
        if key == _STOP_LIVE:
            return not btn.isHidden()
    raise AssertionError("the Stop button is not registered")


def test_hidden_before_anything_is_started(hub):
    assert _shown(hub) is False


def test_shown_once_coach_live_is_running(hub):
    hub._children.append((_FakeProc(), ["live"]))
    hub._refresh_buttons()
    assert _shown(hub) is True


def test_hidden_again_when_the_coach_exits_on_its_own(hub):
    """Closing the coach's own window must tidy the panel without a click."""
    proc = _FakeProc()
    hub._children.append((proc, ["live"]))
    hub._refresh_buttons()
    proc.exit()
    hub._refresh_buttons()          # the 1 s timer calls exactly this
    assert _shown(hub) is False


def test_another_child_does_not_summon_it(hub):
    """The web app isn't a coach; Stop must stay away."""
    hub._children.append((_FakeProc(), ["web"]))
    hub._refresh_buttons()
    assert _shown(hub) is False
