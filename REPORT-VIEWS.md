# Reportistica HONE — nuove viste (spec)

> Panel di valutazione (2026-07-02): dashboard-dev, telemetry-analyst, race-engineer-GT3
> + analisi concorrenza (Track Titan, Trophi.ai, Garage61, MoTeC i2, Coach Dave Delta).
> Obiettivo: decidere quali viste aggiungere alla web app di analisi (`accoach/web`).

## Contesto

La reportistica oggi ha 4 tab (`compare`, `map`, `sectors`, `progress`) servite da
`api.py` + frontend offline in `accoach/web` (canvas 2D disegnati a mano, zero
librerie JS). Il differenziatore già in mano è il **debrief causale per curva**
(sotto/sovrasterzo × fase × velocità) — nessun concorrente "giovane" ce l'ha.

### Viste esistenti (baseline — non duplicare)

| Tab | Contenuto |
|---|---|
| **Compare** | delta trace, velocità, gas/freno, sterzo (overlay vs reference), mini-mappa, tabella vmin per curva, debrief mini-lesson |
| **Map** | linea colorata sul delta + spessore = tempo perso, punti di frenata, nomi curve |
| **Sectors** | barre delta per settore + giro ideale ricucito |
| **Trends** | tempi nel tempo, consistenza globale, gomme (medie per giro), punti deboli sistematici, errori ricorrenti |

## Il dato chiave

Lo schema giro (v7, 32 canali) è molto più ricco di ciò che disegniamo:
`_channels()` in `api.py` serve al frontend **solo 8 canali** (`pos, speed,
throttle, brake, steer, gear, x, z`). Restano **registrati ma mai visualizzati**:

- `g_lat`, `g_long` (G laterale/longitudinale) — validati live 2026-06-28
- `slip_ratio` (`sr_fl/fr/rl/rr`) — slip fisico car-agnostico, affidabile per lock/spin
- `yaw_rate`, `abs_active`, `tc_active`, `rpm`
- `tyre_core_temp` / `tyre_pressure` **per-punto** (oggi solo medie per giro)

Aggiungere una vista su questi costa in pratica **una riga per canale** in
`_channels()` + una `drawXxx()` da ~15 righe (il toolkit canvas e l'hover
sincronizzato esistono già). Nessuna nuova pipeline di registrazione.

Da escludere finché non si ri-registra (bump schema del writer, non recuperabile
dai giri esistenti): `brake_temp`, `fuel`, `clutch`, `brake_bias`/`tc_level`
per-campione, "% redline" (manca `max_rpm` per-campione).

## Benchmark concorrenza (sintesi)

- **Tavola posta minima** (quasi tutti): delta trace, overlay input, track map,
  track map colorata gain/loss, comparazione settori, reference overlay, cursore
  sincronizzato. → **già coperta.**
- **Avanzate/differenzianti** (solo i migliori): G-G / traction circle (MoTeC,
  Racelab), time-variance dedicata (MoTeC), line-deviation laterale (Garage61),
  consistenza/varianza multi-giro (Trophi), AI insight prioritizzati per
  costo-in-tempo e per fase (Trophi/Delta/Track Titan), video sincronizzato
  (Delta 5.5), tyre temp/press over-lap (Delta ACC).
- **Gap tipici di un prodotto giovane**: line-deviation, G-G, time-variance,
  consistenza multi-giro localizzata, tyre over-lap.

## Proposta prioritizzata

Ordine per (valore diagnostico × convergenza dei tre esperti × basso costo).

### 🥇 Tier 1 — massimo impatto, dato solido, costo minimo

1. **Diagramma G-G (friction circle)** — scatter `g_lat`×`g_long`. Mostra quanto
   grip il pilota sfrutta e come combina freno+curva: la "croce" (frena dritto →
   poi gira) svela il trail-braking assente. *Dato: g_lat/g_long, assi validati.*
2. **Trail-braking / coasting** — per curva, sovrapposizione rilascio-freno ↔
   apertura-gas e i ms di *coasting* (né gas né freno): tempo morto tipico
   dell'intermedio, quantificato. *Dato: throttle/brake — già serviti, zero backend.*
3. **Lock/Spin trace (`slip_ratio`)** — slip per asse (ant/post): dove blocchi
   l'anteriore in staccata / pattini in uscita. *Dato: sr_*, soglie per-classe
   (lock −0.15 all-class; rear-spin Road +0.12 / GT3 +0.13 / Formula +0.15).*

### 🥈 Tier 2 — alto valore, sforzo medio

4. **Gomme intra-giro** — temp+pressione lungo il giro (oggi solo medie in Trends).
5. **Line-deviation / traiettoria vs reference** — offset laterale in metri: dove
   vai largo/stretto. *Dato: car_x/z già validati.*
6. **Consistenza per curva (banda σ localizzata)** — N giri sovrapposti con banda
   di dispersione per curva: dove sei incostante, non solo σ globale sul tempo.
7. **Balance ribbon sulla mappa** — linea in pista colorata sotto/sovrasterzo (da
   `yaw_rate`, segnale che `coaching/balance.py` già calcola live, `_YAW_SIGN=-1.0`).

### 🥉 Tier 3 — utile, più di nicchia

8. **Waterfall "dove ho perso il giro"** — barre curve ordinate per decimi persi +
   causa. I `losses[]` sono **già calcolati** dal debrief: solo un grafico.
9. **Yaw vs sterzo** (rotazione), **smoothness pedali/sterzo** (jerk, reversal
   rate), **punti di cambiata** (RPM/gear).

## Note di implementazione

- **Backend**: aggiungere canali per-punto = una riga in `_channels()`
  (`api.py`). Le route non si ricaricano a caldo → **riavviare il server**. I file
  statici in `web/` sì.
- **Frontend**: riusare `setup(cv)`, `line()`, `cornerBands()`, `crosshair()`,
  `nearest()`. Grafico su asse posizione = crosshair condiviso automatico. Grafico
  non-posizione (G-G) = hover screen-space come la mappa (`nearestPos`).
- **i18n**: ogni stringa chrome va in `web/i18n.js` (EN+IT) con `data-i18n`.
- **Test**: `tests/test_api.py` (FastAPI TestClient) per i nuovi canali; il demo
  seed (`_seed_demo`) e `tests/synth.py` vanno popolati coi nuovi canali o le
  viste restano vuote in `--demo`.
- **Coordinamento**: il working tree è condiviso con la sessione
  `feat/engineer-voice`. Allinearsi prima di toccare `web/` o `coaching/`.

## Stato implementazione

- [x] Tier 1.1 — Diagramma G-G
- [x] Tier 1.2 — Trail-braking / coasting
- [x] Tier 1.3 — Lock/Spin trace
- [x] Tier 2.4 — Gomme intra-giro (temp+press per posizione, tab Dinamica)
- [x] Tier 2.5 — Line-deviation (scostamento laterale in metri; canale `line_offset` in `/api/analysis`)
- [x] Tier 2.6 — Consistenza per curva (banda σ localizzata; `corner_consistency` in `/api/progress`, sezione in Trends)
- [x] Tier 2.7 — Balance ribbon (nastro traiettoria sotto/sovrasterzo da `yaw_rate`; riusa le soglie di `coaching/balance.py`)
- [x] Tier 3.8 — Waterfall "dove ho perso il giro" (barre curve ordinate dai `losses[]` esistenti, tab Confronto)
- [x] Tier 3.9a — Yaw vs sterzo (rotazione; canale `yaw` in `_channels`, grafico in Dinamica)
- [x] Tier 3.9b — Punti di cambiata (canale `rpm` + marker gear-change ▲▼, grafico in Dinamica)
- [x] Tier 3.9c — Smoothness sterzo (correzioni/cambi di direzione, metrica nel riepilogo Dinamica)
- [x] 2026-07-30 — vista **Traiettoria** (`trajectory.py` + `/api/trajectory`) e
      passata di leggibilità sui grafici (scale, griglie, font, riga d'apertura)

### Note Tier 3
- Il waterfall è **solo frontend**: riusa i `losses[]` già calcolati dal debrief → resta in sync con le mini-lezioni.
- Nuovi canali: `yaw`, `rpm` in `_channels` (una riga each). Demo seed: marcia/RPM derivati dalla velocità (sawtooth + gradini) così le cambiate si vedono in `--demo`.
- Lo yaw è mostrato con il segno invertito (`_YAW_SIGN`) così in curva pulita segue lo sterzo; dove diverge = sotto/sovrasterzo.
- Verificato live: waterfall (Curva 1 −0.510s), grafici yaw (bianco+ambra) e RPM (linea giri + marker ▲▼), correzioni sterzo nel riepilogo; suite 413 verde.

## Aggiornamento 2026-07-30 — vista «Traiettoria» + leggibilità

Due lavori distinti nella stessa sessione, entrambi partiti da un giro di
schermate dei concorrenti (Track Titan, Garage61, MoTeC i2, Coach Dave Delta).

### 1. La vista «Traiettoria» (nuova scheda, fra Mappa e Settori)

Il Tier 2.5 (line-deviation) dava **metri col segno e nient'altro**: quale lato
sia il «+» dipende da come gira la curva, e quella conversione la faceva il
lettore a mente. La scheda nuova la fa lei.

- **Motore**: `src/accoach/trajectory.py` — funzioni pure sulle coordinate
  `car_x/car_z` (v3+) più le curve già rilevate da `track.detect_corners`.
  Niente nuova cattura, niente database per pista. Riusa `_menger_curvature`
  del rilevatore di curve (stessa geometria, o una curva è «tornante» di là e
  R=90 m di qua). Il segno è quello validato su Imola: **curvatura positiva =
  destra**, quindi `offset × verso della curva` = **dentro(+)/fuori(−)**.
- **Cosa misura per curva**: scarto in ingresso/apex/uscita, punto più largo,
  spostamento dell'apex **in metri lungo la pista** (non in posizione
  normalizzata, che non è lineare nella distanza), **raggio effettivamente
  percorso** contro quello del riferimento, metri di strada in più, vmin e
  velocità d'uscita. Più il totale sul giro.
- **Soglie dichiarate e motivate** (`_MIN_OFFSET_M` 0.8 m ≈ mezza vettura,
  `_MIN_APEX_SHIFT_M` 5 m perché un minimo di velocità è piatto per costruzione,
  `_MIN_EXTRA_M` 2 m ≈ 0.05 s a 150 km/h, raggio ±10% perché 5 m su un tornante
  e 5 m su un curvone non sono la stessa notizia). Sotto la soglia **non si
  scrive niente**: due giri identici non producono un solo tag.
- **Le etichette sono descrittive, non prescrittive** («apex 8 m prima», «1.4 m
  largo in uscita»). Il *perché* e il *cosa fare* restano del debrief, che ha il
  modello causale: due moduli che danno consigli sulla stessa curva prima o poi
  si contraddicono. Il testo sta in `trajectory.py` accanto ai numeri (come per
  il debrief), non in `i18n.js`.
- **API**: `/api/trajectory` (endpoint suo, non campi in più su `/api/analysis`:
  i ritagli per curva sono l'unica cosa che vuole il giro a piena risoluzione) +
  `fmt=csv` che scarica la tabella. ~24 KB di payload sul demo.
- **Frontend**: mappa della curva ingrandita con **la fascia fra le due linee**
  (lo scarto *è* la fascia), apex tuo e del riferimento, punti di frenata, barra
  di scala in metri; pannello dei fatti; grafico dello scarto sul giro; grafico
  di curvatura; tabella cliccabile con export CSV.
- **Il magnificatore ×1/×3/×5**: a scala vera una curva è larga 200 m e una buona
  traiettoria sta 1-2 m dal riferimento — pochi pixel. Lo scarto si può gonfiare,
  **ma il grafico lo dichiara a schermo** e la barra di scala continua a misurare
  terreno reale: un'esagerazione non dichiarata è solo un disegno sbagliato.

### 2. Leggibilità dei grafici esistenti

Il divario coi concorrenti qui non erano i dati ma **la scala**: i canvas
disegnavano una traccia e due etichette negli angoli, quindi si leggeva «è
alto», mai «quanto».

- `gridY()` — linee di riferimento orizzontali **con il valore**, disegnate
  dentro il riquadro su una pastiglia scura. Dentro, non in una colonna a
  sinistra: la x di ogni traccia, del mirino e dei due gestori di hover è
  `pos * w`, e una gutter avrebbe voluto dire riderivarla in otto punti.
  Applicata a delta (s), velocità (km/h), gas/freno (%), slip, scostamento (m),
  giri motore. Dove l'unità non dice niente al pilota (radianti) restano le sole
  linee.
- `gridX()` — tacche ogni 10% del giro, con le percentuali **solo sull'ultimo
  grafico di ogni pila** (ripetere l'asse sotto ogni traccia è rumore).
- **Font del brand anche sui canvas**: il canvas non eredita lo stack CSS, quindi
  ogni grafico disegnava nel font di sistema. I numeri vanno in mono per lo
  stesso motivo per cui ci vanno nel CSS.
- **Bug latente corretto**: `axisLabel` inchiodava la didascalia in basso a
  `y=145`, giusto per i grafici da 150px e sbagliato per tutti gli altri.
- **Riga d'apertura di «Confronto»**: la mini-mappa stava su una riga tutta sua,
  dove una pista disegnata in proporzioni vere ne riempiva un quinto. Ora è una
  scheda a fianco dei numeri: si guadagna quasi una schermata di grafici sopra
  la piega.
- `fixz()` — un valore che arrotonda a zero si stampa `0`, mai `-0.0`.

### Note Tier 2
- Nuovi canali serviti: `balance` (in `_channels`), `line_offset` e `tyres` per-punto (payload review), `corner_consistency` (progress).
- Il balance ribbon è reso come **mini-mappa nel tab Dinamica** (non un toggle sul tab Mappa) per non disturbare la legenda esistente della mappa.
- `_balance_at` importa le costanti da `coaching/balance.py` per restare in sync col coach live (sovrasterzo ha precedenza, soglia sterzo più bassa `_STEER_CATCH`).
- Verificato live su `--demo`: line-offset, gomme intra-giro, balance ribbon (blu sottosterzo) e consistenza per curva rendono con dati reali; suite 412 verde.
</content>
</invoke>
