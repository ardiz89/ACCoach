# Handoff — alimentare l'Ingegnere di pista con la diagnosi (`LapStats`)

> Per la sessione che lavora su `coaching/` + telemetria. L'altra metà (setup
> read/write, le 3 UI, la macchina a stati di convergenza) è **completa e testata**
> (F0–F5, vedi `ENGINEER.md`). Manca un solo ponte: produrre la **diagnosi per
> giro** che il motore consuma. Questo documento è il contratto di quel ponte.

## TL;DR

A fine di ogni giro, costruisci un oggetto **`LapStats`** (la diagnosi di quel
giro nella tassonomia sotto/sovrasterzo × entrata/apex/uscita × bassa/alta
velocità) e passalo a `RaceEngineer.observe(stats)`. Tutto il resto (decidere
cosa cambiare, valutare, accettare/ripristinare) è già fatto.

```python
from accoach.engineer import engineer_for, LapStats, Symptom, Balance, Phase, Speed

# engineer_for sceglie profilo (GT3/Formula/Road) E la finestra pressioni dell'auto
eng = engineer_for(snapshot.car_model, track=snapshot.track)
...
# a fine giro:
decision = eng.observe(build_lap_stats(lap, reference, corners))
# quando il pilota SCRIVE il setup proposto (via UI): eng.mark_applied()
```

## Il contratto: `LapStats`

Definito in `src/accoach/engineer/core.py`. Campi (tutti opzionali tranne
`lap_time_ms`):

| Campo | Tipo | Significato | Da dove |
|---|---|---|---|
| `lap_time_ms` | `int` | tempo sul giro | già disponibile |
| `stable` | `bool` | giro "pulito" (no off/pit, tempo entro la banda recente) | filtro tuo (vedi sotto) |
| `warmed_up` | `bool` | gomme in temperatura | `tyre_core_temp` medio ≥ soglia |
| `symptom_scores` | `dict[Symptom, float]` | **il cuore**: intensità ~0..1 per ogni sintomo rilevato | da `balance.py` + curve |
| `symptom_corners` | `dict[Symptom, int]` | **necessario**: n. di curve DISTINTE in cui è apparso il sintomo (gate setup-vs-guida) | conta le curve nel giro |
| `pressures_hot` | `dict\|None` | `{"front": psi, "rear": psi}` a caldo | media `tyre_pressure` per asse |
| `lock_segments` | `int` | n. segmenti distinti con bloccaggio | come `advisor.py` |
| `spin_segments` | `int` | n. segmenti distinti con pattinamento | come `advisor.py` |

Solo i giri con `stable=True and warmed_up=True` entrano nella finestra di
valutazione del motore; gli altri sono ignorati (non serve filtrarli a monte).

> ⚠️ **Salvaguardia anti-falso-positivo (aggiornata 2026-06-27).** Il motore
> propone una modifica di setup per un sintomo SOLO se è: (a) sopra soglia 0.30,
> (b) presente in **≥3 curve distinte** (`symptom_corners ≥ 3` — è SETUP, non
> errore di guida in una curva), e (c) **persistente** su ≥3 dei giri stabili
> recenti. Se non popoli `symptom_corners`, il sintomo è trattato come 1 curva e
> **non genera mai una proposta**. Quindi popolarlo non è opzionale.

## Il vocabolario: `Symptom`

```python
Symptom(balance, phase, speed)
  balance ∈ {Balance.UNDERSTEER, Balance.OVERSTEER}
  phase   ∈ {Phase.ENTRY, Phase.APEX, Phase.EXIT}
  speed   ∈ {Speed.LOW, Speed.HIGH}
```

`symptom_scores` è un dict da `Symptom` a **intensità aggregata sul giro** in
~0..1 (0 = assente). Soglia di rilevazione del motore: **0.30**. Quindi punteggi
sotto 0.30 contano come "assente"; sopra, il motore agisce sul più alto.

Non serve popolare tutte le 12 celle: metti solo i sintomi effettivamente
presenti. Esempio di un giro con sottosterzo all'apex in curve veloci e un filo
di sovrasterzo in uscita lenta:

```python
symptom_scores = {
    Symptom(Balance.UNDERSTEER, Phase.APEX, Speed.HIGH): 0.55,
    Symptom(Balance.OVERSTEER,  Phase.EXIT, Speed.LOW):  0.35,
}
```

## Come calcolare i sintomi (aggancio al codice esistente)

Tutto questo vive già, in forma per-frame, nel vostro layer. Serve **aggregarlo
per curva × fase** e mapparlo sulla tassonomia. Riferimenti reali nel repo:

1. **Segmentazione curva → fase.** `track.detect_corners(samples)` dà
   `Corner(entry_pos, apex_pos, exit_pos)`. Per ogni curva:
   - **ENTRY** = `[entry_pos, apex_pos)` con `brake ≥ ~0.15`
   - **APEX** = intorno di `apex_pos` (minimo velocità)
   - **EXIT** = `(apex_pos, exit_pos]` con throttle in risalita

2. **Bilanciamento.** Riusa la logica di `coaching/balance.py`:
   - UNDERSTEER se `|yaw_rate| / |steer_angle| < _UNDERSTEER_RATIO` (≈0.9)
   - OVERSTEER se controsterzo (`steer_angle * yaw_rate < 0`) con `|yaw|` alto
   - **intensità** = quanto sotto/sopra la soglia, integrata sui frame della fase
     (es. frazione di frame in fault × ampiezza media), normalizzata a ~0..1.

3. **Banda di velocità.** Dalla velocità minima della curva (all'apex):
   **LOW < ~120 km/h**, **HIGH ≥ ~120 km/h** (parametro per pista; affinabile).

4. **Aggregazione robusta.** Mediana/percentili su una finestra di giri, non il
   singolo frame (come fa già `/api/progress` sugli ultimi ≤15 giri). Per un
   singolo `LapStats` basta l'aggregato di **quel** giro; il motore poi media su
   3 giri stabili da sé.

5. **lock/spin segments.** Esattamente come `coaching/advisor.py`: conta i
   **segmenti distinti** con `slip_ratio` oltre soglia (`events.py`:
   `_LOCK_RATIO`, `_SPIN_RATIO`). Passa i due conteggi.

6. **pressures_hot.** Media di `tyre_pressure` per asse a fine giro (front =
   media FL/FR, rear = media RL/RR). `None` se non disponibile (il motore salta
   la fase pressioni).

7. **stable.** Vero se: `lap_span ≥ 0.7`, no pit/off-track/abnormal-state,
   `|lap_time − mediana_recente| < ~1.5%`. (Stessi criteri già usati altrove.)

## Punto di integrazione

Due opzioni, a vostra scelta:

- **A) lato engine/serialize (consigliato per il live):** in `engine.tick`, a
  fine giro, costruite `LapStats`, chiamate `eng.observe(...)`, e mettete la
  `Decision` nel payload `state_to_dict` (un blocco `"engineer"`). L'UID engineer
  già pronta lo mostrerà (oggi mostra il `cue` live; aggiungeremo il blocco).
- **B) lato debrief (più semplice, offline):** in `coaching/debrief.py` o in un
  nuovo endpoint, ricostruite `LapStats` dai giri salvati e fate girare il motore
  a posteriori per un "piano setup" di sessione.

Per il **live**, l'unico campo nuovo nel payload sarebbe qualcosa tipo:

```python
"engineer": {
    "kind": decision.kind.value,          # propose / evaluating / accepted / ...
    "message": decision.message,
    "change": decision.change.as_setup_payload() if decision.change else None,
    "rationale": decision.change.rationale if decision.change else None,
    "tag": decision.change.tag if decision.change else None,  # "AV" / "BOX"
    "confidence": decision.confidence,                        # "alta" / "media"
}
```

(La UI engineer consuma già questo blocco esatto: lo mostra come proposta con
chip di confidenza, separa AV "ora in macchina" da BOX "al prossimo box", e il
bottone "Prepara modifica" precompila l'editor. Verificato con un mock.)

Io (altra sessione) aggancio la UI a quel blocco e gestisco `mark_applied()`
quando il pilota scrive il setup dall'editor. **Non serve che tocchiate `setup/`,
`engineer/`, `api.py`, `web/` o `serialize.py`** — passatemi solo `LapStats` (o,
se preferite l'opzione A, aggiungete il blocco `engineer` al payload e io faccio
il resto lato UI).

## Quick win bloccato: monitor gomme (alto valore, lane telemetria)

Il team è unanime: un **monitor pressioni/temperature a debrief** (psi a caldo per
gomma vs finestra, + profilo interno/centro/esterno per il camber termico) dà "il
70% del valore di un ingegnere reale", senza loop di scrittura. È **bloccato** su
due cose della vostra lane:
- esporre `tyre_pressure[4]` nel payload `serialize.state_to_dict` (oggi assente) e
  persistirlo nei giri (`SAMPLE_FIELDS`);
- esporre i 3 punti `tyreTempI/M/O` per gomma (oggi nello snapshot c'è solo
  `tyre_core_temp` singolo) — richiede toccare la struct in `telemetry/`.

Appena quei canali sono disponibili, **lato mio**: pannello gomme live nell'UI
engineer + monitor a debrief. Piccolo lavoro, gran valore — ma serve il dato prima.

## Cosa NON deve fare la diagnosi

- Non deve decidere le modifiche di setup (lo fa il motore).
- Non deve distinguere setup-vs-guida (lo fa il motore: sintomo in ≥3 curve =
  setup, in 1 = guida). Voi date i sintomi per curva/fase aggregati; se un
  problema è in una sola curva, il motore lo riconosce come guida.

## Validazioni PRIMA di lasciar proporre setup (priorità del team)

Un falso positivo qui fa cambiare l'assetto nella direzione sbagliata. Prima di
fidarsi della diagnosi per muovere molle/ARB/ali, in ordine:

1. **Ri-validare `_YAW_SIGN` (balance.py) cross-car.** Oggi `-1.0` poggia su una
   sessione (AC1 GT3/Imola) con un 70% che `diagnostics._yaw_verdict` stesso
   classifica "inconcludente" (serve ≥80%, ≥10 frame per lato). Tutto il
   sovrasterzo dipende dal segno di `steer*yaw`. Lanciare `verify-yaw` per ogni
   classe d'auto; sotto 80% → gate-off del sovrasterzo→setup.
2. **Persistere i canali mancanti nei giri (schema v5):** `slip_ratio` fisico
   (oggi si salva `wheel_slip` grezzo, scala car-dipendente → lock/spin segments
   inaffidabili offline), `tyre_pressure` per asse (per `pressures_hot`), e
   `brake_bias`/aids come metadati. Sblocca anche la diagnosi retrospettiva a
   debrief.
3. **Harness FP-rate su giro pulito.** Far girare i detector di bilanciamento su
   un reference pulito e misurare la frazione di frame/curve flaggati a torto —
   oggi non c'è un numero. Estendere `run_audit.py`/`synth.py`.
4. **Ri-validare le soglie slip** `-0.15`/`+0.10` (events.py) su una 2ª auto/pista
   e lo split banda velocità di `_UNDERSTEER_RATIO=0.9` separato LOW/HIGH.
5. **Calibrare `symptom_corners`/intensità** così la soglia 0.30 e il gate ≥3
   curve scattino su sintomi veri, non rumore.

Raccomandazione del team: partire dall'**opzione A (live)**, dove il `LapStats` è
completo già oggi, e fare in parallelo lo schema v5 per l'offline. Niente scrittura
file (BOX) finché 1 e 3 non sono fatti; i consigli AV (bias/TC/ABS) hanno già il
gate ≥3 segmenti in `advisor.py` e si possono attivare prima.

## Test di fumo (vostro lato)

```python
from accoach.engineer import RaceEngineer, LapStats, Symptom, Balance, Phase, Speed, profile_for_car
eng = RaceEngineer(profile_for_car("mclaren_720s_gt3_evo"), min_stable=3)
sym = Symptom(Balance.UNDERSTEER, Phase.APEX, Speed.HIGH)
for _ in range(4):
    d = eng.observe(LapStats(100000,
                             symptom_scores={sym: 0.6},
                             symptom_corners={sym: 4},   # in 4 curve → è setup
                             pressures_hot={"front": 27.5, "rear": 27.5}))
print(d.kind, d.message, d.change and d.change.as_setup_payload())
# -> PROPOSE  "Sottosterzo all'apex veloce: meno ala posteriore (−1)"  [{'param':'rearWing','slot':None,'delta_clicks':-1}]
```

Dipendenze: nessuna nuova. Il package `accoach.engineer` è autonomo e già nel repo.
