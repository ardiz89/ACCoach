# Costanza del pilota — piano di lavoro

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un giro pulito che, rispetto agli altri giri dello stesso stint e con le stesse manopole, è più lento di oltre 5 km/h di velocità minima in almeno 3 curve non entra in nessuna lettura dell'Ingegnere, e il pilota sa quale, dove e perché.

**Architecture:** la diagnosi del giro (`coaching/diagnosis.py`) aggiunge a `LapStats` la velocità minima per curva e le manopole; un modulo puro (`engineer/consistency.py`) dice quali giri di un gruppo sono incostanti; l'Ingegnere (`engineer/core.py`) tiene i giri del gruppo in corso in attesa finché non sono giudicabili, poi li mette nella finestra o li toglie, e lo dice. Registro e rigioco lo mostrano.

**Tech Stack:** Python 3.14, pytest (suite solo con `USERPROFILE` finto).

**Spec:** `docs/superpowers/specs/2026-11-17-costanza-pilota-design.md`

## Global Constraints

- Soglie: `_CONSISTENCY_KMH = 5.0`, `_CONSISTENCY_CORNERS = 3`, `_CORNER_MATCH = 0.01` (frazione di giro, distanza sul cerchio).
- Solo giri **più lenti** (scarto = la sua velocità minima − mediana degli altri < −5 km/h). Mediana degli **altri** giri (almeno 2 con quella curva).
- Gruppo = stesso stint **e** stesse manopole (TC, ABS, mappa, ripartitore letti sul giro); un valore non letto (−1 / −1.0 / None) non spezza il gruppo.
- Il giro che apre lo stint (`settling`) non si giudica e non fa da confronto; entra nella finestra come oggi.
- Acceso solo per le auto GT3 (non GT4, GT2, GTE, Formula, stradali); spento, l'Ingegnere si comporta esattamente come oggi.
- Una decisione legge solo giri giudicati; i contatori contano anche i giri in attesa.
- Con una proposta in attesa (`_pending` non None) non si tolgono giri già nella finestra.
- Un giro tolto non rientra.
- Frasi in italiano e inglese; `tests/test_tono.py` vieta frasi ripetute fra i messaggi.
- Suite: `USERPROFILE=<cartella temporanea> .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`.

## Review Focus

- Pilota che gira una manopola a metà stint: i giri dopo non devono risultare incostanti rispetto a quelli prima (test nel Task 4).
- Stint corto (2 giri dopo quello d'apertura) e poi sosta: i suoi giri spariscono dal conto senza bloccare niente e senza frasi sbagliate (test nel Task 4).
- Contatore durante l'attesa: dopo una sosta «servono ancora N giri» deve scendere 3, 2, 1 e non restare fermo e poi saltare (il difetto del 08/11) (test nel Task 4).
- Proposta ai box in attesa mentre il pilota continua a girare: la proposta non sparisce, e la prova applicata parte con la sua lettura di pressione (test nel Task 4).
- Curva a cavallo del traguardo (apice 0,998 contro 0,002): si accoppia (test nel Task 2).

---

### Task 1: la misura nel giro

**Files:**
- Modify: `src/accoach/engineer/core.py` (dataclass `LapStats`, dopo `stint`)
- Modify: `src/accoach/coaching/diagnosis.py` (`build_lap_stats`)
- Test: `tests/test_diagnosis_costanza.py` (nuovo)

**Interfaces:**
- Produces: `LapStats.corner_vmin: tuple[tuple[float, float, str], ...] = ()` — per curva ricevuta: (apice `Corner.apex_pos`, velocità minima in km/h fra i campioni con `entry_pos <= pos <= exit_pos`, nome da `corner_names.get(index, "")`); curve senza campioni assenti.
- Produces: `LapStats.dials: tuple[int, int, int, float] = (-1, -1, -1, -1.0)` — (`lap.tc_level`, `lap.abs_level`, `lap.engine_map`, `lap.brake_bias`), coi default di `Lap` per i giri vecchi.
- Produces: `LapStats.stint_lap: int = 0` (lo riempie il Task 4).

- [ ] **Step 1: test che falliscono.** Con `synth` o un `Lap` costruito a mano con due curve note:
  - `test_lap_stats_carry_min_speed_per_corner`: `[round(v) for _, v, _ in stats.corner_vmin] == [120, 95]` per le curve di `synth` (minimi 120 e 95 km/h), apici uguali a `Corner.apex_pos`.
  - `test_corner_names_ride_along`: con `corner_names={0: "Tosa"}` il primo nome è `"Tosa"`, il secondo `""`.
  - `test_lap_stats_carry_the_dials`: un `Lap` con `tc_level=3, abs_level=4, engine_map=0, brake_bias=0.64` → `stats.dials == (3, 4, 0, 0.64)`; un `Lap` senza → `(-1, -1, -1, -1.0)`.
- [ ] **Step 2:** `pytest tests/test_diagnosis_costanza.py -q` → FAIL (attributi assenti).
- [ ] **Step 3:** campi in `LapStats` (con commento sul perché: costanza del pilota, 17/11) e riempimento in `build_lap_stats`.
- [ ] **Step 4:** `pytest tests/test_diagnosis_costanza.py tests/test_engineer*.py -q` → PASS.
- [ ] **Step 5:** commit «Diagnosi: velocità minima per curva e manopole nel giro».

### Task 2: chi è incostante (modulo puro)

**Files:**
- Create: `src/accoach/engineer/consistency.py`
- Test: `tests/test_engineer_costanza_pura.py`

**Interfaces:**
- Consumes: `LapStats.corner_vmin`, `LapStats.dials` (Task 1).
- Produces:
  - `KMH = 5.0`, `CORNERS = 3`, `MATCH = 0.01` (le costanti del motore le riprendono da qui).
  - `same_dials(a: tuple, b: tuple) -> bool` — uguali sui valori letti da entrambi (≥ 0); un valore non letto non conta.
  - `slow_corners(lap: LapStats, others: list[LapStats], *, kmh: float = KMH, match: float = MATCH) -> list[tuple[str, float]]` — (nome, scarto) delle curve dove `lap` è più lento di oltre `kmh` della mediana delle stesse curve negli `others` (accoppiate per apice entro `match` sul cerchio; servono almeno 2 altri con la curva), ordinate dallo scarto peggiore.
  - `inconsistent(laps: list[LapStats], *, kmh: float = KMH, corners: int = CORNERS, match: float = MATCH) -> dict[int, list[tuple[str, float]]]` — indice in `laps` → curve lente, per i giri con almeno `corners` curve lente, ciascuno contro tutti gli altri; `{}` se `len(laps) < 3`.

- [ ] **Step 1: test che falliscono** (giri finti con `corner_vmin` a mano, 5 curve):
  - un giro più lento di 6 km/h in 3 curve su 3 giri → `inconsistent(...) == {2: [...]}` con 3 curve;
  - più lento di 6 km/h in 2 curve → `{}`;
  - più lento di 4,9 km/h in 5 curve → `{}`;
  - più veloce di 10 km/h in 5 curve → `{}`;
  - 2 giri soli → `{}`;
  - apici spostati di 0,004 e indici diversi → si accoppiano;
  - apice 0,998 contro 0,002 → si accoppiano;
  - apice 0,30 contro 0,32 → non si accoppiano;
  - `same_dials((3,4,0,0.64), (4,4,0,0.64)) is False`; `same_dials((3,4,0,0.64), (-1,-1,-1,-1.0)) is True`; `same_dials((3,4,0,0.64), (3,4,0,0.642)) is False` (il ripartitore si confronta entro mezzo click, 0,001).
- [ ] **Step 2:** `pytest tests/test_engineer_costanza_pura.py -q` → FAIL (modulo assente).
- [ ] **Step 3:** il modulo, senza import da `core` a livello di modulo che creino giri (`LapStats` solo per i tipi).
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5:** commit «Costanza: quali giri di un gruppo sono incostanti».

### Task 3: l'interruttore per le GT3

**Files:**
- Modify: `src/accoach/engineer/classmap.py`
- Modify: `src/accoach/engineer/factory.py` (`engineer_for`)
- Modify: `src/accoach/engineer/core.py` (`RaceEngineer.__init__`)
- Test: `tests/test_engineer_costanza_gt3.py`

**Interfaces:**
- Produces: `classmap.is_gt3(car_model: str) -> bool` — `known_class(car) is CarClass.GT3` e nessun pezzo del nome fra `gt4`, `gt2`, `gte`.
- Produces: `RaceEngineer(..., consistency_kmh: float | None = None)` → `self.consistency_kmh`.
- Produces: `engineer_for` passa `consistency_kmh=consistency.KMH` se `is_gt3(car_model)`, altrimenti lascia `None` (con `kw.setdefault`, come `bias_offset`).

- [ ] **Step 1: test che falliscono:** `is_gt3` vero per `mclaren_720s_gt3_evo`, `ferrari_296_gt3`, `porsche_992_gt3_r`; falso per `mclaren_570s_gt4`, `bmw_m4_gt4`, `ks_porsche_911_gt2_rs`, `ford_gt_gte` (oggi `known_class` le dà tutte GT3: è proprio l'esclusione da provare), `ks_ferrari_sf15t`, `ks_mazda_mx5_cup`, `"sconosciuta"`. Una GT3 che `known_class` non riconosce (`audi_r8_lms_evo_ii` → `None`) resta spenta: vale solo ciò che il nome dice con certezza. `engineer_for("mclaren_720s_gt3_evo", "Imola", is_acc=True).consistency_kmh == 5.0`; per `mclaren_570s_gt4` e `ks_ferrari_sf15t` è `None`; `RaceEngineer(GT3_PROFILE).consistency_kmh is None`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementazione (l'import di `consistency` in `factory` è locale alla funzione se serve a evitare un giro di import).
- [ ] **Step 4:** PASS, più `tests/test_import_order.py`.
- [ ] **Step 5:** commit «Costanza: accesa solo per le GT3».

### Task 4: l'Ingegnere giudica il gruppo

**Files:**
- Modify: `src/accoach/engineer/core.py` (`RaceEngineer.observe`, `progress`, `_reading_need`, `_evaluate_active`, ogni `self.window = []`)
- Test: `tests/test_engineer_costanza.py`

**Interfaces:**
- Consumes: Task 1, 2, 3.
- Produces:
  - `LapStats.stint_lap` riempito in `observe` (= `self._stint_lap` dopo l'incremento).
  - `RaceEngineer.last_dropped: list[dict]` — i giri tolti a QUESTO giro, rifatto a ogni `observe`: `{"stint": int, "stint_lap": int, "last": bool, "corners": [[nome, scarto_kmh], ...]}` (`last` vero se è il giro appena chiuso). Vuota se non è stato tolto niente.
  - `RaceEngineer._clear_window()` — svuota finestra **e** giri in attesa; sostituisce tutti gli `self.window = []`.

Come funziona (solo se `self.consistency_kmh` non è None; altrimenti nessuna differenza):
- il gruppo: un giro apre un gruppo nuovo se cambia lo stint o se `same_dials` è falso rispetto al giro prima. Aprendo un gruppo nuovo, i giri ancora in attesa del gruppo vecchio si buttano senza frase (stint o manopole corti: non si potevano giudicare);
- un giro pulito e caldo che non apre lo stint va **in attesa** (non nella finestra) finché il gruppo non ha almeno 3 giri giudicabili (attesa + finestra del gruppo, senza quello d'apertura); il giro d'apertura va in finestra come oggi;
- da 3 in su, a ogni giro: `consistency.inconsistent` sui giri giudicabili del gruppo (finestra + attesa, in ordine). I giri in attesa non segnati entrano nella finestra in ordine (con `laps_seen += 1` se c'è una prova); quelli segnati non entrano mai; quelli segnati già nella finestra escono, **tranne** se `self._pending` non è None; se ne esce uno che era stato contato da una prova in corso, `laps_seen` scende di 1;
- `self._skipped = None` anche per un giro messo in attesa (non è un giro scartato).

Contatori: `progress()` (`have` della base e della prova), il messaggio di raccolta in `observe` (`len(self.window)`), `_reading_need()` e il conto di `_evaluate_active` contano anche i giri in attesa del gruppo in corso (quelli che entrerebbero nella lettura). Le decisioni (base, lettura, verdetto) leggono solo la finestra.

- [ ] **Step 1: test che falliscono**, con `RaceEngineer(GT3_PROFILE, min_stable=3, consistency_kmh=5.0)` e giri finti con `corner_vmin` su 5 curve e `stint` dalla benzina:
  - `test_a_slow_lap_does_not_enter`: apertura + 4 giri, il 4° più lento di 6 km/h in 3 curve → non è in `eng.window`; `eng.last_dropped == [{"stint": 1, "stint_lap": 5, "last": True, "corners": [...]}]`;
  - `test_an_earlier_lap_goes_after_the_fact`: il 2° giro dello stint lento, scoperto al 4° → esce, `last` falso, `stint_lap == 2`;
  - `test_two_slow_corners_stay`, `test_faster_laps_stay`;
  - `test_opening_lap_is_neither_judged_nor_a_yardstick`: giro d'apertura lento in 5 curve resta nella finestra e non fa uscire gli altri;
  - `test_waiting_laps_are_not_read_but_are_counted`: dopo la sosta, al 2° giro dello stint `eng.window` non lo contiene ma `progress()["have"]` sì, e il messaggio dice «Servono ancora 2…» (il conto scende 3, 2, 1);
  - `test_a_dial_turned_mid_stint_starts_a_group`: 3 giri a TC 3, poi 3 giri a TC 4 più lenti di 6 km/h in 4 curve → nessuno tolto;
  - `test_a_short_stint_leaves_quietly`: apertura + 2 giri, poi sosta → i 2 giri non entrano mai, nessuna voce in `last_dropped`;
  - `test_a_waiting_proposal_keeps_its_laps`: proposta di pressione in attesa, il pilota fa altri giri, uno rende incostante un giro già in finestra → resta; dopo `mark_applied`, `eng.active.base_pressures is not None`;
  - `test_a_dropped_test_lap_is_uncounted`: prova al volante in corso con `laps_seen == 2`, un giro contato tolto a posteriori → `laps_seen == 1`;
  - `test_without_the_switch_nothing_changes`: stessi giri con `consistency_kmh=None` → finestra e decisioni come oggi;
  - `test_a_dropped_lap_never_comes_back`.
- [ ] **Step 2:** `pytest tests/test_engineer_costanza.py -q` → FAIL.
- [ ] **Step 3:** implementazione in `core.py` secondo le regole sopra; costanti `_CONSISTENCY_KMH`, `_CONSISTENCY_CORNERS`, `_CORNER_MATCH` riprese da `consistency`.
- [ ] **Step 4:** `pytest tests/test_engineer*.py tests/test_impronta*.py -q` → PASS.
- [ ] **Step 5:** commit «Ingegnere: un giro guidato diversamente non conta».

### Task 5: la frase, su qualunque decisione

**Files:**
- Modify: `src/accoach/engineer/core.py` (`_DECISION_MSG`, `observe`)
- Test: `tests/test_engineer_costanza.py` (aggiunte), `tests/test_tono.py` (deve restare verde)

**Interfaces:**
- Consumes: `last_dropped` (Task 4).
- Produces: due chiavi di messaggio, `drop_last` e `drop_earlier`:
  - it `drop_last`: « L'ultimo giro non conta: in {where} sei passato più piano di oltre {kmh} km/h rispetto agli altri giri di questo stint.»
  - it `drop_earlier`: « Il {n}° giro di questo stint non conta più: in {where} eri più lento di oltre {kmh} km/h rispetto agli altri giri.»
  - en `drop_last`: « That last lap doesn't count: at {where} you were more than {kmh} km/h slower than on your other laps this stint.»
  - en `drop_earlier`: « Lap {n} of this stint no longer counts: at {where} it was more than {kmh} km/h slower than the others.»
  - `{where}`: i nomi delle prime 3 curve per scarto («Tosa, Piratella e Rivazza»; con più di 3 «… e altre {k} curve»); se una delle curve segnate non ha nome, «{m} curve» con `m` il numero di curve lente. `{kmh}` = `fmt_num(5)` → «5».
- Ogni decisione che esce da `observe` dopo che il giro è entrato (anche PROPOSE, ACCEPTED, DONE, l'attesa delle pressioni) riceve le frasi in coda al `message`, e anche in coda a `tail` se `tail` non è None.

- [ ] **Step 1: test che falliscono:** con `config.set_language("it")`: la frase di `drop_last` coi nomi; con 4 curve senza nome «in 4 curve»; il giro tolto nel giro in cui l'Ingegnere propone → la PROPOSE contiene la frase; un COLLECT ha la frase anche in `tail`; in inglese «That last lap doesn't count».
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementazione (una funzione `_drop_tail(dropped, lang) -> str` e il ritocco in `observe`, con `dataclasses.replace`).
- [ ] **Step 4:** `pytest tests/test_engineer_costanza.py tests/test_tono.py -q` → PASS.
- [ ] **Step 5:** commit «Ingegnere: dice quale giro non conta, dove e perché».

### Task 6: registro e rigioco

**Files:**
- Modify: `src/accoach/engine.py` (`_log_lap`, `_observe_lap` se serve passare i nomi)
- Modify: `src/accoach/engineer/replay.py` (`_row`, `_format`)
- Test: `tests/test_engineer_costanza_registro.py`

**Interfaces:**
- Consumes: `last_dropped` (Task 4).
- Produces: la riga `lap` del registro ha `dropped=eng.last_dropped`; le righe del rigioco hanno `"dropped": int` (quanti giri tolti a quel giro) e `_format` stampa ` -N` dopo i flag quando è più di 0.

- [ ] **Step 1: test che falliscono:** con il banco di `tests/test_impronta_motore.py` (o uno simile) un giro tolto produce una riga `lap` con `dropped` non vuoto nel registro; `replay(...)` su giri finti con un giro lento restituisce una riga con `dropped == 1`, e `_format` contiene «-1».
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementazione.
- [ ] **Step 4:** PASS, più `tests/test_impronta_motore.py`.
- [ ] **Step 5:** commit «Registro e rigioco: i giri tolti per costanza».

### Task 7: la verifica sulle serate vere

**Files:**
- Modify: `HANDOFF-test-ingegnere-2026-11-16.md` (sezione «Le tappe dopo» e una domanda del test)
- Nessun codice di prodotto.

- [ ] **Step 1: rigioco di tutto l'archivio della 720S.** Per ogni serata (pista, giorno) dei giri `mclaren-720s-gt3-evo` in `Documents/ACCoach/laps`, con casa finta, `accoach_main.py replay-engineer <pista> <AAAAMMGG> --laps <cartella>`. Contare i giri puliti degli stint con almeno 3 giri giudicabili e quanti sono stati tolti. Atteso 10-30 % (rimisurato 15 su 79). Fuori intervallo: fermarsi e riferire, niente installazione.
- [ ] **Step 2: le sette serate del 16/11** (`imola 20261114`, `imola 20261108`, `imola 20260924`, `brands-hatch 20261025`, `zolder 20261029`, `red-bull-ring 20261014`, `zolder 20261101`): confronto riga per riga con le uscite del 16/11, e una spiegazione per ogni differenza.
- [ ] **Step 3: suite intera** con casa finta → nessun rosso.
- [ ] **Step 4:** aggiornare il documento di passaggio: cosa guardare dopo la prossima serata (righe `dropped` nel registro, quanti giri tolti, quali curve) e la tappa «c» come prossima.
- [ ] **Step 5:** commit «Handoff: la costanza del pilota, cosa guardare in pista».
