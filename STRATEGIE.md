# Strategie di miglioramento — progetto

Come HONE può rispondere a: *«voglio migliorare a Spa con questo clima — in base a
come guido, cosa devo fare?»*

Documento di design, **revisione 2** dopo panel a cinque revisori (prodotto, ingegneria
di pista, statistica, telemetria, implementazione). Stato del codice verificato al
2026-07-20 su 27 giri reali su disco.

> **La revisione 1 sbagliava il pilastro centrale.** Era costruita sulla segmentazione
> per condizioni meteo, fondata sul campo `grip`. Quel campo vale **0.0 su 26 giri su 26**
> (§4.1): il passo che dichiarava «usa dati già registrati, mezza giornata» non aveva
> input. In compenso il pezzo dato per più ambizioso — la classificazione delle curve —
> è risultato il più solido, misurato stabile su giri veri. Questa revisione inverte
> l'ordine e riscrive ciò che era tecnicamente sbagliato.

---

## 1. La promessa, e quella che non facciamo

La versione ingenua è *«HONE sa come si guida a Spa sul bagnato»*. Non la costruiamo:
**HONE non ha nessuna fonte da cui saperlo**, e le due che potrebbero dargliela sono
chiuse — conoscenza scritta a mano per pista (non scala: `trackdata.py` copre **una**
pista) e dati aggregati di molti piloti (richiede cloud, escluso).

Ma la promessa della revisione 1 — *«confronto te-in-umido con te-in-asciutto»* — è
**anch'essa sbagliata come centro della feature**:

> Il pilota che chiede «come miglioro a Spa sul bagnato» vuole sapere *cosa fare*, e la
> risposta onesta sarebbe «guidi peggio sul bagnato nelle veloci». Lo sa già.

Il valore che nessun altro strumento offline dà è un altro:

> **«È un tuo tratto, o è successo oggi?»**

Sistematico contro sporadico, attraverso le sessioni. Le condizioni meteo sono **una
chiave di segmentazione**, non la feature. Questo cambia le priorità di tutto il resto.

---

## 2. I tre pilastri — stato reale

### A · Contesto (in che condizioni guidavo) — **il campo previsto è morto**

| Campo | Stato misurato su 26 giri |
|---|---|
| `grip` | **0.0 ovunque.** Inutilizzabile |
| `road_temp` / `air_temp` | ✅ vivi e plausibili (38.1 °C / 30.4 °C ACC · 22.8 / 17.0 AC) |
| `tyre_compound` | ✅ `dry_compound`/`wet_compound` su ACC (canonico) · stringa arbitraria del mod su AC (`Semislicks (SM)`) |

Difetto **già attivo** indipendente da questa feature: le query di selezione del
riferimento (`catalog.py:206`, `:222`, `:233`) ignorano le condizioni, quindi un giro
sotto la pioggia viene confrontato col best sull'asciutto. E secondo l'ingegneria di
pista quel confronto non è «con una tolleranza»: in bagnato cambia la **geometria del
giro** — si evita la linea gommata perché è la più scivolosa, si sposta il punto di
frenata, si riduce il trail braking, si sale di marcia per ridurre la coppia. Sono
**due percorsi diversi**.

### B · Circuito (che curva è) — **fattibile e verificato**

`Corner` ha solo `index`, `entry_pos`, `apex_pos`, `exit_pos`, `name` (`track.py:44-59`).
Ma i dati per arricchirlo ci sono già e funzionano: vedi §3.1.

### C · Pilota (come guido io) — **nessuna memoria**

`FocusCoach` tiene 6 giri (`focus.py:183`) ma è ricreato a ogni cambio combo
(`engine.py:328`) e mai serializzato. Gli eventi vivono solo a runtime: su disco
finiscono i canali grezzi, mai le diagnosi. HONE non può dire *«tu tipicamente freni
tardi»*, solo *«in questo giro hai frenato tardi»*.

---

## 3. Cosa costruire

### 3.1 Classificazione delle curve, derivata dai dati — **il pezzo più solido**

Promossa a primo passo. Da `car_x/car_z`, già nei sample, con curvatura di Menger su
stencil ±3 campioni (~15 m di corda):

```
k = 2·((x1-x0)(z2-z0) - (z1-z0)(x2-x0)) / (|P0P1|·|P1P2|·|P0P2|)
```

presa come **mediana** su ±3 campioni attorno ad `apex_pos` (mediana, non media:
robusta ai salti singoli).

Validazione su giri reali — campionamento effettivo ~9 Hz, passo spaziale ~5 m,
coordinate arrotondate a 1 cm (quantizzazione irrilevante):

| | ACC Imola (7 giri) | AC Suzuka (3 giri) |
|---|---|---|
| rumore/segnale, stencil ±3 | 0.23 | 0.10 |
| direzione stabile giro-su-giro | **21/21** | |
| classe stabile | 19/21 | |

Raggi ottenuti: Tosa 34.6 m · Rivazza 41.6 m · tornante Suzuka 21.8 m · 130R 133 m.

Due accortezze obbligatorie:
- **Classificare in bin su κ = 1/R, non su R.** Sulle curve veloci R è instabile
  (kink Imola: 600 ± 295 m, CV 49%) perché lì si misura la traiettoria guidata, quasi
  rettilinea. κ ha errore assoluto limitato vicino a zero.
- **Velocità all'apice come discriminante primario** (CV 0.2-5.8%, molto più stabile).

Attributi risultanti: **tipo** (tornante / lenta / media / veloce) e **direzione**.
Aggiungere se possibile **spigolo vs appoggio**, che secondo l'ingegneria sono tecniche
opposte a parità di velocità apex.

La direzione si calcola ma **non si espone come diagnosi primaria**: l'asimmetria del
pilota esiste ma è di secondo ordine e quasi sempre confusa con banking, cordoli e
pendenza. Usarla solo se sistematica su ≥3 coppie di curve dello stesso tipo.

Implementazione: in `track.py` accanto a `detect_corners`, memoizzata **in processo**
con chiave = path del riferimento. Nessuna cache su disco: sono millisecondi di
aritmetica, e la chiave nuova invalida da sola quando il riferimento cambia.
Nota: `Reference` non espone `car_x/car_z` (`reference.py:28-42`) — leggerli da
`Lap.samples`.

### 3.2 Classe di condizione — su due assi, non uno

La revisione 1 metteva sullo stesso asse due variabili fisiche diverse:
Green/Fast/Optimum descrivono la **gommatura**, Damp/Wet/Flooded descrivono l'**acqua**.
Non sono gradi della stessa scala. E `Greasy` non è «asciutto sporco»: è pista che si
sta bagnando — la condizione tecnicamente più difficile di tutte.

**Asse 1 — acqua (cambia la tecnica):** `asciutto` · `crossover` (slick su umido, o
wet su pista che asciuga) · `bagnato`.
**Asse 2 — temperatura asfalto in bin (freddo / medio / caldo):** mancava del tutto, e
pesa più di Green vs Optimum. *Optimum a 15 °C e a 45 °C non sono la stessa pista.*

Asciutto-ottimale vs asciutto-sporco **non cambia la tecnica**: rilevante come
tolleranza sul confronto, non come classe di strategia.

Sorgenti, in ordine di disponibilità reale:

1. **Oggi, senza toccare nulla:** `tyre_compound` (binario e canonico su ACC) +
   `road_temp` in bin. Sono gli unici campi condizioni con dati veri.
2. **Su ACC, dopo §4.2:** `trackGripStatus`, che è già l'enum giusto.
3. **Su AC:** solo dopo aver corretto l'offset (§4.1) e **misurato live** se il campo
   viene davvero popolato. Finché non lo si sa, non è progettabile.

### 3.3 Riferimento consapevole del contesto

1. Riferimento nella **stessa classe** → confronto normale.
2. Nessun riferimento in quella classe → **HONE lo dice** («non ho ancora un tuo giro
   in bagnato qui: questo diventa il tuo riferimento»).
3. Mai confronto silenzioso fra classi diverse.

Il punto 2 è il costo vero di questo passo: distinguere «nessun riferimento» da
«nessun riferimento *in questa classe*» è un cambio di firma che risale fino a engine,
debrief e UI.

### 3.4 Memoria del pilota — scrivere subito, mostrare dopo

Due tabelle popolate a fine giro: `lap_event` (categoria, posizione, severità) e
`corner_loss` (indice curva, `lost_ms`, categoria, causa). I dati sono **già tutti
calcolati** oggi da `events.py`/`debrief.py` — e buttati via a fine giro.

**Vincolo architetturale, da decidere prima di scrivere una riga.** `lap_id` è
riassegnato a ogni drop-and-rebuild del catalogo (`catalog.py:120-141`), e `sync`
cancella le righe dei file spariti. Tabelle figlie chiavate su `lap_id` non diventano
orfane: **si agganciano al giro sbagliato, in silenzio**. Il catalogo è per contratto
una cache cancellabile (i `.json.gz` sono la fonte di verità). Quindi: chiave su `path`
(UNIQUE, naturale), oppure database separato per il profilo, fuori dal ciclo di rebuild.

**Normalizzazione**: mai «eventi per km». Monza ha ~7 frenate su 5.8 km, un cittadino
~15 su 4 km: il tasso per km confonde *opportunità* con *propensione*. Il denominatore
giusto è il numero di **staccate** (o di ingressi curva).

**Il profilo resta per-combo**, non cross-pista: aggregare auto con e senza ABS/TC
espone al paradosso di Simpson, e il pooling grezzo pesa le piste in proporzione ai
giri fatti.

**Scrivere ≠ mostrare.** Le tabelle si popolano da subito — ogni giorno di ritardo è
storico perso per sempre — ma non alimentano nessun output finché i cue non sono
tarati (§6).

### 3.5 L'output — una riga nel debrief, non una schermata

Niente vista dedicata con due tendine: se le combinazioni con dati sufficienti sono
poche, un selettore quasi vuoto è una promessa mancata a ogni apertura. L'output vive
**dentro il debrief esistente**, dove l'utente già va.

Prima del contenuto, un filtro obbligatorio:

> **Gate guida vs macchina.** In bagnato un «sottosterzo sistematico» è molto spesso
> pressione o temperatura anteriore fuori finestra, o brake bias troppo avanti — non
> tecnica. Senza questo filtro la strategia chiede al pilota di correggere qualcosa che
> l'auto gli sta imponendo, e lui non ci riuscirà mai. HONE ha già pressioni,
> temperature e l'Ingegnere: il gate va **davanti** alla diagnosi.

**L'esempio della revisione 1 era fisicamente sbagliato** e va conservato come
promemoria: *«frena prima e più leggero»* per sottosterzo in ingresso **peggiora** il
sottosterzo, perché scaricare il freno toglie carico all'anteriore. Il consiglio
corretto è: anticipa la frenata, abbassa il picco, ma **allunga il rilascio** tenendo
un filo di freno fino all'apice; e se l'auto non gira, **non aggiungere sterzo**.
Un consiglio alla volta, mai due in una frase.

**Le metriche di verifica della revisione 1 erano altrettanto sbagliate**: nel
sottosterzo la velocità minima **può salire mentre il giro peggiora** (allarghi, apri
il gas più tardi). Metriche corrette: tempo del micro-settore della curva, **istante
del gas pieno**, velocità a fine curva.

---

## 4. Ostacoli tecnici

### 4.1 Bug di offset su AC1 — non censito nella revisione 1

`surfaceGrip` è dichiarato all'offset ACC 1240 (`structs.py:157`), ma AC1 non ha
`activeCars`/`carID[60]`/`playerCarID`/`penalty`: lì il campo sta a **280**, con 960
byte di scarto, oltre la fine della struct AC1 (~324 B) → legge zeri.

`_car_xz` (`reader.py:224-252`) corregge lo shift **solo** per le coordinate. Sono rotti
allo stesso modo: `penalty`, `isInPitLane`, `windSpeed`, `mandatoryPitDone`, `flag`.
È un bug del prodotto **oggi**, indipendente da questa feature, e costa ~10 righe.

### 4.2 ACC — struct troncata

`SPageFileGraphics` si ferma ad `ABS` (`structs.py:172`). `trackGripStatus` e
`rainIntensity` stanno dopo, separati da ~40 campi da dichiarare **nell'ordine esatto
della documentazione ufficiale**, mai a memoria.

Un test su `ctypes.sizeof` è necessario ma **non sufficiente**: scambiare due `_INT`
adiacenti passa il test e legge spazzatura. Serve una seconda guardia a lettura — range
sanity (`trackGripStatus` 0..6, `rainIntensity` 0..6) con clamp a "unknown", come già
si fa per ACC_EXTRA (`structs.py:164-166`).

### 4.3 AC — la pioggia sta in una seconda shared memory

Setup rilevato: CSP 0.2.11 + Pure LCS, controller `pureCtrl static`, weather type Sol
completi. La pioggia **non è** nella shared memory standard: CSP la espone su
`AcTools.CSP.Limited.v*`. È API di terze parti, da trattare come opzionale e
degradabile. `pureCtrl static` significa meteo costante per sessione, quindi il modello
attuale (una lettura per giro) è corretto per AC.

Per ACC dinamico servirebbe invece un **canale meteo per-sample** (`SAMPLE_FIELDS`,
`lap.py:43-63`, non ne ha nessuno) e un bump di schema — non basta una seconda lettura.

---

## 5. Onestà statistica — vincoli non negoziabili

Il campione è piccolo e segmentarlo lo rende più piccolo. Le soglie della revisione 1
erano inventate; queste sono calcolate.

- **n_min = 8 giri puliti per classe**, non 3-5. Per rilevare 120 ms (`SIGNIF_LOSS_MS`)
  con σ ≈ 150 ms a potenza 80% servono n ≈ 12; e i giri non sono indipendenti
  (clusterizzati per stint, ICC ≈ 0.3 → 15 giri nominali ne valgono 7 effettivi).
  Sotto n=8, «sistematico» richiede **unanimità**.
- **Il null non è p=0.5.** Il riferimento è il tuo giro migliore, quindi quasi ogni
  curva perde tempo contro di esso. Con 14 curve a n=5 si producono **~7 curve
  "sistematiche" da puro rumore**. Serve un binomiale esatto contro p₀ = 0.5.
- **Non testare la griglia.** 4 tipi × 2 direzioni × 3 fasi × 8 categorie = 192 celle su
  ~98 osservazioni; anche solo 20 celle popolate danno FWER 64%. Un solo test primario
  (tipo × fase, 12 celle), con direzione e categoria come **descrittori** della cella
  già selezionata. Benjamini-Hochberg (FDR 0.10) su ciò che sopravvive.
- **Controllare l'apprendimento.** Le classi di condizione sono clusterizzate nel tempo:
  «meglio sull'asciutto» può voler dire «asciutto = tre mesi dopo». L'indice temporale
  come covariata è **gratis** (`recorded_utc` c'è già) ed è il confonditore più grande.
- **`setup_hash` sul giro**: oggi non esiste, e senza di esso ogni confronto fra classi
  può essere confuso da un cambio di setup. Costa poco, va aggiunto presto.
- **Intervalli, non verdetti.** Perdita mediana + intervallo di confidenza, con n sempre
  visibile e la frase «su 5 giri non posso distinguerlo dal rumore». Un intervallo che
  include zero è informazione onesta.

---

## 6. Ordine

| # | Passo | Costo | Perché qui |
|---|---|---|---|
| 1 | **Bug di offset AC1** (§4.1) | ~2 ore | Bug attivo che rompe 6 campi su AC. Prerequisito di qualunque discorso su `grip` |
| 2 | **Classificazione curve** (§3.1) | ~1 gg | Il pezzo verificato stabile su dati reali. Indipendente da tutto il resto, nessun rischio |
| 3 | **Decisione architetturale profilo** (§3.4) | ~0.5 gg | `path` o DB separato. Prima di scrivere una riga di persistenza |
| 4 | **Classe condizione + riferimento** (§3.2-3.3) | ~1.5-2 gg | Corregge un difetto attivo. Su `tyre_compound` + `road_temp`, **non** su `grip` |
| 5 | **Struct ACC estesa** (§4.2) | ~1 gg con test | Migliora la classe di condizione su ACC |
| 6 | **Persistenza eventi, silenziosa** (§3.4) | ~2 gg | **Dopo** i fix ai cue. Scrive, non mostra |
| 7 | **Output nel debrief** (§3.5) | ~1 gg | Solo quando le tabelle contengono dati di cui fidarsi |
| — | ~~CSP shared memory su AC~~ (§4.3) | — | **Tagliato dalla v1**: dipendenza da terze parti per una minoranza di casi |

Totale ~7-8 giorni, contro i ~5 stimati nella revisione 1.

---

## 7. Fuori portata

- Consigli assoluti non derivati dai dati dell'utente («a Spa si frena al cartello 100»).
- Database di piste, traiettorie ideali, punti di frenata teorici.
- Qualsiasi componente cloud o confronto con altri piloti.
- Meteo previsionale (`rainIntensityIn10min/30min`): è strategia di gara, non
  miglioramento del pilota.
- Profilo **cross-combo** («succede anche a Monza»): rinviato, vedi §3.4.
- Consigli di setup per condizione: dominio dell'Ingegnere, semmai un seguito.

---

## 8. Rischi

- **Falsi positivi cristallizzati.** Con burst-lock ancora aperto
  (`PIANO-CALIBRAZIONI.md:159-162`) un profilo persistente registrerebbe un evento
  moltiplicato ×5 e lo ripresenterebbe come tendenza. Un falso transitorio è un
  fastidio; scritto in tabella e mostrato come «ricorrente, 5 giri su 7» diventa
  un'accusa **che il pilota sa essere falsa** — e lì non si perde quel cue, si perde la
  fiducia nell'intero livello diagnostico, che è il differenziatore del prodotto.
  Pesare il recente **non** mitiga: i falsi sono continui, non vecchi. Mitigazione vera:
  §3.4, scrivere senza mostrare.
- **Bug silenzioso da disallineamento struct** (§4.2): mitigato da `sizeof` + range sanity.
- **Dati derivati in una cache cancellabile** (§3.4): mitigato dalla decisione al passo 3.
- **Un file giro corrotto** è già presente su disco
  (`imola__mclaren-720s-gt3-evo__1m50s460`, gzip illeggibile): il catalogo deve
  degradare, non fallire.

---

## 9. Bug trovati durante la revisione, indipendenti da questa feature

1. **`trends.py:71` — soglia "ricorrente" sbagliata.** `round(recur_frac * n)` con il
   banker's rounding di Python dà `round(2.5) = 2`: a n=5 la soglia dichiarata ≥50% è
   in realtà **40%**, a n=9 è **44%**. Fix: `ceil`.
2. **Offset AC1** (§4.1): `surfaceGrip`, `penalty`, `isInPitLane`, `windSpeed`,
   `mandatoryPitDone`, `flag` leggono zeri su AC.
3. **`lap_time_consistency`** (`debrief.py:330`) usa varianza di popolazione (÷n): a n=5
   sottostima σ dell'11%. E `spread = max−min` cresce meccanicamente con n, quindi non è
   confrontabile fra sessioni di lunghezza diversa.
