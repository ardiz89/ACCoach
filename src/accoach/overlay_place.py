"""Sposta l'overlay: una copia trascinabile, con dentro un giro d'esempio.

    python -m accoach overlay --place

Il pilota voleva mettere l'overlay dove gli pare (26/10). L'overlay vero non si
prende i click di proposito (non deve rubare il mouse al gioco), quindi non si
trascina lui: si trascina questa copia, che ha la stessa grandezza e lo stesso
disegno, e la posizione salvata finisce in `config.toml`. L'overlay di Coach
Live la rilegge da solo entro un secondo (`Overlay._follow_config`), senza
riavviare niente.

Comandi, scritti anche dentro la finestra:

* trascina col mouse per spostarla;
* rotella per la grandezza (passi da 0,05, fra 0,5 e 2,5 come in Impostazioni);
* Invio o doppio clic salva e chiude;
* Esc chiude senza salvare;
* R la rimette in alto al centro dello schermo di mezzo, e la posizione torna
  automatica.
"""
from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication

from .i18n import current_language, t
from .overlay import (_BASE_H, _BASE_W, _PEDAL_PANEL_H, _PLATE_H_ESSENTIAL,
                      _PLATE_H_FULL, _PLATE_W, _PLATE_X, _PLATE_Y, Overlay)
from .textfmt import fmt_num

# Gli stessi limiti della casella «Grandezza dell'overlay» in Impostazioni.
SCALE_MIN, SCALE_MAX, SCALE_STEP = 0.5, 2.5, 0.05

_CYAN = QColor(0x22, 0xD3, 0xCE)
# La riga dei comandi sta SOTTO l'overlay, in pixel veri: dentro la sua area
# copriva le ultime due righe (focus e curva), cioe' proprio lo spazio che il
# pilota deve vedere per decidere dove metterlo.
_BAND_PX = 52
_BAND = QColor(0x0B, 0x0E, 0x12, 225)


def sample_state() -> dict:
    """Un momento di giro qualunque, per vedere quanto spazio prende tutto."""
    return {
        "connected": True,
        "speed_kmh": 212.0,
        "delta": {"s": -0.184, "text": "-0.184", "ahead": True,
                  "local_s": -0.04, "local_losing": False,
                  "reference": "1:48.512", "brake_in_m": None},
        "focus": {"focus": {"name": "Variante Ascari", "theme": t("place.theme"),
                            "baseline_ms": 320, "trigger": ""}},
        "corner": {"name": "Parabolica", "level": "ok", "lost_ms": -40.0},
    }


def clamp_scale(value: float) -> float:
    return round(min(SCALE_MAX, max(SCALE_MIN, value)), 2)


class PlacementOverlay(Overlay):
    """L'overlay in modalita' trascinabile, che salva quando glielo dici."""

    def __init__(self) -> None:
        super().__init__(url=None, interactive=True)
        # La copia non deve rincorrere il config che sta per scrivere lei.
        self._follow_timer_stop()
        self._saved = False
        self.apply_state(sample_state())
        self.resize(self.width(), self.height() + _BAND_PX)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.SizeAllCursor)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Il bordo dice quale rettangolo stai spostando: senza, su una pista
        # chiara si vede solo dove c'e' qualcosa disegnato.
        pen = QPen(_CYAN, 2, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # Attorno alla piastra, non a tutta la finestra: la finestra e' piu'
        # grande e trasparente, e il pilota deve vedere lo spazio che occupa
        # davvero quello che si legge.
        k = self._scale
        plate_h = _PLATE_H_FULL if self._mode == "full" else _PLATE_H_ESSENTIAL
        if self._show_pedals:
            plate_h = _BASE_H + _PEDAL_PANEL_H - _PLATE_Y - 8
        p.drawRoundedRect(QRectF((_PLATE_X - 4) * k, (_PLATE_Y - 4) * k,
                                 (_PLATE_W + 8) * k, (plate_h + 8) * k), 12, 12)
        # La riga dei comandi, in basso, a grandezza fissa: si legge anche
        # quando l'overlay e' stato rimpicciolito.
        band_h = _BAND_PX - 8
        # Subito sotto la piastra, non in fondo alla finestra: in «Essenziale»
        # fra le due restava un vuoto che sembrava parte dell'overlay.
        top = (_PLATE_Y + plate_h + 4) * k + 6
        p.setPen(Qt.NoPen)
        p.setBrush(_BAND)
        p.drawRoundedRect(QRectF(4, top, self.width() - 8, band_h), 8, 8)
        self._set_font(p, 10, bold=True)
        p.setPen(_CYAN)
        scale = fmt_num(self._scale, 2, current_language())
        p.drawText(QRectF(12, top + 2, self.width() - 24, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, t("place.title").format(scale=scale))
        self._set_font(p, 9)
        p.setPen(QColor(0xE8, 0xED, 0xF2))
        p.drawText(QRectF(12, top + 22, self.width() - 24, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, t("place.keys"))

    # --- comandi ------------------------------------------------------------
    def wheelEvent(self, e) -> None:  # noqa: N802
        step = SCALE_STEP if e.angleDelta().y() > 0 else -SCALE_STEP
        self.set_scale(self._scale + step)

    def set_scale(self, value: float) -> None:
        """Nuova grandezza, tenendo fermo il centro della finestra."""
        new = clamp_scale(value)
        if new == self._scale:
            return
        centre = self.frameGeometry().center()
        self._scale = new
        self.resize(int(_BASE_W * new), int(self._base_h * new) + _BAND_PX)
        self.move(centre.x() - self.width() // 2, centre.y() - self.height() // 2)
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        # Qui il rilascio sposta e basta: si salva con Invio, non a ogni tocco.
        self._drag_off = None

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self.save_and_close()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        key = e.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.save_and_close()
        elif key == Qt.Key_Escape:
            self.close()
        elif key == Qt.Key_R:
            self.reset_and_close()
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self.set_scale(self._scale + SCALE_STEP)
        elif key == Qt.Key_Minus:
            self.set_scale(self._scale - SCALE_STEP)
        else:
            super().keyPressEvent(e)

    def _write(self, x: int, y: int) -> bool:
        from .config import load_config, save_config
        cfg = load_config()
        cfg.overlay.x, cfg.overlay.y = x, y
        cfg.overlay.scale = self._scale
        return save_config(cfg)

    def save_and_close(self) -> None:
        self._saved = self._write(self.x(), self.y())
        self.close()

    def reset_and_close(self) -> None:
        """Torna alla posizione automatica (in alto al centro), grandezza tenuta."""
        self._saved = self._write(-1, -1)
        self.close()


def main(argv: list[str] | None = None) -> None:
    from .theme import load_fonts

    app = QApplication.instance() or QApplication(sys.argv)
    load_fonts()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    win = PlacementOverlay()
    win.show()
    win.raise_()
    win.activateWindow()
    win.setFocus()
    app.exec()

