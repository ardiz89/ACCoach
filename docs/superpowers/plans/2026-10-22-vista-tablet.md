# La vista tablet — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una pagina `/tablet` che gira su Safari 9 (iPad 3, iOS 9.3.6) e passa da sola fra telemetria, avviso di rientro e schermata dei box con il bottone che scrive la modifica.

**Architecture:** il motore calcola «fermo ai box» una volta e lo manda nel frame (`at_box`). Il processo web (8778) ricorda l'ultimo file scritto per auto e pista e sceglie il file di partenza (`/api/setup/base`). La pagina `/tablet` è HTML + `tablet.js` + `tablet.css` in ES5 (più le template string), usa `i18n.js` per i testi, il WebSocket del motore (8777) per il dal vivo e gli endpoint `/api/setup/*` già esistenti per scrivere.

**Tech Stack:** Python 3.11+ / FastAPI / pytest; JavaScript per Safari 9 senza build; node (solo nei test, `skipif` se manca); Playwright WebKit per la prova finale.

**Spec:** `docs/superpowers/specs/2026-10-22-vista-tablet-design.md`

## Global Constraints

- Ogni script che `/tablet` carica (`i18n.js`, `tablet.js`) è sintassi ES5 più template string. Vietati: `let`, `const`, `=>`, `class`, `async`, `await`, `...`, `?.`, `??`; e le API `fetch`, `.forEach` su `querySelectorAll`/`getElementsBy*`, `padStart`, `padEnd`, `Intl.`, `Object.entries`, `Object.values`, `URLSearchParams`.
- `tablet.css`: niente `display: grid`, `clamp(`, `var(--`, `gap:` dentro flex, `min(`/`max(`.
- Testi nuovi solo in `src/accoach/web/i18n.js`, prefisso `tablet.`, in italiano e inglese, col tono del 21/10 (`tests/tono.py` li controlla): frasi brevi col tu, virgola decimale, niente slogan, niente due punti a effetto, niente lineette a effetto, niente «!», niente emoji, mai la stessa frase in due chiavi.
- Fermo ai box = `in_pit or (in_pit_lane and speed_kmh <= 1.0)` (la regola di `coaching/pitcall.py`, `_STOPPED_KMH = 1.0`).
- Nome del file scritto: `HONE_<n>`, `n` = massimo `HONE_<k>` esistente + 1; su 409 «already exists» si prova il successivo, al massimo 4 volte (regola di `applyNow` in `engineer.js`).
- Dopo una scrittura riuscita: `POST http://<host>:8777/engineer/applied` (best-effort).
- Bottoni grandi almeno 44 px. Progetto a 1024 × 768 e 768 × 1024, nessuno scorrimento orizzontale.
- Mai scrivere in `%USERPROFILE%\Documents\ACCoach`; le prove sulla copia in scratchpad.
- Commenti nel codice nello stile dei file vicini (italiano, il perché).

## Review Focus

1. **Doppio tocco sul bottone di conferma**: deve partire una sola scrittura (bottone disattivato finché la richiesta non torna). Test nel Task 5.
2. **Proposta che arriva mentre sei già fermo ai box**: la schermata dei box deve mostrarla subito, senza ricaricare. Test nel Task 5 (render per frame, non una volta sola).
3. **Riparti dopo aver scritto**: il motore rimanda la stessa proposta con `applied: true` fino al giro dopo; l'avviso di rientro non deve tornare. Test nel Task 4.
4. **Auto/pista del frame scritte con maiuscole diverse dalla cartella** (`Imola` contro `imola`): il file di partenza si trova lo stesso. Test nel Task 2.
5. **Motore spento o WebSocket che cade**: lo stato «nessun collegamento», e la pagina si ricollega da sola ogni 3 s. Test nel Task 4.

---

### Task 1: «Fermo ai box» calcolato dal motore

**Files:**
- Modify: `src/accoach/coaching/pitcall.py` (aggiunge `stopped_in_box`, la condizione a riga ~275 la usa)
- Modify: `src/accoach/serialize.py` (`snapshot_to_dict` aggiunge `"at_box"`)
- Modify: `src/accoach/web/engineer.js` (`renderPitReminder` guarda `st.at_box`)
- Test: `tests/test_at_box.py`

**Interfaces:**
- Produces: `stopped_in_box(s: TelemetrySnapshot) -> bool` in `accoach.coaching.pitcall`; campo `at_box: bool` nel frame dal vivo (accanto a `in_pit`).

- [ ] **Step 1: Write the failing tests** in `tests/test_at_box.py`:
  - `test_acc_standing_in_the_box_is_at_box`: snapshot con `in_pit=False, in_pit_lane=True, speed_kmh=0.0` → `stopped_in_box` vero e `snapshot_to_dict(s)["at_box"] is True`.
  - `test_rolling_down_the_pit_lane_is_not_at_box`: `in_pit_lane=True, speed_kmh=60.0` → falso.
  - `test_in_pit_alone_is_at_box`: `in_pit=True, in_pit_lane=False, speed_kmh=0.0` → vero.
  - `test_stopped_on_track_is_not_at_box`: `in_pit=False, in_pit_lane=False, speed_kmh=0.0` → falso.
  - `test_threshold_is_the_briefing_one`: `speed_kmh=1.0` vero, `1.01` falso (con `in_pit_lane=True`).
  - `test_pit_reminder_reads_at_box`: nel sorgente di `engineer.js`, il corpo di `function renderPitReminder` contiene `st.at_box` e non contiene `st.in_pit`.
  Costruire gli snapshot come fanno i test esistenti di `pitcall` (`grep -rn "in_pit_lane=" tests/` per il costruttore).
- [ ] **Step 2: Run** `python -m pytest tests/test_at_box.py -q` — FAIL (`stopped_in_box` non esiste).
- [ ] **Step 3: Implement** `stopped_in_box` in `pitcall.py`, usala nella condizione del briefing al posto dell'espressione scritta lì; in `serialize.py` aggiungi `"at_box": stopped_in_box(s)` subito dopo `"in_pit"`; in `renderPitReminder` sostituisci `if (!st.in_pit)` con `if (!st.at_box)`. Il commento lungo sopra la condizione in `pitcall.py` resta, sopra la funzione.
- [ ] **Step 4: Run** `python -m pytest tests/test_at_box.py tests/ -q -k "pit or serial or engineer"` — PASS.
- [ ] **Step 5: Commit** «Fermo ai box: una regola sola, mandata nel frame».

### Task 2: Il file di partenza scelto dal processo web

**Files:**
- Modify: `src/accoach/setup/store.py` (nessun cambio di firma; solo se serve un aiuto per la data)
- Modify: `src/accoach/setup/web_api.py` (`setup_list` aggiunge `mtime`; `setup_apply` ricorda l'ultimo scritto; nuova `GET /api/setup/base`)
- Test: `tests/test_setup_base.py`

**Interfaces:**
- Produces: `GET /api/setup/base?car=<frame car>&track=<frame track>` →
  `{"car": <cartella auto>|null, "track": <cartella pista>|null, "setups": [{"name", "path", "mtime"}], "base": <path>|null, "last_written": <name>|null}`.
  `setups` in ordine di nome come oggi; `mtime` in secondi (float). `base` = ultimo file scritto da `/api/setup/apply` in questo processo per quella cartella auto/pista, se il file esiste ancora; se no il file con `mtime` più alto; `null` se non ce ne sono. Auto e pista si cercano fra le cartelle di tutte le radici confrontando in minuscolo (la regola di `sameName` in `engineer.js`).
- Produces: `GET /api/setup/list` aggiunge `"mtime"` a ogni voce (le chiavi di prima restano).

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_base.py`, riusando `SAMPLE` e lo schema di `_seed` di `tests/test_setup_api.py` (importali o copia il minimo):
  - `test_base_is_the_most_recent_file`: due file `a.json` (mtime vecchio, `os.utime`) e `b.json` (recente) → `base` termina con `b.json`, `last_written is None`.
  - `test_base_is_the_last_written_after_apply`: dopo `POST /api/setup/apply` (`as_name="HONE_1"`, `confirm=True`, un cambio `tyrePressure` slot 0 `delta_clicks=1`), poi `os.utime` su un altro file per renderlo più recente → `base` termina con `HONE_1.json` e `last_written == "HONE_1"`.
  - `test_last_written_file_deleted_falls_back`: dopo apply, cancella `HONE_1.json` → `base` è il più recente rimasto.
  - `test_case_of_frame_names_does_not_matter`: cartella `Imola`, richiesta `track=imola` e `car` in maiuscolo → `track == "Imola"` e `base` non nullo.
  - `test_unknown_combo`: auto inesistente → `{"car": None, "track": None, "setups": [], "base": None, "last_written": None}`.
  - `test_list_carries_mtime`: `/api/setup/list` → ogni voce ha `name`, `path`, `mtime` numerico.
- [ ] **Step 2: Run** `python -m pytest tests/test_setup_base.py -q` — FAIL (404 su `/api/setup/base`).
- [ ] **Step 3: Implement** in `register_setup_routes`: un dizionario locale `last_written: dict[tuple[str, str], Path]` chiave `(car_dir.lower(), track_dir.lower())`, aggiornato in `setup_apply` dopo `save` riuscito (`out.parent.parent.name`, `out.parent.name`); l'endpoint `setup_base`; `mtime` da `p.stat().st_mtime`.
- [ ] **Step 4: Run** `python -m pytest tests/test_setup_base.py tests/test_setup_api.py -q` — PASS.
- [ ] **Step 5: Commit** «Il file di partenza: l'ultimo scritto, se no il più recente».

### Task 3: Il controllo Safari 9 e `i18n.js` che traduce anche lì

**Files:**
- Create: `tests/safari9.py` (il controllo, importabile)
- Create: `tests/test_safari9.py`
- Modify: `src/accoach/web/i18n.js` (`applyStatic` e `syncSelectors`: `Array.prototype.forEach.call(root.querySelectorAll(...), fn)`)

**Interfaces:**
- Produces: `safari9_problems(src: str, kind: str) -> list[str]` in `tests/safari9.py`, `kind` in `{"js", "css"}`; ogni voce è `"<riga>: <cosa>"`. Per `js` toglie prima commenti, stringhe `'…'`/`"…"` e template string (i `${…}` dentro le template string si controllano) e poi cerca le parole e i simboli vietati dei Global Constraints come token interi (`let`/`const`/`class`/`async`/`await` con `\b`; `=>`, `...`, `?.` non seguito da cifra, `??`; `fetch(`, `.padStart(`, `.padEnd(`, `Intl.`, `Object.entries(`, `Object.values(`, `URLSearchParams`, `querySelectorAll(…).forEach` e `getElementsBy…(…).forEach`). Per `css` toglie i commenti e cerca le forme vietate dei Global Constraints.
- Produces: `TABLET_FILES = ("i18n.js", "tablet.js", "tablet.css")` in `tests/safari9.py`; i test controllano quelli che esistono (il Task 4 crea gli altri due e da lì in poi devono esistere: il test `test_tablet_files_exist` lo aggiunge il Task 4).

- [ ] **Step 1: Write the failing tests** in `tests/test_safari9.py`:
  - `test_checker_catches_each_forbidden_form`: parametrizzato su almeno `"var f = () => 1;"`, `"let a = 1;"`, `"const a = 1;"`, `"async function f() {}"`, `"var a = b ?? c;"`, `"var a = b?.c;"`, `"f(...xs);"`, `"fetch('/x');"`, `"document.querySelectorAll('a').forEach(g);"`, `"var s = x.padStart(2);"`, `"class A {}"` → ogni volta almeno un problema.
  - `test_checker_ignores_strings_and_comments`: `"// let a => 1\nvar s = 'const ?? => ...'; var t = `class ${x}`;"` → nessun problema; e `` "var t = `${a ?? b}`;" `` → un problema.
  - `test_checker_css`: `".a{display:grid}"`, `".a{width:clamp(1px,2px,3px)}"`, `".a{color:var(--x)}"` → un problema ciascuno; `"/* grid */ .a{display:flex}"` → nessuno.
  - `test_shipped_files_pass`: per ogni nome di `TABLET_FILES` che esiste in `src/accoach/web/`, `safari9_problems(...) == []`.
  - `test_i18n_parses_in_node` (`skipif` node assente): `node --check` su `i18n.js` esce con 0.
- [ ] **Step 2: Run** `python -m pytest tests/test_safari9.py -q` — FAIL (`tests/safari9.py` non esiste; poi `test_shipped_files_pass` fallisce su `i18n.js` per `.forEach`).
- [ ] **Step 3: Implement** `tests/safari9.py` e la correzione in `i18n.js`.
- [ ] **Step 4: Mutation check**: aggiungi a mano `var x = () => 1;` in fondo a una copia di `i18n.js` passata come stringa a `safari9_problems` dentro un test (`test_mutation_is_caught`), che deve trovare il problema. Run `python -m pytest tests/test_safari9.py tests/test_web_i18n_keys.py tests/test_tono.py tests/test_lingua_pagine.py -q` — PASS.
- [ ] **Step 5: Commit** «Controllo Safari 9; i testi fissi si traducono anche su Safari 9».

### Task 4: La pagina `/tablet`, in pista e avviso di rientro

**Files:**
- Create: `src/accoach/web/tablet.html`, `src/accoach/web/tablet.js`, `src/accoach/web/tablet.css`
- Modify: `src/accoach/api.py` (route `GET /tablet` → `_serve("tablet.html")`)
- Modify: `src/accoach/web/i18n.js` (chiavi `tablet.*`)
- Modify: `tests/tono.py` (`_ENGINEER_FILES` aggiunge `"tablet.html", "tablet.js"`, così le chiavi `tablet.*` cadono nella superficie `engineer`)
- Test: `tests/test_tablet_page.py`, `tests/test_safari9.py` (aggiunge `test_tablet_files_exist`)

**Interfaces:**
- Consumes: `at_box` (Task 1); `safari9_problems`, `TABLET_FILES` (Task 3).
- Produces: in `tablet.js`, `window.HoneTablet = { mode: mode, render: render }` dove
  `mode(st) -> "off" | "track" | "call" | "box"`:
  - `"off"` se `!st || !st.connected`;
  - `"box"` se `st.at_box`;
  - `"call"` se `st.engineer` ha `tag === "BOX"`, `change` non vuoto, non `applied`, e `kind` è `"propose"` o `"reverted"`;
  - altrimenti `"track"`.
  `render(st)` aggiorna il DOM ed è chiamata a ogni frame. Il boot (WebSocket, `HoneI18n.applyStatic`) parte solo se esiste `document.getElementById("tablet")`, così il file si carica in node per i test.
- Produces: elementi con id stabili per il Task 5 e la prova: `#tablet` (con `data-mode` = il risultato di `mode`), `#t-off`, `#t-track`, `#t-call`, `#t-box`, `#t-phase` (fase + cosa fare, visibile in pista e ai box).
- La porta del motore: `var WS_PORT = 8777;` come `engineer.js`. Riconnessione: `onclose` → `setTimeout(connect, 3000)`.

Contenuto per stato (spec, «I tre stati»):
- `off`: una riga (`tablet.off`) che dice che il coach non è acceso e che la pagina si ricollega da sola.
- `track`: velocità e marcia grandi; TC/ABS/mappa; temperatura e pressione delle quattro gomme (FL FR / RL RR); la striscia di gas, freno e sterzo degli ultimi 8 s su `<canvas>` (stessa logica di `tracePush`/`traceDraw` in `engineer.js`, riscritta in ES5); la fase (`#t-phase`, chiavi `eng.do.<phase.key>` con ripiego `eng.do.default` e etichetta `eng.phaseNow`, come `renderEngineer`); la proposta al volo (`tag === "AV"`) con il suo messaggio e il bottone «Fatto» che fa `POST /engineer/applied` e si nasconde (come `#av-done`; nascosto se `watched` o `applied`).
- `call`: come `track`, più `#t-call` in cima, colore suo (ambra), testo `tablet.call` (proposta) o `tablet.callRestore` (ripristino), che dice di rientrare ai box. La telemetria resta visibile sotto.
- `box`: `#t-box` (il contenuto lo fa il Task 5; qui basta il contenitore con la fase).
Numeri con `HoneI18n.fmtNum`. Un link discreto alla pagina completa (`/engineer`, chiave `tablet.full`).

- [ ] **Step 1: Write the failing tests** in `tests/test_tablet_page.py`:
  - `test_tablet_is_served_with_the_language`: `TestClient(create_api(tmp_path)).get("/tablet")` → 200, contiene `window.HONE_LANG` e `<html lang=` della lingua del config (come `tests/test_lingua_pagine.py`).
  - `test_tablet_loads_only_its_files`: gli `src` degli `<script>` e gli `href` dei `<link rel="stylesheet">` di `tablet.html` sono esattamente `/static/i18n.js`, `/static/tablet.js`, `/static/tablet.css`.
  - `test_mode_*` (`skipif` node): carica `i18n.js` e `tablet.js` in node con `var window = {HONE_LANG: "it"}; var document = undefined;` (o uno stub minimo, se `i18n.js` lo richiede al boot) e stampa `HoneTablet.mode(frame)` per i frame:
    - `{connected: false}` → `"off"`; `null` → `"off"`;
    - `{connected: true, at_box: false, engineer: null}` → `"track"`;
    - proposta `{kind: "propose", tag: "BOX", change: [{param: "tyrePressure", slot: 0, delta_clicks: 1}]}` → `"call"`;
    - la stessa con `applied: true` → `"track"` (Review Focus 3);
    - ripristino `{kind: "reverted", tag: "BOX", change: [...]}` → `"call"`;
    - proposta `tag: "AV"` → `"track"`;
    - `{connected: true, at_box: true, engineer: <proposta>}` → `"box"`.
  - `test_reconnects`: il sorgente di `tablet.js` contiene `onclose` e `setTimeout(` con `3000`.
  - in `tests/test_safari9.py`: `test_tablet_files_exist` → `tablet.js` e `tablet.css` esistono (così `test_shipped_files_pass` li controlla davvero).
- [ ] **Step 2: Run** `python -m pytest tests/test_tablet_page.py tests/test_safari9.py -q` — FAIL.
- [ ] **Step 3: Implement** route, file e chiavi. Layout in flexbox: in orizzontale velocità/marcia a sinistra e gomme a destra, striscia sotto; in verticale tutto in colonna. Dimensioni in px fissi pensate per 1024 × 768 (velocità ~120 px, marcia ~120 px, il resto ≥ 18 px), tema scuro come `engineer.css` ma con colori scritti per esteso.
- [ ] **Step 4: Run** `python -m pytest tests/test_tablet_page.py tests/test_safari9.py tests/test_tono.py tests/test_web_i18n_keys.py -q` — PASS. Se `test_web_i18n_keys` vuole sapere quali file usano le chiavi, aggiungi `tablet.html`/`tablet.js` dove elenca le pagine.
- [ ] **Step 5: Commit** «La vista tablet: in pista e avviso di rientro».

### Task 5: La schermata dei box e il bottone che scrive

**Files:**
- Modify: `src/accoach/web/tablet.html`, `tablet.js`, `tablet.css`, `i18n.js` (chiavi `tablet.*`)
- Test: `tests/test_tablet_box.py`

**Interfaces:**
- Consumes: `GET /api/setup/base` (Task 2), `POST /api/setup/preview`, `POST /api/setup/apply` (risposta: `name`, `reload_hint`), `POST http://<host>:8777/engineer/applied`, `mode` e `#t-box` (Task 4).
- Produces: in `window.HoneTablet` anche `nextName(names: string[]) -> string` (`"HONE_" + (max HONE_<k> + 1)`, maiuscole ignorate nel confronto, `HONE_1` se nessuno) e `changesFor(eng) -> [{param, slot, delta_clicks}]` (da `eng.change`, `slot` `null` → `0` come `prepareChange`).

Schermata (spec, «La schermata dei box», nell'ordine): fase; la modifica con, per ogni leva, nome, ruota/lato, valore da→a (dalla `diff` di `/api/setup/preview` sul file di partenza: `label`, `slot`, `old_phys`→`new_phys`, `old_click`→`new_click`), il perché (`rationale`), la fiducia (`eng.conf.<c>`) e con `low` l'avvertenza `eng.lowConf`; il file di partenza per nome con una `<select>` sui `setups` di `/api/setup/base`; il bottone `#t-write` (`tablet.write`, o `tablet.writeRestore` per un ripristino); la conferma `#t-confirm` con l'elenco delle leve e il nome del file nuovo, bottoni `#t-confirm-ok` e `#t-confirm-no`; dopo la scrittura `#t-done` con il nome scritto e `reload_hint`; per un ripristino anche `#t-restored` («L'ho già rimesso com'era», `POST /engineer/applied`); senza modifica la fase e `eng.message`, nessun bottone.

Regole:
- `/api/setup/base` si chiede quando entri nello stato `box` e quando cambiano auto/pista del frame, non a ogni frame. L'anteprima si ricalcola quando cambiano il file di partenza o `eng.change` (confronto per JSON), non a ogni frame.
- Le richieste con `XMLHttpRequest`, una funzione `xhr(method, url, body, cb)`. `lang` passato come query a `preview`/`apply` come fa `engineer.js`.
- Scrittura: `#t-confirm-ok` disattivato appena premuto (Review Focus 1); `apply` con `as_name = nextName(nomi dei setups)`, `confirm: true`, `changes: changesFor(eng)`; su 409 col testo «already exists» si riprova col nome successivo, massimo 4 tentativi; su altro errore un messaggio (`tablet.writeErr` + il dettaglio) e il bottone torna attivo. Dopo il successo: `POST /engineer/applied`, `#t-done`, e la base ridiventa il file appena scritto (richiedi di nuovo `/api/setup/base`).
- Se arriva una proposta mentre sei già in `box`, la schermata la mostra al frame dopo (Review Focus 2).

- [ ] **Step 1: Write the failing tests** in `tests/test_tablet_box.py` (`skipif` node per quelli in node):
  - `test_next_name`: `nextName([])` → `"HONE_1"`; `nextName(["base", "HONE_1", "hone_3"])` → `"HONE_4"`; `nextName(["HONE_x"])` → `"HONE_1"`.
  - `test_changes_for`: `changesFor({change: [{param: "tyrePressure", slot: null, delta_clicks: 2}]})` → `[{param: "tyrePressure", slot: 0, delta_clicks: 2}]`.
  - `test_write_path_in_source`: nel sorgente di `tablet.js`: `/api/setup/apply`, `confirm: true`, `/engineer/applied`, `already exists`, e il bottone di conferma messo `disabled = true` prima della richiesta.
  - `test_box_write_end_to_end` (Python, nessun browser): con `create_api(laps_dir, setups_root=...)` e `SAMPLE` di `tests/test_setup_api.py`, la sequenza che fa la pagina — `GET /api/setup/base`, `POST /api/setup/preview` con `changesFor` di una proposta, `POST /api/setup/apply` con `nextName` — scrive `HONE_1.json` con la pressione cambiata, e `GET /api/setup/base` dopo dà `last_written == "HONE_1"`. È la prova che i contratti dei Task 2 e 5 combaciano.
- [ ] **Step 2: Run** `python -m pytest tests/test_tablet_box.py -q` — FAIL.
- [ ] **Step 3: Implement** la schermata e le regole sopra.
- [ ] **Step 4: Run** `python -m pytest tests/test_tablet_box.py tests/test_tablet_page.py tests/test_safari9.py tests/test_tono.py -q` — PASS.
- [ ] **Step 5: Commit** «La vista tablet ai box: la modifica e il bottone che la scrive».

### Task 6: Il QR, il preferito vecchio e la guida

**Files:**
- Modify: `src/accoach/netinfo.py` (`device_urls` aggiunge `"tablet": base + "/tablet"`)
- Modify: `src/accoach/livepanel_ui.py` (il QR e l'indirizzo sotto usano `urls["tablet"]`)
- Modify: `src/accoach/web/engineer.html` (nel `<head>`, prima di ogni altro script, uno script ES3 che prova `new Function("async function f(){}")` e su errore fa `location.replace("/tablet")`)
- Modify: `GUIDA.md`, `docs/FAQ.md` (il passo «Collega il tablet» e la sezione sul tablet dicono che si apre la vista tablet, cosa mostra nei tre stati e che la pagina completa resta su `/engineer`)
- Test: `tests/test_tablet_wiring.py`, più i test esistenti di `netinfo`/`livepanel` che fissano l'URL

**Interfaces:**
- Consumes: la route `/tablet` (Task 4).

- [ ] **Step 1: Write the failing tests** in `tests/test_tablet_wiring.py`:
  - `test_device_urls_has_tablet`: `device_urls(8778, ip="192.168.1.23")["tablet"] == "http://192.168.1.23:8778/tablet"`, e le chiavi di prima restano.
  - `test_qr_points_to_tablet`: nel sorgente di `livepanel_ui.py` il QR usa `urls["tablet"]` e non `urls["engineer"]`.
  - `test_engineer_redirects_old_browsers`: in `engineer.html` lo script con `location.replace("/tablet")` sta nel `<head>` prima di ogni `<script src=`, e il suo testo passa `safari9_problems(..., "js")`.
  - `test_redirect_skips_modern_browsers` (`skipif` node): eseguito in node con `location = {replace: function(u){ console.log(u) }}`, non stampa niente (node legge `async`).
- [ ] **Step 2: Run** `python -m pytest tests/test_tablet_wiring.py -q` — FAIL.
- [ ] **Step 3: Implement**; aggiorna i test esistenti che si aspettano `/engineer` nel QR (`grep -rn "s2_\|liveQr\|device_urls" tests/`). Testi della guida col tono deciso; solo cose vere sul codice.
- [ ] **Step 4: Run** la suite intera `python -m pytest -q -p no:cacheprovider` — PASS.
- [ ] **Step 5: Commit** «Il QR apre la vista tablet; il preferito vecchio ci arriva da solo».

### Dopo i task (chi coordina)

Prova nel browser sulla copia dell'archivio in scratchpad, mai `Documents\ACCoach`: processo web di prova sulla copia, un finto motore sulla porta 8777 che manda frame scritti a mano per i quattro stati (`/ws`) e risponde a `/engineer/applied`; Playwright **WebKit** a 1024 × 768 e 768 × 1024; schermate di ogni stato; una scrittura vera di un file d'assetto nella cartella di prova (`setups_root` della copia). Poi la revisione d'insieme, il registro in `docs/superpowers/ledgers/2026-10-22-vista-tablet.md`, la fusione nel main locale. La prova sull'iPad vero resta aperta finché Norton blocca.
