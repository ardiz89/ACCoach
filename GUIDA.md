# Guida a HONE — il tuo ingegnere di pista in tempo reale

HONE è un **coach di guida in tempo reale** per **Assetto Corsa** e **Assetto
Corsa Competizione**. Mentre giri ti parla (voce italiana) e ti mostra un overlay
con il distacco dal tuo giro migliore; a fine sessione ti fa un debrief e un'analisi
dettagliata nel browser. Non serve configurare nulla nel gioco: legge la telemetria
direttamente dalla memoria condivisa di AC/ACC.

Questa guida ti porta dall'avvio al primo giro coachato, fino all'analisi.

---

## 1. Cosa ti serve

- **Assetto Corsa** o **Assetto Corsa Competizione** installato.
- **HONE**, in uno dei due modi:
  - **Eseguibile** (consigliato per usarlo): doppio clic su
    `HONE.bat`. Non serve Python.
  - **Da sorgente** (per chi sviluppa): Python 3.11+, poi
    `pip install -r requirements.txt`.

I tuoi giri vengono salvati in **`Documenti/ACCoach/laps`** (stessa cartella sia
dall'exe sia da sorgente), così l'analisi li ritrova sempre.

---

## 2. Avvio in 30 secondi

1. **Avvia il gioco** e mettiti in pista in una sessione di **Prove libere**
   (Practice) con l'auto e la pista che vuoi allenare.
2. **IMPOSTA IL GIOCO IN MODALITÀ BORDERLESS** (finestra senza bordi), *non*
   fullscreen esclusivo. L'overlay trasparente non si disegna sopra un fullscreen
   esclusivo: con borderless lo vedi, con fullscreen no.
3. **Apri HONE.** Si apre l'**hub**: una finestra con sei sezioni nella barra
   laterale — **Home · Guida · Analisi · Setup · Dispositivi · Impostazioni**.
   Vai su **Guida** e premi **▶ Coach Live**.

> La Home ti mostra l'ultima sessione già analizzata, quindi dopo la prima volta
> è lì che arrivi per sapere com'è andata.

Da riga di comando l'equivalente è:

```
python -m accoach live           # coach vocale + overlay, in un solo processo
```

Aggiungi `--silent` se vuoi solo l'overlay senza voce.

---

## 3. Come funziona il coaching (il flusso da seguire)

Il coach ragiona come un vero ingegnere di pista: prima **ti guarda girare**, poi
ti **corregge**. Due tipi di interventi:

### a) Eventi acuti — immediati, NON serve un giro di riferimento
Dal primo metro del primo giro ti avvisa quando sbagli *in assoluto*:
- **Bloccaggio** in frenata → «Bloccaggio, alleggerisci il freno»
- **Pattinamento** in uscita → «Pattini in uscita, meno gas»
- **Sottosterzo** → «L'anteriore scivola, entra più piano»
- **Sovrasterzo** → «Sovrasterzo, sii più dolce col gas in uscita»
- **Veleggi** (né freno né gas) o **trail-braking** assente.

### b) Consigli di curva — servono un paio di giri "puliti" prima
Per dirti *dove perdi tempo e perché*, il coach ha bisogno di un **giro di
riferimento** (il tuo più veloce valido). Quindi:

1. **Fai 2 giri puliti completi** partendo dal traguardo. Il primo giro intero
   viene salvato e diventa il riferimento.
2. Dal giro successivo il coach confronta il tuo giro col riferimento e, **in
   approccio a ogni curva**, ti anticipa il consiglio per quella curva
   («Porta più velocità in curva», «Puoi frenare più tardi», «Più gas qui»…).
   È un coach che ti parla *prima* della curva, non che brontola dopo.
3. Quando prendi bene quella curva, **smette di ripeterti** quel consiglio.
4. Ogni volta che batti il tuo riferimento, da lì in poi confronti col nuovo.

> Quando NON sei sul giro buono (rientro dai box, testacoda, fuori pista) il coach
> **tace** sui consigli tecnici e ti avvisa solo sugli eventi di sicurezza.

### c) Consigli di setup — a fine giro, ogni tanto
Tra un giro e l'altro, quando un sintomo si ripete, ti suggerisce una regolazione
(pressioni gomme, livelli TC/ABS dove regolabili, bilanciamento freni). Le
pressioni vengono giudicate solo a gomme in temperatura, sul target GT3 (~27.5 psi).

### d) Come vengono registrati i giri (e se parti dai box)
Non devi fare nulla di speciale: avvia la sessione (Pratica, Hotlap, Gara) e guida.

- Il giro viene chiuso quando **passi sul traguardo**. Lo riconosce da **due
  segnali insieme**: il contatore giri del gioco e il riavvolgimento della
  posizione. Nessuno dei due basta da solo — su ACC il contatore **non conta il
  giro di ricognizione**, e senza il secondo segnale il primo giro lanciato dopo
  ogni uscita dai box andava perso. Il tempo salvato è quello ufficiale del gioco.
- Il **primo giro è quasi sempre parziale** (hai iniziato a metà pista): viene
  scartato automaticamente. I giri salvati sono solo quelli **completi,
  traguardo→traguardo**.
- **Se parti dai box:** in garage *e in corsia box* la registrazione è in pausa;
  l'**out-lap** è parziale e viene scartata; il **primo giro lanciato** vero è il
  primo che viene salvato. Anche quando **rientri ai box** quel giro non viene
  salvato, e cambiare auto/pista azzera tutto (un giro non scavalca mai due
  sessioni).
- Due qualità indipendenti del giro: **completo** (partito dalla linea → requisito
  per essere salvato) e **pulito** (nessuna uscita dai limiti della pista). Un
  giro sporco viene salvato ma **non usato come riferimento**.
- **Come si stabilisce se è pulito dipende dal gioco**, perché i due titoli
  espongono cose diverse: su **AC** si contano le ruote fuori (3 o più = sporco),
  su **ACC** si legge il verdetto del gioco stesso sui track limits. Su ACC vale
  quindi anche un taglio senza mai mettere una ruota nell'erba. Se il gioco non
  dice niente il giro resta "sconosciuto", che non è la stessa cosa di "pulito".
- Il report ti dice anche **in che curva** hai perso il giro (es. «fuori pista
  alla Variante Ascari»). I giri registrati prima della versione 8 dello schema
  non hanno questo dato: dicono che il giro è sporco, non dove.

---

## 4. Leggere l'overlay

- **Barra del delta**: si riempie a **destra in rosso** se sei più lento del
  riferimento, a **sinistra in verde** se sei più veloce.
- In alto: il tuo **PB** — cioè *contro cosa stai correndo* — e il **tempo
  previsto** se mantieni il passo. Quando sta arrivando una staccata, quello
  spazio lo prende il **conto alla rovescia in metri**, che al momento di frenare
  diventa una sola parola rossa: **FRENA**. La soglia è in *tempo*, non in
  distanza, perché dieci metri sono 0,14 s a 250 km/h e mezzo secondo in una
  curva lenta.
- Una **pastiglia** mostra l'ultimo consiglio pronunciato, e sfuma da sola.

### Quando il delta non c'è

Il delta compare **solo sui giri che possono contare**, cioè quelli cominciati
dal traguardo. Non è un guasto: un numero che confronta la corsia box con un giro
lanciato caldo schizza oltre i +30 s e pianta la barra sul fondo scala, che si
legge come un giro disastroso invece che come nessun giro. Al suo posto trovi
sempre **il motivo**:

| Cosa leggi | Che sta succedendo |
|---|---|
| *Ai box* | sei in garage o in corsia box |
| *In ricognizione* | out-lap: il coach parte dal traguardo |
| *Nessun riferimento* | non hai ancora un giro completo su questa auto+pista |
| *Giro invalidato — continua* | il gioco ha annullato questo giro (solo ACC) |
| *Giro fuori ritmo* | qui il delta **resta**: il giro è cominciato dal traguardo |
| *Via — giro lanciato* | lampeggia quando il coach ricomincia a lavorare |

Su un **giro invalidato il coach continua a parlare**: sparisce solo il
cronometro. Un giro annullato è un giro gratis — frenate, bloccaggi, gomme e
assetto si leggono uguale, e rientrare ai box è tempo buttato.

Senza riferimento, invece, resta acceso tutto ciò che non ne ha bisogno:
sotto/sovrasterzo, veleggiamento, trail brake, marce, pressioni e temperature.
Vale la pena saperlo alla prima sessione su un'auto nuova.

---

## 5. Analisi & Report (nel browser)

Finita la sessione, rivedi tutto con calma:

- Dall'hub, sezione **Analisi**: **📊 Analisi & Report (browser)**, oppure
  ```
  python -m accoach web
  ```
  Si apre da solo `http://127.0.0.1:8778`.

Cosa trovi:
- **Confronto**: scegli auto+pista e due giri (uno da rivedere, uno di confronto).
  Tre grafici allineati alla posizione in pista — **delta sul giro**, **velocità**
  (tu vs riferimento), **gas/freno** — con le bande delle curve. Passa il mouse:
  un mirino ti dà i valori puntuali. Esporti il giro in **CSV/JSON**.
- **Andamento**: l'andamento dei tempi nel tempo, la **costanza** (migliore/media/
  scarto), e gli **errori ricorrenti** ("5× Porta più velocità in curva · Curve 1, 2").

Nella tendina dei giri, accanto al tempo, trovi **i gradi dell'asfalto** (es.
`2:03.732 · 37.8°`). Non è un dettaglio: fra pista fredda e pista calda i punti
di frenata si spostano di 10-20 metri, quindi due giri con temperature molto
diverse sono due circuiti diversi e confrontarli dice poco.

Nel debrief, **sopra** l'elenco delle curve, possono comparire uno o due riquadri
col bordo azzurro. Sono osservazioni **sull'intero giro**, non su una curva:
- *«Sollevi dove il riferimento sta in pieno»* — con quanto ti è costato, contando
  anche il rettilineo che segue;
- *«Ti mancano N km/h di punta»* — e qui la parte che conta: se in curva vai come
  il riferimento non è l'auto a essere lenta, guarda ala e rapporti; se sei più
  lento anche in curva, è velocità in uscita e l'assetto non c'entra.

### Chi diventa il riferimento

È il tuo giro più veloce su quella auto e quella pista, con due regole sopra:

- **I giri sporchi non sono mai candidabili.** Un giro tagliato è più veloce per
  un motivo.
- **La temperatura dell'asfalto conta.** Un giro fatto in condizioni simili a
  oggi batte uno un po' più veloce fatto in condizioni molto diverse. È una
  preferenza, non un filtro: se niente somiglia a oggi ti do comunque il tuo
  giro migliore, non "nessun riferimento".

Se sei lontano dal passo, il tuo miglior giro è un bersaglio che ti tiene dove
sei. Dalla sezione **Analisi** puoi importare un **giro di riferimento PRO** più
veloce, e da lì in poi il coach ti misura su quello.

> Vuoi solo provarlo senza gioco? `python -m accoach web --demo` carica dati finti.

### Aprire su telefono / tablet (stessa rete)

Comodo se giochi in triple monitor e vuoi il **Report** o l'**Ingegnere** su un
dispositivo a fianco:

1. Nell'hub, sezione **Dispositivi**, attiva e spunta **"Consenti l'accesso
   dagli altri dispositivi in rete"** (si ricorda nel config).
2. Compaiono due **QR code** — **Report** e **Ingegnere** — con sotto l'indirizzo
   (es. `http://192.168.1.23:8778`). **Inquadra il QR** col telefono, oppure
   digita l'indirizzo nel browser.

Note pratiche:
- Il telefono dev'essere sulla **stessa Wi-Fi / rete** del PC.
- Se **Windows** chiede il permesso al primo avvio, **consenti su reti private**.
- Il **Report** (giri salvati) basta avere aperto `web`. L'**Ingegnere in tempo
  reale** richiede anche il backend `server` attivo (lo scenario "secondo schermo").
- Lasciato spento, tutto resta solo-locale (`127.0.0.1`) come prima.

---

## 6. Debrief post-sessione (testo)

Per un riassunto rapido a fine sessione:

```
python -m accoach debrief [auto] [pista]
```

Ti elenca le curve dove hai perso più tempo, con la causa, e la tua costanza. Legge
i giri salvati: il gioco non deve essere aperto.

---

## 7. Tutti i comandi

`python -m accoach <comando>` (o i corrispettivi `run_*.py`):

| Comando | A cosa serve |
|---|---|
| `live [--silent]` | **Coach vocale + overlay** in un processo (uso normale) |
| `coach [--silent]` | Coach vocale nel terminale (senza overlay) |
| `launcher` | La finestra con i pulsanti |
| `web [--demo]` | App di analisi nel browser |
| `server [--demo]` | Backend headless (overlay/più schermi come client) |
| `overlay [--interactive]` | Solo l'overlay (si collega al server) |
| `debrief [auto] [pista]` | Debrief testuale post-sessione |
| `monitor` | Cruscotto della telemetria grezza |
| `recorder` | Registra solo i giri (niente coaching) |
| `compare` | Cruscotto del delta live |
| `verify-g` | Verifica gli assi delle forze G col gioco |
| `selftest` | Controlla che la voce/TTS funzioni |

---

## 8. Consigli per usarlo al meglio

- **Posa un buon riferimento**: i primi 2 giri falli puliti, è il metro su cui ti
  giudicherà. Un riferimento sporco = consigli sporchi.
- **Borderless sempre**, se vuoi l'overlay.
- **Un'auto/pista per volta**: il riferimento è specifico per combinazione.
- Se il coach ti distrae mentre impari un tracciato, usa `--silent` e guarda solo
  l'overlay; riattiva la voce quando vuoi i consigli.
- Rivedi gli **errori ricorrenti** nell'Andamento: è lì che migliori il passo.

---

## 9. Risoluzione problemi

- **"Resta in attesa del gioco" / non si connette** → il gioco dev'essere aperto e
  tu in pista (stato LIVE) in una sessione. HONE legge la memoria condivisa solo
  mentre il gioco gira.
- **Non vedo l'overlay** → sei in fullscreen esclusivo. Passa a **borderless**.
- **Non sento la voce** → lancia `python -m accoach selftest` (o il pulsante): scrive
  un report e prova a parlare. Da sorgente, assicurati di aver fatto
  `pip install pyttsx3`. Serve una voce italiana di sistema (es. "Microsoft Elsa").
- **Nessun consiglio di curva** → ti manca il riferimento: fai 2 giri puliti
  completi. (Gli eventi acuti invece arrivano comunque.)
- **L'analisi non mostra i giri** → guidali prima in modalità live/recorder; finiscono
  in `Documenti/ACCoach/laps`, da cui l'app di analisi legge.

---

Buon divertimento — e occhio ai bloccaggi. 🏁
