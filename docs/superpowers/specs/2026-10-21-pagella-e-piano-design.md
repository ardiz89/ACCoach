# Pagella e piano: la prima pagina del report — design

Data: 2026-10-21. Primo di quattro pezzi decisi col pilota (vedi «Il quadro»).

## Il perché

Il pilota, a fine sessione, apre il report e non capisce com'è andato
l'allenamento, dove ha sbagliato e cosa fare adesso. Parole sue: «manca una
bussola da seguire, non c'è una roadmap e manca qualcosa che tenga traccia dei
miei miglioramenti (oltre al tempo finale sul giro)».

Il segno di progresso che vuole vedere: **i suoi difetti principali che calano da
una sessione all'altra.** Un difetto, per lui, è un'abitudine di guida che si
ripete in più curve («stacco troppo presto»), che poi può approfondire curva per
curva.

Il report oggi ha dieci schede e i pezzi giusti sparsi (perdita per curva con la
causa, piano di allenamento con due obiettivi, esercizi, andamento per curva), ma
nessuno fa da bussola, e non esiste un andamento **per difetto** nel tempo.

## Il quadro (i quattro pezzi, in quest'ordine)

1. **Questo documento.** La Pagella (nuova prima pagina), il piano con «Lo seguo»,
   le viste «Come si fa», lo storico dei difetti per sessione, il riordino delle
   schede.
2. Il giro di Coach Live: pannello «In pista» dell'hub con QR per collegare il
   tablet alla pagina Ingegnere, passi che si spuntano da soli, «Ho finito,
   mostrami com'è andata» che ferma il coach e apre la Pagella. Documento a parte.
3. I rimandi dalle schede esistenti ai consigli seguiti. Documento a parte.
4. Riscrittura dei testi di tutta l'interfaccia col tono deciso qui sotto, e
   lettura comoda su schermi grandi. Documento a parte.

I testi nuovi di questo pezzo nascono già col tono nuovo.

## Obiettivi

- Aprendo il report dopo una sessione, in dieci secondi il pilota sa: com'è
  andata, i suoi 2-4 difetti principali, dove sbaglia di più, quali errori fa più
  spesso, e cosa fare alla prossima uscita.
- Ogni difetto ha un numero che si può seguire nel tempo, e la Pagella mostra se
  rispetto alle sessioni precedenti scende, sale o resta uguale.
- Ogni consiglio del piano si può seguire o no, e ha una vista che spiega cosa
  fare, costruita sui dati del pilota.
- Le schede del report sono ordinate secondo il percorso «oggi → perché → nel
  tempo».

## Non obiettivi

- Contenuti della community (video, forum, link esterni). Deciso dal pilota: il
  consiglio si basa solo sui suoi dati e sulla conoscenza del coach, perché
  materiale esterno «potrebbe sporcare la qualità del consiglio».
- Video. Nessun video in questo pezzo: le figure sono grafici e mappe dai giri del
  pilota.
- Il giro di Coach Live, i rimandi dalle altre schede, la riscrittura dei testi
  esistenti (pezzi 2-4).
- Assetto: la Pagella parla di guida. I problemi d'assetto restano all'Ingegnere.

## Anti-obiettivi (fallimento anche se funziona)

- Un numero inventato o tarato da noi spacciato per misura. Ogni cifra della
  Pagella deve venire dai giri; dove un dato non c'è (giri senza canale, una sola
  sessione), la riga lo dice o non compare.
- Un consiglio generico non ancorato ai dati («frena più tardi» senza dire dove e
  di quanto).
- Testo «da macchina»: la stessa frase ripetuta in più schede, slogan, due punti a
  effetto, emoji (esempio vero del difetto: le schede della scheda Allenamento con
  «Poi questa, che si ripete in 10 giri su 14. Una cosa alla volta: due esercizi
  nella stessa sessione si annullano a vicenda.» identica in ogni scheda).
- Una prima pagina lunga: più di quattro difetti o più di tre consigli.
- Un andamento che sale o scende perché è cambiato il metro, non il pilota (vedi
  «Il metro dello storico»).

## Il tono dei testi (deciso col pilota)

Frasi brevi e dirette, col tu. Numeri con la virgola e l'unità («0,18 s»). Niente
slogan, niente due punti a effetto, niente emoji. Mai la stessa frase in due
posti: una regola valida per tutta la lista si dice una volta, sopra la lista.
Prima il fatto, poi cosa fare. Riferimento approvato dal pilota:

> **Villeneuve** · dopo la Variante Alta
> Qui perdi 0,18 s a giro, e succede quasi sempre (10 giri su 14). Obiettivo:
> scendere sotto 0,12.
> Esercizio, 6 giri: prendi la velocità minima che ti viene naturale e prova a
> portarne un po' di più ogni giro.

Ogni testo esiste in italiano e in inglese (convenzione del progetto).

## La Pagella (nuova prima pagina del report)

Scelta dal pilota fra due bozze (la «A»). Dall'alto in basso:

1. **Intestazione.** Pista, auto, data, giri (validi su totali).
2. **Verdetto, una o due frasi.** Quanto ha perso in media a giro sul suo
   riferimento e dove si concentra (fase o difetto dominante); confronto con la
   sessione precedente sulla stessa auto/pista (tempo e quali difetti sono
   migliorati o peggiorati). Se non c'è una sessione precedente, lo dice.
3. **I tuoi difetti principali (2-4).** Per ognuno: nome (un'abitudine, non una
   curva), costo in secondi a giro, in quante curve e in quanti giri compare, un
   mini-andamento sulle ultime sessioni (fino a 6) con freccia giù/uguale/su. Un
   clic apre il difetto curva per curva.
4. **Dove sbagli di più.** Le 3 curve che costano di più, col nome curva.
5. **Errori più frequenti.** Conteggi della sessione: bloccaggi, pattinamenti,
   sottosterzo, sovrasterzo, uscite di pista. Solo quelli che sono comparsi.
6. **Il piano per la prossima uscita.** Al massimo 3 consigli in ordine, ognuno
   con «Lo seguo» / «Non lo seguo» e «Come si fa →». La regola «una cosa alla
   volta» si dice una volta sopra la lista.

Leggibilità: colonna centrale di larghezza limitata con caratteri più grandi del
resto del report; su un 32" il pilota oggi «si perde a leggere». Verdetto,
difetti e piano devono stare sullo schermo senza scorrere a 1920×1080.

Bozza approvata (struttura, non grafica definitiva): la «A» del brainstorming,
riprodotta qui sotto a parole sopra; i dati della bozza erano finti.

### I difetti: da dove vengono

Un difetto è un raggruppamento delle perdite per curva che il debrief calcola già
(`coaching/debrief.py`, `CornerLoss.category` da `analyzer.classify_corner`), più
due misure di giro:

| Difetto (nome pilota) | Sorgente | Misura |
|---|---|---|
| Freni troppo presto | `BRAKE_LATER` | ms persi, sommati sulle curve |
| Freni troppo tardi (e non paga) | `BRAKE_EARLIER` | ms persi |
| Troppo freno | `LESS_BRAKE` | ms persi |
| Poco gas / gas tardi in uscita | `MORE_THROTTLE` | ms persi |
| Poca velocità in curva | `CARRY_SPEED` | ms persi |
| Veleggi prima di frenare | `GripState.coast_s` | secondi di veleggio a giro |
| Alzi il gas sul dritto | `LapNote` kind `lift` | ms persi |

`TIME_LOSS` (perdita senza causa) non è un difetto e non va in lista. «Compare in
N curve e N giri» si conta sui giri validi della sessione. «Principale» = i
difetti sistematici (stesso criterio di `trends.classify_losses`: ricorrenti, non
sporadici) ordinati per costo a giro, sopra la soglia di significatività già in
uso (`SIGNIF_LOSS_MS`). Il veleggio, che non è in ms, entra in lista se supera una
soglia in secondi; la soglia va motivata coi giri veri dell'archivio, non scelta a
occhio.

### Gli errori frequenti: da dove vengono

- Bloccaggi e pattinamenti: `diagnosis._lock_spin_segments` (già usato per
  l'Ingegnere), contati sui giri della sessione.
- Sottosterzo/sovrasterzo: `diagnosis.corner_symptoms`, una occorrenza per curva
  per giro dove il sintomo c'è.
- Uscite di pista: giri con `clean is False` / `lost_at`.

Oggi il report non li conta: vanno costruiti. Su ACC con l'ABS acceso il
bloccaggio fisico non avviene (memoria del 02/08): il conteggio non deve
inventarlo.

### Il metro dello storico

Il costo di un difetto è relativo a un riferimento. Se ogni sessione si misurasse
col riferimento in vigore quel giorno, migliorando il riferimento si sposta e
l'andamento mentirebbe (difetto già incontrato col focus, memoria del 23/08).
Scelta mia: **tutte le sessioni dell'andamento si misurano contro lo stesso
riferimento**, quello che il report usa oggi per auto/pista/condizioni; quando il
riferimento cambia, lo storico si ricalcola. Come conservarlo (cache per
riferimento in `catalog.db`, o ricalcolo al volo) è lasciato al costruttore,
purché la Pagella si apra in tempi da pagina web su un archivio come quello del
pilota (~160 giri). Le sessioni restano quelle ricostruite da `sessions.py`
(stacco di 20 minuti).

## Il piano e «Lo seguo»

Il piano esiste (`coaching/plan.py`, tabella `plan` in `catalog.db`, proposto →
accettato → misurato sui giri dopo). Diventa il piano della Pagella:

- I consigli sono **per difetto**, con le curve dove pesa di più in ordine (si
  comincia dalla prima). Al massimo 3, in ordine: è una roadmap.
- **Si segue un consiglio alla volta** (deciso dal pilota). Con un consiglio in
  corso, gli altri mostrano solo la loro posizione nella roadmap e «Come si fa →»;
  «Lo seguo» compare sul successivo quando quello in corso è raggiunto o lasciato.
- «Lo seguo» = accettato, con data. «Lascio stare» chiude quello in corso senza
  dichiararlo raggiunto. «Non lo seguo» su un consiglio non ancora iniziato lo
  toglie dalla roadmap ma il difetto resta in Pagella. Ogni scelta si ricorda
  (anche il «non lo seguo»: altrimenti ricompare ogni volta).
- Il modello dati del piano cambia di conseguenza: una riga per consiglio, con
  difetto, curve, stato (proposto / in corso / raggiunto / lasciato / rifiutato) e
  date. Il piano attuale (due obiettivi per curva accettati in blocco) si migra o
  si sostituisce; decide il costruttore, senza perdere un piano già accettato.
- Un consiglio seguito arriva al coach in pista: alla prossima uscita il coach dal
  vivo (focus, `coaching/focus.py`) lavora su quel consiglio e parla in quelle
  curve, così piano e coach dicono la stessa cosa. Proposto da me, confermato dal
  pilota.
- Quando un consiglio è raggiunto (criterio esistente di `measure()`), la Pagella
  lo dice e propone il successivo.

## La vista «Come si fa» (una per consiglio)

Confermata dal pilota così:

1. Il problema in una frase coi suoi numeri («Alla Variante Alta stacchi in media
   14 metri prima del tuo giro migliore, e ci perdi 0,29 s a giro»).
2. In figura, dai suoi giri: la mappa della curva con i punti (il suo solito e il
   suo migliore) e il grafico del pedale/velocità pertinente sovrapposto; una
   figura per curva, dalla più costosa.
3. Come si fa: poche righe dalla conoscenza del coach (gli esercizi di
   `coaching/training.py`, riscritti nel tono nuovo). Cosa fare, cosa guardare in
   pista, cosa ignorare.
4. L'esercizio: quanti giri, obiettivo in numeri, quando è fatto.
5. Come sta andando: da quando l'ha seguito, il numero di quel difetto per
   sessione.

Ogni difetto della tabella sopra deve avere il suo testo «come si fa». Dove oggi
non c'è un esercizio (veleggio, alzate sul dritto, frenata tardiva), va scritto,
partendo dalla ricerca `COACHING-PRO.md`.

## Le schede del report, in quest'ordine (deciso col pilota)

**Com'è andata oggi:** Pagella (si apre per prima) · Giri della sessione · Giro
spiegato.
**Perché, nel dettaglio:** Confronto · Traiettoria · Settori · Dinamica.
**Nel tempo:** Andamento (con i difetti sessione per sessione) · Passo gara.

I tre gruppi si vedono nella barra. La scheda «Com'è andata» attuale confluisce
nella Pagella; la scheda Allenamento si divide fra il piano della Pagella e le
viste «Come si fa» (glossario compreso). Il report oggi riapre l'ultima scheda
vista (`localStorage["hone_view"]`): dopo una sessione nuova deve aprirsi sulla
Pagella.

## Vincoli

- Tutto offline, come il resto dell'app.
- Mai scrivere in `Documents\ACCoach` durante prove e test; si lavora su copie.
- Le prove sui giri veri (archivio del pilota, in sola lettura) valgono più della
  suite: la memoria del progetto mostra che i difetti peggiori del report li hanno
  trovati il browser e i giri veri.
- Ogni test nuovo deve fallire se si toglie la cosa che prova (mutazione).

## Scelte mie, dopo la rilettura del revisore

Prese da me, non dal pilota; il pilota le può rovesciare.

1. **Quale riferimento per lo storico.** Il giro più veloce *pulito* (valido e
   senza uscite) di auto/pista con la stessa classe di gomma della sessione
   (asciutto o bagnato). Le sessioni sull'altra classe di gomma non entrano
   nell'andamento, e la Pagella di una sessione così lo dice. Temperatura e grip
   non separano le sessioni: separarle lascerebbe l'andamento quasi sempre vuoto.
   Le curve si rilevano dal riferimento, quindi con un solo riferimento la
   numerazione è la stessa per tutte le sessioni. Il Confronto continua a eleggere
   il suo riferimento per condizioni: i due numeri possono differire, e la vista
   «Come si fa» dice contro quale giro misura.
2. **Il numero di un difetto.** Per ogni giro valido, la somma delle perdite delle
   curve classificate in quella categoria; il numero della sessione è la media sui
   giri validi. Non dipende da quali curve sono «sistematiche», quindi non salta
   quando una curva passa la soglia. «Principale» = difetto la cui somma per giro
   supera `SIGNIF_LOSS_MS` in almeno metà dei giri validi; si ordinano per media.
3. **Quando un consiglio è raggiunto.** Il difetto, sommato sulle curve del
   consiglio, scende sotto l'obiettivo (metà del valore di partenza, mai sotto
   `SIGNIF_LOSS_MS`) in almeno metà dei giri, con almeno 3 giri dopo l'accettazione:
   la stessa regola di `measure()`, sul totale invece che su una curva. Partenza e
   obiettivo si misurano col riferimento dello storico, e se il riferimento cambia
   si ricalcolano con quello nuovo, così partenza e misura usano sempre lo stesso
   metro.
4. **Il consiglio e il coach in pista.** Il consiglio in corso sostituisce la scelta
   del focus (`FocusCoach`): il focus lavora sulle curve del consiglio una alla
   volta, nell'ordine, col suo ciclo (migliorato / bloccato / parcheggiato). Un
   verdetto del focus non chiude il consiglio: lo chiude solo la misura del punto
   3, nel report. La voce in pista resta qualitativa dove i numeri possono
   differire da quelli della pagina (riferimenti diversi). Senza un consiglio in
   corso il focus sceglie da solo, come oggi.
5. **Il veleggio in classifica.** È in secondi e in parte si sovrappone al tempo
   già attribuito alla frenata, quindi non si ordina insieme agli altri: compare
   dopo i difetti in ms, conta nel limite dei 4, e il testo non lo somma alla
   perdita del verdetto.
6. **Quale sessione.** La Pagella segue il selettore di sessione già esistente
   (`SESSION_I`), con la più recente come predefinita. «Sessione precedente» è
   quella prima sulla stessa auto/pista. Il piano si costruisce sulla storia fino
   alla sessione mostrata compresa.

## Lasciato al costruttore

Struttura degli endpoint e dei moduli, come conservare lo storico dei difetti, la
grafica definitiva entro la struttura sopra, il numero di sessioni del
mini-andamento (fino a 6), la soglia del veleggio (purché misurata).
