# Spike: l'occhio anticipa la curva?

> Proposta dell'utente (2026-07-27): usare la webcam durante le sessioni di
> allenamento per capire **se lo sguardo anticipa le curve e la direzione
> dell'auto**.
>
> Stato: **spike, non feature.** Vive in `tools/gaze_spike.py`, non entra nel
> bundle (`HONE.spec` non lo include, `requirements.txt` non cambia). Serve a
> rispondere a una domanda in qualche giorno invece di scoprire la risposta dopo
> sei settimane di lavoro.

---

## Cosa ne ha detto il team

Tre pareri indipendenti — ingegnere di pista GT3, analista di telemetria,
sviluppatore dashboard/packaging. Hanno **ucciso la stessa cosa** e **salvato le
stesse due**.

**Morto: «dove guardi sullo schermo».** Una webcam consumer sbaglia la direzione
dello sguardo di 4-8° in condizioni reali (luce di una stanza, occhiali, testa
che si muove): su un monitor a 60 cm sono **4-8 cm**. Un punto di fissazione
utile richiede meno di 1,5°. E c'è un argomento peggiore del sensore:
su un monitor da 27-32" il campo visivo è ~45°, dentro cui l'apex **ci sta
già** — la tecnica che vorremmo insegnare («ruota la testa, guarda l'uscita»)
in quel contesto non è nemmeno eseguibile. Misureremmo saccadi da 5° dove in
pista ce ne sono 40.

**Vivo 1: le misure di tempo, non di posizione.** «Lo sguardo si è mosso prima o
dopo lo sterzo» è *change detection* su un segnale relativo a sé stesso: non
richiede calibrazione, e un errore angolare costante si semplifica nella
differenza. È la misura più difendibile che si possa fare con questo sensore, ed
è esattamente quella che l'utente ha chiesto.

**Vivo 2: quanto il pilota guarda il nostro overlay.** Non è coaching, è **QA del
nostro prodotto**: abbiamo l'evidenza raccolta su Reddit («è facile guidare i
toni di frenata invece dell'auto») e abbiamo già spedito la cura — lo
svezzamento della PR #34 — che però oggi scatta su un *proxy* («questa curva
l'hai fatta bene N volte»), non su una misura dell'attenzione. Un esperimento
una tantum, non una funzione.

**Costi che hanno pesato sul verdetto**: il bundle è 231 MB e la computer vision
ne aggiunge 150-250; un exe non firmato che apre la webcam è il profilo che gli
euristici antivirus segnalano; i pesi dei modelli di gaze accademici (MPIIGaze,
GazeCapture) sono **research-only** e su un prodotto a pagamento non si possono
usare. Stima per la feature completa: 4-6 settimane, più di riferimenti visivi,
tagli e tarature ACC messi insieme.

---

## Cosa misura lo spike

Due numeri, per due domande diverse. Non sono la stessa cosa e il report li
tiene separati:

1. **Sfasamento medio** (`vs sterzo`, `vs direzione dell'auto`): correlazione
   incrociata fra il canale sguardo e lo sterzo / lo yaw su tutta la guida. Dice
   di quanto, *in media*, il segnale dello sguardo precede quello del volante.
2. **Anticipo per curva**: per ogni ingresso curva, quando è **cominciato** il
   movimento dello sguardo verso quel lato. È un evento, non una fase, e sul
   sintetico esce più grande dello sfasamento medio — perché l'inizio del
   movimento viene prima del punto in cui i due segnali si allineano meglio.

Insieme, un **pavimento di rumore**: la stessa ricerca ripetuta su versioni
ruotate del segnale, dove per costruzione non c'è relazione. Se il picco vero
non lo supera, il report dice «nessuno sfasamento distinguibile dal rumore» e
non un numero. Su un segnale **periodico** il pavimento rifiuta sempre, ed è
corretto: se le curve fossero equispaziate, «anticipa di 0,4 s» e «ritarda di un
periodo meno 0,4 s» sarebbero la stessa cosa.

**Il limite che va ripetuto ogni volta**: la cattura da webcam ha una latenza
sconosciuta (40-120 ms su USB). Il numero **assoluto** se la porta dentro come
errore sistematico. Il **confronto fra due giri della stessa sessione** no: lì
si semplifica. Per questo lo spike serve a confrontare, e il report ha una riga
che lo dice — con un test che fallisce se qualcuno la toglie.

---

## Protocollo (~20 minuti)

Prima serve l'ambiente separato, una volta sola:

```
py -3.12 -m venv .venv-gaze
.venv-gaze\Scripts\activate
pip install opencv-python mediapipe
```

Poi, con il gioco avviato e tu in pista:

```
python tools/gaze_spike.py record --seconds 300
python tools/gaze_spike.py analyze <file.gaze.json>
```

Come guidare, in tre blocchi dentro la stessa cattura:

1. **5 giri al tuo passo normale**, come guidi sempre. È il riferimento.
2. **2 giri "guardando corto"** di proposito: occhi sul cofano, senza cercare
   l'uscita. Serve un **controllo negativo**: se il numero non cambia fra questi
   e i giri normali, non stiamo misurando lo sguardo — stiamo misurando che la
   testa si muove quando l'auto si muove.
3. **2 giri lenti** (passo turistico) ma guidati bene. Serve a separare
   «l'anticipo cambia col ritmo» da «l'anticipo cambia con la bravura».

Dimmi quali giri sono quali: senza etichette il confronto non si fa.

---

## Quando lo spike è promosso, e quando si butta

**Si butta** (e abbiamo speso qualche giorno invece di sei settimane) se:

- il report dice «nessuno sfasamento distinguibile dal rumore» sui giri normali;
- oppure il numero **non cambia** fra i giri normali e quelli "guardando corto":
  vorrebbe dire che stiamo misurando il movimento della testa indotto dall'auto,
  non l'intenzione del pilota;
- oppure il tracking perde il volto in più del ~20% dei fotogrammi (il report
  stampa quanti).

**Si va avanti** solo se tutte e tre passano, e allora il passo successivo *non*
è la feature: è ripetere la cattura in una seconda sessione, in un altro giorno,
con la sedia rimessa a posto, per vedere se il numero è ripetibile. Un numero che
cambia fra due sessioni dello stesso pilota non può giudicare un pilota.

E anche allora, la regola del progetto resta quella scritta in `ROADMAP.md`:
nessuna voce parla al pilota prima di una validazione live. Un «guarda più
avanti» sbagliato in curva è peggio del silenzio — sarebbe un secondo overlay che
ruba attenzione per dirti che stai perdendo attenzione.

---

## Cosa lo spike NON fa, di proposito

- **Non salva nessun fotogramma.** Dal processo di cattura escono solo numeri: un
  valore orizzontale per fotogramma. Non c'è un percorso di scrittura immagini.
- **Non scrive giri.** Legge la shared memory direttamente, non tramite
  `TelemetryFeed` — quel feed registra anche i giri, e un secondo scrittore sui
  giri è l'invariante che il progetto ha deciso di non rompere.
- **Non tocca lo schema del giro** (siamo alla v10, appena alleggerita): il file
  dello sguardo è affiancato e separato, e si cancella da solo senza toccare la
  telemetria.
- **Non dice niente al pilota mentre guida.**

---

## RISULTATI

*(da riempire dopo la prima cattura)*

| Blocco | Giri | Sfasamento vs sterzo | Anticipo per curva | Volto perso |
|---|---|---|---|---|
| passo normale | | | | |
| "guardando corto" | | | | |
| passo lento | | | | |

Verdetto: ☐ promosso a seconda sessione ☐ buttato
