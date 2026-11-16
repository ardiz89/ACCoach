"""Sposta l'overlay: una copia trascinabile, con dentro un giro d'esempio.

    python -m accoach overlay --place

Il pilota voleva mettere l'overlay dove gli pare (26/10). L'overlay vero non si
prende i click di proposito (non deve rubare il mouse al gioco), quindi non si
trascina lui: si trascina questa copia, che ha la stessa grandezza e lo stesso
disegno, e la posizione salvata finisce in `config.toml`. L'overlay di Coach
Live la rilegge da solo entro un secondo (`Overlay._follow_config`), senza
riavviare niente.

Comandi, scritti anche dentro la finestra:

* trascina col mouse per spostarla: la posizione si salva quando lasci;
* rotella per la grandezza (passi da 0,05, fra 0,5 e 2,5 come in Impostazioni),
  salvata da sola poco dopo l'ultimo scatto;
* Invio, doppio clic o Esc chiude;
* R la rimette in alto al centro dello schermo di mezzo, e la posizione torna
  automatica.

Fino al 03/11 si salvava solo con Invio. Il pilota trascinava la copia e poi
chiudeva l'hub, che la chiude con se': la posizione andava persa. E con la
posizione automatica nel file, «Rimetti al centro» riscriveva lo stesso -1, la
copia non vedeva nessun cambio e restava dove l'avevi lasciata.
"""
from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication

from .config import read_overlay
from .i18n import current_language, t
from .overlay import (_BASE_H, _BASE_W, _PEDAL_PANEL_H, _PLATE_H_ESSENTIAL,
                      _PLATE_H_FULL, _PLATE_W, _PLATE_X, _PLATE_Y, Overlay)
from .textfmt import fmt_num

# Gli stessi limiti della casella «Grandezza dell'overlay» in Impostazioni.
SCALE_MIN, SCALE_MAX, SCALE_STEP = 0.5, 2.5, 0.05
# Gli scatti della rotella diventano una scrittura sola, come in Impostazioni.
_SIZE_SAVE_MS = 300

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
        # La grandezza che il config aveva l'ultima volta che l'abbiamo letto:
        # la copia la segue solo quando cambia li', non quando la rotella la
        # cambia qui (vedi `_follow_config`).
        self._seen_scale = self._scale
        ov = read_overlay()
        self._seen_pos = (ov.x, ov.y) if ov is not None else (-1, -1)
        # Dove la copia sta quando la posizione e' automatica. Se Invio arriva
        # senza che il pilota l'abbia spostata, resta automatica (-1) invece
        # di diventare un punto fisso.
        self._auto_at = self.pos() if self._seen_pos[0] < 0 else None
        self._saved = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SIZE_SAVE_MS)
        self._save_timer.timeout.connect(self._save_here)
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

    def _follow_config(self) -> None:
        """Segue le Impostazioni mentre e' aperta (27/10).

        Prima il timer qui era fermo: il pilota cambiava grandezza o modalita'
        nell'hub e la copia restava com'era. Anche la posizione si segue, ma
        solo quando cambia nel file: «Rimetti al centro» con la copia aperta
        non la muoveva, e Invio riscriveva la posizione di prima (27/10). Quello
        che la copia scrive da se' lo segna come gia' visto in `_write`, quindi
        non la fa saltare."""
        ov = read_overlay()
        if ov is None:                       # file a meta' scrittura: al prossimo giro
            return
        self._apply_look(ov)
        scale = clamp_scale(ov.scale if (ov.scale and ov.scale > 0) else 1.0)
        if scale != self._seen_scale:
            self._seen_scale = scale
            self.set_scale(scale)
        pos = (ov.x, ov.y)
        if pos != self._seen_pos:
            self._seen_pos = pos
            if ov.x >= 0 and ov.y >= 0:
                self.move(ov.x, ov.y)
            else:
                self._place_top_center()
                self._auto_at = self.pos()
        self.update()

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
        self._save_timer.start()
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        # Lasciata, la posizione si salva: l'overlay di Coach Live la segue, e
        # chiudere l'hub (che chiude la copia) non la perde piu'.
        dragged = self._drag_off is not None
        self._drag_off = None
        if dragged:
            self._save_here()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self.save_and_close()

    def closeEvent(self, e) -> None:  # noqa: N802
        # Una grandezza ancora in attesa si scrive lo stesso, anche con Esc.
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_here()
        super().closeEvent(e)

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
        # Dal file e non dalla cache: mentre la copia era aperta l'hub puo'
        # aver scritto modalita' e colori.
        cfg = load_config(reload=True)
        cfg.overlay.x, cfg.overlay.y = x, y
        cfg.overlay.scale = self._scale
        ok = save_config(cfg)
        if ok:
            # Scritto da noi: `_follow_config` non lo deve prendere per un
            # cambio arrivato dall'hub.
            self._seen_pos, self._seen_scale = (x, y), clamp_scale(self._scale)
        return ok

    def _save_here(self) -> bool:
        """Salva dove sta la copia adesso. Se non l'hai spostata dalla
        posizione automatica, resta automatica (-1) invece di diventare un
        punto fisso."""
        if self._auto_at is not None and self.pos() == self._auto_at:
            self._saved = self._write(-1, -1)
        else:
            self._saved = self._write(self.x(), self.y())
        return self._saved

    def save_and_close(self) -> None:
        self._save_timer.stop()
        self._save_here()
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

