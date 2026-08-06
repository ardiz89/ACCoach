# Com'è andata: il recap di una sessione

**Data:** 2026-08-06 · **Stato:** approvato, da pianificare

## Da dove nasce

Il pilota ha visto il **post-session report di trophi.ai** e ne ha chiesto una
nostra versione, con parole precise: *«lato utente, che non è un ingegnere, è
molto intuitiva»*. La loro schermata mette al centro un **72** — un voto sintetico
— con cinque «technique groups» votati 0-100 su un radar, il tempo medio da
guadagnare, e una riga per giro con voto e delta.

## La decisione che viene prima di tutte

**Niente voto.** È la stessa regola che questo progetto si è dato il 05/08 e ha
appena spedito col KPI per curva: una scala 0-100, i pesi fra gli aspetti e la
soglia del sufficiente sarebbero **tarati da noi** e non verificabili da nessuno.

Ma la cosa che rende quella schermata intuitiva **non è il voto**: è la forma —
un colpo d'occhio, poche famiglie, un ordine di priorità. Quella forma la
riempiamo con **decimi misurati**, e in più li facciamo tornare: le famiglie
sommano al gap, esatte. Un voto non può fare quella promessa; un decimo sì.

## Cosa risponde, e a chi

Ti alzi dal volante. Vuoi sapere **dov'è finito il tempo**, in tre secondi, senza
leggere un grafico. Oggi il report non risponde: «Il giro spiegato» è un racconto
a passi (avanti/indietro, una scheda per volta) e «Sessione» elenca i giri di
un'uscita. Un colpo d'occhio d'insieme non esiste.

## Il metro: il tuo miglior giro di quell'uscita

Ogni giro valido della sessione è confrontato col **migliore della sessione
stessa**, non col riferimento eletto per le condizioni. Il recap misura la
**costanza di quell'uscita** — «quanto lasciavo per strada oggi» — e quella
domanda non deve avere dentro il meteo di un'altra sera. Il miglior giro esce a
zero ed è il metro: è corretto, e va scritto a schermo perché non sembri un
difetto.

## L'aritmetica, e perché torna

`phases.py` taglia già la perdita di una curva in **entrata / apice / uscita /
dopo**, e la promessa che quel modulo mantiene è che le quattro parti
**risommano** alla perdita della curva, esatte — non è una stima. La finestra di
una curva va dalla sua entrata all'entrata della successiva, e l'ultima arriva a
fine giro (`_next_entry` → 1.01), quindi **le finestre sono contigue e tappezzano
il giro da lì in poi**.

Resta scoperto un solo tratto: **dal traguardo alla prima staccata**. Prende una
riga sua, il **lancio**. Allora:

    entrata + apice + uscita + dopo + lancio  =  gap del giro

esatto, per costruzione e non per fortuna. La media per giro è la media di quei
numeri, e somma alla media dei gap.

**Il segno si tiene.** Una fase in cui sei stato più veloce del tuo miglior giro
è una perdita negativa: «perdo quattro decimi in entrata e ne riprendo uno in
uscita» è una frase più vera di «perdo tre decimi da qualche parte».

## Il punto architetturale che decide il codice

`build_lap_debrief` **scarta le curve prese bene** (`cue is None or GOOD →
continue`). Fa bene: risponde alla domanda «cosa vale la pena dirti».

Il recap risponde a un'altra domanda — «dov'è finito **tutto** il tempo» — e per
quella servono anche le curve andate bene, altrimenti la somma non torna e la
promessa sopra è falsa.

Quindi: **il filtro del debrief non si tocca.** Si aggiunge una scomposizione
completa e separata, che gira su *tutte* le curve rilevate. Due domande diverse,
due funzioni, nessuna che rovina l'altra. È la stessa lezione del KPI per curva —
la curva presa bene è informazione — applicata al posto giusto invece che
piegando quello sbagliato.

## Cosa si spedisce

### A schermo

La scheda si chiama **«Com'è andata»** e **diventa quella d'ingresso**: apri il
report e la vedi. «Il giro spiegato» resta a un clic. Un riassunto che devi
cercare è un riassunto che nessuno guarda.

```
COM'È ANDATA · Monza · McLaren 720S GT3 · 18 giri · 2026-08-02 16:27

  Miglior giro della sessione   1:53.712
  Da guadagnare, in media       +2.41s     contro il tuo miglior giro di oggi

  Dove sono finiti, in media per giro
    Entrata   ████████████  −1.18s
    Apice     ██████        −0.62s
    Uscita    ████          −0.41s
    Dopo      ██            −0.20s
    Lancio    ▌             −0.00s

  Giro   Tempo       Gap      Curva peggiore
    1   1:55.204   +1.49s    Curva Grande
    2   1:54.880   +1.17s    Lesmo 1
    3   1:53.712      —      — (il tuo metro)
```

**Le righe che hanno una destinazione sono link**: una **curva** porta al Giro
spiegato su quella curva, un **giro** porta al Confronto con quel giro
selezionato. Le fasi **non** sono link: nessuna scheda di oggi mostra il tempo
per fase, e mandare il pilota su una schermata che non risponde è peggio che non
offrire il clic. (Se un giorno una scheda lo mostrerà, quel link si aggiunge
allora.) Il recap è la porta, non il magazzino.

I **nomi delle curve** vengono da `trackdata.name_corners` come in ogni altra
vista, con la mappa imparata per i numeri: un solo modo di chiamare le curve.

**Le barre** sono in scala sulla fase peggiore di quella sessione, come le altre
barre del report. Nessuna soglia nuova, nessun colore che significhi «bravo».

### Nei dati

`/api/sessions` ha già tutto quello che serve intorno — la sessione scelta per
indice, `best_path`, e i giri con i loro tempi. Il recap è **un blocco in più in
quella risposta**, non un endpoint nuovo: la selezione della sessione è già lì e
duplicarla sarebbe una seconda definizione di «quale uscita».

Forma del blocco:

```json
"recap": {
  "gain_avg_s": 2.41,
  "phases": [{"phase": "entry", "avg_s": 1.18}, …, {"phase": "launch", "avg_s": 0.00}],
  "laps": [{"path": "…", "lap_time": "1:55.204", "gap_s": 1.49,
            "worst_corner_index": 3, "worst_corner": "Curva Grande", "worst_s": 0.62}],
  "reference_lap": "1:53.712"
}
```

**Il segno, una volta sola.** Nel payload il numero è **positivo quando hai
perso** tempo (come `lost_ms` ovunque nel progetto) e negativo quando ne hai
guadagnato. A schermo si legge dal punto di vista del pilota — perdere è meno
tempo tuo, quindi `−1.18s` — e a girarlo è il frontend, come fa già la carta
della curva. Una sola conversione, in un posto solo.

**`null` quando non c'è niente da dire**, mai zeri finti: una sessione con **un
solo giro valido** non ha un gap (il migliore è l'unico), e la scheda lo scrive.

## I limiti, dichiarati

- Il metro è **il tuo miglior giro di oggi**. Un recap tutto verde non dice che
  sei veloce: dice che sei stato **costante**. Va scritto dove il pilota lo legge.
- Le fasi sono misurate, ma **i confini fra loro no**: l'apex è ±0.02 di
  tracciato attorno all'apice, ereditato da `diagnosis.py` perché una parola
  significhi un posto solo. Spostando quel numero le righe si spostano. Va nella
  guida accanto alle altre soglie.
- Il **lancio** non è una fase di guida: è il tratto che le curve non coprono. Si
  chiama così, e non «altro», perché «altro» è dove si nascondono gli errori.

## Costo

`build_lap_debrief` costa **7,4 ms** su un giro ACC vero (Imola, 871 campioni, 7
curve) — misurato il 06/08. Un'uscita da 18 giri costa ~0,13 s coi giri già
caricati da disco. La scomposizione completa gira sulle stesse finestre e non
aggiunge un secondo passaggio sui campioni.

## Test

- le cinque righe **sommano al gap del giro**, esatte, su un giro sintetico e su
  un giro vero — è la promessa centrale e va pinnata con una tolleranza da
  arrotondamento, non con `approx` largo;
- una **curva presa bene** entra nella scomposizione (contributo anche zero), che
  è il caso che il debrief scarta: se sparisse, la somma non tornerebbe;
- una fase in cui sei più veloce esce **negativa**, non a zero;
- il **miglior giro della sessione** esce a gap zero e non produce una curva
  peggiore;
- una sessione con un giro valido solo → blocco assente, e la scheda lo dice;
- il debrief **non cambia**: i suoi test passano intatti (è la prova che il
  filtro non è stato piegato).

## Fuori perimetro

Il voto sintetico e il radar; il confronto con giri di altri (community o
datapack); qualunque forma di account o servizio remoto. Restiamo offline.
