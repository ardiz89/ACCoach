"""When the big delta number is on screen, and when it isn't.

One rule: the delta appears on a lap that started at the line and can still
count. It is a stopwatch reading, and the three cases below are the ones where
there is no stopwatch running on a comparable lap.

This paints the real widget rather than asserting on a helper, because the bug
class here is "the branch was right and the drawing didn't follow it".
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QPixmap                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from accoach.overlay import Overlay, _NO_DELTA_QUIET    # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _drawn(app, **state) -> bool:
    """Paint one frame; did the big delta get drawn?"""
    ov = Overlay()
    st = {"connected": True, "delta": {"s": 0.42, "text": "+0.420", "ahead": False}}
    st.update(state)
    ov._state = st
    seen = []
    ov._draw_delta = lambda *a, **k: seen.append(True)   # type: ignore[method-assign]
    ov.render(QPixmap(ov.size()))
    ov.deleteLater()
    return bool(seen)


def test_the_delta_shows_on_a_normal_flying_lap(app):
    assert _drawn(app) is True


def test_no_delta_in_the_pit_lane(app):
    assert _drawn(app, quiet="pit") is False


def test_no_delta_on_the_out_lap(app):
    """Reported from the pits: against a hot reference the number ran past +30 s
    and pinned the bar full-scale red, which reads as a catastrophic lap."""
    assert _drawn(app, quiet="out_lap") is False


def test_no_delta_on_an_invalidated_lap(app):
    assert _drawn(app, lap_invalid=True) is False


def test_the_delta_stays_on_an_off_pace_lap(app):
    """Deliberately not gated: that lap did start at the line, the number is ugly
    but true, and how much you dropped is exactly what you want to read."""
    assert _drawn(app, quiet="off_pace") is True
    assert "off_pace" not in _NO_DELTA_QUIET


def test_an_invalidated_lap_still_hides_it_even_off_pace(app):
    assert _drawn(app, quiet="off_pace", lap_invalid=True) is False
