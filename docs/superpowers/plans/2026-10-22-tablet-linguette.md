# Linguette del tablet e strada dell'ingegnere — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** linguette Telemetria/Assetto su `/tablet` col cambio automatico che resta, e la striscia delle fasi dell'ingegnere col contatore dei giri, sul tablet e sulla pagina Ingegnere.

**Architecture:** `RaceEngineer.progress()` calcola fasi, fase in corso, passo e giri; `engine._engineer_block` lo manda nel frame come `engineer.progress`. Le pagine lo disegnano soltanto.

**Tech Stack:** Python / pytest; JS per Safari 9 senza build (node solo nei test); Playwright Chromium per la prova.

**Spec:** `docs/superpowers/specs/2026-10-22-tablet-linguette-design.md`

## Global Constraints

- `tablet.js`: ES5 + template string; vietati `let`, `const`, `=>`, `class`, `async`, `await`, `...`, `?.`, `??`, `fetch`, ogni `.forEach(`, `padStart`, `padEnd`, `Intl.`, `Object.entries`, `Object.values`, `URLSearchParams`. `tablet.css`: niente grid, `clamp(`, `var(--`, `gap:`, `min(`/`max(`, `vh`. Controllo: `tests/safari9.py`.
- Testi nuovi solo in `src/accoach/web/i18n.js`, IT + EN, prefisso `tablet.` (o `eng.` se servono anche alla pagina Ingegnere), tono: frasi brevi col tu, virgola decimale, numero + spazio + unità, niente slogan, niente due punti a effetto, niente lineette a effetto, niente «!», niente emoji, mai la stessa frase in due chiavi; ogni frase vera sul codice.
- Bottoni e linguette alti almeno 44 px. Nessuno scorrimento a 1024 × 680, 768 × 940, 1024 × 768, 768 × 1024.
- `render(st)` gira ~15 volte al secondo: non ricostruisce il DOM che il pilota sta toccando.
- Mai scrivere in `C:\Users\undrg\Documents\ACCoach`; mai importare/chiamare `accoach.config` fuori dai test isolati o da una casa finta (`USERPROFILE`/`HOME` su una cartella temporanea).
- Commenti nello stile dei file vicini (italiano, il perché).

## Review Focus

1. Il pilota tocca Assetto in pista: al frame dopo la vista non deve tornare su Telemetria (il tocco vale fino al prossimo cambio ai box / non ai box). Test nel Task 2.
2. Riparte dai box mentre guarda Assetto: torna su Telemetria. Test nel Task 2.
3. Assetto finito (`index == len(phases)`, `stage == "done"`): la striscia lo dice, senza contatore e senza «fase 6 di 5». Test nei Task 1 e 3.
4. Frame senza `progress` (motore vecchio o nessuna decisione): nessun errore, striscia nascosta. Test nel Task 3.
5. Una modifica proposta mentre il pilota guarda Assetto: compare al frame dopo (già vero per la schermata dei box, va mantenuto). Test nel Task 2.

---

### Task 1: `progress` dal motore

**Files:** Modify `src/accoach/engineer/core.py` (metodo `RaceEngineer.progress`), `src/accoach/engine.py` (`_engineer_block` aggiunge `"progress"`). Test: `tests/test_engineer_progress.py`.

**Interfaces — Produces:** `RaceEngineer.progress(lang: str | None = None) -> dict` con
`{"phases": [{"key": str, "label": str, "tag": "BOX"|"AV"}], "index": int, "stage": str, "have": int|None, "need": int|None}`. Regole, in quest'ordine:
- `phase is None` → `stage="done"`, `index=len(phases)`, `have=need=None`;
- `_held_revert is not None` oppure (`_pending` e `_pending_is_revert`) → `"restore"`;
- `active is not None` → `"test"`, `have=active.laps_seen`, `need=min_stable`;
- `_pending is not None` → `"change"`;
- `len(window) < min_stable` → `"baseline"`, `have=len(window)`, `need=min_stable`;
- altrimenti `"diagnose"`.
`label` tradotta con `engineer.profiles._common.tr(label, lang)`; `tag` è il tag della fase se le fasi ne hanno uno (`grep -n "tag" src/accoach/engineer/profiles/_common.py` per come le fasi AV sono marcate; se non esiste un attributo, deducilo nello stesso modo in cui `engine.py`/la pagina lo deducono oggi e dillo nel rapporto). In `_engineer_block`: `"progress": self._engineer.progress() if self._engineer else None`.

- [ ] Test (falliscono prima): un `RaceEngineer` GT3 nuovo → `stage == "baseline"`, `have == 0`, `need == 3`, `index == 0`, cinque fasi con le chiavi `pressures, mechanical, aero, brake_bias, electronics`; dopo 2 giri stabili `have == 2`; con una proposta in sospeso → `"change"`; dopo `mark_applied` → `"test"`, `have` sale coi giri; con `phase_idx = len(phases)` → `"done"`, `index == 5`, `have is None`; il blocco di `CoachEngine._engineer_block()` contiene `progress` (costruisci il caso come fanno i test esistenti dell'engine/ingegnere: `grep -rn "_engineer_block\|RaceEngineer(" tests | head`).
- [ ] Implementa; `python -m pytest tests/test_engineer_progress.py tests/ -q -k "engineer"`; poi suite intera; commit «La strada dell'ingegnere nel frame».

### Task 2: Le linguette su `/tablet`

**Files:** Modify `src/accoach/web/tablet.html`, `tablet.js`, `tablet.css`, `i18n.js`. Test: `tests/test_tablet_tabs.py` (node, `skipif` se manca) + `tests/test_safari9.py` già esistente.

**Interfaces — Produces:** in `window.HoneTablet`: `pickTab(prev, st, manual) -> "track"|"setup"` pura, dove `prev = {tab, atBox}` è lo stato precedente e `manual` è la linguetta toccata dal pilota in questo ciclo o `null`. Regole: con `manual` vince `manual`; se `st.at_box` è cambiato rispetto a `prev.atBox` → `"setup"` se ora ai box, `"track"` se no; altrimenti resta `prev.tab`. La prima volta (`prev` nullo) → `"setup"` se ai box, altrimenti `"track"`. Il `mode()` di oggi resta (decide `off` e l'avviso); la schermata mostrata è: `off` → schermata off; altrimenti la linguetta scelta (con l'avviso di rientro sopra la telemetria come oggi). `#tablet` porta anche `data-tab`.
- Linguette `#t-tab-track` e `#t-tab-setup` in alto, alte ≥ 44 px, testo dalle chiavi (riusa `eng.liveDiag`/`setup.title` se dicono la cosa giusta, altrimenti `tablet.tab.track`/`tablet.tab.setup`). Segno su Assetto quando `mode(st) === "call"` o c'è una modifica BOX da fare.
- Un tocco sull'avviso di rientro (`#t-call`) apre Assetto.
- La schermata Assetto è quella dei box di oggi; deve funzionare anche con `at_box` falso (base, anteprima, scrittura): le richieste di base/anteprima oggi partono «entrando nello stato box» — falle partire entrando nella linguetta Assetto o in box, e quando cambiano auto/pista o la modifica.

- [ ] Test (falliscono prima), in node sul vero `tablet.js`: `pickTab(null, {at_box:false})` → `"track"`; `pickTab(null, {at_box:true})` → `"setup"`; tocco manuale su `"setup"` in pista e poi frame uguali → resta `"setup"` (Review Focus 1); da `{tab:"setup", atBox:true}` a `at_box:false` → `"track"` (Review Focus 2); da `{tab:"track", atBox:false}` a `at_box:true` → `"setup"`; con lo stub DOM dei test esistenti (`tests/test_tablet_box.py`) un clic su `#t-tab-setup` durante un frame in pista mostra `#t-box` e una proposta che arriva dopo appare al frame successivo (Review Focus 5).
- [ ] Implementa; `python -m pytest tests/test_tablet_tabs.py tests/test_tablet_page.py tests/test_tablet_box.py tests/test_safari9.py tests/test_tono.py tests/test_web_i18n_keys.py -q`; commit «Linguette Telemetria e Assetto sul tablet».

### Task 3: La striscia della strada, sul tablet e sulla pagina Ingegnere

**Files:** Modify `tablet.html/js/css`, `engineer.html`, `engineer.js`, `engineer.css`, `i18n.js`; `GUIDA.md`, `docs/FAQ.md` (il paragrafo sull'ingegnere e la sezione «La vista tablet»). Test: `tests/test_engineer_strip.py` (node).

**Interfaces — Consumes:** `st.engineer.progress` (Task 1). **Produces:** in `window.HoneTablet` `stripText(progress) -> {steps: [{label, state: "done"|"now"|"next", av: bool}], line: string}` pura (testi da `HoneI18n`); la pagina Ingegnere usa una sua funzione equivalente in `engineer.js` (può essere moderna, ma le stesse chiavi e le stesse regole: test su entrambe con gli stessi casi).
- Frase per passo: `baseline` «Giro buono {have} di {need} per la base.» + perché un giro conta (valido, pulito, gomme sopra 75 °C) in una chiave a parte mostrata sotto, piccola; `change` «C'è una modifica da fare.» (BOX) — per le fasi AV la frase dice dal volante; `test` «Verifico la modifica, giro {have} di {need}. Poi decido se tenerla.»; `restore` «Rimetti l'ultima modifica com'era.»; `diagnose` «Ho i giri, sto decidendo.»; `done` «Assetto finito.». Scrivile col tono deciso; i testi sopra sono il significato, non la forma obbligata, e non devono ripetere frasi già presenti (`tablet.call`, `eng.do.*`).
- Tappe: fasi fatte (indice minore) spuntate, la corrente evidenziata, le altre in grigio; le fasi AV segnate «dal volante».
- Senza `progress` (o `null`) la striscia è nascosta e niente si rompe (Review Focus 4). Con `done` nessun contatore e nessuna tappa evidenziata oltre la fine (Review Focus 3).
- Sul tablet la striscia sta in entrambe le linguette, sopra la riga della fase; sulla pagina Ingegnere sopra `#es-phase`.
- Guide: spiega in poche frasi vere il ciclo (3 giri buoni per la base, una modifica alla volta, 3 giri per verificarla, tiene o rimette com'era, poi la fase dopo) e dove si vede (la striscia). Verifica ogni numero sul codice.

- [ ] Test (falliscono prima): `stripText` per `baseline 2/3`, `test 1/3`, `change` su fase BOX e su fase AV, `restore`, `diagnose`, `done` con `index == len(phases)`, `null`; stessi casi sulla funzione di `engineer.js`; `test_tono` copre le nuove chiavi.
- [ ] Implementa; i test del Task 2 più `tests/test_engineer_strip.py`, `tests/test_engineer*.py`, `tests/test_tono.py`; suite intera; commit «La strada dell'ingegnere: le fasi e i giri che mancano».

### Dopo i task (chi coordina)

Prova Playwright Chromium sulla casa finta (porta 8791) con il finto motore (`scratchpad/ipad/fakeengine.py`, esteso con `progress`) a 1024 × 680, 768 × 940, 1024 × 768, 768 × 1024: linguette, tocco manuale che resta, ritorno automatico, striscia in ogni passo. Revisione d'insieme, registro `docs/superpowers/ledgers/2026-10-22-tablet-linguette.md`, fusione nel main locale.
