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

> Aggiornata dopo: le schede oggi sono nove. Vedi in fondo gli aggiornamenti del
> 2026-07-30 (Traiettoria, asse in metri, layout) e del 2026-07-31 (Allenamento).

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
- `gridX()` — tacche lungo il giro, con le etichette **solo sull'ultimo
  grafico di ogni pila** (ripetere l'asse sotto ogni traccia è rumore).
  *(dal 2026-07-30 le tacche cadono su metri tondi invece che ogni 10% —
  vedi l'aggiornamento in fondo)*
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

---

## Aggiornamento 2026-07-30 (sera) — l'asse in metri, il «sei qui», la frase

Da uno screenshot di Track Titan: nel loro disegno della traiettoria il grafico
ha l'asse **in metri**, c'è una mini-mappa che dice dove sei, e una frase è
attaccata al disegno. Tre cose che **non dipendono dai bordi pista** (quelli
restano il filo aperto: la spline `fast_lane.ai` di AC è nello stesso sistema di
coordinate dei nostri giri, ma il blocco con le larghezze non è decodificato).

### 1. L'asse in metri, misurato e corroborato

`0.25 · 0.50 · 0.75` è un numero da convertire prima di poterci guidare. Adesso
i grafici scrivono `1000 m · 2000 m …`, e le tacche cadono su metri tondi invece
che su frazioni del giro.

- la conversione **non è `pos × lunghezza pista`**: sarebbe un'ipotesi due volte
  (il numero, e che la posizione avanzi linearmente con la distanza). È
  `trajectory.cumulative_distance()` sulle coordinate registrate — la stessa
  geometria con cui la scheda Traiettoria dice «hai percorso N m»;
- misurata al **rate pieno** e solo dopo assottigliata ai 600 punti del browser
  (`_pick_indices`, condiviso con `_downsample`): accumulare sui punti del
  grafico taglierebbe ogni curva in dieci corde;
- **il giro non è creduto sulla parola**: `_distance_channel()` confronta la
  distanza dalle coordinate con quella da velocità×tempo. Misurato sui 39 giri
  in archivio — i 30 sani stanno entro lo **0.1%**, i 6 del Nürburgring
  precedenti al fix delle coordinate AC1 dicono **167 m per un giro di 5 km
  (−96.7%)** e gli ACC di giugno non hanno coordinate (−100%). Tolleranza al 5%:
  cinquanta volte lo scarto osservato, e respinge comunque i rotti. Un giro
  respinto torna alle percentuali — **una scala sbagliata è peggio di una
  astratta**;
- ricaduta: la **demo** disegnava un circuito da 1.8 km e ci girava dentro a 255
  km/h per 100 s. Ora l'anello è lungo 6.3 km, cioè quanto dicono le sue stesse
  velocità: prima la barra della scala contraddiceva il tachimetro dello stesso
  giro.

### 2. La mini-mappa «sei qui» dentro lo zoom della curva

Il disegno della curva era l'unica figura della pagina **senza contesto**: due
tornanti della stessa pista fanno la stessa immagine. In basso a destra ora c'è
il giro intero, con il tratto acceso, un **anello** attorno alla curva (a quella
scala la curva è tre pixel: l'anello è ciò che l'occhio trova) e un punto —
dove sei col cursore, all'apex quando non stai puntando. Stessa proiezione
specchiata della mappa grande: tre figure dello stesso giro che litigano su
destra e sinistra sarebbero peggio di due che non esistono.

### 3. La frase attaccata al disegno

Il debrief quella frase la **scriveva già**; semplicemente stava su un'altra
scheda. Ora è in cima al disegno (`0.57 s · Frena più tardi`, e sotto la nota di
fase o l'effetto a catena), presa **alla lettera** dal payload e mai riderivata:
due moduli che scrivono della stessa curva è esattamente come finiscono per
contraddirsi. La curva che non è costata niente non dice niente — il silenzio è
a sua volta una lettura. L'aggancio è per **numero di curva** (`index`, aggiunto
alle `losses`): i nomi sono curati per pista e due possono somigliarsi.

### Verificato dal vivo (non solo in test)

Sui giri veri in archivio, non sulla demo: Monza legge **5775 m** (pista reale
5793 m, ed è la traiettoria percorsa, non la mezzeria); a Nürburgring l'unico
giro sano prende i metri e i **sei rotti tornano alle percentuali**; gli ACC di
Imola senza coordinate restano in percentuale. Nessun errore in console dopo aver
girato tutte le schede, in italiano e in inglese. Suite **1083** verde.

---

## Aggiornamento 2026-07-30 (tarda sera) — passata di layout, misurata

Quattro difetti **misurati** su uno schermo 2560×1271, non stimati a occhio.

### 1. Una larghezza sola (`--page` / `--gut`)

Le viste a scheda erano centrate a 780-900 px mentre i grafici si stiravano a
**2504 px**: due layout nella stessa app, e un delta alto 100 px lungo due metri
e mezzo. Ora il contenuto è dentro **1600 px** centrati.

Il gutter è `max(24px, calc((100% - var(--page)) / 2))` applicato a ogni fascia,
**non un wrapper**: così ogni fascia tiene il suo sfondo da bordo a bordo mentre
il contenuto si allinea. La percentuale si risolve sulla larghezza della fascia
(il body), quindi è a prova di scrollbar dove `100vw` non lo sarebbe — **ma per
la stessa ragione dentro una colonna stretta collassa a 24 px**: è per questo
che il gutter della riga d'apertura di Confronto lo paga `.hero`, non la
mini-mappa dentro di essa.

### 2. La fascia del giro, su ogni scheda

Giro · riferimento · gap · asfalto stavano **solo dentro il riepilogo di
Confronto**: la landing spiegava un giro senza mai dirti quale. Ora è un nastro
sotto le schede, e i tre numeri sono stati **tolti** dai riepiloghi di Confronto
e Settori (due posti che stampano lo stesso gap divergono il giorno in cui uno
dei due impara qualcosa). Il riepilogo di Confronto resta per ciò che riguarda
*il confronto* (costanza, nota sulle condizioni, differenza di setup) e si
nasconde quando non ha niente da dire.

### 3. Le viste corte

Misurate: «Il giro spiegato» 627 px su 1271, «Sessione» 636, «Settori» 518.

- **Giro spiegato**: da 1180 px in su è una schermata di *focus* — frase a
  sinistra, grafico a destra alto fino a 440 px, bottoni sotto la frase,
  il tutto centrato verticalmente. Sotto i 1180 px resta la pila di prima.
  Sotto la frase c'è la **mappa del giro colorata a delta** (la stessa funzione
  della scheda Mappa, così le due non possono litigare su come gira la pista) col
  **tratto del passo in evidenza**: la traccia accanto dice *cosa* è successo, il
  nome della curva nella scheda è un nome, non un posto. Due difetti visti a
  schermo e corretti subito: al passo panoramico la finestra è tutto il giro e
  accendeva l'intera pista (ora niente evidenza, e **la didascalia cambia** —
  altrimenti promette un tratto che non c'è), e la banda sopra la linea
  seppelliva i colori del delta (ora è disegnata **dietro**, con
  `destination-over`: viene fuori un alone, non una mano di vernice).
- **Sessione**: i giri e «cosa è cambiato» affiancati.
- **Settori**: sotto il giro ideale, **ogni giro settore per settore**
  (`per_lap` in `/api/sectors`), col migliore di ogni colonna in evidenza. Il
  giro ideale dichiarava un tempo che nessuno ha guidato; qui vedi di quali giri
  è fatto. Stessi span e stesso calcolo dell'ideale, così la tabella non può
  contraddire la riga sopra.

**Difetto trovato e corretto durante il lavoro**: `#view-flow { display: grid }`
batte per specificità `.hidden { display: none }` — la landing restava sopra
tutte le altre schede. Ora c'è un test che vieta a qualunque regola `#view-*` di
toccare `display` senza `:not(.hidden)`.

### 4. Ingegnere: il setup a colonne

16 righe su 29 finivano a 1189 px di 2560 (1315 px vuoti) e la pagina scorreva
per 2020 px. Ora `.setup-body` è una griglia `auto-fill` da 430 px: una colonna
sul portatile (identico a prima), due o tre sul monitor largo. I gruppi con le
righe per-ruota prendono tutta la riga **e al loro interno impaginano a loro
volta** le leve a valore singolo — è lì che stava la maggior parte del vuoto
(«Meccanica» da sola ne ha tre). Da 2020 a **1720 px**. Questa pagina **tiene la
larghezza piena** apposta: è uno strumento a due pannelli, non un testo.

### 5. Spiccioli

Ultima scheda e ultima auto/pista ricordate (validate prima dell'uso: una vista
salvata da una build vecchia non deve svuotare la pagina); titolo della finestra
`monza · 2:09.775 — HONE`, con la parte che distingue davanti; **1-9** scelgono
la scheda e **[ ]** scorrono i giri, scritti nei tooltip perché una scorciatoia
che nessuno trova non esiste.

Suite **1090** verde. Nessun errore in console girando tutte le schede, e
nessuno scorrimento orizzontale a 390 px su nessuna vista.

---

## Aggiornamento 2026-07-31 — la scheda «Allenamento»

**Il problema, detto dall'utente**: insight e consigli sono dappertutto, ma se
non mastichi telemetria difficilmente capisci *come* migliorare. «Se l'ideale
teorico è x, come mi devo allenare per arrivarci?»

È una critica giusta e misurabile sul nostro stesso codice. Tutto il resto
dell'app risponde a **cosa** e **perché**: il debrief nomina la curva e la
causa, le tendenze dicono quali si ripetono, `plan.py` ne fa un bersaglio in
secondi, la scala dei livelli dice che l'ideale teorico è otto decimi sotto il
tuo migliore. Nessuno faceva l'ultimo passo — quello che trasforma «perdi 0.31s
a curva 4, quasi tutto in ingresso» in **cosa fare al volante per venti giri**.
Chi legge telemetria lo fa da solo senza accorgersene; tutti gli altri leggono
una pagina di numeri corretti e rifanno lo stesso giro.

### Cosa fa

`coaching/training.py` + `GET /api/training` + scheda **Allenamento** (seconda,
subito dopo «Il giro spiegato»).

1. **Dove sono i tempi.** Miglior giro contro **ideale teorico**, e in quale
   settore sta il grosso del divario. L'ideale è il perno giusto attorno a cui
   organizzare l'allenamento proprio perché *non* è aspirazionale: l'hai già
   guidato a pezzi, quindi il divario non è bravura che ti manca, è ripetizione
   che non hai fatto — e su quello un esercizio può lavorare.
2. **Il programma.** Massimo tre passi (stesso tetto del flusso guidato, stessa
   ragione), **uno solo aperto**. L'ordine ha un motivo scritto sulla scheda: le
   curve che l'analisi a catena indica come *causa* di un'altra passano davanti,
   perché sistemare quella che passa il deficit ne sistema due.
3. **L'esercizio.** Una libreria scritta di sei esercizi. Quale ti tocca lo
   decide **la fase dominante** (`phases.py`) e solo dopo la categoria — vedi
   sotto. Dentro ci vanno i **tuoi** numeri.
4. **La prossima sessione**, in giri: riscaldamento, i giri di esercizio, giri
   liberi per vedere se è entrato quando smetti di pensarci.

### Le decisioni non ovvie

**La fase batte la categoria.** Dove dentro la curva è corso il cronometro è una
*misura*; la categoria è un'*etichetta* messa sul sintomo dominante. Una curva
marcata «porta più velocità in ingresso» che però perde il tempo in uscita
prende l'esercizio dell'uscita: allenare l'ingresso lì significherebbe allenare
l'etichetta invece del problema.

**I due numeri non si sommano, e la pagina lo dice.** Il divario dall'ideale è
misurato ricucendo i tuoi settori migliori; quello che perdi ogni giro nelle
curve è misurato sui giri recenti contro il tuo migliore. Si sovrappongono.
Sommarli conterebbe due volte lo stesso tempo, quindi non li sommiamo e
spieghiamo perché.

**Il piano trasloca, non si duplica.** «Il tuo piano» stava in Andamento. Due
pannelli sullo stesso piano sono due posti dove può contraddirsi, quindi ora un
obiettivo **è** un passo, con l'esercizio che lo chiude attaccato. Andamento
resta il quaderno dei conti e rimanda alla scheda.

**La soglia: 6 giri validi + una debolezza sistematica.** Sei giri ne lasciano
cinque da confrontare col riferimento, e una debolezza per chiamarsi tale deve
tornare in tre di quei cinque (`RECUR_FRAC`). Sotto quella soglia la scheda non
si apre e dice **quanti giri mancano** — mai un pannello vuoto, che si legge
come una funzione rotta. Sull'archivio reale (39 giri) si accende su 3 combo su
7; le altre dicono di quanto sono lontane.

**Una riga senza il suo numero non si stampa.** Mai «il tuo punto si sposta di
&nbsp;m»: se il dato manca, l'esercizio ha una riga in meno.

### Difetti trovati durante il lavoro (tutti sui dati veri o a schermo)

- **«+0 km/h» come obiettivo.** La riga della minima inseguiva uno scarto nullo.
  Ora sotto i 3 km/h (la ripetibilità della curva stessa) la riga sparisce.
- **Sottrazione sbagliata a schermo**: 80.4 contro 76.8 stampava «80», «77» e poi
  «+4». La differenza si calcola ora fra i numeri *stampati*.
- **Due passi dicevano entrambi «si comincia da qui»**: il «perché» è una
  questione di *posizione*, e veniva scritto prima che il passo di costanza
  prendesse il suo posto nella lista. Ora si scrive per ultimo.
- **La catena parlava dalla parte sbagliata**: la frase del debrief è scritta dal
  punto di vista della curva che *paga*, e sulla scheda della curva che *causa*
  si leggeva come se ereditasse da sé stessa. Ora si nomina la vittima.
- **«0.01s che hai già guidato, ma a pezzi»**: con l'ideale a 5 millesimi dal
  miglior giro la frase era ridicola e mandava ad allenare la ripetizione uno che
  già ripete. Ora c'è la frase opposta.
- **La scheda frenate buttata via a metà**: l'esercizio della staccata voleva
  velocità *e* metri, e i metri richiedono le coordinate — **tutti i giri ACC del
  nostro archivio leggono 0 m**. Ora stampa quello che c'è (velocità, marcia, e
  la dispersione in km/h invece che in metri).
- **`renderSession` dichiarata due volte in `app.js`**: l'ultima vince, in
  silenzio, e il piano di sessione non compariva — nessun errore in console,
  tutti i test verdi. Ora c'è un test che vieta due funzioni omonime.
- **Il pannello del blocco usava la classe `.empty`**, che è `display:none`: la
  scheda risultava completamente vuota. Proprio il fallimento che quel pannello
  esiste per evitare.
- **La stampa elencava i pannelli a mano**: una nona scheda si sarebbe stampata
  sotto la scheda frenate. Ora la regola è derivata dal prefisso dell'id.
- **Un piano accettato in inglese restava inglese**: su pagina italiana entrambi
  gli obiettivi leggevano «Time lost here». I numeri sono l'accordo e restano
  congelati; le etichette seguono la lingua della pagina (`category_words`).

Suite **1254** verde. Verificato a schermo su Imola/720S (piano proposto,
avviato, misurato) e a 390 px in iframe.

### Passata sul linguaggio (stessa giornata)

Rilettura richiesta: *il linguaggio deve essere comprensibile anche a un
neofita*. È il punto: questa è **la scheda per chi non legge telemetria**, e ci
era rimasto dentro il gergo di chi la legge. Contati sulle stringhe: `apex` in 7
punti, `stacchi/staccata` in 6, `la minima` in 7, `riferimento` in 6 — e
`riferimento` significava **due cose diverse** (il giro di confronto e un punto
che guardi fuori dal parabrezza).

Le tre regole adottate, scritte nel modulo perché non si perdano:

1. **Dove una parola comune non toglie niente, vince lei**: «il punto in cui
   inizi a frenare», non «la staccata».
2. **Un termine che il resto dell'app usa resta** (settore, apex, ideale
   teorico) — chi lo impara qui lo ritrova sulle altre schede — **ma si spiega
   dentro l'esercizio che lo usa**. È l'unità giusta: a schermo un esercizio
   solo è aperto, quindi una spiegazione ripetuta fra esercizi non è ripetizione
   per nessun lettore.
3. **Nessun termine viene introdotto per essere definito dopo.** «Ideale
   teorico» si **descrive e poi si nomina**: *«il tuo tratto migliore in ogni
   settore, messo insieme — è quello che qui si chiama ideale teorico»*.

Più: una riga d'apertura che dice cosa **è** questa scheda (le altre ti mostrano
qualcosa, questa ti chiede di andare a fare qualcosa), e il titolo generico
**«Tempo perso qui» non si stampa più** — su una scheda che porta già il nome
della curva, il motivo per cui è prima e un bersaglio in secondi, era
un'intestazione che non diceva niente, e la prima riga dell'esercizio lo dice
per bene.

Tre test statici lo tengono fermo: le parole abbandonate non rientrano, un
termine che resta è spiegato **nello stesso esercizio**, e il gergo dell'app è
definito **prima** di essere nominato (verificato sull'ordine dei caratteri
nella frase, non a occhio). Suite **1262**.
