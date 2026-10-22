# La vista tablet: una schermata che cambia col momento — design

Data: 2026-10-22. Parte dal main `9ceeb6a`.

## Il perché

Il pilota guarda la pagina Ingegnere da un tablet accanto al volante. Il tablet
che ha è un iPad di terza generazione con iOS 9.3.6, cioè Safari 9 (2015). Lì la
pagina Ingegnere non può funzionare: `engineer.js` usa `async/await`, funzioni
freccia, `const`/`let`, `fetch` e `??`, e Safari 9 smette di leggere lo script
alla prima di queste. Restano l'intestazione e i riquadri vuoti. Il pilota dice
«non si vede bene su tablet».

Anche su un tablet moderno la pagina Ingegnere è tutta insieme: telemetria,
diagnosi, registro, storico, editor dell'assetto. In pista ne serve una parte, e
quale parte dipende dal momento.

## Deciso col pilota (22/10)

1. **Una vista a sé per il tablet**, leggera, che gira anche su Safari 9. La
   pagina Ingegnere completa resta com'è.
2. **Tre stati, che si alternano da soli**:
   - **in pista**: la telemetria;
   - **avviso di rientro**: quando l'ingegnere ha pronta una modifica da fare ai
     box, l'avviso deve farsi notare;
   - **fermo ai box o al pit**: la schermata dell'assetto con la fase in cui sei.
3. **Ai box anche il bottone** che scrive la modifica nel file dell'assetto, come
   «Prepara la modifica» sulla pagina completa. Non solo da leggere.
4. **Norton resta installato.** Il suo firewall oggi blocca le richieste del
   tablet verso il PC (il ping passa, le pagine no) e il pilota non può
   cambiarlo senza pagare. La vista si costruisce e si verifica senza il
   dispositivo vero; la prova sull'iPad si fa quando il blocco cade.

## Obiettivi

- Sull'iPad 3 con Safari 9 la vista si apre, si aggiorna dal vivo e il bottone
  scrive la modifica.
- Uno sguardo di lato, a caratteri grandi, basta per capire in che stato sei e
  cosa fare.
- Ai box, col motore acceso e i secondi contati, la modifica si scrive con un
  tocco e una conferma, senza scegliere nomi di file.

## Non obiettivi

- Lo storico, il registro delle prove, le previsioni, l'editor completo
  dell'assetto e il report: restano sulla pagina Ingegnere e sul PC.
- Cambiare il motore dell'ingegnere, le sue fasi o quando propone una modifica.
- Togliere il blocco di Norton.

## Anti-obiettivi (fallimento anche se funziona)

- Una vista che su Safari 9 resta vuota o ferma, anche solo per uno script
  caricato che non si legge (il file dei testi compreso).
- L'avviso di rientro che si perde fra i numeri della telemetria.
- La schermata dei box che compare mentre guidi, o che resta mentre riparti.
- Un bottone che scrive su un file diverso da quello che la schermata nomina, o
  che scrive due volte con un doppio tocco.
- Una scrittura che non avvisa il motore: l'ingegnere riproporrebbe la stessa
  modifica a ogni giro (la regola sta già in `afterWrite` di `engineer.js`).
- Testi che rompono il tono deciso il 21/10 (`tests/tono.py`): frasi brevi col
  tu, virgola decimale, niente slogan, niente due punti a effetto, niente emoji,
  mai la stessa frase in due posti.

## I tre stati

Lo stato si decide a ogni frame dal vivo, con le regole che il motore usa già.
Non si inventano condizioni nuove.

| Stato | Quando | Cosa si vede |
|---|---|---|
| Nessun collegamento | il motore non manda frame (`connected` falso o socket chiuso) | una riga che dice che il coach non è acceso, e che la pagina si ricollega da sola |
| In pista | collegato e non fermo ai box (anche mentre percorri la corsia box, all'entrata e all'uscita) | velocità, marcia, TC/ABS/mappa, temperature e pressioni delle quattro gomme, la striscia di gas, freno e sterzo, la fase in cui sei. Se c'è una proposta «al volo» (`tag == "AV"`) la mostra con il suo bottone «Fatto» dove la pagina completa lo mostra |
| Avviso di rientro | collegato, non fermo ai box, e una modifica da fare ai box: proposta non ancora scritta (`kind == "propose"`, `tag == "BOX"`, `change`, non `applied`) o ripristino non ancora fatto (`kind == "reverted"`, `tag == "BOX"`, `change`, non `applied`) | la telemetria resta, ma l'avviso prende la parte alta dello schermo con un colore suo e dice di rientrare ai box. Resta finché la modifica non è scritta o il motore non la ritira |
| Fermo ai box | collegato e fermo ai box (sotto) | la schermata dell'assetto (sotto) |

**Fermo ai box** è la regola del briefing vocale (`coaching/pitcall.py`):
`in_pit`, oppure in corsia box (`in_pit_lane`) e fermo (velocità sotto la
soglia `_STOPPED_KMH`). Su ACC `in_pit` non si accende mai con l'auto ferma nel
box (misurato il 07/08, scritto in `pitcall.py` e `fuel.py`): con `in_pit` da
solo la schermata dei box lì non comparirebbe mai. Il motore calcola questa
condizione una volta e la manda nel frame dal vivo come campo suo; la pagina
non la ricalcola. Lo stesso campo lo usa anche il promemoria ai box della
pagina completa (`renderPitReminder`), che oggi guarda `in_pit` da solo e su
ACC ha lo stesso difetto. Una regola, un posto.

Quando riparti, l'auto si muove e la vista torna in pista: la schermata dei box
non resta.

## La schermata dei box

Dall'alto:

1. **La fase** in cui sei e cosa fare in questa fase (le stesse chiavi
   `eng.do.*` della pagina completa).
2. **La modifica**, se c'è: per ogni leva il nome, la ruota o il lato, e il
   valore da quale a quale, nelle unità della pagina completa (i clic e il
   valore in psi, mm, gradi…). Sotto, il perché in una riga (`rationale`) e il
   grado di fiducia; con fiducia bassa, l'avvertenza della pagina completa.
3. **Il file di partenza**, per nome, con la possibilità di sceglierne un altro
   per l'auto e la pista in corso.
4. **Il bottone** che scrive la modifica. Un tocco apre la conferma con l'elenco
   delle leve e il nome del file nuovo; il secondo tocco scrive. Il file nuovo
   prende il nome progressivo della via corta (`HONE_1`, `HONE_2`, …).
5. **Dopo la scrittura**: il nome del file da caricare nel gioco, e la riga per
   ricaricarlo dal garage (`reload_hint`).
6. **Il ripristino**: per una modifica bocciata, lo stesso bottone scrive il
   ripristino, e accanto c'è «L'ho già rimesso com'era» (`confirmRestored`).
7. **Senza modifica**: la fase e il messaggio dell'ingegnere, e niente bottone.

La scrittura usa gli endpoint che la pagina completa usa già
(`/api/setup/*`) e dopo avvisa il motore come `afterWrite`
(`POST /engineer/applied` sul motore). La regola del nome progressivo e del
409 «già esiste» è quella di `applyNow`.

## Il file di partenza

La modifica si somma a un file d'assetto. La vista non sa quale assetto hai
caricato nel gioco, quindi:

- se da quando il processo web è acceso la vista o la pagina completa ha già
  scritto un file per quell'auto e quella pista, la base è quello (è quello che
  ti ha detto di caricare);
- altrimenti la base è il file d'assetto modificato più di recente per l'auto e
  la pista del frame;
- il nome si vede sempre, e si cambia da un elenco.

Oggi l'ultimo file scritto lo ricorda solo la scheda del browser che l'ha
scritto (`lastWritten` in `engineer.js`), e l'elenco dei file è in ordine di
nome, senza date. Quindi:
- l'ultimo file scritto per auto e pista lo ricorda il processo web (porta
  8778), che è quello che scrive, in memoria: si perde a ogni riavvio, e allora
  vale la seconda regola;
- l'elenco dei file porta anche la data di modifica, così la vista sceglie il
  più recente.

Scelta mia, da far confermare al pilota.

## Safari 9: cosa vuol dire per il codice

- Tutto quello che la vista carica (HTML, script, stili, testi) si legge su
  Safari 9. Gli script sono JavaScript ES5 più le template string (che Safari 9
  ha): niente `let`/`const`, funzioni freccia, `class`, `async/await`, `...`,
  `?.`, `??`; e fra le funzioni del browser niente `fetch`,
  `NodeList.forEach`, `padStart`, `Intl`, `Object.entries`/`values`,
  `URLSearchParams`. Le richieste vanno con `XMLHttpRequest`, il dal vivo col
  `WebSocket` (Safari 9 lo ha).
- Gli stili senza griglia CSS, senza `clamp()`, senza variabili CSS e senza
  `gap` sui flex. Si usano flexbox e misure semplici.
- I testi: la vista carica `i18n.js` come le altre pagine, segue la lingua
  dell'hub (`window.HONE_LANG`) e aggiunge lì le sue chiavi, senza copie da
  tenere allineate. `i18n.js` è scritto con `var` e funzioni; le sue stringhe
  sono template string senza `${}`, che Safari 9 legge. L'unico punto che su
  Safari 9 si rompe è `querySelectorAll(...).forEach` (Safari 9 non ha
  `NodeList.forEach`): sta dentro un `try`, quindi la pagina non cade, ma i
  testi fissi non si traducono mai. Si corregge con
  `Array.prototype.forEach.call`, per tutte le pagine.
- Un controllo automatico prova che ogni script caricato dalla vista non usa la
  sintassi e le funzioni sopra. Deve fallire se qualcuno ci mette una
  funzione freccia.

## Dove si apre

- Indirizzo nuovo: `/tablet`, servito dallo stesso processo della pagina
  Ingegnere (porta 8778, anche con `lan = true`).
- Il QR del pannello «In pista» e l'indirizzo scritto sotto puntano a `/tablet`.
  La vista ha un collegamento alla pagina completa.
- `/engineer` aperta da un browser che non sa leggere il suo script (prova in
  ES3, prima di caricare `engineer.js`) porta a `/tablet`. Così il preferito che
  il pilota ha salvato sul tablet funziona lo stesso.

Scelte mie, da far confermare al pilota.

## Leggibilità

- Lo schermo dell'iPad 3 è 1024 × 768 punti CSS. La vista si progetta lì, in
  orizzontale e in verticale, senza scorrimento in pista.
- In pista i numeri principali (velocità, marcia) si leggono a un metro.
- Ogni bottone è grande almeno 44 punti, come chiede Apple per il dito.
- Il tema scuro della pagina Ingegnere.

## Verifica

- I test della suite (Python): la pagina si serve, la lingua arriva, il
  controllo ES5 su ogni script della vista, gli stati scelti per frame finti
  (pista, avviso, ripristino, box, nessun collegamento), il bottone che chiama
  gli endpoint giusti e avvisa il motore.
- Nel browser, sulla copia dell'archivio (mai `Documents\ACCoach`): la vista
  con WebKit di Playwright a 1024 × 768 e 768 × 1024, con frame dal vivo finti
  per i quattro stati, e la scrittura di un file d'assetto vero sulla copia.
- Sull'iPad vero quando Norton smette di bloccare. Fino ad allora la prova sul
  dispositivo resta aperta, e si dice.

## Scelte mie

Prese da me, il pilota le può rovesciare.

1. **Il file di partenza** è l'ultimo scritto nella sessione, se no il più
   recente per auto e pista; il nome si vede e si cambia.
2. **Indirizzo `/tablet`**, il QR punta lì, e `/engineer` su un browser vecchio
   ci porta da sola.
3. **La conferma prima di scrivere** (due tocchi): ai box un tocco per sbaglio
   scriverebbe un file.
4. **L'avviso di rientro non copre la telemetria**: prende la parte alta, perché
   finché non sei ai box stai ancora guidando.
5. **La proposta «al volo» resta nello stato in pista** con il suo «Fatto», come
   nella pagina completa.
6. **Fermo ai box** è la regola del briefing vocale, calcolata dal motore e
   usata anche dal promemoria della pagina completa, che così si accende anche
   su ACC.
7. **L'ultimo file scritto lo ricorda il processo web**, in memoria, per auto e
   pista; l'elenco dei file porta la data di modifica.
8. **`i18n.js` resta com'è**, con la sola correzione di `NodeList.forEach`, e
   la vista ci aggiunge le sue chiavi: nessuna copia dei testi.
