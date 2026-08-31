# Riquadro guida-test — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una finestrella in alto a sinistra dello schermo centrale che mostra il passo di protocollo in corso durante i test in pista — cosa fare, con quali impostazioni, quanto manca — e diventa verde quando il passo è finito.

**Architecture:** Un processo a sé (`python -m accoach test-panel`) che non apre la memoria condivisa, non parla col motore e non apre socket: legge un file JSON scritto da fuori e lo disegna. Dentro il modulo tre unità con confini netti — `StepFile` (legge il file e applica le due regole di sicurezza), `render_step()` (funzione pura: da passo a righe da disegnare), `TestPanel` (widget Qt che dipinge un `Panel` e possiede timer e posizione). Le prime due non toccano Qt, quindi si testano in memoria; la terza si dipinge fuori schermo.

**Tech Stack:** Python ≥ 3.11, PySide6 (dipendenza opzionale del frontend), pytest.

**Spec:** `docs/superpowers/specs/2026-08-08-riquadro-guida-test-design.md`

## Global Constraints

- **Il riquadro non contiene nessuna regola di protocollo.** Non conta giri, non riconosce eventi, non decide quando un passo è finito — tranne la scadenza dell'orologio, che è aritmetica sul suo stesso campo. Tutto il resto arriva dal file.
- **Non deve mai rubare il fuoco al gioco:** `FramelessWindowHint | WindowStaysOnTopHint | Qt.Tool`, `WA_TranslucentBackground`, `WindowTransparentForInput`, `WA_TransparentForMouseEvents`.
- **Non importa `accoach.engine`, `accoach.telemetry` né apre socket.** È la proprietà che rende impossibile ripetere il quasi-incidente dei due `CoachEngine` accesi (07/08).
- **File del passo:** `paths.base_dir() / "test_step.json"`, cioè `~/Documents/ACCoach/test_step.json`.
- **Soglia del fantasma:** `_STALE_S = 12 * 3600`. Numero **scelto**, non misurato — va detto nel commento.
- **Colori:** da `accoach.brand` (`CYAN`, `GREEN`, `TEXT`, `MUTED`, `INK`), passati a `QColor(...)` come stringhe esadecimali. Non ricopiare valori a mano.
- **Font:** `accoach.theme.DISPLAY` e `MONO`, con `load_fonts()` chiamato in `main()`.
- **Lingua:** commenti e docstring in italiano, come i moduli recenti; le etichette sullo schermo (`PASSO`, `FATTO`, `in attesa`) sono in italiano **fisso, senza i18n** — il contenuto dei passi lo scrive Claude in italiano durante la sessione, e tradurre solo la cornice darebbe un riquadro mezzo tradotto. Va scritto come limite dichiarato nel docstring del modulo.
- **Stile:** righe ≤ 88 colonne, come il codice intorno. Nessun linter configurato nel repo.
- **Test:** `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` **prima** di importare PySide6, e `pytest.importorskip("PySide6")`, come in `tests/test_overlay_paint.py`.

---

### Task 1: `render_step()` — da passo a righe, senza Qt

**Files:**
- Create: `src/accoach/testpanel.py`
- Test: `tests/test_testpanel_render.py`

**Interfaces:**
- Consumes: niente.
- Produces:
  - `@dataclass(frozen=True) class Panel` con campi `where: str`, `title: str`, `body: tuple[str, ...]`, `specs: str`, `countdown: str`, `note: str`, `done: bool`, `done_msg: str`, `waiting: bool` (tutti con default `""` / `()` / `False`).
  - `render_step(step: dict | None, now: float) -> Panel`
  - `_MAX_BODY_LINES: int = 2`

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `tests/test_testpanel_render.py`:

```python
"""Da passo a righe: la funzione che decide cosa finisce sullo schermo.

Pura di proposito — niente Qt, niente file. Le regole che contano davvero
(l'orologio che scade da solo, le due risposte che non convivono, il testo che
viene tagliato invece di allungare il riquadro) si verificano qui in memoria, e
al widget resta da dimostrare solo che le disegna dove ha detto.
"""
from accoach.testpanel import render_step


def test_senza_passo_il_riquadro_e_in_attesa():
    p = render_step(None, now=1000.0)
    assert p.waiting is True
    assert p.title == ""


def test_il_titolo_e_la_posizione_nel_protocollo():
    p = render_step({"title": "BLOCCAGGI", "step": 3, "of": 7}, now=1000.0)
    assert p.title == "BLOCCAGGI"
    assert p.where == "PASSO 3 / 7"


def test_senza_numerazione_non_si_inventa_una_posizione():
    p = render_step({"title": "BLOCCAGGI"}, now=1000.0)
    assert p.where == ""


def test_orologio_in_minuti_e_secondi():
    # 767 s = 12:47
    p = render_step({"title": "STINT", "ends_at": 1767.0}, now=1000.0)
    assert p.countdown == "12:47"
    assert p.done is False


def test_lo_zero_iniziale_c_e_sempre():
    """Un campo che cambia larghezza si sposta sotto l'occhio: 5:05 mai."""
    p = render_step({"title": "STINT", "ends_at": 1305.0}, now=1000.0)
    assert p.countdown == "05:05"


def test_scaduto_significa_fatto_senza_che_nessuno_lo_dica():
    p = render_step({"title": "STINT", "ends_at": 1000.0}, now=1000.0)
    assert p.done is True
    assert p.countdown == ""


def test_resta_fatto_anche_molto_dopo():
    """Il verde non scade a sua volta: mezz'ora dopo è ancora lì."""
    p = render_step({"title": "STINT", "ends_at": 1000.0}, now=2800.0)
    assert p.done is True


def test_un_passo_senza_orologio_si_dichiara_finito_a_mano():
    p = render_step({"title": "BLOCCAGGI", "done": True,
                     "done_msg": "Aspetta il prossimo passo"}, now=1000.0)
    assert p.done is True
    assert p.done_msg == "Aspetta il prossimo passo"


def test_il_verde_non_porta_con_se_il_corpo_del_passo():
    p = render_step({"title": "BLOCCAGGI", "do": "Frena forte",
                     "specs": "ABS 0", "done": True}, now=1000.0)
    assert p.body == ()
    assert p.specs == ""


def test_le_ripetizioni_quando_non_c_e_orologio():
    p = render_step({"title": "BLOCCAGGI", "note": "1 di 3"}, now=1000.0)
    assert p.note == "1 di 3"
    assert p.countdown == ""


def test_mai_due_risposte_alla_stessa_domanda():
    """Orologio e ripetizioni insieme: in staccata se ne legge una sola."""
    p = render_step({"title": "STINT", "ends_at": 1767.0, "note": "1 di 3"},
                    now=1000.0)
    assert p.countdown == "12:47"
    assert p.note == ""


def test_il_corpo_si_ferma_a_due_righe():
    p = render_step({"title": "X", "do": "una\ndue\ntre\nquattro"}, now=1000.0)
    assert p.body == ("una", "due")


def test_i_campi_che_mancano_non_diventano_stringhe_none():
    p = render_step({"title": "X"}, now=1000.0)
    assert (p.body, p.specs, p.note, p.countdown, p.done_msg) == ((), "", "", "", "")
```

- [ ] **Step 2: Eseguirli e vederli fallire**

Run: `python -m pytest tests/test_testpanel_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'accoach.testpanel'`

- [ ] **Step 3: Scrivere il modulo con la sola parte pura**

Creare `src/accoach/testpanel.py`:

```python
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

from dataclasses import dataclass

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
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `python -m pytest tests/test_testpanel_render.py -v`
Expected: PASS — 13 test.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/testpanel.py tests/test_testpanel_render.py
git commit -m "Da passo a righe: la parte del riquadro test che si può sbagliare"
```

---

### Task 2: `StepFile` — le due letture che possono ingannare

**Files:**
- Modify: `src/accoach/testpanel.py`
- Test: `tests/test_testpanel_file.py`

**Interfaces:**
- Consumes: niente dal Task 1 (unità indipendente nello stesso modulo).
- Produces:
  - `_STALE_S: int = 12 * 3600`
  - `step_path() -> Path` — `paths.base_dir() / "test_step.json"`
  - `class StepFile` con `__init__(self, path: Path)` e `read(self, now: float) -> dict | None`

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `tests/test_testpanel_file.py`:

```python
"""Le due letture che possono ingannare il pilota.

Un file letto mentre lo si sta scrivendo è un file rotto per una frazione di
secondo, e un file rimasto da ieri sera è un protocollo che non è più vero. Sono
i due modi in cui questo riquadro potrebbe mettere in pista una bugia
convincente, e sono l'unico motivo per cui `StepFile` esiste invece di una
`json.loads` in linea.
"""
import json
import os
import time

from accoach.testpanel import _STALE_S, StepFile


def _write(path, **step):
    path.write_text(json.dumps({"title": "X", **step}), encoding="utf-8")


def test_senza_file_non_c_e_passo(tmp_path):
    assert StepFile(tmp_path / "mai-scritto.json").read(now=1000.0) is None


def test_legge_il_passo(tmp_path):
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    assert StepFile(p).read(now=os.path.getmtime(p))["title"] == "BLOCCAGGI"


def test_un_json_a_meta_lascia_sullo_schermo_quello_di_prima(tmp_path):
    """Il caso vero: si sta riscrivendo il file mentre il riquadro lo legge."""
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    sf = StepFile(p)
    now = os.path.getmtime(p)
    assert sf.read(now)["title"] == "BLOCCAGGI"

    p.write_text('{"title": "STI', encoding="utf-8")   # scrittura a metà
    os.utime(p, (now + 1, now + 1))
    assert sf.read(now + 1)["title"] == "BLOCCAGGI"


def test_un_passo_senza_titolo_non_sostituisce_quello_buono(tmp_path):
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    sf = StepFile(p)
    now = os.path.getmtime(p)
    sf.read(now)

    p.write_text('{"do": "solo il corpo"}', encoding="utf-8")
    os.utime(p, (now + 1, now + 1))
    assert sf.read(now + 1)["title"] == "BLOCCAGGI"


def test_il_fantasma_di_ieri_sera_vale_come_assente(tmp_path):
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI", done=True)
    # Date vere e non un epoch 0: su Windows le date agli albori del 1970 sono
    # un modo di far fallire il test per il filesystem invece che per la regola.
    now = time.time()
    os.utime(p, (now - _STALE_S - 1, now - _STALE_S - 1))
    assert StepFile(p).read(now) is None


def test_dentro_le_dodici_ore_il_passo_vale_ancora(tmp_path):
    """Un riavvio a metà serata deve ritrovare il passo in corso."""
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    now = time.time()
    os.utime(p, (now - _STALE_S + 60, now - _STALE_S + 60))
    assert StepFile(p).read(now)["title"] == "BLOCCAGGI"


def test_il_file_cancellato_svuota_il_riquadro(tmp_path):
    """Cancellarlo è dirglielo, e va distinto da una lettura andata storta."""
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    sf = StepFile(p)
    sf.read(os.path.getmtime(p))
    p.unlink()
    assert sf.read(now=2000.0) is None


def test_due_scritture_diverse_nello_stesso_istante_si_vedono_entrambe(tmp_path):
    """Su Windows due `write` ravvicinate possono condividere lo stesso mtime."""
    p = tmp_path / "s.json"
    _write(p, title="PRIMO")
    sf = StepFile(p)
    now = os.path.getmtime(p)
    assert sf.read(now)["title"] == "PRIMO"

    _write(p, title="SECONDO", do="una riga in più che cambia la dimensione")
    os.utime(p, (now, now))                     # stesso mtime, di proposito
    assert sf.read(now)["title"] == "SECONDO"
```

- [ ] **Step 2: Eseguirli e vederli fallire**

Run: `python -m pytest tests/test_testpanel_file.py -v`
Expected: FAIL — `ImportError: cannot import name '_STALE_S' from 'accoach.testpanel'`

- [ ] **Step 3: Aggiungere `StepFile` al modulo**

In `src/accoach/testpanel.py`, aggiungere agli import in cima:

```python
import json
from pathlib import Path

from . import paths
```

e in fondo al modulo:

```python
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
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `python -m pytest tests/test_testpanel_file.py tests/test_testpanel_render.py -v`
Expected: PASS — 21 test.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/testpanel.py tests/test_testpanel_file.py
git commit -m "Il file del passo letto in modo che non possa mentire"
```

---

### Task 3: `TestPanel` — il widget, e l'orologio che non si sposta

**Files:**
- Modify: `src/accoach/testpanel.py`
- Test: `tests/test_testpanel_paint.py`

**Interfaces:**
- Consumes: `Panel`, `render_step()` (Task 1), `StepFile`, `step_path()` (Task 2).
- Produces:
  - `_BASE_W: int = 440`, `_BASE_H: int = 200`, `_CLOCK_Y: int = 148`
  - `class TestPanel(QWidget)` con `__init__(self, path: Path | None = None)`, l'attributo `_panel: Panel` e il metodo `refresh(self) -> None`

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `tests/test_testpanel_paint.py`:

```python
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

from accoach.testpanel import Panel, TestPanel            # noqa: E402


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
    assert corto.height() == lungo.height()
    corto.deleteLater()
    lungo.deleteLater()
```

- [ ] **Step 2: Eseguirli e vederli fallire**

Run: `python -m pytest tests/test_testpanel_paint.py -v`
Expected: FAIL — `ImportError: cannot import name 'TestPanel' from 'accoach.testpanel'`

- [ ] **Step 3: Aggiungere il widget**

In `src/accoach/testpanel.py`, dopo gli import esistenti:

```python
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
```

e in fondo al modulo:

```python
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
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `python -m pytest tests/test_testpanel_paint.py -v`
Expected: PASS — 7 test.

Se `test_il_verde_e_verde_davvero_sullo_schermo` fallisce, il difetto è nel disegno, non nel test: il verde è stato chiesto ma non arriva sul pixel. Controllare l'ordine di `setPen` rispetto a `_text` e che il rettangolo di fondo non venga ridisegnato dopo.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/testpanel.py tests/test_testpanel_paint.py
git commit -m "Il riquadro dipinto, e l'orologio che non si sposta sotto l'occhio"
```

---

### Task 4: `main()` e il comando `test-panel`

**Files:**
- Modify: `src/accoach/testpanel.py`
- Modify: `src/accoach/__main__.py` (blocco dispatch intorno a `elif cmd == "overlay":`, e `_HELP_TOOLS`)
- Test: `tests/test_cli.py` (esistente, non va modificato — verifica già che ogni comando spedito sia documentato)

**Interfaces:**
- Consumes: `TestPanel` (Task 3).
- Produces: `main(argv: list[str] | None = None) -> None`

- [ ] **Step 1: Verificare che il test del CLI fallisca appena il comando esiste senza documentazione**

Aggiungere **solo** il ramo di dispatch in `src/accoach/__main__.py`, subito dopo il blocco `overlay`:

```python
    elif cmd == "test-panel":
        from .testpanel import main as run
        run(rest)
```

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL su `test_every_dispatched_command_is_documented_somewhere` con `AssertionError: test-panel`

Questo è il punto: la protezione contro un comando che esiste e che nessuno sa di avere è già nel repo e va vista scattare.

- [ ] **Step 2: Documentare il comando**

In `_HELP_TOOLS`, in fondo, prima della chiusura `"""`:

```
  test-panel                 step-by-step panel for on-track test protocols
                             (reads test_step.json; opens no telemetry, no socket)
```

- [ ] **Step 3: Eseguire il test del CLI e vederlo passare**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 4: Aggiungere `main()` al modulo**

In fondo a `src/accoach/testpanel.py`:

```python
def main(argv: list[str] | None = None) -> None:
    import signal
    import sys

    app = QApplication(sys.argv)
    load_fonts()                     # il riquadro dipinge nel carattere HONE
    # Lascia passare Ctrl+C dal terminale che l'ha avviato: senza un timer che
    # ogni tanto restituisce il controllo a Python, Qt resta nel suo loop e il
    # segnale non viene mai gestito. Stessa ragione e stesso trucco dell'HUD.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)

    panel = TestPanel()
    panel.refresh()                  # non aspettare mezzo secondo per il primo
    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Provare che parte davvero**

Run: `python -c "import accoach.testpanel as m; print(m.step_path())"`
Expected: stampa `C:\Users\...\Documents\ACCoach\test_step.json`

Run: `python -m pytest tests/ -q`
Expected: l'intera suite passa, nessuna regressione.

- [ ] **Step 6: Commit**

```bash
git add src/accoach/testpanel.py src/accoach/__main__.py
git commit -m "Il comando che accende il riquadro, e l'aiuto che dice che esiste"
```

---

### Task 5: Verifica sull'impianto vero

Quello che i test non possono dimostrare. Nessun codice: si guarda.

**Files:** nessuno (eventuali correzioni tornano ai task precedenti).

- [ ] **Step 1: Accendere il riquadro senza gioco**

```bash
python -m accoach test-panel
```

Expected: finestra in alto a sinistra dello schermo **centrale** (X 0-2560), con «in attesa del prossimo passo».

- [ ] **Step 2: Scrivere un passo e vederlo comparire entro mezzo secondo**

Scrivere `~/Documents/ACCoach/test_step.json` con un `ends_at` a due minuti da adesso, poi verificare con uno screenshot della finestra (computer-use) che l'orologio scali da solo senza altre scritture.

- [ ] **Step 3: Vedere arrivare il verde da solo**

Aspettare la scadenza. Expected: `✓ FATTO`, e **resta** — riguardare dopo qualche minuto.

- [ ] **Step 4: Con ACC in borderless, verificare che non rubi il fuoco**

Expected: il gioco continua a ricevere i comandi, la finestra sta sopra e non si può cliccare.

- [ ] **Step 5: La domanda che conta**

Con l'auto in movimento: il titolo si legge con la coda dell'occhio? L'orologio si trova senza cercarlo? Se no, si torna alle costanti di `_BASE_W` e delle dimensioni di carattere — è il tipo di difetto che in questo progetto l'ha sempre trovato lo schermo su giri veri, mai la suite.

- [ ] **Step 6: Annotare l'esito**

Nel verbale della sessione, con gli screenshot in `Documents/ACCoach/audit/`.

---

## Note per chi implementa

**Non aggiungere niente che il piano non chieda.** In particolare: nessuna opzione in `config.toml`, nessun bottone, nessuna animazione, nessun i18n, nessun aggancio a `web/test_plan.json`. Il riquadro esiste quando il processo gira e sparisce quando lo si chiude — è così che il pilota ha chiesto di spegnerlo a fine test.

**Il riquadro non deve mai affermare più di quel che sa.** Il verde dice «FATTO» (il passo è finito), mai «OK» o «SUPERATO» (HONE si è comportato bene): quel giudizio è di chi guarda i dati, non della finestra. In questo progetto uno schermo che afferma una cosa che non ha misurato è il difetto ricorrente.

**Se `render_step` cresce oltre una schermata**, è il segnale che una regola di protocollo si sta infilando dentro il riquadro. Va tolta e rimessa in chi scrive il file.
