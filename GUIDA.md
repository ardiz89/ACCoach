# Guida a ACCoach — il tuo ingegnere di pista in tempo reale

ACCoach è un **coach di guida in tempo reale** per **Assetto Corsa** e **Assetto
Corsa Competizione**. Mentre giri ti parla (voce italiana) e ti mostra un overlay
con il distacco dal tuo giro migliore; a fine sessione ti fa un debrief e un'analisi
dettagliata nel browser. Non serve configurare nulla nel gioco: legge la telemetria
direttamente dalla memoria condivisa di AC/ACC.

Questa guida ti porta dall'avvio al primo giro coachato, fino all'analisi.

---

## 1. Cosa ti serve

- **Assetto Corsa** o **Assetto Corsa Competizione** installato.
- **ACCoach**, in uno dei due modi:
  - **Eseguibile** (consigliato per usarlo): apri `ACCoach.exe` (o doppio clic su
    `ACCoach.bat`). Non serve Python.
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
3. **Apri ACCoach.** Si apre il **Launcher**, una finestra con un pulsante per ogni
   funzione. Premi **▶ Live (coach + overlay)**.

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

---

## 4. Leggere l'overlay

- **Barra del delta**: si riempie a **destra in rosso** se sei più lento del
  riferimento, a **sinistra in verde** se sei più veloce.
- In alto: il tuo **PB**, il **tempo previsto** se mantieni il passo.
- Una **pastiglia** mostra l'ultimo consiglio pronunciato, e sfuma da sola.
- Stati dedicati per "in attesa del gioco" e "nessun riferimento ancora".

---

## 5. Analisi & Report (nel browser)

Finita la sessione, rivedi tutto con calma:

- Dal Launcher: **📊 Analisi & Report (browser)**, oppure
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

> Vuoi solo provarlo senza gioco? `python -m accoach web --demo` carica dati finti.

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
  tu in pista (stato LIVE) in una sessione. ACCoach legge la memoria condivisa solo
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
