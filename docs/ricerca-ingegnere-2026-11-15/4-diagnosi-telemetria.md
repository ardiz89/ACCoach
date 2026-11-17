# 4 · Diagnosi del bilanciamento dalla telemetria (GT3 su ACC)

Ricerca web del 2026-11-15. Scopo: sostituire il rilevatore attuale (rapporto
imbardata/volante sotto soglia = sottosterzo; controsterzo = sovrasterzo), che
su una GT3 con TC e ABS accesi resta muto su 40 giri su 42.

## Come leggere questo rapporto

Ogni affermazione porta un'etichetta di provenienza:

- **[FONTE]** letta direttamente alla pagina indicata.
- **[INDIRETTO]** letta in una fonte secondaria (forum, riassunto, copia) o in un
  riassunto automatico della pagina; il testo originale non l'ho visto.
- **[DERIVATO]** conseguenza algebrica di formule citate; il passaggio è scritto.
- **[MEMORIA]** conoscenza generale di dinamica del veicolo o del libro di
  Segers, **non ritrovata in rete in questa ricerca**. Da non trattare come
  citazione.
- **[CASA]** misurato dal progetto (`TARATURE-ACC.md`, `structs.py`).
- **[PROPOSTA]** scelta di progetto mia, non una pratica documentata.

Tre limiti della ricerca, da sapere prima di fidarsi:

1. **Il libro di Segers non è consultabile in rete.** Ho trovato solo le schede
   dell'editore (SAE R-367 del 2008, R-408 del 2014). Tutto ciò che attribuisco
   a Segers è [MEMORIA].
2. **Quasi nessuna fonte dà soglie assolute.** MoTeC lo dice in chiaro: per il
   canale Oversteer «an absolute reference range can't really be supplied». Le
   soglie numeriche qui sotto sono quasi tutte [PROPOSTA] da tarare sui giri del
   pilota, non numeri di letteratura.
3. **Diverse pagine non si sono lasciate leggere** (Rennlist, eng-tips,
   tapatalk, overtake.gg, GoSetups: 403; il PDF ufficiale Kunos v1.8.12, le
   note di fisica ACC 1.9 e l'articolo OptimumG su Racecar Engineering sono PDF
   a immagine, non estraibili qui). Il coefficiente benzina→tempo per ACC non
   l'ho trovato in nessuna fonte.

---

## 0 · Perché il rilevatore di oggi non vede niente

Le fonti concordano su un punto che spiega i 40 giri muti: sottosterzo e
sovrasterzo **non sono eventi, sono una relazione fra i due assi che esiste in
ogni curva**, e si legge come grandezza continua e relativa.

- «Balance is a tire relationship, not a driver complaint»; «A single slide is
  an event. A repeated phase-specific response is a diagnosis» [FONTE, materiale
  didattico di provenienza non verificata]
  https://paddocklink-docs.pages.dev/lms/vehicle-dynamics-and-setup/making-setup-changes/diagnosing-handling/
- HP Academy: i risultati di bilanciamento «are relative to another driver,
  setup, or tyre set»; più sterzo tenuto più a lungo all'apice = più
  sottosterzo [INDIRETTO]
  https://hpacademy.com/courses/professional-motorsport-data-analysis/cornering-performance-steering-data-and-balance
- Il controsterzo è solo un ripiego: «without an oversteer calculation,
  countersteer indicates oversteer events» [INDIRETTO]
  https://www.designjudges.com/articles/analyzing-driver-data

Con TC e ABS accesi i due segnali su cui ci appoggiamo spariscono per
costruzione: il TC taglia la coppia prima che serva il controsterzo, e il
sottosterzo al limite di una GT3 non abbassa di colpo il rapporto
imbardata/volante, lo fa scivolare di poco e per tutta la curva. Serve quindi
**una misura continua per curva e per fase, confrontata con la propria
distribuzione**, più i segnali degli aiuti come sintomo e non come rumore.

---

## 1 · Catalogo delle metriche

Convenzioni: `δ` angolo ruota anteriore [rad], `L` passo [m], `V` velocità
[m/s], `r` velocità d'imbardata [rad/s], `ay` accelerazione laterale [m/s²],
`β` angolo di assetto del corpo vettura [rad], `a`/`b` distanze del baricentro
dagli assi anteriore/posteriore.

### 1.1 Angolo di sottosterzo (steering − Ackermann)

- **Definizione.** L'angolo di sottosterzo è «the amount of additional steering
  (at the road wheels, not the hand wheel)» oltre l'angolo di Ackermann, che è
  l'angolo con cui l'auto percorrerebbe la curva senza accelerazione laterale
  [INDIRETTO] https://en.wikipedia.org/wiki/Understeer_and_oversteer
- **Formula a regime (via ay).** `δ_us = |δ| − L·|ay|/V²` (dato che
  `L/R = L·ay/V²`). È la stessa struttura del canale Oversteer di MoTeC i2,
  riportato così [INDIRETTO, articolo Silicon Chip che cita i2]:

  ```
  Oversteer (rad) = smooth(choose('Corr Speed'[km/h]<50, 0,
      sgn('G Force Lat'[m/s/s]) * (('Vehicle Wheelbase'[m]*'G Force Lat'[m/s/s]
      / sqr('Corr Speed'[m/s]))
      - sgn(stat_mean('Steered Angle'[rad]*'G Force Lat'[m/s/s]))*'Steered Angle'[rad])), 0.2)
  ```
  https://www.siliconchip.com.au/Issue/2006/August/MoTeC+Race+Car+Data+logging,+Pt.2
  Tre dettagli da copiare: **zero sotto 50 km/h**, **filtro 0.2 s**, e il
  `stat_mean(sterzo × ay)` che scopre da solo il segno del canale sterzo.
  Segno MoTeC: negativo = sottosterzo, positivo = sovrasterzo [INDIRETTO]
  https://coachdaveacademy.com/tutorials/how-to-use-motec-data-in-assetto-corsa-competizione/
  Esempio dell'articolo: −3.9° calcolati con 7.8° di sterzo a 75.5 km/h.
- **Formula dinamica (via imbardata).** `δ_us = δ − L·r/V`. [DERIVATO] dal
  modello a bicicletta riportato da blekenbleu
  (`α_f = δ − atan((v_y + a·r)/v_x)`, `α_r = −atan((v_y − b·r)/v_x)`): per
  angoli piccoli `α_f − α_r = δ − (a+b)·r/v_x = δ − L·r/V`. Quindi **questa
  versione è esattamente la differenza di slip angle anteriore−posteriore** e
  non richiede né `β` né la posizione del baricentro.
  https://blekenbleu.github.io/SimHub/Oversteer
- **Canali.** sterzo, `V`, `ay` oppure `r`, passo.
- **Soglie.** Nessuna assoluta in letteratura (vedi limite 2). [PROPOSTA]
  lavorare in gradi di ruota e confrontare la mediana per curva/fase con la
  distribuzione dei propri giri.
- **Limiti.**
  - MoTeC: «only an approximation, as i2 does not understand the relationship
    between your steering wheel angle and the actual angle of the tires»
    [INDIRETTO] https://forum.motec.com.au/viewtopic.php?p=7621
  - Su ACC `steerAngle` è una frazione −1..1 del fondo corsa, non un angolo
    [CASA]: serve il guadagno volante→ruota per auto. Vedi 1.12.
  - Falso sotto i 50 km/h, su banking, sui cordoli; a regime ignora `dβ/dt`.
  - Un frenante bloccato in rettilineo «presents as massive over- or
    understeer» [FONTE blekenbleu]: va escluso con freno/slip.
  - Parere critico di un forum: buono per le tendenze, «too far» come misura
    oggettiva [INDIRETTO].

### 1.2 Gradiente di sottosterzo

- **Formula.** `δ = 57.3·L/R + K·ay` (δ in gradi, ay in g); `K` in deg/g,
  `K>0` sottosterzo, `K<0` sovrasterzo, `K=0` neutro [INDIRETTO]
  https://formuladen.com/en/steer-angle-given-understeer-gradient-formula/Formula-37140
  e https://en.wikipedia.org/wiki/Understeer_and_oversteer
- **Come si usa sui giri.** Regressione di `δ_us` su `ay` per curva o per banda
  di velocità: la pendenza è `K`, l'intercetta dice se il guadagno dello sterzo
  è sbagliato. [PROPOSTA]
- **Limiti.** Definito a regime e in campo lineare. Wikipedia separa
  esplicitamente il campo lineare dal **comportamento al limite**, per il quale
  raccomanda i termini «push» e «loose»: sono due diagnosi diverse e vanno
  tenute separate (K nella banda 0.3–0.8 del picco di g; saturazione sopra).
  `K` dipende da velocità e ay, «so both must be reported».

### 1.3 Assetto del corpo vettura (β) e sua derivata

- **Formula.** `β = atan2(v_lat, v_long)`; velocità di assetto
  `dβ/dt ≈ ay/V − r` (segno secondo convenzione). [MEMORIA: Segers la chiama
  «attitude velocity»; in pista non si misura `β` e si integra, con deriva].
- **In simulazione `β` è gratis**: ACC espone `localVelocity` [CASA, struct], e
  blekenbleu lo usa proprio così («ratio of lateral velocity / tangential
  speed»). Niente integrazione, niente deriva.
- **Lettura.** `β` più alto a parità di velocità = più scivolamento («higher
  beta at a given speed indicates more sliding»); la **derivata dell'imbardata**
  è «the best way I've found to quantify twitchiness»; la «chassis beta rate» è
  la derivata dell'angolo rispetto alla traiettoria [INDIRETTO designjudges].
- **Uso.** `β` grande e crescente a gas aperto = retrotreno che parte
  (sovrasterzo di potenza), anche quando il TC lo ferma prima del controsterzo.
- **Limiti.** `β` di regime di una GT3 è di pochi gradi e dipende dalla
  velocità: si confronta per curva, non in assoluto.

### 1.4 Differenza di slip angle anteriore/posteriore

- **Definizione.** «Oversteer = Rear tyre slip angle > Front tyre slip angle;
  Understeer = Front > Rear» [INDIRETTO, documento VBOX non raggiungibile]
  https://vboxautomotive.co.uk/downloads/Oversteer-Understeer%20Analysis%20in%20Tyre%20Testing.pdf
  Stessa cosa «per Milliken» in designjudges.
- **Formula.** Vedi 1.1: `α_f − α_r = δ − L·r/V`. Le due singole richiedono
  `a` e `b` (blekenbleu li **assume**: 1.2 m e 1.6 m, «not available in game»).
- **Canale nativo.** `slipAngle[4]` esiste nello struct ACC ma è **da
  verificare** (sezione 5). Se è vivo, `media(ant) − media(post)` è la misura
  diretta e non serve il guadagno dello sterzo.

### 1.5 Imbardata misurata contro imbardata teorica

- **Formula.** `r_teorica = V·δ/L` (cinematica) oppure `ay/V` (dalla
  traiettoria); errore `Δr = r − r_teorica`. Variante con gradiente noto:
  `r_des = V·δ/(L + K·V²)` [INDIRETTO, brevetto GM]
  https://www.freepatentsonline.com/y2009/0182476.html
- **Lettura.** `r < V·δ/L` sottosterzo, `r > V·δ/L` sovrasterzo. È la stessa
  informazione di 1.1 dinamica divisa per `L/V`: **non sono due prove
  indipendenti**, non vanno contate due volte.
- **`r` contro `ay/V`**: la differenza è `dβ/dt`, cioè 1.3.
- **Nota sul rilevatore attuale.** Il rapporto imbardata/volante di oggi è
  questa metrica senza normalizzazione per velocità e passo; il guadagno
  d'imbardata `r/δ = V/(L + K·V²)` cambia con `V`, quindi una soglia fissa è
  per forza larga. [DERIVATO]

### 1.6 Sterzo che cresce senza che cresca il g laterale (saturazione anteriore)

- **Fonte.** «If steering keeps rising while lateral G falls, the front tyres
  have passed their peak slip angle» [INDIRETTO HP Academy]; «Lateral g stops
  building while steering keeps increasing» [FONTE paddocklink]
  https://paddocklink-docs.pages.dev/lms/data-interpretation-ii-advanced/rotational-data/rotation-correlation/
- **Formula [PROPOSTA].** Nella finestra entrata→apice: frazione di tempo con
  `d|δ|/dt > 0` e `d|ay|/dt ≤ 0` (segnali filtrati 0.2–0.3 s), con `|ay|` oltre
  il 70% del picco della curva. In alternativa pendenza locale `d|ay|/d|δ|`:
  vicino a zero o negativa = anteriore saturo.
- **Grafico equivalente.** Nuvola `ay` contro `δ`: ha la forma della curva
  forza laterale–slip angle [INDIRETTO HP Academy].
- **Limiti.** Va escluso il tratto in cui la velocità sta ancora scendendo
  molto (ay cala perché cala V²/R, non per saturazione): condizionare a freno
  sotto una soglia o usare la curvatura `ay/V²` al posto di `ay`.

### 1.7 Traccia dello sterzo: correzioni, ruvidità, integrale

Tutte da HP Academy [INDIRETTO]
https://www.hpacademy.com/courses/professional-motorsport-data-analysis/math-channels-advanced-math-channel-uses

- **Ruvidità/smoothness.** `|sterzo − media_mobile(sterzo, 0.5 s)|`. Si calcola
  separata per entrata e uscita; se cala la pulizia lungo lo stint in uscita =
  degrado del posteriore. Avvertenza: «If I oversmooth, I won't be representing
  anything close to the real channel».
- **Integrale dello sterzo.** `∫|sterzo| dt` solo con `|ay| > 0.5 g`, azzerato a
  ogni giro. Sale = deriva verso il sottosterzo; scende = verso il sovrasterzo.
  È la metrica più robusta per una GT3 con aiuti perché non richiede eventi.
- **Controsterzo.** Sterzo di segno opposto alla curva: evento di sovrasterzo,
  utile ma raro (già lo abbiamo).
- **Correzioni in frenata prima dell'inserimento** = instabilità in frenata
  (bloccaggio posteriore, ripartizione, scalate) [INDIRETTO HP Academy].
- **Entrata «a morsi».** Sterzo a gradini con ritiro dopo ogni morso
  [INDIRETTO designjudges]: errore del pilota, non dell'auto.
- **Offset dello zero.** Media dello sterzo dove `|ay| < 0.05 g`: controllo di
  qualità del canale prima di ogni altra cosa.

### 1.8 G laterale di picco, velocità minima, g combinato

- **Picco di g laterale per curva** e **velocità minima**: prestazione, non
  bilanciamento. Dicono *quanto* si perde, non *quale asse*. [MEMORIA Segers]
- **G combinato** `sqrt(ay² + ax²)`: i buchi fra frenata e curva sono
  esitazione del pilota («Gap between braking G and cornering G») [INDIRETTO
  designjudges]. Serve a separare pilota da assetto (sezione 3).
- **Limiti.** Il g di picco cresce con la velocità per l'aerodinamica: si
  confronta curva con sé stessa.

### 1.9 Attesa prima del gas e modulazione in uscita

- **Priorità.** «Getting to full throttle sooner on corner exit is the most
  important» [INDIRETTO designjudges].
- **Aggressività sul gas** (HP Academy): derivata del gas filtrato, valida solo
  con gas fra 5% e 95%, `|ay| > 0.5 g`, `ax > 0`, derivata > 0. Avvertenza:
  «these values are not generic».
- **Metriche [PROPOSTA].**
  - tempo da apice (minimo di V) a primo gas > 10%, e a gas pieno;
  - numero di inversioni del gas fra primo gas e gas pieno (alzate);
  - frazione dell'uscita con TC attivo (sezione 2).
- **Lettura.** Gas che arriva «while steering demand is still high» =
  sottosterzo in percorrenza che ritarda il gas; gas alzato dopo un'apertura =
  sovrasterzo di potenza o sottosterzo di potenza (si distingue con 1.1: `δ_us`
  sale = anteriore, `β`/TC salgono = posteriore).

### 1.10 Nuvole (scatter) contro velocità e contro g longitudinale

[INDIRETTO designjudges] «Whenever you make a new channel, make a scatter plot
against every other key channel».

- **Sterzo contro velocità**: lo sterzo cala con la velocità; troppo sterzo nei
  veloci è un campanello.
- **Sovrasterzo/twitch contro g longitudinale**: distribuisce il sintomo fra
  entrata (ax<0), percorrenza (ax≈0), uscita (ax>0). È il modo documentato di
  normalizzare per fase.
- **Tendenza con la velocità**: in un'auto con aerodinamica il bilanciamento
  dovrebbe spostarsi verso il sottosterzo salendo di velocità; sovrasterzo che
  cresce con la velocità = auto difficile.

### 1.11 Normalizzazione per fase e per velocità (vale per tutte)

- **Fasi.** Entrata (freno/rilascio/inserimento), percorrenza (carico
  costante, «used as the reference point»), uscita (gas). Una diagnosi è una
  frase in quattro parti: **fase, innesco, asse, prova** [FONTE paddocklink].
  Sottosterzo in entrata + sovrasterzo in uscita non è una contraddizione: sono
  due righe.
- **Segmentazione [PROPOSTA].** entrata = da inizio frenata al rilascio (freno
  < 5%) o al minimo di V; percorrenza = freno < 5% e gas < 20% attorno al
  minimo di V; uscita = da primo gas a gas > 95% o `|ay|` < 0.5 g.
- **Velocità.** Coach Dave Delta divide il suo indicatore a **120 km/h** («over
  120kph/under 120kph») per separare meccanica da aerodinamica [FONTE]
  https://coachdaveacademy.com/documentation/how-to-use-the-oversteer-understeer-widget/
  Paddocklink mette l'aerodinamica «roughly 60 mph / 100 km/h and above… not a
  magic rule».
- **Soglia minima.** 50 km/h (MoTeC) e `|ay| > 0.5 g` (HP Academy) come
  cancelli d'ingresso.

### 1.12 Il guadagno dello sterzo: autotaratura [PROPOSTA]

Problema: ACC dà lo sterzo come frazione del fondo corsa, e il passo non è
nella memoria condivisa. Soluzione ricavata dalle definizioni sopra: a basso g
laterale l'auto è cinematica, quindi `δ ≈ L·r/V`. Regressione per auto di
`steerAngle` contro `r/V` sui campioni con `|ay| < 0.3–0.4 g` e `V > 50 km/h`:
la pendenza è `L / guadagno` in un colpo solo, e **non serve conoscere né il
passo né il rapporto di sterzo separatamente**. Il residuo ad alto g è l'angolo
di sottosterzo in unità di volante. Controllo: l'intercetta deve essere ~0
(altrimenti c'è un offset, vedi 1.7). Nota: nella cartella di ricerca esiste
già un `k_hat.npy`, probabilmente lo stesso guadagno stimato da un altro filone.

### Tabella di affidabilità

| Metrica | Canali | Soglia in letteratura | Affidabilità su GT3+aiuti |
|---|---|---|---|
| `δ_us` dinamico (δ − L·r/V) | sterzo, r, V | nessuna; 50 km/h, filtro 0.2 s | **alta** se il guadagno è autotarato |
| `δ_us` a regime (via ay) | sterzo, ay, V | idem | media (banking, transitori) |
| Gradiente K per curva | δ_us, ay | deg/g, segno | media, solo campo lineare |
| Integrale sterzo | sterzo, ay | `|ay|>0.5 g` | **alta**, relativa a sé stessi |
| Saturazione (δ↑, ay→) | sterzo, ay, V | nessuna | **alta** per il sottosterzo al limite |
| β e dβ/dt | localVelocity, r | nessuna | alta per il posteriore, se il canale è vivo |
| Ruvidità sterzo | sterzo | finestra 0.5 s | media (dipende da volante e pilota) |
| Controsterzo | sterzo, ay | — | bassa: raro con TC |
| slipAngle nativo ant−post | slipAngle[4] | — | **da verificare** |
| TC/ABS (sezione 2) | tc, abs, gas, freno | — | **alta** come sintomo indiretto |

---

## 2 · Segnali indiretti quando gli aiuti mascherano il problema

### 2.1 Attivazioni di TC e ABS

- In ACC `tc` e `abs` (physics) valgono **0 oppure 1 quando l'aiuto lavora**;
  `tcInAction` e `absInAction` restano sempre 0 [FONTE, forum Kunos, post del
  29/12/2024 e 12/01/2025]
  https://www.assettocorsa.net/forum/index.php?threads/acc-shared-memory-documentation.59965/page-26
  [CASA] conferma: ad ABS spento `abs_active = 0.000` su 7307 frame.
- **Metriche [PROPOSTA]** per curva: durata TC in uscita [s e % dell'uscita],
  posizione della prima attivazione rispetto all'apice, gas e `|ay|` al momento
  dell'attivazione; durata ABS in entrata e quanta parte cade **dopo**
  l'inserimento (ABS in appoggio = anteriore al limite in trail braking).
- **Lettura.** TC a gas parziale con `|ay|` alto = posteriore al limite
  laterale (sovrasterzo di potenza mascherato). TC a gas pieno e auto dritta =
  sola trazione, non bilanciamento. Il TC «determines how aggressively the ECU
  cuts engine torque in reaction to rear wheel spin» e troppo intervento può
  «stunt corner exit acceleration» [INDIRETTO, manuale Ford GT GT3]
  https://www.manualslib.com/manual/2121387/Ford-Gt-Gt3.html?page=13
- **Limite.** Il segnale è binario: l'intensità si ricava da `slipRatio` e dal
  buco fra gas richiesto e accelerazione.

### 2.2 Slip ratio per ruota e differenza di velocità ruote

- [CASA] `slipRatio` nativo ACC è vivo e firmato (<0 bloccaggio, >0
  pattinamento): frenata pulita p90 −0.074, bloccaggio vero −1.000; uscite
  pulite p99 0.077–0.080, pattinamenti veri 0.253–0.326.
- [CASA] «con gli aiuti accesi decide il flag, con gli aiuti spenti decide lo
  slip»: con ABS acceso il bloccaggio fisico non avviene.
- **Bilanciamento in frenata [PROPOSTA].** `media(slip ant) − media(slip post)`
  nella frenata: quale asse arriva prima al limite, cioè se la ripartizione è
  la causa dell'instabilità in entrata.
- **Differenza sinistra/destra al posteriore in uscita**: ruota interna che
  scappa = differenziale/precarico.
- Avvertenza di metodo: il 10% di slip non è un bersaglio costante; contano «
  single digit km/h differences between tire speed and vehicle speed»
  [INDIRETTO designjudges]. Un forum riporta finestre TC dall'1% al 7% di slip
  secondo auto e gomma [INDIRETTO, non verificato].

### 2.3 Freno contro decelerazione

- **Efficienza [PROPOSTA]**: `|ax| / pressione freno` per frenata; se cala a
  pari pressione = ABS/aderenza, non pilota.
- `brakeBias` in memoria condivisa ha uno scarto fisso dal valore a schermo
  («Dash Offset», es. −7 su Aston V12) [FONTE forum Kunos, 28/06/2025]. [CASA]
  1 click = 0.002.

### 2.4 Temperature gomme

- **Anteriori contro posteriori (core).** L'asse che lavora di più scalda di
  più: tendenza lenta, da leggere a stint e non a giro. Nessuna soglia trovata
  in fonte: «I found no source that gives a specific front-versus-rear balance
  indicator» è l'esito della ricerca.
- **Interno/centro/esterno.** Regole da paddock [INDIRETTO, forum]: centro più
  caldo della media interno/esterno = pressione alta; 10–15 °F di gradiente con
  interno più caldo = campanatura giusta; ~1 psi ogni 5 °F.
  https://www.corvetteforum.com/forums/autocrossing-and-roadracing/4245541-tire-temperature-interpretation.html
  Opinione contraria nella stessa ricerca: la campanatura incide poco sulla
  temperatura. **In ACC questi tre canali non risultano popolati** (sezione 5):
  la via praticabile è la sola temperatura di carcassa più la pressione.
- **Superficie contro carcassa.** Superficie molto sopra la carcassa =
  scivolamento [MEMORIA]. In ACC `tyreTemp` (superficie) non risulta affidabile
  (sezione 5).
- **Pressione a caldo.** È il primo regolatore del bilanciamento in ACC e il
  canale è vivo; la finestra ottimale va presa dalla documentazione ACC, che
  non ho potuto leggere (403/PDF).

### 2.5 Temperature freni

- [CASA] vive su ACC: anteriori 125→317 °C, posteriori 108→189 °C nella
  staccata. Il rapporto ant/post per frenata è un indicatore lento della
  ripartizione reale del lavoro.

### 2.6 Sospensioni, altezze, ammortizzatori

- `suspensionTravel[4]` risulta popolato (non è nell'elenco Kunos dei non
  usati; ACC lo esporta anche a MoTeC). `rideHeight[2]` è nell'elenco dei non
  usati.
- **Fondo corsa/tamponi [PROPOSTA]**: corsa che si ferma a un plateau sotto
  carico = tampone; se coincide con la fase del sintomo è una causa candidata.
  **Rake dinamico** = differenza corsa media posteriore − anteriore, in
  frenata e in appoggio veloce.
- Correlazione osservata: sovrasterzo insieme a più estensione dell'anteriore
  (specie interno), più compressione al posteriore e rollio posteriore più
  piatto [INDIRETTO designjudges].
- **Istogrammi ammortizzatori** [INDIRETTO HP Academy]
  https://www.hpacademy.com/courses/professional-motorsport-data-analysis/damper-analysis-damping-histogram/
  : campo −250…+250 mm/s, classi da ~20 mm/s; 0–5 mm/s attrito; **5–25 mm/s**
  bassa velocità, «the transient corner entry and exit balance»; 25–200 mm/s
  asperità; oltre 200 cordoli. Punto di partenza: istogramma **simmetrico**
  compressione/estensione per ruota («isn't the actual optimum»), sinistra e
  destra simili sullo stesso asse. Solo giri interi e rappresentativi. Coach
  Dave per ACC: forma a campana [FONTE].
- **Limite forte.** Per gli istogrammi una guida indica 500–1000 Hz
  [INDIRETTO, venditore]; la nostra acquisizione è ~60 Hz: la parte alta dello
  spettro non è affidabile, la banda 5–25 mm/s sì.

---

## 3 · Separare il pilota dall'assetto

Regola guida: «before you diagnose balance, diagnose the request you made of
the car» [FONTE paddocklink].

### 3.1 Criteri

| Criterio | Dice «pilota» | Dice «assetto» |
|---|---|---|
| Variabilità fra giri nella stessa curva | il sintomo va e viene con punto di inserimento, velocità, tempi del gas | stesso sintomo nella stessa fase su giri puliti con comandi stabili |
| Confronto col giro di riferimento | la prima differenza è **a monte** (inserimento, frenata): il sintomo è una conseguenza | comandi sovrapponibili, risposta diversa |
| Coerenza fra curve dello stesso tipo | solo in una curva | in tutte le curve lente (meccanica) o in tutte le veloci (aerodinamica) |
| Ritorno al punto di partenza (A-B-A) | la velocità resta anche tornando indietro | «the old balance or speed pattern returns despite similar driving» |

Fonti: https://paddocklink-docs.pages.dev/lms/data-interpretation-ii-advanced/rotational-data/rotation-correlation/
e https://paddocklink-docs.pages.dev/lms/race-car-mechanic-reference/diagnose-track-symptoms/separate-driver-adaptation-from-car-change/

Soglia di ripetibilità documentata: sintomo con stessa fase e stesso innesco in
**almeno 4 giri su 6** [FONTE paddocklink].

**Prima di tutto si misura la ripetibilità dei comandi** [PROPOSTA]: per curva,
deviazione standard fra giri di punto di frenata, velocità d'ingresso, punto di
inserimento, punto del primo gas. Se i comandi non sono ripetibili il verdetto
è «pilota/inconcludente» e non si tocca l'assetto («If the driver cannot
reproduce comparable inputs, the next step is a repeatability drill»).

### 3.2 Errori tipici e come appaiono

| Errore | Firma nei dati | Fonte |
|---|---|---|
| Frenata troppo tardi | lungo tratto a velocità minima dopo la staccata | designjudges [INDIRETTO] |
| Ingresso troppo veloce | freno rilasciato e **ripreso**; sterzo che fatica; gas in ritardo | designjudges |
| Frenata troppo presto | tratto a comandi quasi nulli prima dell'inserimento (gas, freno e sterzo vicini a zero); buco di g combinato | designjudges |
| Esitazione | calo del g combinato fra frenata e curva | designjudges |
| Inserimento anticipato | all'inizio l'auto pare a posto, poi non ruota a metà e rifiuta il gas; la prima differenza è all'inserimento | paddocklink [FONTE]; HP Academy |
| Prima metà lenta | finta storia di rotazione che sembra bilanciamento | paddocklink |
| Rilascio freno brusco | retrotreno che ruota troppo in fretta al rilascio | paddocklink |
| Freno tenuto fino all'apice | scarica il posteriore, sovrasterzo in entrata | riassunto di Driver61 [INDIRETTO] |
| Gas anticipato | sottosterzo di potenza: `δ_us` sale col gas; oppure sovrasterzo, alzata e controsterzo | paddocklink; designjudges; Driver61 |
| Sottosterzo poi sovrasterzo in uscita | sterzo eccessivo a metà, gas tardivo o brusco, correzione | HP Academy; Fanatec |
| Sovraguida nei veloci | grande alzata del gas più sterzo eccessivo | designjudges |
| Entrata a morsi | sterzo e g a gradini con ritiro | designjudges |
| Doppio apice | due minimi di V o due picchi di sterzo nella stessa curva | [MEMORIA] |

Regola d'oro: **le correzioni sono prova, non causa** («Added steering shows
the front missed. Countersteering shows yaw occurred»). Si registra l'innesco:
gas anticipato, alzata secca, freno, fondo corsa, velocità di sterzata.

---

## 4 · Quanti giri servono e come confrontare prima/dopo

### 4.1 Cosa dicono le fonti

- **A-B-A, 5 giri per blocco, 15 in tutto**, un solo cambiamento [FONTE
  paddocklink]. «Five is not magic, but it is a useful minimum discipline».
- I giri anomali si scartano **con la stessa regola** in ogni configurazione;
  i giri di adattamento si annotano a parte.
- «Suspect drift before blaming a single adjustment»; «A setup change that
  cannot be separated from track evolution is not yet diagnosed».
- Una modifica è abbastanza grande quando la differenza si vede «over top of
  the natural noise» (HP Academy, sugli ammortizzatori).
- Nessuna fonte dà una soglia numerica di accettazione né un coefficiente
  benzina/pista. Quel che segue è statistica standard [PROPOSTA].

### 4.2 Metodo [PROPOSTA]

1. **Unità = curva, non giro.** Per ogni curva e fase si calcola la **mediana**
   della metrica su ciascun blocco (la mediana regge il giro sporco). Con 12–15
   curve e 5 giri si hanno 12–15 differenze accoppiate invece di una.
2. **Test accoppiato per curva.** Differenza `d_c = mediana_dopo −
   mediana_prima`. Segni concordi: con 6 curve su 6 nello stesso verso il test
   dei segni dà p = 0.031 a due code; con 5 su 5 p = 0.0625 (non basta). Il
   Wilcoxon dei ranghi con segno non può scendere sotto 0.05 con meno di 6
   coppie. Sono proprietà dei test, non numeri di motorsport.
3. **Per gruppi omogenei.** Il test si fa separato per curve lente e veloci
   (soglia 120 km/h, 1.11) e per fase: una modifica alare non deve muovere le
   lente.
4. **Dimensione dell'effetto.** `d_c / σ_c`, dove `σ_c` è la deviazione
   standard fra giri di quella curva nel blocco di base (meglio MAD×1.4826).
   Sotto 0.5 è dentro il rumore; fra 0.5 e 1 è «forse»; sopra 1 con segni
   concordi è un effetto. Le soglie sono convenzioni (d di Cohen), da tarare.
5. **Il rumore si misura prima.** `σ_c` viene da giri con assetto invariato: è
   il pavimento sotto il quale nessuna differenza si riporta.
6. **Minimo pratico.** 5 giri puliti per blocco; con 3 si può solo dire «non
   contraddice». Con A-B-A, l'effetto vale se B differisce **sia** da A **sia**
   da A′, e A ≈ A′.

### 4.3 Benzina ed evoluzione della pista

- **Dentro lo stint**: regressione della metrica (o del tempo sul giro) sul
  numero di giro o sui litri a bordo, per curva; si confrontano i residui. Con
  A-B-A la deriva lineare si cancella da sola se i blocchi sono uguali: `B −
  (A + A′)/2`.
- **Stessa benzina a inizio blocco** è la correzione più semplice, e in
  simulazione costa zero.
- **Coefficiente litri→tempo**: **non trovato** per ACC; va misurato in casa
  (stesso assetto, due carichi). Non usare numeri di Formula 1.
- **Pista**: su ACC `surfaceGrip` è 0 per costruzione [CASA]; il grip sta in
  `trackGripStatus` e nelle temperature aria/asfalto. Blocchi con stato pista
  o temperatura asfalto diversi non si confrontano.
- **Gomme**: stesso treno, stessa finestra di pressione a caldo; i primi giri
  a gomma fredda fuori [CASA: già regola del progetto].

---

## 5 · Canali della memoria condivisa di ACC (pagina physics)

Fonti: elenco ufficiale dei campi non usati, post di uno sviluppatore Kunos del
10/09/2019 [FONTE, letta via riassunto]
https://www.assettocorsa.net/forum/index.php?threads/acc-shared-memory-documentation.59965/
; pagina 26 dello stesso thread (2024–2026); README di PyAccSharedMemory
https://github.com/rrennoir/PyAccSharedMemory ; misure del progetto [CASA].
**L'elenco del 2019 è superato almeno in un punto**: dava `slipRatio` come non
usato, e il progetto lo ha misurato vivo sulla coda v1.7+. Quindi ogni «non
usato» qui sotto vale come ipotesi da riconfermare con `monitor`.

| Campo | Stato in ACC | Prova |
|---|---|---|
| `gas`, `brake`, `steerAngle`, `speedKmh`, `gear`, `rpms`, `fuel` | vivi | [CASA] |
| `accG[3]` | vivo | [CASA] (`verify-g` previsto) |
| `localAngularVel[3]` | vivo (imbardata già in uso) | [CASA] |
| `velocity[3]`, `localVelocity[3]` | dichiarati; **`localVelocity` da confermare** (serve a β) | un utente nel 2026 segnala `velocity` non letto da Python, senza risposta |
| `wheelSlip[4]` | vivo | non in elenco «non usati»; unità non documentate |
| `slipRatio[4]` | **vivo**, firmato | [CASA], contro l'elenco 2019 |
| `slipAngle[4]` | **incerto** | «non usato» nel 2019, ma sta accanto a `slipRatio` nella stessa coda: **da misurare** |
| `wheelAngularSpeed[4]` | vivo | non in elenco |
| `wheelsPressure[4]` | vivo | [CASA] |
| `tyreCoreTemperature[4]` | vivo | [CASA] |
| `tyreTempI/M/O[4]` | **non usati** | Kunos 2019 |
| `tyreTemp[4]` | **non usato / non affidabile** | Kunos 2019; nel 2025 un utente: valori che non tornano |
| `brakeTemp[4]` | vivo | [CASA] 125→317 °C |
| `padLife[4]`, `discLife[4]` | vivi | PyAccSharedMemory: pastiglia da 29 mm, disco da 32 mm |
| `suspensionTravel[4]` | vivo | non in elenco; esportato a MoTeC |
| `rideHeight[2]` | **non usato** | Kunos 2019 |
| `tc`, `abs` | vivi, **binari 0/1** in ACC | forum 2024–25; [CASA] |
| `tcinAction`, `absInAction` | **sempre 0** | Kunos 2019; forum 2024 |
| `brakeBias` | vivo, con scarto «Dash Offset» | forum 2025; [CASA] |
| `wheelLoad[4]`, `tyreWear[4]`, `tyreDirtyLevel[4]`, `camberRAD[4]` | **non usati** | Kunos 2019 |
| `mz[4]`, `fx[4]`, `fy[4]` | «non usati» nel 2019, **da rimisurare** (stessa coda di `slipRatio`) | Kunos 2019 |
| `cgHeight`, `ballast`, `airDensity`, `performanceMeter`, `engineBrake`, `currentMaxRpm`* | non usati (*`currentMaxRpm` il progetto lo legge vivo) | Kunos 2019; [CASA] |
| `numberOfTyresOut` | **inerte** | Kunos 2019; [CASA] |
| DRS, KERS/ERS, P2P | non usati | Kunos 2019 |
| `absVibrations` | sempre 0 | forum 2025 |
| `kerbVibration`, `slipVibrations`, `gVibrations` | dichiarati vivi, non verificati | documentazione |
| `clutch` | segnalato sempre 0.0 nel 2019, senza risposta | forum |
| `tyreContactPoint[4][3]` | non verificato; **se vivo dà passo e carreggiata** | da misurare |
| static: `tyreRadius`, `suspensionMaxTravel`, `maxTorque`, `maxPower` | **non usati** | Kunos 2019; [CASA] |
| static: passo | **non esiste** | serve una tabella per auto o l'autotaratura 1.12 |

Canali MoTeC di ACC (per confronto): gas, freno, sterzo, dati gomme, velocità
ruote, g, sospensioni; foglio «Understeer/Oversteer» calcolato da velocità,
sterzo, g laterale, freno e gas [FONTE Coach Dave].

**Tre verifiche da fare prima di scrivere codice** (dieci minuti con
`monitor`): `slipAngle` si muove in curva? `localVelocity[0]` è la velocità
laterale? `tyreContactPoint` è popolato?

---

## 6 · Tabella «sintomo → firma nei dati»

| Sintomo | Fase | Firma principale | Conferma | Da escludere prima |
|---|---|---|---|---|
| Sottosterzo in entrata | freno→inserimento | `δ_us` alto mentre il freno è ancora premuto; ABS attivo dopo l'inserimento | slip anteriore più negativo del posteriore | ingresso troppo veloce (freno ripreso), inserimento anticipato |
| Sottosterzo in percorrenza | freno e gas ~0 | sterzo che sale con `ay` fermo; integrale sterzo alto; sterzo tenuto più a lungo all'apice | velocità minima più bassa del riferimento a pari traiettoria | prima metà lenta, linea diversa |
| Sottosterzo di potenza | uscita | `δ_us` cresce col gas; sterzo non si riapre mentre il gas sale; alzata del gas | TC **non** attivo, `β` piccolo | gas anticipato |
| Sovrasterzo in entrata | rilascio freno | picco di `dr/dt`, `β` che cresce al rilascio, sterzo ridotto o controsterzo | slip posteriore più negativo; scalata nello stesso istante | rilascio brusco, freno tenuto all'apice |
| Sovrasterzo in percorrenza | carico costante | `δ_us` basso o negativo, `r > V·δ/L`, ruvidità sterzo alta | β alto a pari velocità | correzioni da cordolo |
| Sovrasterzo di potenza (mascherato dal TC) | uscita | **TC attivo a gas parziale con `|ay|` alto**; slip posteriore alto; gas a denti di sega | `β` che cresce prima del taglio; ruvidità sterzo in uscita | gas brusco (derivata alta) |
| Instabilità in frenata | staccata dritta | correzioni di sterzo a ruote dritte; `dr/dt` rumoroso | slip posteriore più negativo dell'anteriore; scalate | ripartizione, cordolo |
| Anteriore saturo (troppo sterzo) | inserimento→apice | `ay` cala mentre lo sterzo sale | nuvola ay–sterzo che piega | velocità ancora in calo |
| Solo trazione | uscita dritta | TC a gas pieno, `|ay|` basso | differenza sinistra/destra al posteriore | non è bilanciamento |
| Fondo corsa/tampone | dove capita | plateau di `suspensionTravel` | coincide con la fase del sintomo | cordolo |
| Deriva nello stint | giro su giro | integrale sterzo che sale (sottosterzo) o ruvidità in uscita che sale (posteriore) | temperatura/pressione dell'asse | benzina, pista |
| Errore del pilota | qualunque | sintomo presente in meno di 4 giri su 6; comandi non ripetibili; differenza a monte | buco di g combinato | — |

---

## 7 · Cosa ne esce per l'algoritmo [PROPOSTA]

1. **Non rilevare eventi: misurare.** Per ogni curva e fase, a ogni giro:
   `δ_us` dinamico mediano, integrale sterzo, frazione di saturazione, β e
   picco di `dr/dt`, ruvidità sterzo, durata e contesto di TC/ABS, differenza
   di slip ratio fra gli assi, attesa del gas.
2. **Autotarare il guadagno dello sterzo** per auto sui campioni a basso g
   (1.12): toglie la dipendenza da passo e rapporto di sterzo.
3. **Giudicare contro la propria distribuzione**, non contro una soglia
   assoluta: per curva, percentili dei giri puliti. Le fonti non offrono soglie
   assolute e MoTeC dice che non possono esistere.
4. **Prima il pilota**: ripetibilità dei comandi e differenze a monte; poi la
   regola dei 4 su 6; solo dopo l'assetto.
5. **Aggregare per tipo di curva** (lente/veloci a 120 km/h) e per fase: è
   questo che trasforma un sintomo in una leva di assetto.
6. **Il TC e l'ABS sono il sintomo**, non il motivo per cui non si vede niente.
7. Due metriche di 1.1 e 1.5 sono la stessa cosa: una sola nel punteggio.

---

## 8 · Fonti

Lette direttamente (anche via riassunto della pagina):

- Kunos, thread «ACC Shared Memory Documentation», pagine 1 e 26:
  https://www.assettocorsa.net/forum/index.php?threads/acc-shared-memory-documentation.59965/
- PyAccSharedMemory: https://github.com/rrennoir/PyAccSharedMemory
- Silicon Chip, «MoTeC Race Car Data Logging, Pt.2» (formula Oversteer di i2):
  https://www.siliconchip.com.au/Issue/2006/August/MoTeC+Race+Car+Data+logging,+Pt.2
- blekenbleu, «SimHub Oversteer» (modello a bicicletta, β, avvertenze):
  https://blekenbleu.github.io/SimHub/Oversteer
- HP Academy, sterzo e bilanciamento:
  https://hpacademy.com/courses/professional-motorsport-data-analysis/cornering-performance-steering-data-and-balance
- HP Academy, canali matematici avanzati:
  https://www.hpacademy.com/courses/professional-motorsport-data-analysis/math-channels-advanced-math-channel-uses
- HP Academy, istogramma ammortizzatori:
  https://www.hpacademy.com/courses/professional-motorsport-data-analysis/damper-analysis-damping-histogram/
- Design Judges, «Analyzing driver data»:
  https://www.designjudges.com/articles/analyzing-driver-data
- Coach Dave, MoTeC per ACC:
  https://coachdaveacademy.com/tutorials/how-to-use-motec-data-in-assetto-corsa-competizione/
- Coach Dave Delta, widget sovra/sottosterzo:
  https://coachdaveacademy.com/documentation/how-to-use-the-oversteer-understeer-widget/
- Paddocklink (materiale didattico, autore e provenienza non verificati):
  diagnosi, correlazione della rotazione, adattamento del pilota, metriche:
  https://paddocklink-docs.pages.dev/lms/vehicle-dynamics-and-setup/making-setup-changes/diagnosing-handling/
  https://paddocklink-docs.pages.dev/lms/data-interpretation-ii-advanced/rotational-data/rotation-correlation/
  https://paddocklink-docs.pages.dev/lms/race-car-mechanic-reference/diagnose-track-symptoms/separate-driver-adaptation-from-car-change/
  https://paddocklink-docs.pages.dev/lms/telemetry-systems-engineering/math-channels-and-derived-signals/aero-and-performance-metrics/
- Wikipedia, «Understeer and oversteer» (definizioni SAE J670 / ISO 8855):
  https://en.wikipedia.org/wiki/Understeer_and_oversteer
- Your Data Driven, bilanciamento (solo quadro concettuale, nessuna formula):
  https://www.yourdatadriven.com/fixing-poor-racecar-handling-balance/

Solo estratti dei risultati di ricerca (non lette):

- Forum MoTeC, «Oversteer maths formula»: https://forum.motec.com.au/viewtopic.php?p=7621
- VBOX, «Oversteer-Understeer Analysis in Tyre Testing» (403)
- Rennlist, «Understeer/Oversteer Visualization» (403)
- Fanatec, traccia dello sterzo: https://www.fanatec.com/us/en/explorer/products/steering-wheel/steering-input-telemetry/
- Manuale Ford GT GT3: https://www.manualslib.com/manual/2121387/Ford-Gt-Gt3.html?page=13
- Brevetto GM sul guadagno d'imbardata: https://www.freepatentsonline.com/y2009/0182476.html
- Formula del gradiente: https://formuladen.com/en/steer-angle-given-understeer-gradient-formula/Formula-37140
- Temperature gomme (forum): https://www.corvetteforum.com/forums/autocrossing-and-roadracing/4245541-tire-temperature-interpretation.html

Cercate e non ottenute:

- Segers, «Analysis Techniques for Racecar Data Acquisition» (solo scheda SAE:
  https://saemobilus.sae.org/content/R-408)
- OptimumG / Racecar Engineering, settembre 2019 (PDF a immagine):
  https://optimumg.com/wp-content/uploads/2020/03/RCE-2019-September.pdf
- Racecar Engineering, «Dynamic Drive Part Two» (canale di sterzo neutro): 404
- Documentazione Kunos v1.8.12 in PDF; note di fisica ACC 1.9
- Driver61: nessuna pagina propria raggiunta, solo riassunti di terzi
- Coefficiente benzina→tempo sul giro per ACC: nessuna fonte

Misure del progetto: `TARATURE-ACC.md`, `src/accoach/telemetry/structs.py`,
`src/accoach/telemetry/reader.py`.
