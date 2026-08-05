# Il rail: una colonna sola, e il giro smette di essere una parola

**Data:** 2026-08-05 · **Stato:** approvato, da implementare

## Il problema, come l'ha misurato il panel

Quattro esperti hanno rivisto la reportistica girandola, non leggendola. Nessuno
dei quattro ha detto che le informazioni sono troppe. Hanno detto che le dieci
schede sono organizzate **per tipo di dato invece che per domanda**, che i dieci
nomi **sono** l'unica navigazione, e che manca **un modo di isolare una curva**.

La conseguenza misurata: nove liste per curva sparse su sei schede, senza un
collegamento fra loro. Chi legge deve tenere a mente «stavo guardando la Prima
Variante» mentre cambia scheda, e la scheda nuova non se lo ricorda.

Il rail è il primo passo dell'architettura a oggetti annidati:

```
auto+pista ⊃ sessione/stint ⊃ giro ⊃ curva      + Allenamento
```

Non fonde niente. Aggiunge il livello che manca — **la curva** — e lo rende
persistente attraverso le schede che parlano di un giro.

## Cosa si spedisce

Una colonna sinistra di ~220 px con due cose:

1. **la mappa del giro**, sempre a giro intero;
2. **le curve**, ordinate per tempo perso, con una barretta proporzionale.

```
┌─ rail 220px ──────┐
│   [mappa giro]    │
│                   │
│ ● Tutto il giro   │
│ T1 Prima Variante │  ████  −0.31
│ T4 Lesmo 1        │  ███   −0.22
│ T7 Ascari         │  ██    −0.14
│ T2 Curva Grande   │  █     −0.05
│ ───────────────── │
│ T3 Roggia         │
│ T5 Lesmo 2        │
└───────────────────┘
```

Sopra il separatore la classifica (curve con `lost_s > 0`, peggiore in cima);
sotto, in ordine di pista e senza barretta, **le curve pulite**. Il waterfall
ordina, ma un selettore deve poter selezionare anche una curva dove non hai perso
niente: è lì che si va a vedere *cosa hai fatto giusto*.

L'ordine per perdita costa l'allineamento con la mappa sopra. Si compensa
tenendo il numero `T` davanti a ogni riga e accendendo la curva sul disegno al
passaggio del mouse.

## Dove appare, e dove no

Rail sulle **sei schede del giro**: Il giro spiegato, Confronto, Mappa,
Traiettoria, Settori, Dinamica.

Niente rail su **Sessione, Passo gara, Andamento, Allenamento**: lì l'oggetto è
un altro (una sessione, uno stint, lo storico, un piano) e una curva non
significa niente. Un comando che non risponde è peggio di un comando assente.

La colonna che appare e sparisce col cambio scheda non è un difetto: è leggibile
come «questo gruppo di schede parla di un giro».

## Struttura

Un solo `<aside id="rail">`, **fratello** dei dieci `div#view-*`, dentro una
griglia a due colonne. Non un rail replicato dentro ogni pannello.

La differenza non è estetica. Con un rail per vista servirebbero sei canvas, sei
cablaggi di hover e sei posti dove ricordarsi di ridisegnare — ed è esattamente
la trappola 1 qui sotto, che con un nodo solo **non può verificarsi per
costruzione** invece che per disciplina.

`showView()` marca il rail quando la scheda attiva non è una delle sei.

**Conseguenza da dichiarare:** `main { padding: 16px var(--gut) }` e
`--page: 1600px` diventano una griglia `220px | resto`, e le quattro schede senza
rail tornano a colonna piena. Il layout cambia sotto a **tutte e dieci** le
schede, non solo alle sei. È il rischio di regressione principale di questa
spedizione e si controlla a schermo, scheda per scheda.

## Comportamento

**Stato.** Nessuno stato nuovo: la curva selezionata *è* `RANGE`, reso globale da
PR #78. Clic su una riga → `setRange(cornerWindow(c))`; clic su «Tutto il giro» →
`setRange(null)`. Si aggiunge un solo campo, `RANGE.corner` (l'indice della
curva), perché oggi la riga attiva si riconoscerebbe dal nome e **due curve
possono chiamarsi uguale** — succede su ogni pista senza nomi curati, dove il
nome è `Corner N`.

**Il rail non zooma mai.** `drawMapTo` disegna il giro intero; con la finestra
accesa il tratto scelto si accende e il resto si attenua. Serve a non perdere il
«dove sono nel giro» proprio nel momento in cui ti sei ristretto a una curva.

**La minimappa di Confronto sparisce.** Il rail *è* quella minimappa, spostata a
sinistra e resa persistente: stesso `drawMapTo`, stesso hover bidirezionale. Non
è una fusione di schede, è lo stesso elemento che cambia posto — e Confronto ci
guadagna l'altezza verticale che il panel ha misurato mancante (452 px di
intestazione sopra il primo grafico). La scheda Mappa resta intatta: lì la mappa
grande è il contenuto, non un indice.

**La scheda Mappa è lo stato «Tutto il giro».** `#brakesheet` resta fuori dal
trasloco: è una tabella stampabile, non una mappa.

## Le tre trappole

Le prime due erano state previste dall'ingegnere di telemetria *prima* di
incontrarle. La terza è emersa leggendo il codice.

**1. `redrawCurrentView()` è uno switch per-vista, e un rail persistente non
appartiene a nessuna vista.** `drawRail()` va chiamato **fuori** dallo switch: in
coda a `redrawCurrentView`, dopo `loadCombo`, e nel ramo resize. Senza, al cambio
scheda il rail resta fermo all'ultimo giro, e dopo un resize l'hover punta al
posto sbagliato.

**2. Il giro senza mappa.** `drawMapTo` nasconde il canvas e ritorna `null` sui
giri senza coordinate — **i nostri giri ACC di giugno sono esattamente quel
caso**. Con un rail persistente diventerebbe una colonna vuota su *tutte* le
schede. Rimedio: al posto del disegno una riga breve che dice perché, e **la
lista curve resta viva**, perché viene da `a.corners`, non dalle coordinate. Il
rail non è mai una colonna vuota.

**3. L'hover della minimappa è cablato a una vista sola.** Oggi `mousemove` su
`#c-minimap` chiama `redraw(p)`, che è la funzione della *sola* vista Confronto.
Spostato in un rail che vive su sei schede, va instradato per vista: serve un
`hoverTo(p)` unico che faccia la cosa giusta dove c'è un consumatore e **niente**
dove non c'è, invece di sei `if` sparsi.

## Dati

Nessun endpoint nuovo, nessuna modifica al backend. Il rail si costruisce
interamente lato client da quello che il payload già porta:

- `DATA.corners[] = {index, entry, apex, exit, name}` — le curve, anche sui giri
  senza coordinate;
- `DATA.losses[] = {index, label, lost_s, message, …}` — le perdite, con
  `losses[].index` che combacia con `corners[].index` (`api.py:1133`, e il
  commento lì spiega perché l'aggancio è per numero e non per nome).

## Test

`tests/test_web_views.py` ha già il pattern giusto — regex sul sorgente, perché
queste cose falliscono **in silenzio**: un pannello si aggiunge senza cablarlo a
una scheda, e niente solleva un errore.

1. `#rail` è fratello delle viste e non sta dentro nessun `#view-*` (via
   `_view_of_ids()`, che attribuisce ogni id al pannello in cui cade: il rail
   deve risultare fuori da tutti, quindi va scritto **prima** di `#view-flow`);
2. `drawRail()` è chiamato fuori dallo switch di `redrawCurrentView`;
3. l'elenco delle sei schede col rail esiste **una volta sola** e i suoi nomi
   sono `data-view` reali;
4. le chiavi i18n nuove esistono in entrambe le lingue (`test_web_i18n_keys.py`
   lo copre già, ma va eseguito);
5. controllo a schermo col browser su tutte e dieci le schede, incluso un giro
   **senza mappa**. In questo progetto è il browser ad aver trovato tutti i
   difetti veri.

## Fuori perimetro

Non in questa spedizione, per tenerla additiva:

- cancellare la sezione `#waterfall` da Confronto (il rail la duplica come
  navigazione; si toglie quando il rail ha dimostrato di funzionare);
- fondere schede, l'interruttore «Avanzato», la gerarchia dei titoli;
- la demo che si autosabota, la sovrapposizione multi-giro, il ripiego al secondo
  miglior giro.
