# Il Confronto con la mappa accanto

**Data:** 2026-08-06 · **Stato:** approvato, da pianificare

## Da dove nasce

Il pilota ha indicato **popometer.io**: grafici di telemetria a sinistra, mappa
del tracciato a destra, sullo stesso schermo. Le sue parole: *«mettere la mappa
full sulla destra e i grafici della telemetria sulla sinistra»*.

## Cosa c'è già, e cosa manca davvero

I grafici che vuole a sinistra **esistono e sono al loro posto**: la scheda
**Confronto** disegna delta, velocità, gas/freno e sterzo. La scheda **Mappa**
disegna la mappa e la scheda frenate, e nient'altro.

Quindi non manca un grafico: manca che le due cose stiano **sullo stesso
schermo**. Oggi leggere una curva del grafico e poi guardare dove sei sul
tracciato costa un cambio di scheda, e il pensiero si interrompe lì.

## La decisione

**Il Confronto assorbe la mappa**, e la scheda Mappa sparisce.

Il nome dice la verità su cosa si sta facendo — un confronto fra due giri — e la
mappa è uno dei modi di guardarlo, non un argomento a sé. Il contrario (la Mappa
che assorbe i grafici) darebbe lo stesso schermo con un'etichetta che ne descrive
metà.

## Cosa si spedisce

**Due colonne.** A sinistra i quattro grafici esistenti, nell'ordine di oggi. A
destra la mappa, **che resta ferma mentre scorri i grafici**: è tutto il senso
della cosa, e una mappa che scorre via mentre leggi il grafico non serve a
niente.

La **scheda frenate** si trasferisce con la mappa: è la stessa domanda («dove
freni») in forma di numeri, e oggi vive già sotto la mappa.

**Su schermo stretto** le colonne si impilano e **la mappa va sopra**: è
l'orientamento, e serve prima del dettaglio. La regola stretta si scrive
**insieme** al layout, non dopo: questa pagina ha già spedito 39 px di scroll
laterale su telefono, da una colonna che non poteva restringersi.

## Le due cose che si rompono in silenzio

1. **Il rail.** La colonna che ricorda quale curva stavi guardando (fusa il
   05/08) ha una lista di viste che lo ospitano, `RAIL_VIEWS`, e `"map"` è
   dentro. Va tolta di lì, e va **verificato a schermo** che sul Confronto
   continui a funzionare — non solo che i test passino.
2. **Il canvas.** La mappa oggi si disegna a tutta larghezza; da domani sta in
   una colonna. Non basta spostare il nodo: il disegno deve **ridimensionarsi
   davvero**, e questo è un difetto che si vede solo aprendo la pagina.

Vanno con loro: la riga di lettura della mappa, la legenda (compresa la voce
«dove il giro si è perso», che compare solo quando quel giro ce l'ha) e lo stato
vuoto «questo giro non ha coordinate».

## Test

- la scheda `map` non esiste più: nessun bottone, nessuna vista, nessuna
  traduzione orfana;
- `RAIL_VIEWS` non la nomina, e il rail risponde sul Confronto;
- mappa, legenda, stato vuoto e scheda frenate sono dentro la vista Confronto;
- la pagina **non scorre di lato** né a larghezza piena né stretta — misurato su
  `scrollWidth` contro `innerWidth`, come è stato fatto per la serie per
  sessione, non a occhio.

## Fuori perimetro

Cambiare cosa disegnano i grafici o la mappa. Questo lavoro **sposta**, non
ridisegna: se qualcosa non piace di come sono fatti oggi, è un altro lavoro.
