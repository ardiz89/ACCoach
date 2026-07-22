# Roadmap HONE

Aggiornata il **2026-07-22**. Ogni voce dice da dove viene: una richiesta reale
misurata, un difetto trovato in casa, o un'ipotesi nostra. Le ipotesi nostre sono
etichettate come tali, perché in questo progetto ne abbiamo già sbagliate due in
un giorno.

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

## Cosa entra in roadmap

Ordinate per rapporto tra quanto spostano il cronometro (o la fiducia) e quanto
costano. Le prime tre hanno evidenza esterna misurata; le altre no.

| # | Voce | Origine | Peso |
|---|---|---|---|
| 1 | **Riferimenti di frenata adattati ad auto e condizioni** | 332 voti su Reddit | medio |
| 2 | **Riferimenti visivi** («al cordolo», «al cartello») invece dei soli metri | richiesta esplicita | medio-grande |
| 3 | **Aiuti che si ritirano** quando sei costante in quella curva | comportamento osservato | medio |
| 4 | **Condizioni pista nell'elezione del riferimento** | audit + evidenza (2) | piccolo-medio |
| 5 | **Rilevare il gas parziale** tenuto in percorrenza | vocabolario coach umani | piccolo |
| 6 | **Sollevamenti in zona di pieno**, quantificati sul rettilineo seguente | vocabolario coach umani | piccolo |
| 7 | **Velocità di punta vs riferimento → ipotesi ala/drag** | vocabolario coach umani | piccolo |
| 8 | **Grip combinato (G-G) come causa** nel debrief | audit interno | medio |
| 9 | **Granularità per livello**: tecnica generale prima dell'analisi curva per curva | vocabolario coach umani | medio |
| 10 | **Riferimento esterno/PRO con interfaccia** | audit interno | medio |
| 11 | **Tarature su ACC** | mai fatte | serve pista |
| 12 | **Documentazione e tutorial allineati** (fermi al 29/06) + aiuto contestuale nelle impostazioni | segnalazione utente | piccolo |

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
