# Ingegnere — le stesse curve per tutta la serata

Stato: progetto breve del 17/11/2026, approvato dal pilota («ok»). Le scelte segnate
*[mia scelta]* sono mie.

## Perché

Il controllo di costanza (`docs/superpowers/specs/2026-11-17-costanza-pilota-design.md`)
confronta i giri curva per curva, e vale solo se tutti i giri sono misurati sulle stesse
curve. In pista oggi non lo sono:

- l'Ingegnere riceve le curve del riferimento del coach (`engine._corners`), che il motore
  ricalcola a ogni nuovo miglior giro (`engine._rebuild_reference`). Ogni nuovo miglior
  giro cambia la chiave delle curve (`LapStats.corners_key`) e il gruppo ricomincia: mentre
  il pilota migliora il controllo giudica poco;
- senza riferimento (prima serata su un'auto o una pista) ogni giro trova le sue curve
  (`corners_own`) e non si giudica niente.

Le stesse curve per tutta la serata servono anche alla tappa dopo, il confronto fra base e
prova curva per curva (il punto «c»).

## Obiettivi

1. L'Ingegnere misura tutti i giri di una serata (stessa auto, stessa pista) sulle stesse
   curve, con gli stessi nomi.
2. Senza riferimento, si giudica dal primo giro pulito e valido in poi.

## Non obiettivi

- Il coach dal vivo (Focus, analyzer, debrief) resta com'è: continua a inseguire il nuovo
  miglior giro col suo riferimento.
- Il rigioco resta com'è: curve del giro più veloce, pulito e valido della serata
  (`replay._evening_corners`).
- Niente memoria fra una serata e l'altra: quando l'Ingegnere rinasce (auto o pista
  diverse, riavvio dell'app) le curve si fissano di nuovo.

## Anti-obiettivi

- Perdere i nomi delle curve («Tosa», «Rivazza») quando il riferimento li ha.
- Cambiare qualunque cosa che il coach dice o mostra.

## Approcci

1. **Curve del riferimento nel momento in cui nasce l'Ingegnere della serata, con ripiego
   sul primo giro pulito e valido** — *scelto*. Il riferimento è un buon giro e porta i
   nomi curati.
2. Sempre dal primo giro pulito della serata: scartato, perde i nomi curati e usa un giro
   di solito peggiore del riferimento.
3. Curve aggiornate a ogni sosta: scartato, romperebbe il confronto fra uno stint e
   l'altro, che è proprio quello che serve al punto «c».

## Come si costruisce (deciso)

Tutto in `src/accoach/engine.py`:

- quando il motore crea l'Ingegnere (`self._engineer = engineer_for(...)`, dopo
  `_rebuild_reference`), tiene una copia delle curve e dei nomi di quel momento: le curve
  dell'Ingegnere e i loro nomi. Se il riferimento non c'è, le curve dell'Ingegnere
  restano vuote;
- in `_observe_lap`, la diagnosi per l'Ingegnere (`build_lap_stats`) usa le curve e i
  nomi dell'Ingegnere, non quelli correnti del coach;
- se le curve dell'Ingegnere sono vuote e il giro è valido e pulito
  (`lap.valid and lap.clean is not False`), si fissano da quel giro
  (`detect_corners(lap.samples)`, nomi con `_corner_labels`) e quel giro è già misurato
  su di esse. Se il rilevamento non trova curve, si riprova al giro dopo. Un giro sporco o
  incompleto non fissa niente e si misura come oggi (curve proprie, non giudicato);
- le curve dell'Ingegnere si azzerano soltanto quando l'Ingegnere rinasce.

Aggiunto dopo la revisione finale (17/11, su richiesta del pilota di sistemare le note
minori):

- il primo giro pulito e valido controlla anche le curve prese dal riferimento: se meno
  della metà delle sue curve ha un apice entro `consistency.MATCH` da una di quelle, la
  serata si misura sulle sue. Su Assetto Corsa la pista non dice il layout, e il
  riferimento può essere un giro di un altro layout dello stesso circuito (Brands Hatch GP
  mentre si gira sull'Indy): prima un nuovo miglior giro lo sostituiva, con le curve fisse
  sarebbe rimasto tutta la sera;
- i nomi si rileggono a ogni giro (`_corner_labels` sulle curve della serata): le curve
  restano, ma un nome scritto dal pilota a metà serata o un cambio di lingua arrivano al
  giro dopo.

## Verifica

Test del motore:

- il riferimento cambia a metà serata: i giri dopo hanno la stessa `corners_key` di prima;
- senza riferimento: il primo giro pulito e valido fissa le curve, i giri dopo hanno la sua
  chiave e non sono `corners_own`; un giro sporco prima di lui non fissa niente;
- cambio di auto o pista: le curve si fissano di nuovo;
- i nomi seguono il catalogo a ogni giro, sulle curve della serata;
- un riferimento di un altro layout cede al primo giro pulito, uno dello stesso resta.

Più la suite intera con la casa finta.

## Lasciato al costruttore

Nomi degli attributi, punto esatto dell'azzeramento, forma dei test (il banco di
`tests/test_impronta_motore.py` o uno nuovo).
