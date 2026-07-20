# Piano test — validare le calibrazioni fragili

> Obiettivo: trasformare le calibrazioni "tarate su una sola sessione" in numeri
> di cui fidarsi, PRIMA che l'ingegnere proponga modifiche di setup. Le ha
> segnalate il panel del 2026-06-27 (vedi `HANDOFF-engineer-diagnosis.md` §
> Validazioni). Ordine pensato per una sessione di ~30–40 min in pista.
>
> Come funziona: tu guidi come indicato, io lancio la cattura (basta un "vai" o
> dimmi quando sei in pista). Ogni voce ha un **criterio di promozione** netto:
> se non lo passa, la calibrazione resta "non fidata" e l'ingegnere non agisce su
> quel sintomo.

Comando generico (da sorgente): `python -m accoach.diagnostics <cmd> --seconds N`.
Puoi lanciarli tu col prefisso `!`, oppure dimmi "pronto" e li avvio io.

---

## 0. Prerequisito — assi G (solo se testi ACC)
- **Perché**: g_lat/g_long alimentano la diagnosi; l'asse va confermato per gioco.
- **Guida**: una frenata forte in rettilineo + una curva decisa a destra e una a
  sinistra.
- **Comando**: `verify-g` (lo lancio io).
- **Promozione**: il report dice "assi coerenti" (long negativo in frenata, lat
  col segno giusto in curva). Se no, si corregge la mappatura prima di tutto.

---

## 1. Segno yaw (`_YAW_SIGN`) — cross-car ⚠️ priorità alta
- **Perché fragile**: oggi `-1.0` poggia su UNA sessione (GT3/Imola) con un 70%
  che il nostro stesso verdetto classifica "inconcludente". Tutto il **sovrasterzo**
  dipende dal segno di `steer·yaw`: se è sbagliato su un'altra auto, o le curve
  pulite sparano "sovrasterzo", o i veri sovrasterzi si perdono.
- **Guida**: 2–3 min, curve **sopra 60 km/h**, sia a sinistra sia a destra,
  guida pulita (niente sovrasterzo voluto).
- **Comando**: `diagnostics yaw --seconds 150`.
- **Ripeti su ≥2 classi**: una **GT3** e una **stradale** (e/o una Formula).
- **Promozione**: ≥**80%** dei frame in curva con lo **stesso** segno di
  `steer·yaw`, con ≥10 frame per lato. Sotto 80% = "inconcludente" → il
  sovrasterzo→setup resta disattivato per quell'auto.

## 2. Soglie slip lock/spin (`-0.15` / `+0.10`) — 2ª auto ⚠️ priorità alta
- **Perché fragile**: abbassate aggressivamente (da -0.25) su un'auto con aids
  spazzatura. Su un'auto con baseline di slip diverso, un normale trail-braking
  può contare come bloccaggio e gonfiare i `lock_segments`.
- **Guida**: 3–4 giri con **staccate forti** (qualche bloccaggio vero va bene) e
  **trazioni decise** in uscita, su un'auto/pista DIVERSA dalla taratura GT3.
- **Comando**: `diagnostics stats --seconds 180`.
- **Promozione**: nel log, lo slip **tipico** in frenata forte e in trazione
  pulita deve restare **dentro** le soglie (cioè `> -0.15` e `< +0.10`), mentre i
  bloccaggi/pattinamenti **veri** le superano. Se il tipico le sfora →
  ricalibrare la soglia da p99 per quell'auto.

## 3. Rapporto sotto/sovrasterzo (`_UNDERSTEER_RATIO=0.9`) — split velocità
- **Perché fragile**: `|yaw|/|steer|` dipende dalla velocità, ma la soglia (da una
  mediana ~1.9 di un'auto/pista) è applicata uguale a curve lente e veloci.
- **Guida**: qualche giro pulito con un mix di **curve lente e veloci**.
- **Comando**: `diagnostics stats --seconds 180` (logga il rapporto per curva).
- **Promozione**: la mediana del rapporto in curva **pulita** è ben sopra 0.9
  (verso ~1.5–2.0) sia in lento sia in veloce; se le due bande sono molto diverse,
  serviranno due soglie (LOW/HIGH).

## 4. Tasso di falsi positivi su giro pulito
- **Perché**: il punto chiave per fidarsi. Su un giro pulito i detector devono
  **tacere quasi sempre**. Se "sparano" sottosterzo/sovrasterzo dove non c'è, il
  motore inseguirebbe fantasmi.
- **Guida**: 2–3 **giri puliti** del tuo passo normale, senza errori voluti.
- **Comando**: `diagnostics dryrun --seconds 240` (mostra i cue che scatterebbero,
  senza voce).
- **Promozione**: pochissimi cue tecnici in curve pulite. Annota ogni cue che ti
  sembra **falso** (es. "sovrasterzo" in una curva fatta bene): è oro per la
  taratura. Idealmente < ~1 falso ogni 2–3 curve.

## 5. Livelli aiuti (`tc_level/abs_level`) — GT3 con HUD ⚠️ da validare
- **Perché fragile**: gli offset della struct aid-level GT3 non sono confermati;
  se leggiamo garbage, l'ingegnere consiglierebbe TC/ABS a vuoto.
- **Guida**: con una **GT3 (ACC)** che mostra TC/ABS a HUD: **cambia** TC e ABS di
  un paio di tacche mentre catturo (es. TC 3→5, ABS 2→4).
- **Comando**: `diagnostics aids --seconds 120` (lo lancio io).
- **Promozione**: i valori letti **seguono** i cambi a HUD (stessi numeri). Se no,
  gli aiuti restano "sconosciuti" (-1) e l'ingegnere usa solo lo slip fisico.

---

## Riepilogo rapido (ordine consigliato)
1. (ACC) `verify-g` — assi a posto
2. `yaw` su GT3 → poi su stradale/Formula — segno ≥80% per auto
3. `stats` su 2ª auto/pista — soglie slip + rapporto sotto/sovra
4. `dryrun` su giri puliti — conta i falsi positivi
5. `aids` su GT3 con HUD cambiando TC/ABS — livelli affidabili

**Cosa porto a casa**: per ogni auto provata, un verdetto "fidato / non fidato"
su yaw, slip e aids. Le auto promosse possono ricevere proposte di setup;
le altre restano in sola diagnosi finché non le ritariamo. Annota i falsi
positivi: guidano la calibrazione fine.

---

## RISULTATI — sessione 2026-06-27 · BMW M4 GT3 · Monza · AC

Prima auto validata col piano. Cross-engine importante: tutte le tarature
nascevano in ACC o su AC1 GT3 McLaren/Imola; qui è BMW M4 GT3 in AC/Monza.

| # | Calibrazione | Verdetto | Evidenza |
|---|---|---|---|
| 1 | `_YAW_SIGN = -1.0` | ✅ **FIDATO (alta)** | 723 frame curva pulita, **100% opposto** (sx 544 / dx 179). Conferma cross-engine ACC→AC. |
| 2a | lock anteriore `_LOCK_RATIO = -0.15` | ✅ **FIDATO** | frenata forte tipica -0.066 (p99 -0.041); lock vero -0.417 → margine netto. |
| 2b | spin posteriore `_SPIN_RATIO = +0.10` | 🟡 **DA ALZARE → +0.13** | uscite **pulite** (giudizio pilota) sparano `wheelspin` a Rsp +0.11/+0.12, stessa chicane ogni giro. 5 falsi positivi su dryrun. |
| 3 | `_UNDERSTEER_RATIO = 0.9` | ✅ **FIDATO (parziale)** | curve veloci pulite: mediana \|yaw\|/\|steer\| = **1.77** ≫ 0.9, nessun falso. Split lento/veloce NON verificato (serve logging a bande). |
| 5 | aiuti `tc/abs_active` | ⚪ **N/A in AC** | canali = 0 ovunque; in AC l'ingegnere usa solo slip fisico. Step `aids` resta solo-ACC. |

### ⚠️ Finding per la lane `coaching/` (NON modificato da questa sessione)
`_SPIN_RATIO` in `src/accoach/coaching/events.py:42` è tarato (commento righe 59-61)
sul **traction ceiling +0.071 della McLaren MP4-12C GT3 (Imola)**. La BMW M4 GT3
ha un ceiling più alto: in trazione pulita p90 = 0.036 ma **p99 = 0.105** e le
uscite pulite reali toccano **0.11-0.12**. Quindi +0.10 sta SOTTO il ceiling pulito
della BMW → falsi positivi confermati dal pilota.

→ **Il rear-spin clean-ceiling VARIA per auto** (0.071 McLaren vs ~0.12 BMW),
contrariamente all'assunzione del commento ("reads the same on any car"). Il lock
anteriore invece regge bene cross-car.

**Raccomandazione**: alzare `_SPIN_RATIO` a **+0.13** (sopra il 0.12 pulito BMW,
sotto i pattinamenti veri: 0.16 qui, 0.138 sull'auto vecchia). Fix pulito a lungo
termine: soglia spin **per-classe/per-auto** (decisione architetturale `coaching/`).
Il `_LOCK_RATIO = -0.15` può restare globale.

**Pattini veri vs falsi (BMW, da dryrun)**: falso = Rsp 0.11-0.12 a tutto gas in
uscita chicane lenta; vero = fino a 0.16. Soglia 0.13 separa i due.

---

## RISULTATI — sessione 2026-06-27 · Ferrari SF25 · Nürburgring GP · AC

Seconda classe validata (profilo **Formula**). Id mod: `gp_2025_sf25` (track
`ks_nurburgring`). Classificazione: serviva fix in `classmap.py` — aggiunti i
marker `gp_2025/2024/2023` (pacchetti-stagione F1 moderni) così la SF25 prende
il profilo Formula. Test class-agnostic (soglie raw in `coaching/`).

| Calibrazione | Verdetto | Evidenza + giudizio pilota |
|---|---|---|
| `_YAW_SIGN = -1.0` | ✅ **FIDATO** | 1678 frame curva pulita, **100% opposto** (sx 932/dx 746). Ora cross-CLASSE (GT3+Formula) e cross-engine. |
| lock anteriore `_LOCK_RATIO = -0.15` | ✅ **FIDATO** | pilota: "stavo bloccando l'anteriore" → `locked` (Flk fino a -1.00) veri. Regge globale cross-classe. |
| sovrasterzo (yaw·steer + `_YAW_SIGN`) | ✅ **FIDATO** | pilota: "sovrasterzo confermato" → entrambi i cue veri, incluso quello a sterzo ~0. |
| spin posteriore `_SPIN_RATIO = +0.10` | 🔴 **PER-CLASSE** | pilota: "uscite pulite" → `wheelspin` a Rsp 0.10-0.13 FALSI. Spin vero = 0.24. |
| `_UNDERSTEER_RATIO = 0.9` | ✅ no falsi, ⚠️ poco sensibile | mediana curve pulite = **2.54** (vs 1.77 GT3). Nessun cue falso ma su F1 va reso relativo al baseline. |

### ⚠️ Finding forte (2 auto): `_SPIN_RATIO` deve essere PER-CLASSE
Il clean-ceiling posteriore scala con la classe — confermato su due classi:

| Classe | Auto | Uscite pulite fino a | Spin vero | Soglia consigliata |
|---|---|---|---|---|
| GT3 | BMW M4 (Monza) | 0.12 | 0.16 | **+0.13** |
| Formula | SF25 (Nürburgring) | 0.13 | 0.24 | **+0.15** |

→ `coaching/events.py:42` `_SPIN_RATIO` da rendere **per-classe** (GT3 +0.13,
Formula +0.15), NON un globale. `_LOCK_RATIO = -0.15` invece regge globale.

### Altri finding (lane `coaching/`)
- ~~**Sottosterzo relativo**: `_UNDERSTEER_RATIO` assoluto (0.9) è poco sensibile su
  auto ad alto yaw (F1 baseline 2.54). Meglio "ratio < frazione del baseline pulito
  dell'auto" invece di una soglia assoluta.~~ **RISOLTO 2026-07-20.** Baseline
  misurato sui giri registrati: Formula 2.50 (1737 campioni, SF25 @ Nürburgring),
  GT3 1.93/1.98, stradale 1.95 — conferma il 2.54 annotato qui. La soglia è ora
  `yaw_baseline × 0.45` per classe (`coaching/tuning.py`), cioè il ~5% peggiore dei
  campioni in curva in ogni classe. Effetto misurato: Formula 0.90 → 1.12 (frame
  rilevati 4.0% → 5.4%), GT3 e stradali invariati (0.90 → 0.88). **Da confermare
  in pista**: che i nuovi rilevamenti su Formula siano sottosterzi veri.
- **Burst lock**: in staccata pesante l'F1 spara 5 `locked` in ~1.5s (stesso evento,
  segmenti pos diversi → non deduplicati). Tema cadenza/scheduler.
- **Abnormal-state gate**: frame `st+1.00 Flk-1.00 yaw-1.09` = quasi-testacoda →
  lì dovrebbe sopprimere il cue "bloccaggio", non emetterlo.

### Fix applicato in questa sessione (lane engineer — mia)
`engineer/classmap.py`: aggiunti marker `gp_2025/2024/2023` → la griglia F1
moderna prende il profilo Formula.

---

## RISULTATI — sessione 2026-06-28 · BMW M3 E92 · Suzuka · AC

Terza classe validata (profilo **Stradale**). Id `bmw_m3_e92` → classificato
Stradale senza fix. TP senza aiuti, basso carico. Completa il giro sui 3 profili.

| Calibrazione | Verdetto | Evidenza + giudizio pilota |
|---|---|---|
| `_YAW_SIGN = -1.0` | ✅ **FIDATO** | 325 frame, **100% opposto**. 3ª classe → yaw blindato su GT3+Formula+Stradale. |
| lock `_LOCK_RATIO = -0.15` | ✅ **FIDATO** | **zero falsi** in dryrun nonostante margine stretto (tipico -0.096, lock più profondo solo -0.171). |
| `_UNDERSTEER_RATIO = 0.9` | ✅ **VALIDATO** | pilota: "anteriore scivolato" → il cue understeer (ratio 0.81) era VERO. La soglia 0.9 aggancia sottosterzo reale su stradale/GT3 (mediana ~1.8). |
| spin `_SPIN_RATIO = +0.10` | 🟡 **→ +0.12** | 1 solo falso (pilota: "pulita") a Rsp 0.11. Road clean p99=0.086 ma picco pulito 0.11. |
| **trail_brake** (`coaching/braking.py`) | 🔴 **TROPPO AGGRESSIVO** | 6 falsi (pilota: "detector troppo aggressivo"). Penalizza la frenata in rettilineo, corretta su stradale. |

### Quadro per-classe CONSOLIDATO (3 classi)
`_SPIN_RATIO` globale +0.10 è troppo basso per tutte → per-classe:

| Classe | Auto | Uscita pulita fino a | Spin vero | Soglia |
|---|---|---|---|---|
| Stradale | M3 E92 (Suzuka) | 0.11 | 0.24 | **+0.12** |
| GT3 | M4 (Monza) | 0.12 | 0.16 | **+0.13** |
| Formula | SF25 (Nürburgring) | 0.13 | 0.24 | **+0.15** |

`_UNDERSTEER_RATIO = 0.9`: ✅ validato su Stradale/GT3 (aggancia sottosterzo vero);
⚠️ poco sensibile SOLO su Formula (mediana 2.54) → relativo-al-baseline lì.
`_LOCK_RATIO = -0.15`: ✅ globale su tutte e 3 le classi.

### ✅ CHIUSO 2026-07-17 — trail_brake per-classe
Il cue trail-brake è ora **spento sul profilo Stradale** e attivo su GT3/Formula,
via `trail_brake_cue` in `coaching/tuning.py` (stessa tabella di `spin_ratio`).
Scelto **silenzio** e non una soglia rilassata: l'audit sulla M3 dà 6 falsi e zero
veri, quindi non c'è alcun dato che dica *dove* mettere una soglia intermedia (a
differenza dello spin, dove avevamo 0.11 pulito vs 0.16 vero). Se in una sessione
futura emergono trail-brake **veri** su stradale, si riaccende con una soglia tarata
su quei numeri. `BrakingDetector` prende la classe come `EventDetector`
(costruttore + `set_car_class`), l'engine la aggiorna al cambio auto.
Sistemato anche `diagnostics dryrun`: costruiva i detector senza classe, quindi
auditava una stradale con le soglie GT3 — ora ritara al cambio auto e stampa la
classe riconosciuta.

### Finding originale (lane `coaching/braking.py`): trail_brake class-aware
Il detector (`_trail_fault`, braking.py:99) spara su "frenata forte → inserimento
col freno già rilasciato" entro 0.8s. Su stradali a basso carico la frenata in
rettilineo + rilascio prima dell'inserimento è TECNICA CORRETTA → 6 falsi sulla
M3. Direzioni: renderlo **class-aware** (trail-braking premia le alto-carico;
rilassare/sopprimere su profilo Road) e/o richiedere un **gap reale freno→sterzo**,
non solo "freno basso all'inserimento". L'autore stesso lo marca "heuristic"
(braking.py:18).
