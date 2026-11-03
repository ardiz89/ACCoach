# Causa per costo e riferimento per curva — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** il coach sceglie la causa di una curva in base a quanto costa davvero, e la misura contro il tuo gesto migliore in quella curva, anche se viene da un giro diverso dal tuo migliore.

**Architecture:** due parti. (A) `classify_corner` riceve la perdita già divisa per fase (la scomposizione di `coaching/phases.py`, che risomma esatta) e fra le cause che superano le loro soglie sceglie quella la cui fase costa di più. Vale per voce e report insieme, perché la regola è una. (B) un nuovo `coaching/corner_refs.py` tiene, per ogni curva, il tuo giro più veloce in quella finestra fra i giri nelle stesse condizioni; l'analyzer dal vivo e il debrief del report confrontano ogni curva con quel giro. Delta a schermo, focus, tendenze, pagella e giro ideale per settori restano sul riferimento di adesso.

**Tech Stack:** Python 3.14, pytest, PySide6 solo dove già usato. Nessuna dipendenza nuova.

**Spec:** la decisione presa in chat il 03/11 (riassunta qui sotto) e `COACHING-PRO.md`. Fonti verificate: Coach Dave Delta, pagina del 07/10/2026 (riferimento più veloce di 0,5–1,5 s, quattro fasi); Track Titan, novembre 2025 (costo per errore, causa prima, catena). Track Titan dice di **simulare** gli scenari; noi **misuriamo** il costo con la scomposizione per fase. Non lo chiamiamo simulazione da nessuna parte.

## Global Constraints

- Testi in italiano con «tu», frasi brevi, virgola decimale, niente slogan, niente due punti a effetto, niente emoji; massimo 25 parole per frase in guida e pagine (`tests/test_tono.py`).
- **Nessuna frase vocale nuova.** Le cause riusano le frasi già registrate in `coaching/spoken.py`; il testo nuovo sta solo nel report e nella guida.
- Test sempre con casa finta: `USERPROFILE=<scratch>/ov/casa HOME=<scratch>/ov/casa QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:cacheprovider`. Mai la cartella vera `Documents\ACCoach`.
- Le misure su giri veri si fanno sulla **copia** dell'archivio nello scratchpad, mai sull'originale.
- `CornerStats` non ha default sui campi: ogni costruttore (analyzer e debrief) deve rispondere a ogni campo.
- Soglie riusate, non inventate: `_LOSS_MS`/`SIGNIF_LOSS_MS` = 120 ms, margini di `analyzer.py` invariati, `phases._GAIN_MS` = 50 ms come guadagno minimo che regge la dispersione fra giri.
- Commit con le righe `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`. Niente push.

## Decisioni

1. **Fasi di ogni causa.** `BRAKE_LATER` → entry. `BRAKE_EARLIER` → entry + apex. `LESS_BRAKE` → entry + apex. `CARRY_SPEED` → apex. `MORE_THROTTLE` → exit + after. `after` esiste solo nel debrief (finestra fino alla curva dopo); dal vivo la zona finisce a `exit_pos` e `after` vale 0.
2. **Scelta.** Candidate = cause le cui condizioni di oggi sono vere. Vince quella con il costo più alto. A parità vince l'ordine di oggi. Se nessuna candidata ha costo > 0, nessuna spiega la perdita: si dice `TIME_LOSS`. Senza fasi (`phase_ms is None`) resta l'ordine fisso di oggi.
3. **Finestra di una curva per il riferimento per curva.** Da `entry_pos` all'`entry_pos` della curva dopo, come il debrief (`debrief._next_entry`).
4. **Quando un giro diventa il riferimento di una curva.** Stessa auto e pista; `valid`; `clean_verdict(...) != 0`; `source != "pro"`; stessa mescola se entrambe note; `road_temp` entro `_TEMP_BAND_C` (8 °C) se entrambe note; campioni che coprono la finestra (primo campione entro 0,005 dall'inizio, ultimo entro 0,005 dalla fine, nessun buco di posizione oltre 0,01). Sostituisce il riferimento principale solo se è più veloce in quella finestra di almeno 50 ms.
5. **Spento** quando il riferimento principale è un giro PRO, o quando non ci sono curve (zone fisse).
6. **Dove vale.** Analyzer dal vivo (consiglio e riquadro dell'ultima curva) e debrief del giro nel report. **Non** vale per: delta a schermo, focus (tiene fermo il suo metro apposta, `engine.py:630-645`), `link_corners`, tendenze, pagella, giro ideale per settori.
7. **Bacino.** I 20 giri più veloci tuoi e affidabili, filtrati con lo stesso rilassamento delle condizioni che ha eletto il riferimento principale. Caricati fuori dal tick (thread), perché il tick gira a 60 Hz.

## Review Focus

1. Un giro con un buco di campioni dentro la finestra (box, ripartenza) non deve diventare il riferimento di quella curva. → Task 2, test di copertura.
2. Un giro tagliato (`clean` = 0) più veloce in una curva non deve diventarne il riferimento. → Task 2.
3. Il riferimento principale passa a un giro PRO: il riferimento per curva si spegne. → Task 5.
4. Il giro appena salvato ha la tua migliore Parabolica: dal giro dopo la Parabolica si confronta con quello, senza ricaricare il bacino. → Task 5.
5. Un consiglio memorizzato per la curva (si dice al giro dopo) era stato calcolato contro un altro riferimento: deve restare coerente con la curva, non con l'indice. → Task 4, test che cambia i riferimenti per curva fra due giri.

---

### Task 1: la causa la sceglie il costo

**Files:**
- Modify: `src/accoach/coaching/analyzer.py` (`CornerStats`, `classify_corner`, `_Seg`, `_accumulate`, `_finalize`)
- Modify: `src/accoach/coaching/debrief.py:847-853` (passa le fasi)
- Test: `tests/test_causa_per_costo.py` (nuovo); aggiorna i costruttori di `CornerStats` nei test esistenti (`grep -rn "CornerStats(" tests`)

**Interfaces:**
- Produces: `CornerStats.phase_ms: dict[str, float] | None` (chiavi `PHASES` di `phases.py`); `CAUSE_PHASES: dict[CueCategory, tuple[str, ...]]` in `analyzer.py`; `classify_corner(st, index, pos)` con la stessa firma.

- [ ] **Step 1: test che falliscono**

```python
def _st(**kw):
    base = dict(lost_ms=300.0, throttle_live=0.5, throttle_ref=0.5, brake_live=0.2,
                brake_ref=0.2, min_speed_live=100.0, min_speed_ref=100.0,
                braking_early=False, braking_late=False, phase_ms=None)
    return CornerStats(**{**base, **kw})

def test_the_most_expensive_cause_wins_over_the_fixed_order():
    # frenata anticipata (entry 40 ms) e gas mancante (exit 260 ms): oggi vince la frenata
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6,
             phase_ms={"entry": 40.0, "apex": 0.0, "exit": 260.0, "after": 0.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.MORE_THROTTLE

def test_a_cause_whose_phase_gained_time_is_not_the_cause():
    st = _st(braking_early=True,
             phase_ms={"entry": -80.0, "apex": 150.0, "exit": 230.0, "after": 0.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.TIME_LOSS

def test_without_phases_the_old_order_holds():
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6)
    assert classify_corner(st, 0, 0.5).category is CueCategory.BRAKE_LATER

def test_a_tie_keeps_the_old_order():
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6,
             phase_ms={"entry": 150.0, "apex": 0.0, "exit": 150.0, "after": 0.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.BRAKE_LATER

def test_live_zone_records_its_three_phases():
    # analyzer alimentato con frame sintetici: delta cresce solo dopo l'apex
    # (riusa gli helper di tests/test_analyzer.py); il CornerStats finale ha
    # phase_ms["exit"] ≈ perdita totale e "after" == 0.0
    ...
```

L'ultimo test lo scrive l'implementatore sul modello di `tests/test_analyzer.py`, con la perdita tutta dopo `apex + _APEX_HALF`; deve fallire oggi perché `phase_ms` non esiste.

- [ ] **Step 2:** `pytest tests/test_causa_per_costo.py -q` → FAIL (`unexpected keyword argument 'phase_ms'`).
- [ ] **Step 3: implementa.** In `classify_corner`, dopo `GOOD` e la soglia: raccogli le candidate nell'ordine di oggi con le condizioni di oggi; se `phase_ms` c'è, costo = somma delle fasi in `CAUSE_PHASES`, scegli `max` stabile (il primo a parità), scarta se costo ≤ 0; se non resta nessuna, ramo `TIME_LOSS` di oggi. Dal vivo `_Seg` registra il delta al primo frame con `pos >= mid - _APEX_HALF` e con `pos >= mid + _APEX_HALF` (importa `_APEX_HALF` da `diagnosis.py`, come `phases.py`); `_finalize` costruisce `phase_ms` = entry/apex/exit da quei tre tagli, `after` = 0.0; se un taglio non è mai stato attraversato la sua fase vale 0.0. Nel debrief `phase_ms={p.phase: p.lost_ms for p in phases} or None`.
- [ ] **Step 4:** test nuovi e `tests/test_analyzer.py tests/test_debrief.py tests/test_phases.py` → PASS, poi suite intera → PASS.
- [ ] **Step 5: misura sui giri veri (copia dell'archivio).** Script nello scratchpad: per ogni giro della copia, debrief contro il riferimento del suo giorno con la regola vecchia e nuova; conta quante curve cambiano causa e in quale direzione. Il numero va nel messaggio di commit. Se cambiano più del 40 % delle curve, fermati e riferisci prima di proseguire.
- [ ] **Step 6: commit** «La causa di una curva la sceglie quanto costa la sua fase».

### Task 2: il gesto migliore di ogni curva

**Files:**
- Create: `src/accoach/coaching/corner_refs.py`
- Test: `tests/test_riferimento_per_curva.py` (nuovo)

**Interfaces:**
- Consumes: `Reference` (`comparison/reference.py`), `Corner` (`track.py`), `Lap`, `clean_verdict` (`recording/lap.py`), `debrief._next_entry`.
- Produces:
  - `MIN_GAIN_MS = 50.0`, `POOL_SIZE = 20`
  - `@dataclass(slots=True) class CornerRef: reference: Reference; window_ms: float; gain_ms: float; lap_time_ms: int`
  - `def window_ms(ref: Reference, lo: float, hi: float) -> float | None` — None se i campioni non coprono la finestra (Decisione 4).
  - `class CornerBests: __init__(self, main: Reference, corners: list[Corner]); offer(self, lap: Lap) -> bool; at(self, pos: float) -> CornerRef | None`
  - `def eligible(lap: Lap, main: Lap) -> bool`

- [ ] **Step 1: test che falliscono.** Con `synth.build_lap(slow_corner=..., amt=...)` costruisci un riferimento principale lento nella curva 2 e un secondo giro veloce lì e lento altrove.

```python
def test_a_lap_faster_in_one_corner_becomes_that_corners_reference(): ...
    # bests.offer(other) is True; bests.at(apex_2).gain_ms >= 50; bests.at(apex_1) is None
def test_a_gain_under_fifty_ms_is_noise(): ...
def test_a_cut_lap_is_never_a_reference():          # clean=False
def test_a_lap_with_a_hole_in_the_window_is_skipped():  # togli i campioni fra entry e apex
def test_another_compound_or_a_track_twelve_degrees_hotter_is_skipped():
def test_a_pro_lap_is_never_a_corner_reference():
def test_offering_a_slower_lap_changes_nothing():   # offer -> False
def test_positions_on_a_straight_belong_to_the_corner_before():
    # at(pos) fra exit_pos e la entry dopo ritorna il CornerRef della curva prima
```

- [ ] **Step 2:** → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: implementa.** `CornerBests` tiene una lista di `(lo, hi, CornerRef | None)` ordinata per `lo`; `offer` scarta con `eligible`, costruisce `Reference(lap)` una volta, e per ogni finestra confronta `window_ms` con quella del riferimento attuale della finestra (o del principale). `at` cerca con `bisect`. Il docstring del modulo dice perché (Decisioni 4-6) e che è una misura, non una simulazione.
- [ ] **Step 4:** test → PASS.
- [ ] **Step 5: commit** «Il gesto migliore di ogni curva, dai tuoi giri nelle stesse condizioni».

### Task 3: il bacino dal catalogo

**Files:**
- Modify: `src/accoach/recording/catalog.py` (`_own_reference` → condivide il ciclo)
- Modify: `src/accoach/recording/storage.py` (funzione pubblica accanto a `find_reference_lap`)
- Test: `tests/test_riferimento_per_curva.py`

**Interfaces:**
- Produces: `LapCatalog.reference_pool_paths(car_model, track, road_temp=None, grip=None, compound=None, limit=20) -> list[str]`; `storage.reference_pool(car_model, track, laps_dir, road_temp=None, grip=None, compound=None, limit=20) -> list[Lap]` (salta i file che non si caricano).

- [ ] **Step 1: test.** Catalogo in `tmp_path` con 25 giri: 3 tagliati, 2 PRO, 5 su un'altra mescola. `reference_pool_paths(..., compound="dry_compound")` → 15 giri, nessun tagliato, nessun PRO, nessuna mescola diversa, ordinati per tempo. Con condizioni che nessun giro ha → si rilassa come `_own_reference` (stesso ordine: grip, temperatura, mescola).
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** porta il ciclo di rilassamento in `_own_rows(car, track, road_temp, grip, compound, limit)`; `_own_reference` diventa `rows[0] if rows else None`. `best_reference_path` non cambia comportamento (i suoi test esistenti lo provano).
- [ ] **Step 4:** test nuovi e `pytest tests -q -k catalog` → PASS.
- [ ] **Step 5: commit** «Il catalogo dà il bacino dei giri nelle stesse condizioni».

### Task 4: l'analyzer confronta ogni curva col suo gesto migliore

**Files:**
- Modify: `src/accoach/coaching/analyzer.py`
- Test: `tests/test_riferimento_per_curva.py`

**Interfaces:**
- Consumes: `CornerBests.at(pos)` (Task 2), `phase_ms` (Task 1).
- Produces: `CoachAnalyzer.set_corner_refs(bests: CornerBests | None) -> None`.

- [ ] **Step 1: test.** Analyzer con le curve del riferimento principale e `set_corner_refs(bests)` dove la curva 2 ha un riferimento suo. Un giro che ricalca il principale: la curva 2 dà un consiglio (perdi rispetto al gesto migliore), la curva 1 no. Senza `set_corner_refs` lo stesso giro non dà consigli. Per la Review Focus 5: un consiglio memorizzato sulla curva 2 resta sulla curva 2 dopo un `set_corner_refs` nuovo.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** `_Seg` prende `ref: CornerRef | None` all'ingresso (`bests.at(mid)`). In `_accumulate`, con `seg.ref`: `rp = seg.ref.reference.point_at(pos)` e delta = `s.current_lap_ms - seg.ref.reference.time_at(pos)`; senza, il delta e il punto di oggi. `set_corner_refs` non tocca `_advice` né `_announced`.
- [ ] **Step 4:** test e `tests/test_analyzer.py` → PASS.
- [ ] **Step 5: commit** «Dal vivo ogni curva si misura col tuo gesto migliore».

### Task 5: il motore lo tiene aggiornato

**Files:**
- Modify: `src/accoach/engine.py` (`_rebuild_reference`, ciclo dei giri salvati ~1268-1280, tick)
- Test: `tests/test_riferimento_per_curva.py` (sul modello dei test del motore che usano `synth` e una cartella giri finta)

**Interfaces:**
- Consumes: `storage.reference_pool` (Task 3), `CornerBests` (Task 2), `set_corner_refs` (Task 4).

- [ ] **Step 1: test.**
  - il riferimento principale cambia → parte una costruzione in background e, finita, l'analyzer ha i suoi riferimenti per curva;
  - riferimento PRO → `set_corner_refs(None)`;
  - giro salvato con una curva più veloce → `offer` e `set_corner_refs` subito, senza ricaricare il bacino;
  - una costruzione finita per un riferimento ormai vecchio (token diverso) si butta.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** un `ThreadPoolExecutor(max_workers=1)` del motore; in `_rebuild_reference`, dopo le curve, se `self._reference.lap.source != "pro"` e ci sono curve: `submit` di una funzione che carica il bacino e costruisce `CornerBests`, legata a `_reference_token`. Nel tick, se il future è pronto e il token è quello di adesso, `set_corner_refs`, poi `offer` dei giri salvati nel frattempo. Nel ciclo dei giri salvati, prima di `_rebuild_reference`: `offer(lap)` se ci sono già i `CornerBests`. Prima di scriverlo misura `load_lap` su 20 giri della copia dell'archivio e scrivi il numero nel commento: se tutto sta sotto i 50 ms, il thread resta lo stesso (il motore non deve dipendere dalla dimensione dell'archivio).
- [ ] **Step 4:** test e suite → PASS.
- [ ] **Step 5: commit** «Il motore tiene i gesti migliori aggiornati senza fermare il tick».

### Task 6: il report dice con cosa confronta

**Files:**
- Modify: `src/accoach/coaching/debrief.py` (`build_lap_debrief(..., corner_refs: CornerBests | None = None)`, `CornerLoss.compared_ms: int = 0`)
- Modify: `src/accoach/api.py:~1208` (solo il debrief del giro rivisto)
- Modify: `src/accoach/i18n.py` o le tabelle di testo del debrief, `GUIDA.md`, `docs/FAQ.md`
- Test: `tests/test_riferimento_per_curva.py`, `tests/test_debrief.py`

- [ ] **Step 1: test.** Con `corner_refs`, la curva 2 misura perdita, fasi, statistiche e frenata contro il suo riferimento; `compared_ms` = tempo sul giro di quel riferimento; il dettaglio contiene «Confronto con la tua migliore in questa curva, dal giro in 1:48,912.» (en: «Compared with your best through this corner, from the 1:48.912 lap.»). Senza `corner_refs` il debrief è identico a oggi (stesso oggetto confrontato campo per campo). Le chiamate di focus, tendenze e pagella non passano `corner_refs` (test che lo verifica su `engine.py:610` e `pagella.py`).
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** per ogni curva `ref_c = corner_refs.at(c.apex_pos)`; se c'è, usa `ref_c.reference` al posto di `reference` per finestra, fasi, `refs`, onset e `_braking_detail`; `_grip_envelope` e `link_corners` restano sul principale (Decisione 6). In `api.py` costruisci i `CornerBests` con `storage.reference_pool` usando le stesse condizioni con cui l'endpoint elegge il riferimento, e passali solo al debrief del giro rivisto.
- [ ] **Step 4:** guida e FAQ, un paragrafo nella sezione del report: cosa vuol dire «la tua migliore in questa curva», perché il delta a schermo resta sul giro migliore, perché i numeri per curva possono essere più alti di prima. Poi `tests/test_tono.py` e suite → PASS.
- [ ] **Step 5: prova nel browser** su `127.0.0.1:8778` con la copia dell'archivio come casa (mai svuotare il localStorage): un giro con almeno una curva confrontata col gesto migliore mostra la frase, uno senza no.
- [ ] **Step 6: commit** «Il report dice con quale giro confronta ogni curva».
