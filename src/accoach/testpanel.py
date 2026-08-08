"""Il riquadro che guida il protocollo di test in pista.

Nasce da una frase del pilota il 07/08: «non mi ricordo a memoria tutti questi
passaggi». Il protocollo glielo detta Claude a voce — la regola nata
dall'incidente del 02/08 vieta di chiedergli di leggere una chat mentre guida —
ma fra un passo e l'altro non aveva nessun posto dove guardare per ricordarsi
cosa stava facendo e con quali impostazioni.

**Questo riquadro è uno schermo, non un giudice.** Non sa cos'è un bloccaggio,
non conta giri, non decide quando un passo è finito: testo e avanzamento li
scrive Claude da fuori, in `~/Documents/ACCoach/test_step.json`. È quello che lo
rende buono anche per un test inventato lì per lì — ed è successo, il 07/08, con
la semantica di `verify-aids` su ACC.

Gira come processo a sé (`python -m accoach test-panel`) e **non apre la memoria
condivisa**: il 07/08 abbiamo sfiorato l'incidente di due `CoachEngine` accesi
insieme, con ogni giro salvato due volte e la copia indistinguibile da un giro
vero. Un processo che non legge telemetria non può ripeterlo, comunque venga
lanciato. Spegnerlo a fine test è chiuderlo: nessuna opzione da ricordare, quindi
nessuna opzione che resti accesa per sbaglio.

Limite dichiarato: le etichette (`PASSO`, `FATTO`, `in attesa`) sono in italiano
fisso, fuori dall'i18n. Il contenuto dei passi lo scrive Claude in italiano
durante la sessione, e tradurre solo la cornice darebbe un riquadro mezzo
tradotto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import paths

import time

from . import brand
from .theme import DISPLAY, MONO, load_fonts

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QPainter
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:  # pragma: no cover - dipendenza opzionale
    print("Questo riquadro ha bisogno di PySide6:  pip install PySide6")
    raise SystemExit(1)

# Due righe e non tre. Il riquadro ha altezza fissa: il testo che non ci sta
# viene tagliato, perché un riquadro che si allunga sposta la riga dell'orologio
# a ogni cambio di passo — e l'orologio si cerca con la coda dell'occhio, in un
# punto che deve restare lo stesso.
_MAX_BODY_LINES = 2


@dataclass(frozen=True)
class Panel:
    """Le righe già decise, nella forma che il widget deve solo disegnare."""

    where: str = ""
    title: str = ""
    body: tuple[str, ...] = ()
    specs: str = ""
    countdown: str = ""
    note: str = ""
    done: bool = False
    done_msg: str = ""
    waiting: bool = False


def render_step(step: dict | None, now: float) -> Panel:
    """Da un passo letto dal file alle righe da disegnare.

    Pura: nessun file, nessun orologio di sistema, nessun Qt. Tutte le regole
    che si possono sbagliare stanno qui, dove un test le vede in memoria.
    """
    if not step:
        return Panel(waiting=True)

    title = str(step.get("title") or "")
    n, of = step.get("step"), step.get("of")
    where = f"PASSO {n} / {of}" if n and of else ""

    # La scadenza è un istante assoluto, non una durata: così il conto scorre
    # anche quando nessuno sta riscrivendo il file, e una finestra chiusa e
    # riaperta riprende dal punto giusto invece di ricominciare da capo.
    done = bool(step.get("done"))
    countdown = ""
    ends_at = step.get("ends_at")
    if ends_at:
        left = float(ends_at) - now
        if left <= 0:
            # Un contatore che si muove da solo deve sapersi fermare da solo: a
            # `00:00` in attesa di un aggiornamento, il riquadro sarebbe
            # indistinguibile da un'app morta.
            done = True
        else:
            countdown = f"{int(left) // 60:02d}:{int(left) % 60:02d}"

    if done:
        return Panel(where=where, title=title, done=True,
                     done_msg=str(step.get("done_msg") or ""))

    body = tuple(str(step.get("do") or "").splitlines()[:_MAX_BODY_LINES])
    # Orologio e ripetizioni sono due risposte alla stessa domanda — «quanto
    # manca» — e in staccata se ne legge una sola. Se il file le porta entrambe
    # vince l'orologio, perché è quello che si muove.
    note = "" if countdown else str(step.get("note") or "")
    return Panel(where=where, title=title, body=body,
                 specs=str(step.get("specs") or ""),
                 countdown=countdown, note=note)


# Dodici ore. Numero **scelto**, non misurato: nessuna sessione in pista dura
# mezza giornata, e un riavvio a metà serata deve invece ritrovare il passo in
# corso. Serve a un caso solo, ma è un caso che inganna: il file resta sul disco
# a fine sessione, e senza questa regola un riquadro avviato prima del primo
# passo mostrerebbe quello di ieri sera — col suo verde già acceso, e il pilota
# non avrebbe motivo di dubitarne.
_STALE_S = 12 * 3600


def step_path() -> Path:
    """Il file che Claude scrive e il riquadro legge."""
    return paths.base_dir() / "test_step.json"


class StepFile:
    """Il file del passo, letto in modo che non possa mentire.

    Due regole, e sono le uniche due ragioni per cui questa classe esiste invece
    di una `json.loads` in linea:

    * **una lettura andata storta non svuota lo schermo.** Mentre il file viene
      riscritto, per una frazione di secondo il JSON è mezzo scritto; se il
      riquadro lo leggesse e si svuotasse, il pilota vedrebbe il protocollo
      sparire in curva. Il passo di prima resta finché non ne arriva uno valido.
    * **un file vecchio vale come assente** (vedi `_STALE_S`).

    Cancellare il file, invece, svuota: quello è dirglielo.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stamp: tuple[float, int] | None = None
        self._step: dict | None = None

    def read(self, now: float) -> dict | None:
        try:
            st = self._path.stat()
        except OSError:
            self._stamp, self._step = None, None
            return None
        if now - st.st_mtime > _STALE_S:
            self._stamp, self._step = None, None
            return None
        # La dimensione insieme al tempo: su Windows due scritture ravvicinate
        # possono condividere lo stesso mtime, e il secondo passo non si vedrebbe.
        stamp = (st.st_mtime, st.st_size)
        if stamp == self._stamp:
            return self._step
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._step        # mezza scrittura: resta quello di prima
        if not isinstance(data, dict) or not data.get("title"):
            return self._step
        self._stamp, self._step = stamp, data
        return data


# Coordinate di progetto: la finestra è queste misure × la scala salvata.
_BASE_W, _BASE_H = 440, 200
_MARGIN = 24              # distanza dall'angolo dello schermo centrale
_POLL_MS = 500            # ogni quanto si rilegge il file
_TICK_MS = 250            # ogni quanto si ridisegna (l'orologio scala di 1 s)

# Le righe, in coordinate di progetto. Sono costanti e non calcolate dal
# contenuto di proposito: `_CLOCK_Y` è il punto che l'occhio cerca senza
# guardare, e deve restare lo stesso fra un passo di una riga e uno di due.
_WHERE_Y, _TITLE_Y, _BODY_Y, _SPECS_Y, _CLOCK_Y = 14, 34, 74, 118, 148
_BODY_STEP = 22           # distanza fra la prima e la seconda riga del corpo


class TestPanel(QWidget):
    """La finestrella in alto a sinistra dello schermo centrale."""

    # pytest raccoglie per nome (`Test*`), e questa classe non è un test.
    __test__ = False

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        # Stessa ricetta dell'HUD, che è già dimostrata sull'impianto del
        # pilota. `WindowTransparentForInput` non è cosmetica: un riquadro che
        # intercettasse un clic in staccata sarebbe peggio di non averlo.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        from .config import load_config
        scale = load_config().overlay.scale
        self._scale = scale if (scale and scale > 0) else 1.0
        self.resize(int(_BASE_W * self._scale), int(_BASE_H * self._scale))
        self._place()

        self._file = StepFile(path or step_path())
        self._panel = Panel(waiting=True)

        self._poll = QTimer(self)
        self._poll.timeout.connect(self.refresh)
        self._poll.start(_POLL_MS)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self.update)
        self._tick.start(_TICK_MS)

    def _place(self) -> None:
        """L'angolo in alto a sinistra dello schermo che il pilota guarda.

        Lo schermo di riferimento è quello sotto il centro del desktop virtuale:
        è la stessa regola con cui l'HUD si centra (`Overlay._place_top_center`),
        e non se ne introduce una seconda perché due finestre che decidono da
        sole quale sia «quello di mezzo» prima o poi non sono d'accordo.

        Limite dichiarato: con tre monitor uniti in una superficie sola
        (Eyefinity/Surround) Windows ne riporta uno largo quanto tutti e tre, e
        questa regola atterra sul pannello di sinistra. Sull'impianto del pilota,
        misurato l'08/08, i display sono tre separati da 2560×1440.
        """
        prim = QApplication.primaryScreen()
        if prim is None:                       # pragma: no cover - senza schermi
            return
        screen = QApplication.screenAt(prim.virtualGeometry().center()) or prim
        g = screen.geometry()
        self.move(g.left() + _MARGIN, g.top() + _MARGIN)

    def refresh(self) -> None:
        """Rilegge il file e ricalcola le righe. Chiamato dal timer."""
        now = time.time()
        self._panel = render_step(self._file.read(now), now)
        self.update()

    # --- disegno -----------------------------------------------------------
    def _font(self, p: QPainter, size: int, bold: bool = False,
              mono: bool = False) -> None:
        f = QFont(MONO if mono else DISPLAY, size)
        f.setStyleHint(QFont.Monospace if mono else QFont.SansSerif)
        f.setBold(bold)
        p.setFont(f)

    def _text(self, p: QPainter, x: int, y: int, w: int, h: int,
              flags, text: str) -> None:
        """Un solo punto per tutto il testo, così i test possono spiarlo.

        Senza flag di a-capo di proposito: il testo che non ci sta viene
        tagliato, e il riquadro non cresce.
        """
        p.drawText(x, y, w, h, flags, text)

    def paintEvent(self, _event) -> None:  # noqa: N802 (nomenclatura Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._scale != 1.0:
            p.scale(self._scale, self._scale)

        back = QColor(brand.INK)
        back.setAlpha(190)
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(0, 0, _BASE_W, _BASE_H, 10, 10)

        pan = self._panel
        if pan.waiting:
            self._font(p, 15, bold=True)
            p.setPen(QColor(brand.MUTED))
            self._text(p, 16, _TITLE_Y, _BASE_W - 32, 30, Qt.AlignLeft,
                       "in attesa del prossimo passo")
            return

        if pan.where:
            self._font(p, 11, bold=True)
            p.setPen(QColor(brand.MUTED))
            self._text(p, 16, _WHERE_Y, _BASE_W - 32, 16, Qt.AlignLeft, pan.where)

        if pan.done:
            self._font(p, 20, bold=True)
            p.setPen(QColor(brand.GREEN))
            self._text(p, 16, _TITLE_Y, _BASE_W - 32, 32, Qt.AlignLeft,
                       f"✓ FATTO — {pan.title}")
            if pan.done_msg:
                self._font(p, 14)
                p.setPen(QColor(brand.MUTED))
                self._text(p, 16, _BODY_Y, _BASE_W - 32, 20, Qt.AlignLeft,
                           pan.done_msg)
            return

        self._font(p, 22, bold=True)
        p.setPen(QColor(brand.CYAN))
        self._text(p, 16, _TITLE_Y, _BASE_W - 32, 32, Qt.AlignLeft, pan.title)

        self._font(p, 14)
        p.setPen(QColor(brand.TEXT))
        for i, line in enumerate(pan.body):
            self._text(p, 16, _BODY_Y + i * _BODY_STEP, _BASE_W - 32, 20,
                       Qt.AlignLeft, line)

        if pan.specs:
            self._font(p, 12)
            p.setPen(QColor(brand.MUTED))
            self._text(p, 16, _SPECS_Y, _BASE_W - 32, 18, Qt.AlignLeft, pan.specs)

        if pan.countdown:
            self._font(p, 26, bold=True, mono=True)
            p.setPen(QColor(brand.CYAN))
            self._text(p, 16, _CLOCK_Y, _BASE_W - 32, 36, Qt.AlignLeft,
                       pan.countdown)
        elif pan.note:
            self._font(p, 18, bold=True, mono=True)
            p.setPen(QColor(brand.TEXT))
            self._text(p, 16, _CLOCK_Y, _BASE_W - 32, 36, Qt.AlignLeft, pan.note)
