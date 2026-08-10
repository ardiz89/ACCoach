"""The focus line names the word you'll hear, so it doesn't arrive out of nowhere.

The pact that agrees the trigger word is in the focus briefing, and the briefing
reaches the terminal coach and the web page — never the overlay, and it is never
spoken. `python -m accoach live` is overlay plus voice, which is the normal way
to run this, so that driver would hear "less brake" from the fourth lap with no
idea where it came from.

Like `test_overlay_pit_due.py`: the real widget is painted and the strings it
draws are read back, instead of re-implementing the logic under test.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                            # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPixmap                 # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

from accoach.overlay import Overlay                       # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


_BASE = {"connected": True, "speed_kmh": 150.0,
         "delta": {"s": 0.1, "text": "+0.100", "ahead": False}}


def _focus_line(state: dict) -> str:
    """The single string `_draw_focus` writes for this state ("" if it draws none)."""
    o = Overlay(pedals=False)
    o.apply_state(dict(state))

    drawn: list[str] = []
    real_focus = o._draw_focus

    def spy(p, w):
        orig_text = p.drawText

        def grab(*a, **kw):
            if a and isinstance(a[-1], str):
                drawn.append(a[-1])
            return orig_text(*a, **kw)

        p.drawText = grab
        try:
            return real_focus(p, w)
        finally:
            # See test_overlay_pit_due.py: the closure would keep the painter
            # alive past paintEvent and it would die on a dead device.
            del p.drawText

    o._draw_focus = spy
    pm = QPixmap(o.size())
    pm.fill(QColor(0, 0, 0))
    o.render(pm)
    del o._draw_focus
    o.deleteLater()
    return drawn[0] if drawn else ""


def _state(**focus_fields) -> dict:
    target = {"name": "Variante Ascari", "theme": "frenata",
              "baseline_ms": 180.0, **focus_fields}
    return {**_BASE, "focus": {"focus": target}}


def test_the_focus_line_shows_the_trigger_word(app):
    line = _focus_line(_state(trigger="meno freno"))
    assert "MENO FRENO" in line
    assert "VARIANTE ASCARI" in line, "and it doesn't replace what was already there"
    assert "FRENATA" in line


def test_no_trigger_leaves_the_line_as_it_was(app):
    """No word agreed (no focus theme on the gate): nothing extra, no empty quotes."""
    line = _focus_line(_state())
    assert "«" not in line
    assert "VARIANTE ASCARI" in line
