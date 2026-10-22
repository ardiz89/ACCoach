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
  anche fuori dai box. Il bottone scrive comunque solo dopo la conferma.
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
| `have`, `need` | giri buoni contati e giri che servono, solo per `baseline` e `test` |

La striscia, sul tablet in entrambe le linguette e sulla pagina Ingegnere sopra
la riga della fase:

- le fasi come tappe in fila, la fase in corso evidenziata, le fatte spuntate;
- sotto, una frase sul passo in corso col contatore, per esempio «Giro buono 2 di
  3 per la base» o «Verifico la modifica, giro 1 di 3». Poi cosa succede dopo
  («Poi decido se tenerla»).

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
2. La linguetta Assetto si apre anche in pista, e il bottone scrive lo stesso
   (sempre dopo la conferma).
3. Il contatore c'è solo per `baseline` e `test`: sono gli unici passi in cui il
   motore conta giri verso una soglia.
4. La striscia va anche sulla pagina Ingegnere, così le due pagine raccontano la
   stessa cosa.
