# Pagella e piano — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una nuova prima pagina del report (la Pagella) che dice in dieci secondi com'è andata, i difetti principali con il loro andamento fra sessioni, dove si sbaglia, gli errori frequenti e una roadmap di consigli da seguire uno alla volta, ognuno con la sua vista «Come si fa».

**Architecture:** Un modulo puro misura i difetti da un `LapDebrief` (`coaching/defects.py`) e conta gli errori da un `Lap` (`coaching/errors.py`); un modulo backend (`pagella.py`) elegge il riferimento dello storico, rigioca le sessioni e costruisce i payload; un modulo puro gestisce la roadmap dei consigli (`coaching/advice.py`) persistita in una tabella nuova di `catalog.db`; i testi «come si fa» stanno in `coaching/howto.py`. `api.py` espone tre endpoint sottili. Il focus del coach dal vivo riceve le curve del consiglio in corso. Il frontend aggiunge le viste `pagella` e `howto` e riordina le schede in tre gruppi.

**Tech Stack:** Python 3 (FastAPI, dataclass, sqlite3), JavaScript vanilla, pytest.

**Spec:** `docs/superpowers/specs/2026-10-21-pagella-e-piano-design.md`

## Global Constraints

- Tutto offline; nessuna risorsa esterna.
- Mai scrivere in `%USERPROFILE%\Documents\ACCoach`: le prove sull'archivio si fanno su una copia nello scratchpad.
- Ogni testo esiste in italiano e inglese.
- Tono (deciso col pilota): frasi brevi col tu; numeri con la virgola in italiano e l'unità («0,18 s»); niente slogan, niente due punti a effetto, niente emoji; mai la stessa frase in due posti; prima il fatto, poi cosa fare.
- Al massimo 4 difetti e 3 consigli in Pagella; si segue un consiglio alla volta.
- Soglie esistenti, non nuove: `SIGNIF_LOSS_MS = 120.0`, `RECUR_FRAC = 0.5` (`coaching/thresholds.py`).
- Ogni test nuovo deve fallire se si toglie la cosa che prova: per ogni task, una mutazione verificata a mano (togli la riga, il test diventa rosso, rimetti).
- Commit in italiano, con `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

- Una sessione senza giri validi, o con un solo giro, o un'auto/pista con un solo giro in archivio (che è anche il riferimento): la Pagella risponde con una frase, mai un 500 né numeri a zero spacciati per misure.
- Una sessione sul bagnato con lo storico sull'asciutto (e viceversa): fuori dall'andamento, e la Pagella lo dice.
- Giri vecchi senza coordinate o senza canali (schema vecchio): la vista «Come si fa» nasconde la figura con una frase, il resto si vede.
- Un consiglio in corso le cui curve non cadono in nessuna curva del riferimento del motore: il focus torna a scegliere da solo, senza eccezioni.
- Un piano vecchio (tabella `plan`) già accettato dal pilota: non si perde, diventa il consiglio in corso.

---

### Task 1: I difetti di un giro e di una sessione

**Files:**
- Create: `src/accoach/coaching/defects.py`
- Test: `tests/test_defects.py`

**Interfaces:**
- Consumes: `LapDebrief`, `CornerLoss` (`coaching/debrief.py`), `CueCategory`, `SIGNIF_LOSS_MS`, `RECUR_FRAC`.
- Produces:
  - `DEFECTS: tuple[str, ...] = ("brake_early", "brake_late", "over_brake", "throttle_late", "min_speed", "lift", "coasting")`
  - `CATEGORY_OF: dict[str, CueCategory]` = brake_early→BRAKE_LATER, brake_late→BRAKE_EARLIER, over_brake→LESS_BRAKE, throttle_late→MORE_THROTTLE, min_speed→CARRY_SPEED (lift e coasting non hanno categoria).
  - `@dataclass LapDefects: ms: dict[str, float]; corners: dict[str, dict[int, float]]; coast_s: float; total_gap_ms: int; corner_loss: dict[int, float]` — `corner_loss` è la perdita totale per curva (tutte le categorie, `TIME_LOSS` compreso) per «dove sbagli di più».
  - `lap_defects(d: LapDebrief) -> LapDefects`
  - `@dataclass DefectSummary: key: str; mean: float; unit: str ("ms"|"s"); laps_with: int; laps: int; corners: list[tuple[int, float]]; main: bool`
  - `summarize(laps: list[LapDefects]) -> list[DefectSummary]`
  - `worst_corners(laps: list[LapDefects], n: int = 3) -> list[tuple[int, float]]`
  - `COAST_MAIN_S: float` (misurata, vedi Step 5)

- [ ] **Step 1: Scrivi i test che falliscono** in `tests/test_defects.py`, con i costruttori `CornerLoss`/`LapDebrief` come in `tests/test_plan.py` (`_loss(index, lost_ms, category)`, `_debrief(*losses, notes=())`):

```python
def test_a_lap_sums_each_defect_over_its_corners():
    d = _debrief(_loss(0, 200, BRAKE_LATER), _loss(3, 150, BRAKE_LATER),
                 _loss(5, 300, CARRY_SPEED), _loss(6, 90, TIME_LOSS))
    ld = lap_defects(d)
    assert ld.ms["brake_early"] == 350 and ld.ms["min_speed"] == 300
    assert ld.corners["brake_early"] == {0: 200, 3: 150}
    assert "time_loss" not in ld.ms              # non è un difetto
    assert ld.corner_loss[6] == 90               # ma conta per «dove sbagli»

def test_lift_comes_from_the_lap_notes_and_coasting_from_the_grip():
    d = _debrief(_loss(0, 200, BRAKE_LATER, coast_s=0.4),
                 notes=[LapNote(kind="lift", message="", lost_ms=80)])
    ld = lap_defects(d)
    assert ld.ms["lift"] == 80 and ld.coast_s == pytest.approx(0.4)

def test_the_session_number_is_the_mean_over_valid_laps_counting_zeros():
    laps = [lap_defects(_debrief(_loss(0, 300, BRAKE_LATER))),
            lap_defects(_debrief())]
    s = {x.key: x for x in summarize(laps)}["brake_early"]
    assert s.mean == 150 and s.laps_with == 1 and s.laps == 2

def test_main_means_over_the_threshold_in_at_least_half_the_laps():
    hit = lap_defects(_debrief(_loss(0, 130, BRAKE_LATER)))
    miss = lap_defects(_debrief(_loss(0, 110, BRAKE_LATER)))
    assert {x.key: x for x in summarize([hit, miss])}["brake_early"].main
    assert not {x.key: x for x in summarize([hit, miss, miss])}["brake_early"].main

def test_ms_defects_by_mean_then_coasting_last_and_never_more_than_four():
    ...  # sei difetti ms principali + coasting principale:
    # assert [x.unit for x in out][-1] == "s"; len([x for x in out if x.main]) <= 4
    # e i ms sono in ordine di mean decrescente

def test_worst_corners_ranks_total_loss_per_lap():
    laps = [lap_defects(_debrief(_loss(2, 400, CARRY_SPEED), _loss(7, 100, TIME_LOSS)))]
    assert worst_corners(laps) == [(2, 400.0), (7, 100.0)]
```

Il test sui quattro: costruisci le liste con un ciclo, non a mano. `_loss` accetta `coast_s` e lo mette in `GripState(coast_s=...)`.

- [ ] **Step 2: Lancia i test e verifica che falliscono**

Run: `python -m pytest tests/test_defects.py -q`
Expected: FAIL con `ModuleNotFoundError: accoach.coaching.defects`

- [ ] **Step 3: Implementa `coaching/defects.py`** con le firme sopra. `summarize` restituisce **tutti** i difetti con `mean > 0`, ordinati: prima quelli in ms per `mean` decrescente, poi `coasting`. `main` è vero se il valore per giro supera la soglia (ms: `SIGNIF_LOSS_MS`; coasting: `COAST_MAIN_S`) in almeno `ceil(RECUR_FRAC * n)` giri, e solo i primi 4 difetti principali in quest'ordine restano `main=True`. Per difetto, `corners` = curve con il valore medio per giro (zeri compresi), decrescente.

- [ ] **Step 4: Lancia i test**

Run: `python -m pytest tests/test_defects.py -q`
Expected: PASS

- [ ] **Step 5: Misura `COAST_MAIN_S` sull'archivio** (copia, sola lettura). Script nello scratchpad: copia `Documents\ACCoach\laps\*.lap.json.gz` in una cartella dello scratchpad, per ogni auto/pista elegge il giro più veloce pulito, costruisce `build_lap_debrief` di ogni altro giro valido contro di lui e calcola `lap_defects(d).coast_s`. `COAST_MAIN_S` = il 75° percentile di quei valori, arrotondato a 0,1 s. Scrivi il valore nella costante con un commento che dice quanti giri, quali combo e la data della misura.

- [ ] **Step 6: Commit**

```bash
git add src/accoach/coaching/defects.py tests/test_defects.py
git commit -m "I difetti di guida si contano per giro e per sessione"
```

---

### Task 2: Gli errori frequenti di una sessione

**Files:**
- Create: `src/accoach/coaching/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: `diagnosis._lock_spin_segments(samples, spin_ratio)`, `diagnosis.corner_symptoms(samples, corner, tuning)` (chiavi `Symptom` con `.balance`), `tuning_for_car(car_model)`, `Lap.clean`, `Lap.lost_at`.
- Produces:
  - `ERRORS: tuple[str, ...] = ("lock", "spin", "understeer", "oversteer", "off")`
  - `lap_errors(lap: Lap, corners: list[Corner]) -> dict[str, int]` — lock/spin = segmenti; understeer/oversteer = curve del giro in cui compare almeno un sintomo con quel bilanciamento; off = 1 se `lap.clean is False`.
  - `session_errors(per_lap: list[dict[str, int]]) -> list[tuple[str, int]]` — somme, solo quelle > 0, decrescenti.

- [ ] **Step 1: Test che falliscono** con `synth` (giri sintetici): un giro con un bloccaggio chiaro conta `lock == 1`; lo stesso giro senza conta 0; un giro `clean=False` conta `off == 1`; `session_errors([{"lock":2,"off":0},{"lock":1,"off":1}]) == [("lock",3),("off",1)]`. Usa lo stesso profilo di bloccaggio dei test esistenti di `diagnosis` (cerca `lock_segments` in `tests/`).
- [ ] **Step 2: Lancia** `python -m pytest tests/test_errors.py -q` → FAIL (modulo mancante).
- [ ] **Step 3: Implementa** `coaching/errors.py`. Non riscrivere la regola del bloccaggio: chiama `_lock_spin_segments` (stessa regola del rilevatore dal vivo; con l'ABS acceso su ACC il bloccaggio non avviene e il conto resta 0, non va forzato).
- [ ] **Step 4: Lancia** → PASS.
- [ ] **Step 5: Commit** `"Bloccaggi, pattinamenti, sotto/sovrasterzo e uscite si contano per sessione"`.

---

### Task 3: Lo storico — riferimento unico e sessioni rigiocate

**Files:**
- Create: `src/accoach/pagella.py`
- Test: `tests/test_pagella_storico.py`

**Interfaces:**
- Consumes: Task 1 e 2; `group_sessions`, `Session` (`sessions.py`); `load_lap`, `Reference`, `detect_corners`, `build_lap_debrief`; `diagnosis._is_wet`-equivalente sulle righe del catalogo.
- Produces:
  - `is_wet_row(row: dict) -> bool | None` — stessa regola di `diagnosis._is_wet` sul campo `tyre_compound` della riga.
  - `history_reference(rows: list[dict], wet: bool) -> dict | None` — la riga più veloce con `valid` e `clean != 0`, `lap_time_ms > 0` e `is_wet_row(row)` uguale a `wet` (righe con compound mancante contano come asciutto).
  - `@dataclass SessionReplay: session: Session; wet: bool; laps: list[LapDefects]; errors: list[dict[str,int]]; mean_gap_ms: float | None`
  - `replay(session: Session, reference_row: dict, corners, ref: Reference, cache: dict) -> SessionReplay` — solo `session.valid_laps`, escluso il riferimento stesso; `mean_gap_ms` = media di `lap_time_ms - reference.lap_time_ms`.
  - `_CACHE: dict[tuple[str, str], tuple[LapDefects, dict]]` modulo-livello, chiave `(reference_path, lap_path)`.

- [ ] **Step 1: Test che falliscono**, con giri salvati in `tmp_path` come fa `tests/test_plan.py` (`save_lap` + catalogo): due sessioni a 30 minuti di distanza; `history_reference` sceglie il giro più veloce pulito, non uno più veloce con `clean=False`; con un giro bagnato più veloce e `wet=False` sceglie l'asciutto; `replay` di una sessione con 3 giri validi ha `len(laps) == 3` meno il riferimento se ci sta dentro; una seconda chiamata a `replay` non chiama `build_lap_debrief` (monkeypatch che conta).
- [ ] **Step 2: Lancia** `python -m pytest tests/test_pagella_storico.py -q` → FAIL.
- [ ] **Step 3: Implementa** `pagella.py` (solo queste funzioni). File illeggibili: il giro si salta, mai un'eccezione verso l'alto (`OSError`, `ValueError`), come `_history` in `api.py`.
- [ ] **Step 4: Lancia** → PASS.
- [ ] **Step 5: Commit** `"Lo storico dei difetti si misura contro un riferimento solo"`.

---

### Task 4: La roadmap dei consigli e la sua tabella

**Files:**
- Create: `src/accoach/coaching/advice.py`
- Modify: `src/accoach/recording/catalog.py` (schema: nuova tabella; metodi nuovi accanto a `load_plan`)
- Test: `tests/test_advice.py`

**Interfaces:**
- Consumes: `DefectSummary`, `LapDefects` (Task 1); `SIGNIF_LOSS_MS`, `RECUR_FRAC`; `catalog.load_plan/clear_plan` (per la migrazione).
- Produces:
  - `MAX_ADVICE = 3`, `MAX_CORNERS = 3`
  - `@dataclass AdviceCorner: index: int; name: str; apex_pos: float; mean: float`
  - `@dataclass Advice: defect: str; corners: list[AdviceCorner]; baseline: float; target: float; status: str; accepted_utc: str = ""; closed_utc: str = ""` — `status` ∈ `"proposed" | "active" | "reached" | "dropped" | "declined"`.
  - `propose_advice(summaries: list[DefectSummary], stored: list[Advice], names: dict[int,str], apex: dict[int,float]) -> list[Advice]` — dai difetti `main`, nell'ordine di `summarize`, saltando quelli `declined` o `reached`; mette per primo l'eventuale `active`; al massimo `MAX_ADVICE`; curve = le prime `MAX_CORNERS` di `summary.corners` con media ≥ `SIGNIF_LOSS_MS / 2` (per coasting: ≥ `COAST_MAIN_S / 2`); `baseline` = somma delle medie su quelle curve; `target = max(SIGNIF_LOSS_MS, baseline * 0.5)` (coasting: `max(COAST_MAIN_S, baseline*0.5)`).
  - `@dataclass AdviceProgress: laps: int; hits: int; needed: int; median: float; done: bool`
  - `measure_advice(a: Advice, laps_since: list[LapDefects]) -> AdviceProgress` — per giro, la somma del difetto sulle curve del consiglio; `hits` = giri ≤ `target`; `needed = max(2, ceil(RECUR_FRAC*n))`; `done = n >= 3 and hits >= needed`.
  - `rebase(a: Advice, summary: DefectSummary) -> Advice` — ricalcola `baseline`/`target` sulle stesse curve con lo storico attuale (cambio di riferimento).
  - Catalogo: tabella `advice(car_key, track_key, defect, status, accepted_utc, closed_utc, data_json, PRIMARY KEY(car_key, track_key, defect))`; `load_advice(car, track) -> list[dict]`, `save_advice(car, track, advice: dict) -> None`, `migrate_plan_to_advice(car, track) -> None` (un piano vecchio accettato diventa il consiglio `active` del difetto della categoria del primo obiettivo, con quella curva; poi `clear_plan`).

- [ ] **Step 1: Test che falliscono:**

```python
def test_only_main_defects_become_advice_and_at_most_three():
def test_a_declined_defect_is_not_proposed_again():
def test_the_active_one_comes_first_and_only_one_can_be_active():
    # due Advice "active" passati a propose_advice -> ValueError
def test_target_is_half_the_baseline_never_under_the_threshold():
    # baseline 180 -> target 120.0 ; baseline 400 -> target 200.0
def test_reached_needs_three_laps_and_half_of_them_under_target():
    # 2 giri sotto -> not done ; 3 giri, 2 sotto -> done ; 4 giri, 1 sotto -> not done
def test_advice_round_trips_through_the_catalog(tmp_path):
def test_an_old_accepted_plan_becomes_the_active_advice(tmp_path):
    # save_plan con un Goal category="brake_later" corner 4 -> migrate ->
    # load_advice == [{"defect": "brake_early", "status": "active", ...corner 4...}]
    # e load_plan(...) is None
```

- [ ] **Step 2: Lancia** `python -m pytest tests/test_advice.py -q` → FAIL.
- [ ] **Step 3: Implementa** `advice.py` e i metodi del catalogo. La tabella va nello stesso blocco `CREATE TABLE IF NOT EXISTS` di `plan` e sopravvive al rebuild della tabella `lap` come le altre.
- [ ] **Step 4: Lancia** → PASS; poi `python -m pytest tests/test_plan.py tests/test_catalog*.py -q` → PASS.
- [ ] **Step 5: Commit** `"I consigli sono una roadmap, uno alla volta, e si ricordano"`.

---

### Task 5: I testi della Pagella e del «Come si fa»

**Files:**
- Create: `src/accoach/coaching/howto.py`
- Test: `tests/test_howto_tono.py`

**Interfaces:**
- Produces:
  - `defect_name(key: str, lang: str) -> str` — il nome-abitudine («Freni troppo presto», «Gas tardi in uscita», «Poca velocità in curva», «Troppo freno», «Freni troppo tardi», «Alzi il gas sul dritto», «Veleggi prima di frenare»).
  - `error_name(key: str, lang: str) -> str`
  - `@dataclass HowTo: what: str; watch: str; ignore: str; drill: str; laps: int; done_when: str`
  - `howto(key: str, lang: str) -> HowTo` — uno per ognuno dei 7 `DEFECTS`.
  - `verdict(mean_gap_s: float, top: DefectSummary | None, share: float, prev: dict | None, lang: str) -> str` — una o due frasi; `prev` = `{"gap_delta_s": float, "better": [key], "worse": [key]}` o `None` («È la tua prima sessione qui: il confronto arriva dalla prossima.»).
  - `problem(key: str, corner_name: str, value: float, unit: str, lang: str, metres: float | None = None) -> str`
  - `fmt_s(v: float, lang: str) -> str` — `"0,18 s"` in it, `"0.18 s"` in en.

- [ ] **Step 1: Test di tono che falliscono:**

```python
@pytest.mark.parametrize("lang", ["it", "en"])
def test_every_defect_has_its_own_howto_and_no_sentence_repeats(lang):
    sentences = [s for k in DEFECTS for s in _sentences(howto(k, lang))]
    assert len(sentences) == len(set(sentences))

def test_no_emoji_and_no_slogan_colons():
    for text in _all_texts():           # howto, verdict su 4 casi, problem su 7
        assert not re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text)
        assert not re.search(r"^[^:]{1,30}:\s", text)   # «Una cosa alla volta: …»

def test_italian_numbers_use_the_comma():
    assert fmt_s(0.18, "it") == "0,18 s" and fmt_s(0.18, "en") == "0.18 s"
    assert "0,29 s" in problem("brake_early", "Variante Alta", 290, "ms", "it", metres=14)
```

- [ ] **Step 2: Lancia** `python -m pytest tests/test_howto_tono.py -q` → FAIL.
- [ ] **Step 3: Scrivi `howto.py`.** I testi partono dagli esercizi di `coaching/training.py` (`_T`) e da `COACHING-PRO.md`, riscritti nel tono della spec; per `lift`, `coasting`, `brake_late` gli esercizi oggi non esistono e vanno scritti. Modello di tono approvato dal pilota (spec, sezione «Il tono dei testi»). La regola «una cosa alla volta» **non** sta qui: sta una volta sola sopra il piano (Task 7).
- [ ] **Step 4: Lancia** → PASS.
- [ ] **Step 5: Commit** `"I testi della Pagella, nel tono deciso col pilota"`.

---

### Task 6: Gli endpoint

**Files:**
- Modify: `src/accoach/pagella.py` (aggiunge i builder dei payload)
- Modify: `src/accoach/api.py` (tre route sottili accanto a `/api/plan`)
- Test: `tests/test_api_pagella.py`

**Interfaces:**
- Consumes: Task 1-5; `name_corners`, `cornernames.for_track`, `learn_from` come in `_history`.
- Produces:
  - `build_pagella(cat, car: str, track: str, index: int, lang: str) -> dict` con chiavi: `session` (`started_utc`, `laps`, `valid`, `wet`), `excluded` (`None` | `"wet"` | `"dry"` | `"no_reference"` | `"no_laps"`), `verdict` (str), `defects` (lista: `key`, `name`, `value`, `unit`, `laps_with`, `laps`, `corners` [{`name`, `value`}], `series` [valori delle ultime ≤6 sessioni stessa classe, la più vecchia prima], `trend` `"down"|"same"|"up"|None`), `worst_corners` [{`name`, `value_s`}], `errors` [{`key`, `name`, `count`}], `advice` [{`defect`, `name`, `status`, `corners` [names], `target`, `unit`, `progress`}], `reference` {`lap_time`, `recorded_utc`}.
  - `trend`: `"down"` se il valore di questa sessione è sotto quello della precedente di almeno il 10% **e** di almeno 20 ms (coasting: 0,1 s); `"up"` simmetrico; altrimenti `"same"`; `None` senza sessione precedente.
  - `build_howto(cat, car: str, track: str, defect: str, index: int, lang: str) -> dict` con: `name`, `problem`, `howto` (campi di `HowTo`), `figures` [{`corner`, `name`, `entry_pos`, `exit_pos`, `typical_path`, `best_path`, `brake_points_m`: {`typical`, `best`} | None}], `progress` [valori per sessione dal `accepted_utc`], `reference_lap` (tempo e data: la vista dice contro quale giro misura).
  - `GET /api/pagella?car&track&index=0&lang`, `GET /api/howto?car&track&defect&index=0&lang`, `POST /api/advice` body `{car, track, defect, action}` con `action` ∈ `follow | drop | reached | decline | undecline`; `follow` con un altro consiglio `active` → 409.

- [ ] **Step 1: Test che falliscono** con `TestClient(create_api(tmp_path))` e giri sintetici salvati come in `tests/test_plan.py`:
  - una auto/pista con due sessioni: `/api/pagella` ha `verdict` non vuoto, `defects` ordinati, `series` lunga 2, `advice[0].status == "proposed"`;
  - un solo giro in archivio → 200 con `excluded == "no_reference"` e `defects == []`;
  - sessione bagnata, storico asciutto → `excluded == "wet"`;
  - `POST follow` poi un secondo `follow` su un altro difetto → 409; `drop` poi `follow` del secondo → 200;
  - `decline` → il difetto resta in `defects` e sparisce da `advice`;
  - `/api/howto` di un difetto: `problem` contiene il nome della curva, `figures[0].typical_path` e `best_path` sono percorsi di giri esistenti, `progress` vuoto prima di `follow`.
- [ ] **Step 2: Lancia** `python -m pytest tests/test_api_pagella.py -q` → FAIL.
- [ ] **Step 3: Implementa** i builder in `pagella.py` e le route in `api.py` (solo parsing dei parametri, `with _catalog() as cat:` e chiamata al builder). `build_pagella` chiama `migrate_plan_to_advice` prima di leggere i consigli e `rebase` sui consigli `active` quando il riferimento dello storico è cambiato dall'accettazione (salva il percorso del riferimento in `data_json`). Quando `measure_advice` del consiglio `active` dà `done`, `build_pagella` lo salva come `reached` (con `closed_utc`) e il verdetto lo dice; il successivo diventa il primo `proposed`. Difetti e consigli si costruiscono sulle sessioni fino a quella mostrata compresa (`index`), mai su quelle dopo. Test: un consiglio `active` con 3 giri dopo l'accettazione, 2 sotto obiettivo → la risposta lo ha `reached` e il secondo difetto è `proposed`. `brake_points_m` usa la stessa misura del foglio frenate (`braking_points.py`), non una nuova.
- [ ] **Step 4: Lancia** → PASS; poi `python -m pytest -q` intera → PASS.
- [ ] **Step 5: Misura il tempo** su una copia dell'archivio (Task 1, Step 5): `build_pagella` sulla combo con più giri. Expected: sotto 2 s a freddo, sotto 0,3 s alla seconda chiamata (cache). Se no, il collo di bottiglia si misura prima di toccarlo.
- [ ] **Step 6: Commit** `"La Pagella e il Come si fa hanno i loro endpoint"`.

---

### Task 7: La Pagella nel report e le schede in tre gruppi

**Files:**
- Modify: `src/accoach/web/index.html` (nav `.tabs`, nuovo `#view-pagella`, rimozione di `#view-recap` e `#view-training` e delle loro schede)
- Modify: `src/accoach/web/app.js` (`showView`, `redrawCurrentView`, `init`, `savedView`, nuovo `loadPagella`/`renderPagella`, rimozione di render/load di recap e training)
- Modify: `src/accoach/web/style.css`, `src/accoach/web/i18n.js`, `src/accoach/web/tour.js` (i passi che puntavano a recap/training)
- Test: `tests/test_web_pagella.py` più gli esistenti `tests/test_web_views.py`, `tests/test_web_i18n_keys.py`

**Interfaces:**
- Consumes: `GET /api/pagella`, `POST /api/advice`.
- Produces: vista `pagella` (prima scheda, `active` in HTML); gruppi nella nav come `<div class="tab-group" data-i18n-label="tabgroup.today|why|time">` con le schede in quest'ordine: pagella · session · flow | compare · line · sectors · dynamics | progress · stint. `openHowto(defect)` (usata dal Task 8).

- [ ] **Step 1: Test che falliscono** (statici sul markup, come `tests/test_web_views.py`): l'ordine dei `data-view` nella nav è esattamente quello sopra; `pagella` è `active`; `view-recap` e `view-training` non esistono; in `app.js` una funzione apre la Pagella quando la sessione più recente ha `started_utc` diverso da `localStorage["hone_seen_session"]` (asserisci che `hone_seen_session` compare e che `showView("pagella")` è nel suo ramo).
- [ ] **Step 2: Lancia** `python -m pytest tests/test_web_pagella.py -q` → FAIL.
- [ ] **Step 3: Implementa.** La Pagella segue `SESSION_I` (selettore esistente). Struttura e contenuti: spec, sezione «La Pagella». Layout: colonna centrale `max-width: 860px`, testo base 16 px; verdetto, difetti e piano visibili senza scorrere a 1920×1080. Mini-andamento: barre come nella bozza approvata, in CSS, una per sessione di `series`. Piano: la frase «Lavora su un consiglio alla volta, nell'ordine.» una volta sopra la lista; sul consiglio `active` «Lascio stare» e «Come si fa →»; sul primo `proposed` quando nessuno è `active` «Lo seguo» e «Non lo seguo»; sugli altri solo posizione e «Come si fa →». `excluded` → una frase al posto dei blocchi.
- [ ] **Step 4: Lancia** → PASS; `python -m pytest -q` → PASS.
- [ ] **Step 5: Prova nel browser** (`web` servito su una porta libera con casa finta, archivio copiato): a 1920×1080 e 1280×800 la Pagella si legge senza scorrere fino al piano; «Lo seguo» → il consiglio diventa in corso e gli altri bottoni spariscono; cambio lingua → testi in inglese, nessuna chiave grezza; nessun errore in console. Screenshot nella PR.
- [ ] **Step 6: Commit** `"Il report si apre sulla Pagella e le schede seguono il filo oggi, perché, nel tempo"`.

---

### Task 8: La vista «Come si fa»

**Files:**
- Modify: `src/accoach/web/index.html` (`#view-howto`, fuori dalla nav), `src/accoach/web/app.js` (`openHowto`, `renderHowto`), `src/accoach/web/style.css`, `src/accoach/web/i18n.js`
- Test: `tests/test_web_pagella.py` (aggiunte)

**Interfaces:**
- Consumes: `GET /api/howto`; per le figure, le funzioni di disegno esistenti del Confronto (mappa e traccia del freno: `drawMapTo`, `line`) ristrette a `entry_pos..exit_pos` della curva, con i giri `typical_path` e `best_path` caricati da `/api/analysis`.
- Produces: vista con, nell'ordine, problema, figure (una per curva), «come si fa», esercizio, andamento da quando lo segui, «← Torna alla Pagella».

- [ ] **Step 1: Test statici che falliscono:** `view-howto` esiste, non ha una scheda nella nav, e `openHowto` chiama `/api/howto`; un link «Come si fa →» della Pagella chiama `openHowto`.
- [ ] **Step 2: Lancia** → FAIL.
- [ ] **Step 3: Implementa.** Giro senza coordinate o senza il canale: la figura lascia il posto a una frase (come `rail-nomap`). La vista dice contro quale giro misura (`reference_lap`).
- [ ] **Step 4: Lancia** → PASS; suite intera → PASS.
- [ ] **Step 5: Prova nel browser** su ognuno dei difetti presenti nell'archivio copiato: figura giusta per curva, numeri del problema uguali a quelli della Pagella. Screenshot nella PR.
- [ ] **Step 6: Commit** `"Ogni consiglio ha la sua vista Come si fa, dai tuoi giri"`.

---

### Task 9: Il consiglio in corso guida il focus in pista

**Files:**
- Modify: `src/accoach/coaching/focus.py` (`FocusCoach.__init__`, `_choose`)
- Modify: `src/accoach/engine.py` (dove si crea il `FocusCoach` con `mastered`/`parked`, ~riga 1040)
- Test: `tests/test_focus_segue_il_consiglio.py`

**Interfaces:**
- Consumes: `catalog.load_advice` (Task 4), `AdviceCorner.apex_pos`.
- Produces: `FocusCoach(..., preferred: list[int] | None = None)`; in `_choose`, se `preferred` non è vuoto, si sceglie la prima curva di `preferred`, nell'ordine, che non è `mastered`/`parked` e passa la stessa ricorrenza e soglia di oggi; se nessuna passa, la scelta di sempre. Il motore traduce le curve del consiglio `active` nelle sue: una curva del consiglio corrisponde alla curva del motore con `entry_pos <= apex_pos <= exit_pos`; quelle senza corrispondenza si scartano.

- [ ] **Step 1: Test che falliscono:**

```python
def test_the_followed_advice_wins_over_a_worse_corner():
    # finestra dove la curva 5 perde 300 ms e la 2 perde 180 ms, entrambe ricorrenti;
    # FocusCoach(preferred=[2]) -> focus.corner_index == 2 ; senza preferred -> 5
def test_an_advice_corner_that_is_fine_falls_back_to_the_usual_choice():
    # preferred=[2] ma la 2 non perde -> focus sulla 5
def test_the_engine_maps_advice_corners_by_apex_position(tmp_path):
    # advice active con apex_pos dentro la curva 3 del riferimento del motore
    # e un apex_pos fuori da ogni curva -> preferred == [3]
```

- [ ] **Step 2: Lancia** `python -m pytest tests/test_focus_segue_il_consiglio.py -q` → FAIL.
- [ ] **Step 3: Implementa.** Il verdetto del focus non tocca il consiglio (lo chiude solo il report). Catalogo illeggibile → `preferred=None`, come `_load_focus_state`.
- [ ] **Step 4: Lancia** → PASS; poi `python -m pytest tests/test_focus*.py tests/test_engine*.py -q` → PASS.
- [ ] **Step 5: Prova coi giri veri rigiocati nel motore** (approccio della memoria del 13/10: feed finto, casa finta con la copia dell'archivio, `app.make_step`): con un consiglio `active` su una curva, il log `focus | <nome curva>` nomina quella curva.
- [ ] **Step 6: Commit** `"In pista il coach lavora sul consiglio che hai scelto"`.

---

### Task 10: Chiusura

**Files:**
- Modify: `GUIDA.md` (§5 report: la Pagella, il piano, «Come si fa»), `docs/FAQ.md` (EN, stessa sezione)
- Test: suite intera

- [ ] **Step 1:** Aggiorna la guida nel tono nuovo (le due lingue).
- [ ] **Step 2:** `python -m pytest -q` → tutti PASS.
- [ ] **Step 3:** Rilettura dell'intero ramo da parte di un revisore nuovo (sola lettura), con la spec in mano.
- [ ] **Step 4:** PR verso `main` con screenshot della Pagella e di un «Come si fa» su dati della copia dell'archivio, e la lista di cosa resta da provare in pista (il focus che segue il consiglio).
