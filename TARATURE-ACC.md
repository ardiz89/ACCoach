# Tarature su ACC — piano per la prossima sessione in pista

> **Stato al 2026-07-27: su ACC non è mai stata tarata nessuna soglia.** Tutte le
> tarature del coach vengono da tre sessioni su **Assetto Corsa** (vedi
> `PIANO-CALIBRAZIONI.md`): M4 GT3 a Monza, SF25 al Nürburgring, M3 E92 a Suzuka.
> ACC ha cominciato a registrare un giro solo il 20 luglio 2026 (PR #22).
>
> Questo documento è la voce **11** della `ROADMAP.md`. È l'unica voce ferma su
> di te: nessuna riga di codice la sblocca. Serve una sessione guidata.
>
> Come funziona, come nelle sessioni AC: tu guidi come indicato, i comandi li
> lanci col prefisso `!` oppure dici "pronto" e li avvio io. Ogni voce ha un
> **criterio di promozione** netto. Se non lo passa, **la soglia resta com'è** e
> la diagnosi corrispondente resta non fidata: non si inventa un numero per
> chiudere la casella.

---

## Perché non basta dire «vale anche su ACC»

Tre motivi, in ordine di forza.

**1. Il canale su cui poggiano bloccaggi e pattinamenti ha una sorgente diversa
sui due giochi.** In `telemetry/reader.py::_slip_ratio`:

- su **AC** il rapporto di slittamento non esiste come campo, e lo calcoliamo
  noi: `(wheelAngularSpeed × tyreRadius − v) / v`;
- su **ACC** `tyreRadius` resta a zero (un residuo di AC1 che ACC non riempie) e
  leggiamo il campo **nativo** `slipRatio`.

Stesso nome, stesso significato fisico, **due numeri prodotti da due strade
diverse**. `_LOCK_RATIO = -0.15` e gli `spin_ratio` per classe (0.12 / 0.13 /
0.15) sono stati misurati sul primo. Che valgano anche sul secondo è
un'assunzione, e finora nessuno l'ha misurata.

**2. Non c'è materiale ACC su cui rifare i conti a tavolino.** Nei 39 giri
registrati non ce n'è uno che porti dati che solo ACC riempie: i livelli aiuti
sono `-1` su tutti e nessun giro arriva allo schema v9. Qualunque numero ACC va
quindi *guidato*, non estratto dallo storico.

**3. Metà delle diagnosi che il coach oggi pronuncia sono nate dopo l'ultima
sessione in pista.** Gas parziale, sollevamento in zona di pieno, velocità di
punta come indizio d'ala, cerchio di aderenza, riferimenti visivi di staccata,
svezzamento del countdown: tutte spedite fra il 22 e il 27 luglio, tutte provate
solo su giri registrati. Nessuna ha mai parlato a un pilota in movimento.

### Cosa invece NON è in dubbio

Da non rifare da zero — ma il primo passo di ogni sessione le riconferma in due
minuti, perché costano poco e reggono tutto il resto:

| Taratura | Dove è stata misurata | Su ACC |
|---|---|---|
| `_YAW_SIGN = -1.0` | 3 classi, 100% dei frame in curva pulita | riconfermare in 2 min (`verify-yaw`), non ricalibrare |
| `_LOCK_RATIO = -0.15` | 3 classi, margine netto su tutte | **da rimisurare**: canale con sorgente diversa (motivo 1) |
| `spin_ratio` per classe | 3 classi, ceiling pulito misurato | **da rimisurare**, stesso motivo |
| `UNDERSTEER_FRAC = 0.45` | baseline yaw per classe, dai giri registrati | riconfermare che non spari falsi |
| `trail_brake_cue` spento su Stradali | 6 falsi, 0 veri sulla M3 | invariato: su ACC non ci sono stradali |

---

## Sessione 0 — la struttura, prima dei numeri (~15 min, box + un giro)

Nessuna di queste è una soglia: sono i campi da cui tutto il resto legge. Se uno
è sbagliato, ogni numero misurato dopo è sbagliato con lui.

### 0.1 Livelli aiuti — `verify-aids` ⚠️ **mai eseguito su ACC**
- **Perché**: `TC`, `TCCut`, `EngineMap`, `ABS` stanno nella coda della struct
  graphics (`structs.py`, offset 1268-1280). Se leggiamo byte sbagliati,
  l'ingegnere consiglia manopole a vuoto e il giro registra un setup che non è
  quello guidato (schema v9).
- **Aggiornamento 2026-07-28 — il rischio è sceso, da tavolino.** Espandendo la
  coda documentata di ACC campo per campo, `isValidLap` cade **esattamente sul
  1408 misurato in pista**. Quel numero è la somma di tutto ciò che sta sopra:
  se uno solo dei campi fosse mancante, di troppo o di dimensione sbagliata — i
  tre di riempimento prima di `TC` compresi — il totale non tornerebbe. Quindi
  **gli offset sono corroborati aritmeticamente**; resta da vedere in pista solo
  la *semantica* (che i numeri seguano il HUD), che è un controllo da 30 secondi,
  non una misura da reverse engineering. L'aritmetica è bloccata in
  `tests/test_lap_valid_acc.py`.
- **Un controllo gratis, già che ci sei**: la coda documentata chiamerebbe
  `iSplit` l'intero a 1404, che noi chiamiamo `iEstimatedLapTime`. Non lo
  leggiamo mai come dato, quindi nessun comportamento distingue i due nomi, e il
  valore misurato a Monza (142 427 ms, scala giro e non settore) dà ragione al
  nostro. Se durante 0.4 stampi anche 1396 e 1404, la questione si chiude senza
  costare un metro di pista.
- **Guida**: fermo ai box o in pista tranquilla, **ruota le manopole**: TC di due
  tacche, ABS di due, mappa motore di una. Dimmi i valori a HUD mentre lo fai.
- **Comando**: `python -m accoach verify-aids`
- **Promozione**: i valori letti **seguono** il HUD, stessi numeri. Attenzione: la
  mappa motore è 0-based da noi e il HUD mostra +1 — atteso, non è un errore.
- **Se fallisce**: restano `-1` ("sconosciuto"), l'ingegnere degrada a consigli
  direzionali e il campo setup del giro resta vuoto. Non si tira a indovinare un
  offset: si misura confrontando le tacche con i byte.

### 0.2 Assi G — `verify-g`
- **Perché**: confermato due volte, ma **sempre su AC**. `g_lat`/`g_long`
  alimentano il cerchio di aderenza, cioè la diagnosi più nuova.
- **Guida**: una frenata forte in rettilineo, poi una curva tenuta a destra e una
  a sinistra.
- **Comando**: `python -m accoach verify-g`
- **Promozione**: `✓ accel_g mapping CONFIRMED`.

### 0.3 Settori reali — `verify-sectors`
- **Perché**: la vista Settori usa `currentSectorIndex`/`sectorCount` del gioco.
  Su ACC non è mai stata verificata.
- **Guida**: un giro intero, pulito basta.
- **Promozione**: i tre split coincidono con quelli del gioco.

### 0.4 Il traguardo e la validità — un giro sporcato apposta
- **Perché**: `isValidLap` all'offset 1408 è stato **trovato per misura** e regge
  la regola del pulito su ACC (`numberOfTyresOut` su ACC è inerte: misurato a
  Monza con quattro ruote fuori, restava 0). Va visto reggere in una sessione
  vera, insieme a `lost_at` (schema v8), che dice *in che curva* il giro è morto.
- **Guida**: un giro d'uscita, poi **un giro lanciato buono**, poi un giro in cui
  **tagli deliberatamente** in un punto che ricordi (dimmi quale).
- **Promozione**: il giro buono viene registrato e conta; quello tagliato risulta
  non valido **e** `lost_at` nomina la curva giusta; l'out-lap non finisce nello
  storico e il rientro ai box non gonfia la σ della consistenza.

### 0.5 Temperature freni — vive o finte?
- **Perché**: su AC `brakeTemp` è dichiarato e mai simulato (misurato a Spa:
  fermo a 16.2 °C per secondi a 315 km/h). `monitor` per questo mostra `—` su AC
  e i numeri su ACC. Se su ACC sono vivi, è un canale in più che oggi
  raccogliamo e non usiamo.
- **Guida**: due staccate forti di fila, poi guarda il cruscotto.
- **Comando**: `python -m accoach monitor`
- **Promozione**: i quattro numeri si muovono con le staccate. Non cambia niente
  oggi: è la premessa per usarli domani.

---

## Sessione 1 — i numeri, su una GT3 ACC (~30 min in pista)

Auto consigliata: la **GT3 che guidi più spesso**, su una pista che conosci
(Monza chiude anche il punto 3.5 qui sotto). Le soglie sono per classe, e la
classe GT3 è quella su cui ACC ha senso.

### 1.1 Distribuzioni reali — `stats`
- **Comando**: `python -m accoach stats --seconds 240`
- **Guida**: 3-4 giri con **staccate forti** (qualche bloccaggio vero va bene, e
  serve), **trazioni decise** in uscita, un mix di curve lente e veloci.
- **Cosa raccoglie**: le distribuzioni dei canali nei regimi che contano —
  slip anteriore in frenata, slip posteriore in trazione, rapporto yaw/sterzo in
  curva.
- **Promozione — anteriore**: lo slip **tipico** in frenata forte pulita resta
  sopra `-0.15` (cioè non lo sfiora) e i bloccaggi **veri** lo superano netto,
  come su AC (tipico -0.066 contro lock vero -0.417). Se il tipico lo sfora, la
  soglia va rifatta dal p99 **per ACC**.
- **Promozione — posteriore**: il tetto delle uscite **pulite** resta sotto
  `0.13` (soglia GT3) e i pattinamenti veri lo superano. Su AC il tetto pulito
  GT3 era 0.12: un margine di un centesimo, quindi qui basta poco per spostarlo.
- **Promozione — sotto/sovrasterzo**: la mediana di `|yaw|/|steer|` in curva
  pulita sta vicino al `yaw_baseline` GT3 (1.95). Se su ACC è sensibilmente
  diversa, la soglia relativa (`× 0.45`) si sposta con lei e va aggiornata.

### 1.2 Falsi positivi su giro pulito — `dryrun`
- **Comando**: `python -m accoach dryrun --seconds 240` *(si ferma da solo a 240 s)*
- **Guida**: **2-3 giri puliti al tuo passo**, senza errori voluti. Poi, solo
  quando te lo dico, provoca **uno per volta**: un bloccaggio, un pattinamento in
  uscita, un sottosterzo, un sovrasterzo.
- **Promozione**: sui giri puliti i detector **tacciono quasi sempre** (meno di
  un falso ogni 2-3 curve); sui difetti provocati, ognuno viene nominato con
  numeri sensati.
- **Cosa annotare**: ogni cue che *ti sembra falso*, con la curva. È il dato più
  prezioso della giornata — le tre correzioni per classe su AC sono nate tutte da
  lì, non dai test.

### 1.3 Gas parziale in percorrenza ⚠️ **mai visto in pista**
- **Perché**: rilevatore nuovo (`braking.py`, PR #30). Scatta se il gas resta fra
  il 15% e l'85% per più di 1.2 s senza salire di 12 punti — il «1-90% tenuto»
  che i coach umani indicano come causa diretta di sottosterzo.
- **Guida**: in una curva lunga che conosci, **tieni il gas a metà** per un paio
  di secondi invece di aprire. Poi rifà la stessa curva **giusta** (coasting e
  poi pieno appena puoi).
- **Promozione**: scatta sulla prima, **tace** sulla seconda.
- **Se sbaglia**: su una GT3 in percorrenza lunga potrebbe essere normale tenere
  gas parziale — in quel caso la soglia di durata (1.2 s) sale, o il cue diventa
  per classe come il trail-brake.

### 1.4 Il coach che parla ⚠️ **mai osservato su ACC**
- **Perché**: che il coach parli subito dopo il traguardo del **primo giro
  lanciato** su ACC è stato verificato solo dai test. Con le cuffie a zero non
  l'ha mai sentito nessuno.
- **Guida**: `python -m accoach live`, out-lap, un giro lanciato, **ascolta**.
- **Promozione**: parla al momento giusto, con la curva giusta, in italiano.

### 1.5 Riferimenti visivi di staccata — solo se la pista è Monza
- **Perché**: la PR #37 spedisce cinque punti di riferimento visivi per Monza
  (cartello dei 150 m al Rettifilo, barriera arancione alla Roggia, cartello dei
  50 m a Lesmo 1, cartello dei 100 m all'Ascari, fine del verde alla Parabolica).
  Sono presi da guide pubblicate e **mai verificati in pista**: nessuno dei giri
  registrati perde per staccata anticipata, quindi la frase non è mai scattata su
  dati veri.
- **Guida**: un giro in cui **freni volutamente presto** in due o tre di quelle
  curve.
- **Promozione**: il debrief dice i metri **e** nomina il riferimento; tu guardi
  la ripetizione e confermi che il punto nominato è dove il riferimento frena
  davvero. Una descrizione che non corrisponde si **toglie**, non si aggiusta a
  occhio: la tabella in `trackdata.py` accetta il silenzio.

---

## Sessione 2 — le diagnosi da tavolino (dopo la sessione, sui giri appena guidati)

Queste non si provano in pista: parlano solo nel debrief, e per parlare hanno
bisogno di un giro registrato e di un riferimento. Si fanno **dopo**, sui giri
della sessione 1, aprendo `python -m accoach web`.

| Voce | Come verificarla | Promozione |
|---|---|---|
| **Sollevamento in zona di pieno** | in un giro, **solleva** dove il riferimento è in pieno | la nota compare, con un costo in ms plausibile per la lunghezza del rettilineo |
| **Velocità di punta → ipotesi ala** | confronta due giri con ala diversa, se ne hai | la nota compare solo con divario > 4 km/h, e dice "ala" non "sei lento" |
| **Cerchio di aderenza** | guida un giro **conservativo** e uno al limite | il conservativo dice "hai margine", quello al limite tace |
| **Titolo per livello** | confronta un tuo giro col riferimento di un pilota molto più veloce | oltre ~3% di distacco il debrief guida con **un** tema, non con 18 curve |
| **Svezzamento del countdown** | ripeti la stessa curva bene per più giri | l'overlay smette di contare la staccata **lì**, non ovunque |
| **Memoria del Focus** | chiudi tutto e riapri sulla stessa auto+pista | le curve domate restano domate |
| **Tasso di falsi offline** | `python -m accoach verify-diag <auto> <pista>` | pochi cue tecnici sui giri che tu chiami puliti |

---

## Cosa porto a casa

Per ogni voce, una riga in una tabella come quelle che chiudono
`PIANO-CALIBRAZIONI.md`: **fidato / da correggere / non applicabile**, con il
numero misurato accanto. Le soglie promosse restano; quelle bocciate si spostano
**del valore misurato**, non di un valore scelto. Le diagnosi che sparano falsi
si spengono per quella classe — come il trail-brake sulle stradali — finché non
c'è un numero che dica dove rimetterle.

E una regola che vale più di tutte, imparata su AC: **il giudizio del pilota è il
dato**. Quando dici «quella uscita era pulita» e il coach ha detto pattinamento,
hai appena misurato un falso positivo che nessun test avrebbe trovato.

---

## RISULTATI

*(da riempire in sessione — una sezione per auto/pista, come in
`PIANO-CALIBRAZIONI.md`)*

### Sessione 2026-08-02 · McLaren 720S GT3 Evo · Monza · ACC

| # | Voce | Verdetto | Evidenza |
|---|---|---|---|
| 0.1 | livelli aiuti (offset struct) | **fidato** | TC 6→5→4 e ABS 6→5→4 seguono il HUD tacca per tacca; mappa 0→1 (HUD +1, atteso); `brake_bias` segue nei due versi, 1 click = 0.002 (0.750→0.760→0.746). Corroborato una seconda volta: ad ABS spento `abs_active` = 0.000 su 7307 frame |
| 0.2 | assi G | **fidato** | picco in frenata `g_long=-1.91` / `g_lat=-0.01`; picco in curva `g_lat=-1.28` / `g_long=-0.39` |
| 0.3 | settori reali | **fidato** | 3 settori dichiarati e 3 visti, confini a 0.337 e 0.665, in ordine crescente |
| 0.4 | `isValidLap` + `lost_at` | **fidato** | taglio deliberato: il gioco invalida a `pos 0.451`, l'archivio scrive `lost_at=0.4512` e `clean=False`. La catena completa (con controllo del verso) chiama quel punto **Lesmo 1**, e i 7 nomi di Monza escono in ordine senza doppioni |
| 0.5 | temperature freni vive | **vive** | anteriori 125→**317 °C**, posteriori 108→**189 °C**, picco dentro la staccata su 4 ruote su 4. Su AC misurate ferme a 16 °C (ambiente) lo stesso giorno: la differenza fra i due giochi è confermata |
| 1.1 | `_LOCK_RATIO` su slip nativo ACC | **fidato** | ad ABS **spento**: frenata non bloccata p90 `-0.074`, bloccaggio vero p50 `-1.000` (ruota ferma). La soglia `-0.15` sta nel vuoto, con margine più largo che su AC (dove il lock vero misurava -0.417) |
| 1.1 | `spin_ratio` GT3 su slip nativo ACC | **fidato** | uscite pulite p99 `0.077`–`0.080`, pattinamenti veri `0.253`–`0.326`. Su AC il tetto pulito GT3 era 0.12 contro soglia 0.13: qui il margine è cinque volte tanto |
| 1.1 | `yaw_baseline` GT3 | **fidato** | mediana `\|yaw\|/\|steer\|` in curva pulita = **1.849** su 1682 frame, contro 1.95 dichiarato (−5%) |
| 1.2 | falsi positivi su giro pulito | **fidato, con un difetto** | 9 cue in ~1.7 giri (veleggiamento ×5, trail brake ×3, limitatore ×1), sopra il criterio «uno ogni 2-3 curve» — **ma non sono falsi**: misurato sui 4 giri archiviati, il vuoto fra rilascio freno e apertura gas è di **0.87–2.35 s** ad Ascari, Roggia e Rettifilo, tutti i giri. Il pilota conferma («non le sto sfruttando appieno»). **Difetto vero**: ad Ascari `trail_brake` e `coasting` scattano sullo stesso vuoto a 0.5 s di distanza — due frasi per un errore solo |
| 1.3 | gas parziale | non provato | |
| 1.4 | il coach parla al primo giro lanciato | non verificato | `live` ha girato tutta la sessione, ma il primo giro lanciato non è stato osservato apposta |
| 1.5 | riferimenti visivi Monza | non provato | serve un giro con staccate volutamente anticipate |

**Il fatto che non ci aspettavamo.** Su ACC con l'ABS acceso il bloccaggio
fisico **non avviene**: in 11 690 frame lo slip anteriore non è mai sceso sotto
`-0.106`. Non è un difetto della soglia — è l'ABS che fa il suo mestiere. Quindi
su ACC le due vie di `_lock_spin_segments` si dividono il lavoro in modo netto:
**con gli aiuti accesi decide il flag, con gli aiuti spenti decide lo slip**, e
oggi sono state misurate valide tutte e due (zero falsi bloccaggi sui giri
puliti).

> **Correzione del 2026-08-12.** Il paragrafo qui sopra vale per
> `_lock_spin_segments`, cioè l'analisi **dopo** il giro, e nel 2026-08-12 è
> stato letto per errore come se valesse anche per l'allarme **dal vivo**: da
> lì un'istruzione sbagliata data al pilota in macchina («lascia gli aiuti
> accesi» per provocare un bloccaggio, che con l'ABS acceso non può avvenire).
> Le due vie **non** seguono la stessa regola. Dal vivo (`events.py`), dal
> 19/07 il flag solo *apre la porta* e lo slip deve confermare. Dopo il giro
> (`diagnosis.py`) il flag decide da solo.
>
> E il «zero falsi bloccaggi sui giri puliti» non regge per la via post-giro:
> misurato il 12/08 a Monza sul 720S, con ABS 6 conta **5-7 segmenti di
> bloccaggio su giri che dal vivo erano silenziosi**, contro 7 su un giro con
> quattro bloccaggi veri (slip −1.00). Non distingue i due casi.

### Sessione 2026-08-02 · SF25 (`gp_2025_sf25`) · Red Bull Ring · AC

Fuori piano — la sessione è proseguita su AC con una Formula, che è la classe
dove restavano aperte due voci da `PIANO-CALIBRAZIONI.md`.

| Voce | Verdetto | Evidenza |
|---|---|---|
| classe riconosciuta | **fidato** | `gp_2025_sf25` → `CarClass.FORMULA` via `_FORMULA_MARKERS` |
| `spin_ratio` Formula (0.15) | **fidato, margine stretto** | uscite pulite p99 `0.114`, pattinamenti veri fino a `0.612`. Separa, ma il margine è metà di quello GT3 |
| `yaw_baseline` Formula (2.50) | **misurato 2.749** (+10%) | mediana su 1900 frame di curva pulita. **Non corretto**: un'auto sola su una pista sola non muove una costante di classe, e l'errore è nel verso prudente (baseline più bassa = sottosterzo dichiarato più tardi, semmai ne perde, non ne inventa) |
| `_LOCK_RATIO` / burst lock su Formula | **non misurato** | in 4 minuti senza ABS l'anteriore non è mai sceso sotto `-0.107`: nessun bloccaggio è avvenuto. Non è un esito, è un evento mancato. Il burst lock resta aperto |
| `grip` per gioco | **confermato** | `surface_grip` = **1.000** su AC contro **0.000** su ACC, misurato lo stesso giorno sulle due sessioni |

### Come è stata condotta (vale per la prossima)

Le istruzioni al pilota sono arrivate **a voce** e i check si sono accorti da
soli delle manovre, invece di chiedere conferma. Non è una comodità: la prima
mezz'ora è stata condotta in chat, il pilota leggeva il telefono guidando ed
**è andato a sbattere**. Da lì la regola: tutto ciò che serve mentre l'auto si
muove si dice a voce, tutto ciò che richiede una risposta si fa a macchina
ferma.

Il riconoscimento vocale (vosk, modello italiano piccolo, tutto in locale)
prende bene le **frasi intere** e male le **parole singole**: «continua» e
«basta» sono stati sbagliati due volte di fila, mentre una risposta lunga è
passata. Chiedere «sì o no» è la domanda peggiore da fargli.
