"""Il riquadro della curva, dipinto davvero.

Come `test_overlay_paint.py`: si dipinge il widget vero e si guarda che testo
chiede, invece di riscrivere nel test la logica che si vuole verificare.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QPixmap                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from accoach.overlay import _AMBER, _GREEN, _RED, Overlay   # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _texts(app, state) -> list:
    """Dipinge un frame; torna tutte le stringhe passate a drawText."""
    drawn = []
    o = Overlay()
    o._state = state
    real = o._draw_corner_card

    def spy(p, w):
        orig = p.drawText

        def grab(*a, **kw):
            if a and isinstance(a[-1], str):
                drawn.append(a[-1])
            return orig(*a, **kw)

        p.drawText = grab
        try:
            return real(p, w)
        finally:
            # Senza questo, `grab` tiene un riferimento al painter che lo tiene:
            # il QPainter sopravvive a paintEvent e la gc ciclica lo distrugge
            # più tardi, su un device già morto — un access violation dentro un
            # test che non c'entra niente.
            del p.drawText

    o._draw_corner_card = spy
    o.render(QPixmap(o.size()))
    del o._draw_corner_card
    o.deleteLater()
    return drawn


_BASE = {"connected": True, "speed_kmh": 150.0,
         "delta": {"s": 0.1, "text": "+0.100", "ahead": False}}


def _with(card):
    return {**_BASE, "corner": card}


def test_a_loss_reads_as_negative_tenths(app):
    drawn = _texts(app, _with({"index": 5, "name": "Variante Ascari",
                               "lost_ms": 310.0, "level": "bad"}))
    assert "Variante Ascari" in drawn
    assert "−0.31" in drawn


def test_a_gain_reads_as_positive(app):
    drawn = _texts(app, _with({"index": 5, "name": "Curva 6",
                               "lost_ms": -260.0, "level": "gain"}))
    assert "+0.26" in drawn


def test_nothing_is_drawn_without_a_card(app):
    assert _texts(app, {**_BASE, "corner": None}) == []


def test_nothing_is_drawn_when_the_key_is_missing(app):
    assert _texts(app, _BASE) == []
