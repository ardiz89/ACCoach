# ACCoach — Ingegnere di pista (Race Engineer)

Sistema che chiude il loop **telemetria → diagnosi → consiglio di setup → modifica → ri-test**, giro
dopo giro, una volta scelti auto e circuito. Tre ingegneri specializzati con **UI dedicate**:
**Formula** (monoposto alto downforce), **GT3** (ACC/AC), **Stradali** (basso/nullo downforce).

> Documento di progetto. Sintesi del panel di ingegneri (race-engineer-f1/gt3/road),
> telemetry-analyst e dashboard-dev del 2026-06-27. Coordinare con l'altra sessione prima di
> toccare `src/accoach/coaching/`.

---

## 0. Il vincolo tecnico fondamentale (leggere per primo)

**Non si può modificare il setup di garage mentre si guida.** Verificato sul nostro stesso codice:

- La shared memory AC/ACC è **sola lettura** (`reader.py`, `_FILE_MAP_READ`), e soprattutto **il
  setup di garage non è in memoria**: molle, barre, ammortizzatori, ali, altezze, camber, toe,
  differenziale vivono solo nei **file di setup su disco** e nel motore fisico.
- Né AC né ACC ricaricano il setup a caldo: il file è applicato **solo quando il pilota rientra ai
  box, apre la schermata Setup e carica quel file**.
- Scorciatoie "live" (memory-write, input-injection) = fragili e territorio cheat/ban. **Scartate.**

### Il loop ONESTO che promettiamo

```
Guidi → diagnosi live (telemetria) → l'ingegnere consiglia → l'app SCRIVE il file di setup
   (backup + validazione) → rientri ai box e CARICHI il setup → riparti → ri-test
```

Più un livello separato e dichiarato — **"manopole al volo"** — per ciò che il pilota *può* davvero
cambiare in macchina: **brake bias, TC, ABS, mappa motore** (e su monoposto brake migration/ERS).
L'app le **suggerisce** (overlay/voce, già esistente); il pilota le applica coi tasti. Non le scrive.

Cosa **non** promettiamo mai: molle/ARB/ali/ammortizzatori che cambiano in pista.

---

## 1. Architettura a profili plug-in

Motore comune class-agnostic + un `EngineerProfile` per classe. Nuovi package, **non** toccano
`coaching/` né `telemetry/`.

```
src/accoach/setup/                 # FONDAZIONE (class-agnostic) — lettura/scrittura file
  acc_format.py    # JSON ACC  <-> valori fisici; tabella indice<->psi/grado, range, passo per carModel
  ac_format.py     # INI AC    <-> valori fisici (fase 2)
  store.py         # path Documents/.../Setups/<car>/<track>; backup atomico; scrittura atomica; undo
  diff.py          # diff leggibile vecchio->nuovo in unità fisiche
  params.py        # capability/range/passo per carModel; raggruppamento in CarClass

src/accoach/engineer/              # MOTORE + PROFILI
  core.py          # macchina a stati class-agnostic: evaluate_lap(), propose_change(),
                   #   accept_or_reject(); fasi, gate, rollback, cooldown, anti-loop
  classmap.py      # carModel -> CarClass (FORMULA / GT3 / ROAD) + override manuale UI
  profiles/
    gt3.py         # fasi P1..P5, tabella sintomo->modifica, range/passi GT3
    formula.py     # fasi P1..P7, aero-first, no ABS/TC su storiche
    road.py        # fasi P1..P6, no aero/elettronica, degrado con grazia

src/accoach/web/
  engineer.html / engineer.js      # shell UI; carica il layout della classe attiva
  (stile condiviso con la web app esistente; canvas a mano, zero librerie JS)
```

**Data flow** (riusa lo stack esistente):

```
Gioco ──shared mem──> server.py (engine.tick) ──WS 8777──> Engineer UI (telemetria + diagnosi live)
File setup .json <──backup/atomic write── setup/store ──REST 8778 (api.py)──> Engineer UI (read/preview/apply/undo)
   (poi il pilota RICARICA ai box)
```

La **diagnosi** (tassonomia sotto/sovrasterzo × entrata/apex/uscita × velocità) nasce in `coaching/`
(lane dell'altra sessione); l'app engineer la **consuma** via firme stabili
(`build_lap_debrief`/`CornerStats`) nel payload serializzato. Noi presentiamo e applichiamo.

### Contratto REST (`/api/setup/*` in `api.py` — aggiungere route = riavviare il server)

- `GET  /api/setup/list?car&track` — file disponibili per la combo.
- `GET  /api/setup/current?car&track&name` — setup parsato → valori fisici + range + passo.
- `POST /api/setup/preview` — modifiche → diff + validazione range, **senza scrivere**.
- `POST /api/setup/apply` — modifiche + `confirm:true` + `as_name` → backup + scrittura atomica → diff.
- `POST /api/setup/undo?car&track&name` — ripristina dall'ultimo backup.

`car_model`/`track` del payload coincidono coi nomi cartella dei setup ACC (es. `mclaren_720s_gt3`
/ `monza`): mapping diretto della combo. La tabella **range/passo per-auto** invece va costruita e
testata con cura (i valori nei file sono **indici/click, non psi/gradi**).

---

## 2. Il motore (macchina a stati) — comune a tutte le classi

Una valutazione **per giro al traguardo** (trigger `_prev_pos>0.7 and pos<0.3`, come `advisor.py`).
Ogni iterazione: al massimo **una modifica**, poi cooldown di re-test.

### Fasi sequenziali con gate

Ordine e parametri dipendono dalla classe (§3), ma lo scheletro è comune:

- Ogni fase ha un **gate di completamento** quantitativo, valutato su **N≥3 giri "stabili"**
  (`lap_span≥0.7`, no pit/off/abnormal, `|lap_time − mediana| < 1.5%`, gomme in temp).
- **Rollback di fase**: se una modifica a valle rompe un gate a monte (es. il rake sposta le
  pressioni fuori finestra), torna alla fase competente prima di proseguire.

### Loop di accettazione di una modifica

```
1. BASELINE: mediana(lap_time) e symptom_score su 3 giri stabili.
2. Applica UNA modifica (~2 click) sul rimedio #1 della cella sintomo.
3. INVALIDA il reference (cambia il punto di frenata) → 1 giro di ri-adattamento scartato.
4. Misura 3 giri stabili → mediana(lap_time'), symptom_score'.
5. DECISIONE:
   Δsym<0 e Δt≤+ε_t   → ACCETTA, continua stessa direzione
   Δsym≈0 e Δt≈0      → "non peggiora → vai bene": tieni; se ancora piatto → rimedio #2
   Δt peggiora >ε_t   → RIFIUTA, ripristina, passa al rimedio #2
```

Soglie: `ε_sym` ≈ 15% di riduzione del bucket; `ε_t = max(0.001·t, 0.5·std)` dai 3 giri baseline.

### Sicurezza / anti-loop

Una variabile per volta · cooldown re-test (1 scarto + 3 misura) · ripristino esatto al RIFIUTA ·
budget per cella (~5 rimedi, poi "possibile problema di guida") · isteresi anti-ping-pong ·
backup obbligatorio + scrittura atomica (tmp+replace) + undo · validazione range per-auto ·
scrivi sempre su **nome nuovo** (l'originale resta intatto e il reload in MFD è affidabile).

### Setup vs guida (disambiguazione, prima di proporre setup)

| Segnale | SETUP (macchina) | PILOTA (guida) |
|---|---|---|
| Diffusione | sintomo in **≥3 curve** distinte | sintomo in **1 curva** → coaching di quella curva |
| Ripetibilità | in tutti i giri stabili, stesso punto | sporadico, varia col giro |
| Correlazione input | indipendente dagli input | sparisce quando l'input rientra |

Ogni modifica accettata che tocca grip/aero/freni **re-invalida il giro di riferimento**.

---

## 3. I tre profili (cosa cambia)

### 3.1 GT3 (ACC/AC) — il riferimento

- **Fasi**: P1 pressioni → P2 aero → P3 meccanico (molle→bump→ammortizzatori) → P4 brake bias →
  P5 elettronica (TC/ABS/mappa).
- 4 leve forti: aero, elettronica, meccanico, gomme. Pressioni a caldo target ~27.5 ± 0.7 psi.
- Lock diffusi → `ABS +1` finché `abs_level<8`, poi brake bias indietro (logica `advisor`).
  Spin diffusi → `TC +1`, poi diff/molla post.
- Asse velocità pieno (bassa = meccanico/diff; alta = aero/altezze).

### 3.2 Formula (monoposto, alto downforce) — **aero-first**

- **Fasi**: P1 pressioni → P2 temp/camber → **P3 aero+rake (PRIMA del meccanico)** → P4 meccanico →
  P5 differenziale → P6 brake bias + **brake migration** → P7 mappe/ERS/freno-motore (solo moderne).
- Leva primaria del bilanciamento: **ali + rake/ride height** (effetto fortissimo, passo 1 mm). In
  curva veloce (`speed ≥ ~150 km/h`) instrada il sintomo su aero/rake, in lenta sul meccanico.
- **No ABS, spesso no TC** (storiche): bloccaggi/pattinamento tutti **setup + guida**. `_lock_advice`
  va **diretto a brake bias/migration** (salta `ABS_UP`); spin → diff/posteriore (no `TC_UP`).
- Gomme: finestra **più bassa e più stretta** (tol ±0.3), camber più negativo. Storiche turbo: il
  lag è **guida**, non setup. `aids_adjustable=False` ⇒ mai cue su aiuti inesistenti.
- Soglie slip `_LOCK_RATIO=-0.15` / `_SPIN_RATIO=+0.10` già validate live su F1 1990 senza aids.

### 3.3 Stradali (basso/nullo downforce) — **degrado con grazia**

- **Fasi**: P1 pressioni → P2 meccanico → P3 allineamento → **P4 differenziale/trazione (sale di
  priorità)** → P5 brake bias (solo se regolabile) → P6 aero/rake (quasi sempre N/A).
- Solo **2 leve e mezzo**: gomme, meccanico, *forse* brake bias. Aero ed elettronica spesso assenti.
- **Asse velocità collassato** (no downforce → grip non cambia con la velocità): una sola bucket
  meccanica per sintomo.
- Sintomo-firma: **sovrasterzo in rilascio (lift-off)** delle trazioni posteriori → toe-in post,
  rebound post più morbido, ARB post più morbida, diff coast. Trazione in uscita senza TC → diff
  power più dolce + guida.
- Gomme: finestra **più larga** (tol ~1.5), warmup ~60 °C, `target_psi` **per-auto** (28–34 psi) o
  fallback al metodo temperatura/bilanciamento.
- **Capability detection**: parametro presente solo se `!= sentinel` (`tc_level/abs_level/
  engine_map != -1`, `brake_bias != -1.0`). Nascondi tile/sezioni assenti; banner "Setup limitato:
  questa auto regola solo {…}". Caso minimo = monitor gomme + consigli a debrief.

### Regola trasversale UI: tag `AV` (al volo) vs `BOX` (garage)

Ogni consiglio porta un tag. Il motore vocale pronuncia solo gli `AV` (brake bias, TC/ABS/mappa dove
esistono); tutto il resto (pressioni a freddo, molle, barre, ammortizzatori, geometria, diff, ali,
altezze) è **BOX** → compare nel debrief/pannello tra i run, non a metà giro.

---

## 4. Gap di telemetria (lane altra sessione — da segnalare, non toccare)

Per chiudere il loop in autonomia servono canali oggi non cablati/persistiti:

1. **Persistere `slip_ratio` fisico** nei giri (oggi si salva `wheel_slip` grezzo) → analisi
   lock/spin offline e car-agnostic.
2. **Persistere pressioni/temp/brake_bias/aids** nei giri (oggi nessuno) → diagnosi setup retrospettiva.
3. **Cablare `tyreTempI/M/O`** (interno/medio/esterno, ACC) → vera lettura "a 3 strisce" =
   camber termico e profilo di gonfiaggio. Senza, camber resta "suggerimento + conferma".
4. **Esporre `camberRAD`, `suspensionTravel`, `rideHeight`** → inferenze su molle/altezze/rollio.
5. **Validare** offset aid-level GT3 (`g.TC/ABS/EngineMap`), asse `accG`, segno `_YAW_SIGN` prima di
   affermazioni quantitative su TC/ABS/bias.
6. **Lettura file di setup ACC** (già nel package `setup/`) per conoscere i valori statici impostati.

---

## 5. Roadmap a fasi

- **F0 — Fondazione setup (class-agnostic, mia lane).** `setup/acc_format.py` + `store.py` + `diff.py`
  + tabella range/passo per qualche GT3, con test su un `.json` reale e demo CLI read→modifica→write
  (backup+undo). Nessuna UI. *È il prerequisito di tutto e non dipende dal coaching.*
- **F1 — Route REST `/api/setup/*`** in `api.py` + test TestClient (preview non scrive, apply senza
  confirm rifiuta, undo ripristina, range → 4xx).
- **F2 — UI engineer GT3** (vista web): diagnosi live (WS) + setup corrente in unità fisiche +
  controlli +/− con conferma esplicita prima di scrivere + banner "ricarica ai box".
- **F3 — Motore macchina a stati** (`engineer/core.py` + `profiles/gt3.py`): convergenza guidata
  giro-dopo-giro con diagnosi minima dai canali live.
- **F4 — Profili Formula e Stradali** (`profiles/formula.py`, `road.py`) + layout UI dedicati +
  classmap carModel→CarClass + capability detection.
- **F5 — AC (INI)** come seconda piattaforma; canali telemetria mancanti (coord. altra sessione).

Si parte da **ACC** (JSON, dove abbiamo già brake_bias/TC/ABS/EngineMap come stato live). AC in fase 2.

---

## 6. Rischi principali (onesti)

1. **Niente applicazione live del setup** — il valore è il loop tra-i-run; va comunicato chiaro.
2. **Valori a indici, non fisici, e per-auto** — la tabella range/passo è il pezzo fragile; ogni
   patch/auto può cambiarla; va versionata e testata.
3. **Non sappiamo quale setup è caricato** (la shared memory non lo espone) → lavoriamo per combo e
   scriviamo sempre nome nuovo.
4. **Reload non automatico a parità di nome** → nome nuovo.
5. **Qualità della diagnosi** dipende dal layer `coaching/` → siamo il vettore di presentazione.
6. **Online/anti-cheat** — scrivere setup in garage è lecito; qualsiasi "live" sconfina nel cheat.
7. **AC vs ACC** — formati diversi: partire solo da ACC.
