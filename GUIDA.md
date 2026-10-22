# Guida a HONE

HONE è un coach di guida in tempo reale per **Assetto Corsa** e **Assetto Corsa
Competizione**. Mentre giri ti parla in italiano e ti mostra un overlay col
distacco dal tuo giro migliore. A fine sessione trovi il debrief e l'analisi
completa nel browser. Nel gioco non devi configurare niente, perché HONE legge
la telemetria dalla memoria condivisa di AC e ACC.

Questa guida ti accompagna dall'avvio al primo giro col coach, fino all'analisi.

---

## 1. Cosa ti serve

- **Assetto Corsa** o **Assetto Corsa Competizione** installato.
- **HONE**, in uno dei due modi.
  - **L'eseguibile**, se vuoi solo usarlo. Fai doppio clic su `HONE.bat`, e
    Python non ti serve.
  - **Il sorgente**, se sviluppi. Ti serve Python 3.11 o più recente, poi
    `pip install -r requirements.txt`.

I tuoi giri finiscono in **`Documenti/ACCoach/laps`**, sia dall'eseguibile sia
dal sorgente. Così l'analisi li ritrova sempre.

---

## 2. Avvio in 30 secondi

1. **Avvia il gioco** ed entra in pista in una sessione di **Prove libere**,
   con l'auto e la pista che vuoi allenare.
2. **Metti il gioco in modalità Borderless**, cioè in finestra senza bordi, e
   non a schermo intero esclusivo. Sopra lo schermo intero esclusivo l'overlay
   non si vede.
3. **Apri HONE.** Si apre l'**hub**. Nella barra laterale ha sei sezioni,
   **Home · In pista · Analisi · Setup · Dispositivi · Impostazioni**. Vai su
   **In pista** e premi **Coach Live**.

> Dopo la prima volta, la Home ti mostra l'ultima sessione già analizzata.
> È lì che arrivi per sapere com'è andata.

**Il pannello In pista ti accompagna.** Dopo che hai premuto Coach Live, la
pagina passa per tre momenti, uno dopo l'altro.

**Prima di partire.** Il primo passo, *Coach Live acceso*, si spunta appena il
coach risponde, di solito in un paio di secondi. A quel punto voce e overlay
sono pronti. Poi viene *Collega il tablet all'ingegnere*. Inquadra il codice
QR con la fotocamera del tablet, oppure apri l'indirizzo scritto accanto. Il
tablet si collega solo con la rete locale attiva. Se è spenta, il pannello ti
offre il bottone *Attiva la rete locale*, e dopo devi riavviare Coach Live. Se
il tablet non ti serve, premi *Salta, guido senza*. L'ultimo passo, *Avvia il
gioco ed esci dai box*, si spunta da solo quando arriva la telemetria.

**Stai guidando.** Il pannello ti dice se il tablet è collegato, su che pista e
con che auto sei, quanti giri hai completato e il tuo migliore. Se segui un
consiglio della Pagella, leggi *Stai seguendo il consiglio* col suo nome, e il
coach te lo ricorda nelle curve di quel consiglio. Quando hai finito premi
**Ho finito, mostrami com'è andata**. Il coach si ferma e il report si apre
sulla Pagella. *Ferma senza aprire il report* ferma il coach e basta.

**Sessione finita.** Se chiudi il gioco, dopo un minuto il pannello passa a
*Sessione finita* e ti offre due scelte. *Mostrami com'è andata* apre il
report, *Resto in pista* serve quando stai solo cambiando pista. Il coach resta
acceso finché non lo fermi tu.

**Se ti dimentichi di premere il bottone.** In **Impostazioni** c'è *Registra
da solo quando parte il gioco*. Con l'hub aperto, HONE si accorge che AC o ACC
è partito e avvia la registrazione da solo. Così non perdi una sessione che
avevi dimenticato di avviare. Parte **solo la registrazione silenziosa**, e
voce e overlay restano spenti finché non premi Coach Live. Un coach che si
mette a parlare solo perché hai aperto il gioco sarebbe un'intrusione.
L'opzione all'inizio è spenta. Se fermi la registrazione a mano resta ferma, e
riparte solo quando chiudi e riapri il gioco.

Dalla riga di comando fai la stessa cosa così.

```
python -m accoach live           # coach vocale + overlay, in un solo processo
```

Aggiungi `--silent` se vuoi l'overlay senza la voce.

---

## 3. Come ti allena il coach

Il coach lavora come un ingegnere di pista vero. Prima **ti guarda girare**,
poi **ti corregge**. I suoi interventi sono di tre tipi.

### Gli avvisi immediati

Questi non hanno bisogno di un giro di riferimento. Dal primo metro del primo
giro il coach ti avvisa quando sbagli in assoluto.

- Se **blocchi** in frenata senti «Blocchi le ruote, alleggerisci il freno».
- Se **pattini** in uscita senti «Pattini in uscita, dosa il gas».
- Se l'auto **sottosterza** senti «L'anteriore scivola, entra più piano».
- Se l'auto **sovrasterza** senti «Sovrasterzo, in uscita apri il gas piano».
- Se **veleggi**, cioè non premi né freno né gas, senti «Veleggi, passa subito
  dal freno al gas».
- Se molli il freno troppo presto, senza **trail braking**, senti «Molli presto
  il freno, tienine un filo all'inserimento».

### I consigli di curva

Per dirti dove perdi tempo e perché, il coach ha bisogno di un **giro di
riferimento**, il tuo più veloce fra quelli validi.

1. **Fai un giro pulito completo**, dal traguardo al traguardo. Quello che
   parte dai box non conta. Si salva e diventa il riferimento.
2. Dal giro dopo arrivano i consigli di curva. Il coach confronta il tuo giro
   col riferimento. **Mentre ti avvicini a ogni curva** ti anticipa il
   consiglio per quella curva. Ti dice, per esempio, «Porta più velocità in curva» o «Arrivi lungo, frena
   prima». Ti parla prima della curva, quando puoi ancora farci qualcosa.
3. Quando prendi bene quella curva, **smette di ripeterti** quel consiglio.
4. Ogni volta che batti il tuo riferimento, da lì in poi il confronto è col
   giro nuovo.

> Quando non sei su un giro buono, come al rientro dai box, dopo un testacoda o
> un'uscita di pista, il coach **tace** sui consigli tecnici. Restano solo gli
> avvisi di sicurezza.

### Un tema alla volta

Dopo qualche giro completo, anche sporco, il coach smette di commentarti tutto
ed **elegge una debolezza**, la curva dove perdi di più e il perché. Te lo
annuncia con una frase come «Il nuovo focus è Variante Ascari. Lavoriamo sulla
frenata». **Da quel momento in pista ti parla solo di quel tema**, su tutta la
pista e non solo in quella curva. Se freni male, non lo fai in un posto solo,
ed è il difetto che si allena.

Vale per i temi che il coach sa riconoscere in ogni punto della pista, cioè la
frenata e la trazione. Con un focus sulla percorrenza o sulla linea la voce non
si restringe, perché quei consigli nascono solo a curva chiusa.

Sulla frenata e sulla trazione te ne parla **con una parola** invece che con una
frase, come «meno freno», «più tardi» o «gas». Le parole te le dice **prima**,
nel messaggio che annuncia il focus, per esempio «In pista sentirai solo parole
di frenata, come “meno freno”». Poi te le ricorda sulla riga del focus
dell'overlay, così le hai davanti mentre guidi.

Tre coach professionisti indipendenti si danno lo stesso
limite, **due o tre temi per sessione**, e in pista **parole brevi**,
concordate prima. Chi guida riesce ad ascoltare poco, e alla decima frase in
tre giri smette di sentire.

**Non perdi niente.** Quello che il coach tace in pista lo trovi nel **debrief**
di fine sessione e nel report, coi suoi decimi. Il debrief si calcola sul giro e
non su quello che ha detto la voce. Così ci trovi anche le curve su cui la voce
è stata zitta. La voce sceglie cosa dirti adesso, il debrief non sceglie niente.

**Il filtro vale solo per la tecnica di guida.** Bloccaggi, pattinamenti, sotto
e sovrasterzo, benzina, chiamate ai box, avvisi d'assetto al traguardo e
complimenti li senti sempre.

Finché un focus non c'è, nei primi giri in cui ti sta ancora guardando, il
coach parla di tutto. Quando la curva migliora, o dopo qualche giro non
migliora, il coach la mette da parte e passa alla successiva. Cambia il tema e
cambiano le parole.

### I consigli di setup

Fra un giro e l'altro, quando un sintomo si ripete, il coach ti suggerisce una
regolazione. Può riguardare le pressioni delle gomme, i livelli di TC e ABS
dove si regolano, o il bilanciamento dei freni. Le pressioni le giudica solo
sulle GT3, a gomme in temperatura, con l'obiettivo di circa 26,5 psi. Sulle
altre auto non ne parla, perché quel numero vale solo per le GT3.

Le modifiche sono di due tipi, e si chiudono in modo diverso.

- **Dal volante.** È una manopola che giri sul rettilineo, come TC, ABS o
  bilanciamento dei freni. Non devi confermare niente, perché HONE **guarda il
  canale** e si accorge da solo che la manopola si è mossa. Così la prova
  comincia senza che tu tolga le mani dal volante. Su AC quei livelli non si
  leggono, e nella pagina Ingegnere trovi il bottone **L'ho cambiato**.
- **Ai box.** È un file di setup da scrivere. Qui il coach ti dice anche
  **quando rientrare**.

### Il registro delle prove

Nella pagina **Ingegnere**, sotto la proposta, c'è il **Registro delle prove**.
Ti dice quante modifiche proposte sono state **tenute** dopo la misura, e
quante bocciate. È l'unico numero di quella pagina che non è una nostra
affermazione. Lo contano le prove che hai guidato tu, e può darci torto.

Ci trovi anche **quali leve si guadagnano il posto**, se regge l'ordine «prima
il rimedio più efficace», e gli **effetti collaterali** che hai visto. Per
esempio una modifica che toglieva il sottosterzo in ingresso e ne portava uno
in uscita. Gli effetti collaterali non li prevediamo mai. Si vedono e si
scrivono.

Finché le prove sono poche, **non trovi percentuali** ma solo i conteggi. Su
tre prove un tasso di riuscita è solo rumore.

### Il rientro ai box

Quando una modifica va fatta in garage, senti tre cose.

1. **All'inizio dell'ultimo settore**, o circa 20 s prima dell'ingresso della
   corsia box se arriva prima, «Modifica pronta, rientra ai box a fine giro».
   Il secondo criterio serve. Su certi circuiti la corsia box si stacca
   **prima** dell'ultimo settore, e una chiamata legata al settore
   arriverebbe con l'ingresso già alle spalle.
2. **Poco prima dell'ingresso**, «Ingresso box qui davanti, rientra».
3. **Da fermo ai box**, cosa fare con la modifica. Te lo dice a voce perché la
   modifica sta in una pagina del browser che mentre guidavi non guardavi.

C'è poi una quarta cosa che non senti ma **vedi**. Dalla prima chiamata
l'avviso di rientro resta acceso sull'overlay finché non entri in corsia. Lo
trovi spiegato in «Leggere l'overlay».

Sappi che **l'ingresso della corsia box nessun gioco lo pubblica**. HONE lo
impara guardando dove lasci la pista quando rientri davvero, e ne tiene la
mediana su più rientri. Su una pista dove non sei mai rientrato, l'avviso
numero 2 **non c'è**, perché una corsia indovinata ti farebbe alzare il piede
nel posto sbagliato. Dal secondo rientro in poi l'avviso c'è.

Rientrare col menu del gioco, con «torna ai box», non insegna niente, ed è
voluto. L'auto sparisce a metà pista e ricompare in garage. Prendere per buono
quel salto vorrebbe dire mettere l'ingresso box in mezzo a un rettilineo.

### Come si registrano i giri

Non devi fare niente di speciale. Avvia la sessione, prove, hotlap o gara, e
guida.

- Il giro si chiude quando **passi sul traguardo**. HONE lo riconosce da **due
  segnali insieme**, il contatore dei giri del gioco e la posizione che
  ricomincia da zero. Uno solo non basta. Su ACC il contatore non conta il giro
  di lancio. Senza il secondo segnale si perdeva il primo giro lanciato dopo
  ogni uscita dai box. Il tempo che salviamo è quello ufficiale del gioco.
- Il **primo giro è quasi sempre parziale**, perché parti a metà pista, e lo
  scartiamo. Salviamo solo i giri **completi**, da traguardo a traguardo.
- **Se parti dai box**, in garage e in corsia box la registrazione è in pausa.
  Il giro di lancio è parziale e lo scartiamo, e il primo giro salvato è il
  primo giro lanciato. Anche il giro in cui rientri ai box non si salva. Se
  cambi auto o pista si azzera tutto, e un giro non sta mai in due sessioni.
- Un giro ha due qualità indipendenti. È **completo** se è partito dalla linea,
  e solo così si salva. È **pulito** se non sei uscito dai limiti della pista.
  Un giro sporco si salva, ma **non diventa mai il riferimento**.
- **Come decidiamo se è pulito dipende dal gioco**, perché i due titoli dicono
  cose diverse. Su **AC** contiamo le ruote fuori, e con 3 o più il giro è
  sporco. Su **ACC** leggiamo il verdetto del gioco sui limiti della pista. Su
  ACC conta quindi anche un taglio senza ruote nell'erba. Se il gioco non dice
  niente il giro resta «sconosciuto», che non vuol dire pulito.
- Il report ti dice anche **in che curva** hai perso il giro, per esempio
  «fuori pista in Variante Ascari». I giri registrati prima della versione 8
  dello schema non hanno questo dato. Dicono che il giro è sporco, ma non dove.

---

## 4. Leggere l'overlay

- **La barra del delta** si riempie **a destra in rosso** se sei più lento del
  riferimento, e **a sinistra in verde** se sei più veloce.
- **In alto** trovi il tuo **PB**, cioè il giro contro cui stai correndo, e il
  **tempo previsto** se tieni il passo. Quando arriva una staccata, quello
  spazio lo prende il **conto alla rovescia in metri**. Al momento di frenare
  diventa una parola sola, in rosso, **FRENA**. La soglia è in tempo e non in
  distanza. Dieci metri sono 0,14 s a 250 km/h, e mezzo secondo in una curva
  lenta.
- **Un'etichetta** mostra l'ultimo consiglio detto, e sparisce da sola. Quando
  l'ingegnere propone una modifica che si fa **solo ai box**, il coach ti
  richiama a fine giro. Da quel momento l'etichetta diventa l'**avviso di
  rientro**, in ambra, e non sparisce più. Resta finché non entri in corsia box,
  o finché la modifica non è più in attesa, per esempio se viene ritirata. Un
  richiamo che dura due secondi lo perdi se in quel momento guardavi la curva.
  I consigli continuano ad arrivare a voce. Cedono solo quella riga, e la
  riprendono quando l'avviso si spegne.
- **Sotto c'è una riga sottile in ambra**, il **focus**, cioè il tema su cui
  stai lavorando, con la curva e i decimi che ci perdi. Quando il coach è
  passato alle parole brevi, descritte in «Un tema alla volta», lì trovi anche
  **una parola d'esempio**, come «MENO FRENO». La frase intera resta
  nell'etichetta e nel debrief. La riga del focus ti ricorda il tema, non tutte le
  parole che sentirai.

### La traccia dei pedali

Si accende da **Impostazioni**, con **Mostra la traccia dei pedali**. All'inizio
è **spenta**, perché allunga l'overlay. Tienila accesa quando lavori sul
rilascio del freno, e spegnila quando vuoi lo schermo pulito.

È una striscia sotto l'overlay col tuo **gas in verde** e il tuo **freno in
rosso**, negli ultimi secondi, mentre li usi. Sotto le due tracce c'è un nastro
che si colora da solo.

| Nastro | Cosa stai facendo |
|---|---|
| **ambra** | Premi tutti e due i pedali, quindi **stai facendo trail braking**. |
| **grigio** | Non premi nessun pedale, ed è **tempo regalato**. |
| niente | Rilascio pulito. Hai mollato il freno e ripreso il gas senza vuoti. |

In alto a destra trovi la stessa cosa in una parola, **TRAIL**, oppure
**COAST** col cronometro di quanto stai veleggiando.

Il coach il trail braking te lo **dice**, ma a cose fatte. Qui lo **vedi mentre lo fai**, ed è l'unico modo di correggere un
rilascio. Dove le due tracce si sovrappongono c'è il tuo trail braking.

> Sulle auto stradali il consiglio a voce sul trail braking è **spento**. Lì
> portare il freno fino all'inserimento fa girare l'auto, e senza carico
> aerodinamico mollarlo tardi la fa partire. La traccia invece resta, perché
> guardarla non ti dice cosa fare.

### Il numero della curva

In basso, dopo ogni curva, leggi **quanto ti è costata quella curva** rispetto
al tuo riferimento, con un pallino colorato. Resta lì finché non chiudi la
curva dopo.

| Colore | Cosa dice |
|---|---|
| **ciano** | Hai guadagnato **almeno 0,25 s**. È la soglia per cui il coach ti fa i complimenti. |
| **verde** | Sei nella norma, fra 0,25 s di guadagno e 0,12 s di perdita. |
| **giallo** | Perdi **da 0,12 a 0,25 s**. Da 0,12 il coach comincia a parlarti. |
| **rosso** | Perdi **più di 0,25 s**. |

Tre cose sembrano guasti e non lo sono.

- **Il numero è misurato, il colore è tarato.** I decimi li puoi ricontare a
  mano. Le soglie dei colori le abbiamo scelte noi, e sono le stesse con cui il
  coach decide se parlare. Così colore e voce non ti dicono mai cose diverse.
- **Il numero è relativo al tuo riferimento**, quello scelto per le condizioni
  di oggi. Se il tuo giro migliore è lento, il verde non dice che sei veloce.
  Dice che sei **costante**.
- **Alla prima sessione con un'auto o su una pista nuova il riquadro non c'è**,
  nemmeno con un trattino. Senza un tuo giro completo non c'è niente contro cui
  misurare, e un numero inventato sarebbe peggio di nessun numero. Sparisce
  anche ai box, nel giro di lancio e sui giri fuori ritmo.

Il consiglio a voce **non cambia**. Arriva sempre all'ingresso della stessa
curva, al giro dopo, dove puoi ancora farci qualcosa. Il numero è un conto a
cose fatte, e per questo può anche mancare.

### Quando il delta non c'è

Il delta compare **solo sui giri che possono contare**, cioè quelli cominciati
dal traguardo. Non è un guasto. Un numero che confronta la corsia box con un
giro lanciato supera i 30 s e inchioda la barra a fondo scala. Sembrerebbe un
giro disastroso, e invece non è un giro. Al suo posto trovi sempre **il
motivo**.

| Cosa leggi | Cosa sta succedendo |
|---|---|
| *Sei ai box. Parto dal traguardo.* | Sei in garage o in corsia box. |
| *Giro di lancio. Comincio dal traguardo.* | Il coach comincia a lavorare dal traguardo. |
| *Ancora nessun riferimento. Fai un giro pulito.* | Con questa auto su questa pista non hai ancora un giro completo. |
| *Giro invalidato. Continua, senza delta.* | Il gioco ha annullato questo giro, e succede solo su ACC. |
| *Giro fuori ritmo. Riprendo dal traguardo.* | Qui il delta **resta**, perché il giro è cominciato dal traguardo. |
| *Giro lanciato* | Si accende per un momento quando il coach ricomincia a lavorare. |

Su un **giro invalidato il coach continua a parlarti**, e sparisce solo il
delta. Un giro annullato è un giro gratis. Frenate, bloccaggi, gomme e assetto
si leggono lo stesso, e rientrare ai box sarebbe tempo buttato.

C'è un'eccezione sola, **i complimenti**. Su un giro che il gioco non conta
più, in una curva dove hai guadagnato non senti «Qui guadagni, rifalla così». E
il riquadro non mostra quel guadagno. Quel tempo l'hai guadagnato
uscendo di pista, e un complimento ti insegnerebbe la scorciatoia. I consigli
sulle curve dove hai **perso** restano tutti. Su un giro buttato, di solito, è
lì che c'è più da imparare.

Senza riferimento, invece, resta acceso tutto quello che non ne ha bisogno.
Sottosterzo e sovrasterzo, veleggio, trail braking, marce, pressioni e
temperature ci sono sempre. Ti conviene saperlo alla prima sessione con
un'auto nuova.

---

## 5. Analisi e report nel browser

Finita la sessione, rivedi tutto con calma.

- Dall'hub, nella sezione **Analisi**, premi **Analisi e report**. Dalla riga
  di comando invece scrivi
  ```
  python -m accoach web
  ```
  La pagina `http://127.0.0.1:8778` si apre da sola.

Su un portatile, fino a 1600 px di larghezza, la pagina resta com'è. Su uno
schermo più largo il testo del report e della pagina Ingegnere cresce da solo,
fino a 20 px invece di 14.

### La Pagella

Apri il report e arrivi sulla **Pagella** della tua ultima uscita. È una pagina
sola, da leggere in dieci secondi. In alto trovi pista, auto, data e quanti giri
hai fatto, coi validi fra parentesi. Con la tendina scegli un'uscita più
vecchia.

Sotto c'è il verdetto, in una o due frasi. Ti dice quanto lasci in media a ogni
giro rispetto al tuo giro di riferimento, e dove si concentra. Lo confronta con
la sessione prima, con la stessa auto sulla stessa pista. Se una sessione prima
non c'è, lo scrive.

Poi trovi quattro blocchi, in quest'ordine.

- **I tuoi difetti principali.** Sono abitudini di guida che si ripetono in più
  curve, come frenare troppo presto o tornare tardi sul gas. Per ognuno vedi
  quanto ti costa a giro, in quante curve e in quanti giri compare. Accanto,
  una freccia ti dice se è sceso, è rimasto uguale o è salito rispetto alla
  sessione prima, e di fianco vedi le ultime sessioni. Il progresso lo leggi lì, in un difetto che cala da una
  sessione all'altra. Con un clic lo apri curva per curva.
- **Dove sbagli di più.** Le curve che ti costano di più, col loro nome.
- **Errori più frequenti.** Bloccaggi, pattinamenti, sottosterzo, sovrasterzo e
  uscite di pista, contati sulla sessione. Compaiono solo quelli che ci sono
  stati. Su ACC con l'ABS acceso il bloccaggio fisico non avviene, quindi non
  lo contiamo.
- **Il piano per la prossima uscita.** Al massimo tre consigli, in ordine.

Ogni numero viene dai tuoi giri. Se un dato manca, la riga lo dice o non
compare, e non lo inventiamo. Tutte le sessioni si misurano contro lo stesso
riferimento, quello di oggi. Così, se un difetto cala, sei cambiato tu e non il
metro. Quando il riferimento cambia, lo storico si ricalcola.

La Pagella parla di guida. I problemi d'assetto restano all'Ingegnere.

**Il piano si segue un consiglio alla volta.** Ogni consiglio riguarda un
difetto e le curve dove pesa di più. **Lo seguo** e **Non lo seguo** compaiono
sul primo consiglio proposto, finché non ne segui uno. **Lascio stare** compare
sul consiglio in corso. Tutti hanno **Come si fa →**.

- **Lo seguo** lo mette in corso, con la data di oggi.
- **Non lo seguo** toglie dal piano un consiglio che non hai ancora cominciato.
  Il difetto resta in Pagella, e il consiglio resta fuori dal piano finché non
  lo riprendi. Lo ritrovi sotto «Hai messo da parte questi consigli.», col
  bottone **Riprendi**.
- **Lascio stare** chiude il consiglio in corso senza darlo per raggiunto.

Il consiglio in corso si misura solo sui giri che fai dopo averlo preso. È
raggiunto quando, su almeno tre giri, stai sotto l'obiettivo in metà di quelli.
L'obiettivo è recuperare metà di quello che perdi oggi. Quando succede, la
Pagella te lo dice e ti propone il consiglio dopo.

**In macchina, il coach segue il tuo consiglio.** Alla prossima uscita il focus,
descritto in «Un tema alla volta», lavora sulle curve del consiglio che stai
seguendo e parla lì. Così piano e coach ti dicono la stessa cosa. Se in quelle
curve non perdi più abbastanza, il coach sceglie da solo come sempre. Un
verdetto del coach non chiude il consiglio, lo chiude solo la misura del
report.

**Nelle altre schede il consiglio che segui è segnato.** Confronto, Traiettoria,
Settori, Dinamica e Andamento hanno in cima una riga col bordo viola. La riga
nomina le curve del consiglio e ti dice cosa guardare in quella scheda. Un clic
sul nome di una curva ti porta lì, e **Come si fa →** apre la pagina del
consiglio. Nei grafici e nelle liste, le curve del consiglio hanno un pallino
viola. Senza un consiglio in corso le schede restano come sono.

### Come si fa

**Come si fa →** su un consiglio apre la sua pagina, e torni indietro con
**← Torna alla Pagella**. La pagina è costruita sui tuoi giri, e ha queste
parti.

- In cima, il problema in una frase coi tuoi numeri. Ti dice dove cominci a
  frenare, quanti metri prima del tuo giro migliore, e quanto ci perdi.
- **Dai tuoi giri**, le figure, una per curva, dalla più costosa. Ognuna ha la
  mappa della curva coi punti del tuo giro solito e del tuo migliore, e il
  grafico del freno, del gas o della velocità sovrapposti. Se a un giro mancano
  le coordinate o un canale, al posto della figura trovi scritto cosa manca.
- **La tecnica**, poche righe su cosa fare, cosa guardare in pista e cosa
  ignorare. Dove la tecnica cambia da un'auto all'altra, cambia anche qui. Su
  una stradale con poco carico aerodinamico non ti fa allenare il trail
  braking. Lì la tecnica giusta è frenare dritto e poi girare. Per lo stesso
  motivo il coach in pista, su quelle auto, non te ne parla.
- **L'esercizio**, con quanti giri fare, l'obiettivo in numeri e quando è fatto.
- **Come sta andando**, cioè il numero di quel difetto in ogni sessione da
  quando lo segui. Si riempie dalla prima sessione dopo che hai premuto
  **Lo seguo**.
- **Glossario**, le parole che usa la pagina, come punto di frenata, apex o
  giro di riferimento, con una frase ciascuna.

### Le schede del report

Le schede stanno in tre gruppi, nell'ordine in cui di solito le leggi.

**Com'è andata oggi**

- **Pagella** è la pagina descritta qui sopra. Si apre da sola dopo una
  sessione nuova. Altrimenti il report riapre l'ultima scheda che guardavi.
- **Sessione** racconta una sola uscita. Trovi i giri nell'ordine in cui li hai
  guidati. Ci sono anche quelli tagliati o non validi, che però non fanno
  media. Poi il migliore, la costanza, la temperatura dell'asfalto, e
  **cosa è cambiato dall'ultima volta** con la stessa auto sulla stessa pista,
  curva per curva. Con un clic su un giro lo apri in Confronto. Le sessioni le
  deduciamo dagli orari, e una pausa lunga vale come sessione nuova.
  Trovi anche la **benzina al giro**, misurata dal serbatoio e non stimata,
  accanto a ogni giro e come media della sessione. Sui giri registrati prima
  che HONE leggesse il serbatoio non compare, perché non lo sappiamo, e non
  vuol dire zero litri. Non compare nemmeno sui giri in cui hai rifornito,
  perché in mezzo c'è un rifornimento e non un consumo.
- **Il giro spiegato** ti mostra il giro una cosa alla volta, invece di cinque
  grafici insieme. Ti dice cosa ti è costato di più, perché, e cosa fare, col
  grafico ritagliato sul tratto di cui parla. Sono al massimo tre passi. Se sei
  lontano dal passo apre col tema generale e si ferma lì, perché a quella
  distanza l'analisi curva per curva non serve. Sul tuo giro di riferimento ti
  dice che non c'è niente da correggere, invece di inventarsi una lezione.

**Perché, nel dettaglio**

- **Confronto.** Scegli auto e pista e due giri, uno da rivedere e uno di
  confronto. Vedi quattro grafici allineati alla posizione in pista, cioè
  **delta sul giro**, **velocità**, **gas e freno** e **sterzo**, con le bande
  delle curve. Passando il mouse leggi i valori punto per punto. Il giro lo
  esporti in **CSV** o **JSON**.

  Sullo **stesso schermo** c'è la **mappa della pista**. Mostra la traiettoria
  colorata sul distacco e i punti di frenata tuoi e del riferimento. Le curve
  hanno **il loro nome**, lo stesso che trovi nel resto della pagina. Se hai perso
  il giro, una croce rossa segna il punto in cui l'hai perso. La mappa **resta
  ferma** mentre scorri i grafici. Se passi il mouse sul delta, lo stesso punto
  si accende anche sulla mappa.

  Sotto la mappa trovi **Le tue frenate**, la scheda dei tuoi punti di frenata
  curva per curva. Per ogni curva leggi **a che velocità freni**, in che marcia,
  quanto è lunga la staccata e che minima porti. La velocità è un riferimento
  che hai su ogni auto, e la leggi sul cruscotto. C'è anche il **riferimento
  visivo** dove la pista ne ha uno, come il cartello dei 150 m. Dove non ce
  l'ha, **scrivilo tu**. La cella si apre, e il tuo riferimento entra nella
  scheda e nella voce del coach. Su Imola due guide indipendenti si
  contraddicono su quasi ogni curva, e nessuna misura sceglie fra il cartello
  dei 50 e quello dei 100. La curva davanti ce l'hai tu.

  L'ultima colonna è la **dispersione**, cioè di quanto si sposta il tuo punto
  di frenata da un giro all'altro. La leggi in km/h e nei metri che valgono su
  quella staccata. La misuriamo sui tuoi ultimi giri **nella stessa fascia di
  temperatura dell'asfalto**, e l'intestazione dice su quali giri e a quanti
  gradi. Le schede di frenata dei forum questo non lo sanno, ed è per questo
  che i loro numeri non sono i tuoi. La scheda si scarica in **CSV**, e il
  bottone **Stampa** stampa solo lei.
- **Traiettoria.** Mostra dove sei passato, curva per curva. La curva
  ingrandita ha la tua linea e quella del riferimento, e **la fascia colorata
  fra le due è lo scarto**. Se a scala vera è troppo sottile, il selettore
  **scarto ×3** la ingrandisce. Il grafico lo scrive, e la barra della scala
  resta vera. Accanto trovi la stessa curva in numeri. Ti dicono quanto
  eri **dentro o fuori** in ingresso, all'apex e in uscita. Poi vedi se il tuo
  punto più lento cade **prima o dopo** quello del riferimento. C'è anche quanto è
  stretto l'**arco** che hai percorso, e quanta **strada in più** hai fatto.
  Sotto c'è la tabella di tutte le curve, da scaricare in **CSV**.

  Sulle due linee vedi anche **dove freni e dove torni sul gas**, col segno
  pieno per te e vuoto per il riferimento. È quello che trasforma «sei più
  largo in ingresso» in una diagnosi. Largo con la stessa staccata e largo
  staccando 15 m dopo sono due errori diversi. Le soglie sono le stesse della
  scheda Le tue frenate, quindi il segno e la colonna **Freni a** parlano dello
  stesso punto.

  In basso a destra del disegno c'è **il giro intero con la curva cerchiata**.
  Due tornanti della stessa pista fanno la stessa immagine, e senza quel
  disegno dovresti ricordarti tu quale hai aperto. In alto c'è la **frase del
  debrief** per quella curva. È la stessa frase del debrief, non un secondo
  parere.

  **Il nome della curva lo puoi dare tu.** Accanto al titolo della curva c'è
  una matita. Scrivi come la chiami, e da lì in poi quel nome compare ovunque,
  nel debrief, nelle perdite, nelle frenate e nella voce del coach. HONE
  conosce i nomi di **14 circuiti su 26**, e di altri dieci circuiti ACC non
  ha nemmeno la forma. Lì il nome della curva lo sai solo tu. Il tuo nome
  batte anche il nostro, se il nostro non ti piace, e lo togli come lo hai
  messo. I nomi stanno in `Documenti/ACCoach/corner-names.json`, in chiaro, e
  li puoi leggere, copiare e correggere a mano.

  Sotto le due linee vedi **la pista dall'alto**, con l'asfalto e i cordoli, e
  di fianco l'erba, la ghiaia e il cemento. Non è un disegno nostro. È la
  geometria con cui il gioco decide dove sei, letta dal suo modello delle
  superfici pezzo per pezzo.

  La pista la riconosciamo **dalla forma del tuo giro, non dal nome**. I due
  simulatori chiamano i circuiti in modo diverso. Mount Panorama per uno è
  `mount_panorama` e per l'altro `rt_bathurst`, quindi il nome non basta per
  trovarla. Se il gioco non è installato restano i **26 circuiti che HONE si
  porta dietro**. Linea centrale e larghezze vengono da OpenStreetMap e da
  immagini satellitari. Sono meno dettagliati, senza cordoli, ma non dipendono
  da cosa hai sul disco.

  La pagina ti avverte di due cose.

  * La pista compare **solo se è davvero quella su cui hai guidato**. Dello
    stesso circuito girano versioni diverse, e una che non combacia
    disegnerebbe la strada nel posto sbagliato.
  * La pista **sparisce se ingrandisci lo scarto ×3**. Lì la linea disegnata
    non è più dove sei passato, e sembreresti fuori strada senza esserlo.

  Il disegno **si gira** per riempire il riquadro. Una rotazione non sposta un
  punto rispetto a un altro. Forma, larghezze e metri restano gli stessi, e la
  barra della scala misura gli stessi metri.

  Sul «prima o dopo» la scheda ti dà da sola due avvertenze. In una curva
  lunga il fondo della velocità è **piatto**, come a Fagnes per un centinaio
  di metri. Lì due giri identici avrebbero il minimo in due punti diversi per
  puro caso. HONE scrive allora **stesso punto** e dice per quanti metri il
  minimo è piatto, invece di farti inseguire una differenza che non c'è. Se in
  quella curva sei uscito o hai girato, non ti dice che hai preso l'apex
  tardi. Ti dice, per esempio, «Scendi a 32 km/h contro 93, e qui la
  traiettoria non si legge».
- **Settori.** Mostra i tre settori, quelli **veri della pista** quando il gioco
  li pubblica, altrimenti il giro diviso in tre parti. La scheda dice quale dei
  due. Vedi il tuo tempo contro il riferimento con le barre del distacco. Poi
  c'è il **giro ideale**, cioè i tuoi settori migliori messi insieme, con
  quanto vale rispetto al tuo giro migliore vero. Sotto trovi **ogni giro, settore per
  settore**, col migliore di ogni colonna in evidenza. Il giro ideale è un
  tempo che nessuno ha guidato, e lì vedi **di quali giri è fatto**. Così
  capisci se quel settore è stato un colpo di fortuna o un'abitudine.
- **Dinamica.** Ti dice cosa faceva l'auto, non cosa hai fatto tu. Trovi le G
  longitudinali e laterali nel **diagramma G-G**, che ti dice quanto del grip
  disponibile stavi usando. Poi c'è lo **slittamento** per asse, con
  l'anteriore che blocca e il posteriore che pattina. Seguono la **rotazione**
  contro lo sterzo, i **giri motore** con le cambiate, e le **gomme lungo il
  giro**, con temperatura e pressione. Il grafico del **Bilanciamento** colora la
  traiettoria in blu dove l'auto sottosterza e in rosso dove sovrasterza. È la
  scheda da aprire quando il debrief ti dice il perché e tu vuoi vederlo coi
  tuoi occhi.

**Nel tempo**

- **Andamento.** In cima trovi **i tuoi difetti, sessione per sessione**, fino a
  venti sessioni, misurati contro lo stesso riferimento della Pagella. Lì vedi
  se un difetto cala, e con un clic sul nome apri il suo **Come si fa**. Sotto
  c'è l'andamento dei tempi, la **costanza** e i **punti deboli** curva per
  curva, sistematici o sporadici. Poi gli **errori ricorrenti**, con quante
  volte li hai fatti e in quali curve. È il quaderno dei conti. Il piano che ne esce
  sta nella **Pagella**, e le gomme stanno in **Passo gara**.
- **Passo gara.** Ti dice come regge il passo **su un pieno solo**. È un taglio
  diverso da Sessione, e la differenza conta. Una sessione la deduciamo dagli
  orari, e dentro un'uscita ci può stare un **rifornimento**. Fare la media del
  passo a cavallo di un rifornimento mescola due carichi di benzina. Lo stint
  invece si taglia dove il serbatoio **risale**, confrontando la benzina a fine
  giro con quella all'inizio del giro dopo.

  Per ogni stint trovi il **passo**, cioè la mediana dei giri davvero a passo.
  Un testacoda resta nella lista ma non fa media. Poi la **dispersione**, il
  consumo al giro, i giri che ti restano nel serbatoio e il grafico del passo
  giro per giro. In fondo ci sono le **gomme lungo lo stint**, con temperature
  e pressioni per ruota.

  Più dei numeri conta **quello che i numeri non dicono**. La pendenza del passo
  è un valore **netto**. Lo stint accelera perché il serbatoio si svuota e
  rallenta perché le gomme calano. Per separare le due cose serve sapere quanto
  vale un litro in secondi, e oggi **non lo sappiamo**. Si misura guidando uno
  stint apposta a passo costante. Per questo la pendenza ha il suo margine
  d'errore. Quando è più piccola di quel margine la scheda scrive «Non c'è una
  deriva misurabile.», invece di inventarti un degrado. Non è nemmeno usura
  delle gomme, perché nessuno dei due simulatori la pubblica. Quello che vedi
  è la temperatura.

Nella tendina dei giri, accanto al tempo, trovi **i gradi dell'asfalto**, come
in `2:03.732 · 37,8 °`. Non è un dettaglio. Fra pista fredda e pista calda i
punti di frenata si spostano di 10-20 metri. Due giri con temperature molto
diverse sono quasi due circuiti diversi, e confrontarli dice poco.

Sotto le altre schede c'è sempre **il giro che stai guardando**, con tempo,
riferimento, distacco e gradi dell'asfalto. Con tante schede è facile leggere i
numeri di un giro pensando a un altro.

L'asse orizzontale di tutti i grafici è **in metri**, non in percentuale del
giro. «Al 50 %» è un numero da convertire prima di poterci guidare. I metri li
**misuriamo sulle coordinate registrate**, e non li ricaviamo dalla posizione
per la lunghezza della pista. A volte un giro non ha coordinate, o le sue
coordinate non tornano con velocità e tempo. Allora l'asse torna in percentuale,
invece di darti una scala sbagliata.

Ci sono due scorciatoie. **Ogni scheda si apre con un tasto**, in ordine da
sinistra a destra, e lo vedi passandoci sopra col mouse. Vale anche per la
tendina dei giri. I tasti **[** e **]** scorrono i giri.

Sotto ogni curva vedi anche **dove, dentro la curva, è finito il tempo**. Può
essere una barra divisa in *ingresso, apex, uscita e tratto dopo*, e passando
il mouse leggi i secondi di ciascun pezzo. Quando il tempo sta quasi tutto in
un punto, trovi invece una frase sola, come «Il tempo lo perdi soprattutto in
ingresso, 0,21 s.». Non è una stima. È il tempo perso nella curva diviso in
pezzi, e i pezzi tornano esattamente al totale. Il tratto dopo c'è perché il
debrief dà a una curva anche il rettilineo che la segue. È lì che si paga
un'uscita storta, e senza quel pezzo gli altri tre non tornerebbero.

A volte, sotto il titolo di una curva, trovi una riga che comincia con **↩**.
Vuol dire che **la perdita di quella curva non è nata lì**. Ci sei arrivato già
più lento, e i km/h che ti mancano all'ingresso li avevi già persi all'uscita
della curva prima. In quel caso è **quella** la curva su cui lavorare, e
sistemata lei, questa migliora da sola. La riga compare solo quando i conti
tornano davvero. Se la velocità l'hai persa sul rettilineo fra le due, con
un'alzata o una cambiata sbagliata, non diamo la colpa alla curva prima.

Nel debrief, **sopra** l'elenco delle curve, possono comparire uno o due
riquadri col bordo azzurro. Sono osservazioni **su tutto il giro**, non su una
curva.

- *Alzi il gas dove il riferimento va in pieno.* Il riquadro ti dice quanto ti
  è costata l'alzata. Il conto copre solo l'alzata, ma la velocità che perdi
  te la porti sul rettilineo.
- *Ti mancano N km/h di velocità di punta.* Qui conta il resto della frase. Se
  in curva vai come il riferimento, non sei tu a essere più lento, e devi
  guardare ala e rapporti. Se sei più lento anche in curva, è velocità
  d'uscita e l'assetto non c'entra.

### Curva per sessione

Sotto i punti deboli, ogni curva **sistematica** ha il suo grafico. Mostra la
perdita mediana in quella curva, **una barra per sessione**. Due uscite nello
stesso pomeriggio restano due barre. Così vedi se quello che hai cambiato fra
l'una e l'altra ha funzionato.

Le soglie sono due, e valgono insieme. Una sessione con **meno di tre giri** su
quella curva non compare. Una mediana su due giri vale poco più di un giro
solo. Una sessione che manca **non** si disegna
a zero, perché lo zero qui vuol dire che l'hai presa bene. Poi la curva compare
solo con **almeno due sessioni** sopra quella soglia. Un punto solo non è un
andamento, è un giro fortunato. Una curva appena diventata sistematica può non
avere ancora un grafico, finché non ha due sessioni buone.

### Chi diventa il riferimento

È il tuo giro più veloce con quell'auto su quella pista, con tre regole in più.

- **I giri sporchi non sono mai candidati.** Un giro tagliato è più veloce per
  un motivo.
- **Un giro che nessuno ha giudicato non batte un giro giudicato.** Su ACC il
  «pulito» dei giri registrati **prima del 21 luglio 2026** veniva da un campo
  che quel gioco dichiara ma non riempie mai. Diceva pulito perché nessuno ha
  guardato, non perché lo fosse. Quei giri non li buttiamo. Restano il tuo
  riferimento se non hai altro, perché un bersaglio dubbio è meglio di nessun
  bersaglio. Perdono però contro qualunque giro verificato davvero. La regola
  è nata da un caso vero. A Monza il riferimento era un 1:53.712 che
  **tagliava la Variante della Roggia** per metà curva, ed era il più veloce
  proprio per quello. Quando succede, il riepilogo scrive «Scelto perché
  verificato». Poi aggiunge «il tuo 1:53.712 è più veloce, ma nessuno ne ha
  verificato i limiti di pista».
- **Le condizioni contano**, e sono tre, la **gomma**, la **temperatura
  dell'asfalto** e il **grip della pista**. Un giro fatto in condizioni simili a
  oggi batte uno un po' più veloce fatto in condizioni molto diverse. La gomma
  pesa più di tutto, perché una mescola diversa è un'altra macchina, e il grip
  pesa meno di tutto. È una preferenza, non un filtro. Se niente somiglia a
  oggi, il riferimento è comunque il tuo giro migliore.

  Due cose da sapere su questi dati. La gomma la **confrontiamo e basta**,
  senza interpretarla. Su ACC il nome della mescola è sempre lo stesso,
  `dry_compound` o `wet_compound`. Su AC è quello che ha scelto chi ha fatto
  l'auto, come `Soft (S)`. Per sapere se due giri erano sulla stessa gomma va
  bene lo stesso. Il **grip su ACC vale sempre 0**. Quel gioco lascia a zero il
  campo vecchio e mette le condizioni in un'altra parte della memoria, che
  ancora non leggiamo. Su ACC quindi il grip non pesa, e il riferimento si
  decide su gomma e temperatura.

Nel **report** vale la stessa regola, ma lì «oggi» non esiste. Il riferimento si
sceglie per le condizioni **del giro che stai rivedendo**. Se rivedi un giro di
un mattino freddo, il bersaglio giusto è il tuo migliore con quel freddo. Non
è il record fatto di sera su asfalto gommato, altrimenti ogni decimo del
debrief misurerebbe il meteo e non la guida. Quando il giro di confronto è più
lento del tuo migliore, il riepilogo te lo dice con i gradi di tutti e due. Per
esempio «Scelto per le condizioni» e «asfalto a 12,0 °C, mentre il tuo
1:39.000 era a 32,0 °C». Se il giro di confronto lo scegli tu dalla tendina,
vale la tua scelta e non cambia più.

Se sei lontano dal passo, il tuo giro migliore è un bersaglio che ti tiene dove
sei. Nella sezione **Analisi** dell'hub c'è **Importa un giro di riferimento
PRO**. Puoi importare un giro più veloce, e da lì in poi il coach ti misura su
quello.

> Vuoi provare HONE senza il gioco? `python -m accoach web --demo` carica giri
> di esempio.

### Aprire il report sul telefono o sul tablet

Ti serve se giochi su tre monitor e vuoi il **Report** o l'**Ingegnere** su uno
schermo a fianco.

1. Nell'hub, sezione **Dispositivi**, spunta **Consenti l'accesso dagli altri
   dispositivi in rete**. HONE se lo ricorda.
2. Compaiono i codici QR, fra cui **Report** e **Ingegnere**, con l'indirizzo
   sotto, come `http://192.168.1.23:8778`. **Inquadra il codice** col telefono,
   oppure scrivi l'indirizzo nel browser.

Qualche dettaglio pratico.

- Il telefono deve stare sulla **stessa rete Wi-Fi** del PC.
- Se **Windows** te lo chiede al primo avvio, consenti l'accesso su **reti
  private**.
- Per il **Report**, cioè i giri salvati, basta che l'analisi sia accesa. La
  pagina **Ingegnere** in tempo reale ha bisogno anche di Coach Live, o del
  Backend live se guidi senza overlay.
- Con l'opzione spenta, tutto resta solo su questo PC, all'indirizzo
  `127.0.0.1`.

---

## 6. Il debrief nel terminale

Per un riassunto veloce a fine sessione, scrivi questo.

```
python -m accoach debrief [auto] [pista]
```

Ti elenca le curve dove hai perso più tempo, con la causa, e la tua costanza.
Legge i giri salvati, quindi il gioco può essere chiuso.

---

## 7. Tutti i comandi

Da un terminale scrivi `python -m accoach <comando>`. Dal sorgente il comando è
`python accoach_main.py <comando>`.

**Per guidare ti bastano tre comandi**, gli stessi che vedi con
`python -m accoach help`.

| Comando | A cosa serve |
|---|---|
| `live [--silent]` | **Coach vocale e overlay** in un solo processo. È l'uso normale. |
| `web [--demo]` | L'analisi nel browser, con giri salvati, report e guida. |
| `launcher` | L'hub, la finestra con tutte le sezioni. |

Gli altri comandi sono strumenti per sviluppare, provare in pista o usare un
secondo schermo. Per guidare non servono, e per questo non stanno nella prima
schermata. L'elenco completo e aggiornato lo trovi così.

```
python -m accoach help --all
```

Questi sono quelli che potrebbero servirti davvero.

| Comando | A cosa serve |
|---|---|
| `debrief [auto] [pista]` | Il debrief in testo a fine sessione. Il gioco può essere chiuso. |
| `coach [--silent]` | Il coach vocale nel terminale, senza overlay. |
| `recorder` | Registra solo i giri, senza coach. |
| `monitor` | Mostra la telemetria grezza. |
| `setup show <file>` | Legge un setup ACC senza avviare il gioco. |
| `selftest` | Controlla che la voce funzioni e scrive un report. |
| `logs` | Apre la cartella dei log e dei crash report. |
| `logs --zip` | Fa un solo file da allegare a una segnalazione, coi log, la versione, il commit, Python e il sistema, e le ultime auto e piste. Il file nasce anche se non ci sono log, e in quel caso lo dice. **I log entrano così come sono, senza filtri.** Contengono percorsi col nome del tuo account Windows, come `C:\Users\<account>\...`, e la cartella di rete se ne hai una. Hanno una riga con data e ora per ogni avvio di HONE, cioè il registro di quando ti sei seduto a guidare. Ci sono i tuoi tempi sul giro, piste, auto e nomi dei file aperti. Ci sono anche i crash report, con l'errore completo. È voluto, perché un log ripulito non serve a trovare un difetto. Il comando lo scrive dentro lo ZIP e a schermo quando finisce. Aprilo e guardalo prima di mandarlo. |
| `find-rain` | Trova i campi della pioggia di ACC misurandoli. Ti serve una sessione con meteo variabile. |

### Il file di configurazione

Quasi tutto si regola da **Impostazioni**. Il resto sta in
`Documenti/ACCoach/config.toml`, che HONE crea al primo avvio con un commento per
ogni voce. Modificalo ad app chiusa, perché **i valori si leggono all'avvio**.

Queste voci esistono solo lì.

| Voce | A cosa serve |
|---|---|
| `data.laps_dir` | Sposta la cartella dei giri, su un altro disco o in una cartella sincronizzata. Se la lasci vuota resta `Documenti/ACCoach/laps`. |
| `acquire.hz` | Quanti campioni al secondo legge il registratore. |
| `server.host` · `server.port` · `server.hz` | Indirizzo, porta e frequenza del Backend live. |
| `web.port` | La porta dell'analisi. |
| `logging.level` · `logging.console` | Quanto scrivono i log. |

---

## 8. Consigli per usarlo al meglio

- **Fai un buon riferimento.** Il coach ti confronta col tuo giro pulito più
  veloce. All'inizio è il primo giro pulito completo, poi lo sostituisce ogni
  volta che ne fai uno migliore.
- **Usa sempre Borderless** se vuoi l'overlay.
- **Lavora su un'auto e una pista per volta.** Il riferimento vale solo per
  quell'auto su quella pista.
- Se il coach ti distrae mentre impari una pista, usa `--silent` e guarda solo
  l'overlay. Riaccendi la voce quando vuoi i consigli.
- Rivedi gli **errori ricorrenti** nell'Andamento. È lì che migliori il passo.

---

## 9. Se qualcosa non va

- **L'overlay resta su «Aspetto il gioco…» e non si collega.** Il gioco deve
  essere aperto e tu devi essere in pista, in una sessione. HONE legge la
  memoria condivisa solo mentre il gioco gira.
- **Non vedi l'overlay.** Sei a schermo intero esclusivo. Passa a
  **Borderless**.
- **Non senti la voce.** Lancia `python -m accoach selftest`, che scrive un
  report e prova a parlare. Dal sorgente, installa pyttsx3 con
  `pip install pyttsx3`. Ti serve anche una voce italiana di Windows, come
  Microsoft Elsa.
- **Alcune frasi suonano più robotiche delle altre.** Le frasi fisse del coach
  e le parole brevi del focus sono registrate con una voce neurale. Le frasi
  che cambiano ogni volta, come l'annuncio del focus col nome della curva,
  escono dalla voce di Windows, che è più robotica. Cambia il suono, non
  quello che ti dice.
- **Non arriva nessun consiglio di curva.** Ti manca il riferimento. Ti basta un giro
  pulito completo, dal traguardo al traguardo. Gli avvisi immediati invece arrivano comunque.
- **L'analisi non mostra i giri.** Prima devi guidarli con Coach Live o col
  registratore. Finiscono in `Documenti/ACCoach/laps`, dove l'analisi li legge.
