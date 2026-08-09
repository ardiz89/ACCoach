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
   laterale — **Home · In pista · Analisi · Setup · Dispositivi · Impostazioni**.
   Vai su **In pista** e premi **▶ Coach Live**.

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

### b-bis) Un tema alla volta — perché a un certo punto il coach dice di meno

Dopo qualche giro pulito il coach smette di commentarti tutto ed **elegge una
debolezza**: la curva dove perdi di più, e il perché. Te lo annuncia
(«Nuovo focus — Variante Ascari: lavoriamo la frenata…»), e **da quel momento in
pista ti parla solo di quel tema**. Su tutta la pista, non solo in quella curva:
se stai frenando male, non lo stai facendo in un posto solo, ed è il *difetto*
che si allena.

E te ne parla **con una parola**, non con una frase: «meno freno», «più tardi»,
«gas». Le parole te le dichiara **prima**, nel messaggio che annuncia il focus —
*«In pista ti dirò solo parole sulla frenata, tipo «meno freno»»* — e te le
ricorda sulla riga del focus dell'overlay, così ce l'hai davanti mentre guidi.

Non è un capriccio: tre coach professionisti indipendenti impongono lo stesso
limite — **due o tre temi per sessione**, e in pista **parole di una-tre parole**
concordate prima. Il motivo che danno è sempre lo stesso, ed è il tuo: chi guida
ha una banda passante finita, e alla decima frase in tre giri non la ascolti più.

**Niente va perso.** Quello che il coach tace in pista lo trovi nel **debrief** di
fine sessione e nel report, con i suoi decimi: il debrief è calcolato sul giro,
non su quello che è stato detto, quindi le curve su cui la voce è rimasta zitta
ci sono tutte. La voce sceglie cosa dirti *adesso*; il debrief non sceglie niente.

Restano **fuori dal filtro gli eventi**: bloccaggio, pattinamento, benzina e le
chiamate ai box si sentono sempre. Non sono temi da allenare, sono cose che
stanno succedendo.

Finché un focus non c'è — i primi giri, quando ti sta ancora guardando girare —
il coach parla di tutto, come sempre. E quando la curva migliora, o non scende
dopo qualche giro, la parcheggia e passa alla successiva: cambia il tema, e
cambiano le parole.

### c) Consigli di setup — a fine giro, ogni tanto
Tra un giro e l'altro, quando un sintomo si ripete, ti suggerisce una regolazione
(pressioni gomme, livelli TC/ABS dove regolabili, bilanciamento freni). Le
pressioni vengono giudicate solo a gomme in temperatura, sul target GT3 (~27.5 psi).

Le modifiche sono di due tipi, e si chiudono in modo diverso.

- **Al volo** — una manopola che giri sul rettilineo (TC, ABS, bilanciamento
  freni). Non devi confermare niente: HONE **guarda il canale** e si accorge da
  solo quando la manopola si muove, così la prova può cominciare senza che tu
  tolga le mani dal volante. Su AC quei livelli non sono leggibili, quindi lì
  trovi un pulsante **«Fatto — l'ho cambiato»** nella pagina Ingegnere.
- **Da box** — un file di setup da scrivere. Qui non basta dirti *cosa*
  cambiare, e infatti ti dice anche **quando rientrare**.

### c-ter) Il registro: quante modifiche hanno funzionato davvero

Nella pagina **Ingegnere**, sotto la proposta, c'è il **registro**: quante delle
modifiche che ti ha proposto sono state **tenute** dopo la misura, e quante
annullate. È l'unico numero di quella pagina che non è una nostra affermazione —
è contato su prove che hai guidato tu, e può darci torto.

Ci trovi anche **quali leve si guadagnano il posto**, se regge l'ordine «prima il
rimedio più efficace», e gli **effetti collaterali** osservati (una modifica che
sistemava il sottosterzo in ingresso e ne portava uno in uscita). Quelli non li
prevediamo mai: si vedono e si scrivono.

Finché le prove sono poche **non trovi nessuna percentuale**, solo i conteggi. Un
tasso di riuscita su tre campioni è rumore travestito da percentuale.

### c-bis) Il rientro ai box

Quando c'è una modifica che richiede il garage, senti tre cose:

1. **All'inizio dell'ultimo settore** (o ~20 s prima dell'ingresso corsia, quello
   che viene prima): *«Modifica pronta: rientra ai box a fine giro»*. Il secondo
   criterio non è un doppione: su certi circuiti la corsia box si stacca dalla
   curva **prima** dell'ultimo settore, e lì una chiamata legata al settore
   arriverebbe con l'ingresso già alle spalle.
2. **Poco prima dell'ingresso**: *«Ingresso box qui davanti, rientra»*.
3. **Da fermo nel box**: cosa fare con la modifica, perché vive in una pagina del
   browser che mentre guidavi non stavi guardando.

E c'è una quarta cosa che non senti: la **vedi**. Dalla prima chiamata l'avviso
di rientro resta acceso sull'overlay finché non entri in corsia — §4, «Leggere
l'overlay».

Una cosa da sapere: **l'ingresso della corsia box nessun gioco lo pubblica**. Lo
imparo guardando dove lasci la pista la prima volta che rientri davvero, e ne
tengo la mediana su più visite. Quindi su una pista dove non sei mai rientrato
l'avviso numero 2 **non esiste**: preferisco tacere che indicarti una corsia
indovinata, per cui alzeresti il piede. Dalla seconda visita in poi c'è.

Rientrare col menu di gioco («torna ai box») non insegna niente, ed è voluto:
l'auto sparisce da metà pista e riappare in garage, e prendere per buono quel
salto vorrebbe dire piazzare l'ingresso box in mezzo a un rettilineo.

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
  Quando l'ingegnere propone una modifica che si fa **solo ai box**, il coach
  ti richiama a fine giro — e da quel momento quella pastiglia non è più
  quella dell'ultimo consiglio: è l'**avviso di rientro**, in ambra, e non
  sfuma. Resta finché non entri in corsia box, o finché la modifica non è più
  in sospeso (per esempio se viene ritirata): un richiamo che sparisce dopo
  due secondi è un richiamo che ti perdi se in quel momento stavi guardando la
  curva davanti. I consigli continuano a essere **detti**: cedono solo quella
  riga, e la riprendono appena l'avviso si spegne.
- Sotto, una riga sottile in ambra: il **focus**, cioè su cosa stai lavorando —
  tema, curva e i decimi che ci perdi. Quando il coach è passato alle
  parole-innesco (§3, «Un tema alla volta») lì c'è anche **la parola** che
  sentirai, tipo «MENO FRENO»: la frase intera resta nella pastiglia e nel
  debrief, la riga del focus ti ricorda solo cosa vuol dire quella parola.

### La traccia dei pedali (per il trail braking)

Si accende da **Impostazioni → Mostra la traccia dei pedali**, ed è **spenta di
default** perché allunga l'overlay: tienila accesa quando stai lavorando sul
rilascio del freno, spenta quando vuoi lo schermo pulito.

È una striscia sotto l'HUD con il tuo **gas in verde** e il tuo **freno in
rosso** mentre succedono, negli ultimi secondi. Sotto le due tracce c'è un
nastro che si colora da solo:

| Nastro | Cosa stai facendo |
|---|---|
| **ambra** | premi tutti e due i pedali → **stai trailando** |
| **grigio** | non ne premi nessuno → **tempo morto**, tempo regalato |
| niente | rilascio pulito: hai mollato il freno e ripreso il gas senza vuoto |

In alto a destra la stessa cosa in una parola — **TRAIL**, oppure **COAST** col
cronometro di quanto stai veleggiando.

Serve per una ragione precisa: il coach il trail braking te lo **dice**, ma te lo
dice a cose fatte. Qui lo **vedi mentre lo fai**, che è l'unico modo di correggere
un rilascio — la sovrapposizione fra le due curve è, letteralmente, il tuo trail
braking disegnato.

> Il consiglio a voce sul trail braking è **spento sulle stradali**: lì portare
> il freno fino all'inserimento fa girare l'auto, e su una macchina senza carico
> aerodinamico mollarlo tardi la fa partire. La traccia invece resta, perché
> guardare non è farsi dire cosa fare.

### Il numero della curva

In basso, dopo ogni curva: **quanto ti è costata quella curva** rispetto al tuo
riferimento, e un pallino colorato. Resta lì finché non chiudi la curva dopo.

| Colore | Cosa dice |
|---|---|
| **ciano** | hai guadagnato **almeno 0,25 s**: è la stessa soglia con cui il coach ti fa i complimenti |
| **verde** | sei nella norma: fra 0,25 s di guadagno e 0,12 s di perdita |
| **giallo** | perdi **da 0,12 a 0,25 s**: 0,12 è la soglia con cui il coach apre bocca |
| **rosso** | perdi **più di 0,25 s** |

Tre cose da sapere, perché sembrano guasti e non lo sono:

- **Il numero è misurato, il colore è tarato.** I decimi li puoi rifare a mano;
  le soglie dei colori le abbiamo scelte noi — sono le stesse due con cui il
  coach decide se parlare, così colore e voce non possono dirti cose diverse.
- **È relativo al *tuo* riferimento**, quello eletto per le condizioni di oggi.
  Se il tuo miglior giro è lento, il verde non dice che sei veloce: dice che sei
  **costante**.
- **Alla prima sessione su un'auto o una pista nuova il riquadro non c'è**, e
  non c'è nemmeno un trattino: senza un giro tuo completo non c'è niente contro
  cui misurare, e un numero inventato sarebbe peggio di nessun numero. Sparisce
  anche ai box, in ricognizione e sui giri fuori ritmo.

Il consiglio a voce **non cambia**: arriva sempre all'*ingresso* della stessa
curva al giro successivo, dove puoi ancora farci qualcosa. Il numero è un
consuntivo, e per questo può stare zitto.

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

### Com'è andata (la prima schermata)

Apri il report e la prima cosa che vedi è **l'ultima uscita**: quanto lasciavi
per strada in media, e dove.

Le cinque righe — **entrata, apice, uscita, dopo, lancio** — non sono un voto:
sono i **secondi** che quella parte del giro ti è costata, e sommano **al
numero grande in alto**. Quel numero non è il distacco che leggi a cronometro:
è misurato sull'orologio della telemetria, che sui giri veri si scosta anche
di un decimo da quello del gioco. Se sommi le cinque righe a mano ti torna
comunque lui: è fatto apposta, ed è la differenza fra un dato e una pagella.

Tre cose da sapere:

- **Il metro è il tuo miglior giro di quell'uscita**, non il tuo record. Quindi
  misura la **costanza** di quel pomeriggio: numeri piccoli non vogliono dire
  che eri veloce, vogliono dire che eri ripetibile — un pomeriggio lento ma
  costante mostra numeri piccoli lo stesso. Ed è per questo che il tuo giro
  migliore **non compare nell'elenco dei giri**: è lui il metro, e mostrarlo
  sarebbe una riga di zeri.
- **«Lancio» non è una fase di guida.** È il tratto dal traguardo alla prima
  staccata, che non appartiene a nessuna curva. Ha una riga sua perché senza di
  lui la somma non tornerebbe, e una somma che non torna è una somma che non
  puoi controllare.
- **Quando in quell'uscita non c'è ancora abbastanza per misurarlo, la
  schermata lo dice** invece di mostrarti uno zero: un dato mancante dichiarato
  tale è meglio di un numero che sembra vero e non lo è.

Cosa trovi nelle altre schede:
- **Il giro spiegato** (la seconda scheda): il giro una cosa alla volta invece di
  cinque grafici insieme. Ti dice cosa ti è costato di più, perché, e cosa farci,
  col grafico ritagliato sul tratto di cui sta parlando. Al massimo tre passi: se
  sei lontano dal passo apre col tema generale e si ferma lì, perché a quella
  distanza l'analisi curva per curva è la lente sbagliata. Sul tuo giro di
  riferimento ti dice che non c'è niente da correggere, invece di inventarsi una
  lezione.
- **Allenamento**: la scheda che risponde alla domanda che tutte le altre
  lasciano aperta — *e adesso come mi alleno?*. Parte da dove sei e da dove puoi
  arrivare: il tuo miglior giro contro il tuo **ideale teorico** (i tuoi settori
  migliori ricuciti), che non è un tempo inventato — l'hai già guidato tutto,
  solo mai nello stesso giro — e ti dice **in quale settore** sta il grosso di
  quel divario. Sotto, il programma: al massimo tre passi, **uno alla volta**, e
  solo il primo è aperto. Ogni passo porta un **esercizio vero**: quanti giri
  farlo, cosa fare giro per giro, **cosa guardare** e **cosa ignorare di
  proposito**, più il numero che dice quando è fatto. L'esercizio non è generico:
  viene scelto da dove *dentro la curva* stai perdendo il tempo — se il tempo se
  ne va in staccata ti fa spostare il punto di frenata un'auto per volta, se se
  ne va all'apex ti fa prima misurare quanta velocità la macchina regge davvero,
  se se ne va in uscita ti fa costruire l'uscita prima dell'apex — e dentro ci
  sono i **tuoi** numeri: a che velocità stacchi lì, di quanto ti sposti da un
  giro all'altro, che minima porti contro quella del riferimento. In fondo c'è
  **la tua prossima sessione**, in giri: riscaldamento, i giri di esercizio, e
  qualche giro libero per vedere se è entrato quando smetti di pensarci.

  Qui vive anche **Il tuo piano** (prima stava in Andamento): uno o due obiettivi
  presi dai tuoi punti deboli *sistematici* (i casuali non ci finiscono: non puoi
  allenare un episodio), con un bersaglio in secondi — «qui perdi 0.42s, portalo
  sotto 0.21s». Finché non premi **Inizia questo piano** è solo una proposta; da
  quel momento ha una data, **non cambia più** mentre ci lavori, e i giri che fai
  da lì in poi vengono misurati su quel bersaglio: «2 dei 2 giri che servono». È
  fatto quando il bersaglio regge in metà dei giri — la stessa frazione con cui
  una curva era diventata un punto debole. Le curve che il coach live ha già
  dichiarato **superate** non ci finiscono: la memoria di «questa curva ce l'hai»
  è una sola. Con **Cambia obiettivo** butti il piano e te ne propone uno nuovo.

  **La scheda si apre solo quando ha di che parlare**: servono **6 giri validi**
  su quella auto e quella pista, e almeno una debolezza che si ripeta. Sotto
  quella soglia non trovi una pagina vuota, trovi quanti giri mancano — sei giri
  ne lasciano cinque da confrontare col tuo riferimento, e una debolezza per
  chiamarsi tale deve tornare in tre di quei cinque. Con meno, quello che sembra
  un punto debole è quello che hanno fatto due giri, e un programma costruito lì
  sopra cambierebbe ogni volta che guidi.

  Una cosa che la scheda dice e vale la pena leggere due volte: i due numeri di
  tempo che vedi **non si sommano**. Il divario dall'ideale teorico e quello che
  perdi in media ogni giro nelle curve sono la stessa strada misurata in due
  modi, e sommarli conterebbe due volte lo stesso tempo.

  **È la scheda scritta per chi non mastica telemetria**, quindi è anche l'unica
  che si spiega le parole mentre le usa: «l'ideale teorico» viene prima
  descritto («i tuoi tempi migliori, uno per settore, messi insieme») e poi
  nominato, e i termini che restano — apex, settore, velocità minima — sono
  spiegati dentro l'esercizio che li usa, perché a schermo ne è aperto uno solo.
  Dove una parola comune bastava, c'è quella: *il punto in cui inizi a frenare*,
  non *la staccata*.

  In fondo alla scheda c'è **«Le parole che sentirai dire dagli altri»**: un
  dizionario di poche voci, chiuso, che mostra i termini in fila. Lo scorri e lo
  apri solo per la parola che non conosci. Non è mai l'unico posto in cui una
  parola è spiegata — l'esercizio sopra la spiega comunque — e contiene solo i
  termini dell'esercizio che hai aperto in quel momento.

  Gli esercizi **non sono uguali per tutte le auto** dove la differenza conta:
  su una stradale a basso carico HONE non ti fa allenare il trail braking (il
  freno trascinato dentro la curva), perché su quelle auto la tecnica corretta è
  rallentare dritti e poi girare — è la stessa decisione, presa sugli stessi
  dati, per cui il coach in tempo reale su quelle auto sta zitto. Al suo posto
  ricevi **«Frena dritto, poi gira»**.
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
- **Passo gara**: come regge il passo su **un pieno solo**. È un taglio diverso da
  Sessione, e la differenza è misurata: una sessione la deduciamo dagli orari, e
  dentro una sola uscita ci può stare un **rifornimento** — mediare il passo
  attraverso quel confine media due carichi di benzina e chiama costanza il
  risultato. Lo stint invece si taglia dove il serbatoio **risale**, confrontando
  quanto ne resta a fine giro con quanto ce n'è all'inizio del successivo.
  Per ogni stint: il **passo** (mediana dei giri che erano davvero un passo — un
  testacoda resta nella lista ma non fa la media), la **dispersione**, il consumo
  al giro e i giri che ti restano nel serbatoio, il grafico del passo giro per
  giro e le **gomme lungo lo stint** (temperature e pressioni per ruota).
  E poi la cosa che vale più dei numeri: **cosa quei numeri non dicono**. La
  pendenza del passo è un valore **netto** — lo stint accelera perché il
  serbatoio si svuota e rallenta perché le gomme mollano — e per separare le due
  cose serve sapere quanto vale un litro in secondi, che oggi **non lo sappiamo**
  (va misurato guidando uno stint apposta a passo costante). Quindi la pendenza
  esce con la sua barra d'errore, e quando è più piccola di quella barra la
  scheda scrive **«nessuna deriva misurabile»** invece di inventarti un degrado.
  Non è nemmeno usura gomme: nessuno dei due simulatori pubblica un'usura che
  registriamo, quello che vedi è la temperatura.
- **Confronto**: scegli auto+pista e due giri (uno da rivedere, uno di confronto).
  Tre grafici allineati alla posizione in pista — **delta sul giro**, **velocità**
  (tu vs riferimento), **gas/freno** — con le bande delle curve. Passa il mouse:
  un mirino ti dà i valori puntuali. Esporti il giro in **CSV/JSON**.
- **Mappa**: la traiettoria colorata sul distacco, i punti di frenata tuoi e del
  riferimento, e le curve **chiamate per nome** (non più «T1, T2»: sono gli stessi
  nomi del resto della pagina, compresi quelli che hai scritto tu). Se il giro è
  stato buttato c'è una **✕ nel punto in cui l'hai perso**. Sotto,
  **«Le tue frenate»**: la scheda dei tuoi punti di frenata,
  curva per curva. Per ognuna: **a che velocità stacchi** (è il riferimento che
  ogni auto ti dà gratis, ce l'hai sul cruscotto), in che marcia, quanto è lunga
  la staccata, la minima che porti, il **riferimento visivo** dove la pista ce
  l'ha («al cartello dei 150 m») — e dove non ce l'ha, **scrivilo tu**: quella
  cella si apre e il tuo riferimento entra nella scheda e nella voce del coach.
  Serviva: le posizioni erano misurate da un pezzo, le *parole* no, perché su
  Imola due guide indipendenti si contraddicono su quasi ogni curva e nessuna
  misura può arbitrare fra un cartello dei 50 e uno dei 100. Tu la curva ce
  l'hai davanti. E la **dispersione** — di quanto si sposta il
  tuo punto di frenata da un giro all'altro, in km/h e nei metri che valgono su
  quella staccata. È misurata sui tuoi ultimi giri **nella stessa fascia di
  temperatura dell'asfalto**, e l'intestazione dice quali e a quanti gradi: le
  schede di frenata che girano sui forum non possono saperlo, ed è il motivo per
  cui i loro numeri non sono i tuoi. Si scarica in **CSV** e si **stampa** (il
  tasto 🖨 stampa solo la scheda).
- **Traiettoria**: dove sei passato, curva per curva. La curva ingrandita con la
  tua linea e quella di riferimento, e **la fascia colorata fra le due è lo
  scarto**; se a scala vera è troppo sottile per vedersi, il selettore «scarto
  ×3» la ingrandisce (il grafico lo dichiara, e la barra di scala resta
  reale). Accanto, la stessa curva in numeri: quanto eri **dentro o fuori** in
  ingresso, all'apex e in uscita, se il tuo punto più lento cade **prima o dopo**
  di quello del riferimento, quanto stretto è l'**arco** che hai percorso e
  quanti **metri di strada in più** hai fatto. Sotto, la tabella di tutte le
  curve, scaricabile in **CSV**.
  Sulle due linee trovi anche **dove stacchi e dove riapri il gas** (triangolo
  pieno il tuo, anello quello del riferimento): è quello che trasforma «sei più
  largo in ingresso» in una diagnosi, perché largo *con la stessa staccata* e
  largo *staccando 15 m dopo* sono due errori diversi. Le soglie sono le stesse
  con cui misura la scheda frenate, quindi il triangolo e la riga «Freni a»
  parlano dello stesso punto.
  In basso a destra del disegno c'è **il giro intero con la curva cerchiata**: due
  tornanti della stessa pista fanno la stessa immagine, e senza quello dovevi
  ricordarti tu quale avevi aperto. In alto, la **frase del debrief** per quella
  curva — la stessa, presa di peso: non è una seconda opinione.

  **Il nome lo puoi dare tu.** Accanto al titolo della curva c'è una matita: ci
  scrivi come la chiami, e da lì in poi quel nome compare *ovunque* — nel
  debrief, nelle perdite, nella scheda frenate e nella voce del coach. Serve
  perché HONE conosce i nomi di **14 circuiti su 26**, e altri dieci circuiti
  ACC non hanno nemmeno la geometria: su quelli l'unico che sa come si chiama
  quella curva sei tu. Il tuo nome batte anche il nostro, se il nostro non ti
  piace, e si toglie con lo stesso gesto con cui si mette. Stanno in
  `Documenti/ACCoach/corner-names.json`, in chiaro: si leggono, si copiano e si
  correggono a mano.
  Sotto le due linee vedi **la pista vista dall'alto**: l'asfalto, i cordoli, e
  di fianco l'erba, la ghiaia e il cemento. Non è un disegno nostro — è la
  geometria con cui il gioco decide dove sei, letta dal suo modello delle
  superfici, pezzo per pezzo e con i tipi già separati.

  La pista viene riconosciuta **dalla forma del tuo giro, non dal nome**: i due
  simulatori non chiamano i circuiti allo stesso modo (Mount Panorama è
  `mount_panorama` per uno e `rt_bathurst` per l'altro), quindi il nome non è
  una strada affidabile per arrivarci. Se il gioco non è installato restano i
  **26 circuiti che HONE si porta dietro** (linea centrale e larghezze, da
  OpenStreetMap e da immagini satellitari): meno dettagliati — niente cordoli —
  ma indipendenti da cosa hai sul disco.

  Due avvertenze, tutte e due visibili nella pagina:

  * compare **solo se la pista trovata è davvero quella su cui hai guidato**. Di
    uno stesso circuito girano versioni diverse, e una che non combacia
    disegnerebbe la strada nel posto sbagliato;
  * **sparisce se ingrandisci lo scarto ×3**, perché lì la linea disegnata non
    è più dove sei passato e sembreresti fuori strada senza esserlo.

  E il disegno **si gira** per riempire il riquadro: una rotazione non muove un
  punto rispetto a un altro, quindi forma, larghezze e metri restano quelli e la
  barra della scala misura gli stessi metri.
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
  scarto), i **punti deboli** curva per curva (sistematici o casuali) e gli
  **errori ricorrenti** ("5× Porta più velocità in curva · Curve 1, 2"). È il
  quaderno dei conti; il piano che ne esce sta in **Allenamento**, e le gomme
  stanno in **Passo gara** — qui la serie copriva tutto l'archivio pur
  chiamandosi «lungo lo stint».

Nella tendina dei giri, accanto al tempo, trovi **i gradi dell'asfalto** (es.
`2:03.732 · 37.8°`). Non è un dettaglio: fra pista fredda e pista calda i punti
di frenata si spostano di 10-20 metri, quindi due giri con temperature molto
diverse sono due circuiti diversi e confrontarli dice poco.

Sotto le schede c'è sempre **quale giro stai guardando** — tempo, riferimento,
distacco e gradi dell'asfalto — perché con tutte queste schede è facile finire a leggere
i numeri di un giro pensando a un altro.

E l'asse orizzontale di tutti i grafici è **in metri** (`1000 m · 2000 m …`), non
in percentuale di giro: «al 50%» è un numero da convertire prima di poterci
guidare. I metri sono **misurati sulle coordinate registrate**, non `posizione ×
lunghezza della pista`; se un giro non ha coordinate, o se le sue coordinate non
tornano con velocità e tempo, l'asse torna in percentuale invece di darti una
scala sbagliata.

Due scorciatoie: **ogni scheda ha un tasto che la apre**, in ordine da
sinistra a destra, e lo vedi passandoci sopra il mouse (vale anche per la
tendina dei giri); **[** e **]** scorrono i giri.

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

### Curva per sessione

Sotto i punti deboli, per ogni curva **sistematica**: la perdita mediana in
quella curva, **una barra per sessione**. Due uscite nello stesso pomeriggio
restano due barre — è lì che si vede se la cosa che hai cambiato fra l'una e
l'altra ha funzionato.

Due soglie, e si compongono: una sessione in cui hai fatto **meno di tre
giri** su quella curva non compare — una mediana su due giri è l'ultimo giro
con un nome più serio — e una sessione assente **non** viene disegnata a
zero, perché lo zero qui vuol dire «l'hai presa bene», che è un'altra cosa
dal non avere il dato. E la curva **intera** compare solo con **almeno due
sessioni** che superano quella prima soglia: un punto solo non è un
andamento, è un giro fortunato. Una curva appena diventata sistematica può
non avere ancora un grafico qui: prima le servono due sessioni buone, non una
sola.

### Chi diventa il riferimento

È il tuo giro più veloce su quella auto e quella pista, con due regole sopra:

- **I giri sporchi non sono mai candidabili.** Un giro tagliato è più veloce per
  un motivo.
- **Un giro che nessuno ha giudicato non batte un giro giudicato.** Su ACC il
  «pulito» dei giri registrati **prima del 21 luglio 2026** veniva da un campo
  che quel gioco dichiara e non riempie mai: dice pulito perché nessuno ha
  guardato, non perché lo fosse. Quei giri non vengono buttati — restano il tuo
  riferimento se non hai altro, perché un bersaglio dubbio batte nessun
  bersaglio — ma perdono contro qualunque giro verificato davvero. È nato da un
  caso vero: a Monza il riferimento era un 1:53.712 che **tagliava la Variante
  della Roggia** per metà curva, ed era il più veloce *proprio per quello*.
  Quando succede il riepilogo te lo dice: «scelto perché verificato — il tuo
  1:53.712 è più veloce ma nessuno ne ha mai verificato i limiti di pista».
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
| `find-rain` | Trova i campi pioggia di ACC misurandoli (serve una sessione con meteo variabile) |

### Il file di configurazione

Quasi tutto si regola da **Impostazioni**. Il resto sta in
`Documenti/ACCoach/config.toml`, che HONE crea al primo avvio con dentro un
commento per ogni voce. Si modifica a app chiusa: **i valori si leggono
all'avvio**.

Le voci che esistono *solo* lì:

| Voce | A cosa serve |
|---|---|
| `data.laps_dir` | Sposta la cartella dei giri (un altro disco, una cartella sincronizzata). Vuota = `Documenti/ACCoach/laps` |
| `acquire.hz` | Quanti campioni al secondo legge il registratore |
| `server.host` · `server.port` · `server.hz` | Interfaccia, porta e ritmo del backend live |
| `web.port` | Porta dell'app di analisi |
| `logging.level` · `logging.console` | Quanto scrivono i log |

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
- **Le parole-innesco suonano peggio delle frasi** → è vero, e lo sappiamo. Le
  frasi fisse escono da una voce **neurale** pre-registrata; le parole-innesco
  del focus non sono ancora state registrate, quindi per ora escono dalla voce
  **di sistema**, che è più robotica. Ci stiamo lavorando: cambia il suono, non
  quello che ti viene detto.
- **Nessun consiglio di curva** → ti manca il riferimento: fai 2 giri puliti
  completi. (Gli eventi acuti invece arrivano comunque.)
- **L'analisi non mostra i giri** → guidali prima in modalità live/recorder; finiscono
  in `Documenti/ACCoach/laps`, da cui l'app di analisi legge.

---

Buon divertimento — e occhio ai bloccaggi. 🏁
