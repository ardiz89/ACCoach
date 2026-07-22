"""L'overlay disegnato davvero: la staccata commuta a tempo, e le cifre ci stanno.

Questo file prima non dipingeva niente. Verificava che ``_BRAKE_NOW_S`` fosse
sensato usando una funzione ``_seconds()`` **riscritta nel test**: se
``_draw_brake_cue`` fosse tornata a commutare sui metri, tutti i test sarebbero
rimasti verdi. Adesso dipinge il widget vero e osserva quale testo chiede — la
parola "FRENA" viene richiesta solo nell'istante in cui bisogna agire.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QPixmap                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from accoach import overlay as ov_mod                   # noqa: E402
from accoach.overlay import (                           # noqa: E402
    _BRAKE_NEAR_S,
    _BRAKE_NOW_S,
    _DELTA_BOX_H,
    _DELTA_FONT_PX,
    Overlay,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _keys_drawn(app, metres: int, kmh: float, monkeypatch) -> set:
    """Paint one frame with a braking point ``metres`` ahead; which strings?"""
    asked: set = set()
    real_t = ov_mod.t

    def spy(key, *a, **kw):
        asked.add(key)
        return real_t(key, *a, **kw)

    monkeypatch.setattr(ov_mod, "t", spy)
    o = Overlay()
    o._state = {
        "connected": True, "speed_kmh": kmh,
        "delta": {"s": 0.1, "text": "+0.100", "ahead": False,
                  "brake_in_m": metres},
    }
    o.render(QPixmap(o.size()))
    o.deleteLater()
    return asked


def test_the_word_appears_at_the_moment_to_act(app, monkeypatch):
    """15 m a 200 km/h = 0.27 s: siamo dentro. Deve uscire la parola."""
    assert "overlay.brake" in _keys_drawn(app, 15, 200.0, monkeypatch)


def test_ten_metres_at_speed_is_already_the_moment(app, monkeypatch):
    """0.14 s a 250 km/h: il motivo per cui una soglia in metri era sbagliata."""
    assert "overlay.brake" in _keys_drawn(app, 10, 250.0, monkeypatch)


def test_the_same_ten_metres_is_early_in_a_slow_corner(app, monkeypatch):
    """0.6 s a 60 km/h: gli stessi metri, e qui la parola sarebbe prematura."""
    assert "overlay.brake" not in _keys_drawn(app, 10, 60.0, monkeypatch)


def test_far_out_there_is_no_word(app, monkeypatch):
    assert "overlay.brake" not in _keys_drawn(app, 150, 200.0, monkeypatch)


def test_with_no_braking_point_nothing_of_the_sort_is_drawn(app, monkeypatch):
    asked = _keys_drawn(app, None, 200.0, monkeypatch)
    assert "overlay.brake" not in asked


# --- soglie: i vincoli umani dietro i numeri -------------------------------

def test_now_fires_before_human_reaction_time_runs_out():
    """~0.25 s è la reazione; il colore deve arrivare col piede, non dopo."""
    assert _BRAKE_NOW_S >= 0.25


def test_near_leaves_room_to_prepare_but_not_to_stare():
    assert _BRAKE_NOW_S < _BRAKE_NEAR_S <= 2.5


# --- il numero grande ci sta nella sua casella -----------------------------

def test_the_delta_box_is_taller_than_the_glyphs_line_box():
    """Misurato con QFontMetrics? No: Qt headless non ha font e riporta l'altezza
    di un carattere da 28px come esattamente 28 — sarebbe passato anche col box
    da 34 che tagliava le cifre davvero."""
    assert _DELTA_BOX_H >= _DELTA_FONT_PX * 1.4


def test_the_box_that_used_to_clip_would_now_fail():
    assert 34 < _DELTA_FONT_PX * 1.4
