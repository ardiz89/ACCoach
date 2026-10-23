# Linguette del tablet, strada dell'ingegnere e report a fine sessione — registro (22-23/10)

Spec `docs/superpowers/specs/2026-10-22-tablet-linguette-design.md`, piano
`docs/superpowers/plans/2026-10-22-tablet-linguette.md`. Suite finale 3151.

## Cosa aveva detto il pilota

- «Da tablet non riesco a passare da engineer a telemetria e viceversa.»
- «Non è chiara la dinamica … come il coach suggerisce il setup step by step e
  quali sono gli step di setup man mano che si gira.»
- «Il report a fine sessione mi faceva vedere il recap di una delle sessioni di
  Imola, non l'ultima fatta ieri» (aveva guidato a Spa).

## Il report a fine sessione (ramo `fix/report-ultima-sessione`)

Causa, letta nel log del 22/10 e nel codice: chiuso ACC, il pannello «In pista»
riceveva `connected: false` con auto e pista vuote e se le dimenticava; «Ho
finito» apriva il report senza combo, e il report riapriva l'ultima combo vista
(Imola) e l'ultima scheda (il recap). Ora il pannello ricorda auto, pista, giri
salvati, giri fatti e miglior tempo per tutta la corsa, e il report senza
parametri apre la Pagella della combo più recente se ha una sessione non vista.

## Decisioni prese per il pilota

1. Due copie di `stripText` (tablet ES5 e `engineer.js`), tenute uguali da test
   che fanno girare gli stessi casi su tutte e due.
2. Prima della prima decisione il frame porta `{phase, progress}`: la strada si
   vede dal primo giro.
3. «Dal volante» / «ai box» viene dalla **modifica**, non dalla fase: le fasi «dal
   volante» della GT3 propongono anche rimedi da fare ai box, e la ripresa delle
   pressioni propone ai box in ogni fase.
4. `progress()` guarda prima le modifiche aperte e poi «finito».
5. **In pista Assetto si legge ma non si scrive** (rovescia una mia scelta della
   spec): scrivere avvisa il motore, che comincia a contare i giri di verifica
   con l'assetto vecchio ancora montato.
6. Le fasi saltate dal motore (cieche, o senza niente da correggere) non si
   spuntano.
7. Un solo nome per i giri che contano: «puliti».

## Difetti trovati che i test non vedevano

- La striscia diceva «Assetto finito» con una modifica delle pressioni ancora da
  fare.
- La guida diceva che ogni fase raccoglie 3 giri di base (falso dopo il primo) e
  che il motore lavora sul bagnato (si ferma).
- Il riquadro del file scritto restava dopo un cambio d'auto o una
  riconnessione.
- La correzione del report aveva introdotto «nessun giro ancora» a gioco chiuso.

## Aperti

- Sulla pagina Ingegnere completa «Prepara e scrivi» e «L'ho già rimesso com'era»
  avvisano il motore anche in pista: stesso problema del punto 5, c'era già prima.
- Mai provato sull'iPad vero (Norton blocca il tablet), né col pannello vero
  dell'hub a gioco chiuso.
- «Saltata» è una parola debole per una fase dove sono state provate modifiche
  e il cancello non si è mai aperto.
