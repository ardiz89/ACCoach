# Guida a HONE — il tuo ingegnere di pista in tempo reale

HONE è un **coach di guida in tempo reale** per **Assetto Corsa** e **Assetto
Corsa Competizione**. Mentre giri ti parla (voce italiana) e ti mostra un overlay
con il distacco dal tuo giro migliore; a fine sessione ti fa un debrief e un'analisi
dettagliata nel browser. Non serve configurare nulla nel gioco: legge la telemetria
direttamente dalla memoria condivisa di AC/ACC.

Questa guida ti porta dall'avvio al primo giro coachato, fino all'analisi.

---

## 1. Cosa ti serve

- **Assetto Corsa** o **Assetto Corsa Competizione** installato.
- **HONE**, in uno dei due modi:
  - **Eseguibile** (consigliato per usarlo): doppio clic su
    `HONE.bat`. Non serve Python.
  - **Da sorgente** (per chi sviluppa): Python 3.11+, poi
    `pip install -r requirements.txt`.

I tuoi giri vengono salvati in **`Documenti/ACCoach/laps`** (stessa cartella sia
dall'exe sia da sorgente), così l'analisi li ritrova sempre.

---

## 2. Avvio in 30 secondi

1. **Avvia il gioco** e mettiti in pista in una sessione di **Prove libere**
   (Practice) con l'auto e la pista che vuoi allenare.
2. **IMPOSTA IL GIOCO IN MODALITÀ BORDERLESS** (finestra senza bordi), *non*
   fullscreen esclusivo. L'overlay trasparente non si disegna sopra un fullscreen
   esclusivo: con borderless lo vedi, con fullscreen no.
3. **Apri HONE.** Si apre l'**hub**: una finestra con sei sezioni nella barra
   laterale — **Home · Guida · Analisi · Setup · Dispositivi · Impostazioni**.
   Vai su **Guida** e premi **▶ Coach Live**.

> La Home ti mostra l'ultima sessione già analizzata, quindi dopo la prima volta
> è lì che arrivi per sapere com'è andata.

**Se ti dimentichi di premere il pulsante.** In **Impostazioni** c'è
*«Registra da solo quando parte il gioco»*: con l'hub aperto, HONE si accorge che
AC/ACC è comparso e **avvia la registrazione da sé**, così una sessione che non
hai armato non è una sessione persa. Parte **solo la registrazione silenziosa**:
voce e overlay restano spenti finché non premi tu ▶ Coach Live — un coach che si
mette a parlare perché hai aperto il gioco è un'intrusione. **Di default è
spenta**, e se fermi la registrazione a mano resta ferma: non riparte finché non
chiudi e riapri il gioco.

Da riga di comando l'equivalente è:

```
python -m accoach live           # coach vocale + overlay, in un solo processo
```

Aggiungi `--silent` se vuoi solo l'overlay senza voce.

---

## 3. Come funziona il coaching (il flusso da seguire)

Il coach ragiona come un vero ingegnere di pista: prima **ti guarda girare**, poi
ti **corregge**. Due tipi di interventi:

### a) Eventi acuti — immediati, NON serve un giro di riferimento
Dal primo metro del primo giro ti avvisa quando sbagli *in assoluto*:
- **Bloccaggio** in frenata → «Bloccaggio, alleggerisci il freno»
- **Pattinamento** in uscita → «Pattini in uscita, meno gas»
- **Sottosterzo** → «L'anteriore scivola, entra più piano»
- **Sovrasterzo** → «Sovrasterzo, sii più dolce col gas in uscita»
- **Veleggi** (né freno né gas) o **trail-braking** assente.

### b) Consigli di curva — servono un paio di giri "puliti" prima
Per dirti *dove perdi tempo e perché*, il coach ha bisogno di un **giro di
riferimento** (il tuo più veloce valido). Quindi:

1. **Fai 2 giri puliti completi** partendo dal traguardo. Il primo giro intero
   viene salvato e diventa il riferimento.
2. Dal giro successivo il coach confronta il tuo giro col riferimento e, **in
   approccio a ogni curva**, ti anticipa il consiglio per quella curva
   («Porta più velocità in curva», «Puoi frenare più tardi», «Più gas qui»…).
   È un coach che ti parla *prima* della curva, non che brontola dopo.
3. Quando prendi bene quella curva, **smette di ripeterti** quel consiglio.
4. Ogni volta che batti il tuo riferimento, da lì in poi confronti col nuovo.

> Quando NON sei sul giro buono (rientro dai box, testacoda, fuori pista) il coach
> **tace** sui consigli tecnici e ti avvisa solo sugli eventi di sicurezza.

### c) Consigli di setup — a fine giro, ogni tanto
Tra un giro e l'altro, quando un sintomo si ripete, ti suggerisce una regolazione
(pressioni gomme, livelli TC/ABS dove regolabili, bilanciamento freni). Le
pressioni vengono giudicate solo a gomme in temperatura, sul target GT3 (~27.5 psi).

### d) Come vengono registrati i giri (e se parti dai box)
Non devi fare nulla di speciale: avvia la sessione (Pratica, Hotlap, Gara) e guida.

- Il giro viene chiuso quando **passi sul traguardo**. Lo riconosce da **due
  segnali insieme**: il contatore giri del gioco e il riavvolgimento della
  posizione. Nessuno dei due basta da solo — su ACC il contatore **non conta il
  giro di ricognizione**, e senza il secondo segnale il primo giro lanciato dopo
  ogni uscita dai box andava perso. Il tempo salvato è quello ufficiale del gioco.
- Il **primo giro è quasi sempre parziale** (hai iniziato a metà pista): viene
  scartato automaticamente. I giri salvati sono solo quelli **completi,
  traguardo→traguardo**.
- **Se parti dai box:** in garage *e in corsia box* la registrazione è in pausa;
  l'**out-lap** è parziale e viene scartata; il **primo giro lanciato** vero è il
  primo che viene salvato. Anche quando **rientri ai box** quel giro non viene
  salvato, e cambiare auto/pista azzera tutto (un giro non scavalca mai due
  sessioni).
- Due qualità indipendenti del giro: **completo** (partito dalla linea → requisito
  per essere salvato) e **pulito** (nessuna uscita dai limiti della pista). Un
  giro sporco viene salvato ma **non usato come riferimento**.
- **Come si stabilisce se è pulito dipende dal gioco**, perché i due titoli
  espongono cose diverse: su **AC** si contano le ruote fuori (3 o più = sporco),
  su **ACC** si legge il verdetto del gioco stesso sui track limits. Su ACC vale
  quindi anche un taglio senza mai mettere una ruota nell'erba. Se il gioco non
  dice niente il giro resta "sconosciuto", che non è la stessa cosa di "pulito".
- Il report ti dice anche **in che curva** hai perso il giro (es. «fuori pista
  alla Variante Ascari»). I giri registrati prima della versione 8 dello schema
  non hanno questo dato: dicono che il giro è sporco, non dove.

---

## 4. Leggere l'overlay

- **Barra del delta**: si riempie a **destra in rosso** se sei più lento del
  riferimento, a **sinistra in verde** se sei più veloce.
- In alto: il tuo **PB** — cioè *contro cosa stai correndo* — e il **tempo
  previsto** se mantieni il passo. Quando sta arrivando una staccata, quello
  spazio lo prende il **conto alla rovescia in metri**, che al momento di frenare
  diventa una sola parola rossa: **FRENA**. La soglia è in *tempo*, non in
  distanza, perché dieci metri sono 0,14 s a 250 km/h e mezzo secondo in una
  curva lenta.
- Una **pastiglia** mostra l'ultimo consiglio pronunciato, e sfuma da sola.

### Quando il delta non c'è

Il delta compare **solo sui giri che possono contare**, cioè quelli cominciati
dal traguardo. Non è un guasto: un numero che confronta la corsia box con un giro
lanciato caldo schizza oltre i +30 s e pianta la barra sul fondo scala, che si
legge come un giro disastroso invece che come nessun giro. Al suo posto trovi
sempre **il motivo**:

| Cosa leggi | Che sta succedendo |
|---|---|
| *Ai box* | sei in garage o in corsia box |
| *In ricognizione* | out-lap: il coach parte dal traguardo |
| *Nessun riferimento* | non hai ancora un giro completo su questa auto+pista |
| *Giro invalidato — continua* | il gioco ha annullato questo giro (solo ACC) |
| *Giro fuori ritmo* | qui il delta **resta**: il giro è cominciato dal traguardo |
| *Via — giro lanciato* | lampeggia quando il coach ricomincia a lavorare |

Su un **giro invalidato il coach continua a parlare**: sparisce solo il
cronometro. Un giro annullato è un giro gratis — frenate, bloccaggi, gomme e
assetto si leggono uguale, e rientrare ai box è tempo buttato.

Senza riferimento, invece, resta acceso tutto ciò che non ne ha bisogno:
sotto/sovrasterzo, veleggiamento, trail brake, marce, pressioni e temperature.
Vale la pena saperlo alla prima sessione su un'auto nuova.

---

## 5. Analisi & Report (nel browser)

Finita la sessione, rivedi tutto con calma:

- Dall'hub, sezione **Analisi**: **📊 Analisi & Report (browser)**, oppure
  ```
  python -m accoach web
  ```
  Si apre da solo `http://127.0.0.1:8778`.

Cosa trovi:
- **Il giro spiegato** (è dove atterri): il giro una cosa alla volta invece di
  cinque grafici insieme. Ti dice cosa ti è costato di più, perché, e cosa farci,
  col grafico ritagliato sul tratto di cui sta parlando. Al massimo tre passi: se
  sei lontano dal passo apre col tema generale e si ferma lì, perché a quella
  distanza l'analisi curva per curva è la lente sbagliata. Sul tuo giro di
  riferimento ti dice che non c'è niente da correggere, invece di inventarsi una
  lezione.
- **Sessione**: com'è andata una sola uscita. I giri nell'ordine in cui li hai
  guidati (compresi quelli tagliati o non validi — sono giri che hai fatto, solo
  non possono fare la media), migliore, costanza, temperatura dell'asfalto, e
  **cosa è cambiato dall'ultima volta** su quella auto+pista, curva per curva.
  Clicca un giro per aprirlo in Confronto. Le sessioni sono dedotte dagli orari:
  una pausa lunga vale come sessione nuova.
  Da qui in avanti trovi anche la **benzina al giro**, misurata dal serbatoio e
  non stimata, accanto a ogni giro e come media della sessione. Sui giri
  registrati prima non compare — non è «zero litri», è «non lo sappiamo» — e non
  compare nemmeno sui giri in cui hai rifornito, perché fra i due estremi di quel
  giro c'è un rifornimento, non un consumo.
- **Confronto**: scegli auto+pista e due giri (uno da rivedere, uno di confronto).
  Tre grafici allineati alla posizione in pista — **delta sul giro**, **velocità**
  (tu vs riferimento), **gas/freno** — con le bande delle curve. Passa il mouse:
  un mirino ti dà i valori puntuali. Esporti il giro in **CSV/JSON**.
- **Mappa**: la traiettoria colorata sul distacco, i punti di frenata tuoi e del
  riferimento, e sotto **«Le tue frenate»**: la scheda dei tuoi punti di frenata,
  curva per curva. Per ognuna: **a che velocità stacchi** (è il riferimento che
  ogni auto ti dà gratis, ce l'hai sul cruscotto), in che marcia, quanto è lunga
  la staccata, la minima che porti, il **riferimento visivo** dove la pista ce
  l'ha («al cartello dei 150 m»), e la **dispersione** — di quanto si sposta il
  tuo punto di frenata da un giro all'altro, in km/h e nei metri che valgono su
  quella staccata. È misurata sui tuoi ultimi giri **nella stessa fascia di
  temperatura dell'asfalto**, e l'intestazione dice quali e a quanti gradi: le
  schede di frenata che girano sui forum non possono saperlo, ed è il motivo per
  cui i loro numeri non sono i tuoi. Si scarica in **CSV** e si **stampa** (il
  tasto 🖨 stampa solo la scheda).
- **Traiettoria**: dove sei passato, curva per curva. La curva ingrandita con la
  tua linea e quella di riferimento, e **la fascia colorata fra le due è lo
  scarto**; se a scala vera è troppo sottile per vedersi, il selettore «scarto
  ×3 / ×5» la ingrandisce (il grafico lo dichiara, e la barra di scala resta
  reale). Accanto, la stessa curva in numeri: quanto eri **dentro o fuori** in
  ingresso, all'apex e in uscita, se il tuo punto più lento cade **prima o dopo**
  di quello del riferimento, quanto stretto è l'**arco** che hai percorso e
  quanti **metri di strada in più** hai fatto. Sotto, la tabella di tutte le
  curve, scaricabile in **CSV**.
  In basso a destra del disegno c'è **il giro intero con la curva cerchiata**: due
  tornanti della stessa pista fanno la stessa immagine, e senza quello dovevi
  ricordarti tu quale avevi aperto. In alto, la **frase del debrief** per quella
  curva — la stessa, presa di peso: non è una seconda opinione.
  Sotto le due linee vedi anche **il nastro d'asfalto**. Viene da due posti:
  i 26 circuiti che HONE si porta dietro, e — se hai Assetto Corsa installato —
  i dati delle piste che hai. Le due sorgenti vengono messe in concorrenza e
  vince quella che descrive meglio *il tuo* giro; il gioco non c'entra, perché
  la pista viene riconosciuta dalla forma del giro e non dal nome. Tre
  avvertenze, tutte e tre visibili nella pagina stessa: è l'**asfalto**, non i
  limiti di pista (sui cordoli ci passi sopra di un paio di metri ed è normale);
  compare **solo se la pista trovata è davvero quella su cui hai guidato** (di
  uno stesso circuito girano versioni diverse, e una che non combacia
  disegnerebbe la strada nel posto sbagliato); e **sparisce se
  ingrandisci lo scarto ×3/×5**, perché lì la linea disegnata non è più dove sei
  passato e sembreresti fuori strada senza esserlo. Su ACC non c'è: i dati pista
  di ACC non sono leggibili.
  Sul «prima o dopo» due avvertenze che la scheda ti dà da sola. Se la curva è
  lunga, il fondo della velocità è **piatto** (a Fagnes per un centinaio di
  metri): lì due giri identici avrebbero il minimo in due punti diversi per puro
  rumore, quindi HONE scrive **«stesso punto»** e dice per quanti metri il minimo
  è piatto, invece di mandarti a inseguire una differenza che non c'è. E se in
  quella curva sei andato fuori o hai girato, non ti dice che hai apexato tardi:
  ti dice che **a 32 km/h contro 93 non c'è una traiettoria da leggere**.
- **Settori**: i tre settori (quelli **veri della pista** quando il gioco li
  pubblica, altrimenti tre terzi di posizione — la scheda dichiara quale dei
  due), il tuo tempo contro il riferimento con le barre del distacco, e il
  **giro ideale**: i tuoi migliori settori cuciti insieme, con quanto vale
  rispetto al tuo miglior giro vero. Sotto, **ogni giro settore per settore**,
  col migliore di ogni colonna in evidenza: il giro ideale dichiara un tempo che
  nessuno ha guidato, e lì vedi **di quali giri è fatto** — e se quel settore è
  stato un colpo di fortuna o un'abitudine.
- **Dinamica**: cosa faceva l'auto, non cosa hai fatto tu. G longitudinali e
  laterali col **cerchio di aderenza** (quanto del grip disponibile stavi usando
  davvero), lo **slittamento** per assale (anteriore che blocca, posteriore che
  pattina), la **rotazione** contro lo sterzo, i **giri motore** con le cambiate,
  le **gomme lungo il giro** (temperatura e pressione) e il **nastro del
  bilanciamento**: la traiettoria colorata in blu dove l'auto sottosterza e in
  rosso dove sovrasterza. È la scheda da aprire quando il debrief dice *perché* e
  tu vuoi vederlo con i tuoi occhi.
- **Andamento**: l'andamento dei tempi nel tempo, la **costanza** (migliore/media/
  scarto), e gli **errori ricorrenti** ("5× Porta più velocità in curva · Curve 1, 2").
  In cima c'è **Il tuo piano**: uno o due obiettivi presi dai tuoi punti deboli
  *sistematici* (i casuali non ci finiscono: non puoi allenare un episodio), con
  un bersaglio in secondi — «qui perdi 0.42s, portalo sotto 0.21s». Finché non
  premi **Inizia questo piano** è solo una proposta; da quel momento ha una data,
  **non cambia più** mentre ci lavori, e i giri che fai da lì in poi vengono
  misurati su quel bersaglio: «2 dei 2 giri che servono». È fatto quando il
  bersaglio regge in metà dei giri — la stessa frazione con cui una curva era
  diventata un punto debole. Le curve che il coach live ha già dichiarato
  **superate** non finiscono nel piano: la memoria di «questa curva ce l'hai» è
  una sola. Con **Cambia obiettivo** butti il piano e te ne propone uno nuovo.

Nella tendina dei giri, accanto al tempo, trovi **i gradi dell'asfalto** (es.
`2:03.732 · 37.8°`). Non è un dettaglio: fra pista fredda e pista calda i punti
di frenata si spostano di 10-20 metri, quindi due giri con temperature molto
diverse sono due circuiti diversi e confrontarli dice poco.

Sotto le schede c'è sempre **quale giro stai guardando** — tempo, riferimento,
distacco e gradi dell'asfalto — perché con otto schede è facile finire a leggere
i numeri di un giro pensando a un altro.

E l'asse orizzontale di tutti i grafici è **in metri** (`1000 m · 2000 m …`), non
in percentuale di giro: «al 50%» è un numero da convertire prima di poterci
guidare. I metri sono **misurati sulle coordinate registrate**, non `posizione ×
lunghezza della pista`; se un giro non ha coordinate, o se le sue coordinate non
tornano con velocità e tempo, l'asse torna in percentuale invece di darti una
scala sbagliata.

Due scorciatoie: **1-9** aprono le schede in ordine, **[** e **]** scorrono i
giri. (Le trovi anche passando il mouse sulle schede e sulla tendina.)

Sotto ogni curva c'è anche **dove, dentro la curva, è finito il tempo**: una
barra divisa in *ingresso · apex · uscita · tratto dopo* (passa il mouse per i
secondi di ciascun pezzo), o una frase sola quando è tutto in un punto — «di
questi, 0.21s in ingresso». Non è una stima: è quel numero **spezzato**, e i
pezzi risommano esattamente al tempo perso nella curva. Il «tratto dopo» c'è
perché il debrief attribuisce a una curva anche il rettilineo che la segue — è
lì che si paga un'uscita storta — e senza nominarlo gli altri tre non
tornerebbero.

A volte, sotto il titolo di una curva, trovi una riga col bordo azzurro che
comincia con **↩**. Vuol dire che **la perdita di quella curva non è nata lì**:
ci sei arrivato già più lento, e i km/h che ti mancano all'ingresso ce li avevi
già all'uscita della curva precedente. In quel caso è **quella** la curva su cui
lavorare — sistemata lei, questa migliora da sé. Compare solo quando i conti
tornano davvero: se il deficit l'hai creato *sul rettilineo* fra le due (un
sollevamento, una cambiata sbagliata) non ti diciamo che è colpa della curva
prima, perché non lo è.

Nel debrief, **sopra** l'elenco delle curve, possono comparire uno o due riquadri
col bordo azzurro. Sono osservazioni **sull'intero giro**, non su una curva:
- *«Sollevi dove il riferimento sta in pieno»* — con quanto ti è costato, contando
  anche il rettilineo che segue;
- *«Ti mancano N km/h di punta»* — e qui la parte che conta: se in curva vai come
  il riferimento non è l'auto a essere lenta, guarda ala e rapporti; se sei più
  lento anche in curva, è velocità in uscita e l'assetto non c'entra.

### Chi diventa il riferimento

È il tuo giro più veloce su quella auto e quella pista, con due regole sopra:

- **I giri sporchi non sono mai candidabili.** Un giro tagliato è più veloce per
  un motivo.
- **Le condizioni contano**, e sono tre: la **gomma**, la **temperatura
  dell'asfalto** e il **grip della pista**. Un giro fatto in condizioni simili a
  oggi batte uno un po' più veloce fatto in condizioni molto diverse. La gomma
  pesa più di tutto — una mescola diversa è un'altra macchina, quindi è l'ultima
  cosa a cui rinuncio; il grip è la prima. È una preferenza, non un filtro: se
  niente somiglia a oggi ti do comunque il tuo giro migliore, non "nessun
  riferimento".

  Due note oneste su questi campi. La gomma la **confronto e basta**, non la
  interpreto: su ACC la stringa è canonica (`dry_compound` / `wet_compound`), su
  AC è quella che ha scelto il mod (`Soft (S)`), e per rispondere a «i due giri
  erano sulla stessa gomma?» va benissimo lo stesso. Il **grip su ACC vale
  sempre 0**: quel gioco lascia il campo storico a zero e dice le condizioni
  altrove, in una parte della memoria che non leggiamo ancora — quindi su ACC
  quel criterio non fa niente, e il riferimento si decide su gomma e
  temperatura.

Nel **report** la stessa regola vale, ma "oggi" lì non esiste: il riferimento
viene scelto per le condizioni **del giro che stai rivedendo**. Se rivedi un giro
di un mattino freddo, il bersaglio giusto è il tuo migliore *a quel freddo*, non
il primato messo giù di sera su asfalto gommato — altrimenti ogni decimo del
debrief è meteo invece che guida. Quando il confronto risulta più lento del tuo
giro migliore, il riepilogo te lo dice e ti mostra i gradi di entrambi
(«scelto per le condizioni · asfalto 12° · il tuo 1:39.000 era a 32°»). Se scegli
tu il giro di confronto dalla tendina, comanda la tua scelta e non si tocca più.

Se sei lontano dal passo, il tuo miglior giro è un bersaglio che ti tiene dove
sei. Dalla sezione **Analisi** puoi importare un **giro di riferimento PRO** più
veloce, e da lì in poi il coach ti misura su quello.

> Vuoi solo provarlo senza gioco? `python -m accoach web --demo` carica dati finti.

### Aprire su telefono / tablet (stessa rete)

Comodo se giochi in triple monitor e vuoi il **Report** o l'**Ingegnere** su un
dispositivo a fianco:

1. Nell'hub, sezione **Dispositivi**, attiva e spunta **"Consenti l'accesso
   dagli altri dispositivi in rete"** (si ricorda nel config).
2. Compaiono due **QR code** — **Report** e **Ingegnere** — con sotto l'indirizzo
   (es. `http://192.168.1.23:8778`). **Inquadra il QR** col telefono, oppure
   digita l'indirizzo nel browser.

Note pratiche:
- Il telefono dev'essere sulla **stessa Wi-Fi / rete** del PC.
- Se **Windows** chiede il permesso al primo avvio, **consenti su reti private**.
- Il **Report** (giri salvati) basta avere aperto `web`. L'**Ingegnere in tempo
  reale** richiede anche il backend `server` attivo (lo scenario "secondo schermo").
- Lasciato spento, tutto resta solo-locale (`127.0.0.1`) come prima.

---

## 6. Debrief post-sessione (testo)

Per un riassunto rapido a fine sessione:

```
python -m accoach debrief [auto] [pista]
```

Ti elenca le curve dove hai perso più tempo, con la causa, e la tua costanza. Legge
i giri salvati: il gioco non deve essere aperto.

---

## 7. Tutti i comandi

Da un terminale: `python -m accoach <comando>` (da sorgente, `python
accoach_main.py <comando>`).

**Per guidare bastano tre comandi**, ed è quello che vedi digitando
`python -m accoach help`:

| Comando | A cosa serve |
|---|---|
| `live [--silent]` | **Coach vocale + overlay** in un processo — l'uso normale |
| `web [--demo]` | App di analisi nel browser (giri salvati, report, guida) |
| `launcher` | L'hub: la finestra con tutte le sezioni |

Il resto sono strumenti — sviluppo, validazione in pista, secondo schermo. Non
servono per guidare e stanno apposta fuori dalla prima schermata; l'elenco
completo e sempre aggiornato è:

```
python -m accoach help --all
```

Quelli che potresti volere davvero:

| Comando | A cosa serve |
|---|---|
| `debrief [auto] [pista]` | Debrief testuale post-sessione (il gioco può essere chiuso) |
| `coach [--silent]` | Coach vocale nel terminale, senza overlay |
| `recorder` | Registra solo i giri, niente coaching |
| `monitor` | Cruscotto della telemetria grezza |
| `setup show <file>` | Legge un setup ACC senza avviare il gioco |
| `selftest` | Controlla che la voce/TTS funzioni, e scrive un report |
| `logs` | Apre la cartella di log e crash report |

---

## 8. Consigli per usarlo al meglio

- **Posa un buon riferimento**: i primi 2 giri falli puliti, è il metro su cui ti
  giudicherà. Un riferimento sporco = consigli sporchi.
- **Borderless sempre**, se vuoi l'overlay.
- **Un'auto/pista per volta**: il riferimento è specifico per combinazione.
- Se il coach ti distrae mentre impari un tracciato, usa `--silent` e guarda solo
  l'overlay; riattiva la voce quando vuoi i consigli.
- Rivedi gli **errori ricorrenti** nell'Andamento: è lì che migliori il passo.

---

## 9. Risoluzione problemi

- **"Resta in attesa del gioco" / non si connette** → il gioco dev'essere aperto e
  tu in pista (stato LIVE) in una sessione. HONE legge la memoria condivisa solo
  mentre il gioco gira.
- **Non vedo l'overlay** → sei in fullscreen esclusivo. Passa a **borderless**.
- **Non sento la voce** → lancia `python -m accoach selftest` (o il pulsante): scrive
  un report e prova a parlare. Da sorgente, assicurati di aver fatto
  `pip install pyttsx3`. Serve una voce italiana di sistema (es. "Microsoft Elsa").
- **Nessun consiglio di curva** → ti manca il riferimento: fai 2 giri puliti
  completi. (Gli eventi acuti invece arrivano comunque.)
- **L'analisi non mostra i giri** → guidali prima in modalità live/recorder; finiscono
  in `Documenti/ACCoach/laps`, da cui l'app di analisi legge.

---

Buon divertimento — e occhio ai bloccaggi. 🏁
