# Le linguette del tablet e la strada dell'ingegnere — design

Data: 2026-10-22. Parte dal main `ee4d6f3` (vista tablet pubblicata, PR #116).

## Il perché

Il pilota, il 22/10, dopo la prima prova della vista tablet:

- «Da tablet non riesco a passare da engineer a telemetria e viceversa.» Su
  `/tablet` la schermata la sceglie solo lo stato del frame. `/engineer` su un
  browser vecchio rimanda a `/tablet`. Sull'iPad 3 non c'è quindi nessun modo di
  scegliere.
- «Non è chiara la dinamica … come il coach suggerisce il setup step by step e
  quali sono gli step di setup man mano che si gira.» Il motore sa in che fase
  è, quante fasi ci sono, quanti giri ha e quanti ne servono. La pagina vede
  solo la fase in corso e una frase.

## Deciso col pilota (22/10)

1. Due linguette fisse in alto su `/tablet`: **Telemetria** e **Assetto**. Il
   cambio automatico resta. Il pilota può sempre toccare l'altra linguetta.
2. Una striscia che fa vedere la strada dell'ingegnere: le fasi in ordine, quella
   in corso, e il contatore dei giri del passo in corso.

## Le linguette

- **Telemetria** è la schermata «in pista» di oggi, con l'avviso di rientro in
  alto quando c'è.
- **Assetto** è la schermata «ai box» di oggi: fase, modifica leva per leva, file
  di partenza, bottone che scrive con la conferma, ripristino. La si può aprire
  anche fuori dai box, ma lì si legge e basta: *Scrivi la modifica* e *L'ho già
  rimesso com'era* si accendono solo con `at_box`, e una riga dice che il file
  si scrive da fermo ai box. **Cambiato dopo la revisione finale** (vedi
  «Scelte mie», n. 2).
- Lo stato «nessun collegamento» resta a tutto schermo, senza linguette utili.
- Automatico: quando il pilota si ferma ai box la vista passa ad Assetto; quando
  riparte torna a Telemetria. Un tocco su una linguetta vale fino al prossimo
  cambio di stato (ai box / non ai box). Così la vista non toglie la schermata al
  pilota a ogni frame, e non resta su Assetto quando riparte.
- Sull'avviso di rientro, un tocco porta ad Assetto, per leggere la modifica
  prima di entrare.
- La linguetta Assetto mostra un segno quando c'è una modifica da fare ai box.

## La strada dell'ingegnere

Il motore aggiunge al blocco `engineer` del frame un campo `progress`, calcolato
da `RaceEngineer` (una regola, un posto):

| Campo | Significato |
|---|---|
| `phases` | le fasi del profilo in ordine: `key`, `label` tradotta, `tag` («BOX» o «AV» quando la fase si fa dal volante) |
| `index` | la fase in corso (da 0); uguale al numero di fasi quando l'assetto è finito |
| `stage` | il passo in corso: `baseline` (raccolgo i giri), `change` (modifica proposta da fare), `test` (verifico la modifica), `restore` (rimetti com'era), `diagnose` (ho i giri, sto decidendo), `done` |
| `have`, `need` | giri puliti contati e giri che servono, solo per `baseline` e `test` |
| `skipped` | gli indici delle fasi che il motore ha passato senza chiuderle (cieche, o niente da correggere col cancello chiuso); la strada le disegna barrate, senza spunta. Va su disco con `phase_idx` |

Accanto a `progress`, il blocco porta `tail`: su una raccolta o una prova, la
parte del messaggio del motore che il contatore non dice (perché l'ultimo giro
non conta, il sospetto sulle uscite), `""` se non c'è, `null` altrove. Quando
la strada conta i giri la pagina mostra solo quella, così lo stesso numero non
si legge due volte con due frasi. Quando l'ultima decisione è `stand_down`
(bagnato, fase cieca, leva che non si sa scrivere) la frase del passo sarebbe
falsa, e la strada dice solo «Per ora non scrivo modifiche.»; il perché sta nel
messaggio.

La striscia, sul tablet in entrambe le linguette e sulla pagina Ingegnere sopra
la riga della fase:

- le fasi come tappe in fila, la fase in corso evidenziata, le fatte spuntate;
- sotto, una frase sul passo in corso col contatore, per esempio «Giri puliti
  per la base, 2 di 3.» o «Provo la modifica, giri puliti 1 di 3.». Poi cosa
  succede dopo («Poi decido se tenerla»). «Puliti», la parola che il motore usa
  già nei suoi messaggi, e la stessa nelle guide.

Le parole sono nuove chiavi di `i18n.js`, italiano e inglese, col tono del 21/10.
Ogni frase deve dire il vero sul codice: per esempio che un giro conta solo se è
valido, pulito e con le gomme calde (sopra 75 °C).

## Vincoli

- Safari 9 come la vista tablet: ES5 + template string, niente `.forEach` in
  `tablet.js`, CSS senza grid/var/clamp/gap/min()/max()/vh. `tests/safari9.py`.
- Tutto deve stare senza scorrimento a 1024 × 680 e 768 × 940.
- Il frame non si ingrandisce di molto: le fasi sono al massimo 5.
- Mai scrivere in `Documents\ACCoach`; mai importare `accoach.config` fuori dai
  test isolati o da una casa finta.

## Scelte mie

1. Il tocco manuale vale fino al prossimo cambio ai box / non ai box.
2. La linguetta Assetto si apre anche in pista, ma lì si legge e basta: il
   bottone che scrive e «L'ho già rimesso com'era» funzionano solo con
   `at_box`. **Cambiato dopo la revisione finale** (Ruling 5). All'inizio il
   bottone scriveva anche in pista. Ma la scrittura avvisa il motore
   (`/engineer/applied` → `mark_applied`), che apre la prova della modifica
   mentre la macchina ha ancora l'assetto vecchio: un file si carica solo dal
   garage. I giri di prova e il verdetto sarebbero stati misurati sull'assetto
   sbagliato. «L'ho già rimesso com'era» chiama lo stesso endpoint: su un
   ripristino `mark_applied` svuota la finestra e rifà la base da lì, quindi
   anche lui vale solo ai box, dove il file di prima si ricarica.
3. Il contatore c'è solo per `baseline` e `test`: sono gli unici passi in cui il
   motore conta giri verso una soglia.
4. La striscia va anche sulla pagina Ingegnere, così le due pagine raccontano la
   stessa cosa.
