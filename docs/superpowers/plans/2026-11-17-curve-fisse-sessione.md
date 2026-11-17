# Curve fisse per la serata dell'Ingegnere — piano di lavoro

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** l'Ingegnere misura tutti i giri di una serata sulle stesse curve e con gli stessi nomi, anche dopo un nuovo miglior giro e anche senza riferimento.

**Architecture:** il motore (`src/accoach/engine.py`) tiene una copia delle curve e dei nomi dell'Ingegnere, fissata quando l'Ingegnere nasce (curve del riferimento) o, senza riferimento, sul primo giro pulito e valido; la diagnosi per l'Ingegnere usa quella copia. Il coach dal vivo non cambia.

**Tech Stack:** Python 3.14 locale (CI 3.11/3.12), pytest (suite solo con `USERPROFILE` finto).

**Spec:** `docs/superpowers/specs/2026-11-17-curve-fisse-sessione-design.md`

## Global Constraints

- Il coach dal vivo (Focus, analyzer, debrief) continua a usare `self._corners` e `self._corner_names` come oggi.
- Il rigioco (`engineer/replay.py`) non cambia.
- Un giro fissa le curve solo se `lap.valid and lap.clean is not False`; se `detect_corners` non trova curve, si riprova al giro dopo.
- Le curve dell'Ingegnere si azzerano solo quando l'Ingegnere rinasce (cambio di auto o pista).
- Suite: `USERPROFILE=<cartella temporanea> .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`.

## Review Focus

- Nuovo miglior giro a metà serata: le curve dell'Ingegnere non cambiano, quelle del coach sì (test nel Task 1).
- Primo giro della serata sporco, senza riferimento: non fissa le curve, il primo pulito sì (test nel Task 1).
- Riferimento che arriva DOPO che le curve sono state fissate da un giro: restano quelle del giro (test nel Task 1).
- Cambio di pista nella stessa sessione dell'app: si fissano di nuovo (test nel Task 1).

---

### Task 1: le curve dell'Ingegnere nel motore

**Files:**
- Modify: `src/accoach/engine.py` (creazione dell'Ingegnere vicino a `self._engineer = engineer_for(...)`, `_observe_lap`)
- Test: `tests/test_engineer_curve_fisse.py` (nuovo)

**Interfaces:**
- Produces: `CoachEngine._engineer_corners: list[Corner]` e `CoachEngine._engineer_corner_names: dict[int, str]`, copiati da `self._corners` / `self._corner_names` quando l'Ingegnere nasce (liste vuote se non c'è riferimento).
- Produces: `CoachEngine._engineer_stats(lap: Lap) -> LapStats` — se `_engineer_corners` è vuota e il giro è valido e pulito, le fissa con `detect_corners(lap.samples)` e `_corner_labels(lap.car_model, lap.track, corners, self.laps_dir)`; poi `build_lap_stats(lap, self._engineer_corners or None, corner_names=self._engineer_corner_names)`. `_observe_lap` la usa al posto della chiamata di oggi.

- [ ] **Step 1: test che falliscono** (motore vero con lettore finto come `_Rig` in `tests/test_impronta_motore.py`; spia su `eng._engineer.observe` per leggere le `LapStats`; giri da `synth.build_lap`):
  - `test_a_new_best_does_not_move_the_engineers_corners`: Ingegnere nato con le curve A; poi `eng._corners` diventa B (nuovo miglior giro); un giro osservato ha `corners_key` di A e `corners_own` falso; `eng._corners` resta B.
  - `test_without_a_reference_the_first_clean_lap_fixes_the_corners`: niente riferimento; primo giro con `clean=False` → `corners_own` vero e `_engineer_corners` vuota; secondo giro pulito → curve fissate, `corners_own` falso; terzo giro → stessa `corners_key` del secondo.
  - `test_a_reference_arriving_later_does_not_replace_fixed_corners`: curve fissate dal primo giro pulito; poi `eng._corners` diventa C; il giro dopo ha ancora la chiave del primo giro pulito.
  - `test_a_new_track_fixes_the_corners_again`: cambio di pista (snapshot con altra pista) → `_engineer_corners` presa dal riferimento della pista nuova (o vuota senza).
  - `test_the_engineer_names_come_from_when_the_corners_were_fixed`: con nomi {0: "Tosa"} al momento del fissaggio e nomi diversi dopo, `lost_where` / i nomi in `corner_vmin` dicono «Tosa».
- [ ] **Step 2:** `pytest tests/test_engineer_curve_fisse.py -q -p no:cacheprovider` (con casa finta) → FAIL.
- [ ] **Step 3:** implementazione in `engine.py` secondo le Interfaces; commento in italiano col perché (17/11: il gruppo della costanza ricominciava a ogni nuovo miglior giro).
- [ ] **Step 4:** `pytest tests/test_engineer_curve_fisse.py tests/test_impronta_motore.py tests/test_engine*.py tests/test_engineer*.py -q -p no:cacheprovider` → PASS; poi la suite intera.
- [ ] **Step 5:** commit «Ingegnere: le stesse curve per tutta la serata».
