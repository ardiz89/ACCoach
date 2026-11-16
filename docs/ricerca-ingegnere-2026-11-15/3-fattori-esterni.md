# Ricerca 3 · Fattori esterni e setup: come li tratta un ingegnere di pista (GT3 reale e ACC)

Data della ricerca: 2026-11-15. Solo fonti web pubbliche.

## Come leggere questo rapporto

Ogni regola porta un'etichetta di provenienza:

- **[KUNOS]** — scritto da Kunos: changelog ufficiali, note di fisica della 1.9, blog di Aristotelis Vasilakos. È la cosa più vicina a «come è fatto il modello».
- **[PIRELLI]** — documento tecnico Pirelli per il GT3 reale.
- **[CDA]** — Coach Dave Academy. Fonte seria della community, a volte con prove misurate, ma **non è Kunos**.
- **[COMMUNITY]** — guide e forum (Solox, Blue Dragon, Trophi, Steam, GTPlanet). Regole pratiche non confermate da Kunos, spesso senza dati di prova.
- **[REALE]** — ingegneri o testate del motorsport reale.
- **[CALCOLO MIO]** — aritmetica mia, non una fonte. Da trattare come ipotesi da misurare.
- **non trovato** — ho cercato e non c'è una fonte citabile. Non ho riempito il buco con un numero.

Limiti della ricerca, detti subito:

1. **Il PDF ufficiale «ACCSharedMemoryDocumentationV1.8.12.pdf» non l'ho potuto aprire**: è un allegato del forum Kunos e si scarica solo da iscritti. Ho verificato che esiste, chi l'ha pubblicato e la versione. I nomi dei campi vengono da PyAccSharedMemory (che dichiara di essere «per lo più una copia» di quel PDF) e, per i campi già mappati, da `src/accoach/telemetry/structs.py` del nostro repository.
2. **Il blog di Aris sulle gomme (overtake.gg), l'intervista Unreal Engine a Kunos, l'articolo di Grassroots Motorsports con Jeff Braun, il post GTPlanet sugli stati pista, boxthislap.org e suspensionsecrets.co.uk hanno risposto 403 o con una verifica anti-bot**: di queste pagine ho solo gli estratti restituiti dal motore di ricerca. Dove uso un estratto lo dico.
3. **Il Server Admin Handbook di Kunos** (sezione meteo) non è stato raggiungibile in testo: sta nella cartella `server` del dedicated server su Steam. È la fonte ufficiale da leggere per la simulazione del meteo e vale la pena aprirla in locale.
4. Nessuna fonte di **Driver61, OptimumG, Racecar Engineering o Michelin** con regole numeriche sui fattori esterni è emersa dalle ricerche: per quei nomi il risultato è «non trovato».

---

## 1. Temperatura dell'aria e dell'asfalto

### Effetto fisico

- L'aria nella gomma si scalda con carcassa, cerchio e freni: la pressione a caldo sale con la temperatura del gas. In ACC la temperatura ambiente sposta quindi la pressione a caldo a parità di pressione a freddo.
- In ACC la temperatura dell'asfalto **non si imposta**: la calcola il gioco da aria, sole, nuvole e ora del giorno. Al sole la pista è molto più calda dell'aria; sotto le nuvole o di notte le due convergono. [COMMUNITY, Solox] Kunos conferma solo che il rapporto è stato rivisto: «Improved ambient vs. track temperature delta» (v1.8). [KUNOS]
- Con il freddo aumentano potenza del motore e carico aerodinamico; ma la temperatura minima non dà per forza il tempo record, perché di notte e al mattino presto ACC simula umidità e rugiada: «we simulate night and early morning humidity and dew». [KUNOS, Aris via DrivingItalia]
- Gomma fredda = nervosa; gomma calda = «gommosa»; surriscaldata = vaga. [KUNOS, Aris]
- Dalla v1.8 le gomme perdono temperatura del nucleo molto più lentamente, e possono servire 3-4 giri per avere letture di pressione affidabili. [KUNOS, Aris via DrivingItalia]

### Finestre di riferimento

| Grandezza | Valore | Chi lo afferma |
|---|---|---|
| Pressione a caldo slick, v1.9 | 26-27 psi, «indicativa»: la finestra è più larga di prima e 26,5 non è più il punto magico | [KUNOS] note di fisica v1.9 |
| Pressione a caldo slick, v1.9 | 26,0-27,0 psi per tutte le auto, GT4 e monomarca comprese | [CDA] FAQ 1.9 |
| Temperatura del nucleo | 70-100 °C; stabile intorno a 80-90 °C | [KUNOS] note v1.9 |
| Temperatura superficiale (flash) | da 50 °C in rettilineo a 120 °C e oltre in curva: è normale | [KUNOS] note v1.9 |
| Differenza esterno-interno | non più di 15 °C | [KUNOS] note v1.9 |
| Pressione minima | 20,3 psi «as per Pirelli document request» | [KUNOS] changelog 1.0.8 |
| Pressione minima GT3 reale | 1,4 bar / 20,3 psi; obiettivo a caldo 2,0 bar / 29 psi | [PIRELLI] booklet GT World Challenge Asia GT3 2019 |
| Camber statico massimo reale | −3,5° anteriore, −3,0° posteriore | [PIRELLI] idem |
| Slick preriscaldate | 70 °C qualunque sia la temperatura ambiente | [KUNOS] changelog 1.0.8 |
| Da freddo a caldo | «usually 2psi less than the hot pressure you want» | [KUNOS] changelog 1.0.8 (attenzione: è del 2019, prima dei modelli gomma 1.8 e 1.9) |
| Costo di 1 psi fuori finestra | 5-6 decimi al giro | [CDA], affermato senza dati; precedente alla finestra larga della 1.9 |

Nota sul reale: l'obiettivo Pirelli a caldo (29 psi) è diverso dalla finestra di ACC (26-27 psi). **Le pressioni reali non si trasferiscono su ACC**: si trasferisce il metodo («imposta il freddo in modo da arrivare all'obiettivo a caldo»), che è testuale nel documento Pirelli.

### Regole «psi per grado»

| Regola | Fonte | Stato |
|---|---|---|
| 0,1 psi di pressione a freddo per ogni 1 °C di aria (più caldo → togli, più freddo → aggiungi) | [CDA] guida pressioni; [COMMUNITY] Trophi, Solox | **Regola della community, non confermata da Kunos.** Solox stesso la chiama «a first guess and nothing more» |
| 0,1 psi ogni 1,5-2 °C | [COMMUNITY] estratto da forum | non confermata |
| +5 °C pista → +0,3 psi a caldo; +10 °C → +0,7 psi | [COMMUNITY] Blue Dragon Racing | non confermata; la stessa pagina scrive anche «0,25 psi ogni 10 °C», quindi **si contraddice da sola** |
| 1 psi per 1 °C | [COMMUNITY] simracingsetup.com | quasi certamente un refuso per 0,1; da scartare |
| «1 psi per 10 degrees of ambient temp» | [REALE] Jeff Braun, ingegnere IMSA, su Grassroots Motorsports | solo estratto di ricerca (pagina 403). L'unità non è verificata: testata americana, quindi verosimilmente °F, cioè circa 0,18 psi/°C |
| circa 0,11 psi per °C di temperatura **del gas** | [CALCOLO MIO] legge dei gas: (27 + 14,7) psi assoluti / 363 K | coerente come ordine di grandezza con la regola 0,1; ma lega la pressione alla temperatura del gas, non a quella dell'aria esterna |

Kunos non ha pubblicato, in nessuna delle fonti che ho raggiunto, una regola «X psi ogni Y °C». **Regola di Aris: non trovata.**

### Freni e prese d'aria

- La presa freno influenza la temperatura del disco e l'efficienza della frenata, **ma anche il cerchio e l'aria dentro la gomma**. Scala 0-6: 0 è chiusa e porta al fading molto in fretta, oltre 1000 °C; 6 è tutta aperta e tiene i freni molto freddi. Un valore basso non solo scalda di più ma non raffredda in rettilineo. Obiettivo: indicatore dei freni anteriori verde o appena giallo alla fine della staccata, posteriori verdi. [KUNOS] changelog 0.7.0
- Dalla v1.8 l'influenza delle prese sul calore delle gomme è minore di prima, ma resta: «Aggressive drivers will need more open ducts to somewhat limit the tyres overheating». [KUNOS, Aris]
- Temperatura ottimale freni: 600-650 °C davanti, 450 °C dietro. [CDA] guida setup. Non confermata da Kunos.
- Più presa aperta = più resistenza e meno velocità massima; meno presa sulle piste veloci, più presa sulle piste che lavorano i freni. [CDA]
- **Quanti psi vale uno scatto di presa: non trovato.**

### Motore

- Freddo = più potenza e più carico. [KUNOS, Aris] Numeri: **non trovati**.

### Regole operative

- **Se** l'aria cambia di N °C rispetto alle condizioni in cui il setup è stato costruito, **allora** proponi circa −0,1·N psi a freddo su tutte e quattro come prima ipotesi [COMMUNITY], e verifica sulle pressioni a caldo dopo almeno 3 giri (3-4 secondo Aris).
- **Se** le pressioni a caldo misurate sono sotto 26 psi su pista fredda, **allora** alza il freddo; sopra 27 psi su pista calda, abbassa il freddo e apri la presa freno di uno scatto. [COMMUNITY, Solox]
- **Se** la pista si raffredderà durante lo stint (verso sera), **allora** parti un po' più alto; se si scalderà (dal mattino a mezzogiorno), parti un po' più basso; correggi al pit stop. [COMMUNITY, Solox] Entità: non trovata.
- **Se** una gomma resta sotto 80 °C dopo 4 giri, la pressione è troppo alta; oltre 95 °C è troppo bassa. [COMMUNITY, Blue Dragon] Coerente con Aris («lower pressure tyres generate more heat»), ma le soglie non sono di Kunos.
- I setup di Coach Dave per la 1.9 sono costruiti a **24 °C aria / 33 °C pista, sole, ore 13**; quelli da bagnato a 18 °C aria / 24 °C pista. [CDA] Utile come ancora: un setup scaricato ha una temperatura di nascita, e la correzione si calcola da lì.

---

## 2. Evoluzione della pista

### Come è modellata in ACC

- Stati esposti dal gioco: Green, Fast, Optimum (asciutto); Greasy, Damp, Wet, Flooded (bagnato). Corrispondono all'enum `ACC_TRACK_GRIP_STATUS` 0..6. [PyAccSharedMemory, derivato dal PDF Kunos]
- Green, Fast e Optimum sono **fasce, non valori puntuali**: due sessioni entrambe «Fast» possono dare tempi diversi. [COMMUNITY, GTPlanet, da estratto]
- Green: poca gomma, grip basso ma uniforme. Optimum: massimo grip in traiettoria, fuori traiettoria ci sono i detriti di gomma ed è molto più scivoloso. [COMMUNITY, GTPlanet]
- La differenza di grip fra dentro e fuori la traiettoria esiste ancora ma dalla 1.8 è meno marcata: «The difference in grip is still present but less evident». [KUNOS, Aris] Changelog: «Improved track grip simulation on and off the racing line». [KUNOS] v1.8
- Con la pioggia la pista gommata diventa la più insidiosa: lo stato Greasy è la traiettoria gommata che si bagna; una pista green bagnata ha più «morso». [COMMUNITY, GTPlanet]
- Pioggia prolungata lava via la gomma; una linea asciutta compare dove passano le auto. [COMMUNITY, Steam: solo utenti, nessuno di Kunos]
- Nel weekend: venerdì grip basso, sabato già alto, domenica di solito optimum. [COMMUNITY, GTPlanet]
- I tempi di riferimento di Coach Dave sono fatti in Hot Lap, che usa pista Optimum. [CDA]

### Quanto tempo o quanti giri servono, e quanto vale in tempo sul giro

- **In ACC: non trovato.** Nessuna fonte, né Kunos né community, dà un numero di giri o di minuti per passare da Green a Fast a Optimum, né uno scarto in secondi fra gli stati. L'unico dato trovato è un'impressione su Steam («la green è un po' più lenta»).
- Nel reale (Formula 1, non GT3): miglioramento medio sull'asciutto fra le prime libere e la pole circa 2,5 s; su un circuito nuovo 5,3 s (Corea 2010); sui cittadini circa 5,5 %; una pioggia notturna riporta la pista quasi a green e costa fino a 2 s. I settori con più curve migliorano di più (3,2 % contro 6,2-6,7 %). [REALE, Nextgen-Auto 2011: analisi dell'autore, senza fonti esterne]
- **Valore per GT3: non trovato.**

### Come non confonderla con una modifica di setup

Nessuna fonte di ingegnere reale descrive il metodo in modo citabile (**non trovato**). Quello che è emerso:

- Un approccio statistico documentato in un progetto open source su dati F1: usare tutto il campo come sensore, tenere solo i giri lanciati in bandiera verde entro il 107 % del migliore, e fare la regressione del tempo sul giro contro il tempo trascorso nella sessione. [COMMUNITY, progetto GitHub, non il metodo di una squadra]
- La letteratura sulla strategia corregge il tempo sul giro per l'effetto benzina prima di attribuire il resto alle gomme. [REALE, articolo accademico arXiv, da estratto]

Regole che ne derivo per l'algoritmo [CALCOLO MIO, ipotesi di progetto, non fonti]:

- **Se** `trackGripStatus` è cambiato fra il giro di base e il giro di prova, **allora** il confronto non è valido per giudicare una modifica: va segnalato e non attribuito.
- **Se** lo stato è lo stesso ma siamo a inizio sessione su pista Green o Fast, **allora** un miglioramento va attribuito alla modifica solo se supera la deriva misurata sui giri di controllo precedenti alla modifica.
- Lo stato a parole non basta, perché è una fascia: servono comunque i giri di controllo.
- Per separare gli effetti servono, in quest'ordine: correzione benzina (sezione 4), stesso stato pista, stessa fascia di temperatura asfalto, gomme con usura paragonabile.

---

## 3. Meteo: umido, bagnato, pista che si asciuga, pioggia in arrivo

### Effetto fisico e modello di ACC

- La profondità del velo d'acqua influenza l'aerodinamica: «Wet asphalt water film depth now influences aerodynamics». E la nota operativa: può servire alzare l'altezza da terra **fino a 4-5 mm** per ritrovare lo stesso equilibrio di splitter e diffusore. [KUNOS] changelog 1.0.8. È l'unico numero ufficiale di setup da bagnato che ho trovato.
- «Slicks are death traps when wet». L'aquaplaning è forte ad alta velocità e con grandi angoli di deriva anche con le rain. La finestra di temperatura delle rain è più larga, ma non sempre più prestazionale. [KUNOS, Aris]
- v1.2: nuovo modello delle rain, meno grip di adesione, tempi più lenti, più controllo in scivolata; aggiunto un livello massimo di TC per le condizioni di temporale su tutte le auto. [KUNOS]
- Il meteo evolve su tempi realistici e usa il tempo di gioco: il moltiplicatore del tempo accelera le transizioni. Il cielo nuvoloso ha molta più probabilità di dare precipitazioni. Esiste un widget con previsione e stato del grip. [KUNOS] changelog 0.7.0
- v1.8: la variabilità alta produce cicli meteo più ampi e meno prevedibili; quella bassa cicli più regolari. [KUNOS]
- v1.8.5: rivista la velocità di formazione delle pozzanghere. [KUNOS, da estratto]
- Le rain su pista che si asciuga si surriscaldano in pochi giri, diventano molli e vaghe e le pressioni salgono in fretta; passare sulle zone bagnate in rettilineo aiuta a raffreddarle. Le pozzanghere sono le ultime ad asciugarsi. [COMMUNITY]
- Il modello delle rain non è cambiato con la 1.9. [COMMUNITY]

### Finestre di pressione da bagnato in ACC

| Finestra a caldo | Fonte | Nota |
|---|---|---|
| 29,5-31,0 psi (rain DHE 2020 e DHD2 2019) | [CDA] tabella della guida pressioni | |
| 29,5-30,5 psi | [CDA] FAQ della stessa guida e pagine prodotto | la stessa pagina dà due finestre diverse |
| 29,5-30 psi | [CDA] diagramma «Wet Setup Workflow» | |
| 30,0-31,0 psi | [CDA] guida setup; [COMMUNITY] Solox | |
| **35 psi, il massimo, sempre** | [CDA] articolo «Wet tyre pressures: myth or meta» | prova misurata, vedi sotto |
| Finestra da Kunos | **non trovata** | |

### La prova di Coach Dave a 35 psi [CDA, misurata]

Due piloti, un ingegnere, circa 1 GB di dati MoTeC, più piste, cinque stati. Guadagno a 35 psi rispetto a 30 psi:

| Condizione | Guadagno sul giro |
|---|---|
| Flooded, 70 % di bagnato, Silverstone | Ferrari 296 −0,76 s; Porsche −0,47 s |
| Wet medio, 40 %, Silverstone | Ferrari −0,73 s; Porsche −0,31 s; Lamborghini −1,01 s |
| Damp, 28-15 %, Hungaroring | Ferrari −1,60 s; Porsche −1,29 s; Lamborghini −1,72 s; BMW −0,96 s |

Sul damp anche il degrado in 10 giri si dimezza (per esempio Lamborghini 3 s contro 0,9 s). Conclusione degli autori: «Right now there is no downside to running maximum tyre pressures», ignorando il widget del gioco. Il meccanismo indicato è il controllo della temperatura. **Non confermato da Kunos**, e in contrasto con la finestra indicata dal gioco: vedi «Punti controversi».

### Quale setup per quale stato [CDA]

| Stato pista | Setup | Gomme |
|---|---|---|
| Green, Greasy, Damp | setup da asciutto di base | slick |
| Wet con pioggia assente o leggera | piccoli ritocchi al setup da asciutto | rain |
| Wet con pioggia media o più forte | setup da bagnato | rain |
| Flooded, acqua stagnante | setup da bagnato adattato: altezze e molle | rain |

Variante [COMMUNITY, Solox]: Damp è il punto di decisione, slick se la pioggia sta smettendo e rain se continua. Le due fonti non coincidono sul Damp.

### Cosa cambia e in che ordine

Diagramma «Wet Setup Workflow» di Coach Dave [CDA], dal setup da asciutto. **Primo blocco, tutto insieme:**

- Gomme: meno camber davanti e dietro; pressioni a caldo 29,5-30 psi.
- Strategia: mescola delle pastiglie 3.
- Grip meccanico: ripartizione più indietro; molle più morbide davanti e dietro; barre più morbide davanti e dietro; meno pressione dei freni.
- Aerodinamica: alzare l'altezza anteriore; più ala posteriore; chiudere le prese freno.
- Elettronica: più TC e ABS.

**Poi un giro di prova, e si corregge il bilanciamento:**

- Sottosterzo → meno precarico del differenziale; alzare l'altezza posteriore; ammorbidire la compressione anteriore.
- Sovrasterzo → più precarico; abbassare l'altezza posteriore; ammorbidire la compressione posteriore; più convergenza posteriore.

Entità dei ritocchi [COMMUNITY, Solox, «il setup che userei io», senza dati]: barre 2-3 scatti più morbide; altezze «qualche millimetro» in più; ala +2 scatti o più; TC1 +2 o +3; ABS +2 o +3; ripartizione 1-2 % indietro; prese freno 1-2 scatti più chiuse; pastiglie 2 o 3; mappa da bagnato se c'è.

Altri dati [CDA, note dei setup wet]: TC 6/7 come ordine di grandezza sulla Ferrari 296 sul bagnato; TC1 5 sulla McLaren 720S Evo come base; i setup «medium wet» sono fatti con pioggia al 40 %, gli «heavy wet» al 60 %. Non tutte le auto seguono la regola generale: la Porsche 992 da bagnato pesante ha le barre **più rigide** e il posteriore più basso; la Bentley resta al massimo camber negativo.

Mappe motore: ogni auto ha mappe da asciutto e da bagnato, queste ultime con risposta del gas più graduale. [CDA]

### Regole operative

- **Se** `rainIntensityIn10min` o `rainIntensityIn30min` è maggiore di `rainIntensity`, **allora** avvisa prima: la decisione sulle gomme si prende al pit stop, non in pista.
- **Se** lo stato è Greasy o Damp con le slick, **allora** niente modifiche di setup: l'obiettivo è tenere temperatura nelle slick. [CDA] Su pista fredda e umida le slick vogliono più pressione a freddo. [COMMUNITY]
- **Se** lo stato è Wet con pioggia almeno media, **allora** proponi il blocco iniziale completo; **se** è Flooded, aggiungi altezze (fino a 4-5 mm [KUNOS]) e molle.
- **Se** con le rain la pista si asciuga (stato che scende verso Damp, temperature e pressioni delle rain in salita rapida), **allora** segnala il surriscaldamento e l'avvicinarsi del cambio gomme, e suggerisci di cercare le zone bagnate.
- **Dal volante, in pista, sono regolabili solo TC, ABS, ripartizione e mappa**: tutto il resto è lavoro da box. È il vincolo già scritto in ENGINEER.md.
- Ordine dei cambi nel motorsport reale (fonte di ingegnere GT): **non trovato**. Un forum di monoposto cita altezza più alta per non galleggiare e meno camber per far drenare gli intagli [COMMUNITY, F1technical, da estratto].

---

## 4. Carico di benzina

### Effetto sul tempo sul giro

| Valore | Fonte | Vale per |
|---|---|---|
| circa 0,03 s per kg | [REALE] un ingegnere su X, da estratto | categoria non dichiarata, contesto F1 |
| 0,025-0,040 s per kg «nella maggior parte delle categorie in circuito» | [COMMUNITY] blog di analisi | generico |
| 0,3-0,4 s per 10 kg; 0,32 s per 10 kg (simulazione Prost 2001, Barcellona) | [COMMUNITY] F1technical | F1 |
| 0,22-0,29 s per 10 kg | [COMMUNITY] blog di strategia F1 | F1 2013 |
| 0,405 s per 10 kg | [REALE] PMW Magazine, simulazione sul giro, da estratto | Hypercar a Le Mans (giro lungo) |
| 0,2 s per 10 kg | [COMMUNITY] blog sulla strategia, da estratto | non dichiarato |
| 0,15 s per 10 kg | [COMMUNITY] simracingsetup.com, come **esempio** del BoP di Low Fuel Motorsport | ACC, valore illustrativo, non ufficiale e diverso per ogni pista |
| 0,1 s per 10 kg | [COMMUNITY] un utente su Rennlist | aneddoto |
| **GT3 reale, valore di ingegnere** | **non trovato** | |
| **ACC, secondi per litro misurati** | **non trovato** | |

Conversione in litri [CALCOLO MIO]: con la benzina a circa 0,74-0,75 kg/l (densità che **non ho verificato per ACC**), l'esempio da 0,15 s per 10 kg diventa circa 0,011 s per litro, cioè più o meno 1,1 s fra 110 litri e serbatoio vuoto. È un ordine di grandezza, non un dato.

Conclusione onesta: la sensibilità dipende da pista e auto, e **va misurata sui giri del pilota** (tempo sul giro contro `fuel`, sui giri puliti di uno stint), non presa da una tabella. Il nostro registratore ha già `fuel_start` e `fuel_end`.

### Bilanciamento, altezze, pressioni

- Più benzina rende l'auto più stabile e «piantata»; con meno benzina diventa più diretta e consuma meno le gomme. Un'auto pesante può consumarle di più. [CDA]
- Le altezze possono richiedere una correzione in base al carico. [CDA] Quanti millimetri: **non trovato**.
- La ripartizione si ritocca nello stint per tenere costante il bilanciamento al variare di benzina, pista e gomme. [CDA] Quanto: **non trovato**.
- Effetto della benzina sulle pressioni: **non trovato**.
- Dove sta il serbatoio e quindi come si sposta il bilanciamento auto per auto: **non trovato**.

### Qualifica e gara

- Qualifica: mappa di massima potenza, molto camber negativo; gara: meno camber per l'usura, mappe meno aggressive in endurance per il consumo. [CDA; DrivingItalia]
- Criterio di prova [CDA]: un setup da gara deve ripetere lo stesso tempo per 30 minuti; uno da qualifica dà un giro che dopo tre giri non si ripete più.
- Pressioni [COMMUNITY, Blue Dragon]: qualifica +0,3 o +0,4 psi a freddo per arrivare in finestra in due giri; gara −0,3 a −0,5 psi per lasciare margine alla crescita. Attenzione: questa fonte usa come finestra 27,3-27,8 psi, che è quella **vecchia** (prima della 1.9).
- Formula del carburante [CDA]: litri = ((minuti × 60) / tempo sul giro) × litri per giro + 2 × litri per giro.

### Regole operative

- **Se** si confrontano due giri con benzina diversa, **allora** correggi il tempo per la benzina prima di giudicare una modifica, con il coefficiente misurato sul pilota. Senza correzione, il calo di tempo durante lo stint viene scambiato per un miglioramento del setup.
- **Se** non c'è ancora un coefficiente misurato, **allora** dichiara il confronto «non corretto per la benzina» invece di usare un numero preso da una tabella.

---

## 5. Usura e degrado delle gomme nello stint

### Modello ACC

- Battistrada nuovo: 3 mm. Sotto 1,5 mm squadre e Pirelli considerano la gomma molto usurata. [KUNOS, blog di Aris sulle gomme, **da estratto**: il blog è vecchio e precede i modelli 1.8 e 1.9]
- Il grip cala lentamente e in modo regolare con il battistrada; «ben sotto i 2 mm» l'auto scivola di più e la scivolata accelera l'usura. Le gomme vogliono 1-2 giri di rodaggio prima del picco. [COMMUNITY, Solox, affermato senza dati]
- Esempio (ipotetico, aritmetica dell'autore): circa 0,04 mm al giro dietro e 0,03 davanti; uno stint a pieno carico, circa un'ora, è alla portata «se le tratti bene». [COMMUNITY, Solox]
- Usura e temperatura esterno/centro/interno dipendono dal camber (v1.8). Molto camber negativo consuma l'interno sulla distanza. [KUNOS]
- Il TC moderno controlla meglio lo slittamento ma può portare a usura eccessiva; correre senza TC si può, non è per forza più veloce, e consuma di più sulla distanza. [KUNOS, note 1.9; DrivingItalia]
- Fasi dello stint [COMMUNITY, Blue Dragon, senza dati]: giri 1-8 le pressioni si stabilizzano; 8-25 oscillano entro ±0,2 psi; oltre il 25° la pressione sale di più per giro.
- **Quanto tempo sul giro costa un millimetro: non trovato.**

### Come riconoscerlo dai dati

| Segnale | Lettura | Fonte |
|---|---|---|
| Usura maggiore davanti | sottosterzo, troppo angolo volante a centro curva | [COMMUNITY] Solox |
| Usura maggiore dietro | pattinamento in uscita | [COMMUNITY] Solox |
| Bordo interno | troppo camber negativo | [KUNOS] Aris; [COMMUNITY] |
| Bordo esterno | troppo poco camber | [COMMUNITY] |
| Centro | pressione alta | [COMMUNITY] |
| Temperatura sopra 90 °C circa e pressione sopra 27 psi | surriscaldamento: arriva in pochi giri e **rientra** se si alza il piede | [COMMUNITY] Solox |
| Usura | sale piano e **non rientra** | [COMMUNITY] Solox |

La distinzione che serve all'algoritmo è l'ultima: **il surriscaldamento è reversibile, l'usura no**. Un calo di ritmo che rientra dopo un giro tranquillo non è degrado.

Attenzione al dato: nel thread ufficiale della shared memory, Ensi Ferrum elenca `tyreWear[4]` e `tyreTemp[4]` fra i campi **non usati da ACC**. L'usura quindi non si legge in tempo reale da lì (coerente con quanto già misurato da noi il 2026-11-01: «usura morta»).

### Cosa si regola dal volante

- TC1 su di uno scatto se l'asse posteriore si consuma. [COMMUNITY, Solox]
- TC1 e TC2 entro ±1 fra loro, i più alti possibile prima che il tempo ne soffra. [CDA]
- ABS: partire alto e scendere finché l'auto non diventa instabile. [CDA]
- Ripartizione: più avanti = stabilità in frenata e sottosterzo in ingresso; più indietro = il contrario. Si ritocca nello stint. [CDA]
- Mappa: più bassa di numero = più potenza e più consumo (in generale; dipende dall'auto). [CDA]
- **Di quanti scatti e a che punto dello stint, da ingegnere reale: non trovato.**

### Regole operative

- **Se** il tempo cala nello stint, **allora** prima sottrai la benzina (che fa andare più forte) e controlla stato pista e temperatura; solo quello che resta è gomma.
- **Se** temperatura e pressione di un asse salgono insieme e il ritmo rientra dopo un giro di gestione, **allora** è surriscaldamento: il consiglio è di guida o di TC, non di setup.
- **Se** il calo è monotono e non rientra, **allora** è degrado: i ritocchi possibili in pista sono TC, ABS, ripartizione; quelli di setup (camber, convergenza, barre dell'asse che si consuma) vanno al prossimo box.

---

## 6. Ora del giorno, notte, vento, altitudine

| Fattore | In ACC | Fonte |
|---|---|---|
| Altitudine | Simulata su tutte le piste dalla v1.2: aria meno densa = meno potenza, meno carico ma anche meno resistenza; anche il riscaldamento di gomme e freni ne è leggermente influenzato | [KUNOS] changelog 1.2 |
| Notte e mattino | Umidità e rugiada simulate; foschia notturna a certe temperature; la temperatura più bassa non dà per forza il tempo migliore | [KUNOS] Aris, changelog 1.8 |
| Ora del giorno | La temperatura asfalto deriva da aria, sole, nuvole, ora; cala in fretta con nuvole o tramonto, quindi la sera le pressioni scendono | [COMMUNITY] Solox |
| Meteo e densità | Il modello cambia nuvolosità, pioggia, velocità e direzione del vento; il meteo influenza densità dell'aria e temperature di aria e pista; ne risentono frenata, grip, coppia e carico | [KUNOS] intervista Unreal Engine 2019, **da estratto** |
| Vento | Esposto nella shared memory (`windSpeed` in m/s, `windDirection` in radianti). **Quanto pesi sulla fisica e sul tempo: non trovato.** Nei changelog raggiunti non c'è una riga sul vento, a parte l'audio | — |
| Nel reale | Con le nuvole l'aria si raffredda subito, la pista più lentamente (Mercedes F1); gli ingegneri IndyCar ritoccano le pressioni di partenza con la temperatura pista, e anteriore e posteriore reagiscono in modo diverso, spostando il bilanciamento (Racer) | [REALE], da estratti |

Regole operative:

- **Se** `clock` indica una sessione che attraversa il tramonto o l'alba, **allora** aspettati una deriva di pressioni e tempi che non dipende dal setup, e non confrontare giri di fasce orarie diverse.
- **Se** il vento cambia fra due run, per ora è un fattore da **registrare**, non da correggere: manca un modello citabile.
- L'altitudine è una costante della pista: entra nel punto di partenza del setup, non nell'adattamento durante la sessione.

---

## 7. Tipo di circuito

- Curve veloci e ad alto carico chiedono più pressione, per sostegno e precisione; curve lente e a basso carico chiedono meno pressione, per flessione, rotazione e trazione. Si possono differenziare gli assi: meno pressione dietro = fianchi più morbidi = più rotazione di imbardata; bastano 0,5° in più per cambiare l'auto. [KUNOS] note 1.9
- Tamponi di fine corsa: dalla 1.9 corsa massima 20-30 mm, poi la sospensione si ferma e il telaio flette. In generale il grip meccanico vale più della resistenza guadagnata correndo bassissimi, **«tranne forse su piste specifiche come Monza»**. Segnali di compromesso sbagliato: saltellamenti laterali in curva, reazioni imprevedibili sui cordoli. [KUNOS] note 1.9
- Cordoli a gradino con gomma fredda e pressione bassa possono far perdere pressione o forare; sopra 26 psi si è relativamente al sicuro. [KUNOS] changelog 0.7.0
- Meno camber e convergenza danno stabilità sulle irregolarità longitudinali (tramlining), a spese del grip laterale. [KUNOS, Aris]
- Molle più rigide su piste lisce, più morbide su piste sconnesse; le piste vecchie sono più sconnesse. Zolder e Bathurst citate come sconnesse. [CDA]
- Prese freno più chiuse sulle piste veloci, più aperte su quelle che lavorano i freni. [CDA]
- Piste ad alta quota (per esempio Spa nella nota di Kunos): tempi leggermente diversi dopo l'introduzione dell'altitudine. [KUNOS] 1.2
- **Asfalto abrasivo, cioè abrasività diversa pista per pista in ACC: non trovato.** Nessuna fonte dice che ACC la modelli in modo distinto.
- **Tabella «livello di carico per pista» da fonte citabile: non trovata.**

Regola operativa: il tipo di circuito determina il **punto di partenza** (ala, altezze, rigidezze, prese freno), non l'adattamento in sessione. Per l'algoritmo è un attributo statico della pista.

---

## Campi della shared memory di ACC utili

Fonte dei nomi: PyAccSharedMemory (snake_case, copia dichiarata del PDF Kunos). La colonna «nome nel repo» riporta il nome già presente in `src/accoach/telemetry/structs.py`; dove è vuota, **il nome camelCase originale va verificato sul PDF**: non l'ho letto.

### Physics (`acpmf_physics`)

| Campo (PyAcc) | Nome nel repo | Tipo e unità | A cosa serve |
|---|---|---|---|
| `air_temp` | `airTemp` | float, °C | correzione pressioni; ancora delle condizioni |
| `road_temp` | `roadTemp` | float, °C | fascia di confronto fra giri; deriva nello stint |
| `wheel_pressure` | `wheelsPressure` | 4 float, psi | pressioni a caldo contro finestra |
| `tyre_core_temp` | `tyreCoreTemperature` | 4 float, °C | finestra 70-100 °C; surriscaldamento |
| `brake_temp` | `brakeTemp` | 4 float, °C | prese freno |
| `fuel` | `fuel` | float, litri | correzione benzina |
| `tc`, `abs` | `tc`, `abs` | float | **intervento** in atto, non il livello |
| `brake_bias` | `brakeBias` | float | ripartizione |
| `water_temp` | — | float | raffreddamento motore |
| `pad_life`, `disc_life` | — | 4 float, mm (pastiglia nuova 29 mm, disco 32 mm) | usura freni nello stint |
| `front_brake_compound`, `rear_brake_compound` | — | int | mescola pastiglie |
| `suspension_travel` | `suspensionTravel` | 4 float | fine corsa sui tamponi |
| `kerb_vibration` | — | float | uso dei cordoli |
| `tyreWear`, `tyreTempI/M/O`, `rideHeight` | presenti nel repo | — | **dichiarati non usati da ACC** nel thread ufficiale (`tyreWear[4]`, `tyreTemp[4]`, `rideHeight[2]`, `camberRAD[4]`) |

### Graphics (`acpmf_graphics`)

| Campo (PyAcc) | Nome nel repo | Tipo | A cosa serve |
|---|---|---|---|
| `track_grip_status` | (citato in `diagnostics.py`) | enum 0..6: Green, Fast, Optimum, Greasy, Damp, Wet, Flooded | stato pista; validità dei confronti |
| `track_status` | — | stringa con gli stessi nomi | idem, in testo |
| `rain_intensity` | (citato in `diagnostics.py`) | enum 0..5: No rain, Drizzle, Light, Medium, Heavy, Thunderstorm | pioggia adesso |
| `rain_intensity_in_10min` | — | enum | pioggia in arrivo |
| `rain_intensity_in_30min` | — | enum | pioggia in arrivo |
| `wind_speed` | `windSpeed` | float, m/s | da registrare |
| `wind_direction` | `windDirection` | float, radianti | da registrare |
| `clock` | — | int, secondi dell'ora del giorno | fascia oraria, notte |
| `rain_tyres` | — | bool | rain montate |
| `tyre_compound` | `tyreCompound` | stringa | mescola |
| `tc_level`, `tc_cut_level`, `abs_level`, `engine_map` | `TC`, `TCCut`, `ABS`, `EngineMap` | int | livelli impostati dal volante |
| `fuel_per_lap`, `used_fuel`, `fuel_estimated_laps` | — | float | consumo e autonomia |
| `mfd_tyre_pressure`, `mfd_fuel_to_add`, `mfd_tyre_set` | — | 4 float, float, int | cosa è impostato per il prossimo pit stop |
| `current_tyre_set`, `strategy_tyre_set` | — | int | treno montato (da noi già segnalato come sospetto) |
| `exhaust_temp` | — | float | motore |
| `session_time_left`, `is_valid_lap`, `is_in_pit`, `is_in_pit_lane` | `sessionTimeLeft`, `isValidLap`, … | — | contesto |
| `surfaceGrip` | `surfaceGrip` | float | **sempre 0 su ACC** (già verificato da noi: lo stato passa per `trackGripStatus`) |

### Static (`acpmf_static`)

| Campo | Nome nel repo | A cosa serve |
|---|---|---|
| `max_fuel` | `maxFuel` | capienza del serbatoio |
| `aid_fuel_rate`, `aid_tyre_rate` | `aidFuelRate`, `aidTireRate` | moltiplicatori di consumo e usura della sessione: cambiano tutte le stime |
| `track`, `car_model` | `track`, … | attributi statici della pista |
| `dry_tyres_name`, `wet_tyres_name` | — | nomi delle mescole |

### Cosa la shared memory NON dà

- La percentuale di bagnato e il livello dell'acqua stagnante: solo lo stato a fasce.
- Il grip come numero: solo la fascia.
- L'usura del battistrada in tempo reale.
- Nuvolosità e umidità.
- Altitudine e densità dell'aria.

Gli enum sono a gradini: un software vede «Fast», non «Fast quasi Optimum».

---

## Punti controversi

1. **Pressioni da bagnato: 30-31 psi o 35 psi.** Il gioco, le guide e la stessa Coach Dave nelle pagine più vecchie indicano 29,5-31. Una prova misurata di Coach Dave dice che 35 psi, il massimo, è sempre più veloce (da 0,3 a 1,7 s al giro) e degrada meno. Non c'è conferma di Kunos, non ho la data dell'articolo né la versione di ACC su cui è stata fatta la prova, e una patch potrebbe averla superata. Un algoritmo che consiglia 35 psi contraddice il widget che il pilota ha davanti: va deciso col pilota, o misurato.
2. **La regola 0,1 psi per °C.** Ripetuta ovunque, mai attribuita a Kunos. Le fonti divergono su aria contro asfalto (un commento Reddit sostiene che conti solo l'aria; Blue Dragon ragiona sull'asfalto) e sull'entità (0,1 per °C; 0,1 ogni 1,5-2 °C; 0,03-0,07 per °C). Va usata come prima ipotesi e corretta sulle pressioni a caldo misurate.
3. **Finestra a caldo sull'asciutto.** 26-27 (Kunos 1.9, «indicativa»); 26-27,2 e 26,5-27,5 nella stessa pagina di Coach Dave; 27,3-27,8 nelle fonti vecchie. Molte guide ancora in rete parlano della gomma **prima** della 1.9. Regola: conta la versione; e dalla 1.9 la finestra è larga e la pressione è anche una leva di bilanciamento, non solo un bersaglio.
4. **Damp: slick o rain.** Coach Dave mette Damp con le slick; Solox lo considera il punto di decisione.
5. **Barre da bagnato.** La regola generale è ammorbidire; i setup di Coach Dave per alcune auto (Porsche 992) le irrigidiscono. Il bagnato è specifico per auto.
6. **La gommatura è dinamica o predeterminata.** Su Steam si legge che la linea gommata è predeterminata e anche che cresce col passaggio: nessuna voce di Kunos. Non trovata una descrizione ufficiale del modello.
7. **Costo di 1 psi fuori finestra: 5-6 decimi** [CDA]. È precedente alla finestra larga della 1.9, e Kunos dice che ora la pressione è una leva: il numero è probabilmente superato.
8. **Prese freno e gomme.** Prima della 1.8 erano la leva principale per scaldare le gomme; Aris dice che dalla 1.8 l'influenza è ridotta. Le guide più vecchie la sopravvalutano.
9. **Effetto benzina.** Fra 0,1 e 0,4 s per 10 kg secondo fonte e categoria; nessun valore per il GT3. Non va scritto un coefficiente fisso nel codice.

---

## Cosa manca, in ordine di utilità

1. Leggere il PDF ufficiale della shared memory (serve l'accesso al forum Kunos) per i nomi esatti e gli offset dei campi dopo `isValidLap`.
2. Leggere il Server Admin Handbook nella cartella del dedicated server per la sezione meteo.
3. Misurare in pista, perché nessuna fonte li dà: psi a caldo per °C di aria su un'auto; psi per scatto di presa freno; secondi per litro; scarto fra Green e Optimum; effetto del vento.
4. Verificare la prova dei 35 psi sulla versione installata.

---

## Fonti

### Kunos (ufficiali o testo di Kunos riportato da terzi)

- Thread ufficiale «ACC Shared Memory Documentation» (Fernando Barbarossa, 28/08/2019; allegato `ACCSharedMemoryDocumentationV1.8.12.pdf`; elenco di Ensi Ferrum dei campi non usati): https://www.assettocorsa.net/forum/index.php?threads/acc-shared-memory-documentation.59965/
- «Version 1.9 – Physics notes» (PDF): https://assettocorsa.gg/wp-content/uploads/ACCv19-physics_notes.pdf
- Changelog 1.0.8 (velo d'acqua e 4-5 mm, minimo 20,3 psi, slick a 70 °C): https://assettocorsa.gg/1-0-8-is-out-now-on-steam/
- Changelog 1.2 (altitudine, nuovo modello rain): https://www.bsimracing.com/assetto-corsa-competizione-update-v-1-2-deployed/
- Changelog 0.7.0 (prese freno 0-6, cordoli e pressione, meteo dinamico): https://www.bsimracing.com/assetto-corsa-competizione-release-7-deployed/
- Changelog 1.8 (delta aria/pista, prese freno, grip dentro e fuori traiettoria, foschia): https://assettocorsa.gg/assetto-corsa-competizione-pc-update-v-1-8-out-now/
- Aris sulla 1.8, citazioni dal blog ufficiale riportate da DrivingItalia: https://www.drivingitalia.net/home-page/software/assetto-corsa-competizione-consigli-e-spiegazioni-da-aris-su-assetto-e-stile-di-guida-dopo-lupdate-18-r27714/
- Blog di Aris sulle gomme (403, solo estratto): https://www.overtake.gg/threads/assetto-corsa-competizione-blog-post-2-tyres.159095/
- Intervista Unreal Engine a Kunos, 2019 (403, solo estratto): https://www.unrealengine.com/en-US/developer-interviews/assetto-corsa-competizione-leans-into-realism-to-create-the-ultimate-racing-sim

### Shared memory, terze parti

- PyAccSharedMemory, tabelle dei campi e degli enum: https://github.com/rrennoir/PyAccSharedMemory e https://libraries.io/pypi/pyaccsharedmemory
- pyacc (gotzl): https://github.com/gotzl/pyacc
- Proprietà ACC di LSR: https://docs.lsr.gg/properties/acc.html

### Pirelli

- «Tyre Data Booklet 2019 – Blancpain GT World Challenge Asia GT3» (PDF): https://www.gt-world-challenge-asia.com/documents/team/581/P_Book%20-%20Blancpain%20GT%20World%20Challenge%20Asia%20GT3%202019.pdf

### Coach Dave Academy

- Pressioni: https://coachdaveacademy.com/tutorials/how-to-set-the-correct-tyre-pressures-in-acc/
- Pressioni da bagnato, «myth or meta»: https://coachdaveacademy.com/tutorials/acc-wet-tyre-pressures-myth-or-meta/
- Setup da bagnato: https://coachdaveacademy.com/tutorials/how-to-setup-your-car-for-the-wet-in-assetto-corsa-competizione
- Diagramma «Wet Setup Workflow» (PDF): https://coachdaveacademy.com/wp-content/uploads/2020/06/workflow-wet-setups.pdf
- Note dei setup wet CDA4 per la 1.9: https://coachdaveacademy.com/release-notes/cda4-wet-setup-release-notes/
- Guida al setup: https://coachdaveacademy.com/tutorials/the-ultimate-acc-car-setup-guide/
- FAQ 1.9: https://coachdaveacademy.com/announcements/1-9-acc-faq-coach-dave/
- Benzina: https://coachdaveacademy.com/tutorials/how-to-manage-your-fuel-in-acc/

### Community

- Solox, temperature pista: https://solox.gg/acc-track-temperatures/
- Solox, bagnato: https://solox.gg/acc-wet-weather-driving-and-setup/
- Solox, usura: https://solox.gg/acc-tyre-wear/
- Blue Dragon Racing, pressioni: https://bluedragonracing.eu/protips/all-about-the-tires-in-acc-first-part-what-the-hell-is-psi/
- Trophi, pressioni: https://www.trophi.ai/post/why-tyre-pressures-are-crucial-in-acc
- simracingsetup.com, pressioni: https://simracingsetup.com/assetto-corsa/acc-tyre-pressure-guide/
- simracingsetup.com, BoP: https://simracingsetup.com/assetto-corsa/what-is-bop-in-sim-racing/
- GTPlanet, stati pista (403, solo estratto): https://www.gtplanet.net/forum/threads/what-i-found-out-tips.394684/post-13168444
- Steam, pista dinamica: https://steamcommunity.com/app/805550/discussions/0/2946998508800932015/
- Progetto GitHub sull'evoluzione pista (dati F1): https://github.com/parekhrohan21/fastf1_pitwall/pull/179

### Motorsport reale

- Grassroots Motorsports, Jeff Braun (403, solo estratto): https://grassrootsmotorsports.com/articles/managing-tire-temperatures-improved-track-performa/
- Nextgen-Auto, evoluzione pista in F1: https://motorsport.nextgen-auto.com/en/formula-1/Track-evolution-in-Formula-1,31611.html
- Effetto benzina, post di un ingegnere su X (solo estratto): https://x.com/brrrake/status/1677934036130430976
- F1technical, tempi corretti per la benzina: https://www.f1technical.net/forum/viewtopic.php?t=7982
- F1technical, setup da bagnato: https://www.f1technical.net/forum/viewtopic.php?t=15310
- PMW Magazine, BoP Hypercar (solo estratto): https://pmw-magazine.com/features/tech-insight-le-mans-hypercar-bop-analysis.html
- Mercedes F1, temperature (solo estratto): https://www.mercedesamgf1.com/news/insight-temperature-talk
- Racer, IndyCar e temperatura pista (solo estratto): https://racer.com/2023/04/11/indycar-tech-download-taming-the-track/
- Rennlist, carichi di benzina: https://rennlist.com/forums/racing-and-drivers-education-forum/432026-fuel-loads-2.html
