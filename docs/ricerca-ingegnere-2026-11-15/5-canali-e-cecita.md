# 5 · Canali disponibili e cecità della diagnosi (McLaren 720S GT3 Evo, ACC)

Data: 2026-11-15. Sola lettura sull'archivio `%USERPROFILE%\Documents\ACCoach\laps` (il db non è stato aperto). Repo al commit `bc721d7`, nessun file modificato.

Convenzioni: **[M]** = misurato sui giri d'archivio con gli script di questa cartella; **[C]** = letto nel codice (file:riga); **[I]** = ipotesi o dato esterno non verificato qui.

Base dati: 211 giri della `mclaren_720s_gt3_evo` (tutti `valid`), 147 con `clean=True`, 64 con `clean=False`. «Giri puliti a passo» = puliti ed entro il 107% del migliore pulito della stessa pista: **127 giri** (Imola 54, Monza 32, Zolder 14, Brands Hatch 11, Red Bull Ring 8, Suzuka 3, Spa 3, Nürburgring 1, Bathurst 1). Tutti `dry_compound`.

Script (stessa cartella): `common.py`, `b_inventario.py`, `c_cecita.py`, `c2_unita_segni.py`, `d_segnali.py`, `d2_leve_note.py`, `e_stint.py`. Output grezzi: `out_b.txt`, `out_c.txt`, `out_c2.txt`, `out_d.txt`, `out_d2.txt`, `out_e.txt`.

---

## A. Inventario dei canali

### A1. Registrati per campione nei file giro (schema v11) [C]

Definizione: `src/accoach/recording/lap.py:124-144` (`SAMPLE_FIELDS`), dataclass `LapSample` `lap.py:401-424`, riempimento `lap.py:427-449`.

| Canale nel file | Origine shared memory | Unità | Note |
|---|---|---|---|
| `t_ms` | graphics `iCurrentTime` | ms dal via del giro | |
| `pos` | graphics `normalizedCarPosition` | 0..1 | arrotondato a 1e-5 |
| `speed_kmh` | physics `speedKmh` | km/h | |
| `throttle`, `brake` | `gas`, `brake` | 0..1 | |
| `steer_angle` | `steerAngle` | **frazione di corsa −1..1, + a sinistra** (non radianti) | vedi C3 |
| `gear`, `rpm` | `gear`, `rpms` | etichetta, giri/min | |
| `g_lat`, `g_long` | `accG[0]`, `accG[2]` | g | `accG[1]` (verticale) letto ma non registrato |
| `abs_active`, `tc_active` | `abs`, `tc` | dichiarati 0..1, **in pratica 0/1** | vedi B |
| `yaw_rate` | `localAngularVel[1]` | rad/s | segno opposto allo sterzo |
| `tyre_fl..rr` | `tyreCoreTemperature[4]` | °C (core) | |
| `car_x`, `car_z` | `carCoordinates[playerCarID]` | m | |
| `current_sector` | `currentSectorIndex` | indice | |
| `sr_fl..rr` | ACC `slipRatio[4]` nativo (`reader.py:412-439`) | adimensionale, <0 blocco, >0 pattinamento | |
| `press_fl..rr` | `wheelsPressure[4]` | psi | |
| `fuel` | `fuel` | litri | dal v11 |

**Frequenza.** L'acquisizione gira a 60 Hz (`telemetry/feed.py:52`), ma il registratore decima: tiene un campione ogni ≥0,2% di giro **oppure** ≥100 ms (`recording/recorder.py:45-46, 431-434`). **[M]** Sui 211 giri: intervallo mediano fra campioni **108 ms** (p5 100, p95 125), cioè **≈9,1 Hz**; 990 campioni per giro di mediana. È un limite reale per ogni segnale dinamico veloce (un controsterzo dura 2-5 campioni).

**Per giro (non per campione)** `lap.py:525-545`, scritti al traguardo in `recorder.py:582-590`: `clean`, `lost_at`, `air_temp`, `road_temp`, `grip`, `tyre_compound`, `tc_level`, `abs_level`, `engine_map`, `brake_bias`. Sono il valore **al passaggio sul traguardo**, non una traccia.

### A2. Letti dalla shared memory ma NON registrati [C]

Mappatura in `src/accoach/telemetry/reader.py:174-230`, campi in `telemetry/snapshot.py`.

| Campo snapshot | Riga reader / snapshot | Stato |
|---|---|---|
| `brake_temp[4]` (physics `brakeTemp`, `structs.py:94`) | reader 204 / snapshot 82 | letto, usato solo da `monitor.py:78`; **mai registrato** |
| `clutch` | reader 182 / snapshot 57 | non registrato |
| `accel_g[1]` (verticale) | reader 188 / snapshot 71 | non registrato |
| `wheel_slip[4]` (grezzo) | reader 190 / snapshot 73 | tolto dai file al v10 |
| `max_rpm` | reader 186 / snapshot 67 | non registrato |
| `tc_level`, `abs_level`, `engine_map`, `brake_bias` | reader 207-210 / snapshot 89-92 | solo per giro (valore al traguardo) |
| `air_temp`, `road_temp` | reader 221-222 / snapshot 117-118 | solo per giro |
| `surface_grip` | reader 223, 284-308 | solo per giro, **sempre 0 su ACC** |
| `tyres_out` | reader 220 | inerte su ACC |
| `lap_valid`, `penalty`, `in_pit`, `in_pit_lane` | reader 217, 225-228 | usati dal registratore, non salvati per campione |
| `last_lap_ms`, `best_lap_ms`, `completed_laps`, `sector_count` | reader 212-214, 219 | non per campione |

### A3. Campi utili a un ingegnere che NON leggiamo affatto [C]

Dichiarati nello struct (`src/accoach/telemetry/structs.py`) ma mai copiati nello snapshot:

| Campo | structs.py riga | A cosa servirebbe |
|---|---|---|
| `tyreTempI`, `tyreTempM`, `tyreTempO` [4] | 96-98 | campanatura e pressione (profilo interno/centro/esterno) |
| `suspensionTravel[4]` | 62 | rollio, beccheggio, fondo corsa, altezze dinamiche |
| `rideHeight[2]` | 76 | rake dinamico |
| `slipAngle[4]` | 118 | **angolo di deriva per ruota: la misura diretta di sotto/sovrasterzo** |
| `localVelocity[3]` | 104 | angolo di assetto β = atan(vx/vz): sovrasterzo senza passare dallo sterzo |
| `velocity[3]`, `heading`, `pitch`, `roll` | 52, 65-67 | idem, più rollio/beccheggio |
| `localAngularVel[0]`, `[2]` | 82 | velocità di rollio e beccheggio (leggiamo solo `[1]`) |
| `mz[4]`, `fx[4]`, `fy[4]` | 114-116 | forze e momento autoallineante per ruota |
| `wheelAngularSpeed[4]` | 57 | letto solo su AC per derivare lo slip |
| `tyreWear[4]`, `tyreDirtyLevel[4]`, `camberRAD[4]`, `wheelLoad[4]` | 55, 58, 59, 61 | usura, sporco, camber dinamico, carico |
| `carDamage[5]` | 69 | un giro con danno non è confrontabile |
| `finalFF` | 83 | forza al volante |
| `airDensity`, `turboBoost`, `pitLimiterOn` | 77, 79, 71 | |
| `windSpeed`, `windDirection` (graphics) | 159-160 | vento |
| `TCCut` (graphics) | 170 | secondo parametro TC |
| `distanceTraveled`, `sessionTimeLeft`, `flag` (graphics) | 139-140, 153 | |
| `trackSPlineLength`, `maxFuel`, `aidStability` ecc. (static) | 249, 228, 239 | lunghezza pista per convertire `pos` in metri |

**Non dichiarati nemmeno nello struct** (la pagina physics si ferma a `slipAngle`, `structs.py:118`; la graphics salta 120 byte opachi `_acc_tail`, `structs.py:193`, e si ferma a `isValidLap`, riga 206). **[I]** Secondo la documentazione dell'SDK di ACC, citata a memoria e da verificare dal vivo, lì stanno: in coda a physics `tcInAction`/`absInAction`, `suspensionDamage`, `tyreTemp` (superficie), `waterTemp`, `brakePressure[4]`, `padLife[4]`, `discLife[4]`; in graphics `fuelXLap`, `usedFuel`, `rainTyres`, `trackStatus`/`trackGripStatus`, `rainIntensity` (+10/+30 min), `currentTyreSet`, `Clock`. Il commento in `reader.py:295-297` conferma che `trackGripStatus` «sta più giù, in una coda che non dichiariamo ancora».

**Avvertenza [I]:** la stessa documentazione marca come «non usati in ACC» `wheelLoad`, `tyreWear`, `tyreDirtyLevel`, `camberRAD`, `rideHeight`, `cgHeight` e, mi risulta, anche `tyreTempI/M/O`. Dichiarato non vuol dire riempito: questo progetto ci è già cascato con `numberOfTyresOut`, `surfaceGrip` e `tyreRadius`. Ogni campo della tabella va misurato una volta dal vivo prima di costruirci sopra. Offline non si può verificare.

---

## B. I canali registrati sono davvero popolati? [M]

211 giri, 218 448 campioni (`out_b.txt`).

| Canale | min | p1 | mediana | p99 | max | quota zeri | giri tutti a zero |
|---|---|---|---|---|---|---|---|
| speed_kmh | 0 | 1,4 | 157,3 | 259,2 | 278,9 | 0,1% | 0 |
| throttle | 0 | 0 | 0,984 | 1 | 1 | 21,7% | 0 |
| brake | 0 | 0 | 0 | 1 | 1 | 84,2% | 0 |
| steer_angle | −0,949 | −0,489 | 0,001 | 0,431 | 0,935 | 2,5% | 0 |
| g_lat | −4,08 | −1,81 | −0,01 | 1,76 | 5,98 | 1,2% | 0 |
| g_long | −4,57 | −1,85 | 0,20 | 0,78 | 1,67 | 0,9% | 0 |
| yaw_rate (rad/s) | −1,60 | −0,66 | −0,003 | 0,67 | 3,90 | 0,6% | 0 |
| abs_active | 0 | 0 | 0 | 1 | 1 | 96,4% | 2 |
| tc_active | 0 | 0 | 0 | 1 | 1 | 90,2% | 2 |
| tyre_fl / fr (°C) | 62,9 / 61,8 | 65,5 / 64,1 | 83,1 / 82,3 | 91,1 / 90,7 | 97,2 / 93,4 | 0% | 0 |
| tyre_rl / rr (°C) | 63,5 / 62,1 | 66,3 / 64,9 | 86,6 / 83,8 | 94,8 / 95,9 | 102,0 / 98,0 | 0% | 0 |
| press_fl / fr (psi) | 23,72 / 23,62 | 24,13 / 23,99 | 26,00 / 25,99 | 28,55 / 28,45 | 28,75 / 28,57 | 0% | 0 |
| press_rl / rr (psi) | 23,88 / 23,74 | 24,08 / 24,14 | 26,23 / 25,97 | 27,61 / 27,35 | 27,82 / 27,77 | 0% | 0 |
| sr_fl / fr | −1,00 | −0,078 | −0,001 | 0,002 | 1,01 / 1,35 | 19,9% / 19,5% | 8 |
| sr_rl / rr | −8,8 / −10,9 | −0,056 / −0,054 | 0,018 / 0,019 | 0,090 / 0,085 | 54,8 / 16,1 | 6,6% / 6,5% | 8 |
| fuel (L) | 0 | 0 | 50,6 | 62 | 62 | 4,7% | 10 |
| rpm | −178 | 1877 | 6456 | 7610 | 8109 | 0% | 0 |

Fatti da tenere presenti:

- **`abs_active` e `tc_active` sono binari**: i soli valori presenti sono 0 e 1 (2 valori distinti su 218 448 campioni). Sono un flag, non un'intensità. ABS acceso nel 3,6% dei campioni, TC nel 9,8%.
- **Slip ratio**: vivo su 203 giri; a zero sugli 8 giri del 18/07 (prima della correzione del 19/07). Le code (54,8; −10,9) sono artefatti a bassa velocità: usare i percentili, mai i massimi.
- **Benzina**: a zero sui 10 giri pre-v11.
- **Temperature gomme**: solo il core, popolato sempre. I/M/O, superficie, freni: non registrati.
- **Pressioni**: popolate sempre, risoluzione 0,01 psi.
- **Sospensioni, altezze, temperature freni, vento, stato pista, pioggia**: assenti dai file.
- **`grip`**: 0,0 su 211 giri su 211. Canale morto.
- **Aria / pista (per giro)**: aria 23,0-30,8 °C (10 valori distinti), pista 23,0-39,3 °C. Tolta Bathurst (23/23), l'aria sta in 29,2-30,8 e la pista in 34,3-39,3: quasi costanti, perché sono le condizioni che il pilota imposta. Dentro una serata la pista sale di circa 1 °C (37,7→38,7 nel log dell'Ingegnere).
- **Aiuti per giro**: `tc_level` 3/4/5/6, `abs_level` 0/2/3/4/5/6, `brake_bias` 0,64/0,75 e altri; −1 sui 10 giri pre-v9.

---

## C. Perché la diagnosi è cieca

### C1. Il fatto, riprodotto [M]

Soglie in vigore per la 720S (`out_c.txt`): `_STEER_HARD` 0,15 · `_STEER_CATCH` 0,04 · `_YAW_LOOSE` 0,30 rad/s · `_MIN_SPEED_KMH` 60 · `yaw_baseline` GT3 1,95 × `UNDERSTEER_FRAC` 0,45 = **soglia di sottosterzo 0,8775** (`coaching/tuning.py:61-63, 106`; `coaching/balance.py:48, 58-70`) · `_PRESENCE` 0,15 (`coaching/diagnosis.py:44`) · `_SYMPTOM_THRESH` 0,30 e `_MIN_CORNERS` 3 (`engineer/core.py:337-338`).

| Pista | giri puliti a passo | `symptom_scores` vuoto |
|---|---|---|
| Imola | 54 | 54 |
| Monza | 32 | 31 |
| Zolder | 14 | 13 |
| Brands Hatch | 11 | 10 |
| Red Bull Ring | 8 | 8 |
| Suzuka | 3 | 2 |
| Spa | 3 | 3 |
| Nürburgring, Bathurst | 1 + 1 | 2 |
| **Totale** | **127** | **123 (96,9%)** |

- Imola 8 e 14 novembre, tutti i 42 giri (puliti e no): **40 con `symptom_scores` vuoto**. Il numero di partenza è confermato.
- Coppie (giro, sintomo) che superano **insieme** 0,30 e 3 curve, cioè il minimo perché l'Ingegnere agisca: **0 su 127 giri**.
- I 6 sintomi comparsi in tutto: 3 di sottosterzo in un solo giro di Monza, 3 di sovrasterzo (uno a Suzuka, uno a Brands Hatch, uno a Zolder), ognuno in una sola curva.

### C2. Di quanto manca [M]

2455 coppie curva×fase su 127 giri.

**Per campione:**

| Fase | campioni | campioni per fase (mediana) | \|sterzo\| p10/p50/p90 | quota campioni che passano `_STEER_HARD` e 60 km/h | rapporto yaw/sterzo p1/p5/p25/p50/p75 | campioni «hard» sotto 0,8775 | idem su tutti i campioni della fase |
|---|---|---|---|---|---|---|---|
| ingresso | 7 750 | 9 | 0,001 / 0,011 / 0,094 | **2,2%** | 0,85 / 1,27 / 1,77 / 2,13 / 2,44 | 1,18% | 0,03% |
| apex | 45 301 | 44 | 0,029 / 0,145 / 0,358 | 47,3% | 0,63 / 1,06 / 1,55 / 1,87 / 2,20 | 2,50% | 1,18% |
| uscita | 12 737 | 20 | 0,055 / 0,101 / 0,233 | 24,1% | 0,54 / 0,96 / 1,45 / 1,83 / 2,18 | 3,62% | 0,87% |

Su tutte le fasi (24 682 campioni «hard»): rapporto mediano **1,87**, p5 1,05, p1 0,62. Sotto soglia il **2,6%**.

**Per curva×fase** (l'intensità che il codice confronta con 0,15 e 0,30):

| Fase | n | sottosterzo p50 | p90 | p99 | max | ≥0,15 | ≥0,30 | sovrasterzo p99 | max | ≥0,15 | ≥0,30 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ingresso | 777 | 0 | 0 | 0 | 0,018 | 0% | 0% | 0 | 0 | 0% | 0% |
| apex | 1119 | 0 | 0,005 | 0,039 | 0,310 | 0,36% | 0,09% | 0,044 | 0,242 | 0,09% | 0% |
| uscita | 559 | 0 | 0 | 0,036 | 0,250 | 0,36% | 0% | 0,026 | 0,181 | 0,36% | 0% |
| tutte | 2455 | 0 | 0 | 0,032 | 0,310 | **0,24%** | **0,04%** | 0,019 | 0,242 | **0,12%** | **0%** |

Lettura: all'apex il 99° percentile dell'intensità di sottosterzo è 0,039. Per arrivare a `_PRESENCE` manca un fattore **3,8 sopra il 99° percentile** (30 sopra il 90°). A `_SYMPTOM_THRESH` è arrivata una sola curva×fase su 2455. Il sovrasterzo non ha mai toccato 0,30.

**Spostare la soglia non basta:**

| Soglia sul rapporto | intensità p90 | curve×fase ≥0,15 | ≥0,30 |
|---|---|---|---|
| 0,8775 (oggi) | 0,000 | 0,24% | 0,04% |
| 1,25 | 0,014 | 0,53% | 0,08% |
| 1,50 | 0,033 | 0,98% | 0,20% |
| 2,00 (sopra la mediana) | 0,102 | 4,52% | 0,61% |
| 3,00 | 0,253 | 27,2% | 5,34% |

Anche mettendo la soglia sopra il valore normale dell'auto, il 95% delle curve resta sotto 0,15. Il limite è nella forma della misura, non nel numero.

### C3. Unità e segno [M]

`out_c2.txt`, 123 841 campioni a v ≥ 60 km/h, di cui 46 173 in curva (|g_lat| > 0,8).

- **`yaw_rate` è in rad/s**: contro 9,81·g_lat/v la pendenza è **0,996** (r 0,907 in curva; 0,997 e r 0,980 su tutti i campioni). Contro la velocità di rotazione della traiettoria ricavata da `car_x`/`car_z`: pendenza 1,012 (r 0,74, più rumorosa a 9 Hz).
- **Segno**: sterzo e yaw hanno segno opposto nel **99,1%** dei campioni in curva; yaw e g_lat concordi nel 99,9%. `_YAW_SIGN = −1` (`balance.py:54`), tarato su AC, è giusto anche su ACC.
- **`steer_angle` non è in radianti**: è la frazione di corsa. Massimo per giro: mediana 0,59, p95 0,81, massimo assoluto 0,949. I commenti «rad» accanto a `_STEER_HARD`, `_STEER_CATCH` (`balance.py:63, 69`) e in `track.py:36` sono sbagliati come unità; i valori vengono applicati alla frazione.
- **Rapporto di sterzo stimato**: dal fit di `sterzo·v/yaw = a + b·v²` sulle mediane di 10 fasce di velocità (31 020 campioni quasi stazionari) escono **a = 10,45** e **b = 0,00503**. Con passo 2,67 m **[I, dato di scheda non misurato]**: fondo scala ≈ **0,256 rad = 14,6° alle ruote**, gradiente di sottosterzo apparente ≈ **0,72°/g**. **Riserva**: l'auto è quasi sempre al limite (g_lat mediano 0,9-1,4 in ogni fascia), quindi il fit mescola cinematica, non linearità delle gomme e carico aerodinamico; `a` è solido come numero empirico, la conversione in gradi lo è meno. Quindi `_STEER_HARD` = 0,15 vale ≈2,2° alle ruote.

### C4. Le cause, in ordine di peso

1. **La regola è nata come allarme dal vivo per l'evento raro ed è riusata come media di fase.** [C+M] `UNDERSTEER_FRAC` 0,45 è scelto per stare «sul peggior ~5% dei campioni in curva» (`tuning.py:103-105`). Sui dati cade sul peggior 2,6%. Poi `corner_symptoms` fa la **media su tutti i campioni della fase** (`diagnosis.py:205`) e chiede ≥0,15. Con il 47% dei campioni d'apex ammissibili, per fare 0,15 quelli ammissibili dovrebbero avere un deficit medio di 0,32, cioè un rapporto medio ≈0,60: **tutta la fase al 1° percentile** (p1 = 0,62). Per 0,30 servirebbe un rapporto medio ≈0,32, cioè un'auto che ruota al 17% del normale per tutto l'apex.
2. **La baseline non è tarata male.** [M] `yaw_baseline` GT3 = 1,95 (misurata su AC, `tuning.py:20-23`); qui la mediana è 1,87. L'ipotesi «soglie tarate su un'altra auto» è **smentita** per la baseline. Sbagliato è l'uso: 45% del normale è uno stato che un pilota al limite con una GT3 non tiene per una fase intera.
3. **La fase d'ingresso è cieca per costruzione.** [C+M] Ingresso = prima di `apex − 0,02` **e** freno ≥ 0,15 (`diagnosis.py:68`). Lì si frena dritti: |sterzo| mediano 0,011, e solo il **2,2%** dei campioni passa `_STEER_HARD`. Massimo di intensità mai visto: 0,018. I sintomi «ingresso» non possono scattare; la frenata in appoggio cade quasi tutta nella banda d'apex.
4. **La banda d'apex è larga e diluisce.** [C+M] ±0,02 di giro (`diagnosis.py:38`) a Imola sono ±98 m: 44 campioni di mediana (≈4,8 s), di cui metà a sterzo quasi dritto che entrano nel denominatore con zero.
5. **Il rapporto yaw/sterzo dipende dalla velocità per fisica, e la soglia è una sola.** [M]

   | Fascia km/h | campioni (sterzo ≥0,15) | p5 | mediana | p95 | 0,8775 in % della mediana |
   |---|---|---|---|---|---|
   | 60-80 | 2962 | 0,93 | 1,60 | 2,32 | 55% |
   | 80-100 | 6944 | 1,03 | 1,83 | 2,56 | 48% |
   | 100-120 | 5823 | 1,14 | 2,04 | 2,81 | 43% |
   | 120-150 | 7420 | 1,15 | 1,97 | 2,77 | 44% |
   | 150-180 | 1735 | 0,90 | 1,87 | 2,78 | 47% |
   | 180-220 | 326 | 0,95 | 1,74 | 2,50 | 50% |
   | 220-280 | 175 | 0,31 | 1,29 | 2,20 | 68% |

   Per scendere sotto soglia servirebbe da 1,8 a 2,3 volte lo sterzo normale. I tre «sottosterzi» di Monza nascono dalla coda veloce: alla Curva Grande il rapporto mediano è 0,42 con il 2% dei campioni ammissibili, cioè un artefatto dell'alta velocità, non un sintomo.
6. **Gli aiuti spostano il sintomo su un altro canale.** [M] Controsterzo (segno invertito, |sterzo| ≥ 0,04): **0,26%** dei campioni; con anche |yaw| ≥ 0,30: **0,078%**. Intanto il TC è acceso nel 62% dei campioni d'uscita delle curve lente di Imola a TC 6 (D2) e l'ABS nel 30-44% dei campioni di frenata. Che il TC *impedisca* la sbandata è l'interpretazione coerente coi dati [I]; misurato è che il controsterzo quasi non esiste e l'intervento del TC sì.
7. **9 Hz.** [M] Un evento da 0,3 s sono 3 campioni: pesa poco su una media di 44.

---

## D. Segnali alternativi già nei dati [M]

Metodo (`d_segnali.py`): le curve sono quelle del giro pulito più veloce di ogni pista, applicate a tutti i giri. Per ogni metrica: **SD intra** = deviazione standard fra giri sulla stessa curva (mediana sulle curve); **CV intra** = SD/|media|; **ICC** = varianza fra curve / (fra curve + intra). ICC vicino a 1 = la metrica distingue le curve più di quanto balli da un giro all'altro.

Definizioni: `UA` = angolo di sottosterzo = k·(sterzo verso la curva − 10,45·yaw/v), in gradi alle ruote con k = 0,256 [I per la scala]. `UA_mid` sui campioni con g laterale ≥ 80% del picco della curva; `UA_exit` in uscita con gas ≥ 0,2 e ancora ≥ 0,5 g; `UA_trail` con freno ≥ 0,10 e ≥ 0,5 g. `bdot` = yaw − ay/v (gradi/s; >0 = l'auto ruota più di quanto curva). `g95` = 95° percentile di |g_lat| nella curva. `tc_exit` = quota di campioni d'uscita con TC acceso. `abs_entry` = quota di campioni di frenata con ABS acceso. `sr_rear_exit` = slip ratio posteriore massimo fra le due ruote, in uscita.

### D1. Stabilità e discriminazione fra curve

| Metrica | Imola (54 giri, 10 curve) CV · ICC | Monza (32, 7) | Zolder (14, 9) | Brands (11, 10) | RBR (8, 8) |
|---|---|---|---|---|---|
| velocità minima | 4,8% · 0,99 | 5,3% · 0,89 | 5,1% · 0,98 | 5,9% · 0,91 | 4,2% · 0,98 |
| g95 | 5,5% · 0,87 | 8,6% · 0,49 | 4,6% · 0,67 | 7,5% · 0,24 | 5,6% · 0,67 |
| **UA_mid** | **41% · 0,11** | **67% · 0,06** | 20% · 0,41 | 47% · 0,34 | 39% · 0,52 |
| UA_exit | 57% · 0,21 | 59% · 0,35 | 23% · 0,71 | 69% · 0,17 | 64% · 0,50 |
| UA_trail | 77% · 0,36 | 55% · 0,12 | 51% · 0,64 | 159% · 0,24 | 56% · 0,47 |
| rapporto yaw/sterzo a centro curva | 11% · 0,45 | 12% · 0,60 | 6% · 0,79 | 8% · 0,64 | 5% · 0,65 |
| bdot uscita p95 | 36% · 0,31 | 66% · 0,31 | 23% · 0,28 | 46% · 0,12 | 35% · 0,15 |
| bdot centro curva (media) | 186% · 0,33 | 108% · 0,34 | 92% · 0,36 | 300% · 0,11 | 226% · 0,27 |
| **tc_exit** | 71% · 0,53 | 33% · 0,76 | 19% · 0,86 | 94% · 0,33 | 23% · 0,70 |
| abs_entry | 57% · 0,44 | 86% · 0,21 | 61% · 0,32 | 144% · 0,53 | 49% · 0,51 |
| **sr_rear_exit (media)** | 41% · 0,37 | 11% · 0,88 | 8% · 0,85 | 15% · 0,66 | 6% · 0,88 |
| sr_rear_exit p95 | 45% · 0,41 | 20% · 0,70 | 12% · 0,48 | 22% · 0,46 | 11% · 0,69 |
| sr anteriore minimo in frenata | 45% · 0,01 | 13% · 0,46 | 14% · 0,54 | 21% · 0,26 | 13% · 0,54 |
| quota di controsterzo | 224% · 0,08 | 424% · 0,03 | — · 0,13 | 230% · 0,07 | — · 0,22 |

I numeri di Imola per `tc_exit` e slip sono inquinati da due cose scoperte dopo: i 7 giri di luglio con slip a zero, e tre livelli di TC mescolati. A leva ferma migliorano molto (D2).

### D2. Rispondono a una leva nota? [M]

Imola, giri puliti a passo, metriche mediate sulle 7 curve con apex <140 km/h (`out_d2.txt`):

| TC registrato | giri (date) | tc_exit | sr_rear_exit media | sr p95 | bdot uscita p95 | UA_exit | UA_mid | T ant−post °C | tempo giro s |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 15 (3) | 0,154 ± 0,076 | 0,062 ± 0,006 | 0,099 ± 0,014 | 4,80 ± 1,07 | 0,84 ± 0,35 | 1,00 ± 0,30 | −6,8 ± 1,2 | 106,54 ± 0,90 |
| 4 | 7 (2) | 0,274 ± 0,066 | 0,065 ± 0,005 | 0,104 ± 0,009 | 5,59 ± 1,29 | 1,08 ± 0,42 | 1,32 ± 0,30 | −6,5 ± 1,5 | 106,20 ± 0,96 |
| 6 | 25 (8) | 0,618 ± 0,046 | 0,057 ± 0,003 | 0,084 ± 0,006 | 4,26 ± 0,63 | 0,64 ± 0,37 | 0,75 ± 0,25 | −1,2 ± 0,6 | 108,10 ± 1,31 |

**Riserva importante:** TC 3/4 e TC 6 non differiscono solo per il TC. I giri a TC 3/4 hanno anche ABS 4 (contro 6), ripartizione 0,64 (contro 0,75) e pressioni anteriori più alte (27,4 contro 25,9 psi l'8/11). Sono **due configurazioni**, non una leva isolata. Quello che si può dire è che i segnali le separano; a quale leva attribuirlo no.

Nella stessa serata (8/11): TC 3 (11 giri) contro TC 6 (3 giri): `tc_exit` 0,136 ± 0,064 contro 0,604 ± 0,009; T ant−post −6,8 ± 1,3 contro −1,7 ± 0,2 °C; UA_mid 1,08 ± 0,28 contro 0,74 ± 0,04. Il 14/11 uguale: `tc_exit` 0,22 / 0,32 / 0,62 per TC 3 / 4 / 6; T ant−post −6,7 / −8,0 / −1,5.

**A leva ferma** (Imola, solo TC 6, 25 giri su 8 date):

| Metrica | SD fra curve | SD intra | CV intra | ICC | SD fra giri della media sulle 7 curve lente | differenza minima rilevabile con 3+3 giri |
|---|---|---|---|---|---|---|
| tc_exit | 0,339 | 0,085 | 23,5% | **0,91** | 0,046 (media 0,618) | 0,106 |
| sr_rear_exit media | 0,016 | 0,003 | 6,5% | **0,90** | 0,003 (media 0,057) | 0,006 |
| sr_rear_exit p95 | 0,026 | 0,011 | 13,4% | 0,76 | — | — |
| g95 | 0,254 | 0,088 | 5,4% | 0,85 | 0,053 g (media 1,71) | 0,12 g |
| velocità minima | 54,7 | 5,2 km/h | 4,7% | 0,99 | — | — |
| abs_entry | 0,178 | 0,186 | 46,5% | 0,48 | — | — |
| UA_mid | 0,157 | 0,177 | 32,2% | 0,14 | 0,25° (media 0,75°) | 0,57° |
| UA_exit | 0,264 | 0,360 | 53,4% | 0,13 | 0,37° (media 0,64°) | 0,85° |
| bdot uscita p95 | 1,23 | 1,54 | 33,0% | 0,33 | 0,63°/s (media 4,26) | 1,43°/s |

(«Rilevabile» = 2,8·SD·√(2/n), potenza ≈80% al 5%.)

### D3. Verdetto per segnale

- **Angolo di sottosterzo: non regge, così com'è.** CV 32-67% sulle piste con più giri, ICC 0,06-0,14 a Imola e Monza. Con 3 giri per finestra si vede solo una differenza ≥0,57°, contro un valore medio di 0,75°. Va un po' meglio dove i giri sono pochi e di una sola serata (Zolder 20%, ICC 0,41), il che indica che parte del rumore è fra serate. Vede la differenza fra le due configurazioni (0,75° contro 1,0-1,3°), ma a 1-1,5 SD. Cause probabili [I]: 9 Hz, auto sempre al limite, traiettoria che cambia.
- **Yaw contro ay/v: non regge.** A centro curva la media è 0,2°/s con SD 0,3 (CV 92-300%); il picco in uscita ha CV 23-66% e ICC 0,12-0,33.
- **Picco di g laterale e velocità minima: stabili, ma misurano la prestazione, non il verso del bilanciamento.** g95 CV 5-9%; velocità minima CV 4-6%, ICC 0,89-0,99. A Imola la velocità minima media correla col tempo sul giro ρ = −0,82 (54 giri), g95 ρ = −0,61. Risoluzione di g95 con 3+3 giri: 0,12 g, che è grande.
- **Quota di TC in uscita: il più promettente.** A leva ferma ICC 0,91; SD per giro 0,046 su 0,618; separa le due configurazioni di 5-10 SD. Va letto per livello di TC.
- **Slip posteriore medio in uscita: stabile.** CV 6-11% (Monza, Zolder, RBR, Imola a TC 6), ICC 0,85-0,90. Ma l'escursione fra configurazioni è piccola (0,057 contro 0,062-0,065), pari alla risoluzione di 3+3 giri (0,006).
- **Quota di ABS in frenata: rumorosa.** CV 47-144%, ICC 0,2-0,5. Distingue ABS 4 da ABS 6 a Imola (0,32 ± 0,10 contro 0,44 ± 0,09, 22 e 25 giri) solo in media su molti giri.
- **Slip anteriore minimo in frenata: non discrimina.** −0,087 con entrambi i livelli di ABS.
- **Controsterzo: troppo raro** (0,2-0,8% dei campioni in appoggio).

### D4. Gomme: temperature e pressioni [M] (`out_e.txt`)

**Differenze di temperatura core, per giro (giri puliti):**

| Pista | giri | T ant−post | T sin−des | P ant−post psi | SD entro stint di (ant−post) dal 4° giro |
|---|---|---|---|---|---|
| Imola | 55 | −3,9 ± 2,9 | −4,0 ± 0,6 | +0,06 ± 0,45 | 0,40 (4 stint) |
| Monza | 43 | −3,8 ± 1,1 | +5,6 ± 1,3 | −0,29 ± 0,43 | 0,45 (2) |
| Zolder | 16 | −1,1 ± 1,2 | +4,9 ± 1,1 | −0,05 ± 0,22 | 1,21 (2) |
| Brands Hatch | 16 | −2,1 ± 1,4 | +6,1 ± 2,9 | +0,18 ± 0,59 | 0,36 (2) |
| Red Bull Ring | 8 | −0,2 ± 0,3 | +2,4 ± 0,5 | −0,10 ± 0,06 | 0,31 (1) |

- **Sin−des** segue il verso della pista (Imola antioraria −4,0; le altre +2,4…+6,1) ed è stabile (±0,5-1,3 °C): descrive il tracciato, non l'assetto.
- **Ant−post** è stabile dentro lo stint (SD 0,3-0,45 °C dal 4° giro; Zolder 1,2) e si muove molto fra configurazioni: a Imola da −0,4 a −5,7 °C a seconda della serata; −1,2 ± 0,6 a TC 6 contro −6,8 ± 1,2 a TC 3. Correlazione per giro con `tc_exit`: ρ = +0,83 (54 giri). Stessa riserva di D2: le configurazioni differiscono per più leve.

**Deriva delle pressioni** (11 stint di almeno 6 giri; il «giro 1» è il primo registrato, quindi dopo il giro d'uscita):

| Giro registrato | stint | P ant | P post | ΔP ant dal giro prima (mediana; p10…p90) | ΔP post | T ant | T post |
|---|---|---|---|---|---|---|---|
| 1 | 11 | 26,23 | 26,01 | — | — | 79,7 | 83,2 |
| 2 | 11 | 26,41 | 26,18 | **+0,20** (+0,08…+0,26) | **+0,15** (+0,10…+0,28) | 81,6 | 85,0 |
| 3 | 11 | 26,45 | 26,25 | +0,04 (−0,03…+0,13) | +0,05 (0,00…+0,25) | 82,2 | 86,0 |
| 4 | 11 | 26,36 | 26,19 | −0,03 (−0,08…+0,09) | +0,02 (−0,06…+0,08) | 81,4 | 85,4 |
| 5 | 11 | 26,41 | 26,22 | +0,01 (−0,09…+0,15) | −0,01 (−0,16…+0,15) | 82,0 | 85,8 |
| 6 | 11 | 26,49 | 26,26 | +0,03 (−0,03…+0,30) | +0,02 (−0,04…+0,28) | 82,8 | 86,2 |
| 7 | 6 | 26,59 | 26,36 | +0,07 | +0,03 | 83,9 | 87,7 |
| 8 | 3 | 26,34 | 26,46 | −0,01 | 0,00 | 83,1 | 86,7 |

- Si stabilizzano al **2° giro registrato di mediana** (p75: 3° davanti, 2°-3° dietro), cioè al 3°-4° giro dall'uscita dai box. «Stabile» = entro 0,10 psi dalla media dei giri successivi e passi <0,15. Non si stabilizzano mai in 1 stint su 11 davanti e in 3 su 11 dietro.
- Deriva: **+0,20 psi/giro davanti e +0,15 dietro fra 1° e 2° giro, +0,04/+0,05 fra 2° e 3°, poi entro ±0,1**. Dal primo all'ultimo giro: +0,26 davanti, +0,24 dietro (mediane).
- A regime: SD della pressione media fra giri dal 5° in poi 0,04 psi (solo 3 stint di almeno 8 giri). Dentro un giro la pressione oscilla di 0,15 psi (p95−p5).

---

## E. Rumore del tempo sul giro [M] (`out_e.txt`)

Stint = giri consecutivi, stessa pista, benzina che non risale di più di 0,5 L, nessun buco di oltre 20 s fra un giro e il successivo. Sui 211 giri escono **52 stint**: 8 da un giro, 11 da tre, 15 da quattro, **11 da sei o più**, il più lungo da 12. Consumo misurato: Imola 2,82 L/giro, Monza 3,11, Zolder 2,35, Red Bull Ring 2,51, Brands Hatch 1,63.

Stint con almeno 4 giri puliti a passo (entro 5% della mediana dello stint): **13 stint, 60 giri**.

| Pista | data | giri (puliti) | benzina L | mediana s | SD ms | SD da differenze successive ms | trend ms/giro ± IC95 | tempo~benzina ms/L ± IC95 |
|---|---|---|---|---|---|---|---|---|
| Imola | 18/07 | 4 (4) | n.d. | 108,683 | 882 | 569 | −644 ± 691 | n.d. |
| Monza | 02/08 | 10 (8) | 59,2→27,8 | 117,623 | 1928 | 1514 | +260 ± 541 | −83 ± 171 |
| Monza | 10/08 | 4 (4) | 59,2→47,9 | 139,011 | 2977 | 2707 | −1208 ± 5977 | +415 ± 2076 |
| Monza | 14/08 | 4 (4) | n.d. | 114,347 | 930 | 856 | −348 ± 1919 | n.d. |
| Imola | 24/09 | 6 (4) | 44,2→26,6 | 107,016 | 716 | 825 | −164 ± 1084 | +56 ± 368 |
| Red Bull Ring | 14/10 | 12 (8) | 59,5→29,1 | 94,052 | 558 | 552 | −13 ± 171 | +5 ± 67 |
| Brands Hatch | 25/10 | 6 (4) | 17,7→4,9 | 89,456 | 1228 | 678 | −490 ± 488 | +230 ± 225 |
| Zolder | 29/10 | 7 (4) | 59,7→43,3 | 94,750 | 916 | 582 | −385 ± 541 | +164 ± 226 |
| Zolder | 29/10 | 6 (4) | 59,7→45,2 | 94,867 | 536 | 424 | −272 ± 477 | +110 ± 196 |
| Zolder | 01/11 | 5 (4) | 61,6→50,1 | 94,659 | 616 | 488 | −394 ± 818 | +168 ± 354 |
| Imola | 08/11 | 4 (4) | 47,1→35,9 | 107,374 | 672 | 367 | −520 ± 19 | +185 ± 7 |
| Imola | 14/11 | 6 (4) | 59,1→42,3 | 106,874 | 588 | 502 | −182 ± 616 | +65 ± 219 |
| Imola | 14/11 | 7 (4) | 47,0→27,1 | 105,601 | 1070 | n.d. | −390 ± 324 | +138 ± 115 |

(L'IC strettissimo dell'8/11 è un caso di 4 punti quasi allineati, non una misura precisa.)

- **SD del tempo sul giro dentro lo stint: mediana 882 ms (0,81% del giro)**; p25 616, p75 1070; minimo 536, massimo 2977.
- **Tolto il trend** (differenze fra giri consecutivi): **mediana 575 ms (0,60%)**; p25 499, p75 833.
- **Trend**: negativo in **12 stint su 13** (mediana −385 ms/giro), significativo al 95% in 3 su 13. Il pilota si sta ancora scaldando dentro stint da 4-7 giri.
- **Confronto con la banda dell'Ingegnere**: `_TIME_BAND_FRAC` = 0,15% (`engineer/core.py:340`) vale ≈160 ms su un giro da 1:47. Ricampionando i 56 residui dal trend (SD 0,77%), la differenza fra **due mediane di 3 giri a parità di tutto** ha SD 0,60%; supera 0,15% nel **78%** dei casi, e nel 10% dei casi supera 0,93% (≈1,0 s). Con 3 giri per finestra, un verdetto ACCEPT/REVERT basato sul tempo è quasi tutto rumore.

**Quanto vale un litro.** Non si riesce a stimare.

| Insieme | stint | giri | stima | IC95 |
|---|---|---|---|---|
| tutte le piste, effetti fissi di stint | 11 | 52 | +0,026 %/L ≈ **+28 ms/L** su 1:46 | **± 55 ms/L** |
| Imola | 4 | 16 | +105 ms/L | ± 56 |
| Monza | 2 | 12 | −56 | ± 194 |
| Zolder | 3 | 12 | +147 | ± 69 |
| Red Bull Ring (lo stint più lungo) | 1 | 8 | +5 | ± 67 |
| tutte, solo dal 4° giro di stint | 2 | 13 | −93 | ± 135 |

L'intervallo della stima complessiva contiene lo zero. Dentro uno stint benzina e numero di giro sono collineari: l'effetto del peso non si separa da gomme che entrano in temperatura e pilota che migliora. I +105 e +147 ms/L di Imola e Zolder vengono da stint di 4 giri puliti col trend di riscaldamento dentro; se fosse tutta benzina, a 2,8 L/giro vorrebbero dire 0,3-0,4 s al giro di guadagno, il che non è credibile. Il dato più pulito è lo stint di 12 giri al Red Bull Ring: +5 ± 67 ms/L, cioè «meno di circa 70 ms/L». Per misurarlo serve uno stint lungo a passo costante fatto apposta, o due stint a carichi diversi nella stessa serata.

---

## Sintesi

1. **Canali**: 29 per campione a ≈9 Hz, tutti vivi tranne `grip`. Mancano profilo termico I/M/O, freni (letti, non salvati), sospensioni, altezze, deriva per ruota, velocità locale, vento, stato pista. TC e ABS sono flag 0/1.
2. **Cecità**: non è la taratura della baseline (1,95 contro 1,87 misurato). È la forma: soglia da evento raro (peggior 2,6% dei campioni) usata come media di fase, fase d'ingresso senza sterzo (2,2% dei campioni ammissibili), banda d'apex da ±98 m, soglia unica per un rapporto che cambia con la velocità, e sovrasterzo cercato nel controsterzo che con gli aiuti compare nello 0,26% dei campioni.
3. **Segnali che reggono**: quota di TC in uscita (ICC 0,91 a leva ferma), differenza di temperatura anteriore−posteriore (SD 0,4 °C nello stint, 5 °C fra configurazioni), slip posteriore medio in uscita (CV 6-11%); velocità minima e g laterale come misura d'esito. Angolo di sottosterzo e yaw−ay/v, calcolati a 9 Hz con i canali attuali, no.
4. **Tempo sul giro**: SD 0,6-0,8% dentro lo stint contro una banda di 0,15%; un litro non è stimabile (+28 ± 55 ms/L).
