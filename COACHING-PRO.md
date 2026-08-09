# Cosa sanno i coach professionisti, e cosa sa il nostro ingegnere

Ricerca del 2026-08-08. Nove analisti in parallelo: tre sul nostro codice, sei sui video e sugli
scritti dei migliori coach di simracing. L'obiettivo non era raccogliere consigli di guida — quelli
li abbiamo già — ma capire **dove il nostro ingegnere di pista sa meno di un coach vero**.

La risposta breve: non nel catalogo. Nel metodo.

---

## 0. Quanto vale questo documento

Regola imposta a tutti i ricercatori: ogni frase attribuita a qualcuno dev'essere una **citazione
testuale ritrovata con una ricerca dentro il file salvato su disco**, con timestamp e URL. Chi non
riusciva a verificarla doveva cancellarla. Quattro fronti su sei hanno scritto un verificatore che
rifà il controllo a macchina e fallisce se una citazione salta.

| Fronte | Base documentale | Citazioni verificate |
|---|---|---|
| Frenata e ingresso | 12 trascrizioni video | 145 |
| Metodo del coach | 8 trascrizioni + fonti scritte | 192 |
| Rotazione e apex | trascrizioni preesistenti + articoli Driver61 | 148 |
| Setup e ingegneria | 13 post firmati di Aris sul forum Kunos + descrizioni video | 232 |
| Telemetria | 15 fonti scritte | 110 |
| Gara e pioggia | descrizioni, capitoli e commenti di 49 video + 4 articoli | verificate a macchina |

**Il limite, dichiarato in apertura perché cambia come si legge il resto.** A metà lavoro Google ha
bloccato l'IP di questa macchina sull'endpoint dei sottotitoli (`/api/timedtext`, 429). Ha retto
contro sette strade diverse — `youtube-transcript-api`, `yt-dlp` con sei client, InnerTube,
host alternativi, proxy di terze parti, e persino Chrome nella sessione autenticata. Tre fronti su
sei non hanno ottenuto **una sola trascrizione parlata** e hanno ripiegato su fonti scritte,
descrizioni e commenti, dichiarandolo invece di riempire il buco.

Conseguenza pratica: mancano i drill di GITGUD Racing (l'unico canale strutturato esplicitamente a
esercizi), le sessioni di coaching di Perel e le due parti di Almeida sulla costanza. La lista dei
video e gli script per riprenderli sono nel corpus.

**Dov'è il materiale grezzo.** Fuori da questo repository, che è pubblico:
`Documenti/ACCoach-ricerca/2026-08-08-coaching-pro/`. Contiene i nove report per esteso, 21
trascrizioni, i commenti di 49 video, 69 fonti scritte e gli script di verifica. Qui dentro restano
solo citazioni brevi e attribuite, con i link.

---

## 1. La conclusione: il catalogo ce l'abbiamo, il metodo no

L'audit interno ha contato **50 capacità diagnostiche** verificate riga per riga nel coach live e a
debrief, più una tassonomia di assetto completa — 12 celle sintomo × fase × velocità per GT3 e
Formula, 6 per le stradali, con i rimedi ordinati in click. Il loop che propone una modifica, la
misura sui giri successivi e la annulla se non funziona **gira davvero, dalla diagnosi al disco**.

Nessuno dei coach studiati ha un catalogo più ricco del nostro.

Quello che hanno e noi no sono quattro cose, tutte di metodo:

1. **Un budget di attenzione.** Sanno quante cose può ricevere un pilota, e il numero è basso.
2. **Un ordine.** Sanno cosa correggere per primo, e non è quello che costa più tempo.
3. **Il silenzio.** Sanno quando non parlare, e il momento in cui tacciono è preciso.
4. **Sapere a chi stanno parlando.** Il nostro advisor non sa nemmeno che auto guidi.

---

## 2. Le tre regole di dosaggio, tutte solide e tutte assenti da noi

### 2.1 Massimo tre temi per sessione

Ross Bentley lavora su **3 item, 5-6 giri ciascuno, con rientro ai box fra uno e l'altro**. Il suo
cliente lo distilla in regola dopo quattro sessioni nello stesso giorno: *«Maximum of three items in
any test session»*, *«5-6 laps on each item»*. Suellio Almeida lavora su due, e in una sessione
documentata su **uno solo**: quarantacinque minuti dedicati esclusivamente allo sguardo, 4.5 secondi
trovati, *«we didn't talk about his breaking his Trail breaking his steering his downshifting
anything related to the car handling»*.

Due coach indipendenti, numeri espliciti, e una procedura invece di uno slogan. **Verdetto: solida.**

**Cosa abbiamo noi.** Un limite di *frequenza*, non di *argomenti*: `CueScheduler` impone 4 secondi
fra un consiglio e l'altro, sopprime per 20 secondi lo stesso consiglio nello stesso punto e scarta
i consigli scaduti. Ottimo lavoro, ma nessuno impedisce dodici temi diversi nella stessa sessione.
Il pilota non riceve troppi messaggi al minuto: riceve troppe cose *diverse* da tenere a mente.

Il `focus` coach lavora già su una debolezza per volta e il piano di allenamento su due obiettivi:
il concetto esiste nel prodotto, ma non governa la voce in pista.

### 2.2 In pista solo parole-innesco

Tre fonti indipendenti usano lo stesso strumento e **lo stesso nome** — *trigger words* — con lo
stesso motivo dichiarato: la capacità mentale del pilota in movimento è finita. Almeida lo annuncia
prima di usarlo: *«what you're about to see is a coaching technique where I'm going to use only a
few trigger words so he can hyperfocus on one thing»*. Poi in pista si sente solo questo: «over
slow over slow less breaks», «light light light light», «power power power». Una parola, ripetuta
come un metronomo. Bentley assegna le frasi **prima** della sessione e le fa scrivere sugli appunti.

L'unica frase intera osservata in una sessione arriva **dopo** la curva, non dentro.

**Regola operativa**: se il consiglio non entra in tre parole, non va detto in pista — va nel
debrief. E dev'essere **la stessa parola ogni volta** per quell'obiettivo.

Questo si sposa con una cosa che il progetto ha già imparato in pista: il protocollo a voce nato da
un incidente vero, in movimento si parla, da fermi si risponde. Le parole-innesco sono la versione
fine dello stesso principio.

### 2.3 Il secondo tema si dà quando il primo è automatico

Non a tempo, non a fine sessione: quando il pilota ha *spazio in testa*. Il criterio di riuscita di
un esercizio più utile trovato in tutta la ricerca non è «lo esegue», ma **«finché sbagliarlo sembra
sbagliato»** — che è traducibile in dato: la metrica regge quando il pilota non ci sta più pensando.

---

## 3. La gerarchia: il nostro ordine non è il loro

I coach ordinano gli interventi così, incrociando le fonti:

1. **La vista e il piano di curva.** Mansell: *«there's not been one driver come through our
   programs that we've not at least tweaked their vision»*. Almeida ci dedica una sessione intera.
   Due fonti autorevoli indipendenti, stesso posto in classifica.
2. **Usare tutta la larghezza della pista** — *«a very simple win»*.
3. **L'ingresso prima dell'uscita**: *«entry determines everything if you don't have a good entry
   you will never have a good exit»*.
4. **Chiedere la rotazione ai pedali e ridurre lo sterzo in ingresso.** Aris lo mostra misurato:
   stesso punto di frenata, meno sterzo, **84 → 95 km/h all'apex**.
5. **Il rilascio del freno proporzionale a quanto l'auto sta girando.**
6. **Spostare il punto di velocità minima prima dell'apex e aprire il gas prima.**
7. **Ripulire il gas in uscita**: un riferimento fisso, nessuna correzione.
8. **Solo dopo, il setup.** *«you find the limit first and then you change the setup»*.

E il punto di frenata? **Cinque coach su sei lo mettono ultimo.** Almeida ha un nome per l'errore di
metterlo per primo — *«this guessing game of breaking later is what's making you take so many hours
to become competitive»*.

**Cosa facciamo noi.** Ordiniamo per millisecondi persi (`debrief.py:787`). È un ordine difendibile
e non è quello di nessun coach. Peggio: quando parliamo di frenata apriamo spesso con «freni N metri
prima», cioè diamo per primo il consiglio che i professionisti danno per ultimo.

### La regola diagnostica che possiamo implementare domani

Bentley sovrappone le tracce di velocità di **3-5 giri** e cerca la curva con la **varianza
maggiore**: *«that's where the driver is the least consistent […] and that may be the biggest
opportunity for improvement»*. L'analista che lo intervista corrobora nel merito: *«it should be one
thin line. If it's not, then what's going on?»*

È l'unica regola trovata in tutta la ricerca che sia **numerica, falsificabile e già alla nostra
portata**: i dati ci sono, manca l'indice. Oggi mostriamo la curva dove hai perso di più. Loro
attaccano la curva dove sei meno ripetibile — perché quella la puoi *guadagnare*, mentre la prima
magari l'hai già guidata al tuo limite.

Corollario dallo stesso ambiente: *«If you can be three tenths quicker every lap, that's better»*
di mezzo secondo una volta ogni dieci.

---

## 4. Dieci misure nuove, tutte dai canali che già leggiamo

Nessuna richiede un canale che non abbiamo. Sono ordinate per rapporto valore/costo.

| # | Misura | Come si calcola | Cosa rivela |
|---|---|---|---|
| 1 | **Saturazione del pedale** | durata continua di `brake ≥ 0.995` | il pilota crede di rilasciare, la cella di carico è già a fondo. In una sessione reale è costata un'ora di coaching |
| 2 | **Varianza per curva** | dispersione della traccia di velocità su 3-5 giri | la prima opportunità secondo Bentley (§3) |
| 3 | **Istogramma del freno** | distribuzione di `brake` nella zona di frenata | bimodale = pedale usato come interruttore |
| 4 | **Δ_MRP** | `s(apex geometrico) − s(velocità minima)`, in metri | apex precoce o tardivo **misurato**, non giudicato |
| 5 | **Freno al turn-in** | `brake` quando `|steerAngle|` supera la soglia | girare col freno a fondo: l'ABS lo nasconde al pilota, non a noi |
| 6 | **Durata del rilascio** | dall'80% al 5% del picco, in metri e millisecondi | il gesto che i coach mettono al primo posto |
| 7 | **Filo sterzo-gas** | campioni con `gas > 0.5` mentre `|sterzo| > 0.8 × picco` | gas aperto mentre l'auto sterza ancora |
| 8 | **Tempo nel trail** | tempo con `1% ≤ brake ≤ 20%` fra turn-in e apex | se il trail braking c'è davvero |
| 9 | **Peso della curva** | `(velocità recuperabile in uscita) × (durata del tratto seguente)` | quali curve valgono di più, in decimi |
| 10 | **ABS cumulato** | durata totale di intervento ABS nella staccata | su ACC il bloccaggio non avviene: la soglia si sfiora, non si supera |

Due avvertenze che vengono dalla nostra esperienza, non dalle fonti:

- **`steerAngle` su ACC è la posizione del volante, non l'angolo ruota.** Un indice di rotazione
  costruito senza lo `steerLock` per vettura sarebbe tarato da noi, non misurato — la stessa
  trappola dei venti circuiti.
- **Le fonti parlano quasi tutte di iRacing.** Le soglie vanno rimisurate su AC/ACC prima di essere
  promosse, esattamente come le tarature ACC.

---

## 5. Sette cose che dobbiamo smettere di dire

1. **«Alza l'ABS» a un'auto che non ha l'ABS.** `advisor.py:142-144` non conosce la classe;
   `ENGINEER.md:157-158` prescrive il contrario. È un consiglio impossibile da eseguire, detto a
   voce, mentre guidi.
2. **«Freni troppo presto» con il verso prefissato.** Driver61 ha un video intero su chi frena
   troppo presto; Baldwin dice sapendolo l'opposto — *«the majority of people I see are breaking too
   late, not too early»*. Il verso va derivato dal dato del pilota. E oggi `BRAKE_EARLIER` ha
   titolo, grafico ed esercizio dedicato ma **nessun produttore che la emetta**.
3. **L'apex precoce come errore in assoluto.** **Ross Bentley in persona**, nei commenti al proprio
   video, difende l'apex precoce per le curve senza rettilineo dopo: *«there are corners that don't
   have much of a straight afterwards, so exit speed is not important»*. La condizione è misurabile
   con il peso di curva (#9). Dove la curva pesa poco in uscita, dobbiamo tacere.
4. **Il coasting condannato a prescindere.** Almeida e Morad lo prescrivono deliberatamente in
   ingresso; Mansell lo vuole impercettibile. Va raccontato *dove* è avvenuto e *se ha prodotto
   rotazione*, non contato e basta.
5. **«Se non sei costante non sarai mai veloce».** Contestata: Mansell descrive il pilota costante e
   lento, Krause dice l'opposto — *«Drive every corner, every lap, as quickly as you can»*. Usare la
   versione di Bentley, che è una procedura invece di uno slogan.
6. **Il giro di riferimento come «il tuo giro più veloce».** Bentley: *«you may find a lap where you
   did the right thing. You just only did it that one time»*, e il valore è proprio quello — *«I
   actually did it once. So that means I can go and do it again»*. Il riferimento giusto per un
   gesto è il **miglior esempio di quel gesto**, anche dentro un giro lento. Per noi è un cambio di
   indice, non di algoritmo.
7. **Rimproverare un delta fatto nel traffico.** Non sappiamo vedere le altre auto, ma sappiamo
   riconoscere un giro anomalo: lì il valore sta nel non parlare.

E un rischio che un coach nomina esplicitamente, ed è il nostro prodotto: *«Coaches that tell you
exactly what to do without explaining properly why they do that will only make your life worse
because they will make you dependable on them.»* Un overlay che dice «qui freni 8 metri prima»
produce dipendenza e non trasferisce. Il progetto lo sa già — «il perché, non il cosa» è in
`README:27` — ma vale la pena rileggerlo detto da chi vive di coaching.

---

## 6. Le soglie: quali si possono pinnare e quali no

| Grandezza | Valore trovato | Fonte | Cosa ne facciamo |
|---|---|---|---|
| Finestra pressione GT3 ACC | 27.3–27.9 psi | Aris, Kunos, **nov 2020, v1.6** | La nostra è 27.5 ± 0.7. È centrata bene **su quella versione**. Va marcata con data e versione |
| idem, community post-1.9 | 26.0–27.0 psi | Coach Dave (in disaccordo con sé stesso nella stessa pagina: 26–27.2, 26.5–27.5) | **Non pinnare.** Ma con quella finestra la Ferrari 488 a 26.5 psi sarebbe già dentro, e noi le diciamo «alza 1.0 psi» |
| Δ temperatura fra le tre zone | 15 °C / 9 °C / 9-5 °C | tutte e tre Coach Dave, in disaccordo | **Folklore.** Kunos ha scritto la simulazione a tre zone e non ha mai pubblicato un numero. Se ci serve, va misurato da noi |
| σ dei tempi, GT3 professionisti in gara | 0.129–0.276 s | British GT, Donington | **Il numero che ci mancava.** Con σ≈0.15 e tre giri l'intervallo di confidenza è ±0.17 s |
| Slip ratio ottimale in frenata | 3–10% | Driver61, con definizione operativa | Solida, ma senza ABS |
| Pressione residua nel trail | 2–10% | Morad, Aris | Solida come ordine di grandezza; la versione 10–20% è contestata |
| Gas di equilibrio a metà curva | 10–20% | Mansell | Plausibile |
| Mappa motore | *nessuna regola universale* | tabelle Kunos per vettura | Sulla Huracán EVO2 i livelli 1-5 sono **freno motore**; sulla 296 nulla cambia. «Più bassa = più potente» salta su quattro famiglie |

**La regola che vale più di tutte le cifre**: una soglia di pressione va legata alla **versione del
gioco** e marcata con la **fonte**. Oggi il nostro 27.5 non ha né data né versione accanto, e la
patch che lo invalida non ci avviserà.

### Il differenziatore che nessuno occupa

Nessuno dei tool commerciali esaminati — VRS, Coach Dave, Track Titan, trophi.ai — **dichiara un
margine di rumore**. Con la σ dei professionisti sopra, sotto i due decimi non si può affermare
nulla su tre giri. Noi riportiamo perdite per curva molto più piccole di così, e il veto sul tempo
dell'ingegnere è tarato allo 0.15% del giro, cioè proprio al confine.

È la stessa famiglia di onestà che il progetto già pratica altrove (`hit_rate` che resta `None`
finché non c'è niente, il rifiuto sul bagnato, «misurato vs tarato»). Qui però sarebbe anche una
cosa che **nessun concorrente fa**.

---

## 7. Cosa la ricerca ha fatto emergere del nostro codice

Trovati incrociando i tre audit interni con la ricerca esterna. Ognuno è verificato nel codice.

- **Il veto sul tempo dell'ingegnere è di fatto spento.** Sospende il confronto se le due finestre
  differiscono di più di 2 litri, ma si consumano 3.1–3.3 litri al giro: bastano 0.6 giri di
  disallineamento. Decide quasi solo il punteggio del sintomo.
- **Nessun tetto ai click.** `setup/params.py` non è mai stato scritto: si può proporre `+1` su un
  parametro già al massimo, la scrittura riesce, il gioco tronca al caricamento, e il verdetto
  successivo misura una modifica avvenuta a metà.
- **Il parser dei setup non ha mai visto un file prodotto dal gioco.** Zero file ACC reali nei test.
- **Il sottosterzo si spegne per tutta la sessione** appena rileva il canale sterzo tosato — e
  questa **non è una svista**: il commento in `balance.py:139-143` la difende, perché la tosatura è
  una proprietà della periferica e dimenticarla a ogni giro vorrebbe dire riscoprirla riparlando
  ogni volta. Se ne va solo al cambio auto o pista. La domanda aperta non è se sia un difetto, ma se
  sia la scelta giusta: un pilota che sistema le impostazioni del volante a metà sessione resta
  senza diagnosi di sottosterzo fino a fine sessione, e nessuno glielo dice.
- **Sotto e sovrasterzo non sono fra le categorie di sicurezza**, quindi tacciono su out-lap, ai box
  e oltre i 3 secondi di delta — cioè quando l'auto si comporta peggio.
- **Il coach non guarda mai la traiettoria.** `trajectory.py` esiste e non è collegato: non sappiamo
  dire «sei entrato stretto» o «hai mancato l'apex». È metà del vocabolario di un coach vero.
- **Temperature freni vive su ACC** (125-317 °C misurati) e mai lette dal coaching, come
  `slipAngle`, la G verticale e l'usura gomma.
- **La guida e le FAQ promettono il briefing da fermo ai box**, che su ACC non nasce mai perché
  `isInPit` resta 0 nella piazzola. Lo sappiamo dal 7 agosto; i due documenti non sono stati
  corretti.
- **`STRATEGIE.md` è orfano**: il suo pilastro C non è mai stato costruito e non compare in roadmap.

E due cose che invece **erano già giuste**, e vale la pena saperlo perché la ricerca le indica come
le trappole più comuni:

- Il riquadro «decimi persi per curva» misura da questa curva **all'ingresso della successiva**,
  quindi il rettilineo è accreditato alla curva che ha impostato l'uscita (`debrief.py:704-713`).
  Senza quella scelta, dice la ricerca, il verdetto si **inverte**.
- La perdita è calcolata come differenza del delta fra due cursori, mai come valore del delta in un
  punto. È la procedura corretta, e il commento nel codice spiega già perché.

---

## 8. Cosa non possiamo fare, e perché

**Il racecraft è relazionale e noi siamo ciechi sugli altri.** Leggiamo `carCoordinates` solo al
nostro indice; `position`, `flag` e `carID` sono dichiarati e mai letti. Sorpassi, difesa e traffico
restano fuori portata finché non cabliamo quei canali. Le tre cose fattibili oggi sono: riconoscere
un giro fatto in traffico e **tacere**; scegliere **la curva dove pagare** per gestire le gomme
invece di spalmare un decimo su tutto il giro; e distinguere la stanchezza dal degrado, perché il
degrado sposta la media degli input e la stanchezza ne **allarga la dispersione**.

**Sul bagnato non abbiamo un solo giro in archivio.** Il canale che sembrerebbe servire non serve:
`catalog.py:408-410` documenta che **ACC lascia `grip` a 0 per scelta di progetto** (riporta le
condizioni via `trackGripStatus`, che il reader non dichiara), e `ENGINEER.md §7.5` riporta la
misura fatta sull'archivio — 0.0 su tutti e 39 i giri, su AC *e* su ACC. `rainIntensity` non è
nemmeno dichiarato. Tutto il materiale raccolto sulla pioggia è marcato da
verificare in pista. Una cosa però è falsificabile e vale la pena misurarla appena piove: Bentley
sostiene che sul bagnato si perde **più aderenza laterale che longitudinale**, quindi la velocità
minima in curva deve *scendere* e il circuito si guida «come una serie di rettilinei
d'accelerazione». È controintuitivo, quindi è un buon test.

La zona intermedia — troppo freddo per le slick, troppo asciutto per le rain — è il buco più grande
anche nella letteratura: due praticanti la chiedono in commenti diversi e nessuno risponde. È
esattamente il momento in cui servirebbe un ingegnere di pista.

---

## 9. Nota competitiva trovata per strada

La pagina di coaching simracing di Driver61 oggi **non vende più il coaching di Scott Mansell: vende
trophi.ai**, marchiato *«MANSELL AI»*. Il concorrente che le nostre note indicano come il più vicino
si è preso la credibilità del coach umano di riferimento e la rivende come nome di prodotto.

Vale la pena registrarlo insieme all'altra cosa che questa ricerca dice: **il metodo è il
posizionamento**. Non i dati — quelli li hanno tutti — ma sapere in che ordine parlare, quanto dire
e quando tacere. È l'unica parte che nessun concorrente esaminato ha messo in un prodotto, ed è
anche l'unica parte in cui noi oggi siamo indietro rispetto a un coach umano.

---

## 10. Priorità proposte

In ordine di rapporto fra ciò che cambia per il pilota e ciò che costa.

1. **Il budget di attenzione.** Un tetto di temi distinti per sessione (due o tre), e la voce in
   pista ridotta a parole-innesco. Tocca `scheduler.py` e i testi, non la diagnosi.
2. **Riparare i due consigli falsi**: l'ABS sulle auto senza ABS (nessuna guardia
   `aids_adjustable` esiste nel codice, in nessun file), e sotto/sovrasterzo muti proprio quando
   l'auto si comporta peggio.
3. **La varianza per curva come primo indice** accanto ai decimi persi. Il dato c'è già.
4. **Il margine di rumore dichiarato**: sotto i due decimi, dirlo invece di affermare.
5. **La saturazione del pedale e la durata del rilascio.** Due misure nuove, canali già letti, e
   colpiscono il gesto che i coach mettono al primo posto.
6. **Datare le soglie**: versione del gioco e fonte accanto a ogni numero di pressione.
7. **`setup/params.py`**, cioè il tetto ai click. È lavoro di contenuti per vettura, non di codice,
   e va aperto come tale.
8. **La traiettoria nel coaching**: collegare `trajectory.py`, che è metà del vocabolario mancante.
9. **La curva dove pagare** per la gestione gomme, sui dati che abbiamo già.
10. **Il bagnato**: una sessione vera in pista, prima di qualsiasi riga di codice.

Le prime quattro non richiedono un canale di telemetria nuovo né un giro nuovo: sono tutte
riorganizzazioni di cose che il sistema già sa.
