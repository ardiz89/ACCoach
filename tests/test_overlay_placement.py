"""Dove si piazza l'overlay: in alto a sinistra dello schermo CENTRALE.

Il piazzamento non aveva nessun test. Il commento di ``_watch_screens``
dichiarava di aver chiuso il difetto dell'origine che si sposta quando AMD
Eyefinity fonde i tre monitor — e il difetto era vivo sulla macchina del pilota,
perche' non l'aveva mai provato niente.

Qui la matematica sta in una funzione pura (``top_left_in_center_panel``), quindi
si rigiocano le geometrie **misurate** senza monitor veri:

    Eyefinity spento → tre 2560x1440 a x = -2560 / 0 / +2560, virtual a -2560
    Eyefinity acceso → un solo 7680x1440 a x = 0

Quello che questi test NON provano: che Eyefinity si accenda davvero. Nessuno lo
puo' accendere da questo processo; la prova vera la fa il pilota avviando il
gioco. Qui si prova che, **cambiata la geometria sotto un overlay gia' piazzato**,
il punto scelto cambia — e che cambia senza che nessun segnale di Qt sia partito.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from accoach import overlay as ov_mod                   # noqa: E402
from accoach.overlay import (                           # noqa: E402
    _EDGE_MARGIN,
    Overlay,
    center_panel,
    top_left_in_center_panel,
)

# Le due geometrie misurate su questa macchina (vedi brief).
OFF_SCREENS = ((0, 0, 2560, 1440), (2560, 0, 2560, 1440), (-2560, 0, 2560, 1440))
OFF_VIRTUAL = (-2560, 0, 7680, 1440)
ON_SCREENS = ((0, 0, 7680, 1440),)
ON_VIRTUAL = (0, 0, 7680, 1440)

SIZE = (560, 210)   # l'overlay a scala 1.0


# --- la funzione pura, sulle geometrie della tabella ------------------------
def test_eyefinity_spento_il_pannello_centrale_e_quello_che_contiene_il_centro():
    """Tre schermi: nessuna assunzione, il centro del virtual cade in x=0..2560."""
    assert center_panel(OFF_SCREENS, OFF_VIRTUAL) == (0, 0, 2560, 1440)
    assert top_left_in_center_panel(OFF_SCREENS, OFF_VIRTUAL, SIZE) == (24, 24)


def test_eyefinity_acceso_un_solo_schermo_largo_si_divide_in_tre():
    """7680/1440 = 5.33 → N = 3 → il pannello centrale parte a 2560."""
    assert center_panel(ON_SCREENS, ON_VIRTUAL) == (2560, 0, 2560, 1440)
    assert top_left_in_center_panel(ON_SCREENS, ON_VIRTUAL, SIZE) == (2584, 24)


def test_un_monitor_solo_resta_un_monitor_solo():
    screens = ((0, 0, 2560, 1440),)
    assert center_panel(screens, (0, 0, 2560, 1440)) == (0, 0, 2560, 1440)
    assert top_left_in_center_panel(screens, (0, 0, 2560, 1440), SIZE) == (24, 24)


def test_due_pannelli_fusi_il_centrale_e_quello_di_destra():
    """N pari non ha un centro: la scelta pinnata qui e' l'indice N//2.

    Con due pannelli fusi (5120x1440) N//2 = 1, cioe' il pannello **destro**.
    E' una scelta, non una misura: con due monitor il pilota guarda la giunzione
    e nessuno dei due e' "il centrale".
    """
    screens = ((0, 0, 5120, 1440),)
    assert center_panel(screens, (0, 0, 5120, 1440)) == (2560, 0, 2560, 1440)
    assert top_left_in_center_panel(screens, (0, 0, 5120, 1440), SIZE) == (2584, 24)


def test_uno_span_che_non_torna_ricade_sullo_schermo_intero():
    """5000x1440: N verrebbe 2, ma 2500x1440 non e' 16:9 → non ci si fida.

    Il ripiego e' lo schermo intero, non un pannello inventato a 2500.
    """
    screens = ((0, 0, 5000, 1440),)
    assert center_panel(screens, (0, 0, 5000, 1440)) == (0, 0, 5000, 1440)
    assert top_left_in_center_panel(screens, (0, 0, 5000, 1440), SIZE) == (24, 24)


def test_un_ultrawide_non_viene_spezzato_in_pannelli():
    """3440x1440 e' 21:9: il rapporto non e' vicino a un intero di 16:9."""
    screens = ((0, 0, 3440, 1440),)
    assert center_panel(screens, (0, 0, 3440, 1440)) == (0, 0, 3440, 1440)


def test_tre_pannelli_fullhd_fusi():
    """5760x1080 = 3 x 1920: la deduzione vale anche fuori dalla macchina del pilota."""
    assert center_panel(((0, 0, 5760, 1080),), (0, 0, 5760, 1080)) == (1920, 0, 1920, 1080)


def test_il_bordo_alto_e_quello_del_pannello_non_quello_del_desktop():
    """Pannelli non allineati in verticale: il margine parte dal pannello scelto."""
    screens = ((0, 120, 2560, 1440), (2560, 0, 2560, 1440), (-2560, 300, 2560, 1440))
    assert top_left_in_center_panel(screens, (-2560, 0, 7680, 1740), SIZE) == (24, 144)


def test_se_il_centro_cade_in_un_buco_si_prende_il_pannello_piu_vicino():
    """Due schermi lontani e diversi: il centro non sta dentro nessuno dei due."""
    screens = ((0, 0, 1024, 768), (3000, 0, 1920, 1080))
    panel = center_panel(screens, (0, 0, 4920, 1080))
    assert panel == (3000, 0, 1920, 1080)


def test_un_pannello_piu_stretto_dell_overlay_non_lo_butta_fuori():
    """Guardia: il margine si accorcia invece di spingere l'overlay oltre il bordo."""
    screens = ((0, 0, 400, 200),)
    assert top_left_in_center_panel(screens, (0, 0, 400, 200), SIZE) == (0, 0)


def test_senza_schermi_si_usa_il_virtual_desktop():
    """Guardia: Qt che non riporta schermi non deve far esplodere il conto."""
    assert top_left_in_center_panel((), (100, 50, 1920, 1080), SIZE) == (124, 74)


def test_uno_schermo_di_altezza_zero_non_divide_per_zero():
    assert center_panel(((0, 0, 1920, 0),), (0, 0, 1920, 0)) == (0, 0, 1920, 0)


def test_il_margine_e_lo_stesso_sui_due_bordi():
    """Il +24 dal bordo alto c'era gia'; da sinistra si usa lo stesso."""
    x, y = top_left_in_center_panel(ON_SCREENS, ON_VIRTUAL, SIZE)
    assert (x - 2560, y) == (_EDGE_MARGIN, _EDGE_MARGIN)


# --- (a) il conto rifatto quando la geometria cambia, senza segnali ---------
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_eyefinity_che_si_accende_sposta_l_overlay_gia_piazzato(app, monkeypatch):
    """Il difetto del pilota, rigiocato: l'origine si sposta di 2560.

    Nessun segnale di Qt viene emesso qui — e' esattamente il punto: sulla
    macchina del pilota i segnali non bastano, quindi il riposizionamento non
    deve dipenderne.
    """
    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (OFF_SCREENS, OFF_VIRTUAL))
    o = Overlay()
    assert (o.x(), o.y()) == (24, 24)          # dentro il pannello centrale, x=0..2560

    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (ON_SCREENS, ON_VIRTUAL))
    o._reposition_if_geometry_changed()
    assert (o.x(), o.y()) == (2584, 24)        # il terzo di mezzo del nuovo span
    o.deleteLater()


def test_il_riposizionamento_scatta_dal_timer_non_dai_segnali(app, monkeypatch):
    """Il tick e' suo e parte comunque: qui si emette solo il suo timeout."""
    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (OFF_SCREENS, OFF_VIRTUAL))
    o = Overlay()
    assert o._geometry_poll.isActive()
    assert o._geometry_poll.interval() == ov_mod._GEOMETRY_POLL_MS

    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (ON_SCREENS, ON_VIRTUAL))
    o._geometry_poll.timeout.emit()
    assert o.x() == 2584
    o.deleteLater()


def test_geometria_immutata_l_overlay_non_si_muove_da_solo(app, monkeypatch):
    """Chi ha trascinato in --interactive non deve vedersi rimbalzare la finestra.

    (Qui l'overlay e' in automatico, ma il principio e' lo stesso: senza un
    cambio di geometria il tick non tocca niente.)
    """
    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (OFF_SCREENS, OFF_VIRTUAL))
    o = Overlay()
    o.move(1000, 500)                 # come se l'avesse spostata qualcun altro
    o._reposition_if_geometry_changed()
    assert (o.x(), o.y()) == (1000, 500)
    o.deleteLater()


def test_una_posizione_appuntata_non_si_tocca_quando_l_origine_si_sposta(app, monkeypatch):
    """Comportamento dichiarato: la posizione appuntata vince sempre.

    Resta appuntata anche dopo che Eyefinity ha spostato l'origine, finche' e'
    ancora sopra uno schermo. E' il comportamento di prima e non lo cambiamo.
    """
    from accoach import config
    cfg = config.load_config()
    monkeypatch.setattr(cfg.overlay, "x", 3000)
    monkeypatch.setattr(cfg.overlay, "y", 100)
    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (OFF_SCREENS, OFF_VIRTUAL))
    o = Overlay()
    assert (o.x(), o.y()) == (3000, 100)

    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (ON_SCREENS, ON_VIRTUAL))
    o._reposition_if_geometry_changed()
    assert (o.x(), o.y()) == (3000, 100)
    o.deleteLater()


def test_una_posizione_appuntata_finita_fuori_torna_dentro(app, monkeypatch):
    """Se il desktop si stringe e la posizione salvata resta fuori, si ripiazza."""
    from accoach import config
    cfg = config.load_config()
    monkeypatch.setattr(cfg.overlay, "x", 7000)
    monkeypatch.setattr(cfg.overlay, "y", 100)
    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: (ON_SCREENS, ON_VIRTUAL))
    o = Overlay()
    assert (o.x(), o.y()) == (7000, 100)

    small = (((0, 0, 2560, 1440),), (0, 0, 2560, 1440))
    monkeypatch.setattr(ov_mod, "_screen_snapshot", lambda: small)
    o._reposition_if_geometry_changed()
    assert (o.x(), o.y()) == (24, 24)
    o.deleteLater()
