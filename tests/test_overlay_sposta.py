"""Il pilota sposta l'overlay da solo (26/10).

L'overlay vero non prende i click, quindi si trascina una copia
(`overlay_place.PlacementOverlay`) che salva posizione e grandezza nel config;
l'overlay di Coach Live le rilegge da solo (`Overlay._follow_config`).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                     # noqa: E402
from PySide6.QtGui import QKeyEvent                               # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from accoach import config                                         # noqa: E402


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: path)
    config.load_config(reload=True)
    QApplication.instance() or QApplication([])
    return path


def _key(widget, key):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier))


def test_enter_saves_position_and_size(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    win.move(321, 123)
    win.set_scale(1.3)
    _key(win, Qt.Key_Return)
    ov = config.read_overlay()
    assert (ov.x, ov.y) == (win.x(), win.y())
    assert ov.scale == 1.3


def test_escape_leaves_the_config_alone(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    win.move(400, 400)
    _key(win, Qt.Key_Escape)
    ov = config.read_overlay()
    assert (ov.x, ov.y) == (-1, -1)


def test_r_puts_it_back_to_automatic(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    cfg = config.load_config()
    cfg.overlay.x, cfg.overlay.y = 50, 60
    config.save_config(cfg)
    win = PlacementOverlay()
    _key(win, Qt.Key_R)
    ov = config.read_overlay()
    assert (ov.x, ov.y) == (-1, -1)


def test_the_size_stays_inside_the_settings_limits(cfg_file):
    from accoach.overlay_place import PlacementOverlay, clamp_scale
    assert clamp_scale(9) == 2.5 and clamp_scale(0.1) == 0.5
    win = PlacementOverlay()
    centre = win.frameGeometry().center()
    win.set_scale(2.0)
    # La rotella ingrandisce attorno al centro, non dall'angolo in alto.
    assert abs(win.frameGeometry().center().x() - centre.x()) <= 1
    assert abs(win.frameGeometry().center().y() - centre.y()) <= 1


def test_the_coach_live_overlay_follows_the_config(cfg_file):
    from accoach.overlay import Overlay
    ov = Overlay(url=None)
    assert ov._auto_place
    cfg = config.load_config()
    cfg.overlay.x, cfg.overlay.y, cfg.overlay.scale = 200, 150, 1.5
    config.save_config(cfg)
    ov._follow_config()
    assert (ov.x(), ov.y()) == (200, 150) and not ov._auto_place
    assert ov._scale == 1.5 and ov.width() == int(560 * 1.5)
    # Di nuovo automatica: torna in alto al centro.
    cfg.overlay.x, cfg.overlay.y = -1, -1
    config.save_config(cfg)
    ov._follow_config()
    assert ov._auto_place


def test_an_unreadable_config_moves_nothing(cfg_file):
    from accoach.overlay import Overlay
    ov = Overlay(url=None)
    before = (ov.x(), ov.y(), ov._scale)
    cfg_file.write_text("overlay = \n", encoding="utf-8")
    ov._follow_config()
    assert (ov.x(), ov.y(), ov._scale) == before


def test_a_drag_in_interactive_mode_pins_the_position(cfg_file):
    """Prima il trascinamento salvava ma lasciava `_auto_place` acceso, e al
    primo cambio di geometria (Eyefinity) l'overlay tornava al centro."""
    from accoach.overlay import Overlay
    ov = Overlay(url=None, interactive=True)
    ov._drag_off = object()
    ov.mouseReleaseEvent(None)
    assert not ov._auto_place


def test_moving_the_overlay_is_allowed_while_coach_live_runs():
    from accoach.hubgate import (CENTER_OVERLAY, CLICKABLE, PLACE_OVERLAY,
                                 button_state)
    assert button_state(PLACE_OVERLAY, live=True, busy=True) == CLICKABLE
    assert button_state(CENTER_OVERLAY, live=True, busy=True) == CLICKABLE


def test_the_overlay_command_opens_the_copy_with_place(monkeypatch):
    import accoach.overlay as overlay_mod
    import accoach.overlay_place as place_mod
    seen = []
    monkeypatch.setattr(place_mod, "main", lambda argv=None: seen.append(argv))
    overlay_mod.main(["--place"])
    assert seen == [["--place"]]


def test_back_to_the_centre_writes_even_after_another_process_moved_it(cfg_file):
    """L'hub ha letto -1 all'avvio; la copia ha scritto 500. «Rimetti al
    centro» deve scrivere -1 lo stesso, non tacere perche' uguale a prima."""
    from accoach import launcher
    win = launcher.MainWindow()
    try:
        disk = config.load_config(reload=True)
        disk.overlay.x, disk.overlay.y = 500, 400
        config.save_config(disk)
        config._cache.overlay.x = config._cache.overlay.y = -1      # l'hub ricorda -1
        config._baseline.overlay.x = config._baseline.overlay.y = -1
        win._settings._center_overlay()
        ov = config.read_overlay()
        assert (ov.x, ov.y) == (-1, -1)
    finally:
        win.close()
