# Curva per curva — la sessione intera, e cosa dicono le fonti

Stato: proposta del 10/11, da approvare. Il pilota ha chiesto di saltare le domande
(«salta le domande e arriva con una proposta»): tutte le scelte qui sotto sono mie,
segnate *[mia scelta]* quando non sono sue parole.

## Perché

Le parole del pilota, l'08-09/11, dopo il test a Imola:

- «dove frenavo male e che traiettoria sbagliavo»;
- «voglio sapere dove sta la linea giusta anche se non l'ho mai fatta».

Oggi il report risponde a pezzi e sempre su un giro solo. Il «Confronto» mette un giro
contro il riferimento, la «Traiettoria» lo stesso, le frenate stanno in fondo al
Confronto. Nessuna vista dice, per una curva, cosa hai sbagliato **di solito** in tutta
la sessione. `session_recap` calcola già la perdita per fase su tutti i giri, ma
nessuna pagina la mostra. E i fatti dalle fonti pubbliche (`trackfacts/*.json`) non li
legge ancora nessuno.

## Cosa si vede *[mia scelta]*

Una scheda nuova, **«Curva per curva»**, nel gruppo «Come è andata oggi», accanto a
Pagella e Sessione. Una riga per curva, ordinate per tempo perso in tutta la sessione,
la peggiore in cima. Una riga si apre in quattro blocchi.

1. **Quanto e dove perdi.** Tempo perso in tutta la sessione e in quanti giri. Le fasi
   (ingresso, apice, uscita, dopo) come mediana sui giri, e la causa che torna più
   spesso, con quante volte. Si misura come oggi: contro il tuo gesto migliore in
   quella curva, se c'è, altrimenti contro il riferimento.
2. **La tua frenata.** Dove attacchi il freno (mediana e dispersione in metri), la
   velocità di stacco e la marcia più bassa, sui giri di questa sessione. Accanto, il
   tuo giro migliore in quella curva. Se la curva ha un riferimento visivo
   (`_LANDMARKS`), la frenata si dice anche rispetto a quello.
3. **La tua traiettoria.** Lo scarto medio dalla linea del riferimento in ingresso, apice
   e uscita, in metri e col verso (dentro o fuori), e lo spostamento dell'apice. Un
   ritaglio della mappa con due linee: il tuo giro migliore in quella curva e il tuo
   giro più tipico della sessione, cioè quello con la perdita più vicina alla mediana.
4. **Cosa dicono le fonti.** I fatti di `trackfacts/<pista>.json` per quella curva, in
   tre gruppi:
   - **Riferimento**: verificato e confermato dal factchecker. Oggi nessuno, su
     Imola e Spa;
   - **Una fonte dice**: le voci `single`, con quanti autori, la citazione breve, il
     link e il minuto del video;
   - **Le fonti non concordano**: le voci contese o respinte, con tutti i valori.
     Esempio: Bus Stop, seconda per due guide, prima per TraxionGG.
   - Gli errori tipici delle fonti (`mistake`) in una riga a parte: «Errori che altri
     segnalano qui».

   Dove il confronto è un fatto, la riga lo mette accanto alla tua guida senza
   giudicare: «Tu: terza. Una fonte: seconda.» Vale solo per la marcia *[corretto
   scrivendo il piano: il nostro spostamento d'apice è rispetto al tuo riferimento,
   non all'apice geometrico che le fonti chiamano anticipato o ritardato, e il
   cordolo non lo misuriamo]*. Il cartello di frenata non si confronta: non sappiamo
   a quanti metri sta il cartello dei 100 sulla mappa di ACC.

## Cosa non deve mai succedere

- **Un'AI nel report.** Tutto viene da numeri dei tuoi giri e da `trackfacts`, con
  regole fisse. Le frasi sono modelli scritti nel codice.
- **Una fonte sola presentata come verità.** «Una fonte dice» non è mai un riferimento,
  non entra nella voce, nel focus o nel piano di allenamento, e non ha il colore dei
  riferimenti (scelta B del pilota, 10/11).
- **Un cartello come obiettivo di frenata.** Nessuna frase «frena ai 100».
- **Il testo grezzo delle fonti.** Solo le citazioni brevi già nel file esportato.

## Fuori da questo lavoro

- La voce e il coach dal vivo: non leggono `trackfacts`.
- Il tablet. La scheda è del report sul PC *[mia scelta: prima si vede se serve]*.
- Mettere i cartelli sulla mappa in metri. Servirebbe una misura, ed è un lavoro a sé.
- Raccogliere altre fonti o altre piste.

## Come si costruisce *[mia scelta]*

- **I dati della sessione.** Un endpoint nuovo, `/api/corners`, per la sessione
  scelta. Per ogni giro valido della sessione si rifà il debrief (`build_lap_debrief`
  con `corner_refs`), e si aggregano perdite, fasi e cause per curva. Si rifà anche la
  traiettoria (`build_line_report`) e si prendono le frenate (`brake_points_of_lap`).
  Si aggrega con regole fisse: mediane, conteggi, ordine stabile. Una sessione con un
  giro solo mostra quel giro, e lo dice.
- **Le fonti.** Un lettore in `accoach/trackfacts/__init__.py`, `load(track)`, col
  percorso dal file come per le altre risorse del pacchetto (`Path(__file__)`). Una
  pista senza file non ha il blocco 4. Un file con una versione che non conosce si
  ignora, e il registro lo scrive.
- **Abbinare le curve.** `trackfacts` usa i nomi del catalogo (`_CORNERS`). Il report
  può avere nomi scritti dal pilota. Si abbina per posizione: il nome del catalogo dà
  la frazione di giro dell'apice, e vale la curva rilevata più vicina, come già fanno
  le viste fra loro.
- **La pagina.** Il JS segue lo stile di `app.js` (le altre schede), senza librerie
  nuove. I testi in italiano col tu, frasi brevi, virgola decimale, e in `docs/FAQ.md`
  e `GUIDA.md` la sezione sulla scheda.

## Vincoli

- Test con la casa finta e senza rete, come sempre. Nessun accesso a
  `Documents\ACCoach` vero.
- `tests/test_tono.py` per ogni frase nuova.
- Niente installazione, push o EXE finché il pilota non lo dice.

## Lasciato al costruttore

- Il disegno esatto delle righe e dei blocchi, dentro lo stile delle altre schede.
- Come mettere in cache i debrief della sessione se il calcolo è lento.
- Le soglie di rumore per dire «di solito» (per esempio una causa che torna in almeno
  metà dei giri), purché fissate in un test.
