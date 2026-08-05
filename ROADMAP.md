# Roadmap HONE

Evidenza raccolta il **2026-07-22**, stato delle voci riverificato **contro il
codice** il **2026-07-31**. Ogni voce dice da dove viene: una richiesta reale
misurata, un difetto trovato in casa, o un'ipotesi nostra. Le ipotesi nostre sono
etichettate come tali, perché in questo progetto ne abbiamo già sbagliate due in
un giorno.

> **Come si aggiorna questa tabella.** Una voce si dichiara fatta solo dopo aver
> aperto il codice che la chiude, non a memoria: la riverifica del 31/07 ha
> trovato **sette voci ancora scritte come aperte che erano state implementate**
> fra il 22 e il 23 luglio. Una roadmap che sopravvaluta il lavoro rimasto
> costa quanto una che lo sottovaluta — si finisce a rifare cose già fatte.

---

## Evidenza raccolta il 2026-07-22

Panel di tre tracce (concorrenza, audit prodotto, red team) + lettura diretta di
Reddit. Cosa ne è uscito, in ordine di quanto sposta le decisioni.

### 1. Il "perché" è confermato dagli utenti, con le nostre stesse parole

Non è più una tesi nostra. In un thread di 11 giorni fa sui coach AI, un utente
li liquida dicendo che si limitano a dire *«frena 10 metri dopo»* e che quello
non serve a niente. In un altro thread la critica è più precisa: *«prova a
frenare 50 metri più tardi» è inutile se non hai un punto di riferimento comune*.
E su Garage61 — lo strumento che la comunità consiglia davvero — la domanda posta
da un utente è letteralmente la nostra tesi: **ti dà solo le informazioni, o ti
dice cosa significano?**

### 2. I punti di frenata visivi sono una domanda MISURATA, non un'intuizione

Un post con **332 voti** presenta una "cheat sheet" statica dei punti di frenata
di Monza. Il motivo dichiarato dall'autore: non sopportare venti minuti di video
YouTube solo per trovare il punto della Parabolica. L'autore stesso osserva che
**i punti si spostano di 10-20 m** a seconda dell'auto (296 vs Porsche) e della
temperatura della pista, e propone una web app che li adatti ad auto e
condizioni. La reazione della comunità è entusiasta, con richieste per altre
piste.

Due cose importanti dentro questo dato:
- il pubblico **vuole i riferimenti**, e li vuole adattati alle condizioni;
- la critica più tagliente al post è che *i punti di frenata sono dinamici giro
  dopo giro in gara* — che è esattamente il limite di una scheda statica, e
  esattamente dove uno strumento **live** vince.

E la richiesta raccolta altrove è di un livello ancora superiore: riferimenti
**visivi** («frena all'inizio del cordolo bianco e rosso», «appena dopo l'inizio
della recinzione»), non metri. Nessuno lo fa.

### 3. Gli aiuti vanno saputi togliere

Due utenti indipendenti descrivono lo stesso percorso: imparano con traiettoria e
indicatori di frenata, poi **li rimuovono uno alla volta**. Uno avverte che col
coach AI *è facile perdere la prospettiva e guidare i toni di frenata invece
dell'auto*. Un altro consiglia di tenere l'assistente in modalità a segnale
singolo, e di alternare due giri senza e due giri con **un solo tema** di
consiglio.

Quest'ultimo punto è la validazione esterna del layer Focus/Lesson: gli utenti
esperti si costruiscono a mano il "una cosa alla volta" che noi già facciamo.

### 4. Il vocabolario dei coach umani veri

Da un thread in cui un pilota fermo a 2:20 a Spa chiede aiuto e riceve risposte
lunghe e tecniche. Cosa nominano gli umani che noi **non** rileviamo:

- **il gas parziale tenuto troppo a lungo** (l'1-90% mantenuto in percorrenza):
  viene indicato come causa diretta di sottosterzo, con l'alternativa esplicita
  «o freni più tardi e moduli usando il carico sull'anteriore per completare la
  rotazione, o fai coasting *prima* di aprire — e quando apri, 100% appena puoi».
  Noi rileviamo il coasting, non il gas parziale.
- **il sollevamento dove si dovrebbe essere in pieno**, quantificato e
  moltiplicato per il rettilineo che segue («quel sollevamento ti è costato .3,
  forse .5, per via della lunghezza del Kemmel»).
- **la velocità massima sul rettilineo come indizio di setup**: «io arrivo a
  271-272 in qualifica, forse stai usando un'ala troppo alta». È diagnosi causale
  di setup ricavata da un solo numero che noi già registriamo.
- **la granularità giusta cambia col livello**: «al tuo ritmo è più questione di
  tecnica generale che di analisi curva per curva». Noi facciamo sempre e solo
  analisi curva per curva.

### 5. Il mercato è ostile a "coach AI", e ci riguarda

Alla domanda «quale coach AI compro per ACC» le risposte sono state *nessuno* e
insulti. Uno sviluppatore che presentava uno strumento di telemetria per AC si è
preso *«è vibe-coded»*, con la spiegazione che nel sub ne escono 2-3 a settimana
e non piacciono a nessuno.

Nello stesso sub, la scheda dei punti di frenata ha preso 332 voti. **Stesso
pubblico, stesso problema, reazione opposta a seconda di come è presentato.**

### 6. Dove siamo scoperti secondo l'audit interno

- Il riferimento sei sempre e solo tu: chi è a 3 secondi dal passo si allena
  contro il proprio 3-secondi-lento. L'import di un giro esterno esiste solo da
  riga di comando.
- L'elezione del riferimento **ignora le condizioni** che pure registriamo
  (temperatura aria/asfalto, grip, mescola sono in SQLite e non li legge
  nessuno). Il punto 2 qui sopra dice che è proprio ciò che sposta i riferimenti
  di 10-20 m.
- Segnale registrato e mai usato: `g_lat`/`g_long` (il grip combinato è la
  risposta al «perché non posso frenare più tardi»), forma delle curve,
  scostamento dalla traiettoria, temperatura freni.
- Tutte le soglie sono tarate su **tre auto, tutte su AC**. Su ACC non è mai
  stato calibrato niente, perché fino al 20 luglio non registrava.

### 7. Concorrenza: due differenziatori su tre si sono ristretti

- **Diagnosi causale**: Track Titan ha chiuso $5M dichiarando come obiettivo
  esplicito il «capire *perché* perdi tempo»; Coach Dave "Auto Insights" usa già
  linguaggio causale debole **da marzo 2025**, cioè da prima che noi
  rivendicassimo il vuoto. Nessuno però fa ancora diagnosi *fisica*.
- **Setup AI su AC**: Track Titan elenca già AC liscio; onRails ha lanciato il 22
  luglio 2026 posizionandosi su AC e sul «ragionamento dietro ogni modifica».
- **Italiano + offline**: nessun concorrente controllato lo offre. Regge.

---

## Cosa resta aperto

**Una sola**, la 18, e le serve tempo al volante. La misura che le manca ha una
proprietà che le altre non avevano: **non aspetta il meteo né la fortuna**.

La 2 è stata chiusa il 04/08 dal lato che mancava — le parole le scrive il
pilota — e con lei è caduto l'ultimo pezzo che dipendeva da «qualcuno che quelle
piste le abbia davanti agli occhi».

Fuori da questa tabella restano aperte due cose che **non** sono tempo in pista,
e vale la pena non confonderle con la sessione qui sotto:

- **Le clip recitate per la voce di marca** ([[voice-naturalness-todo]]): 2-3
  registrazioni da 10-15 s (neutra / severa / calda), da cui Chatterbox clona la
  voce del coach a *build time*. Ferma dal 02/07 sul **casting**, non sul codice.
- **I 7 circuiti in bundle senza tabella curva** (`corner_atlas.HELD`).
  Erano tredici: il 04/08 ne sono caduti tre — Sepang, il Red Bull Ring e Shanghai —
  perché la regola «conteggi diversi, niente tabella» era **sbagliata** (la
  numerazione ufficiale fonde i complessi) e quello che decide è la **sequenza
  dei versi**. Il 05/08 ne sono caduti altri due, **Melbourne** e **Sakhir**,
  e li ha fatti cadere lo stesso difetto di ragionamento: in entrambi i casi il
  conteggio degli apici **coincideva** con quello pubblicato e quella
  coincidenza era falsa. A Sakhir i quindici apici per quindici curve non
  contenevano la T5 (r=352 m, «T5 isnt really recognizable» lo dice la guida) e
  ne contavano due volte altre due. Il metodo che ne esce è: **il conteggio non
  è mai una conferma, nemmeno quando torna**. Gli altri sono stati riattaccati con lo stesso
  metodo e i motivi ora sono **misurati**, non contati: Yas Marina è chiuso dal
  metro (la traccia fa 5542 m e tutti e due i tracciati pubblicati ne fanno
  5281), Budapest e Sochi da fonti che si contraddicono e da una geometria che
  **non arbitra** — a Budapest le due letture opposte fanno entrambe 14/14.
  **Moscow Raceway** ha cambiato motivo il 05/08: il conteggio pubblicato che
  mancava ora c'è (il metro sceglie il «Full Circuit», 4058 m di traccia contro
  4.070 km, e la variante successiva delle diciotto sta quattro volte più
  lontano), ma quel tracciato è dato a **21 curve** e il rilevatore ne trova 19
  da 200 a 600 m (18 a 150) — e quel 21 sta su una riga **senza citazione**, con
  una lunghezza che altrove la stessa pagina dichiara «di progetto» e una tabella
  che si contraddice da sola su un'altra variante. Soprattutto, **nessuna fonte
  descrive quella strada curva per curva**: le guide che percorrono il giro sono tutte scritte per il Grand
  Prix #1 corso in gara, 3.955 km e 15 curve, che è una strada diversa.

| # | Voce | Origine | Cosa manca davvero |
|---|---|---|---|
| ~~2~~ | ~~**Riferimenti visivi**~~ («al cordolo», «al cartello») | richiesta esplicita | Il meccanismo **funziona end-to-end**: verificato il 31/07 sui giri Monza in archivio, la scheda frenate stampa *«Parabolica — alla fine del verde sulla sinistra»*. Manca la **copertura**, e il 31/07 si è capito che non si chiude da scrivania: a Imola due fonti indipendenti **si contraddicono su quasi ogni curva** (cartelli contro flag-light), e la distanza stacco→apex misurata non arbitra fra un cartello dei 50 e uno dei 100. Le posizioni sono già misurate, le parole no. Spa e Suzuka hanno un ostacolo in più: i riferimenti in archivio sono una monoposto e una stradale, e i cartelli delle guide sono tarati sulle GT3. **Chiusa il 04/08** dalla parte che mancava: la colonna «Riferimento visivo» della scheda frenate si scrive, e quello che scrivi finisce anche nella frase del coach (`POST /api/braking-reference`, stesso file dei nomi curva). Non è una rinuncia alla curatela — è che l'arbitro giusto è chi ha la curva davanti, e le fonti non lo erano |
| 18 | **Passo gara: stint, degrado, benzina** | difetto trovato in casa (03/08) | **Metà fatta il 03/08**: la scheda «Passo gara» esiste (`stints.py` + `/api/stint`), taglia gli stint dove il serbatoio **risale** — cosa che `fuel_used` non può vedere, perché un rifornimento *fra* due giri lascia normali le due bruciature — e riporta passo, dispersione, consumo, autonomia e gomme su **un pieno solo**. Resta aperta perché la domanda vera è ancora senza risposta: **il coefficiente secondi/litro non è estraibile da questo archivio** (il rumore di guida, 115→221 s sugli stessi 15 giri, domina il peso della benzina di due ordini di grandezza), quindi la pendenza del passo esce **netta e non attribuita**, con la sua barra d'errore — e sull'unico stint lungo in archivio è +0.26 s/giro con errore standard 0.22, cioè la scheda dichiara «nessuna deriva misurabile». È anche la ragione per cui il **veto sul tempo dell'ingegnere è di fatto spento**: consumo misurato 3.1-3.3 L/giro (720S/Monza), quindi bastano **0.6 giri** di disallineamento per superare `_FUEL_BIAS_L`. Serve la prova corta qui sotto: da lì la pendenza si separa in benzina e gomme, e l'ingegnere recupera metà del criterio di accettazione |
| ~~11~~ | ~~**Tarature su ACC**~~ | mai fatte | **Chiusa il 02/08**, in pista (720S GT3/Monza, poi SF25/Red Bull Ring su AC). Tutte e tre le soglie **promosse senza correzioni** e i cinque controlli strutturali passati; risultati in [`TARATURE-ACC.md`](TARATURE-ACC.md). Il pezzo non ovvio: **con l'ABS acceso il bloccaggio fisico non avviene** (mai sotto `-0.106` in 11 690 frame), quindi flag e slip si dividono il lavoro — per vedere il fondo dello slip è servito **spegnere l'ABS**. Restano fuori dal conteggio tre righe del piano (gas parziale, coach al primo giro lanciato, riferimenti visivi di Monza) e il **burst lock**, che in quattro minuti di Formula senza ABS non è mai avvenuto |
| ~~12~~ | ~~**Documentazione allineata**~~ | segnalazione utente | **Chiusa il 31/07.** `GUIDA.md` e `docs/FAQ.md` il 30/07; `docs/index.html` (la pagina pubblica, ferma al 29/06) riscritta il 31/07 con quello che l'app fa davvero, e con la sola differenza fra i due giochi dichiarata invece che taciuta. L'**aiuto contestuale nelle impostazioni** risulta fatto e testato da prima (un «?» per riga, `tests/test_settings_help.py` verifica pure che righe e testi coincidano) |

## La prossima sessione in pista (pianificata il 2026-08-03)

Cinque misure, tutte bloccate sulla stessa risorsa scarsa: **il tempo al
volante**. Sono qui insieme perché è più economico prenderle in una sessione
sola che tornare cinque volte, e in quest'ordine perché le prime due sbloccano
del codice già scritto.

| Cosa | Perché è bloccata | Il protocollo, in una frase | Costo |
|---|---|---|---|
| **Stint per la benzina** (voce 18) | Il coefficiente s/litro non si estrae dall'archivio: il rumore di guida domina di due ordini di grandezza. Dal 03/08 la scheda che lo consumerà **c'è già**: misurato quel numero, la sua pendenza si separa in benzina e gomme invece di restare netta | Uno stint di giri il più costanti possibile **a setup fisso, dal pieno fino a scendere** | ~20 min |
| **Campi pioggia ACC** | Gli offset del tail si misurano, non si indovinano — `isValidLap` sta a 1408 perché qualcuno l'ha visto muoversi | `python -m accoach find-rain`, poi **alzare la pioggia dal menu** senza fermarlo: `rainIntensity` sale, `trackGripStatus` scende | ~10 min |
| **`yaw_baseline` Formula** | Il 2.50 fu tarato il 27/06 su SF25/Nürburgring, che è una delle sessioni col **canale sterzo tosato**: quel numero non è confermato | Tre giri SF25 **con la periferica delle sessioni del 02/08** (passo sterzo 0.0004, non 0.009) | ~10 min |
| **Burst lock** | In quattro minuti di Formula senza ABS non è avvenuto **nessun** bloccaggio: resta aperta per evento mancato, non per soglia | Tre frenate volutamente bloccate, ABS a 0 | ~5 min |
| **Parola di attivazione** | La sintesi vocale serve a **bocciare**, non a promuovere: «ehi copilota» torna esatta con una dizione perfetta, non è detto con la voce del pilota in abitacolo | Dieci risvegli a motore acceso, poi si guarda `assistente-udito.jsonl`. Lo strumento è in [`tools/voce/`](tools/voce/README.md) dal 03/08 — prima stava nello scratchpad di una sessione, cioè in una cartella temporanea | ~5 min |

Le prime due sbloccano codice che esiste già e non fa niente: la finestra
pressioni sul bagnato (`engineer/pressures.py`, scritta e mai raggiunta) e il
veto sul tempo dell'ingegnere, oggi sospeso praticamente sempre.

## Cosa è stato chiuso, e da cosa

Riverificato aprendo il codice il 2026-07-31, non a memoria: le voci 3, 5, 6, 7,
8, 9 e 10 erano ancora scritte come aperte pur essendo state implementate fra il
22 e il 23 luglio.

| # | Voce | Chiusa | Dove sta |
|---|---|---|---|
| 5 | **Gas parziale** tenuto in percorrenza | 22/07 (`4e84f66`) | `coaching/braking.py` (`_held_partial_throttle`) + cue `PARTIAL_THROTTLE`. È letteralmente la prima cosa che il coach umano del thread nomina |
| 6 | **Sollevamenti in zona di pieno**, quantificati | 22/07 (`f43585e`) | `coaching/debrief.py` (`_lift_notes`): il costo è misurato **dal sollevamento fino a dove il riferimento stacca il gas**, cioè sul rettilineo che segue, com'era la richiesta |
| 7 | **Velocità di punta → ipotesi ala/drag** | 22/07 (`f43585e`) | `debrief._top_speed_note`: distingue i due casi, *drag* se le velocità in curva combaciano, *uscita* se no — non attribuisce all'ala un problema di trazione |
| 10 | **Riferimento PRO con interfaccia** | 22/07 (`daade07`) | `launcher.py` (`_import_pro`): esisteva solo da riga di comando, quindi in pratica il livello «riferimento PRO» era irraggiungibile |
| 8 | **Grip combinato (G-G) come causa** | 22/07 (`cf1d6dd`) | `debrief._combined_g`, confrontato col riferimento al **95° percentile** e non al massimo (un cordolo o un dosso non sono aderenza usata) |
| 3 | **Aiuti che si ritirano** | 23/07 (`58cff24`) | `coaching/focus.py`: le curve *domate* restano tali fra una sessione e l'altra e non vengono più insegnate |
| 9 | **Granularità per livello** | 23/07 (`7b84037`) | Se il divario è troppo grande il debrief apre col **tema del giro** e si ferma lì: `MAX_STEPS_WITH_HEADLINE = 2`, perché seguire quella frase con tre curve la contraddirebbe |
| 1 | **Frenate adattate ad auto e condizioni** | 30/07 | Scheda «Le tue frenate» (`braking_points.py` + `/api/braking`): i **tuoi** ultimi giri nella stessa fascia di temperatura, con la **dispersione** che dice se un punto di frenata ce l'hai davvero. È la cheat sheet dei 332 voti, ma misurata su di te |
| 4 | **Condizioni pista nel riferimento** | 30/07 | Temperatura asfalto, poi gomma e grip — in SQLite dal 20/07 e letti da nessuno. Misurato sui 39 giri veri: **il grip su ACC è 0 su 15 giri su 15** (serve dichiarare `trackGripStatus`; si valida ai box, senza guidare) |
| 13 | **Effetto a catena fra curve** | 30/07 | `coaching/chain.py`: se la perdita era già nei km/h con cui arrivi, ti manda sulla curva prima. È il loro *Timekiller*, ma noi la causa fisica ce l'abbiamo |
| 14 | **Piano di allenamento** | 30/07 | `coaching/plan.py`: obiettivi dai punti deboli **sistematici**, accettati (quindi con una data), misurati **solo sui giri successivi** |
| 15 | **Avvio automatico col gioco** | 30/07 | `watch.py`: parte il **solo registratore silenzioso**, spento di default, mai la voce |
| 16 | **Tempo perso per fase in curva** | 30/07 | `coaching/phases.py`: ingresso / apex / uscita / tratto dopo, pezzi che **risommano** al totale — scomposizione, non stima |
| 17 | **Nomi curva oltre Monza e Imola** | 30/07 | Spa e Suzuka, misurati dai giri in archivio e confermati su tre letture concordi. Il difetto trovato: un nome raggiungeva la curva accanto, e la leva non era la tolleranza ma il **verso** della curva. Portato a **20 circuiti curati** fra il 03/08 e il 05/08 senza guidarne nessuno: le linee centrali in bundle partono dal traguardo, quindi la frazione d'arco *è* una posizione (12-33 m di errore contro 290 di tolleranza), e `tools/corner_atlas.py` le misura. I sette che restano non sono lavoro non fatto: sono in `corner_atlas.HELD` con scritto cosa li ferma, e `--check` protesta se uno di loro viene curato senza aggiornare la nota. Melbourne, chiuso il 05/08, è il caso che insegna di più: a soglia 150 m il conteggio cade **esattamente sulle 16 curve pubblicate**, e quell'assegnazione è **falsa** (mette T9 e T10 entrambe a sinistra, dove la fonte dice destra-sinistra). A sbloccarlo non è stata una lista di versi ma **due frasi sulla struttura** più l'aritmetica: delle cinque coppie destra-poi-sinistra della traccia, quattro non lasciano spazio a 8 curve davanti e 6 dietro, quindi il complesso T9-T10 è **forzato**. Attenzione a non raccontarla più grossa di com'è, e una verifica del 05/08 ha dovuto correggere proprio questo: l'eliminazione fissa **quattro righe, non tredici**, e da sola lascia **otto** sequenze ammissibili. A chiudere la sequenza sono le fonti — una guida che percorre il tracciato di oggi curva per curva e dichiara lei stessa la rinumerazione del 2022 («now designated Turns 9 and 10, formerly 11 and 12»), quindi tradotta all'indietro dà tutti e sedici i versi. La corroborazione più bella resta però il vincolo globale, perché è stato **previsto prima di essere letto**: la ricostruzione dava 6 sinistre e 10 destre, e la fonte trovata in seguito lo dice testualmente. **Sakhir**, chiuso lo stesso giorno, aggiunge il secondo insegnamento: a bloccarlo non era un verso ma **un vuoto**. Le ultime quattro destre combaciavano una a una con T12-T15, e quell'allineamento metteva 790 m di rettilineo fra la T14 e la sua stessa uscita; la fonte dice invece che il rettilineo sta *fra T13 e T14*, e nella geometria ce n'è uno solo di quella taglia. Spedito a **14 righe su 15**: la T15 non ha una posizione perché non è una curva — due fonti indipendenti la chiamano l'uscita della T14 — e inventargliela sarebbe stato il difetto peggiore. **Montreal**, terzo della giornata, chiude il cerchio metodologico: era fermo perché due guide si contraddicono a T5-T7 (una legge L,R,L, l'altra R,L,R) e un circuito numerato è tutto o niente. Ma quella contraddizione **la geometria la arbitra**, ed è la differenza esatta con Budapest, dove le due letture opposte facevano entrambe 14/14: qui la coda è forzata (sei curve, sei apici da 0.464 in poi) e con la T3 destra e la T4 sinistra — che la guida contesa dichiara lei stessa — la lettura con la **T7 sinistra non ha nemmeno un'assegnazione ammissibile**. Non è meno probabile, è impossibile su quella strada. La seconda fonte lo ha poi detto a parole («Turns 6/7: this time, to the left and then the right») e ha spiegato anche l'apice di troppo, che è un kink che nessuno numera. Spedito a **13 righe su 14**, con la T14 assente per lo stesso motivo della T15 in Bahrain. **Chiusa il 04/08** con l'unica strada che copre anche i dieci circuiti ACC senza geometria: il nome lo dà il pilota, dalla matita accanto al titolo della curva in Traiettoria (`cornernames.py`, `POST /api/corner-name`). Il suo nome batte il nostro, si toglie con lo stesso gesto e sta in `Documenti/ACCoach/corner-names.json` — **fuori dal catalogo**, che è una cache ricostruibile mentre questo è l'unica copia |

## Arrivato fuori tabella

Cose costruite dopo il 22/07 che non erano in roadmap perché nessuno le aveva
ancora chieste. Elencate qui perché una roadmap che ignora metà del lavoro fatto
non descrive il prodotto.

- **«Il giro spiegato» e «Sessione»** (28/07) — dall'analisi di Track Titan: le
  loro cinque tracce «essenziali» le avevamo già, **il divario era la
  presentazione**.
- **Vista Traiettoria** (30/07) e **la pista vista dall'alto** sotto le due linee
  (31/07): asfalto, cordoli, erba e ghiaia, letti dal **modello delle superfici**
  del gioco — la geometria con cui decide dove sei. Il circuito si riconosce
  **dalla forma del giro, non dal nome**, quindi vale su entrambi i simulatori; e
  chi non ha AC installato ha i **26 circuiti impacchettati**, da OpenStreetMap e
  satellite ([`SPIKE-BORDI.md`](SPIKE-BORDI.md), `src/accoach/tracks/NOTICE.md`).
- **Asse in metri misurati** (31/07) — non `pos × lunghezza`: la distanza dalle
  coordinate, **corroborata con velocità×tempo**, e chi non passa il controllo
  torna alle percentuali invece di mostrare una scala sbagliata.
- **Consumo lungo il giro** (schema v11, 31/07) e **benzina per giro** in
  Sessione.
- **Il pannello gomme era disegnato sullo span sbagliato** (03/08) — stava in
  Andamento, si intitolava «lungo lo stint» e la serie sotto era **ogni giro mai
  registrato** per quella auto e quella pista: sere diverse, temperature diverse,
  rifornimenti in mezzo. Trovato costruendo la voce 18, e risolto spostandolo là
  dove uno stint c'è (con il rimando lasciato in Andamento). Nella stessa
  giornata: **la scorciatoia da tastiera arrivava a 9** e le schede erano
  diventate dieci, quindi l'ultima non si apriva più da tastiera — non rompe
  niente, non logga niente, e ci si accorge solo premendo lo zero.
- **Scheda «Allenamento»** (31/07) — segnalazione utente: *insight e consigli
  dappertutto, ma se non mastichi telemetria non capisci come migliorare*. È il
  passo che mancava dopo la voce 14: il piano diceva **quale** curva e **quale**
  bersaglio, mai **come allenarsi** per centrarlo. Ora ogni obiettivo porta un
  esercizio scelto dalla **fase dominante** della perdita (`coaching/training.py`
  + `/api/training`), con i tuoi numeri dentro e la prossima sessione contata in
  giri. Il piano trasloca qui da Andamento: un obiettivo **è** un passo. Si apre
  a **6 giri validi**; sotto soglia dice quanti ne mancano.
- **Guida e FAQ allineate alle schede** (30-31/07) — chiude metà della voce 12.

## Posizionamento

Non presentarsi come «coach AI». Il pubblico di riferimento respinge
l'etichetta e accoglie lo stesso identico contenuto quando è presentato come
**riferimenti e dati che spiegano**. La strada che quel pubblico rispetta è
mostrare la diagnosi su dati veri.

## Cosa NON facciamo, e perché

- **Cloud e giri condivisi in stile Garage61**: è ciò che la comunità consiglia
  davvero, ed è anche il motivo per cui non possiamo batterli sul loro terreno
  (effetto rete). Restiamo offline: è un differenziatore che regge, non un
  ripiego.
- **Nuove diagnosi sopra soglie non validate**: ogni voce che parla al pilota
  deve passare da una sessione live prima di essere accesa. Un consiglio sicuro e
  sbagliato è il difetto peggiore per un coach, e ne abbiamo già corretti tre in
  un giorno.

---

## Nota sul peso dell'evidenza

I dati Reddit vengono da una manciata di thread letti direttamente il 2026-07-22.
È sentiment reale e non filtrato da chi vende qualcosa — al contrario dell'unico
"comparativo indipendente" trovato in rete lo stesso giorno, che si è rivelato
pubblicato dall'azienda che vende uno dei prodotti recensiti. Ma **non è un
campione statistico**: la scheda di Monza a 332 voti è il singolo dato con un
peso serio, il resto è convergenza qualitativa fra utenti diversi.
