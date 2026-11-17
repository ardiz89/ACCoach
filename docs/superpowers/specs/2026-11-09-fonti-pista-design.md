# La linea giusta dalle fonti pubbliche — Imola

Stato: approvato in chat dal pilota il 09/11 («va bene così, procedi con Imola»).
Le scelte segnate *[mia scelta]* non le ha prese il pilota: si possono rivedere.

## Perché

Nel test dell'08/11 il pilota non ha capito come guidare le Acque Minerali, e il
report non lo aiutava: confronta il giro migliore con un altro giro, cioè il
pilota con se stesso. Lui vuole sapere **dove sta la linea giusta anche se non
l'ha mai fatta**: dove si frena, con che marcia, dove si mette la corda, quale
errore è tipico in quella curva.

Su YouTube e Reddit ci sono guide alla pista, onboard commentati e discussioni
sulle piste più note. Da lì si costruisce la base dati che la reportistica
userà. Si parte da una pista sola, Imola.

C'è già un precedente in `src/accoach/trackdata.py`: i riferimenti visivi di
Imola sono vuoti apposta, perché il 31/07 due fonti si contraddicevano su quasi
ogni curva. Questo lavoro serve anche a chiudere quel buco con più fonti e una
regola esplicita.

## Obiettivi

1. Una pipeline ripetibile che, per una pista, raccoglie le fonti pubbliche,
   ne estrae i fatti curva per curva, li verifica e li salva in un database.
2. Per Imola, una base dati di fatti verificati sulle sette curve del
   catalogo: Tamburello, Villeneuve, Tosa, Piratella, Acque Minerali,
   Variante Alta e Rivazza. I tipi di fatto sono:
   - punto di frenata, cioè il cartello o un riferimento visivo;
   - marcia;
   - corda;
   - uso del cordolo;
   - linea in entrata e in uscita;
   - errore tipico.
3. Una pagina di controllo che il pilota possa leggere prima che i dati entrino
   nel report. Per ogni curva mostra i fatti, le fonti e le parti dove le fonti
   non concordano.

## Fuori da questo lavoro

- La vista curva per curva nel report di HONE. Si progetta dopo, guardando i
  dati veri di Imola *[mia scelta: prima si vede cosa esce]*.
- Le altre piste. La pipeline deve funzionare su qualunque pista, ma la si
  lancia solo su Imola.
- Leggere i fotogrammi dei video, cioè HUD, tempi a schermo e posizione
  dell'auto. Si usano solo testo e metadati.
- Una traiettoria disegnata al centimetro. Da queste fonti esce una linea
  descritta a parole e a riferimenti.

## Cosa non deve mai succedere

- **Un fatto inventato.** Tutto ciò che entra nella base dati deve stare,
  parola per parola, nel testo grezzo di una fonte. Vale anche quando a
  estrarlo è un'AI.
- **Un risultato che cambia da solo.** A parità di fonti la base dati è
  identica, ogni volta.
- **L'AI nella reportistica.** Il report legge solo dati congelati e li
  confronta con i giri del pilota con regole fisse.
- **Un riferimento di sicurezza sbagliato.** Un punto di frenata confermato
  da una sola fonte, o contraddetto, non diventa un riferimento.

## Come funziona

### 1. Raccolta (senza AI)

- **Fonti.** Apify scarica:
  - i video YouTube su Imola che hanno un commento, cioè guide alla pista e
    onboard spiegati, con sottotitoli a tempo, canale, data e durata;
  - i thread di Reddit su Imola, nei subreddit di simracing, con i commenti.
  - Quali attori Apify usare lo sceglie il costruttore. Il catalogo del
    progetto Colab Scoring Engine ha già `streamers/youtube-scraper`.
- **Il token Apify.** Si legge dalla variabile `APIFY_API_TOKEN` o da un file
  nella home del pilota, sullo stesso schema della chiave ElevenLabs in
  `tools/render_voice.py`. Il token non si stampa mai e non si scrive mai nel
  repository.
- **Il testo grezzo.** Ogni testo si salva così com'è, con URL, data di
  raccolta e impronta SHA-256 del contenuto. Un testo con un'impronta già
  presente non si risalva.
- Il testo grezzo è contenuto altrui. Sta nel database delle fonti, fuori dal
  repository (vedi «Dove stanno i dati»).

### 2. Estrazione (con l'AI, controllata)

- L'estrazione la fa una squadra di agenti, cioè subagenti di Claude Code con
  istruzioni fisse versionate nel repository e un modello fissato. Lavorano
  un testo grezzo alla volta e rispondono con un JSON a schema fisso.
- Ogni fatto contiene:
  - pista;
  - curva;
  - tipo di fatto;
  - valore;
  - gioco e classe d'auto, se la fonte li dice;
  - la **citazione**, cioè le parole esatte del testo da cui viene;
  - la posizione nel testo, cioè l'offset o il minuto del sottotitolo.
- **Il verificatore**, codice senza AI, scarta un fatto se:
  - la citazione non compare identica nel testo grezzo, ammessa solo la
    normalizzazione di spazi e maiuscole;
  - un numero del valore, come metri, marcia o cartello, non compare nella
    citazione;
  - la curva non si ricava dalla citazione o dalle frasi intorno, usando i nomi
    e gli alias del catalogo di `trackdata.py`.
- Gli scarti si salvano col motivo, così si vede quanto l'AI ha provato a
  inventare.
- **Congelamento.** Il risultato di ogni coppia (impronta del testo, versione
  delle istruzioni, modello) si salva una volta sola. Rilanciare la pipeline
  non rifà i testi già lavorati. Rifare l'estrazione è un comando esplicito,
  che crea una versione nuova e lascia quella vecchia.

### 3. Valutazione delle fonti (con l'AI, controllata)

- Per ogni fonte si registra quanto è affidabile, sempre con le ragioni citate:
  - chi parla, per esempio un pilota o un coach con un nome;
  - quale tempo dichiara o mostra nel titolo o nella descrizione;
  - gioco e auto;
  - cosa ne dice Reddit, quando un thread la nomina.
- Il pilota aveva chiesto in agosto di pesare autore e pubblico «per capire se
  è fuffa». Vedi la memoria `pesare-le-fonti-2026-08-08`.
- Anche qui ogni ragione porta la sua citazione, e passa dallo stesso
  verificatore.

### 4. Consenso (senza AI)

- **Contano solo le fonti su ACC** (deciso dal pilota il 09/11). Le altre
  restano nel database delle fonti, marcate, e non entrano mai nel consenso
  né nell'esportazione.
- **Vocabolario chiuso** *[mia scelta]*:
  - la frenata è un numero di cartello oppure un oggetto con un nome;
  - la marcia è un intero;
  - la corda è anticipata, centrale o ritardata;
  - il cordolo si usa in entrata, all'apice o in uscita, oppure no.

  Una tabella fissa di sinonimi in italiano e inglese porta la citazione nel
  vocabolario, senza AI. L'agente propone un valore. Se la tabella non dà
  lo stesso valore dalla citazione, il fatto si scarta. Linea ed errore
  tipico sono testo descrittivo, si mostrano e non si votano.
- **Fonti indipendenti** *[mia scelta]*: si contano per autore, cioè per
  canale o per utente Reddit, non per video o thread. Chi rilancia un video
  non conta come seconda fonte di quel video.
- **Le frenate** *[mia scelta]* diventano verificate solo se almeno una delle
  due fonti è affidabile, cioè un pilota o un coach con un nome secondo il
  passo 3.
- Un fatto diventa **verificato** quando lo dicono almeno **due fonti
  indipendenti**, cioè due canali o autori diversi. Due video dello stesso
  canale contano come una fonte.
- Se le fonti indipendenti danno valori diversi per lo stesso tipo di fatto
  nella stessa curva, per esempio il cartello dei 100 contro quello dei 150,
  il fatto è **conteso**. Si salvano tutti i valori, con le loro fonti, e
  nessuno diventa riferimento.
- La regola sta nel codice ed è deterministica, compreso l'ordinamento.

### 4b. Fact-check (con l'AI, controllato)

- Il pilota non approva i fatti uno per uno (09/11): «affido il mio check ai
  factchecker».
- Ogni fatto verificato passa da un agente fact-checker separato, con
  istruzioni fisse diverse da quelle dell'estrazione. Il fact-checker
  rilegge le citazioni nel testo grezzo e cerca contraddizioni nelle altre
  fonti ACC di quella curva. Il metodo è quello della verifica adversariale
  di agosto.
- Il suo esito è confermato o respinto, con la ragione citata, e si congela
  come le estrazioni.
- **Si esporta solo un fatto verificato e confermato.** Un fatto respinto
  compare nella pagina di controllo con la ragione.

### 5. Pagina di controllo

Una pagina HTML generata dal database, senza AI. Per ogni curva di Imola
mostra:
- i fatti verificati;
- quelli contesi;
- quelli con una fonte sola.

Accanto a ciascuno ci sono la citazione breve, la fonte e il minuto del
video. Serve al pilota per leggere i dati prima di decidere come entrano nel
report.

## Dove stanno i dati *[mia scelta]*

- **Il database delle fonti** è un SQLite fuori dal repository e fuori da
  `Documents\ACCoach`, in una cartella passata da riga di comando. Contiene
  testi grezzi, estrazioni, scarti, valutazioni e versioni.
- **I fatti verificati** sono un'esportazione deterministica, con ordinamento
  fisso, verso un file nel pacchetto di HONE, accanto a `trackdata.py`. È ciò
  che leggerà il report.
  - Ogni fatto porta l'URL della fonte e il minuto, non il testo grezzo.
  - La citazione nel file è al massimo di 15 parole, e il testo completo resta
    fuori.
- Gli strumenti stanno in `tools/` come gli altri spike, fuori dal bundle
  dell'app.

## Vincoli

- Test sempre con una casa finta e senza rete. Le risposte di Apify e degli
  agenti si registrano in file di prova.
- Niente chiavi o token nei file del repository, nei log o nei messaggi.
- Lo stile dei testi è quello di sempre: italiano col tu, frasi brevi e
  virgola decimale (`tests/test_tono.py`).
- YouTube blocca l'IP per ore se si chiedono troppi sottotitoli. Si passa da
  Apify, a ritmo basso, una pista alla volta.

## Altre scelte mie

- **I nomi alternativi delle curve**, come «T7», «turn 2» o «Acque Minerale»,
  e gli errori dei sottotitoli automatici stanno in una tabella dentro
  `tools/`, non in `trackdata.py`.
- **I riferimenti visivi di Imola** (`_LANDMARKS["imola"]`) non si toccano
  qui. Si riempiono quando si progetta la vista nel report.
- **Gli agenti** sono una sessione di Claude Code che segue istruzioni
  versionate. Gli strumenti Python preparano il lavoro in sospeso e leggono
  i JSON che gli agenti scrivono. Tutto il resto è un comando ripetibile, e
  nei test le risposte degli agenti sono file registrati.
- **Il budget Apify.** È il piano gratuito del pilota, 5 dollari al mese, di
  cui ne restano circa 4,46 fino al 23/11. Il token è quello del progetto
  Colab Scoring Engine. Si legge da lì oppure dalla variabile, senza
  stamparlo, e prima di ogni raccolta si stima il costo. Il tetto per Imola
  lo fissa il pilota.

## Lasciato al costruttore

- Quali attori Apify usare, i filtri di ricerca e quanti video e thread
  raccogliere per Imola. Serve abbastanza materiale da avere almeno due fonti
  indipendenti per curva.
- Lo schema delle tabelle SQLite e il formato del file esportato.
- Come i subagenti ricevono il lavoro e restituiscono il JSON.
- La forma della pagina di controllo.
