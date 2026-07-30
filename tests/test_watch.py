"""Recording by itself: mostly a list of times it must keep its hands off.

The feature exists because a session you forgot to arm leaves no trace — nothing
downstream (debrief, trends, braking sheet, training plan) can be recovered
afterwards. But an app that records without being asked, or that fights the
driver who just stopped it, is worse than one that forgets.
"""
import pytest

from accoach.watch import GameWatcher


class _Rig:
    """A watcher with every input under the test's thumb."""

    def __init__(self, connected=False, busy=False, enabled=True):
        self.connected = connected
        self.busy = busy
        self.enabled = enabled
        self.starts = 0
        self.watcher = GameWatcher(
            connected=lambda: self.connected,
            busy=lambda: self.busy,
            start=self._start,
            enabled=lambda: self.enabled,
        )

    def _start(self):
        self.starts += 1
        self.busy = True          # what really happens: a recorder is now running

    def tick(self):
        return self.watcher.tick()


def test_the_game_appearing_starts_the_recorder():
    r = _Rig(connected=False)
    assert r.tick() is False
    r.connected = True
    assert r.tick() is True
    assert r.starts == 1


def test_the_game_already_running_when_the_hub_opens_counts_as_appearing():
    """That is the case the feature exists for: you were in the car and
    remembered the app afterwards."""
    r = _Rig(connected=True)
    assert r.tick() is True


def test_it_does_not_start_again_while_the_game_stays_up():
    r = _Rig(connected=True)
    r.tick()
    r.busy = False               # the driver stopped the recorder by hand
    for _ in range(5):
        assert r.tick() is False
    assert r.starts == 1


def test_stopping_it_by_hand_keeps_it_stopped_until_the_next_session():
    """No second edge until the game goes away and comes back — otherwise the
    app would argue with the driver three seconds after they pressed Stop."""
    r = _Rig(connected=True)
    r.tick()
    r.busy = False
    assert r.tick() is False
    r.connected = False          # game closed
    r.tick()
    r.connected = True           # …and a new session begins
    assert r.tick() is True
    assert r.starts == 2


def test_it_never_starts_when_the_driver_has_not_asked():
    r = _Rig(connected=True, enabled=False)
    for _ in range(3):
        assert r.tick() is False
    assert r.starts == 0
    assert r.watcher.state == "off"


def test_turning_it_on_mid_session_catches_the_game_that_is_already_there():
    """The driver asked for it *now*, and the game is right there. Waiting for
    the next launch would look broken — so the edge isn't consumed while off."""
    r = _Rig(connected=True, enabled=False)
    for _ in range(3):
        assert r.tick() is False
    r.enabled = True
    assert r.tick() is True
    assert r.starts == 1


def test_it_never_starts_a_second_recorder():
    """Two processes recording one session save every lap twice, and the copy is
    indistinguishable from a real second lap."""
    r = _Rig(connected=False, busy=True)
    r.connected = True
    assert r.tick() is False
    assert r.starts == 0
    assert r.watcher.state == "busy"


def test_a_probe_that_throws_is_not_a_crash():
    """It runs on the hub's clock; a watcher must never take the window down."""
    def boom():
        raise OSError("shared memory went away")

    w = GameWatcher(connected=boom, busy=lambda: False,
                    start=lambda: None, enabled=lambda: True)
    assert w.tick() is False
    assert w.state == "waiting"


def test_a_failed_start_is_reported_not_raised():
    def boom():
        raise OSError("no exe")

    w = GameWatcher(connected=lambda: True, busy=lambda: False,
                    start=boom, enabled=lambda: True)
    assert w.tick() is False


@pytest.mark.parametrize("connected,busy,enabled,expected", [
    (False, False, True, "waiting"),
    (True, False, True, "busy"),        # after starting
    (True, True, True, "busy"),
    (True, False, False, "off"),
])
def test_it_says_what_it_is_doing(connected, busy, enabled, expected):
    """A setting whose effect is invisible until next time is one nobody trusts."""
    r = _Rig(connected=connected, busy=busy, enabled=enabled)
    r.tick()
    assert r.watcher.state == expected


def test_the_hub_wires_the_silent_recorder_and_never_the_voice():
    """The one thing that must not drift: what this starts. A coach that begins
    talking because you opened the game is a different product."""
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "accoach"
           / "launcher.py").read_text(encoding="utf-8")
    block = src.split("self._watcher = GameWatcher(")[1].split(")\n")[0]
    started = re.search(r'start=lambda: self\._spawn\(\["(\w+)"\]', block)
    assert started and started.group(1) == "recorder"
    assert "live" not in block and "coach" not in block


def test_the_hub_counts_coach_live_as_already_recording():
    """Coach Live records too; starting a recorder next to it would duplicate
    every lap of the session."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "accoach"
           / "launcher.py").read_text(encoding="utf-8")
    block = src.split("def _is_recording")[1].split("def ")[0]
    for cmd in ("recorder", "live", "coach"):
        assert f'"{cmd}"' in block


def test_it_is_off_in_a_fresh_config():
    """Software that records you without being asked is a different product from
    the one anyone installed."""
    from accoach.config import Config

    assert Config().autorecord is False
