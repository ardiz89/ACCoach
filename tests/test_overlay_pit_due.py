"""L'avviso di rientro ai box, dipinto davvero.

Come `test_overlay_paint.py`: si dipinge il widget vero e si guarda quali
stringhe chiede, invece di riscrivere nel test la logica da verificare. Qui
serve una cosa in più — l'avviso **non deve scadere** — e una scadenza si vede
solo facendo passare il tempo: l'orologio che `overlay.py` guarda viene
sostituito da uno finto che si può spostare in avanti a mano.

Il pennello non basta a dire che il pilota la vede: la chiave i18n può essere
chiesta e finire fuori schermo, sotto un altro elemento o di un colore
invisibile. Per questo due test guardano il **pixel** della barretta ambra nella
banda della pastiglia, sull'immagine renderizzata davvero.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections import namedtuple                       # noqa: E402

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPixmap                # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from accoach import overlay as ov_mod                    # noqa: E402
from accoach.overlay import _AMBER, _RED, CUE_HOLD_S, Overlay   # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Clock:
    """L'orologio visto da `overlay.py`, che si può spostare in avanti.

    Si sostituisce il modulo `time` dentro `overlay` — non `time.monotonic`
    globale, che sarebbe patchato per tutti (pytest compreso) per la durata del
    test.
    """

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


_BASE = {"connected": True, "speed_kmh": 150.0,
         "delta": {"s": 0.1, "text": "+0.100", "ahead": False}}

_CUE = {"message": "Bloccaggio, alleggerisci il freno", "category": "locked"}

# Il controllo interno dei test dell'assenza. Asserire che una chiave *non* c'è
# è verde anche su un insieme vuoto: se la spia non fosse installata, o `render`
# non dipingesse niente, quei test resterebbero verdi senza misurare più nulla.
# Il focus si disegna **dopo** la banda della pastiglia (`paintEvent` chiama
# `_draw_focus` subito sotto), quindi la sua chiave nello stesso frame dice che
# la pittura è arrivata oltre il punto che quei test guardano. Sta a y 170, sotto
# la banda: non la tocca, e i test del pixel non lo usano.
_FOCUS = {"focus": {"focus": {"name": "Variante Ascari", "theme": "frenata",
                              "baseline_ms": 180.0}}}
_CONTROL_KEY = "overlay.focus"

# La banda della pastiglia: la barretta d'accento sta a x 20-24, y 126-162 in
# coordinate base. Questo punto è dentro, lontano dagli angoli arrotondati.
_ACCENT_X, _ACCENT_Y = 22, 144

# Quanto si aspetta nel test della dissolvenza: due ordini di grandezza oltre la
# durata di una pastiglia, non un margine.
_LONG_WAIT_S = 120.0

_Frame = namedtuple("_Frame", "keys cue_texts accent")


def _paint(monkeypatch, state: dict, wait_s: float = 0.0) -> _Frame:
    """Dipinge un frame vero e riporta cosa è successo.

    - `keys`: le chiavi i18n chieste durante la pittura;
    - `cue_texts`: i testi che `_draw_cue` ha effettivamente disegnato;
    - `accent`: il colore del pixel al centro della barretta della pastiglia.
    """
    clock = _Clock()
    monkeypatch.setattr(ov_mod, "time", clock)

    asked: set = set()
    real_t = ov_mod.t

    def spy_t(key, *a, **kw):
        asked.add(key)
        return real_t(key, *a, **kw)

    monkeypatch.setattr(ov_mod, "t", spy_t)

    o = Overlay(pedals=False)
    o.apply_state(dict(state))
    clock.now += wait_s

    cue_texts: list = []
    real_cue = o._draw_cue

    def spy_cue(p, w):
        orig_text = p.drawText

        def grab(*a, **kw):
            if a and isinstance(a[-1], str):
                cue_texts.append(a[-1])
            return orig_text(*a, **kw)

        p.drawText = grab
        try:
            return real_cue(p, w)
        finally:
            # Senza questo, `grab` tiene un riferimento al painter che lo tiene:
            # il QPainter sopravvive a paintEvent e viene distrutto più tardi su
            # un device già morto — un crash in un test che non c'entra niente.
            del p.drawText

    o._draw_cue = spy_cue
    pm = QPixmap(o.size())
    pm.fill(QColor(0, 0, 0))          # fondo noto: il widget è traslucido
    o.render(pm)
    del o._draw_cue
    img = pm.toImage()
    scale = o._scale
    o.deleteLater()
    accent = img.pixelColor(int(_ACCENT_X * scale), int(_ACCENT_Y * scale))
    return _Frame(asked, cue_texts, accent)


def _keys_drawn(monkeypatch, state: dict, wait_s: float = 0.0) -> set:
    return _paint(monkeypatch, state, wait_s).keys


# --- c'è quando serve, non c'è quando non serve ----------------------------

def test_the_warning_is_asked_for_while_you_are_due_in(app, monkeypatch):
    assert "overlay.pit_due" in _keys_drawn(monkeypatch, {**_BASE, "pit_due": True})


def test_no_warning_when_nothing_is_due(app, monkeypatch):
    """Niente segnaposto spento che occupa la riga quando il rientro non serve."""
    keys = _keys_drawn(monkeypatch, {**_BASE, **_FOCUS})
    assert _CONTROL_KEY in keys, "il frame è stato dipinto davvero (vedi _FOCUS)"
    assert "overlay.pit_due" not in keys


def test_no_warning_when_the_call_is_over(app, monkeypatch):
    """`pit_due` falsa (sei entrato in corsia) spegne l'avviso come la chiave
    mancante: qui il difetto sarebbe un `in` al posto di un test di verità."""
    keys = _keys_drawn(monkeypatch, {**_BASE, **_FOCUS, "pit_due": False})
    assert _CONTROL_KEY in keys, "il frame è stato dipinto davvero (vedi _FOCUS)"
    assert "overlay.pit_due" not in keys


def test_no_warning_on_a_disconnected_hud(app, monkeypatch):
    """Gioco chiuso, fermo ancora armato: l'avviso non deve galleggiare.

    Non è un caso di scuola. Se il gioco sparisce mentre devi rientrare,
    `PitCall.update` esce alla prima riga senza disarmare il fermo, quindi il
    payload continua a dire `pit_due` vero con `connected` falso a tempo
    indefinito. L'unica cosa che tiene «RIENTRA AI BOX» fuori da un HUD
    scollegato è la **posizione del `return`** nel ramo «in attesa» di
    `paintEvent`: nessun'altra guardia esiste, e nessun altro test la difende.
    """
    frame = _paint(monkeypatch, {**_BASE, "connected": False, "pit_due": True})
    assert "overlay.waiting" in frame.keys, "il ramo scollegato è stato dipinto"
    assert "overlay.pit_due" not in frame.keys
    assert frame.accent != _AMBER, "e nemmeno la banda ambra è accesa"


# --- il difetto che stiamo correggendo -------------------------------------

def test_the_warning_does_not_fade(app, monkeypatch):
    """Dipinta molto dopo la durata di una pastiglia, la parola c'è ancora.

    È il difetto che stiamo correggendo, quindi è il test che conta: due minuti
    d'orologio simulato contro i pochi secondi di un consiglio di guida.
    """
    assert _LONG_WAIT_S > CUE_HOLD_S * 20, "l'attesa deve superare di molto la pastiglia"
    frame = _paint(monkeypatch, {**_BASE, "pit_due": True}, wait_s=_LONG_WAIT_S)
    assert "overlay.pit_due" in frame.keys
    assert frame.accent == _AMBER, "e non solo chiesta: ancora accesa sullo schermo"


# --- gerarchia: il rientro batte il consiglio di guida ---------------------

def test_a_driving_cue_does_not_cover_it(app, monkeypatch):
    """Con un cue appena arrivato E il rientro dovuto, la riga è dell'avviso."""
    frame = _paint(monkeypatch, {**_BASE, "pit_due": True, "cue": _CUE})
    assert "overlay.pit_due" in frame.keys
    assert frame.cue_texts == [], "il consiglio non deve scrivere nella banda"
    assert frame.accent == _AMBER


def test_without_the_call_the_cue_keeps_the_line(app, monkeypatch):
    """L'altra metà: l'avviso cede la banda quando non c'è nessun rientro.

    Il pixel dice anche che la banda è **la stessa** — lì c'è l'accento rosso
    del cue, nello stesso punto in cui l'avviso mette il suo ambra.
    """
    frame = _paint(monkeypatch, {**_BASE, "cue": _CUE})
    assert _CUE["message"] in frame.cue_texts
    assert frame.accent == _RED


# --- quello che i pixel sanno e le chiavi i18n no --------------------------

def test_the_warning_is_painted_in_the_pill_band(app, monkeypatch):
    """La chiave chiesta non dice dove finisce la parola: questo guarda il
    pixel al centro della barretta, nella banda della pastiglia."""
    lit = _paint(monkeypatch, {**_BASE, "pit_due": True}).accent
    dark = _paint(monkeypatch, _BASE).accent
    assert lit == _AMBER
    assert dark != _AMBER
