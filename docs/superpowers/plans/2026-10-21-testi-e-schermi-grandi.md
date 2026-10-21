# I testi col tono nuovo e gli schermi grandi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tutti i testi che il pilota legge o sente (report, pagina Ingegnere, hub, overlay, voce, guida) seguono il tono deciso col pilota in italiano e in inglese, e il report e la pagina Ingegnere si leggono comodi su un 32".

**Architecture:** Un controllo di tono unico (`tests/tono.py`) applica le regole a ogni catalogo di testi; ogni superficie entra nel controllo quando il suo task la riscrive (un registro `PENDING` si svuota task dopo task, e alla fine è vuoto). I numeri passano da una funzione di formato per lingua (JS in `i18n.js`, Python in `accoach/textfmt.py`). La dimensione del testo nel web nasce da una base sul `:root` che cresce con la larghezza della finestra; tutto il resto è in `rem`, compresi i caratteri dei canvas.

**Tech Stack:** Python 3, JavaScript vanilla, CSS, pytest; Piper per i WAV della voce.

**Spec:** `docs/superpowers/specs/2026-10-21-testi-e-schermi-grandi-design.md`

## Global Constraints

- Regole del tono (spec, «Le regole, come si controllano»): niente emoji; niente due punti a effetto; niente lineetta a effetto; niente «!»; frasi di al massimo 25 parole; virgola decimale in italiano anche nei numeri composti a runtime; numero e unità separati da uno spazio; mai la stessa frase in due chiavi o due cataloghi, per lingua; niente formule da slogan (lista nella spec). Tempi sul giro nel formato «1:47.427».
- Il significato non cambia: stessi fatti, stessi numeri, stessi segnaposti (un segnaposto si può rinominare solo insieme al codice che lo riempie). Un testo vecchio che afferma qualcosa che la schermata non mostra si corregge e si scrive nel report del task.
- Ogni testo in italiano e inglese, con le stesse regole. L'inglese è una traduzione naturale, non una copia parola per parola.
- La «Prima e dopo» della spec è il metro: frasi col tu, prima il fatto poi cosa fare, nessun riempitivo.
- Voce: al massimo otto parole per frase, un imperativo, nessun numero dove non serve.
- Fuori: `web/test_plan.json`, l'aiuto CLI di `__main__.py`, i nomi di curve e circuiti.
- I test che fissano il testo esatto si aggiornano; quelli che controllano un significato restano. Ogni test nuovo fallisce se si toglie la cosa che prova (mutazione verificata a mano).
- Mai scrivere in `C:\Users\undrg\Documents\ACCoach`. Niente `git stash` (pila condivisa fra worktree).
- Commit in italiano con `Co-Authored-By:` del modello reale.

## Review Focus

- Un testo riscritto perde un segnaposto o ne cambia il nome senza il codice: la pagina mostra «{v}» o una stringa vuota (Task 3-8: il controllo di tono verifica che gli insiemi di segnaposti it/en/vecchio coincidano).
- Un numero composto a runtime in italiano esce ancora col punto (Task 2 e 5-8: controllo statico che vieta `toFixed` e `:.Nf` fuori dagli helper nei moduli di testo).
- Una frase vietata torna da un'altra superficie: lo stesso testo in due cataloghi (Task 1: il controllo dei duplicati è fra tutti i cataloghi registrati).
- Su un portatile a 1366 px il report cambia aspetto o va a capo dove prima non andava (Task 9: base fissa a 14 px fino a 1600 px).
- Una frase della voce cambia e il WAV no: in pista parte la sintesi SAPI al posto della voce neurale (Task 8: il test del manifest esistente).

---

### Task 1: Il controllo di tono e i formati dei numeri

**Files:**
- Create: `tests/tono.py` (helper, non un test), `tests/test_tono.py`, `src/accoach/textfmt.py`, `tests/test_textfmt.py`
- Modify: `src/accoach/web/i18n.js` (aggiunge `fmtNum`), `src/accoach/coaching/howto.py` (`fmt_s` usa `textfmt`)

**Interfaces:**
- Produces:
  - `textfmt.fmt_num(v: float, decimals: int, lang: str, unit: str | None = None) -> str` — «0,18 s» / «0.18 s»; `unit=None` senza unità; `-0` diventa `0`.
  - JS `fmtNum(v, decimals, unit)` in `i18n.js` (lingua da `LANG()` o dall'equivalente della pagina Ingegnere), stesso comportamento.
  - `tono.violations(text: str, lang: str) -> list[str]` — una voce per regola violata (`emoji`, `colon`, `dash`, `bang`, `long`, `decimal`, `unit`, `slogan`); i segnaposti `{...}` si ignorano; `colon` si applica a ogni testo, con le sole eccezioni di orari («22:58»), tempi sul giro («1:47.427»), rapporti («3:1») e segnaposti.
  - `tono.SURFACES: dict[str, Callable[[], dict[str, dict[str, str]]]]` — nome della superficie → funzione che restituisce `{chiave: {"it": …, "en": …}}`. Superfici: `report` (CAT di `i18n.js` tranne le chiavi della pagina Ingegnere), `engineer` (chiavi usate solo da `engineer.html`/`engineer.js`, più i dizionari `{"it","en"}` di `engineer/`), `report_backend` (dizionari `{"it","en"}` e blocchi it/en di `coaching/debrief.py`, `trajectory.py`, `training.py`, `howto.py`, `pagella.py`, `api.py`), `hub` (`i18n._UI`), `coach` (`coaching/cue.py`, `focus.py`, `pitcall.py`, `voice.py`, `i18n._CUE_EN`), `guide` (frasi di `GUIDA.md` e `docs/FAQ.md`, it ed en rispettivamente).
  - `tono.PENDING: set[str]` — le superfici non ancora riscritte; all'inizio tutte. Ogni task che riscrive una superficie la toglie.
  - `tono.placeholders(text) -> set[str]`.
- `test_tono.py`: per ogni superficie fuori da `PENDING`, nessuna violazione e segnaposti it == en; fra tutte le superfici fuori da `PENDING`, nessuna frase uguale in due chiavi (per lingua); `PENDING` non contiene nomi sconosciuti.

- [ ] **Step 1:** test di `textfmt` e di `tono.violations` con un esempio per regola (positivo e negativo), compresi «1:47.427» e «22:58» ammessi, «Obiettivo: sotto» vietato, «0.18 s» vietato in it e ammesso in en, «0,18s» vietato (unità), «bella costanza!» vietato due volte (`slogan`, `bang`).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementa; `fmt_s` di `howto.py` delega a `fmt_num` (i suoi test restano verdi).
- [ ] **Step 4:** `test_tono.py` verde con `PENDING` = tutte le superfici; mutazioni sulle regole.
- [ ] **Step 5:** commit.

---

### Task 2: I numeri del report e della pagina Ingegnere

**Files:** Modify `src/accoach/web/app.js`, `engineer.js`, `test.js`. Test: `tests/test_tono.py` (o `tests/test_web_numeri.py`).

**Interfaces:** Consumes `fmtNum` (Task 1).

- [ ] **Step 1:** test statico: nessun `.toFixed(` in `app.js`, `engineer.js`, `test.js` fuori dalle funzioni di formato (`fmtNum`, `fixz`, `fmtDec`, `fmtSecs` e i formati dei tempi sul giro, elencati nel test); nessuna concatenazione numero+unità senza spazio («+ "s"», «+ "m"», «+ "°"»).
- [ ] **Step 2:** FAIL (circa 75 `toFixed` oggi).
- [ ] **Step 3:** ogni numero mostrato passa da `fmtNum` (o da `fmtDec`/`fmtSecs` riscritte sopra `fmtNum`); i valori che finiscono in attributi, CSV o JSON restano col punto.
- [ ] **Step 4:** test verdi + suite web; mutazione.
- [ ] **Step 5:** commit.

---

### Task 3: Il report, parte prima (Pagella, piano, sessione, navigazione)

**Files:** Modify `src/accoach/web/i18n.js`, `index.html`, eventuali test che fissano questi testi. Test: `tests/test_tono.py`.

Chiavi di questo task: prefissi `pag. howto. adv. ses. flow. recap. plan. train. rec. prog. dh. trends. recur. cornerses. cons. tour. tab. tabgroup. nav. title. demo. lang. combo. empty. load. err. modal. kbd. badge. btn. lbl. ctl. lvl. focus. live. debrief.` e i testi fissi di `index.html`, tranne le chiavi della pagina Ingegnere (Task 6).

- [ ] **Step 1:** in `tono.py` dividi la superficie `report` in `report_a` (queste chiavi) e `report_b` (le altre), entrambe in `PENDING`; togli `report_a` da `PENDING`: il test diventa rosso con l'elenco delle violazioni.
- [ ] **Step 2:** riscrivi it ed en secondo la spec; elimina le chiavi diventate inutili («Curve: ») insieme al loro uso; aggiorna i test che fissavano i testi vecchi.
- [ ] **Step 3:** `test_tono.py` verde, `pytest tests/test_web_*.py -q` verde.
- [ ] **Step 4:** report del task: tabella prima → dopo delle 20 frasi più lette (Pagella, piano, sessione), per la revisione.
- [ ] **Step 5:** commit.

---

### Task 4: Il report, parte seconda (Confronto, Traiettoria, Settori, Dinamica, Passo gara, Andamento, grafici)

**Files:** Modify `src/accoach/web/i18n.js`, `index.html`, test che fissano questi testi. Test: `tests/test_tono.py`.

Chiavi: tutte quelle di `report_b`.

- [ ] **Step 1:** togli `report_b` da `PENDING`: rosso.
- [ ] **Step 2:** riscrivi; le legende dei grafici («Velocità — bianco = tu, ciano = riferimento») diventano frasi o didascalie senza lineetta a effetto («Velocità. Bianco sei tu, ciano il riferimento.»).
- [ ] **Step 3:** verde + suite web.
- [ ] **Step 4:** report con prima → dopo delle 20 frasi più visibili.
- [ ] **Step 5:** commit.

---

### Task 5: I testi del report scritti dal motore

**Files:** Modify `src/accoach/coaching/debrief.py`, `trajectory.py`, `training.py`, `howto.py`, `src/accoach/pagella.py`, `api.py`; test che fissano questi testi. Test: `tests/test_tono.py` più un test che compone i testi con numeri veri.

- [ ] **Step 1:** togli `report_backend` da `PENDING`; aggiungi un test che rende ogni messaggio del debrief e della traiettoria con valori di esempio (stesso schema di `test_howto_tono.py`) e applica `tono.violations` al testo composto (così la virgola si controlla a runtime). Rosso.
- [ ] **Step 2:** riscrivi; i numeri nei testi italiani passano da `textfmt.fmt_num` invece di `:.Nf`.
- [ ] **Step 3:** verde + `pytest -q`.
- [ ] **Step 4:** report con prima → dopo di 15 messaggi del debrief.
- [ ] **Step 5:** commit.

---

### Task 6: La pagina Ingegnere

**Files:** Modify `src/accoach/web/i18n.js` (chiavi della pagina Ingegnere), `engineer.html`, `src/accoach/engineer/core.py`, `steps.py`, `profiles/*.py`; test che fissano questi testi. Test: `tests/test_tono.py` + rendering dei messaggi con valori.

- [ ] **Step 1:** togli `engineer` da `PENDING`, aggiungi il rendering dei messaggi di `engineer/core.py` con valori di esempio. Rosso.
- [ ] **Step 2:** riscrivi (es. «Il problema di tenuta «{sym}» è risolto. Era {a}, ora è {b}.»); numeri da `textfmt`.
- [ ] **Step 3:** verde + `pytest -q`.
- [ ] **Step 4:** report con prima → dopo di 15 messaggi.
- [ ] **Step 5:** commit.

---

### Task 7: Hub, avvio, pannello In pista, overlay, pagina di prova

**Files:** Modify `src/accoach/i18n.py` (`_UI`), `launcher.py`, `hub_home.py`, `livepanel_ui.py`, `overlay.py`, `testpanel.py`, `web/test.js`, `web/test.html`, `theme.py` (dimensioni minime); test che fissano questi testi. Test: `tests/test_tono.py`.

- [ ] **Step 1:** togli `hub` da `PENDING`; aggiungi i testi fissi di `testpanel.py`/`test.js` alla superficie `hub`. Rosso (emoji sui bottoni compresi).
- [ ] **Step 2:** riscrivi; i bottoni perdono le emoji e le frecce decorative; nessun testo Qt sotto 12 px (`theme.py`).
- [ ] **Step 3:** verde + `pytest -q`; rendi l'hub in PNG offscreen (come i test esistenti dei dialoghi Qt) e allega il percorso nel report.
- [ ] **Step 4:** report con prima → dopo di tutti i bottoni e dei passi del pannello In pista.
- [ ] **Step 5:** commit.

---

### Task 8: La voce e i testi del coach

**Files:** Modify `src/accoach/coaching/cue.py`, `focus.py`, `pitcall.py`, `voice.py`, `src/accoach/i18n.py` (`_CUE_EN`), `src/accoach/voice_cues/*`, `src/accoach/voice_cues_male/*`; test che fissano le frasi. Test: `tests/test_tono.py` (+ regola delle otto parole per la superficie `coach`), `tests/test_voice_cues.py`.

- [ ] **Step 1:** togli `coach` da `PENDING` e aggiungi la regola «al massimo otto parole» per questa superficie. Rosso.
- [ ] **Step 2:** riscrivi le frasi (italiano e `_CUE_EN`), con le espressioni regolari di `_CUE_EN` allineate.
- [ ] **Step 3:** copia `tools/piper/` dal worktree `C:/Users/undrg/orca/workspaces/ACCoach/potenziamento-ingegnere-di-pista` (è ignorata da git) e rigenera: `python tools/render_cues.py` e `python tools/render_cues.py --male`. Togli i WAV orfani.
- [ ] **Step 4:** `pytest tests/test_voice_cues.py tests/test_tono.py -q` verdi + `pytest -q`; elenco prima → dopo di tutte le frasi nel report.
- [ ] **Step 5:** commit (WAV compresi).

---

### Task 9: Il testo che cresce con lo schermo

**Files:** Modify `src/accoach/web/style.css`, `engineer.css`, `test.css`, `app.js` (caratteri dei canvas), `engineer.js` (se disegna). Test: `tests/test_web_scala.py`.

**Interfaces:** Produces la variabile CSS `--fs` sul `:root` e la funzione JS `canvasFont(px)` che restituisce la dimensione dei caratteri dei canvas scalata con la stessa base.

- [ ] **Step 1:** test statici: `:root` ha `font-size: clamp(14px, calc(14px + (100vw - 1600px) * 6 / 1280), 20px)` (o equivalente che dà 14 px fino a 1600 px di larghezza, 18,5 px a 2560 e 20 px da 2880); nessun `font-size` in `px` nei tre CSS fuori da `:root`; nessun valore sotto `0.857rem` (12 px a base 14); `--page` in `rem`; nessun `ctx.font` in `app.js` con una dimensione in px scritta a mano (passa da `canvasFont`). Node: `canvasFont(10)` con base 14 dà 10 e con base 18 dà circa 12,9.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** converti; le colonne di lettura (`.flow-shell` e simili) in `ch` o `rem` sotto i 75 caratteri.
- [ ] **Step 4:** verdi + suite web.
- [ ] **Step 5:** commit.

---

### Task 10: La guida in italiano

**Files:** Modify `GUIDA.md`. Test: `tests/test_tono.py` (superficie `guide`, parte italiana), `tests/test_guide.py`.

- [ ] **Step 1:** dividi `guide` in `guide_it` e `guide_en`; togli `guide_it` da `PENDING`. Rosso.
- [ ] **Step 2:** riscrivi `GUIDA.md` col tono nuovo; i nomi di schede, bottoni e messaggi citati devono essere quelli nuovi dei Task 3-8 (controlla ogni citazione contro `i18n.js`/`i18n.py`). Mantieni struttura e ancore delle sezioni usate dai collegamenti (`/guida#…`): verifica con `grep` nei sorgenti.
- [ ] **Step 3:** verde + `pytest tests/test_guide.py tests/test_bundle_contents.py -q`.
- [ ] **Step 4:** report con l'elenco delle sezioni toccate.
- [ ] **Step 5:** commit.

---

### Task 11: La guida in inglese

**Files:** Modify `docs/FAQ.md`. Test: come il Task 10 per `guide_en`; alla fine `PENDING` è vuoto (assert nel test).

- [ ] **Step 1:** togli `guide_en` da `PENDING` e aggiungi `assert not PENDING`. Rosso.
- [ ] **Step 2:** riscrivi `docs/FAQ.md` con gli stessi contenuti della guida italiana nuova.
- [ ] **Step 3:** verde + `pytest -q`.
- [ ] **Step 5:** commit.

---

### Task 12: Prova del controllore

Il controllore, non un subagente: server del ramo su una copia dell'archivio; report e pagina Ingegnere a 1366, 1920 e 2560 px di larghezza (dimensione del testo misurata dal DOM, nessuna riga che esce dalla colonna, grafici leggibili); lettura delle schermate principali in italiano e in inglese a caccia di frasi «da macchina»; l'hub reso in PNG; ascolto di tre WAV a caso (durata e testo dal manifest). I difetti tornano come fix ai task che li possiedono; poi revisione finale e fusione nel main locale.
</content>
</invoke>
