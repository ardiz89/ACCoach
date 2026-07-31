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

Tre voci su diciassette. Due delle tre **non si chiudono da scrivania**: sono le
uniche del documento il cui costo non è codice ma tempo in pista.

| # | Voce | Origine | Cosa manca davvero |
|---|---|---|---|
| 2 | **Riferimenti visivi** («al cordolo», «al cartello») | richiesta esplicita | Il meccanismo c'è dal 27/07 (`_LANDMARKS` + `landmark_at`, la nota additiva nel debrief, e la scheda frenate li usa dove esistono). Manca la **copertura** — oggi: **Monza 5 staccate, Imola 0**, tutte le altre piste zero — e soprattutto la **validazione**: nessun landmark ha mai fatto scattare una frase su un giro reale. Aggiungere piste a tavolino senza quella prova moltiplica un meccanismo mai visto funzionare |
| 11 | **Tarature su ACC** | mai fatte | Serve pista. Piano pronto in [`TARATURE-ACC.md`](TARATURE-ACC.md). Il pezzo scomodo è noto: lo **slip ratio ha sorgente diversa fra AC e ACC**, quindi le soglie non si trasportano |
| 12 | **Documentazione allineata** | segnalazione utente | La parte che riguarda chi usa il prodotto **è stata chiusa il 30/07**: `GUIDA.md` e `docs/FAQ.md` ora descrivono tutte le schede (prima l'inglese non nominava l'intera app di analisi). Resta **`docs/index.html`**, la pagina pubblica, ferma al 29/06 — è incompleta, non falsa — e l'**aiuto contestuale nelle impostazioni** |

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
| 17 | **Nomi curva oltre Monza e Imola** | 30/07 | Spa e Suzuka, misurati dai giri in archivio e confermati su tre letture concordi. Il difetto trovato: un nome raggiungeva la curva accanto, e la leva non era la tolleranza ma il **verso** della curva |

## Arrivato fuori tabella

Cose costruite dopo il 22/07 che non erano in roadmap perché nessuno le aveva
ancora chieste. Elencate qui perché una roadmap che ignora metà del lavoro fatto
non descrive il prodotto.

- **«Il giro spiegato» e «Sessione»** (28/07) — dall'analisi di Track Titan: le
  loro cinque tracce «essenziali» le avevamo già, **il divario era la
  presentazione**.
- **Vista Traiettoria** (30/07) e il **nastro d'asfalto** sotto le due linee
  (31/07) — i bordi veri di Kunos, letti da `fast_lane.ai`, e solo dove la pista
  installata è quella guidata ([`SPIKE-BORDI.md`](SPIKE-BORDI.md)).
- **Asse in metri misurati** (31/07) — non `pos × lunghezza`: la distanza dalle
  coordinate, **corroborata con velocità×tempo**, e chi non passa il controllo
  torna alle percentuali invece di mostrare una scala sbagliata.
- **Consumo lungo il giro** (schema v11, 31/07) e **benzina per giro** in
  Sessione.
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
