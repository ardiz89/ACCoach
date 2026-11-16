"""I pedali a barre, con la tacca del riferimento, e il verso dello sterzo.

Chiesto dal pilota il 03/11: nell'overlay, barre affiancate con la percentuale
dentro al posto delle linee. Le barre dicono l'istante e la traccia la forma,
quindi sono due viste da scegliere in Impostazioni. La tacca e' quanto premeva il
giro di riferimento in questo punto: senza, una barra e' un numero senza
confronto. Lo stesso giorno: il lato dello sterzo era scritto al contrario.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from accoach.comparison.delta import DeltaState
from accoach.comparison.reference import ReferencePoint
from accoach.serialize import delta_to_dict


def _delta(brake=0.62, throttle=0.0) -> DeltaState:
    rp = ReferencePoint(t_ms=1000.0, speed_kmh=150.0, throttle=throttle, brake=brake,
                        g_long=0.0, g_lat=0.0, steer_angle=0.0, gear="3",
                        abs_active=0.0, tc_active=0.0, yaw_rate=0.0)
    return DeltaState(pos=0.4, delta_ms=120.0, predicted_lap_ms=90_000.0,
                      reference_lap_ms=89_880, live_speed_kmh=140.0,
                      reference_point=rp)


def test_the_live_state_says_what_the_reference_pressed_here():
    d = delta_to_dict(_delta(brake=0.6234, throttle=0.1))
    assert d["ref_brake"] == 0.623 and d["ref_throttle"] == 0.1


def test_the_view_is_saved_and_a_wrong_one_falls_back_to_the_trace():
    import tomllib

    from accoach import config
    cfg = config.Config()
    assert cfg.overlay.pedal_view == "trace"
    cfg.overlay.pedal_view = "bars"
    back = config.Config()
    config._merge(back, tomllib.loads(config._to_toml(cfg)))
    assert back.overlay.pedal_view == "bars"
    fresh = config.Config()
    config._merge(fresh, tomllib.loads(config._DEFAULT_TOML))
    assert fresh.overlay.pedal_view == "trace"


def test_the_help_no_longer_calls_both_pedals_trail_braking():
    from accoach.i18n import t
    assert "tutti e due i pedali" not in t("set.pedals.help", lang="it")
    assert "volante girato" in t("set.pedals.help", lang="it")
    for key in ("set.pedal_view", "set.pedal_view.help", "set.pedal_view_trace",
                "set.pedal_view_bars", "overlay.ref_mark"):
        for lang in ("it", "en"):
            assert t(key, lang=lang) != key


def test_the_steering_side_follows_the_game_sign():
    """Positivo a destra: sui giri veri il 92 % delle curve a destra ha lo
    sterzo positivo. Le tre viste dal vivo lo scrivevano a sinistra."""
    from pathlib import Path
    web = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
    for name in ("engineer.js", "tablet.js"):
        js = web.joinpath(name).read_text(encoding="utf-8")
        assert 'steer > 0.02 ? tf("trace.steerRight"' in js, name


# --- l'overlay -------------------------------------------------------------

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage, QPainter     # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from accoach.overlay import (_BAR_GAP, _BAR_H, _BAR_TOP, _BASE_H,  # noqa: E402
                             _BASE_W, _TRACK, Overlay, _bar_text_spot, _trailing)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _bars(o: Overlay) -> QImage:
    o._pedal_view = "bars"
    img = QImage(_BASE_W, _BASE_H + 200, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    o._draw_pedals(p, _BASE_W)
    p.end()
    return img


# il centro di ogni riga, come nel disegno
_ROW_Y = {name: _BASE_H + _BAR_TOP + i * (_BAR_H + _BAR_GAP) + _BAR_H // 2
          for i, name in enumerate(("brake", "throttle", "steer"))}


def _span(o: Overlay) -> tuple[int, int]:
    """Dove sta la traccia delle barre: si disegna a pedali fermi, quando e' vuota."""
    hist, state = o._pedal_hist, o._state
    _feed(o, 0.0, 0.0, 0.0)
    img = _bars(o)
    o._pedal_hist, o._state = hist, state
    xs = [x for x in range(_BASE_W) if img.pixelColor(x, _ROW_Y["brake"]) == _TRACK]
    return min(xs), max(xs)


def _xs(img: QImage, y: int, test, x0: int) -> list[int]:
    """I pixel che passano ``test`` dentro la traccia: a sinistra c'e' il nome
    della riga, nello stesso colore della barra."""
    return [x for x in range(x0, _BASE_W) if test(img.pixelColor(x, y))]


def _red(c):
    return c.red() > 200 and c.green() < 160 and c.blue() < 170


def _green(c):
    return c.green() > 180 and c.red() < 120


def _cyan(c):
    return c.blue() > 170 and c.green() > 170 and c.red() < 90


def _white(c):
    return c.red() > 200 and c.green() > 200 and c.blue() > 200


def _feed(o, thr, brk, steer, delta=None):
    now = time.monotonic()
    o._pedal_hist = [(now - 0.1, thr, brk, steer), (now, thr, brk, steer)]
    o._state = {"connected": True, "delta": delta}


def test_the_brake_bar_is_as_long_as_the_pedal_and_the_mark_sits_at_the_reference(app):
    o = Overlay(pedals=True)
    x0, x1 = _span(o)
    _feed(o, 0.0, 0.5, 0.0, delta={"ref_brake": 0.8, "ref_throttle": 0.0})
    img = _bars(o)
    o.deleteLater()
    y = _ROW_Y["brake"]
    # la meta' del freno riempie la meta' della traccia
    assert abs(max(_xs(img, y, _red, x0)) - (x0 + (x1 - x0) * 0.5)) <= 3
    cyan = _xs(img, y, _cyan, x0)
    assert cyan and abs(sum(cyan) / len(cyan) - (x0 + (x1 - x0) * 0.8)) <= 3, cyan


def test_without_a_reference_there_is_no_mark(app):
    o = Overlay(pedals=True)
    x0, _ = _span(o)
    _feed(o, 0.4, 0.5, 0.0, delta=None)
    img = _bars(o)
    o.deleteLater()
    for row in ("brake", "throttle"):
        assert not _xs(img, _ROW_Y[row], _cyan, x0), row


def test_the_throttle_bar_has_its_own_row(app):
    o = Overlay(pedals=True)
    x0, _ = _span(o)
    _feed(o, 0.7, 0.0, 0.0)
    img = _bars(o)
    o.deleteLater()
    assert _xs(img, _ROW_Y["throttle"], _green, x0)
    # il freno a zero non riempie niente: la sua scritta sta subito dopo l'inizio
    assert img.pixelColor(x0 + 2, _ROW_Y["brake"]) == _TRACK
    assert img.pixelColor(x0 + 2, _ROW_Y["throttle"]) != _TRACK


@pytest.mark.parametrize("steer,side", [(-0.5, "left"), (0.5, "right")])
def test_the_steering_bar_grows_towards_the_side_you_turn(app, steer, side):
    o = Overlay(pedals=True)
    o._steer_scale = 0.5
    x0, x1 = _span(o)
    _feed(o, 0.0, 0.0, steer)
    filled = _xs(_bars(o), _ROW_Y["steer"], _white, x0)
    o.deleteLater()
    centre = (x0 + x1) / 2
    left = sum(1 for x in filled if x < centre - 20)
    right = sum(1 for x in filled if x > centre + 20)
    assert (left > right) if side == "left" else (right > left), (left, right)


def test_the_percentage_goes_inside_when_it_fits_and_after_the_tip_when_not():
    x, inside = _bar_text_spot(100, 300, 40, 100, 500)
    assert inside and x == 106
    x, inside = _bar_text_spot(100, 120, 40, 100, 500)
    assert not inside and x == 126
    # verso sinistra (lo sterzo): fuori, a sinistra della punta
    x, inside = _bar_text_spot(300, 290, 40, 100, 500)
    assert not inside and x == 290 - 6 - 40
    # mai fuori dalla traccia
    x, _ = _bar_text_spot(100, 495, 40, 100, 500)
    assert x == 106


def test_trail_braking_is_brake_with_the_wheel_turned():
    assert _trailing(0.4, 0.2) and _trailing(0.4, -0.2)
    assert not _trailing(0.4, 0.0)          # freno dritto: staccata
    assert not _trailing(0.0, 0.3)          # volante senza freno: in curva
