# Impronta dell'assetto caricato — piano di lavoro

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** l'Ingegnere riconosce ai box quale file di setup ACC è montato, se ne accorge quando l'assetto cambia o non è quello scritto, non scrive su un assetto non salvato; e il test finale in pista è preparato (registro, rigioco, verifica dal vivo, piano di prova).

**Architecture:** un modulo puro `engineer/fingerprint.py` (letture, valori dei file, confronto, osservatore dei box) alimentato dal motore a ogni frame; il motore costruisce un `SetupReport` e lo passa al `RaceEngineer`, che applica le regole R1–R3 e le espone come `Decision`. Le pagine leggono `loaded` nel blocco dell'Ingegnere e mandano al server il file scritto o scelto.

**Tech Stack:** Python 3 (dataclass, pytest), FastAPI (`server.py`), JavaScript delle pagine (`web/engineer.js`, `web/tablet.js`, `web/i18n.js`), openpyxl per il piano di prova.

**Spec:** `docs/superpowers/specs/2026-11-16-impronta-setup-design.md`

## Global Constraints

- Ogni testo per il pilota in italiano e inglese, nei dizionari che ci sono già (`core._DECISION_MSG`, `web/i18n.js`), e deve passare i controlli di tono (`tests/test_engineer_tono.py`, modulo `tono`).
- Nessuna frase a voce nuova (niente WAV da registrare): le richieste ai box usano `confirm_base`, che fa già scattare «Rientra ai box, scegli l'assetto.».
- Costanti dello spec: `COLD_PSI_VERIFIED = False`; tolleranza pressioni a freddo `0,3 psi`; pressione a freddo del file `20,3 + 0,1 × click`; ripartitore `0,002` di frazione per click, tolleranza mezzo click (`0,001`).
- TC, ABS, mappa del file sono `basicSetup.electronics.tC1`, `.abs`, `.eCUMap`; il ripartitore `advancedSetup.mechanicalBalance.brakeBias` (click); le pressioni `basicSetup.tyres.tyrePressure` (click, FL FR RL RR); la benzina `basicSetup.strategy.fuel`.
- Il ripartitore si tara **solo** dalla risposta del pilota; il confronto usa **file + modifiche al volo accettate** (`carry`).
- La suite si lancia sempre con la casa finta: `USERPROFILE=<tmp> HOME=<tmp> python -m pytest -q -p no:cacheprovider`. I test non toccano mai i file veri del pilota (solo `tmp_path`).
- Messaggi di commit in italiano, con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Niente push, niente installazione.
- Assetto Corsa 1 (`is_acc` falso): l'impronta tace e tutto resta come oggi.

## Review Focus

1. Cartella della pista con maiuscole diverse dallo snapshot (`Imola` contro `imola`): il riconoscimento deve trovarla lo stesso — test in Task 4.
2. Cartella con un file rotto, un `.ini` o un JSON senza `electronics`: quel file si salta, gli altri si confrontano — test in Task 1.
3. Uscita dalla corsia box senza essersi fermati in piazzola (drive-through, uscita diretta dal garage): impronta senza pressioni a freddo, gli altri campi valgono — test in Task 2.
4. Gioco in pausa o scollegato a metà sosta, o cambio di auto/pista: nessuna uscita fantasma — test in Task 2.
5. Cartella dei log non scrivibile: un giro non si rompe mai per il registro — test in Task 5.

---

### Task 1: Letture, valori dei file e confronto

**Files:**
- Create: `src/accoach/engineer/fingerprint.py`
- Test: `tests/test_impronta.py`

**Interfaces:**
- Produces:
  - costanti `COLD_PSI_VERIFIED: bool = False`, `PSI_TOL = 0.3`, `BIAS_STEP = 0.002`, `BIAS_TOL = 0.001`
  - `@dataclass(frozen=True) Reading(tc: int, abs: int, emap: int, bias: float, cold_psi: tuple[float, float, float, float] | None, fuel: float, air_temp: float, road_temp: float)` con `to_dict() -> dict`, `from_dict(d) -> Reading`, `from_snapshot(s, cold_psi) -> Reading`; `-1` / `-1.0` = non letto
  - `@dataclass(frozen=True) FileValues(name: str, path: str, tc: int, abs: int, emap: int, bias_clicks: int, cold_psi: tuple[float, ...], fuel: int)`
  - `file_values(path: Path) -> FileValues | None`
  - `@dataclass(frozen=True) FieldDiff(field: str, seen: float, want: float)`; `field` è uno di `"tc" "abs" "emap" "bias" "psi_fl" "psi_fr" "psi_rl" "psi_rr"`
  - `compare(r: Reading, f: FileValues, *, carry: dict[str, int], bias_offset: float | None) -> tuple[tuple[FieldDiff, ...], tuple[FieldDiff, ...]]` — (campi certi, pressioni)
  - `@dataclass(frozen=True) Match(state: str, names: tuple[str, ...], best: str | None, probable: bool, diffs: dict[str, tuple[FieldDiff, ...]])`; `state` ∈ `"match" "ambiguous" "unsaved" "unknown"`
  - `match(r: Reading, files: list[FileValues], *, carry: dict[str, int], bias_offset: float | None) -> Match`
  - `changed(before: Reading, after: Reading) -> tuple[FieldDiff, ...]`
  - `describe(diffs, lang: str) -> str`

Regole che i test fissano:
- `carry` ha chiavi `"tC1" "abs" "eCUMap" "brakeBias"`, delta in click sommati ai valori del file prima del confronto.
- Il ripartitore entra in `compare` solo con `bias_offset` non `None`: atteso `bias_offset + BIAS_STEP × (click + carry)`, diverso se lo scarto supera `BIAS_TOL`.
- Pressioni del file: `20.3 + 0.1 × click`; diverse se lo scarto supera `PSI_TOL`. Con `COLD_PSI_VERIFIED` falso stanno nel secondo elemento e non decidono la compatibilità.
- `match`: `unknown` se TC, ABS o mappa non letti o nessun file; `unsaved` se nessun file è compatibile sui campi certi (`best` = il file con meno differenze certe, `diffs` piene); `match` se uno solo; con più compatibili, `match` con `probable=True` se uno solo ha tutte le pressioni entro `PSI_TOL` (letture presenti), altrimenti `ambiguous`.
- `changed`: TC, ABS, mappa diversi se entrambi letti; ripartitore se entrambi letti e scarto > `BIAS_TOL`; pressioni solo con `COLD_PSI_VERIFIED`.
- `describe` in italiano: `"TC 6 invece di 3, ABS 6 invece di 4, ripartitore 75,0 % invece di 64,0 %"` (numeri con `textfmt.fmt_num`); in inglese `"TC 6 instead of 3, …, brake bias 75.0 % instead of 64.0 %"`. Le pressioni: `"anteriore sinistra 25,9 psi invece di 26,0 psi"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_impronta.py`, con file ACC scritti in `tmp_path` sul modello di `SAMPLE` di `tests/test_setup_format.py`, coi valori di Imola dell'archivio:

```python
IMOLA_0 = dict(press=[57, 52, 51, 48], tc=3, abs=4, emap=0, bias=0, fuel=48)
HONE_7  = dict(press=[60, 55, 44, 41], tc=3, abs=4, emap=0, bias=0, fuel=48)
HONE_8  = dict(press=[52, 47, 44, 41], tc=3, abs=4, emap=0, bias=0, fuel=48)
PRESET  = Reading(tc=6, abs=6, emap=0, bias=0.75, cold_psi=None, fuel=59.1, air_temp=0, road_temp=0)

def test_the_game_preset_of_0811_is_not_a_saved_file(tmp_path):
    m = match(PRESET, _files(tmp_path, IMOLA_0, HONE_7, HONE_8), carry={}, bias_offset=None)
    assert m.state == "unsaved" and m.names == ()
    assert "TC 6 invece di 3" in describe(m.diffs[m.best], "it")

def test_three_files_with_the_same_electronics_are_ambiguous_without_pressures(tmp_path): ...
    # Reading(tc=3, abs=4, emap=0, bias=0.64, cold_psi=None) → state "ambiguous", 3 nomi
def test_cold_pressures_pick_the_probable_file(tmp_path): ...
    # cold_psi=(25.5, 25.0, 24.7, 24.4) → state "match", best "HONE_8", probable True
def test_an_accepted_tc_click_keeps_the_file_recognised(tmp_path): ...
    # Reading tc=4 con carry={"tC1": +1} → "match"; senza carry → "unsaved"
def test_bias_counts_only_once_calibrated(tmp_path): ...
    # bias 0.75 su file a 0 click: bias_offset=None → nessun FieldDiff "bias"; bias_offset=0.64 → FieldDiff bias
def test_a_broken_or_ac_file_is_skipped(tmp_path): ...
    # file_values su JSON rotto, su .ini e su JSON senza "electronics" → None
def test_changed_sees_tc_and_bias_but_not_a_tenth_of_a_percent(): ...
    # 0.640 → 0.6405: nessuna differenza; 0.64 → 0.75 e TC 3 → 6: due FieldDiff
def test_unknown_when_the_aids_are_not_read(tmp_path): ...
    # tc=-1 → state "unknown"
```

- [ ] **Step 2: Run** `python -m pytest tests/test_impronta.py -q` — Expected: FAIL, `ModuleNotFoundError: accoach.engineer.fingerprint`.
- [ ] **Step 3: Implement** in `src/accoach/engineer/fingerprint.py` le interfacce sopra. `file_values` legge solo `.json` con `setup.acc_format.load`, e qualunque eccezione o campo mancante dà `None`.
- [ ] **Step 4: Run** `python -m pytest tests/test_impronta.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Impronta: letture, valori dei file di setup e confronto"`

### Task 2: L'osservatore dei box

**Files:**
- Modify: `src/accoach/engineer/fingerprint.py`
- Test: `tests/test_impronta.py`

**Interfaces:**
- Consumes: `Reading.from_snapshot`.
- Produces: `class PitWatch` con `update(snap: TelemetrySnapshot) -> str | None` (`"live"`, `"exit"` o `None`), attributi `entry: Reading | None`, `live: Reading | None`, `exit: Reading | None`, e `reset() -> None`.

Comportamento:
- frame non connessi, non `LIVE` o con `is_acc` falso: `None`, e lo stato della sosta si azzera (niente uscita fantasma dopo una pausa o un cambio di gioco);
- in pista (`in_pit` e `in_pit_lane` falsi) tiene l'ultima lettura: diventa `entry` al primo frame in corsia box;
- in piazzola da fermo (`in_pit` e `speed_kmh < 1`) salva le pressioni a freddo (tutte e quattro > 0, arrotondate a 0,1) e aggiorna `live`; risponde `"live"` solo quando `live` cambia;
- al primo frame in pista dopo almeno un frame in corsia box o piazzola risponde `"exit"`, con `exit` letto da quel frame e le pressioni a freddo dell'ultima sosta da ferma (o `None` se non c'è stata).

- [ ] **Step 1: Write the failing tests** (snapshot da `dataclasses.replace(TelemetrySnapshot.disconnected(), connected=True, status=ACStatus.LIVE, is_acc=True, …)`):
  - `test_a_stop_in_the_box_gives_cold_pressures_and_an_exit` — pista → corsia → piazzola ferma con pressioni (26.0, 25.5, 25.4, 25.1) → corsia → pista: eventi `[None…, "live", …, "exit"]`, `exit.cold_psi == (26.0, 25.5, 25.4, 25.1)`, `entry.tc` uguale al TC dell'ultimo frame in pista.
  - `test_a_drive_through_exits_without_cold_pressures` — corsia senza fermarsi → `"exit"` con `cold_psi is None`.
  - `test_live_fires_only_when_something_changes` — tre frame fermi uguali → un solo `"live"`; TC cambiato in piazzola → un secondo `"live"`.
  - `test_a_pause_in_the_pits_is_not_an_exit` — piazzola → frame `status=PAUSE` → pista: nessun `"exit"`.
  - `test_assetto_corsa_stays_silent` — `is_acc=False`: sempre `None`.
- [ ] **Step 2: Run** `python -m pytest tests/test_impronta.py -q -k "box or drive or live or pause or assetto"` — Expected: FAIL (`PitWatch` non definito).
- [ ] **Step 3: Implement** `PitWatch` in `fingerprint.py`.
- [ ] **Step 4: Run** lo stesso comando — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Impronta: l'osservatore dei box, a freddo da fermo e all'uscita"`

### Task 3: Le regole dell'Ingegnere (R1, R2, R3) e la taratura del ripartitore

**Files:**
- Modify: `src/accoach/engineer/core.py`
- Test: `tests/test_engineer_impronta.py`

**Interfaces:**
- Produces, in `core.py`:
  - `@dataclass(frozen=True) SetupReport(state: str, name: str | None, probable: bool, changed: str, expected: str | None, expected_ok: bool | None, expected_diff: str, psi_doubt: str, unsaved_diff: str)` con `to_dict()` / `from_dict()`. Le stringhe sono già in parole (`fingerprint.describe`); `core` non importa `fingerprint`.
  - `RaceEngineer.carry: list[AtomicChange]` — modifiche `AV` accettate dopo l'ultima scrittura ai box; **non** va su disco.
  - `RaceEngineer.carry_clicks() -> dict[str, int]`
  - `RaceEngineer.setup_seen(report: SetupReport, *, at_exit: bool) -> Decision | None`
  - `RaceEngineer.base_confirmed(*, expected: bool | None = None) -> Decision | None` (estende quella del main, che resta valida chiamata senza argomenti)
  - `RaceEngineer.bias_offset: float | None` e `RaceEngineer.learn_bias(observed: float, clicks: int) -> None`; in `state()`/`restore()` le chiavi `"bias_offset"` e `"bias_pending"`.

Regole (i test le fissano):
- **carry**: `_record` di una modifica `AV` aggiunge i suoi `AtomicChange`; `mark_applied` di una modifica `BOX` (non ripristino) svuota `carry` e segna «scritta da HONE, da controllare all'uscita».
- **R2** (all'uscita, dopo una scrittura ai box): `expected_ok is False` → la prova resta aperta con `laps_seen = 0`, la finestra si svuota, e la decisione tenuta è `STAND_DOWN` con `confirm_base=True` e il messaggio `"All'uscita dai box l'assetto non è quello che ho scritto ({name}): {diff}. Ai box carica {name}."`; `observe` la ripete a ogni giro, senza contare i giri. Si scioglie con `setup_seen(..., expected_ok=True)` (dal vivo o all'uscita) → `EVALUATING` con `"Ora TC, ABS e mappa sono quelli di {name}. Le pressioni le controllo a fine prova."`, oppure con `base_confirmed(expected=True)` (stesso esito) o `base_confirmed(expected=False)` (prova buttata, base da capo, `COLLECT`). Con `expected_ok` vero e `psi_doubt` non vuoto: coda `" Le pressioni a freddo non sembrano quelle di {name}: {psi_doubt}."` sui messaggi `EVALUATING` fino al verdetto.
- **R1** (all'uscita, nessuna scrittura HONE in quella sosta, `changed` non vuoto): finestra e uscite svuotate; senza prova → `COLLECT` `"Hai cambiato assetto rispetto allo stint di prima: {changed}. Rifaccio la base."`; con una prova aperta → `_hold_base` del main con la stessa frase seguita da `base_ask`.
- **R3**: `state == "unsaved"` mette l'assetto non salvato (anche dal vivo); qualunque altro stato lo toglie. Con l'assetto non salvato `_propose` di una modifica `BOX` non tiene niente in sospeso e risponde `STAND_DOWN` `"L'assetto in macchina non è fra i file salvati: {unsaved_diff}. Se hai girato le manopole, rimettile come nel file; se è un assetto nuovo, in garage salvalo con un nome e caricalo."`; le `AV` passano. Quando si toglie, `setup_seen` risponde `"In macchina ora c'è {name}: le modifiche ai box le posso scrivere."` e, se la base c'è e non ci sono prove, il risultato di `_advance()` subito. `base_confirmed(...)` lo toglie sempre (scelta esplicita).
- **Taratura**: `learn_bias(observed, clicks)` calcola `observed − BIAS_STEP × clicks` (`BIAS_STEP = 0.002` copiato qui, non importato). Prima risposta → `bias_offset`. Risposta che concorda entro mezzo click → resta. Risposta discorde → `bias_offset = None`, `bias_pending` = la nuova; la risposta dopo, se concorda con `bias_pending`, la promuove.
- Testi nuovi in `_DECISION_MSG`, chiavi `setup_changed`, `setup_wrong`, `setup_right`, `setup_psi_doubt`, `setup_unsaved`, `setup_saved`, in italiano e inglese.

- [ ] **Step 1: Write the failing tests** in `tests/test_engineer_impronta.py` (motore `RaceEngineer(GT3_PROFILE, min_stable=3)`, report costruiti a mano):
  - `test_an_unrequested_change_restarts_the_base` — 3 giri buoni, `setup_seen(SetupReport(state="match", changed="TC 6 invece di 3", …), at_exit=True)` → `COLLECT`, `len(eng.window) == 0`, `"Rifaccio la base"` nel messaggio (italiano).
  - `test_a_change_during_a_test_is_not_judged` — prova aperta, R1 → `STAND_DOWN` con `confirm_base`.
  - `test_the_wrong_file_after_a_write_pauses_the_test_and_keeps_the_base` — proposta pressioni, `mark_applied`, `setup_seen(expected_ok=False, expected="HONE_8", expected_diff="TC 6 invece di 3")` → `STAND_DOWN` `confirm_base`; due `observe` → stessa decisione e `active.laps_seen == 0`; `setup_seen(expected_ok=True)` → `EVALUATING`; `active.base_pressures` invariato.
  - `test_the_answer_on_the_page_resumes_or_drops_the_paused_test` — `base_confirmed(expected=True)` → `EVALUATING`, prova aperta; `base_confirmed(expected=False)` → `COLLECT`, `eng.active is None`.
  - `test_an_unsaved_setup_measures_but_does_not_write` — `state="unsaved"`, pressione fuori finestra → `STAND_DOWN` col testo R3, `eng._pending is None`; poi `setup_seen(state="match", name="HONE_8")` → `PROPOSE` subito.
  - `test_wheel_levers_still_pass_on_an_unsaved_setup` — una proposta `AV` (ripartitore) → `PROPOSE`.
  - `test_an_accepted_wheel_change_is_carried_until_the_next_box_write` — modifica `AV` tenuta → `carry_clicks() == {"brakeBias": +1}`; `mark_applied` di una `BOX` → `{}`.
  - `test_bias_is_learned_only_from_agreeing_answers` — `learn_bias(0.64, 0)` → `0.64`; `learn_bias(0.7, 0)` → `None`; `learn_bias(0.7, 0)` → `0.7`; sopravvive a `state()`/`restore()`.
  - `test_a_psi_doubt_rides_on_the_counter` — `expected_ok=True`, `psi_doubt` non vuoto → il prossimo `EVALUATING` lo porta in coda.
- [ ] **Step 2: Run** `python -m pytest tests/test_engineer_impronta.py -q` — Expected: FAIL (`SetupReport` non definito).
- [ ] **Step 3: Implement** le interfacce e le regole in `core.py`; `observe` controlla la decisione tenuta di R2 subito dopo `_held_revert` e `_held_base`; `progress()` la tratta come `_held_base` (nessun contatore).
- [ ] **Step 4: Run** `python -m pytest tests/test_engineer*.py tests/test_assetto_di_partenza.py -q` — Expected: PASS, compresi i controlli di tono sui testi nuovi.
- [ ] **Step 5: Commit** `git commit -m "Ingegnere: cambio di assetto, file sbagliato all'uscita, assetto non salvato"`

### Task 4: Il motore e il server

**Files:**
- Modify: `src/accoach/setup/store.py`, `src/accoach/engine.py`, `src/accoach/server.py`
- Test: `tests/test_impronta_motore.py`

**Interfaces:**
- Consumes: `PitWatch`, `file_values`, `match`, `compare`, `changed`, `describe` (Task 1–2); `SetupReport`, `setup_seen`, `carry_clicks`, `bias_offset`, `learn_bias`, `base_confirmed(expected=…)` (Task 3).
- Produces:
  - `store.find_setup_files(car: str, track: str, roots=DEFAULT_ROOTS) -> list[Path]` — cartelle auto e pista confrontate in minuscolo, come `/api/setup/base`; solo `.json`.
  - `CoachEngine.mark_setup_applied(path: str | None = None)`, `CoachEngine.mark_base_confirmed(path: str | None = None)` — il percorso viaggia col segnale fino al tick.
  - `POST /engineer/applied` e `POST /engineer/base` accettano un corpo JSON facoltativo `{"path": "<percorso>"}` (corpo vuoto o `{}` vale come oggi).
  - nel blocco dell'Ingegnere (anche quello parziale) la chiave `"loaded"`: `None` oppure `{"state", "name", "names", "probable", "at": "live"|"exit", "observed": Reading.to_dict()}`.
  - su una `PROPOSE` con tag `BOX` e `carry` non vuoto: `"change"` porta anche le voci di `carry` (`{"param", "slot", "delta_clicks"}`), e `"carry"` le elenca a parte.

Comportamento:
- `PitWatch` nasce con l'Ingegnere e si azzera a ogni cambio di auto o pista.
- A ogni evento `"live"`/`"exit"`: file da `find_setup_files`, `match` con `carry_clicks()` e `bias_offset`, file atteso = l'ultimo percorso ricevuto da `/engineer/applied` o `/engineer/base` (se c'è e si legge), `expected_ok` = nessuna differenza certa contro di lui, `psi_doubt` = `describe` delle pressioni contro di lui, `changed` = `describe(changed(entry, exit))` solo all'uscita e solo se nessuna scrittura è arrivata durante quella sosta, `unsaved_diff` = `describe` delle differenze dal file più vicino. Il risultato di `setup_seen` diventa la decisione corrente e lo stato si salva.
- Sulla risposta della pagina (`/engineer/base` con un percorso): `learn_bias` con la lettura dal vivo (o quella dell'uscita) e i click del file più `carry`, e `base_confirmed(expected=<percorso uguale al file scritto>)`.

- [ ] **Step 1: Write the failing tests**, motore come in `tests/test_assetto_di_partenza.py` (`CoachEngine` con `tmp_path`, lettore finto che restituisce snapshot scritti dal test, cartella setup in `tmp_path` passata come radice):
  - `test_find_setup_files_ignores_the_case_of_the_track` — cartella `Imola`, richiesta `imola` → trovati.
  - `test_the_frame_says_which_file_is_in_the_car` — piazzola ferma con TC 3 / ABS 4 / pressioni di HONE_8 → `_engineer_block()["loaded"]["name"] == "HONE_8"`, `probable is True`.
  - `test_the_page_tells_the_server_which_file_it_wrote` — `POST /engineer/applied` con `{"path": …}` (TestClient su `server`) → il file atteso nel motore è quello.
  - `test_a_write_then_the_wrong_file_at_the_exit_asks_at_once` — proposta, `mark_setup_applied(path=HONE_8)`, uscita con TC 6 → decisione `STAND_DOWN` con `confirm_base`.
  - `test_a_box_proposal_carries_the_wheel_changes` — dopo un `AV` ripartitore tenuto, la `PROPOSE` pressioni ha in `change` anche `{"param": "brakeBias", "slot": None, "delta_clicks": 1}`.
- [ ] **Step 2: Run** `python -m pytest tests/test_impronta_motore.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** in `store.py`, `engine.py`, `server.py`.
- [ ] **Step 4: Run** `python -m pytest tests/test_impronta_motore.py tests/test_assetto_di_partenza.py tests/test_chiamata_attesa.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Motore: riconosce l'assetto ai box e lo passa all'Ingegnere e alle pagine"`

### Task 5: Il registro della sessione

**Files:**
- Create: `src/accoach/engineer/session_log.py`
- Modify: `src/accoach/engine.py`
- Test: `tests/test_registro_sessione.py`

**Interfaces:**
- Produces: `class SessionLog(folder: Path, clock: Callable[[], datetime] = datetime.now)` con `path_for(day: date) -> Path` (`ingegnere-AAAAMMGG.jsonl`) e `write(kind: str, **fields) -> None`: una riga JSON `{"t": "<ISO locale>", "kind": kind, …}`, mai un'eccezione verso chi chiama.
- Il motore scrive in `paths.logs_dir()`:
  - `"lap"` dopo ogni `observe`: `car`, `track`, `lap_ms`, `stable`, `warm`, `stint`, `settling`, `kind`, `message`, `progress`, `reading` (le pressioni della lettura a regime o `None`);
  - `"setup"` a ogni evento dei box: `at`, `report` (`SetupReport.to_dict()`), `reading`, `entry`, `files` (nomi), `expected`;
  - `"applied"` e `"base"` con `path`.

- [ ] **Step 1: Write the failing tests:** `test_each_lap_and_each_pit_exit_leave_a_line` (motore finto del Task 4, un giro e un'uscita → righe `"lap"` e `"setup"` nel file del giorno); `test_an_unwritable_folder_never_breaks_a_lap` (cartella che è un file → `observe` va a buon fine e nessuna eccezione); `test_the_log_has_no_personal_data` (nessun percorso con la casa dell'utente: i percorsi dei setup sono scritti relativi alla radice dei setup).
- [ ] **Step 2: Run** `python -m pytest tests/test_registro_sessione.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** `session_log.py` e le quattro scritture nel motore.
- [ ] **Step 4: Run** lo stesso comando — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Ingegnere: registro della sessione, un giro e una sosta per riga"`

### Task 6: Le pagine

**Files:**
- Modify: `src/accoach/web/engineer.js`, `src/accoach/web/tablet.js`, `src/accoach/web/i18n.js`, `src/accoach/web/engineer.html`, `src/accoach/web/tablet.html`, `GUIDA.md`, `docs/FAQ.md` (e la guida inglese, se il test di parità la chiede)
- Test: `tests/test_impronta_pagine.py`

**Interfaces:**
- Consumes: `engineer.loaded` e `engineer.carry` nel frame (Task 4); `POST /engineer/applied` e `/engineer/base` con `{"path"}`.

Comportamento:
- `afterWrite` (engineer.js) e la scrittura del tablet mandano `{"path": res.path}` a `/engineer/applied`; `sendAnswer` e la risposta del tablet mandano `{"path"}` a `/engineer/base`.
- Una riga sola sotto la strada, su tutte e due le pagine: `"In macchina: {name}"` (con `"probabilmente "` davanti se `probable`), `"Assetto non salvato"`, `"Non riconosciuto"` (stati `ambiguous`/`unknown`); nascosta con `loaded` nullo.
- Con la domanda «Quale assetto hai caricato?» aperta, la voce del file riconosciuto nella tendina porta `" · in macchina"`; la tendina resta vuota (niente scelta automatica).
- File di partenza della pagina diverso dal file riconosciuto (stato `match`): avviso visibile `"In macchina c'è {loaded}, stai modificando {base}."` accanto al nome del file; non blocca la scrittura.
- Le voci di `carry` nella proposta: una riga `"Nel file metto anche le modifiche al volo già tenute."` sotto la proposta.
- Guida e FAQ: un paragrafo «L'Ingegnere riconosce l'assetto ai box» con le tre risposte e cosa fare in ciascuna.

- [ ] **Step 1: Write the failing tests** col banco JS che c'è già (`_BOX_HARNESS` di `tests/test_tablet_box.py`, `needs_node`): corpo con `path` nelle due chiamate di ciascuna pagina; la riga `loaded` nei tre stati; il suffisso `" · in macchina"` senza selezione; l'avviso col file diverso; le chiavi nuove di `i18n.js` in italiano e inglese e nei controlli di tono della superficie `engineer`.
- [ ] **Step 2: Run** `python -m pytest tests/test_impronta_pagine.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** nelle pagine e nella guida.
- [ ] **Step 4: Run** `python -m pytest tests/test_impronta_pagine.py tests/test_tablet_box.py tests/test_engineer_strip.py tests/test_assetto_di_partenza.py -q` più i test della guida — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Pagine: l'assetto in macchina, il file scritto al server, l'avviso se non torna"`

### Task 7: Il rigioco come comando

**Files:**
- Create: `src/accoach/engineer/replay.py`
- Modify: `src/accoach/__main__.py` (comando e riga d'aiuto)
- Test: `tests/test_rigioco.py`

**Interfaces:**
- Consumes: `build_lap_stats`, `engineer_for`, `load_lap`, `SetupReport.from_dict`, `SessionLog.path_for`.
- Produces: `replay(laps_dir: Path, track: str, day: str, car: str | None = None, log: Path | None = None) -> list[dict]`, righe `{"t", "kind", "lap_ms", "fuel", "front", "rear", "stint", "settling", "ok", "decision", "message"}`; comando `accoach replay-engineer <pista> <AAAAMMGG> [auto]` che stampa una riga per giro come lo script del 16/11.
- Con il registro della serata, gli eventi `"setup"`, `"applied"` e `"base"` entrano nel motore all'ora giusta (`setup_seen`, `mark_applied`, `base_confirmed`). Senza registro vale la regola dello script: una proposta `BOX` è applicata quando il giro dopo apre uno stint (benzina +1 L o salto di 0,4 psi).

- [ ] **Step 1: Write the failing tests:** `test_replay_reaches_the_verdict_on_a_synthetic_evening` (giri sintetici salvati in `tmp_path` con `save_lap`: stint a 28,0 psi davanti, sosta, stint a 27,2 → una riga `propose` e poi una `accepted`); `test_replay_uses_the_session_log_when_there_is_one` (registro con un `"setup"` R2 sbagliato → riga `stand_down`); `test_the_command_is_in_the_help`.
- [ ] **Step 2: Run** `python -m pytest tests/test_rigioco.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** `replay.py` e il comando.
- [ ] **Step 4: Run** lo stesso comando, poi a mano `USERPROFILE=<tmp> PYTHONPATH=src python -m accoach replay-engineer imola 20261108` puntato all'archivio vero in sola lettura (variabile o argomento per la cartella dei giri) — Expected: PASS, e una riga `accepted` al giro delle 21:37.
- [ ] **Step 5: Commit** `git commit -m "Comando replay-engineer: rigioca una serata nell'Ingegnere"`

### Task 8: La verifica dal vivo in garage

**Files:**
- Modify: `src/accoach/diagnostics.py`, `src/accoach/__main__.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `Reading.from_snapshot`, `file_values`, `compare`, `store.find_setup_files`.
- Produces: `setup_lines(snap: TelemetrySnapshot, files: list[FileValues]) -> list[str]` (pura) e `run_setup(seconds: float | None = None) -> None` col ciclo `_sample_loop` come `run_box`; comando `accoach verify-setup` nell'elenco «Validation».
- Le righe: flag box e velocità; TC, ABS, mappa, ripartitore, le quattro pressioni, benzina, aria e pista; per ogni file il nome, le differenze certe (ripartitore come frazione letta accanto ai click del file) e le differenze di pressione in psi. Una stampa quando qualcosa cambia.

- [ ] **Step 1: Write the failing test** `test_setup_lines_show_each_file_against_the_car` (snapshot fermo ai box con TC 3, pressioni di HONE_8; due file → righe che contengono `HONE_8`, `HONE_7` e `0,0` / `+0,8` psi sulle anteriori o equivalente in punto).
- [ ] **Step 2: Run** `python -m pytest tests/test_diagnostics.py -q -k setup_lines` — Expected: FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** lo stesso comando — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "verify-setup: in garage i valori letti accanto a ogni file"`

### Task 9: Il piano di prova sul tablet

**Files:**
- Modify: `HONE_Test_Plan_AC_ACC.xlsx` (foglio nuovo «Ingegnere»), `tools/gen_test_plan.py` (`CATEGORIES`, `CAT_ID["Ingegnere"] = "ING"`), `src/accoach/web/test_plan.json` (rigenerato)
- Test: `tests/test_plan.py`

Il foglio ha la riga d'intestazione `#`, `Cosa`, `Come`, `Cosa deve succedere` e questi passi, in quest'ordine (testo esatto da scrivere in italiano semplice, come gli altri fogli):
1. In garage, prima di uscire: `accoach verify-setup` per 30 s da fermo, poi carica un altro file e guarda le righe cambiare (verifica pressioni a freddo e valori in garage).
2. Esci con l'assetto predefinito del gioco: la pagina dice «Assetto non salvato».
3. Salva quell'assetto in garage e caricalo: «In macchina: …», senza giro d'uscita.
4. Tre giri puliti: proposta delle pressioni, con la frase sulla regola dei giri.
5. Scrivi la modifica, caricala ed esci: riconosciuto il file scritto; dopo il primo giro di riscaldamento il conto parte da 3.
6. Rientra a metà prova: il conto riparte e lo dice.
7. Finisci la prova: verdetto con la pressione raggiunta.
8. Scrivi una modifica e carica apposta il file vecchio: all'uscita la prova si mette in pausa e ti chiama ai box.
9. Gira il TC ai box senza proposta ed esci: «Hai cambiato assetto… Rifaccio la base.»
10. A fine sessione: niente da fare in pista, il registro `ingegnere-AAAAMMGG.jsonl` è nella cartella dei log (`accoach logs`).

- [ ] **Step 1: Write the failing test** in `tests/test_plan.py`: la categoria `ING` esiste in `test_plan.json` con 10 test e ogni test ha `how` ed `expected` non vuoti.
- [ ] **Step 2: Run** `python -m pytest tests/test_plan.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement**: foglio con openpyxl, generatore, `python tools/gen_test_plan.py`.
- [ ] **Step 4: Run** lo stesso comando — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Piano di prova: i passi della tappa 1 e 2 per il test finale"`

### Task 10: Chiusura

- [ ] **Step 1:** suite completa con la casa finta — Expected: tutto verde.
- [ ] **Step 2:** `replay-engineer` su Imola 08/11 e 14/11 in sola lettura; confrontare con il rigioco del 16/11 (stessi verdetti; in più nessuna regola dei box, perché le serate non hanno registro).
- [ ] **Step 3:** aggiornare la mappa decisionale (artefatto `https://claude.ai/artifact/7GprcPbwG7Gb7jKQ2kmd7A`, file nello scratchpad) con R1, R2, R3 e la riga «in macchina».
- [ ] **Step 4:** fondere nel main locale (avanti veloce dal worktree `potenziamento-ingegnere-di-pista`, che ha `main`), senza push e senza installare.
- [ ] **Step 5:** memoria del progetto aggiornata.
