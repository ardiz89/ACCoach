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

from accoach.coaching.analyzer import (                     # noqa: E402
    _GAIN_MS, _LOSS_MS, corner_level,
)
from accoach.overlay import (                               # noqa: E402
    _AMBER, _CARD_COLOUR, _CYAN, _GREEN, _RED, Overlay,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _paint(app, state) -> tuple:
    """Dipinge un frame; torna (testi passati a drawText, colori passati a setBrush)."""
    drawn, brushes = [], []
    o = Overlay()
    o._state = state
    real = o._draw_corner_card

    def spy(p, w):
        orig_text, orig_brush = p.drawText, p.setBrush

        def grab(*a, **kw):
            if a and isinstance(a[-1], str):
                drawn.append(a[-1])
            return orig_text(*a, **kw)

        def grab_brush(*a, **kw):
            if a:
                brushes.append(a[0])
            return orig_brush(*a, **kw)

        p.drawText = grab
        p.setBrush = grab_brush
        try:
            return real(p, w)
        finally:
            # Senza questo, `grab` tiene un riferimento al painter che lo tiene:
            # il QPainter sopravvive a paintEvent e la gc ciclica lo distrugge
            # più tardi, su un device già morto — un access violation dentro un
            # test che non c'entra niente.
            del p.drawText
            del p.setBrush

    o._draw_corner_card = spy
    o.render(QPixmap(o.size()))
    del o._draw_corner_card
    o.deleteLater()
    return drawn, brushes


def _texts(app, state) -> list:
    return _paint(app, state)[0]


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


# --- il semaforo: l'unica parte tarata di tutta la feature ------------------
#
# `corner_level` è testata a fondo e l'overlay non porta nessuna soglia: dopo
# quel controllo, una voce scambiata in questa tabella è l'ultimo modo rimasto
# perché il colore dica una cosa diversa dalla voce. Finora la tabella non era
# asserita da nessuna parte — e questo file importava _AMBER/_GREEN/_RED senza
# usarli, un controllo cominciato e lasciato lì.

def test_every_level_the_analyzer_can_return_has_a_colour():
    """Nessun livello deve cadere nel ripiego grigio di `_CARD_COLOUR.get`."""
    levels = {corner_level(v) for v in (-_GAIN_MS - 1, -_GAIN_MS, -_GAIN_MS + 1,
                                        0.0, _LOSS_MS - 1, _LOSS_MS,
                                        _GAIN_MS, _GAIN_MS + 1)}
    assert levels == {"gain", "ok", "warn", "bad"}
    assert set(_CARD_COLOUR) == levels


def test_each_level_is_pinned_to_its_colour():
    assert _CARD_COLOUR["gain"] is _CYAN
    assert _CARD_COLOUR["ok"] is _GREEN
    assert _CARD_COLOUR["warn"] is _AMBER
    assert _CARD_COLOUR["bad"] is _RED


def test_when_the_coach_speaks_the_dot_is_never_green(app):
    """La promessa della feature, verificata sul pennello vero.

    Sopra `_LOSS_MS` il coach apre bocca: lì il pallino non può essere né verde
    né ciano, o schermo e voce direbbero due cose diverse.
    """
    for lost in (_LOSS_MS, _LOSS_MS + 1, _GAIN_MS, _GAIN_MS + 500):
        level = corner_level(lost)
        _, brushes = _paint(app, _with({"index": 0, "name": "Curva 1",
                                        "lost_ms": lost, "level": level}))
        assert brushes, "il pallino si dipinge sempre quando la carta c'è"
        assert brushes[0] == _CARD_COLOUR[level]
        assert brushes[0] not in (_GREEN, _CYAN)


def test_a_corner_taken_well_paints_green(app):
    _, brushes = _paint(app, _with({"index": 0, "name": "Curva 1",
                                    "lost_ms": 0.0, "level": corner_level(0.0)}))
    assert brushes[0] == _GREEN
