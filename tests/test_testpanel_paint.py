"""Il riquadro dipinto davvero.

Come `tests/test_overlay_paint.py`: si dipinge il widget vero fuori schermo e si
guarda cosa ha chiesto al pennello, invece di riscrivere nel test la logica da
verificare. Due cose qui il pennello le sa e una funzione pura no — che
l'orologio cada sempre allo stesso pixel qualunque sia la lunghezza del passo, e
che il verde del «fatto» sia davvero un verde sullo schermo e non una stringa
chiesta e finita invisibile. Nel progetto è già successo: chiedere non è
mostrare.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                            # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPixmap                 # noqa: E402
from PySide6.QtWidgets import QApplication                # noqa: E402

from accoach import testpanel as tp_mod                    # noqa: E402
from accoach.testpanel import Panel, TestPanel             # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _texts_drawn(app, panel: Panel) -> list[tuple[int, str]]:
    """Dipinge un `Panel` e restituisce le coppie (y, testo) chieste."""
    asked: list[tuple[int, str]] = []
    w = TestPanel()
    w._panel = panel
    real = w._text

    def spy(p, x, y, width, height, flags, text):
        if text:
            asked.append((y, text))
        return real(p, x, y, width, height, flags, text)

    w._text = spy
    w.render(QPixmap(w.size()))
    w.deleteLater()
    return asked


def _pixels(app, panel: Panel) -> QPixmap:
    w = TestPanel()
    w._panel = panel
    pm = QPixmap(w.size())
    w.render(pm)
    w.deleteLater()
    return pm


def test_in_attesa_quando_non_c_e_niente(app):
    texts = [t for _, t in _texts_drawn(app, Panel(waiting=True))]
    assert any("attesa" in t for t in texts)


def test_il_passo_finisce_sullo_schermo(app):
    p = Panel(where="PASSO 3 / 7", title="BLOCCAGGI",
              body=("Frena fortissimo in staccata",), specs="ABS 0 · TC 6",
              countdown="12:47")
    texts = [t for _, t in _texts_drawn(app, p)]
    assert "PASSO 3 / 7" in texts
    assert "BLOCCAGGI" in texts
    assert "Frena fortissimo in staccata" in texts
    assert "ABS 0 · TC 6" in texts
    assert "12:47" in texts


def test_l_orologio_non_si_sposta_fra_un_passo_e_l_altro(app):
    """L'asserzione che conta: non «il riquadro è alto uguale», ma «l'orologio
    non si è mosso sotto l'occhio»."""
    corto = Panel(title="X", body=("una riga",), countdown="12:47")
    lungo = Panel(title="X", body=("una riga", "e una seconda"),
                  specs="ABS 0", countdown="12:47")
    y_corto = [y for y, t in _texts_drawn(app, corto) if t == "12:47"]
    y_lungo = [y for y, t in _texts_drawn(app, lungo) if t == "12:47"]
    assert y_corto == y_lungo != []


def test_le_ripetizioni_stanno_dove_stava_l_orologio(app):
    orologio = Panel(title="X", countdown="12:47")
    ripetizioni = Panel(title="X", note="1 di 3")
    y_a = [y for y, t in _texts_drawn(app, orologio) if t == "12:47"]
    y_b = [y for y, t in _texts_drawn(app, ripetizioni) if t == "1 di 3"]
    assert y_a == y_b != []


def test_il_fatto_dice_fatto_e_non_superato(app):
    texts = [t for _, t in _texts_drawn(app, Panel(title="BLOCCAGGI", done=True))]
    assert any("FATTO" in t for t in texts)
    assert not any("OK" in t or "SUPERATO" in t for t in texts)


def test_il_verde_e_verde_davvero_sullo_schermo(app):
    """Una stringa può essere chiesta correttamente e finire invisibile."""
    from accoach import brand

    pm = _pixels(app, Panel(title="BLOCCAGGI", done=True))
    img = pm.toImage()
    target = QColor(brand.GREEN)
    found = False
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if (abs(c.red() - target.red()) < 40
                    and abs(c.green() - target.green()) < 40
                    and abs(c.blue() - target.blue()) < 40):
                found = True
                break
        if found:
            break
    assert found, "il «fatto» è stato chiesto ma non si vede"


def test_l_altezza_della_finestra_non_dipende_dal_passo(app):
    corto = TestPanel()
    corto._panel = Panel(title="X")
    lungo = TestPanel()
    lungo._panel = Panel(title="X", body=("a", "b"), specs="ABS 0",
                         countdown="12:47")
    # Il confronto vale solo dopo un disegno vero: prima di `render()` l'altezza
    # è già fissata dall'`__init__` e il test non vedrebbe mai un ridimensionamento
    # a tempo di paint (es. un `paintEvent` che si allunga col contenuto).
    corto.render(QPixmap(corto.size()))
    lungo.render(QPixmap(lungo.size()))
    assert corto.height() == lungo.height()
    corto.deleteLater()
    lungo.deleteLater()


def test_refresh_porta_il_file_sullo_schermo(app, tmp_path, monkeypatch):
    """Il punto in cui `StepFile` e il widget si toccano davvero: `refresh()`
    deve rileggere il file passato a `path` (non ignorarlo) e finire nello
    stesso `Panel` che `paintEvent` disegna. Ogni altro test qui assegna
    `_panel` a mano, scavalcando questo cablaggio — ed è il punto da cui
    dipenderà anche il CLI del prossimo task.

    Il ripiego deve puntare nel vuoto: senza questo, un `path` ignorato
    leggerebbe il file VERO del pilota — che durante una sessione esiste, e
    porta proprio questo titolo."""
    f = tmp_path / "test_step.json"
    f.write_text('{"title": "BLOCCAGGI"}', encoding="utf-8")
    monkeypatch.setattr(tp_mod, "step_path", lambda: tmp_path / "mai-scritto.json")
    w = TestPanel(f)
    w.refresh()
    assert w._panel.title == "BLOCCAGGI"
    w.deleteLater()
