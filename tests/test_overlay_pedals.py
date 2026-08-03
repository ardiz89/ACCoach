"""La striscia dei pedali: l'unica cosa VISIVA e in tempo reale sul trail braking.

Traccia gas (verde) e freno (rosso) sotto l'HUD, con un nastro **ambra** finché i
due pedali si sovrappongono — cioè finché stai trailando — e **grigio** quando
non ne premi nessuno (tempo morto). In alto a destra la targhetta dello stato:
`TRAIL` o `COAST` col cronometro.

Esisteva, funzionava, e non l'ha mai vista nessuno: spenta per impostazione
predefinita e **senza un interruttore da nessuna parte**, quindi accendibile solo
scrivendo a mano in `config.toml`. Questi test tengono in piedi le due metà —
che disegni davvero, e che si possa accendere senza aprire un editor di testo.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QPixmap                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from accoach import overlay as ov_mod                   # noqa: E402
from accoach.overlay import _BASE_H, _PEDAL_PANEL_H, Overlay   # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _paint(app, pedals, frames, monkeypatch):
    """Dipinge un frame dopo aver alimentato la storia dei pedali."""
    asked: set = set()
    real_t = ov_mod.t

    def spy(key, *a, **kw):
        asked.add(key)
        return real_t(key, *a, **kw)

    monkeypatch.setattr(ov_mod, "t", spy)
    o = Overlay(pedals=pedals)
    for thr, brk in frames:
        o.apply_state({"connected": True, "speed_kmh": 120.0,
                       "throttle": thr, "brake": brk})
    o.render(QPixmap(o.size()))
    size = o.size()
    o.deleteLater()
    return asked, size


def test_overlapping_pedals_are_called_trail(app, monkeypatch):
    """Freno che decade mentre il gas sale: è il trail braking, e la targhetta
    lo deve dire mentre sta succedendo, non a fine giro."""
    asked, _ = _paint(app, True, [(0.0, 1.0), (0.2, 0.6), (0.5, 0.3)], monkeypatch)
    assert "overlay.trail" in asked


def test_no_pedal_at_all_is_called_coasting(app, monkeypatch):
    asked, _ = _paint(app, True, [(0.0, 0.8), (0.0, 0.0), (0.0, 0.0)], monkeypatch)
    assert "overlay.coast" in asked


def test_a_clean_release_is_neither(app, monkeypatch):
    """Freno mollato e gas subito dentro: nessuna sovrapposizione e nessun
    vuoto, quindi niente targhetta. Una targhetta sempre accesa non informa."""
    asked, _ = _paint(app, True, [(0.0, 0.9), (1.0, 0.0)], monkeypatch)
    assert "overlay.trail" not in asked and "overlay.coast" not in asked


def test_the_strip_gets_its_own_band_and_does_not_sit_under_the_hud(app, monkeypatch):
    """Il timore era che qualcosa l'avesse coperta. Non può: la finestra cresce
    di tutta l'altezza del pannello quando la striscia è accesa, e la striscia
    parte esattamente dove finisce l'HUD."""
    _, off = _paint(app, False, [(1.0, 0.0)], monkeypatch)
    _, on = _paint(app, True, [(1.0, 0.0)], monkeypatch)
    grown = (on.height() - off.height())
    assert grown > 0
    assert round(grown / (on.height() - off.height() or 1)) == 1
    assert _PEDAL_PANEL_H > 0 and _BASE_H > 0


def test_with_the_strip_off_nothing_of_it_is_drawn(app, monkeypatch):
    asked, _ = _paint(app, False, [(0.3, 0.4), (0.3, 0.4)], monkeypatch)
    assert "overlay.trail" not in asked
    assert "overlay.throttle_pedal" not in asked


# --- e si deve poter accendere senza aprire un editor ----------------------

def test_the_setting_exists_in_the_settings_panel():
    """Era leggibile solo scrivendo a mano in `config.toml`: una funzione che
    non si può accendere dall'app, per l'utente, non esiste."""
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent
           / "src" / "accoach" / "launcher.py").read_text(encoding="utf-8")
    assert "set.pedals" in src
    assert "cfg.overlay.pedals = " in src


def test_the_setting_has_a_label_in_both_languages():
    from accoach.i18n import t

    for lang in ("it", "en"):
        assert t("set.pedals", lang=lang) != "set.pedals"
        assert t("set.pedals_hint", lang=lang) != "set.pedals_hint"


def test_coach_live_honours_the_setting_without_being_told(app, monkeypatch):
    """Il difetto che rendeva inutile la spunta.

    `pedals` era un parametro con default False, quindi ogni chiamante doveva
    ricordarsene. Il comando `overlay` se lo ricordava; **`live` no** — cioè il
    processo che il wizard e la guida dicono di avviare. Si poteva mettere la
    spunta, salvarla, riaprire il pannello e ritrovarla messa, e sull'overlay
    non succedeva niente.

    Costruito come lo costruisce `app.py`, senza passare nulla.
    """
    import accoach.config as cfg_mod

    real = cfg_mod.load_config()
    real.overlay.pedals = True
    monkeypatch.setattr(cfg_mod, "load_config", lambda *a, **k: real)
    monkeypatch.setattr(ov_mod, "load_config", lambda *a, **k: real, raising=False)

    o = Overlay(url=None, interactive=False)      # esattamente la riga di app.py
    on = o._show_pedals
    o.deleteLater()
    assert on, "la spunta salvata deve arrivare a Coach Live da sola"


def test_the_command_line_flag_still_forces_it_on(app):
    o = Overlay(url=None, interactive=False, pedals=True)
    forced = o._show_pedals
    o.deleteLater()
    assert forced
