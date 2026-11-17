# Gesti per curva e aderenza per velocità — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** il report di una curva dice, oltre a quanto perdi e perché, il gesto che fai diverso dal riferimento (rilascio del freno, apertura del gas, marcia, ABS, sterzo), e misura il grip usato contro il limite dell'auto a quella velocità invece che contro uno solo per tutto il giro.

**Architecture:** un modulo puro nuovo `coaching/gestures.py` calcola le misure di una curva da una lista di campioni; le soglie che separano un gesto diverso dal rumore si misurano sulla copia dell'archivio, come dispersione dei giri del pilota nella stessa curva. Il debrief le calcola per te e per il riferimento della curva (quello di `corner_refs` se c'è) e aggiunge una frase per il gesto più fuori soglia. `_grip_envelope` diventa un inviluppo per fasce di velocità. Solo report: niente voce nuova.

**Tech Stack:** Python 3.14, pytest. Nessuna dipendenza nuova.

**Spec:** la proposta in chat del 03/11 (punti 2 e 3 della risposta «cosa ci manca»), approvata dal pilota con «vai avanti con gli altri task». Riferimento esterno verificato: Coach Dave Delta divide la curva in quattro fasi con misure precise (frenata: punto, pressione iniziale, rilascio; uscita: tempi e intensità del gas), pagina del 07/10/2026. `COACHING-PRO.md` §4 elenca le misure mancanti.

## Global Constraints

- Testi in italiano con «tu», frasi brevi, virgola decimale, niente slogan, niente due punti a effetto, niente emoji; massimo 25 parole per frase in guida e pagine (`tests/test_tono.py`).
- **Nessuna frase vocale nuova**: tutto resta nel report (campo `detail` di `CornerLoss`).
- Test sempre con casa finta (vedi le regole del progetto). Misure solo sulla **copia** dell'archivio. Mai `Documents\ACCoach`, mai la porta 8778.
- Ogni soglia nuova è **misurata** sulla copia dell'archivio e il numero misurato sta nel commento accanto alla costante. Nessuna soglia a sentimento.
- Il debrief senza le misure nuove (giro senza campioni utili) resta identico a oggi.
- Commit con le righe `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`. Niente push.

## Decisioni

1. **Le cinque misure di una curva**, sui campioni da `entry_pos` a `exit_pos`:
   - `release_s`: dal picco del primo tratto di frenata al primo campione dopo il picco con freno sotto `_PEDAL_OFF` (0,05, già in `debrief.py`). None senza frenata.
   - `pickup_s`: dal primo campione dopo la velocità minima con gas sopra `_PEDAL_OFF` al primo con gas ≥ 0,9. None se non ci arriva dentro la curva.
   - `apex_gear`: la marcia al campione di velocità minima.
   - `abs_s`: i secondi con `abs_active > 0`.
   - `steer_reversals`: quante volte la velocità dello sterzo cambia verso con un'ampiezza di almeno 0,02 (isteresi).
   Lo 0,9 e lo 0,02 sono i valori di partenza; il Task 2 li conferma o li corregge sulla misura e lo scrive.
2. **Gesto diverso dal rumore.** Per ogni misura la soglia è il 75° percentile, su tutte le curve dell'archivio, della differenza assoluta fra un giro del pilota e la mediana dei suoi giri in quella curva. Sotto soglia non si dice niente. Per la marcia non c'è soglia: conta la marcia di quel giro, ed è un gesto diverso se è diversa da quella del riferimento.
3. **Quale gesto si dice.** Al massimo uno per curva: quello con il rapporto più alto fra differenza e soglia. A parità vince l'ordine della curva (freno, ABS, marcia, sterzo, gas).
4. **Contro chi.** Contro lo stesso riferimento della curva che usa il debrief (`corner_refs.at(apex)` se c'è, altrimenti il principale), così frase e perdita parlano dello stesso giro.
5. **Inviluppo per velocità.** Fasce di 40 km/h. Per ogni fascia il 95° percentile del G combinato del riferimento, come oggi (`_GRIP_PCTL`). Una fascia con meno di 50 campioni prende l'inviluppo di tutto il giro. La curva usa la fascia della sua velocità mediana fra entry ed exit. Il grip resta sul riferimento principale (decisione 6 del piano di prima).

## Review Focus

1. Un giro registrato prima dei canali G o ABS (campi a 0) non deve produrre frasi. → Task 1.
2. Una curva presa in pieno (niente freno) non ha rilascio e non deve dire «rilasci in 0 s». → Task 1.
3. Una curva dove il riferimento non arriva al 90 % di gas e tu sì non deve dire che lui apre più in fretta. → Task 1.
4. Una fascia di velocità con pochi campioni non deve dare un limite basso che fa dire «sei al limite» ovunque. → Task 4.
5. La marcia letta come «N» o «R» in un campione isolato non conta. → Task 1.

---

### Task 1: le misure di una curva

**Files:** Create `src/accoach/coaching/gestures.py`; Test `tests/test_gesti.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True, slots=True) class Gestures: release_s: float | None; pickup_s: float | None; apex_gear: str | None; abs_s: float; steer_reversals: int`
- `def measure(samples: list[LapSample]) -> Gestures` (campioni già tagliati alla curva).

- [ ] **Step 1: test che falliscono**, con campioni costruiti a mano (helper locale): frenata con picco e rilascio in 0,5 s → `release_s ≈ 0.5`; nessuna frenata → `release_s is None`; gas che arriva a 0,9 dopo 0,8 s dalla minima → `pickup_s ≈ 0.8`; gas che resta a 0,7 → `None`; marcia «3» alla minima → «3»; un solo campione «N» alla minima fra due «3» → «3» (la marcia è la più frequente nei campioni entro ±0,25 s dalla minima); ABS attivo per 0,3 s → `abs_s ≈ 0.3`, campi a 0 → 0.0; sterzo a dente di sega con ampiezza 0,05 per 4 volte → 4; oscillazione di 0,01 → 0.
- [ ] **Step 2:** → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3:** implementa `measure`. Tempo dai `t_ms`.
- [ ] **Step 4:** → PASS. **Step 5:** commit «Le misure dei gesti in una curva».

### Task 2: quanto è rumore

**Files:** Modify `src/accoach/coaching/gestures.py`; Test `tests/test_gesti.py`; script di misura nello scratchpad (non nel repo).

**Interfaces — Produces:** costanti `RELEASE_NOISE_S`, `PICKUP_NOISE_S`, `ABS_NOISE_S`, `STEER_NOISE`; `@dataclass GestureNote: kind: str; live: float | str; ref: float | str; score: float`; `def compare(live: Gestures, ref: Gestures) -> GestureNote | None` (Decisioni 2-3).

- [ ] **Step 1: misura.** Sulla copia dell'archivio: per ogni coppia auto+pista, curve di `detect_corners` sul giro più veloce; per ogni curva e misura, la differenza assoluta di ogni giro dalla mediana dei giri. Riporta per misura: numero di valori, mediana, 75° percentile. Controlla anche lo 0,9 e lo 0,02 della Decisione 1 (quante curve hanno `pickup_s` None con 0,9; quante inversioni conta lo sterzo su un rettilineo di confronto) e correggili se la misura lo chiede, scrivendo perché.
- [ ] **Step 2: test** per `compare`: sotto soglia → None; release oltre soglia e marcia diversa → vince quella col rapporto più alto (la marcia diversa ha rapporto 1,0); `None` da una parte sola (tu freni, lui no) → la misura non si confronta.
- [ ] **Step 3:** implementa; costanti con il numero misurato nel commento. **Step 4:** → PASS. **Step 5:** commit «Quanto un gesto è diverso dal rumore, misurato sui tuoi giri» con i numeri nel corpo.

### Task 3: il report dice il gesto

**Files:** Modify `src/accoach/coaching/debrief.py` (`CornerLoss.gesture: GestureNote | None = None`, frase nel `detail`); `src/accoach/api.py` solo se `CornerLoss` passa al JSON campo per campo (controlla la serializzazione); Test `tests/test_gesti.py`, `tests/test_debrief.py`.

- [ ] **Step 1: test.** Debrief di un giro sintetico che rilascia il freno di colpo dove il riferimento lo rilascia piano: la curva ha `gesture.kind == "release"` e il `detail` contiene «Rilasci il freno in 0,2 s, il riferimento in 0,8 s.» (en: «You release the brake in 0.2 s, the reference in 0.8 s.»). Le altre frasi, una per tipo: «Apri il gas in {x} s, il riferimento in {y} s.»; «All'apex sei in {g}ª, il riferimento in {h}ª.»; «L'ABS lavora {x} s, nel riferimento {y} s.»; «Correggi lo sterzo {n} volte, il riferimento {m}.» (e le inglesi corrispondenti). Con `corner_refs` la misura del riferimento viene dal riferimento della curva. Un giro senza gesti fuori soglia dà un debrief identico a oggi.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa; i campioni del riferimento si prendono dal suo `lap` fra `entry_pos` ed `exit_pos`. **Step 4:** → PASS e suite. **Step 5:** commit «Il report dice il gesto che fai diverso dal riferimento».

### Task 4: il limite di grip a quella velocità

**Files:** Modify `src/accoach/coaching/debrief.py` (`_grip_envelope`, `_grip_state`); Test `tests/test_debrief.py` o un file nuovo `tests/test_aderenza_per_velocita.py`.

- [ ] **Step 1: test.** Riferimento sintetico con G combinato 1,2 sotto i 120 km/h e 2,0 sopra: una curva lenta a 1,15 G è «al limite», non a 58 %; una curva veloce a 1,9 G è al limite; una fascia con 10 campioni usa l'inviluppo del giro.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa (Decisione 5); `_grip_envelope` restituisce un oggetto con `at(speed_kmh) -> float`; `_grip_state` riceve la velocità mediana della curva.
- [ ] **Step 4: misura** sulla copia dell'archivio quante curve cambiano stato («al limite» / «margine» / niente) e scrivilo nel commit. Se cambiano più del 40 %, fermati e riferisci.
- [ ] **Step 5:** commit «Il grip di una curva si misura contro il limite a quella velocità».

### Task 5: guida e FAQ

**Files:** `GUIDA.md`, `docs/FAQ.md`; Test `tests/test_tono.py` e un test in `tests/test_guide.py` che cerca le due frasi.

- [ ] Un paragrafo nella sezione del report: cosa sono le cinque misure, che se ne dice una sola per curva e solo quando esce dal tuo rumore, e che il grip ora si confronta col limite a quella velocità. → PASS, commit «La guida spiega i gesti e il grip per velocità».
