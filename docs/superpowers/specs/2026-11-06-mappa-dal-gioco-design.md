# La pista vista dall'alto con la grafica del gioco — progetto

Data: 06/11/2026. Chiesto dal pilota in chat, approvato con «tutto chiaro».

## Perché

Il pilota guarda la mappa del circuito in reportistica e vuole vederla «come su
Track Titan», cioè la pista dall'alto come nella realtà. Oggi la mappa del giro
intero mostra due linee nel vuoto. La vista della singola curva ha asfalto,
cordoli, erba e ghiaia, ma come poligoni a tinta unita.

La mappa serve per le analisi. Il pilota l'ha detto così: «nella reportistica si
devono vedere bene le linee, la traiettoria e i punti di frenata». Lo sfondo
serve a riconoscere il posto, mentre le linee devono restare la prima cosa che
si legge.

## Cosa si è già provato (spike del 06/11, usa e getta)

Uno script fuori dal repo ha letto i file installati di Assetto Corsa per
Monza e ha disegnato dall'alto il **modello grafico** della pista con le sue
texture, con sopra un giro vero. È venuto fuori qualcosa che sembra una foto
satellitare: parco, paese, paddock, camion, tribune, la vecchia sopraelevata.
Il giro cade sull'asfalto.

Gli script sono nello scratchpad della sessione e non sono permanenti. Le
lezioni utili sono riportate qui sotto, così il builder non dipende da loro.

Cosa è stato misurato:

- **Risoluzione del paesaggio.** La foto aerea sotto Monza (`top_new`,
  ksMultilayer) è una texture 2048×2048 su circa 2.750 ettari. Fa circa 2,9 m
  per texel, e più dettaglio di così nel file non c'è.
- **Risoluzione della pista.** Asfalto, cordoli, vie di fuga e tribune hanno
  texture fra 0,6 e 4 cm per texel. Lì si può ingrandire quanto si vuole.
- **I quadretti.** Venivano dal campionamento al texel più vicino. Con il
  campionamento bilineare spariscono, e il paesaggio diventa sfocato invece che
  a blocchi.
- **Tempi, con un rasterizzatore Python/numpy triangolo per triangolo.**
  - Monza intera a 1 m per pixel, cioè 1412×2327 px, in 118 s.
  - Un riquadro di 220×280 m a 10 cm per pixel, 2200×2800 px, in 26 s.
  - Un riquadro di 340×240 m a 25 cm per pixel in circa 10 s.
- **Alberi.** Nel gioco sono sagome verticali o quasi, quindi dall'alto quasi
  non si vedono. È accettato.

## Obiettivi

1. In reportistica la **mappa del giro intero** ha come sfondo la grafica del
   gioco vista dall'alto. La mappa si può ingrandire con la rotella e spostare
   trascinandola. Più ci si avvicina, più dettaglio compare, fino a circa 10 cm
   per pixel.
2. La **vista ingrandita della singola curva** ha lo stesso sfondo, al posto
   dei poligoni di `drawSurfaces` / `drawRoad`.
3. Lo sfondo è **attenuato**. Il pilota ha scelto questa versione fra piena
   luce e attenuata. Nello spike i valori erano saturazione ×0,55 e luminosità
   ×0,62 (Pillow `ImageEnhance.Color` e `Brightness`). Sono il punto di
   partenza, non un numero misurato.
4. Sopra lo sfondo restano **le stesse informazioni di oggi, con lo stesso
   significato**:
   - la tua linea colorata per il divario di velocità;
   - il riferimento tratteggiato;
   - i punti di frenata (triangolo ambra per i tuoi, anello ciano per il
     riferimento);
   - la croce del giro perso, i segni del consiglio, il mirino dell'hover e la
     finestra del tratto scelto.
   Ogni linea e ogni segno ha un bordo scuro, così si stacca dallo sfondo.
5. Funziona per i giri di **AC** e anche per quelli di **ACC**, quando la
   stessa pista è installata in AC. Il collocamento è lo stesso fit di
   `trackedges.edges_and_fit`, già usato oggi per asfalto e superfici.

## Non obiettivi

- Foto satellitari vere o qualunque servizio di mappe in rete. HONE resta
  offline.
- Piste che esistono solo in ACC. I suoi file sono impacchettati e non si
  leggono.
- Alberi, ombre o illuminazione realistica. Basta il colore delle texture.
- Il rail resta com'è. È la mappa piccola accanto alle schede, e lì lo sfondo
  sarebbe rumore. Questa è una scelta mia, si può cambiare.
- Overlay di guida, pagina Ingegnere, tablet live. Il progetto tocca solo la
  reportistica.
- **Il tablet.** Il pilota l'ha detto così: «mi basta sul pc, chi userà
  dispositivi vecchi si adeguerà». L'iPad gli serve solo per l'Ingegnere.
  Lo sfondo si scrive per il browser del PC, e i tasselli si servono solo a
  chi apre la pagina dal PC stesso. Chi apre la reportistica da un altro
  dispositivo in rete vede la mappa di oggi, senza errori.

## Anti-obiettivi (lavoro fatto ma fallito)

- **Le linee si leggono peggio di oggi.** Se lo sfondo ruba l'occhio alle linee
  o ai punti di frenata, il progetto ha fallito.
- **Il disegno dice che l'auto era fuori pista dove non lo era.** È la ragione
  scritta in `drawMapTo` (app.js, commento «NO ASPHALT HERE») per cui oggi la
  mappa intera non ha asfalto. Alla scala del giro intero la strada è larga
  circa 10 px, e la linea, larga 2-7 px secondo il divario, ne usciva. Con lo
  sfondo vero il rischio è lo stesso. In nessuna scala la linea deve uscire
  visibilmente dall'asfalto dove l'auto non ne è uscita.
- **Uno sfondo sbagliato o inventato.** Se la pista non c'è, se il fit non
  convince o se un file non si legge, lo sfondo semplicemente manca e la mappa è
  quella di oggi. Vale la regola già scritta in `trackedges.py`: «an edge we
  cannot read is an edge we do not draw».
- **Le immagini lasciano il computer del pilota.** Sono ricavate dagli asset
  del gioco. Si generano in locale, restano in locale e non entrano mai nel
  repo, nel bundle, nell'EXE, nei log o nei report esportati.
- **Si scrive nella cartella del gioco.** I file di AC si leggono soltanto.
- **La reportistica si blocca o rallenta** mentre si prepara lo sfondo.

## Vincoli

- Sola lettura dei file di AC, con lo stesso modo di trovarli di
  `trackedges.spline_path` e `trackmesh.physics_model`.
- Le immagini preparate stanno in una cache sotto la cartella dati di HONE
  (`paths.py`, `~/Documents/ACCoach`). Si possono cancellare e ricostruire in
  ogni momento, e non contengono dati del pilota.
- Nessuna dipendenza nuova se si può evitare. Ci sono già numpy 2.4 e Pillow
  12.1, e Pillow apre le DDS DXT. Una dipendenza nuova va giustificata nel piano.
- Un file da centinaia di MB è un file di un altro: vale la difesa di
  `trackmesh._Reader.need`, con conteggi controllati prima di allocare.
- Test senza i file veri del gioco: la CI non li ha. Servono kn5 sintetici,
  come in `tests/test_trackmesh.py`.
- Testi in italiano col tu, frasi brevi, virgola decimale; GUIDA.md e
  docs/FAQ.md aggiornati (`tests/test_tono.py`).
- Suite con la casa finta, mai `Documents\ACCoach` vero e mai la porta 8778.

## Le parti del come già decise

- **La sorgente.** Si usa il modello grafico della pista, cioè i kn5 elencati
  in `models.ini` con le loro POSITION e ROTATION. A Monza sono `2.kn5`,
  `monza.kn5`, `1.kn5`, `3.kn5`, `4.kn5`, `5.kn5` e `100.kn5`, tutti a zero.
  Il modello di collisione si usa solo per il fit.
- **La vista.** È ortografica dall'alto. Vince la superficie più alta in ogni
  pixel (z-buffer sulla quota), e il colore è quello della texture diffusa con
  campionamento bilineare.
- **Lo specchio.** È lo stesso di `drawMapTo`: X ribaltata, perché le
  coordinate di AC sono mancine.
- **Lo sfondo attenuato** è deciso dal pilota.

## Scelte mie dopo la revisione del documento (il pilota può cambiarle)

- **Da dove viene lo sfondo e come si posa.** Viene solo dalla cartella di AC
  della pista e della configurazione su cui si posa, con il suo `models.ini` o
  `models_<layout>.ini`. Si posa con un fit fatto contro la linea dell'IA di
  quella stessa cartella, con le stesse tre condizioni di `trackedges`:
  residuo piccolo, scala circa 1, migliore delle alternative. Se in
  `edges_and_fit` vince un circuito del bundle, serve un secondo fit contro la
  pista di AC. Se nessuna pista di AC convince, lo sfondo manca. Il nome non
  basta, come dice già `trackedges` (`mount_panorama` contro `rt_bathurst`).
- **Cosa sta sopra la strada.** Ponti, portali, striscioni e tettoie sopra la
  pista non si disegnano dove sotto c'è asfalto o cordolo. La strada resta
  sempre visibile, e la linea non finisce mai su un tetto. Il modo di
  riconoscerlo, per esempio una soglia di quota sopra la superficie della pista
  in quel punto, lo sceglie il builder e lo misura.

## Lezioni dello spike sul formato kn5 visivo

Vanno oltre quello che `trackmesh._walk` legge oggi:

- **Texture.** Intestazione con nome e dimensione, poi i byte (DDS o PNG).
  Vanno indicizzate per offset, non lette tutte: `monza.kn5` pesa 316 MB.
- **Materiali.** Nome, shader, blend (1 byte), alpha test (1 byte), poi un int
  se la versione è > 4, le proprietà (nome + float + 36 byte) e le mappe (nome
  dello slot, int, nome della texture). La texture da usare è quella dello slot
  `txDiffuse`.
- **Nodi di tipo 1.** Hanno una matrice 4×4 (64 byte) che **va applicata**. La
  convenzione è vettore riga: `pos_mondo = [x,y,z,1] @ M_nodo @ M_padre`. Il
  modello fisico non ne aveva bisogno, quello visivo sì.
- **Mesh (tipo 2).** Dopo vertici (44 byte: posizione, normale, uv, tangente) e
  indici vengono id del materiale (int), 12 byte, poi 17 byte. Le mesh di tipo
  3 (con ossa) si possono saltare.
- **Shader.**
  - `ksPerPixelAT`, `ksTree` e i materiali con blend 1 hanno l'alpha:
    scartare i texel trasparenti, sotto circa 100 su 255.
  - `ksMultilayer` mescola txDiffuse con quattro texture di dettaglio secondo
    `txMask`. Lo spike ha usato solo txDiffuse, ed era già accettabile.
  - `ksGrass` copre la maggior parte del terreno di `1.kn5`.
- **Triangoli verticali.** Muri, alberi a sagoma e facce delle tribune hanno
  area nulla in pianta. A Monza intera erano 409.000 su circa 487.000
  disegnati. Si scartano subito.
- **Texture BC7.** Pillow potrebbe non aprirle. Il triangolo si disegna allora
  in grigio neutro o si salta, senza far fallire la pista.

## Cosa resta al builder

- **Come preparare e servire lo sfondo per uno zoom continuo.** Una piramide
  di tasselli è l'idea ovvia. A 10 cm per pixel, Monza intera sarebbe circa
  23.000×37.000 px: non un'immagine sola, e forse non tutta preparata in
  anticipo. Il piano deve dire quali livelli, quando si preparano (alla prima
  apertura, in sottofondo, su richiesta), quanto pesa la cache per una pista e
  cosa vede il pilota mentre aspetta.
- **Il motore di disegno.** Il rasterizzatore Python dello spike è lento. Il
  builder sceglie fra ottimizzarlo con numpy, usare la GPU tramite PySide6
  (già dipendenza) o altro, e misura il tempo per pista.
- **Come applicare l'attenuazione:** cotta nei tasselli o applicata nel
  browser.
- **Come tenere la linea dentro l'asfalto alla scala del giro intero.** Per
  esempio larghezza in pixel legata alla scala, o spessore per il divario solo
  da una certa scala in su. Il vincolo è l'anti-obiettivo sul «fuori pista».
- **Come la pagina sa se lo sfondo c'è.** Per esempio un campo nella risposta
  di `/api/lap` o `/api/trajectory`, e gli URL dei tasselli.
- **L'interazione dello zoom** con hover, finestra del tratto (`RANGE`) e
  ingrandimento `LINE_MAG` della curva.
- **Le altre piste installate.** Imola e Suzuka hanno le superfici dentro il
  modello visivo, e mod diverse sono fatte in modo diverso. Il piano dice su
  quali piste si misura prima di dire «fatto».

## Punti del codice

- `src/accoach/web/app.js`:
  - `drawMapTo` (riga 1431 circa), mappa del giro intero;
  - `drawMap`, `drawRail`;
  - `drawCornerZoom` (riga 5111 circa), con `drawSurfaces` / `drawRoad`
    (righe 1192-1266);
  - `hoverTo` (riga 5768 circa).
- `src/accoach/web/index.html`, `#c-map`.
- `src/accoach/api.py`: `/api/trajectory` (riga 1384 circa, chiama
  `edges_and_fit` e `road_shapes`) e il campo `has_map`.
- `src/accoach/trackedges.py`: `spline_path`, `edges_and_fit`, `Fit` (con
  `apply` e `inverse`).
- `src/accoach/trackmesh.py`: lettore kn5, `physics_model`, `_Reader`.
- `src/accoach/paths.py`: cartella dati.
- `tests/test_trackmesh.py`: come si costruiscono kn5 sintetici.
