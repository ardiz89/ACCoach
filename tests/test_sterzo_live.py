"""Lo sterzo dal vivo: arriva nello stato e l'overlay lo disegna.

Il pilota l'ha chiesto il 21/10: nella striscia dei pedali dell'overlay, e nel
grafico della pagina Ingegnere, oltre a gas e freno anche la linea dello
sterzo. Il dato c'era (`steer_angle`, registrato su ogni giro e disegnato nel
Confronto del report) ma lo stato dal vivo non lo portava, quindi nessuna delle
due viste dal vivo poteva mostrarlo.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from accoach.serialize import snapshot_to_dict

import synth


def test_the_live_state_carries_the_steering():
    s = synth.snap(pos=0.5)
    s.steer_angle = 0.41234
    assert snapshot_to_dict(s)["steer"] == 0.412


# --- l'overlay -------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage, QPainter     # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from accoach.overlay import _BASE_H, _BASE_W, _STEER_FLOOR, Overlay   # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _strip(o: Overlay) -> QImage:
    """La sola striscia, disegnata su fondo nero a scala 1."""
    img = QImage(_BASE_W, _BASE_H + 200, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    o._draw_pedals(p, _BASE_W)
    p.end()
    return img


_PLOT_TOP, _PLOT_H = _BASE_H + 30, 64     # come in Overlay._draw_pedals


def _white_rows(img: QImage, x: int) -> list[int]:
    """Le righe bianche dentro il grafico (l'intestazione sopra ha testo bianco)."""
    rows = []
    for y in range(_PLOT_TOP - 3, _PLOT_TOP + _PLOT_H + 4):
        c = img.pixelColor(x, y)
        if c.red() > 180 and c.green() > 180 and c.blue() > 180:
            rows.append(y)
    return rows


def test_the_strip_draws_the_steering_left_up(app):
    """Volante tutto a sinistra per sei secondi: la linea bianca corre in cima
    al grafico. Tutto a destra: in fondo. Dritto: a meta'."""
    o = Overlay(pedals=True)
    now = time.monotonic()
    rows = {}
    # A destra la linea finisce sul fondo, dove i pedali a zero le passano
    # sopra (sono disegnati dopo, apposta): li' i pedali si mettono a fondo.
    for name, steer, ped in (("left", 0.6, 0.0), ("right", -0.6, 1.0),
                             ("dritto", 0.0, 0.0)):
        o._steer_scale = 0.6
        o._pedal_hist = [(now - 5.0, ped, ped, steer), (now, ped, ped, steer)]
        rows[name] = _white_rows(_strip(o), _BASE_W // 2)
    o.deleteLater()
    plot_top, plot_h = _PLOT_TOP, _PLOT_H
    assert rows["left"] and rows["right"] and rows["dritto"], rows
    assert min(rows["left"]) <= plot_top + 2, rows["left"]
    assert max(rows["right"]) >= plot_top + plot_h - 2, rows["right"]
    mid = plot_top + plot_h // 2
    assert any(abs(r - mid) <= 2 for r in rows["dritto"]), rows["dritto"]


def test_without_steering_there_is_no_white_line(app):
    """Il controllo del test sopra: la stessa striscia senza sterzo (dritto)
    non ha bianco in cima. Se il bianco ci fosse comunque, il test sopra non
    proverebbe niente."""
    o = Overlay(pedals=True)
    now = time.monotonic()
    o._pedal_hist = [(now - 5.0, 0.0, 0.0, 0.0), (now, 0.0, 0.0, 0.0)]
    rows = _white_rows(_strip(o), _BASE_W // 2)
    o.deleteLater()
    assert all(r > _PLOT_TOP + 4 for r in rows), rows


def test_the_scale_grows_with_the_wheel_and_never_shrinks(app):
    o = Overlay(pedals=True)
    assert o._steer_scale == _STEER_FLOOR
    for steer in (0.1, 0.8, 0.2):
        o.apply_state({"connected": True, "throttle": 0.5, "brake": 0.0,
                       "steer": steer})
    assert o._steer_scale == 0.8
    o.deleteLater()


def test_an_old_backend_without_steering_still_draws_the_pedals(app):
    """Uno stato senza `steer` (un backend di prima) non deve rompere la
    striscia: lo sterzo vale dritto."""
    o = Overlay(pedals=True)
    o.apply_state({"connected": True, "throttle": 0.5, "brake": 0.2})
    assert o._pedal_hist[-1][1:] == (0.5, 0.2, 0.0)
    _strip(o)
    o.deleteLater()
