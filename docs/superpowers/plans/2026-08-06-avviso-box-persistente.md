# L'avviso di rientro che non se ne va — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** quando il coach chiama il rientro ai box, l'avviso resta a schermo finché non entri in corsia — invece di sfumare in 1,8 secondi come un consiglio qualunque.

**Architettura:** il rientro smette di essere *solo* un evento e diventa anche una **condizione**. `PitCall` tiene un fermo che si arma quando il richiamo parte e si disarma quando entri in corsia (o quando il rientro non serve più); il motore lo espone in `EngineState`, il server lo serializza, l'overlay lo disegna al posto della pastiglia dei consigli finché è attivo.

**Tech Stack:** Python 3.11+, PySide6 (overlay, `QT_QPA_PLATFORM=offscreen` nei test).

**Spec:** `docs/superpowers/specs/2026-08-06-avviso-box-persistente-design.md`

## Global Constraints

- **La voce non cambia.** I cue continuano a essere emessi e pronunciati esattamente come oggi, negli stessi istanti. Cambia **solo chi occupa la riga a schermo**. Se un test dei cue si muove, la modifica è sbagliata.
- **Quando il rientro non serve, l'avviso non c'è.** Nessun avviso spento che occupa spazio, nessun segnaposto.
- **Nessuna soglia nuova.** Non si tocca *quando* il coach chiama il rientro: quella logica è misurata (`pitcall.py`, con la corsia box imparata dai tuoi giri) ed è fuori perimetro.
- **Lingua:** `pitcall.py`, `engine.py`, `serialize.py` sono in inglese; l'overlay è misto. La stringa a schermo passa da `i18n.py` in **entrambe** le lingue — mai testo fisso.
- **Suite:** verde a **1774** su `main` più quello che aggiungono i piani già eseguiti. Deve restare verde.

---

## Struttura dei file

| File | Cosa cambia |
|---|---|
| `src/accoach/coaching/pitcall.py` | + il fermo `calling`, armato al richiamo e disarmato in corsia |
| `src/accoach/engine.py` | + `EngineState.pit_due` |
| `src/accoach/serialize.py` | + `"pit_due"` nel payload |
| `src/accoach/i18n.py` | + `overlay.pit_due` in en/it |
| `src/accoach/overlay.py` | l'avviso prende la banda della pastiglia finché è attivo |

---

### Task 1: Il fermo dentro PitCall

**Files:**
- Modify: `src/accoach/coaching/pitcall.py`
- Test: `tests/test_pitcall.py`

**Interfaces:**
- Produces: `PitCall.calling -> bool` — vero dal richiamo fino alla corsia box

**Perché un fermo e non «ha chiamato in questo giro»:** `_called_lap` vale per un giro solo, e l'avviso deve **sopravvivere al traguardo** — è il difetto che stiamo correggendo. Il fermo si arma quando il richiamo parte e si disarma solo per un motivo vero: sei in corsia, o il rientro non serve più.

- [ ] **Step 1: Scrivi i test che falliscono**

In fondo a `tests/test_pitcall.py`. La helper `_drive(pc, waypoints, **kw)` esiste
già nel file (riga ~27): guida la macchina fra i punti indicati a 20 Hz su un
giro da 110 s, e i `**kw` finiscono in `synth.snap`. Riusala — è tarata apposta
perché il rilevatore misuri una velocità vera invece di collassare sui minimi.

```python
# --- il fermo: il rientro è una condizione, non un evento -------------------

def test_nothing_pending_nothing_calling():
    """Senza una modifica in sospeso non c'è niente da annunciare."""
    pc = PitCall()
    _drive(pc, [0.10, 0.70, 0.90], completed_laps=3)
    assert pc.calling is False


def test_the_latch_arms_when_the_call_goes_out():
    pc = PitCall()
    pc.set_pending(True)
    cues = _drive(pc, [0.10, 0.70, 0.90], completed_laps=3)
    assert _cats(cues) == [CueCategory.PIT_IN]
    assert pc.calling is True


def test_the_latch_survives_the_finish_line():
    """Il difetto che stiamo correggendo. Il cue scatta una volta per giro, ma
    chi è rimasto fuori deve ancora rientrare: a metà del giro dopo, e ancora
    fuori dalla corsia, l'avviso è acceso."""
    pc = PitCall()
    pc.set_pending(True)
    _drive(pc, [0.70, 0.90], completed_laps=3)
    _drive(pc, [0.20, 0.50], completed_laps=4)      # traguardo attraversato
    assert pc.calling is True


def test_entering_the_lane_disarms_it():
    """Sei rientrato: l'avviso ha finito il suo lavoro."""
    pc = PitCall()
    pc.set_pending(True)
    _drive(pc, [0.70, 0.90], completed_laps=3)
    assert pc.calling is True
    _drive(pc, [0.95], completed_laps=3, in_pit_lane=True)
    assert pc.calling is False


def test_dropping_the_pending_change_disarms_it():
    """Un avviso che sopravvive alla sua ragione è peggio di nessun avviso."""
    pc = PitCall()
    pc.set_pending(True)
    _drive(pc, [0.70, 0.90], completed_laps=3)
    pc.set_pending(False)
    assert pc.calling is False


def test_the_cues_are_the_same_as_before():
    """Non-regressione: il fermo è un'uscita in più, non un cambio di
    comportamento. Stessi cue, stesso numero, stesso ordine."""
    pc = PitCall()
    pc.set_pending(True)
    first = _drive(pc, [0.10, 0.70, 0.90], completed_laps=3)
    second = _drive(pc, [0.70, 0.90], completed_laps=4)
    assert _cats(first) == [CueCategory.PIT_IN]
    assert _cats(second) == [CueCategory.PIT_IN]
```

> Verifica che `in_pit_lane` sia il nome esatto del campo in `synth.snap` /
> `TelemetrySnapshot` prima di usarlo, e **non aggiungere metodi a `PitCall` per
> comodità dei test**: se un test è difficile da scrivere, dillo invece di
> piegare il codice di produzione.

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_pitcall.py -q -k "latch or calling"`
Expected: FAIL — `calling` non esiste

- [ ] **Step 3: Implementa**

In `__init__` e in `reset()`, accanto agli altri fermi:

```python
        # Armed when the call goes out, disarmed only when you are in the lane
        # or the stop is no longer needed. Deliberately NOT per-lap like
        # `_called_lap`: a driver who stays out another lap still has to come
        # in, and an on-screen warning that expires with the lap is a warning
        # that expires exactly when it is still true.
        self._calling = False
```

In `set_pending`, dove gli altri fermi vengono azzerati, aggiungi `self._calling = False`.

Proprietà pubblica accanto a `pit_entry`:

```python
    @property
    def calling(self) -> bool:
        """Has the driver been called in and not reached the lane yet?

        A condition, not an event: the cue that announces it fires once a lap,
        this stays true in between.
        """
        return self._calling
```

In `update`, disarmare **prima** di ogni altro ritorno che riguarda la corsia:

```python
        if s.in_pit_lane or s.in_pit:
            self._calling = False
```
da mettere dove il metodo già distingue quei due stati, **senza cambiare quali cue vengono emessi lì**.

E armare dove il cue `PIT_IN` viene aggiunto a `out`:

```python
            self._calling = True
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_pitcall.py tests/test_pitcall_engine.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/accoach/coaching/pitcall.py tests/test_pitcall.py
git commit -m "Il rientro è una condizione, non un evento: il fermo dentro PitCall"
```

---

### Task 2: Il motore lo espone, il payload lo porta

**Files:**
- Modify: `src/accoach/engine.py` (`EngineState`, `tick`), `src/accoach/serialize.py`
- Test: `tests/test_pitcall_engine.py`, `tests/test_serialize.py`

**Interfaces:**
- Consumes: `PitCall.calling` (Task 1)
- Produces: `EngineState.pit_due: bool = False`, chiave `"pit_due"` nel payload

Un booleano e non un blocco: qui non c'è niente da dire oltre «sì, devi rientrare». Il perché lo dice già la pagina Ingegnere, e ripeterlo sull'overlay sarebbe una seconda copia della stessa frase.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
def test_the_state_says_you_are_due_in(tmp_path):
    """Dopo il richiamo lo stato lo dice, e continua a dirlo il giro dopo."""

def test_the_state_stops_saying_it_in_the_lane(tmp_path):
    ...

def test_pit_due_reaches_the_frontends():
    assert state_to_dict(_state(pit_due=True))["pit_due"] is True


def test_pit_due_defaults_to_false():
    assert state_to_dict(_state())["pit_due"] is False
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_serialize.py tests/test_pitcall_engine.py -q -k pit_due`
Expected: FAIL

- [ ] **Step 3: Implementa**

In `EngineState`, accanto a `corner`:

```python
    # Sei stato richiamato ai box e non sei ancora in corsia. Una condizione,
    # non un evento: il cue che la annuncia scatta una volta per giro, questa
    # resta vera in mezzo — ed è per questo che l'overlay può tenerla accesa.
    pit_due: bool = False
```

In `tick`, nella costruzione di `EngineState`: `pit_due=self.pitcall.calling,`.

In `serialize.state_to_dict`, accanto a `"corner"`: `"pit_due": st.pit_due,`.

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_serialize.py tests/test_pitcall_engine.py tests/test_server.py tests/test_engine.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/accoach/engine.py src/accoach/serialize.py tests/
git commit -m "Il rientro dovuto nello stato e nel payload"
```

---

### Task 3: L'overlay lo tiene acceso

**Files:**
- Modify: `src/accoach/i18n.py`, `src/accoach/overlay.py`
- Test: `tests/test_overlay_pit_due.py` (nuovo)

**Interfaces:**
- Consumes: `state["pit_due"]`

- [ ] **Step 1: Scrivi i test che falliscano**

Nuovo file sul modello di `tests/test_overlay_paint.py`, che **spia le chiavi i18n richieste** durante una pittura vera — è il meccanismo giusto qui, perché la stringa passa da `t()`.

> **Non** copiare lo spione del painter di `tests/test_overlay_corner_card.py` senza il suo `finally`: quel file ripristina `p.drawText` apposta, perché un `QPainter` tenuto vivo oltre `paintEvent` ha già fatto crashare un test che non c'entrava niente.

```python
def test_the_warning_is_asked_for_while_you_are_due_in(app, monkeypatch):
    assert "overlay.pit_due" in _keys_drawn({"connected": True, "pit_due": True, ...})


def test_no_warning_when_nothing_is_due(app, monkeypatch):
    assert "overlay.pit_due" not in _keys_drawn({"connected": True, ...})


def test_the_warning_does_not_fade(app, monkeypatch):
    """Dipinta molto dopo la durata di una pastiglia, la parola c'è ancora.
    È il difetto che stiamo correggendo, quindi è il test che conta."""


def test_a_driving_cue_does_not_cover_it(app, monkeypatch):
    """Con un cue appena arrivato E il rientro dovuto, la riga è dell'avviso."""
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_overlay_pit_due.py -q`
Expected: FAIL

- [ ] **Step 3: Implementa — la stringa**

In `src/accoach/i18n.py`, accanto alle altre `overlay.*`:

```python
    "overlay.pit_due": {"en": "▶ BOX THIS LAP", "it": "▶ RIENTRA AI BOX"},
```

- [ ] **Step 4: Implementa — il disegno**

In `overlay.py`, `_draw_cue` comincia con la resa dell'avviso e **cede il posto** solo se non c'è:

```python
    def _draw_pit_due(self, p: QPainter, w: int) -> bool:
        """L'avviso di rientro, nella banda della pastiglia. Torna True se ha
        preso la riga.

        Non sfuma e non ha un timer: è una condizione, non un evento, e finisce
        quando entri in corsia. Prende il posto dei consigli di guida perché la
        gerarchia è quella: un consiglio su come prendere una curva che copre il
        rientro ti fa fare un giro in più col serbatoio vuoto. La voce non
        cambia — i cue continuano a essere pronunciati, cedono solo la riga.
        """
        if not self._state.get("pit_due"):
            return False
        x, y, h = 20, 126, 36
        p.setPen(Qt.NoPen)
        p.setBrush(_DARK)
        p.drawRoundedRect(x, y, w - 2 * x, h, 8, 8)
        p.setBrush(_AMBER)
        p.drawRoundedRect(x, y, 4, h, 2, 2)
        self._set_font(p, 14, bold=True)
        p.setPen(_AMBER)
        p.drawText(x + 16, y, w - 2 * x - 28, h, Qt.AlignVCenter, t("overlay.pit_due"))
        return True
```

E in `paintEvent`, al posto della sola chiamata a `_draw_cue`:

```python
        if not self._draw_pit_due(p, w):
            self._draw_cue(p, w)
```

`_draw_focus` si fa già da parte davanti a un cue recente: **lasciala com'è**. L'avviso vive nella sua banda e non ne tocca altre.

- [ ] **Step 5: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_overlay_pit_due.py tests/test_overlay_paint.py tests/test_overlay_corner_card.py tests/test_overlay_pedals.py tests/test_i18n.py -q`
Expected: PASS

- [ ] **Step 6: Verifica a schermo**

Non basta la suite: guarda l'avviso acceso davvero, e guarda che **sparisca** entrando in corsia.

- [ ] **Step 7: Commit**

```bash
git add src/accoach/overlay.py src/accoach/i18n.py tests/test_overlay_pit_due.py
git commit -m "In pista: l'avviso di rientro resta finché non rientri"
```

---

### Task 4: La guida

**Files:** `GUIDA.md` (§4, dentro «Leggere l'overlay»)

- [ ] **Step 1: Scrivi il paragrafo**

```markdown
Quando l'ingegnere propone una modifica che si fa solo ai box, il coach ti
richiama — e da quel momento **l'avviso resta acceso**, in ambra, al posto dei
consigli, finché non entri in corsia box. Non sfuma: un richiamo che sparisce
dopo due secondi è un richiamo che ti perdi se in quel momento stavi guardando
la curva davanti.

I consigli di guida continuano a essere **detti**: cedono solo quella riga, e la
riprendono appena sei rientrato.
```

- [ ] **Step 2: Verifica e commit**

Run: `python -m pytest tests/test_guide.py -q`

```bash
git add GUIDA.md
git commit -m "La guida: l'avviso di rientro e perché non sfuma"
```

---

## Chiusura

- [ ] `python -m pytest -q` verde
- [ ] Verifica a schermo: l'avviso compare, sopravvive al giro, sparisce in corsia
- [ ] REQUIRED SUB-SKILL: `superpowers:finishing-a-development-branch`
