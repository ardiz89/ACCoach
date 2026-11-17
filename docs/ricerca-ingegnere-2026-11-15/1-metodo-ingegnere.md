# Il metodo operativo dell'ingegnere di pista in una sessione di prove

Ricerca web del 15/11/2026. Scopo: ricavare la PROCEDURA (non la teoria) con cui un ingegnere di pista decide le modifiche di assetto, per tradurla in un algoritmo per ACC/GT3.

## 0. Come leggere questo rapporto

**Livelli di fonte** (li uso accanto a ogni affermazione):

- **[ING]** ingegnere professionista che parla in prima persona o è citato per nome (Mark Williams ex McLaren F1; Richard Frith ex McLaren F1; Gary Anderson ex direttore tecnico F1; Geoff Dymott ex Williams F1; Marie-Alice Lahaye, ingegnere di pista GT3 CMR; Claude Rouelle e Bruno Finco di OptimumG; team Mercedes F1; Jeff Braun, ingegnere IMSA).
- **[COACH]** pilota o coach professionista (Ross Bentley, Dion von Moltke, Ken Hill, Tom Long).
- **[TEC]** fonte tecnica di settore senza un ingegnere di pista nominato (Penske Racing Shocks, High Performance Academy, Your Data Driven di Samir Abid).
- **[SIM]** guida per simulatore (Traxion, Driver61, Coach Dave Academy).
- **[AMAT]** appassionato, forum, autore non qualificato.
- **[ANON]** PaddockLink: sito di corsi senza autore dichiarato («author-review mirror»). Lo cito solo dove concorda con fonti migliori e mai come unica prova.

**Cosa NON ho potuto leggere** (va detto prima di tutto):

- **Carroll Smith** («Tune to Win», «Engineer to Win», «Drive to Win»): nessun estratto verificabile trovato in rete. Tre ricerche mirate non hanno restituito una sola citazione affidabile. **In questo rapporto non gli attribuisco nulla.** Che «una modifica alla volta» e «torna alla baseline» siano nel suo libro è verosimile ma qui non verificato.
- **Jorge Segers**, «Analysis Techniques for Racecar Data Acquisition»: trovata solo la scheda SAE (la 2ª edizione aggiunge un capitolo sull'analisi «metric-driven»). Nessun contenuto procedurale letto.
- **Paul Haney**, «The Racing & High-Performance Tire»: solo una attribuzione indiretta su PaddockLink (bordi caldi/centro freddo = aggiungere aria; centro caldo = toglierne). Marcata come indiretta.
- **Milliken**, «Race Car Vehicle Dynamics»: niente di procedurale reperito.
- **Claude Rouelle**: letti i «101 consigli» sul sito OptimumG; l'articolo su Racecar Engineering (marzo 2018, PDF `RCE5.pdf`) non si è scaricato (connessione chiusa due volte), ne ho solo il riassunto del motore di ricerca: marcato come indiretto.
- Pagine che hanno rifiutato l'accesso: Speedhunters «Race Car Set-up Basics Pt 2», Suspension Secrets, Winding Road (Bentley), serie Lexus RC F GT3, Rennlist «Driver debriefing», Racecar Engineering «Course of Action», guida ammortizzatori di Jim Kasprzak (PDF non leggibile), note di fisica ACC 1.9 (PDF non leggibile).

**Avvertenza sulle citazioni**: le frasi fra virgolette sono quelle restituite dallo strumento di lettura delle pagine (che riassume con un modello piccolo). Prima di pubblicarle testualmente vanno riscontrate sulla pagina. Il senso è affidabile, la lettera va verificata.

**Lacuna principale della ricerca**: non ho trovato **nessuna fonte di un ingegnere GT3 che descriva per iscritto un run plan di prove libere giro per giro**. Il run plan qui sotto è composto da F1 (Anderson, Mercedes, Dymott), fonti tecniche e guide ACC. È la parte meno solida del rapporto.

---

## 1. Procedura passo per passo

### Passo 0 — Prima di girare: piano e previsioni

1. **Non si va in pista senza un piano di prova.** Rouelle [ING]: «You can't go to a race circuit to test your racecar without a test plan.» Dymott [ING]: dopo la macchina, la priorità dell'ingegnere è compilare il run plan del giorno dopo; le gomme si assegnano pensando a qualifica e gara. Mercedes F1 [ING]: giri e obiettivi di ogni sessione sono fissati in anticipo.
2. **Un solo obiettivo per sessione, scelto ogni volta.** Jeff e Colin Braun [ING, via Speed Secrets]: i team migliori capiscono cosa conta di più per *questo* evento, e non è mai la stessa cosa. PaddockLink [ANON] concorda: una domanda causa-effetto, una misura principale e un riscontro.
3. **Scrivere prima cosa ci si aspetta** da ogni regolazione, su quella pista in quel giorno, e poi confrontare con l'accaduto. Braun [ING]: lo fa in un foglio Excel, una riga per voce. È la base del «registro delle previsioni».
4. **Si parte dal miglior assetto noto**, non da zero. Lahaye [ING, GT3]: si comincia dal miglior setup ricavato da test e gare precedenti. Penske [TEC]: partire dalle raccomandazioni del costruttore o da un setup precedente *documentato*.

### Passo 1 — Giro di uscita e riscaldamento

5. **I primi giri non si giudicano.** HP Academy [TEC]: le gomme vanno in pressione «after two or three laps». Traxion [SIM, ACC]: pressioni a caldo valutate dopo 3-4 giri di guida competitiva. Fonti ACC (ricerca): le GT3 hanno le termocoperte, pressioni a regime in 2-3 giri.
6. **Nei primi giri si guardano i dati di sistema, non il bilanciamento.** Anderson [ING]: niente giro d'installazione separato se il tempo è poco, ma occhio ai dati nei primi due giri.

### Passo 2 — Run di baseline

7. **La baseline deve essere ripetibile, non perfetta.** Penske [TEC]: «It doesn't have to be perfect. It just has to be repeatable»; 5-10 giri a passo ripetibile, *non* un giro da qualifica; registrare tempi, pressioni a caldo, temperature se disponibili, note del pilota.
8. **Lunghezza del run.** Le fonti danno numeri diversi (vedi §4): Anderson 10 giri per un run lungo in F1; Penske 5-10; Traxion 8 giri di base su ACC; una guida sim 5-8 giri puliti per confronto; Your Data Driven «un paio di giri esplorativi poi 2-3 giri spinti».
9. **Criterio di baseline stabile.** Penske [TEC]: tempi «within a couple tenths», temperature gomme equilibrate, comportamento uguale dall'inizio alla fine del run. Ken Hill [COACH]: finestra di 0,5 s sul giro, variazione del punto di frenata entro 3 m circa (10 piedi), velocità d'ingresso entro 8 km/h circa (5 mph).

### Passo 3 — Rientro e misure

10. **Rientro senza giro di raffreddamento.** HP Academy [TEC]: guidare «as hard as it possibly can right up to the entry of pit lane», perché nel giro lento la temperatura del battistrada si uniforma. Fonti pirometro (ricerca) concordano: il giro lento falsa la lettura.
11. **Ordine delle misure: temperature prima, pressioni dopo** (la temperatura cala più in fretta) — Northstar Motorsports, da riassunto di ricerca [AMAT/TEC, indiretto]. Tre punti per gomma (interno, centro, esterno), sonda sotto la superficie, a 25-30 mm dalla spalla, cominciando dalla gomma più caricata (MX-5 Club NSW [AMAT]).
12. **Regole di lettura** (accordo ampio: HP Academy, MX-5 Club, Haney indiretto, Driver61 per ACC):
    - centro più caldo dei bordi → pressione troppo alta;
    - centro più freddo → pressione troppo bassa;
    - interno molto più caldo → troppo camber negativo (o convergenza sbagliata);
    - esterno più caldo → poco camber negativo.
    - bersaglio: interno il più caldo, esterno il più freddo, centro a metà.
13. **Pressione PRIMA del camber.** HP Academy [TEC]: sistemata la pressione, «at that point we know that our pressure is correct» e solo allora si tocca il camber, a passi di circa mezzo grado, con il cronometro come giudice finale.
14. **Partire alti e scaricare.** Un ingegnere (riassunto di ricerca, Speedhunters, non letto direttamente) dice di preferire pressioni a freddo alte per essere sicuro di *togliere* aria anziché aggiungerla.

### Passo 4 — Le gomme sono il cancello: niente assetto finché non sono a bersaglio

15. **Regola più concorde di tutta la ricerca.** Speedhunters (indiretto): non tentare modifiche di assetto finché le pressioni non si sono stabilizzate al bersaglio. Traxion [SIM]: è il «first big piece of ACC setup advice», e nel suo esempio la sola correzione delle pressioni vale 1,6 s. Your Data Driven [TEC]: piloti e gomme «dominano tutto», capire le gomme per prime. Rouelle [ING]: «The first thing that influences a race tire's grip is its temperature.»

### Passo 5 — Breve debrief a fine run (vedi §2)

16. **Durante la sessione: due cose, non venti.** Williams [ING]: a fine run vuole sapere dove si perde più tempo e cosa sistemare per primo; l'analisi metro per metro si tiene per il debrief dopo la sessione. Frith [ING]: «just give us three big things that we can fix with this car». Bentley [COACH]: «If I could have the car do just one thing better, what would it be?»

### Passo 6 — Una modifica, un run uguale, confronto

17. **Una modifica mirata a un problema.** Mercedes F1 [ING]: «tackling one problem with one solution». Penske [TEC]: una sola modifica piccola e reversibile sul problema più grosso, annotando cosa e perché, poi stesso numero di giri e stesso approccio.
18. **Valutazione** (Penske [TEC]): media dei tempi e dispersione giro per giro, il problema specifico è migliorato?, temperature e pressioni, **sono nati problemi nuovi?**
19. **Esito a tre vie** (Penske [TEC]): migliora in modo ripetibile → si tiene e la baseline si aggiorna; non aiuta → si torna indietro; misto → si annota, si torna indietro, si prova un'altra direzione.

### Passo 7 — Ritorno alla baseline (A-B-A)

20. **Il run di ritorno è il controllo.** Your Data Driven [TEC], citando James Williams e Dave Devine [ING F1]: «always go back to what you think is your baseline»; il ritorno verifica «that the driver isn't just improving in himself». Ken Hill [COACH]: l'A-B-A garantisce che l'effetto non venga dalle condizioni della pista.
21. **Se il ritorno ad A è anch'esso diverso, il confronto è nullo** (PaddockLink [ANON]): non hai un risultato pulito, hai un problema nuovo da capire.

### Passo 8 — Debrief di fine sessione e registro (vedi §2 e §5)

22. Mercedes F1 [ING]: debrief quotidiano per «refine the set-up direction or find a new route». Tra una sessione e l'altra, cambi più grandi (5-10 parametri).

---

## 2. Il debrief col pilota

### Le domande, nell'ordine

Bentley [COACH] (letto direttamente su speedsecrets.com):

1. Cosa fa la macchina? Sottosterzo, sovrasterzo, neutra?
2. Dove? Quale curva o quali curve?
3. In che punto della curva? Ingresso, centro, uscita?
4. Cosa sto facendo io in quel momento? (frenata, trail braking, rilascio freno, veleggio, gas di mantenimento, in accelerazione; sterzo lento, deciso, fermo, in apertura)
5. È la macchina o sono io?

Frith [ING]: sequenza fissa per fase e velocità — turn-in, ingresso, apice, uscita, alta velocità, bassa velocità. Poi: è un problema di **bilanciamento o di grip**? A cosa equivale? Una modifica già provata l'avrebbe risolto?

Von Moltke [COACH]: qual è il problema più grosso che mi impedisce di andare più forte? Quale dei due mi rallenta di più? **Se ne sistemo uno, l'altro sparisce?**

### Scale di valutazione

- Rouelle [ING]: stabilità e bilanciamento da 0 a 10.
- OptimumG/Racecar Engineering (indiretto): scala −10…+10 in cui il «neutro» del pilota è legato a una distribuzione nota di rigidezza antirollio; le lamentele successive si leggono come **delta** rispetto a quel riferimento.
- Frith [ING]: numeri dati «based on an agreed reference point».
- Your Data Driven [TEC]: 1-10 per grip, bilanciamento, fiducia.
- PaddockLink [ANON]: 1-10 separato per frenata, primo terzo, centro, ultimo terzo.

Accordo pieno sul principio: **scala numerica relativa a un riferimento concordato**, non voto assoluto. Disaccordo solo sull'intervallo.

### Incrocio fra commento e dati

- Frith [ING]: «I want to know that we see it in the data». Se non si vede, si continua a chiedere e si riformula il commento al pilota. Mai tendere trappole al pilota: la fiducia si distrugge in fretta.
- Finco/OptimumG [ING]: il profilo dello sterzo dice il bilanciamento ma non la causa — liscio = neutra, a picco = sottosterzo, correzioni multiple = sovrasterzo; vanno riviste anche le abitudini di freno e gas.
- Rouelle [ING]: tutti i piloti sono molto più sensibili al **bilanciamento** che al **grip**. Conseguenza operativa: il pilota è buon sensore per «da che parte pende», cattivo per «quanto grip c'è in totale» → il grip si misura coi dati.
- Lahaye [ING, GT3]: se il pilota sa dire cosa serve si guadagna molto tempo; altrimenti si passa da video e dati, più lento.
- Williams [ING]: «Drivers drive and geeks do data»; il pilota guardi solo la sovrapposizione col riferimento.
- Importante anche il **briefing**: Frith — «it's as much about the briefing as the debriefing» (dire al pilota su cosa si vuole il commento, senza suggerire la risposta).

### Guida o assetto? I criteri trovati

| Criterio | Fonte | Livello |
|---|---|---|
| Il pilota ripete il giro? Se non è costante, non si tocca l'assetto | Hill; von Moltke («Don't start working on setup before you know your driving foundations are ready») | COACH |
| Distanza dal potenziale: a secondi dal riferimento = pilota; vicino al limite e il difetto resta = assetto | Hill | COACH |
| Stesso sintomo in più curve dello stesso tipo: non si fa ingegneria su un problema che compare in una sola curva | von Moltke («common theme») | COACH |
| Cosa facevano i comandi in quell'istante: un sintomo che compare solo con un certo ingresso è indotto | Bentley; Finco | COACH + ING |
| Sintomo primario vs secondario: «understeer» che in realtà è un turn-in ritardato perché il posteriore è instabile | Williams («focus on the primary balance issue, not the secondary one caused by the primary one») | ING |
| Riscontro fisico: il lamento corrisponde alle gomme? | PaddockLink | ANON |
| Il miglioramento sparisce al ritorno ad A? Allora era il pilota che imparava | Devine via YDD | ING |

Il **confronto col compagno di squadra** come criterio non l'ho trovato documentato in forma procedurale in nessuna fonte letta: è prassi nota ma qui non provata.

---

## 3. Come si sceglie la leva

### Principi (accordo fra fonti)

1. **Il primo problema nella curva prima degli altri.** Von Moltke [COACH]: si comincia dai difetti che compaiono presto nella curva. Penske [TEC]: «Most important is entry», poi centro, poi uscita. Williams [ING] dà il perché: il difetto a valle è spesso conseguenza di quello a monte.
2. **La leva più isolata per prima.** Finco/OptimumG [ING]: per cambiare solo il bilanciamento meccanico, la barra antirollio è preferibile «because it's more isolated»; la molla cambia anche altezze dinamiche e bilanciamento aerodinamico, e si usa quando la barra non ha più corsa.
3. **Gli ammortizzatori agiscono in ingresso e in uscita, non all'apice.** Finco [ING]: all'apice, con la macchina a regime, l'ammortizzatore ha poco effetto sul trasferimento di carico. Your Data Driven [TEC] concorda: il pilota sente solo lo smorzamento a bassa velocità di stelo; molle e barre governano il centro curva.
4. **Lenta = meccanica, veloce = aerodinamica** (Coach Dave [SIM], Tom Long [COACH]: posteriore instabile in curva veloce → abbassare il posteriore o più ala).
5. **Ogni modifica costa altrove.** Mercedes [ING]: l'armonia è lo scopo sfuggente, ogni componente tocca tutta la macchina. Penske [TEC]: ogni regolazione può cambiare un'altra parte della curva o della pista. GT World Challenge America: un assetto ottimo sul giro può consumare troppo sul run lungo.
6. **Il differenziale ha un tetto.** Finco [ING]: una volta bloccato a gas parziale, altra coppia di bloccaggio non fa nulla.

### Gerarchie (accordo solo parziale — attenzione)

**Your Data Driven, «scala del tempo sul giro»** [TEC]: 1) masse e pesi agli angoli, 2) geometria (camber, convergenza — sente soprattutto il turn-in), 3) molle e barre (centro curva), 4) ammortizzatori, (aerodinamica come «1,5»). Ogni gradino va a posto prima del successivo, con rendimenti decrescenti.

**Sequenza ACC di Traxion** [SIM]: pressioni → TC/ABS/ripartizione di frenata → bilanciamento aerodinamico e altezze → molle e barre. Guadagni riportati: 1,6 s / — / poco più di 0,1 s / un paio di decimi. **Driver61** [SIM]: tecnica → pressioni → modifiche «universali» (ali, altezze, ripartizione, TC/ABS) → ammortizzatori.

**Esempio richiesto: sottosterzo a centro curva lenta.** Nessuna fonte professionale dà un ordine validato. Combinando le fonti lette:

1. prima escludere il pilota (ingresso troppo veloce, sterzo eccessivo — Bentley, Finco);
2. controllare le gomme anteriori (pressione, temperature: anteriori molto più calde delle posteriori = troppo sottosterzo, fonte amatoriale);
3. **barre**: più morbida davanti o più rigida dietro (leva isolata, Finco) — *attenzione: Coach Dave scrive il contrario in una sezione («Stiffen the front ARB or soften the rear ARB» per il sottosterzo a centro curva), ed è con ogni probabilità un errore dell'articolo, che lo strumento di lettura ha segnalato come internamente incoerente*;
4. poi molle (anteriore più morbida / posteriore più rigida);
5. poi altezza posteriore (più rake, finché non diventa nervosa in frenata — Coach Dave);
6. differenziale (precarico più basso in ingresso/lenta).

Questo ordine è **una mia composizione**, non una regola citata. Va trattato come ipotesi da validare.

### Quando ci si ferma

- Rendimenti decrescenti (YDD).
- Lo scopo è «the fastest setup the driver likes» (YDD), non il più veloce sulla carta: un pilota che non si fida non spinge (Frith).
- Compare un problema nuovo più grave di quello tolto (Penske, criterio di valutazione).
- La modifica è troppo piccola perché dati e pilota la risolvano (Finco): serve altro strumento, non altri giri.
- Finisce la finestra utile: in qualifica serve una macchina più reattiva, in gara più sottosterzo per proteggere le posteriori (Mercedes) → lo «stop» dipende dall'obiettivo della sessione.

---

## 4. Regole decisionali esplicite

Formulate per l'algoritmo. Tra parentesi la solidità: **A** = più fonti indipendenti di cui almeno un ingegnere; **B** = una fonte di ingegnere o più fonti di coach/tecniche; **C** = fonte debole o mia composizione.

**Cancelli (prima di qualunque consiglio di assetto)**

- R1. SE le gomme non sono a regime (primi 2-3 giri del run) ALLORA non valutare nulla. (A)
- R2. SE le pressioni a caldo sono fuori finestra ALLORA l'unico consiglio ammesso riguarda le pressioni. (A)
- R3. SE il pilota non è ripetibile (dispersione dei tempi oltre ~0,5 s, punti di frenata oltre ~3 m, velocità d'ingresso oltre ~8 km/h) ALLORA niente assetto: il problema è la guida. (B — i numeri vengono da un solo coach)
- R4. SE il pilota è a secondi dal riferimento ALLORA il problema è la guida; SE è vicino e il difetto resta ALLORA assetto. (B)

**Diagnosi**

- R5. Descrivi ogni sintomo come (cosa × curva × fase × velocità × cosa facevano i comandi). Senza le cinque voci non proporre nulla. (A)
- R6. SE il sintomo compare in una sola curva ALLORA non è un tema di assetto; SE compare in più curve dello stesso tipo ALLORA lo è. (B)
- R7. SE il sintomo compare solo quando i comandi sono anomali (ingresso più veloce del solito, sterzo oltre il normale, gas brusco) ALLORA è indotto dalla guida. (A)
- R8. SE ci sono due sintomi nella stessa curva ALLORA lavora su quello a monte e ricontrolla l'altro dopo. (A)
- R9. SE il commento del pilota non si vede nei dati ALLORA non agire: chiedi ancora, riformula. (B)
- R10. Distingui bilanciamento da grip: del primo ci si fida del pilota, del secondo dei dati. (B)

**Scelta della modifica**

- R11. Un problema, una soluzione, una modifica per run. (A)
- R12. SE servono più modifiche insieme ALLORA registrale come pacchetto e abbassa la fiducia nella conclusione. (B/C)
- R13. Preferisci la leva più isolata (barra prima della molla; ala/altezza per l'alta velocità). (B)
- R14. Fase → famiglia di leve: ingresso/uscita = ammortizzatori, differenziale, ripartizione; centro = barre e molle; veloce = aerodinamica e altezze. (B)
- R15. Prima di proporre, scrivi l'effetto atteso e il costo atteso altrove. (B)

**Valutazione**

- R16. Stesso numero di giri, stesso carburante, stesse condizioni del run di confronto. (A)
- R17. Giudica su media e dispersione, non sul giro migliore; scarta i giri anomali (traffico, errore). (B)
- R18. Esito: migliora e si ripete → tieni e aggiorna la baseline; non aiuta → torna indietro; misto → annota, torna indietro, cambia direzione. (B)
- R19. SE il guadagno conta ALLORA rifai A; SE il ritorno ad A non riproduce la baseline ALLORA il confronto è nullo (pista, gomme o pilota sono cambiati). (A)
- R20. SE è nato un problema nuovo ALLORA pesa il saldo, non il solo sintomo curato. (B)

**Ampiezza del passo** (vedi controversie)

- R21. Passo grande abbastanza da essere misurabile da dati e pilota; SE il passo non produce differenza leggibile ALLORA raddoppialo anziché ripetere il run. (B)
- R22. SE la direzione è giusta ALLORA prosegui nello stesso verso finché smette di migliorare, poi torna indietro di mezzo passo. (C — documentato solo da fonti amatoriali e da Driver61)

---

## 5. Il registro

Contenuto della scheda (Penske [TEC], la lista più completa letta): pista, data, condizioni (temperatura, meteo, pista verde o gommata); molle ai quattro angoli; clic di compressione ed estensione; altezze; pesi agli angoli; barre; pressioni **a freddo e a caldo**; tempi (medie) e settori; temperature gomme sul battistrada; commento specifico del pilota (esempio: «entry push in slow corners»).

Regole di tenuta:

- **Storico per poter tornare indietro**: «A history of settings so you can return to original settings if necessary» (Penske).
- **Per ogni modifica: cosa, perché, cosa mi aspetto** (Penske; Braun).
- **Verifica che la modifica sia stata fatta davvero**: controllo delle regolazioni prima e dopo ogni sessione (Penske); Williams [ING] dice di controllare che la modifica sia stata applicata correttamente prima di giudicarla. Per il software: verificare che il setup caricato sia quello proposto.
- **Anche il risultato negativo si registra**: «Sometimes a bad change or feeling is just as good as a positive change» (Penske). Rouelle [ING]: «if you don't know why you win, you won't know why you lose.»
- **Taccuino dei run sempre con sé**, con tutti i dati di prova (Rouelle).
- **Salvare un setup a ogni modifica** (Traxion, ACC).
- **Incertezza della misura**: «There is no useful measurement without another kind of number: the degree of uncertainty» (Rouelle). Per l'algoritmo: ogni delta va confrontato col rumore giro-giro.
- **Lavorare in delta, non in assoluto**: «We really need to work in delta, trends, and sensitivities more than in absolute value» (Rouelle).

---

## 6. Punti controversi (dove le fonti NON concordano)

1. **Una modifica alla volta: regola o ideale?** Coach e fonti tecniche la danno per assoluta (Krider: «universal»). La prassi F1 no: Mercedes dichiara 5-10 parametri cambiati fra una sessione e l'altra e ammette cambi multipli «where multiple changes are required»; Anderson concede al massimo cinque minuti di ritocco fra i run. Coach Dave: a volte bisogna *insieme* aggiungere ala e abbassare il posteriore. **Lettura**: una alla volta *dentro* il run di confronto; a pacchetti fra sessioni, quando il tempo o la fisica lo impongono (ala e altezza sono accoppiate), dichiarandolo come pacchetto.

2. **Passi grandi o piccoli?** Penske: modifica «small enough to understand» e reversibile. HP Academy: mezzo grado di camber. All'opposto: OptimumG (indiretto) consiglia cambi abbastanza grandi da essere quantificabili, con l'esempio della convergenza portata da chiusa ad aperta; Driver61: cambio «fairly dramatic» (ala da 3 a 8) e poi si torna indietro; YDD cita il consiglio di portare le regolazioni agli estremi per capirne l'effetto; forum: più scoperte con cambi grossi che con uno o due clic. **Non c'è accordo.** La spaccatura segue lo scopo: passo grande per *imparare* la sensibilità (giornata di test), passo piccolo per *rifinire* (weekend di gara). Il «bracketing» con dimezzamento è descritto in modo esplicito solo da fonti amatoriali (mountain bike, sim): **nessun ingegnere letto lo formula così**.

3. **L'A-B-A è sempre necessario?** YDD: «[Setup] changes will always be ABA changes». Ma il suo stesso esempio è A-B-C-A (tre pastiglie, 10 giri ciascuna, ritorno alla prima). Anderson, in un'ora di F1, non torna mai alla baseline. Penske non prevede il ritorno se la modifica è chiaramente positiva e ripetibile. **Lettura**: il ritorno costa un run; si fa quando il guadagno è dello stesso ordine del rumore, o quando le condizioni stanno cambiando.

4. **Quanti giri per run.** 2-3 spinti (YDD), 3 (forum), 5-8 (guida sim), 5-10 (Penske), 8 (Traxion), 10 (Anderson, YDD nell'esempio pastiglie), 20+ (guida di gioco, da scartare). Nessuna fonte giustifica il numero con una statistica.

5. **Finestra di pressione in ACC.** 26,0-27,0 psi per tutte le classi dopo la 1.9 (note di fisica, da riassunto di ricerca: «indicative», non un punto dolce); 26,4-27,0 (GO Setups); 27,3-27,9 o 27,3-28 (Traxion, Driver61 — guide **vecchie**, precedenti al nuovo modello gomma); bagnato 30 psi (Coach Dave) contro 29,5-31 (Driver61). **Il valore dipende dalla versione del gioco**: non va scritto in costante senza riscontro sulla versione installata.

6. **Gradiente di temperatura interno-esterno.** 10-15 °C (HP Academy), 10-20 °C (corso HPA sui sensori IR), 5-10 °C (forum). Tutti lo chiamano punto di partenza.

7. **Si parla di assetto durante la sessione o solo dopo?** Von Moltke: per la maggior parte dei piloti solo dopo la sessione. Williams, Long: due cose a fine run, anche via radio; Lahaye agisce sui commenti radio se sono chiari. **Lettura**: dipende dal livello del pilota — con un amatore, meno interruzioni.

8. **Priorità assetto o tecnica?** Hill, von Moltke, Driver61 (guida ACC): prima la tecnica. Driver61 (articolo per principianti, autore non tecnico): l'assetto conta più della tecnica. La seconda posizione è isolata e debole.

9. **Dato o pilota in caso di conflitto.** Frith: voglio vederlo nei dati. Penske: «driver feel is paramount». YDD/Frith: una macchina più veloce sui dati ma che il pilota non ama è più lenta in pratica. Non è una vera contraddizione: i dati decidono *se il sintomo esiste*, il pilota decide *se l'assetto è guidabile*.

10. **Ordine barre/molle.** Finco: barra prima perché isolata. Penske: se si riesce a massimizzare ammortizzatori e molle, poi una barra più piccola «for support». Guida ISDC (forum): molle e ammortizzatori prima, barre per ultime. Disaccordo reale, ma su obiettivi diversi (costruire l'assetto da zero vs ritoccare il bilanciamento in pista). Per un consiglio in sessione vale la posizione di Finco.

### Cosa manca del tutto

- **Separare l'effetto della modifica da calo benzina, usura ed evoluzione pista con un metodo numerico**: nessuna fonte di ingegnere letta lo descrive oltre «confronta mele con mele» (Finco: stesse gomme, pista, pilota, usura) e «torna ad A». La correzione per il carburante esiste in letteratura di strategia F1 (modello tempo = base + carburante + gomma + rumore) ma l'unico coefficiente trovato (0,03 s/giro per kg) viene da una pagina senza fonte: **non usarlo**. Per ACC conviene misurare la propria sensibilità al carburante sui giri registrati.
- **Run plan GT3 reale**: vedi §0.
- **Freni ed elettronica nell'ordine di priorità**: solo fonti sim (Traxion: TC/ABS e ripartizione subito dopo le pressioni). Mercedes nota che differenziale e ripartizione li regola il pilota dal volante durante la sessione → in ACC sono le leve applicabili *mentre si gira*, a differenza di tutto il resto che richiede il box.

---

## 7. Traduzione per l'algoritmo (sintesi operativa)

1. **Stato del run**: uscita → riscaldamento (niente giudizi) → finestra di misura → rientro.
2. **Cancelli in cascata**: gomme a regime → pressioni in finestra → pilota ripetibile → distanza dal riferimento. Finché un cancello è chiuso, il consiglio riguarda quel cancello.
3. **Sintomo strutturato** a cinque campi, con conteggio delle curve dello stesso tipo in cui compare e dei giri in cui si ripete.
4. **Filtro guida/assetto** sui comandi nell'istante del sintomo.
5. **Un solo tema**, il più costoso in tempo, il più a monte nella curva.
6. **Una proposta** con effetto atteso, costo atteso e via di ritorno; leva più isolata; leve da volante (ripartizione, TC, ABS) proponibili in pista, il resto solo al box.
7. **Run di verifica** a parità di giri e carburante; esito a tre vie; ritorno ad A quando il guadagno è vicino al rumore.
8. **Registro**: previsione, misura, esito, incertezza; anche i fallimenti.

---

## 8. Fonti

### Lette direttamente

| Fonte | Chi parla | Livello | URL |
|---|---|---|---|
| Autosport, «How to work with your engineer» | Mark Williams, ex McLaren F1 | ING | https://www.autosport.com/engineering/feature/8072/how-to-work-with-your-engineer |
| Your Data Driven, podcast ep. 39 | Richard Frith, ex McLaren F1 (dinamica veicolo) | ING | https://www.yourdatadriven.com/ep39-f1-engineer-richard-frith-on-suspension-setup-driver-feedback-part-2/ |
| Your Data Driven, test A-B-A | Samir Abid; cita Braun, Devine, J. Williams, Kirkpatrick | TEC/ING | https://www.yourdatadriven.com/how-to-approach-race-car-testing-lessons-from-f1/ |
| Your Data Driven, scala del tempo sul giro | Samir Abid | TEC | https://www.yourdatadriven.com/fixing-poor-racecar-handling-balance/ |
| Your Data Driven, esperimenti | Samir Abid | TEC | https://www.yourdatadriven.com/you-dont-learn-from-experience-you-learn-from-experiments/ |
| Your Data Driven, giornata di test gomme | Samir Abid | TEC | https://www.yourdatadriven.com/planning-a-successful-tyre-test-day/ |
| OptimumG, 101 consigli | Claude Rouelle | ING | https://optimumg.com/claude-rouelles-101-tips-for-formula-student-competition-participants/ |
| OptimumG, Q&A ep. 1 (assetto e cinematica) | Bruno Finco | ING | https://optimumg.com/vehicle-setup-and-kinematics-qa-series/ |
| OptimumG, Q&A ep. 3 (dati, assetto, miti) | Bruno Finco | ING | https://optimumg.com/data-analysis-vehicle-setup-and-common-misconceptions-qa-series-ep-3/ |
| Mercedes-AMG F1, «How do you set up a Formula One car» | team | ING | https://www.mercedesamgf1.com/news/how-do-you-set-up-a-formula-one-car |
| The Race, piano per un'ora di prove | Gary Anderson | ING | https://www.the-race.com/formula-1/gary-anderson-what-f1-teams-should-do-in-their-one-practice-hour |
| MIA School of Race Engineering, giovedì | Geoff Dymott, ex Williams F1 | ING | https://www.schoolofraceengineering.co.uk/blog/post/16477/race-engineering-day-by-day--thursdays/ |
| GT World Challenge Europe, «In Profile: The Race Engineer» | Marie-Alice Lahaye, CMR (Bentley GT3) | ING GT3 | https://gt-world-challenge-europe.com/news/1906/in-profile-the-race-engineer- |
| GT World Challenge America, «Chat GT3» | redazionale, senza nomi | TEC | https://www.gt-world-challenge-america.com/news/1527/chat-gt3-how-much-do-car-setups-vary-depending-on-the-track |
| Speed Secrets, «Make your car handle better» | Ross Bentley | COACH | https://speedsecrets.com/make-your-car-handle-better/ |
| NASA Speed News, «Setup issues» | Dion von Moltke | COACH | https://nasaspeed.news/columns/driver-instruction/driving-tips-setup-issues/ |
| Blayze, lavorare sull'assetto | Ken Hill | COACH | https://blayze.io/blog/car-racing/working-on-racecar-setup |
| Tom Long Racing | Tom Long | COACH | https://tomlongracing.com/2020/03/05/answering-your-questions-turning-feedback-into-adjustments/ |
| Penske Racing Shocks, baseline | azienda | TEC | https://www.penskeshocks.com/blog/how-to-baseline-your-suspension-setup-a-data-driven-approach-to-finding-speed |
| Penske Racing Shocks, processo di messa a punto | azienda | TEC | https://www.penskeshocks.com/master-the-process-of-suspension-tuning-penske-racing-shocks |
| HP Academy, webinar 356 pressione e camber | Andre (HPA) | TEC | https://hpacademy.com/previous-webinars/356-optimising-tyre-pressure-and-camber |
| SCCA, «Change one thing at a time» | Rob Krider, pilota | COACH/AMAT | https://growtiming.scca.com/articles/2020617-change-one-thing-at-a-time |
| Traxion, guida base ACC | Ross McGregor | SIM | https://traxion.gg/assetto-corsa-competizione-basic-setup-guide/ |
| Driver61, guida assetto ACC | redazione | SIM | https://driver61.com/sim-racing/assetto-corsa-competizione-setup-guide/ |
| Driver61, assetto per principianti | «Richard», non tecnico | AMAT | https://driver61.com/uni/understanding-car-setup-for-beginners/ |
| Coach Dave Academy, sotto/sovrasterzo in ACC (con incoerenze interne) | redazione | SIM | https://coachdaveacademy.com/tutorials/how-to-fix-oversteer-and-understeer-in-acc/ |
| Paradigm Shift Racing, diagramma di flusso (solo testo, il diagramma è un'immagine) | Adam Brouillard | COACH/TEC | https://www.paradigmshiftracing.com/racing-basics/race-car-setup-infographic-flowchart |
| PaddockLink, una modifica alla volta | senza autore | ANON | https://paddocklink-docs.pages.dev/lms/race-car-engineering-and-operations/testing-and-development/one-change-at-a-time/ |
| PaddockLink, debrief dopo sessione | senza autore | ANON | https://paddocklink-docs.pages.dev/lms/race-car-engineering-and-operations/debrief-and-continuous-improvement/the-post-session-debrief/ |
| Il Post, l'ingegnere di pista in F1 (ruolo, non procedura) | giornalistico | — | https://www.ilpost.it/2024/06/10/formula-1-ingegnere-di-pista/ |
| Satujoda e Huggins, «Staged GT3 Setup Optimization…», DOI 10.3390/vehicles8070146 (solo riassunto: 134 assetti, BMW Z4 GT3 in Assetto Corsa, pilota IA fisso, −0,390 s) | accademico | — | https://www.citedrive.com/en/discovery/staged-gt3-setup-optimization-with-setup-conditioned-telemetry-response-modeling-in-simulation/ |

### Solo dal riassunto del motore di ricerca (indirette, da riscontrare)

- Speedhunters, «Race Car Set-up Basics Pt 2» (pressioni alte a freddo; niente assetto finché le pressioni non sono stabili): https://www.speedhunters.com/?p=9016
- OptimumG su Racecar Engineering, marzo 2018 (scala −10…+10 legata alla distribuzione antirollio): http://downloads.optimumg.com/Technical_Papers/RCE5.pdf
- Winding Road / Bentley, «Handling Debrief Process»: https://windingroad.com/?p=801
- Winding Road / Jeff Braun (scrivere le previsioni, lavorare il weekend a ritroso): https://windingroad.com/?p=931 e https://windingroad.com/?p=1797
- Suspension Secrets, albero sotto/sovrasterzo: https://suspensionsecrets.co.uk/how-to-remove-oversteer-and-understeer
- MX-5 Club NSW, pirometro: https://nsw.mx5.com.au/motorsport/tyre-technician
- Northstar Motorsports, temperature prima delle pressioni: https://www.northstarmotorsports.com/tech.tips2
- PaddockLink, gomme (attribuzione a Haney): https://paddocklink-docs.pages.dev/lms/vehicle-dynamics-and-setup/alignment-tire-science/tire-temperatures-and-pressures/
- Note di fisica ACC 1.9 (finestra 26,0-27,0): https://coachdaveacademy.com/wp-content/uploads/2023/04/ACCv19-physics_notes-3.pdf
- GO Setups, pressioni GT3 ACC: https://support.gosetups.gg/hc/en-gb/articles/23218772165906-What-Are-the-Optimal-Tyre-Pressures-for-GT3-Cars-in-ACC
- Coach Dave, FAQ 1.8 (bagnato 30 psi): https://coachdaveacademy.com/release-notes/v1-8-acc-update-faq-coach-dave-academy/
- Kaz Technologies, guida agli ammortizzatori di Jim Kasprzak («don't be afraid to make big changes»): https://www.kaztechnologies.com/wp-content/uploads/A-Guide-To-Your-Dampers-Chapter-from-FSAE-Book-by-Jim-Kasprzak-Updated.pdf
- Scheda SAE del libro di Segers: https://saemobilus.sae.org/content/R-408
