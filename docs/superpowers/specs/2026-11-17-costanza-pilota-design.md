# Ingegnere — la costanza del pilota: un giro guidato diversamente non conta

Stato: progetto del 17/11/2026. La regola e la strada le ha scelte il pilota («ok B»,
«ok come proposto», «ok 1»). Le scelte segnate *[mia scelta]* sono mie e il pilota le
può correggere.

## Perché

Il 16/11 il pilota ha chiesto se l'Ingegnere distingue un errore o una distrazione di
guida da un problema d'assetto. Oggi no: dalla finestra dei giri escono solo i giri con
un'uscita di pista (`clean`), quelli con le gomme fredde, e per proporre una modifica
serve un sintomo in 3 curve per 3 giri. Una curva sbagliata, uno stacco lungo, un giro
con la testa altrove entrano nella finestra come giri buoni e spostano le letture. Il
pilota ha detto che è importante.

## Cosa dice l'archivio

Misurato il 16-17/11 in sola lettura sui giri della McLaren 720S
(`tools/costanza_archivio.py` e uno script di soglie nella cartella temporanea):

- **Lo stacco oggi non si misura.** Il registratore teneva un campione ogni ~100 ms, cioè
  ~7,5 m in frenata, e il pedale va da zero a pieno in meno di un campione: la
  dispersione in tre giri puliti era sempre un campione. Corretto nel registratore il
  16/11 (`9a5e07e`), si misura dalla prossima serata. **Non entra in questa tappa.**
- **La velocità minima per curva sì.** Ogni giro pulito confrontato con la mediana degli
  *altri* giri puliti dello stesso stint, curva per curva (76 giri puliti, in stint con
  almeno 3):
  - contando anche i giri diversi in meglio, 7 dei 12 giri «diversi» (oltre 4 km/h di
    scarto mediano) erano **più veloci** degli altri: la regola avrebbe buttato i giri
    migliori. Contano quindi solo i più lenti;
  - «almeno 3 curve più lente di oltre 5 km/h»: 12 giri su 76 (16 %). 10 dei 12 sono
    anche più lenti sul cronometro, da +0,40 a +2,43 s rispetto agli altri giri dello
    stint; 1 era 1,57 s più veloce. Fra i giri con un'uscita di pista: 38 %;
  - «almeno 3 curve più lente di oltre 8 km/h»: 3 giri su 76 (4 %).
- **Rimisurato con le regole che userà l'Ingegnere** (17/11, dopo la revisione): tutte le
  curve rilevate, nessun taglio sui giri lenti, gruppi per stint **e** manopole (vedi
  sotto). La regola toglie **15 giri puliti su 79 (19 %)**: tempi rispetto agli altri giri
  del gruppo −3,58, −1,57, −0,01, +0,40, +0,69, +0,78, +0,81, +1,19, +1,31, +1,52, +1,96,
  +2,51, +3,58, +88,8 e +96,7 s. Gli ultimi due sono giri «puliti» di un minuto e mezzo
  più lunghi degli altri (Monza 02/08, Brands Hatch 25/10), che è giusto togliere. I primi
  due sono più veloci sul cronometro pur essendo più lenti in 3 curve: è un'imperfezione
  nota della regola, accettata.
- **Oggi sulla 720S quasi ogni verdetto è sulle pressioni**, e dalla tappa 1 si dà sulla
  pressione raggiunta, che la guida sposta poco. I verdetti sul bilanciamento (sintomo +
  tempo) sulla 720S quasi non scattano. Per questo la regola vale per **tutte** le
  letture, non solo per i verdetti (scelta B del pilota).

## La regola (decisa col pilota)

Un giro pulito **non conta** se, rispetto agli altri giri puliti dello stesso stint, è
**più lento di oltre 5 km/h di velocità minima in almeno 3 curve**. L'Ingegnere lo dice
come dice oggi un'uscita di pista.

- **Stesso stint**: non il miglior giro, non lo stint di prima. Un cambio d'assetto
  sposta tutti i giri insieme e non deve sembrare un errore di guida. Per la stessa
  ragione, dentro uno stint il gruppo si spezza quando cambiano le manopole (vedi «Il
  gruppo» sotto).
- **Solo più lento**: un giro migliore degli altri non è un errore.
- **Anche a posteriori**: i primi giri di uno stint si possono giudicare solo quando ce
  ne sono altri due, quindi un giro può essere tolto qualche giro dopo, e lo si dice.

## Obiettivi

1. Un giro così non entra in nessuna lettura: pressioni, base di una proposta, finestra
   di una prova, verdetti.
2. Il pilota sa quale giro, dove e perché: in pagina e dove oggi passa la frase delle
   uscite di pista.
3. Si ritrova dopo: il registro della serata (`ingegnere-AAAAMMGG.jsonl`) dice quali giri
   sono stati tolti e su quali curve; il rigioco (`replay-engineer`) lo mostra.
4. Si verifica senza guidare, rigiocando l'archivio (vedi Verifica).

## Non obiettivi

- Il confronto base/prova curva per curva (il punto «c» concordato il 16/11): tappa a
  sé, dopo questa.
- La costanza sullo stacco: dopo due o tre serate registrate col registratore nuovo.
- Le classi dove la soglia non è misurata. *[mia scelta]* La regola vale per le auto
  GT3 (ACC e Assetto Corsa), dove è misurata sulla 720S. Restano come oggi Formula,
  stradali **e** GT4, GT2 e GTE: oggi `classmap` le manda tutte sul profilo GT3 (i pezzi
  `gt3`, `gt4`, `gt2`, `gte` del nome), ma 5 km/h su un'auto più lenta o più veloce non
  sono la stessa cosa.
- Un punteggio di costanza da mostrare al pilota.

## Anti-obiettivi

- Buttare i giri migliori.
- Scambiare un cambio d'assetto per un errore di guida.
- Una soglia tarata a occhio: è quella misurata, e se il rigioco dell'archivio dà una
  quota molto diversa ci si ferma e si riguarda prima di installare.
- Un contatore muto: se uno stint non arriva a una lettura perché i giri vengono tolti,
  la frase lo dice a ogni giro tolto.

## Approcci

1. **Dentro l'Ingegnere** — *scelto dal pilota*. La diagnosi di ogni giro aggiunge la
   velocità minima per curva con la posizione della curva; l'Ingegnere confronta i giri
   dello stint e toglie dalla finestra quelli incostanti, anche a posteriori; la frase è
   quella delle uscite; il registro lo scrive. *Pro:* uguale in pista e nel rigioco, quindi
   verificabile subito sulle serate vere; un posto solo per tutte le letture. *Contro:* la
   finestra oggi può solo allungarsi; il conto «servono ancora N giri» e quello di una
   prova in corso devono poter tornare indietro.
2. **Nel motore dell'app, prima di passare il giro all'Ingegnere.** Scartato: giudica un
   giro solo quando arriva, quindi non può mai giudicare i primi due di uno stint, e il
   rigioco (che non passa dal motore dell'app) non lo vede.
3. **Filtro a ogni lettura** (la finestra resta com'è, ogni calcolo salta i giri
   incostanti). Scartato: i punti che leggono la finestra sono una decina (lettura delle
   pressioni, mediane di tempo e sintomo, sintomo dominante, persistenza, curve…),
   dimenticarne uno è facile, e la frase al pilota diventa difficile da dare al giro
   giusto.

## Come si costruisce (deciso)

**La misura, nella diagnosi.** `coaching.diagnosis.build_lap_stats` aggiunge a `LapStats`
la velocità minima di ogni curva che riceve: per curva, la posizione dell'apice
(`Corner.apex_pos`), la velocità minima (`speed_kmh` minima fra i campioni con
`entry_pos <= pos <= exit_pos`) e il nome, se il chiamante lo passa (`corner_names`). In
pista le curve sono quelle del riferimento del motore, coi nomi; nel rigioco
(`engineer/replay.py`, che chiama `build_lap_stats(lap)` senza curve) sono quelle
rilevate sul giro stesso, senza nomi.

**Curve accoppiate per posizione, non per numero.** In pista le curve si ricalcolano
quando cambia il riferimento (nuovo miglior giro, `engine._rebuild_reference`), e nel
rigioco ogni giro ha le sue: i numeri non si corrispondono. Due curve sono la stessa se i
loro apici distano al più 0,01 di giro, misurati sul cerchio (vicino al traguardo 0,995 e
0,003 sono vicine). *[mia scelta: a Imola circa 50 m; con le curve del riferimento
coincidono esattamente, nel rigioco assorbe le piccole differenze di rilevamento]*

**Il gruppo: stesso stint e stesse manopole.** Dentro uno stint l'assetto può cambiare
senza una sosta: una prova al volante dell'Ingegnere (TC +1), o il pilota che gira una
manopola (il 14/11 il TC è passato fra 3 e 4 dentro lo stesso stint). I giri dopo il
cambio avrebbero curve diverse e sembrerebbero errori di guida. Quindi il gruppo di
confronto è: stesso stint **e** stessi TC, ABS, mappa e ripartitore letti sul giro
(`Lap.tc_level`, `abs_level`, `engine_map`, `brake_bias`, da portare su `LapStats`). Un
valore non letto (giri vecchi, −1 o assente) non spezza il gruppo. *[trovato dopo la
revisione, mia scelta]*

**Il controllo, nell'Ingegnere.** In `RaceEngineer.observe`, dopo che il giro ha il suo
stint ed è entrato nella finestra, e prima di qualunque decisione che legga la finestra:

- si guardano i giri della finestra **del gruppo in corso** che **non aprono lo stint**
  (`settling` falso). *[mia scelta: il giro che apre lo stint ha le gomme ancora in
  salita ed è più lento per natura; nella misura sull'archivio era escluso allo stesso
  modo]* Il giro che apre lo stint resta nella finestra per tutto il resto, come oggi;
- se sono almeno 3: per ogni giro e per ogni sua curva, la mediana della velocità minima
  della stessa curva negli **altri** giri (servono almeno 2 altri giri con quella curva);
  scarto = la sua − la mediana; si contano le curve con scarto sotto −5 km/h;
- se sono almeno 3, il giro è incostante. Si valutano tutti i giri sullo stesso insieme,
  poi quelli incostanti escono insieme dalla finestra;
- un giro tolto non rientra, anche se i giri dopo lo farebbero sembrare normale. *[mia
  scelta: semplice e prevedibile, e il pilota ha già sentito che non conta]*

Le soglie stanno con le altre costanti dell'Ingegnere (`_CONSISTENCY_KMH = 5.0`,
`_CONSISTENCY_CORNERS = 3`, `_CORNER_MATCH = 0.01`). L'interruttore non può stare sul
`Profile`, perché il profilo GT3 è condiviso con GT4, GT2 e GTE: lo passa `engineer_for`
per auto, come già fa con lo scarto del ripartitore misurato (`bias_offset`), acceso solo
per le auto GT3. Come riconoscerle con certezza (il pezzo `gt3` del nome non basta per
tutte le GT3 di ACC, per esempio `audi_r8_lms_evo`) resta al costruttore.

**Una decisione legge solo giri giudicati.** Il pilota ha scelto che un giro incostante
non entri in nessuna lettura. La lettura delle pressioni lo rispetta già (chiede 3 giri
dello stint che non lo aprono). Le altre decisioni no: la base di una proposta
(`len(self.window) >= min_stable`) e il verdetto di una prova (`_Active.laps_seen`)
contano anche il giro che apre lo stint, e possono partire quando nel gruppo ci sono solo
2 giri giudicabili, cioè prima che il controllo abbia mai girato. Regola: una decisione
che legge la finestra usa solo giri già giudicati, più il giro che apre lo stint (che non
si giudica, come oggi conta). I giri di un gruppo che ha ancora meno di 3 giri
giudicabili non contano finché il gruppo non arriva a 3; quelli di un gruppo chiuso così
(uno stint corto) non contano. Effetto: dopo una sosta il verdetto di una prova sul
bilanciamento arriva un giro più tardi; le prove al volante (nessuna sosta, nessun giro
d'apertura) restano a 3 giri; le pressioni non cambiano. *[deriva dalla scelta B del
pilota; il meccanismo resta al costruttore]*

**Una decisione data non si rimangia.** *[mia scelta]* Mentre una proposta aspetta di
essere applicata, il controllo non toglie giri: la base su cui è stata calcolata resta
quella. Altrimenti la proposta sparirebbe dallo schermo (il difetto del 13/10), e una
prova di pressione applicata dopo una rimozione nascerebbe senza la sua lettura di
partenza (`_base_pressures` vuoto) e verrebbe giudicata sul tempo senza dirlo. Un verdetto
già dato e scritto nel registro non si rivede.

**Le letture si aggiustano da sole.** La lettura delle pressioni (`_reading_laps`), le
mediane e il sintomo dominante leggono la finestra: un giro tolto ne esce. Fa eccezione il
conto dei giri di una prova in corso (`_Active.laps_seen`), che oggi si incrementa quando
un giro entra: un giro tolto che era stato contato va scontato.

**La frase** (italiano e inglese, nello stesso meccanismo di `_skip_tail`):

- il giro appena chiuso: «L'ultimo giro non conta: a Tosa, Piratella e Rivazza sei
  passato più piano di oltre 5 km/h rispetto agli altri giri di questo stint.»
- un giro di prima, tolto a posteriori: «Il 2° giro di questo stint non conta più: …»
  (serve sapere il numero del giro nello stint: il motore lo conosce già,
  `RaceEngineer._stint_lap`, e va messo sul giro);
- senza nomi (rigioco, o una curva senza nome): «in 4 curve». Con più di 3 curve, le
  prime 3 per scarto e «e altre N».

La frase deve dire quale giro, dove, di quanto e rispetto a cosa. La forma esatta resta
al costruttore, nei vincoli del test sul tono (`tests/test_tono.py` vieta le frasi
ripetute fra i messaggi). Va detta **qualunque** sia la decisione di quel giro: oggi
`_skip_tail` viaggia solo sui messaggi di attesa e di conto, e una rimozione nel giro di
una proposta, di un verdetto, di «finito» o di un'attesa delle pressioni resterebbe muta.
Come agganciarla resta al costruttore; il registro la tiene comunque.

**Il registro.** *[mia scelta]* La riga `lap` di ogni giro riceve un campo con i giri
tolti a quel giro (stint, numero nello stint, curve con il loro scarto), vuoto quando non
ne è stato tolto nessuno. Così dopo una serata si ritrova senza rigiocare.

## Verifica

1. **Test dell'Ingegnere**, con giri finti: un giro più lento in 3 curve esce; in 2 curve
   resta; più veloce in 4 curve resta; il giro che apre lo stint non viene giudicato e
   non fa da confronto; giri di stint diversi non si mescolano; con 2 soli giri non si
   giudica; tolto a posteriori, con la frase giusta; in una prova in corso il conto dei
   giri scende; Formula e stradali non cambiano; curve con numeri diversi e apici vicini
   si accoppiano, anche a cavallo del traguardo; un cambio di manopola dentro lo stint
   spezza il gruppo; una decisione non parte su giri non ancora giudicati; con una
   proposta in attesa non si toglie niente; la frase c'è anche quando la decisione del
   giro è una proposta o un verdetto; GT4 e GTE non cambiano.
2. **Rigioco di tutto l'archivio della 720S** con `replay-engineer`: quanti giri puliti
   vengono tolti negli stint con almeno 3, quali, e quanto erano più lenti sul cronometro.
   Atteso intorno a 1 su 5 (15 su 79 rimisurati con le regole del motore). Il motore
   giudica con meno giri a disposizione della misura (la finestra tiene 6 giri, il
   controllo gira man mano che i giri arrivano, e chi viene tolto presto non rientra),
   quindi la quota può essere un po' diversa: se esce dall'intervallo 10-30 %, ci si
   ferma e si riguarda prima di installare. Per ogni giro tolto: il tempo rispetto agli
   altri giri del gruppo.
3. **Le sette serate rigiocate il 16/11**: confronto prima/dopo, riga per riga, e
   spiegazione di ogni differenza.
4. **Suite intera** con la casa finta.

## Cosa resta al costruttore

- Nomi e forma dei campi nuovi (velocità minima per curva sul giro, numero nello stint,
  giri tolti nel registro).
- Come tenere coerente il conto di una prova in corso (ricalcolarlo o scontarlo).
- La frase esatta, nei vincoli sopra.
- Il punto preciso di `observe` dove sta il controllo, purché dopo l'assegnazione dello
  stint e prima di ogni decisione che legge la finestra.
- Il meccanismo con cui le decisioni usano solo giri giudicati, e come riconoscere le
  auto GT3.
- Come agganciare la frase a qualunque decisione del giro.

## Dopo questa tappa

- «c»: il confronto base/prova curva per curva, con le curve accoppiate per posizione
  (lo stacco lungo ripetuto in tutti i giri della prova la dispersione non lo vede).
- La costanza sullo stacco, con le serate registrate dal registratore nuovo.
