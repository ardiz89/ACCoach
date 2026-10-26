"""Il disegno dell'overlay del 26/10, deciso col pilota.

Una piastra sola, tre righe fisse: il numero col delta, la riga d'azione (una
cosa alla volta), e solo in «Completa» focus e ultima curva. Il delta ha tre
decimali e la virgola in italiano, e si riscrive circa quattro volte al secondo.
Chi installa adesso parte da «Essenziale»; un config di prima resta «Completa».
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QPixmap                                  # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

import accoach.overlay as ov_mod                                    # noqa: E402
from accoach import config                                          # noqa: E402
from accoach.overlay import Overlay                                 # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


_DELTA = {"s": 0.312, "text": "+0.312", "ahead": False, "reference": "1:48.512"}
_BASE = {"connected": True, "speed_kmh": 200.0, "delta": dict(_DELTA)}
_FOCUS = {"focus": {"focus": {"name": "Variante Ascari", "theme": "frenata"}}}
_CARD = {"corner": {"name": "Lesmo 2", "level": "warn", "lost_ms": 120.0}}


def _paint(o: Overlay, monkeypatch) -> tuple[set, list]:
    """Dipinge un frame: (chiavi i18n chieste, testi passati a drawText)."""
    keys: set = set()
    real_t = ov_mod.t
    monkeypatch.setattr(ov_mod, "t", lambda k, *a, **kw: keys.add(k) or real_t(k, *a, **kw))
    texts: list = []
    from PySide6.QtGui import QPainter
    real_draw = QPainter.drawText

    def grab(self, *a, **kw):
        if a and isinstance(a[-1], str):
            texts.append(a[-1])
        return real_draw(self, *a, **kw)

    monkeypatch.setattr(QPainter, "drawText", grab)
    o.render(QPixmap(o.size()))
    monkeypatch.setattr(QPainter, "drawText", real_draw)
    return keys, texts


def _overlay(state, mode="full"):
    o = Overlay(url=None)
    o._mode = mode
    o.apply_state(state)
    return o


# --- Essenziale e Completa ---------------------------------------------------

def test_essential_shows_delta_and_action_row_only(app, monkeypatch):
    _, texts = _paint(_overlay({**_BASE, **_FOCUS, **_CARD}, "essential"), monkeypatch)
    assert any("0.312" in x for x in texts)
    assert not any("Ascari" in x for x in texts)
    assert "Lesmo 2" not in texts


def test_full_adds_focus_and_last_corner(app, monkeypatch):
    # Senza font veri (Qt offscreen) la riga si accorcerebbe: vedi
    # test_a_long_focus_line_drops_the_theme_before_the_voice_word.
    monkeypatch.setattr(ov_mod, "_fit_focus",
                        lambda fm, theme, name, word, room:
                        " · ".join(x for x in (theme, name, word) if x))
    _, texts = _paint(_overlay({**_BASE, **_FOCUS, **_CARD}, "full"), monkeypatch)
    assert any("Ascari" in x for x in texts)
    assert "Lesmo 2" in texts


def test_no_brand_and_no_fixed_pb_while_driving(app, monkeypatch):
    """Marchio e PB stavano in alto per tutto il giro: in guida non servono."""
    _, texts = _paint(_overlay(dict(_BASE)), monkeypatch)
    assert "HONE" not in texts
    assert not any("1:48.512" in x for x in texts)


def test_the_brand_stays_while_waiting_for_the_game(app, monkeypatch):
    _, texts = _paint(_overlay({}), monkeypatch)
    assert "HONE" in texts


# --- il numero del delta ------------------------------------------------------

def test_three_decimals_and_the_comma_in_italian(app, monkeypatch):
    monkeypatch.setattr(ov_mod, "current_language", lambda: "it")
    o = _overlay(dict(_BASE))
    assert o._delta_text({"s": 0.312}) == "+0,312"
    o._delta_shown = None
    assert o._delta_text({"s": -0.184}) == "−0,184"
    o._delta_shown = None
    assert o._delta_text({"s": 0.0}) == "0,000"


def test_english_keeps_the_point(app, monkeypatch):
    monkeypatch.setattr(ov_mod, "current_language", lambda: "en")
    o = _overlay(dict(_BASE))
    assert o._delta_text({"s": 0.312}) == "+0.312"


def test_the_number_is_rewritten_about_four_times_a_second(app, monkeypatch):
    """La barra e' fluida, il numero no: l'ultima cifra che cambia 20 volte al
    secondo e' movimento ai margini dello sguardo."""
    clock = {"t": 100.0}
    monkeypatch.setattr(ov_mod.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(ov_mod, "current_language", lambda: "en")
    o = _overlay(dict(_BASE))
    first = o._delta_text({"s": 0.312})
    clock["t"] += 0.05
    assert o._delta_text({"s": 0.400}) == first
    clock["t"] += ov_mod._DELTA_TEXT_S
    assert o._delta_text({"s": 0.400}) == "+0.400"


# --- la riga d'azione: una cosa alla volta -----------------------------------

def test_brake_now_beats_the_pit_call(app, monkeypatch):
    state = {**_BASE, "pit_due": True, "speed_kmh": 250.0,
             "delta": dict(_DELTA, brake_in_m=10)}
    keys, _ = _paint(_overlay(state), monkeypatch)
    assert "overlay.brake" in keys and "overlay.pit_due" not in keys


def test_the_pit_call_beats_a_far_braking_point(app, monkeypatch):
    state = {**_BASE, "pit_due": True, "delta": dict(_DELTA, brake_in_m=400)}
    keys, texts = _paint(_overlay(state), monkeypatch)
    assert "overlay.pit_due" in keys
    assert not any("▼" in x for x in texts)


def test_a_near_braking_point_shows_its_metres_in_the_middle_row(app, monkeypatch):
    state = {**_BASE, "speed_kmh": 200.0, "delta": dict(_DELTA, brake_in_m=60)}
    _, texts = _paint(_overlay(state), monkeypatch)
    assert "▼ 60 m" in texts


def test_a_new_reference_is_announced_once_then_goes(app, monkeypatch):
    clock = {"t": 50.0}
    monkeypatch.setattr(ov_mod.time, "monotonic", lambda: clock["t"])
    o = _overlay(dict(_BASE))                 # il primo riferimento non si annuncia
    keys, _ = _paint(o, monkeypatch)
    assert "overlay.new_ref" not in keys
    o.apply_state({**_BASE, "delta": dict(_DELTA, reference="1:47.900")})
    keys, texts = _paint(o, monkeypatch)
    assert "overlay.new_ref" in keys and any("1:47.900" in x for x in texts)
    clock["t"] += ov_mod._PB_HOLD_S + 0.1
    keys, _ = _paint(o, monkeypatch)
    assert "overlay.new_ref" not in keys


# --- daltonici -----------------------------------------------------------------

def test_the_colour_blind_palette_swaps_green_and_red(app):
    o = Overlay(url=None)
    o._apply_look(config.OverlayCfg(cb=True))
    assert (o._faster, o._slower) == (ov_mod._CB_FASTER, ov_mod._CB_SLOWER)
    o._apply_look(config.OverlayCfg(cb=False))
    assert (o._faster, o._slower) == (ov_mod._GREEN, ov_mod._RED)


def test_mode_and_palette_follow_the_config_while_running(app, tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: path)
    cfg = config.load_config(reload=True)
    o = Overlay(url=None)
    cfg.overlay.mode, cfg.overlay.cb = "full", True
    config.save_config(cfg)
    o._follow_config()
    assert o._mode == "full" and o._faster == ov_mod._CB_FASTER


# --- chi installa adesso parte da Essenziale ------------------------------------

def test_a_new_install_starts_essential(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: path)
    assert config.load_config(reload=True).overlay.mode == "essential"
    assert config.load_config(reload=True).overlay.mode == "essential"


def test_a_config_from_before_keeps_the_full_overlay(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('language = "it"\n\n[overlay]\nscale = 1.0\n', encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: path)
    assert config.load_config(reload=True).overlay.mode == "full"


def test_settings_save_mode_and_palette(app, tmp_path, monkeypatch):
    from accoach import launcher
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    win = launcher.MainWindow()
    try:
        s = win._settings
        s._mode.setCurrentIndex(1)
        s._cb.setChecked(True)
        s._do_save()
        ov = config.read_overlay()
        assert (ov.mode, ov.cb) == ("full", True)
    finally:
        win.close()


def test_a_long_focus_line_drops_the_theme_before_the_voice_word():
    """La parola della voce resta sempre: e' quella che il pilota sente."""
    from accoach.overlay import _fit_focus

    class _FM:                                  # 10 px a carattere
        def horizontalAdvance(self, s):
            return 10 * len(s)

        def elidedText(self, s, _mode, width):
            n = width // 10
            return s if len(s) <= n else s[:max(0, n - 1)] + "…"

    fm = _FM()
    full = "Frenata · Ascari · «prima»"
    assert _fit_focus(fm, "Frenata", "Ascari", "«prima»", 400) == full
    assert _fit_focus(fm, "Frenata", "Ascari", "«prima»", 170) == "Ascari · «prima»"
    tight = _fit_focus(fm, "Frenata", "Variante Ascari", "«prima»", 150)
    assert tight.endswith("«prima»") and "…" in tight
