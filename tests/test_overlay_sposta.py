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
from PySide6.QtGui import QKeyEvent, QShowEvent                   # noqa: E402
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


# --- 27/10: quello che il pilota ha visto provandolo ---------------------------

def test_a_second_click_does_not_open_a_second_copy(cfg_file, monkeypatch):
    """Ogni clic su «Sposta l'overlay» apriva un'altra copia: il pilota se ne
    e' trovate sei una sopra l'altra."""
    from accoach import launcher
    from accoach.hubgate import PLACE_OVERLAY
    started = []

    class _Proc:
        pid = 1

        def poll(self):
            return None                      # ancora aperta

    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: started.append(a) or _Proc())
    win = launcher.MainWindow()
    try:
        win._spawn(list(PLACE_OVERLAY), False)
        win._spawn(list(PLACE_OVERLAY), False)
        assert len(started) == 1
        win._children = []                   # la copia e' stata chiusa
        win._spawn(list(PLACE_OVERLAY), False)
        assert len(started) == 2
    finally:
        win._children = []
        win.close()


def test_size_mode_and_colours_are_written_without_save(cfg_file):
    """Prima arrivavano al file solo con Salva, e la copia aperta non cambiava."""
    from accoach import launcher
    win = launcher.MainWindow()
    try:
        s = win._settings
        s._scale.setValue(1.4)
        s._mode.setCurrentIndex(1)
        s._cb.setChecked(True)
        assert s._look_timer.isActive()      # una scrittura sola, dopo i clic
        s._look_timer.stop()
        s._save_look()
        ov = config.read_overlay()
        assert (ov.scale, ov.mode, ov.cb) == (1.4, "full", True)
    finally:
        win.close()


def test_showing_settings_again_does_not_write_anything(cfg_file):
    """Rimettere nelle caselle i valori del file non e' una scelta del pilota."""
    from accoach import launcher
    win = launcher.MainWindow()
    try:
        s = win._settings
        disk = config.load_config(reload=True)
        disk.overlay.scale = 1.7
        config.save_config(disk)
        s.showEvent(QShowEvent())
        assert s._scale.value() == 1.7
        assert not s._look_timer.isActive()
    finally:
        win.close()


def test_the_open_copy_follows_size_and_mode_from_settings(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    cfg = config.load_config(reload=True)
    cfg.overlay.scale, cfg.overlay.mode = 1.5, "essential"
    config.save_config(cfg)
    win._follow_config()
    assert win._scale == 1.5 and win._mode == "essential"


def test_the_wheel_in_the_copy_is_not_undone_by_the_config(cfg_file):
    """La copia segue il config solo quando cambia li'."""
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    win.set_scale(1.8)
    win._follow_config()
    assert win._scale == 1.8


def test_the_copy_keeps_the_mode_chosen_while_it_was_open(cfg_file):
    """Invio salva posizione e grandezza, non riporta indietro la modalita'
    scritta dall'hub mentre la copia era aperta."""
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    cfg = config.load_config(reload=True)
    cfg.overlay.mode = "full"
    config.save_config(cfg)
    _key(win, Qt.Key_Return)
    assert config.read_overlay().mode == "full"

def test_back_to_the_centre_moves_the_open_copy(cfg_file):
    """Con la copia aperta «Rimetti al centro» non la muoveva, e Invio
    riscriveva la posizione di prima (27/10)."""
    from accoach.overlay_place import PlacementOverlay
    cfg = config.load_config(reload=True)
    cfg.overlay.x, cfg.overlay.y = 300, 300
    config.save_config(cfg)
    win = PlacementOverlay()
    assert (win.x(), win.y()) == (300, 300)
    cfg = config.load_config(reload=True)
    cfg.overlay.x, cfg.overlay.y = -1, -1                # il bottone dell'hub
    config.save_config(cfg)
    win._follow_config()
    assert (win.x(), win.y()) != (300, 300)
    _key(win, Qt.Key_Return)
    ov = config.read_overlay()
    assert (ov.x, ov.y) == (-1, -1)                      # resta automatica


def test_a_drag_is_not_undone_by_the_config(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    win.move(410, 220)
    win._follow_config()
    assert (win.x(), win.y()) == (410, 220)
    _key(win, Qt.Key_Return)
    ov = config.read_overlay()
    assert (ov.x, ov.y) == (410, 220)


def test_long_tooltips_wrap_and_short_ones_stay_on_one_line():
    """Il pilota non riusciva a leggerli: una riga sola, piu' larga dello
    schermo. Qt manda a capo solo il rich text."""
    from accoach.theme import tip_text
    long = tip_text("Legge i consigli ad alta voce. Spegnila per tenere solo l'overlay.")
    assert long.startswith("<table width=")
    assert "<p" in tip_text("Apre il report")
    assert tip_text("") == ""
    assert "&lt;b&gt;" in tip_text("<b>")                # il testo non e' markup


# --- 03/11: trascinata e mai salvata -----------------------------------------

def _drag(win, x, y):
    """Un trascinamento vero: premi, muovi, lascia."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    start = win.frameGeometry().topLeft()
    grab = QPointF(start.x() + 10, start.y() + 10)
    to = QPointF(x + 10, y + 10)
    for kind, at in ((QMouseEvent.MouseButtonPress, grab),
                     (QMouseEvent.MouseMove, to),
                     (QMouseEvent.MouseButtonRelease, to)):
        ev = QMouseEvent(kind, at, at, Qt.LeftButton,
                         Qt.NoButton if kind == QMouseEvent.MouseButtonRelease
                         else Qt.LeftButton, Qt.NoModifier)
        {QMouseEvent.MouseButtonPress: win.mousePressEvent,
         QMouseEvent.MouseMove: win.mouseMoveEvent,
         QMouseEvent.MouseButtonRelease: win.mouseReleaseEvent}[kind](ev)


def test_a_drag_is_saved_when_you_let_go(cfg_file):
    """Il pilota trascinava la copia e chiudeva l'hub: la posizione si salvava
    solo con Invio, e chiudendo l'hub la copia moriva senza scrivere niente."""
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    _drag(win, 500, 300)
    ov = config.read_overlay()
    assert (ov.x, ov.y) == (500, 300)


def test_back_to_the_centre_after_a_drag_moves_the_copy(cfg_file):
    """Il caso visto il 03/11: posizione automatica, copia trascinata, poi
    «Rimetti al centro». Il file diceva gia' -1, quindi la copia non vedeva
    nessun cambio e restava dov'era."""
    from accoach import launcher
    from accoach.overlay_place import PlacementOverlay
    hub = launcher.MainWindow()
    try:
        win = PlacementOverlay()
        auto = win.pos()
        _drag(win, 500, 300)
        hub._settings._center_overlay()
        win._follow_config()
        assert win.pos() == auto
        assert (config.read_overlay().x, config.read_overlay().y) == (-1, -1)
    finally:
        hub.close()


def test_the_wheel_saves_the_size_by_itself(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    win.set_scale(1.4)
    assert win._save_timer.isActive()
    win._save_timer.stop()
    win._save_here()
    assert config.read_overlay().scale == 1.4
    win._follow_config()
    assert win._scale == 1.4


def test_closing_with_a_size_still_pending_writes_it(cfg_file):
    """La rotella e poi subito Esc, o l'hub chiuso: la grandezza c'e' lo stesso."""
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    win.set_scale(1.6)
    _key(win, Qt.Key_Escape)
    assert config.read_overlay().scale == 1.6


def test_its_own_save_does_not_make_the_copy_jump(cfg_file):
    from accoach.overlay_place import PlacementOverlay
    win = PlacementOverlay()
    _drag(win, 420, 260)
    win._follow_config()
    assert (win.x(), win.y()) == (420, 260)


def test_changing_the_mode_keeps_the_size_set_with_the_wheel(cfg_file):
    """La rotella nella copia scrive 1,6; poi in Impostazioni cambi modalita'.
    La casella della grandezza dice ancora 1,0, e non la deve riscrivere."""
    from accoach import launcher
    from accoach.overlay_place import PlacementOverlay
    hub = launcher.MainWindow()
    try:
        win = PlacementOverlay()
        win.set_scale(1.6)
        win._save_timer.stop()
        win._save_here()
        s = hub._settings
        s._mode.setCurrentIndex(1 - s._mode.currentIndex())
        s._look_timer.stop()
        s._save_look()
        assert config.read_overlay().scale == 1.6
        s._scale.setValue(1.2)                 # questa invece e' una scelta
        s._look_timer.stop()
        s._save_look()
        assert config.read_overlay().scale == 1.2
    finally:
        hub.close()
