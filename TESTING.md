# HONE — la prova a mano, prima di dare l'app a qualcuno

Questo è il giro di controllo veloce: si fa **senza pista**, in mezz'ora, e serve
a scoprire se l'installazione è sana prima di far salire qualcuno in macchina.

**Non è il piano delle prove in pista.** Quello vive dentro l'app, alla pagina
`/test` (Analisi & Report → `localhost:8778/test`): sono 58 prove divise in GT3,
Formula, Stradali e Generale, pensate per essere spuntate da un tablet mentre
guidi, e si salvano da sole in `Documenti/ACCoach/test_runs/`.

Per ogni problema annota **cosa facevi**, **cosa è successo** e **cosa ti
aspettavi** — e se eri in macchina, auto e pista. Poi manda il pacchetto dei log
(§8): senza quello, «non ho sentito niente» e «era rotto e non l'ha detto» si
leggono uguali.

---

## 0. Prerequisiti

- [ ] Gioco in **Borderless / Windowed**, non fullscreen esclusivo, altrimenti
      l'overlay non si disegna sopra (la voce funziona lo stesso).
- [ ] Volume di sistema acceso.
- [ ] I dati vivono in **`Documenti\ACCoach\`** — la cartella nasce al primo
      giro salvato, quindi al primo avvio è normale che non ci sia.

## 1. Avvio

- [ ] Doppio click su **`HONE.bat`** (dal sorgente: al primo avvio si crea da
      sola la `.venv` e installa tutto, ci mette qualche minuto) oppure su
      **`dist\HONE\HONE.exe`** se hai costruito l'eseguibile.
- [ ] Si apre il **Launcher** con sei sezioni nella barra a sinistra: *Home*,
      *In pista*, *Analisi*, *Setup*, *Dispositivi*, *Impostazioni*.
- [ ] Al primo avvio in assoluto compare la finestrella «Come si comincia».
- [ ] Atteso: finestra leggibile, testi non troncati, pulsanti cliccabili.

## 2. Demo senza gioco — la verifica più veloce che esista

- [ ] *In pista* → **Coach Live — DEMO (senza gioco)**.
- [ ] Atteso: overlay in alto sullo schermo centrale, con la **barra del delta**
      che si muove, l'intestazione PB/PRED, e la **voce** che dice i cue
      («Bloccaggio…», «Porta più velocità…»).
- [ ] La voce deve suonare **neurale**, non robotica. Se suona robotica su
      *tutte* le frasi, i cue pre-registrati non sono stati caricati → §3.

## 3. Voce — self test

- [ ] Da terminale: `python accoach_main.py selftest` (o `HONE.exe selftest`).
- [ ] Ascolta: prima una frase **neurale**, poi una SAPI5 («Self test
      completato»). Due voci diverse: è così apposta, sta provando due strade.
- [ ] Il report è in `%TEMP%\accoach_selftest.json`. Deve avere `is_audio: true`
      e **`prerendered_cues: 54`**.
- [ ] Se `prerendered_cues` è **0**, il pacchetto ha perso i cue: è il difetto
      che degrada in silenzio, non ignorarlo. Se è un numero diverso da 54,
      confrontalo con i file in `src/accoach/voice_cues/` — devono coincidere.

## 4. Coach Live — il cuore (serve AC o ACC)

Avvia il gioco, poi *In pista* → **Coach Live**, ed entra in una sessione.

### 4a. Eventi immediati (già al primo giro, senza riferimento)
Sbaglia **apposta** e verifica che il coach parli (voce + pastiglia sull'overlay):
- [ ] **Bloccaggio**: frenata fortissima → «Bloccaggio, alleggerisci il freno».
      ⚠️ Con l'**ABS acceso il bloccaggio fisico non avviene**: per provarlo
      davvero l'ABS va messo a 0 (misurato il 02/08 su 11 690 frame).
- [ ] **Pattinamento**: gas brusco in uscita lenta.
- [ ] **Sottosterzo** / **Sovrasterzo** (vedi §9: sono le due soglie più fragili).
- [ ] **Coasting**: lascia un buco fra freno e gas → «Stai veleggiando…».

### 4b. Senza riferimento
- [ ] L'overlay mostra «REC ● sto imparando il riferimento…» finché non chiudi
      un giro valido.

### 4c. Coaching per curva (dal 2° giro)
- [ ] Chiudi un giro valido → diventa il riferimento, e la **barra del delta si
      muove** (rosso = più lento, verde = più veloce).
- [ ] I consigli di curva arrivano **prima** della curva, non dentro.
- [ ] Quando **sistemi** una curva, il coach smette di ripetertelo.

### 4d. Il focus — un tema alla volta
- [ ] Dopo tre giri **puliti** il coach elegge un tema e da lì parla quasi solo
      di quello (è il budget di attenzione: accorcia, non dirada).
- [ ] Se giri sporco, il focus **non elegge** — e ora lo dice: nel log trovi
      `focus | nessuno | stato=assess | non contato: giro non pulito | scartati=N`.
      Se resti in `assess` senza capire perché, la risposta è lì.

### 4e. Carburante e box
- [ ] Con poca benzina: «Benzina per circa N giri» → «Ultimo giro, rientra ai box!».
- [ ] Rientra ai box e **fermati**: arriva il briefing, che ti manda sulla pagina
      Ingegnere. Da Coach Live quella pagina va aperta come descritto in §5.

### 4f. Robustezza
- [ ] Esci dalla sessione → overlay «in attesa del gioco…», e riconnessione
      automatica quando rientri.

## 5. Lo scambio al Backend live — **da guardare a occhio, è nuovo**

La pagina Ingegnere la alimenta solo il **Backend live**, che non può girare
insieme a Coach Live (due motori salverebbero ogni giro due volte).

- [ ] Con Coach Live acceso, premi **Ingegnere di pista**: il bottone **non**
      deve essere spento e muto. Si apre una finestra che spiega perché, e offre
      tre strade: *Ferma Coach Live e passa* · *Apri comunque la pagina* ·
      *Lascia acceso Coach Live*.
- [ ] Verifica che il testo si legga tutto, senza troncature, anche in italiano.
- [ ] **Apri comunque**: la pagina si apre, Coach Live **resta acceso** e
      l'overlay resta al suo posto. Hai l'editor assetti e i setup salvati; la
      diagnosi dal vivo resta vuota, ed è quello che la finestra ti ha detto.
- [ ] **Ferma e passa**: Coach Live si chiude, parte il Backend live e si apre
      la pagina. ⚠️ **L'overlay si spegne**: si riaccende da *Dispositivi* →
      *Solo overlay*. Se compare invece «Coach Live è ancora acceso», nessun
      backend è partito — è la protezione che ha funzionato, riprova dopo che la
      finestra si è chiusa.

## 6. Analisi & Report (browser)

Dopo aver registrato qualche giro vero: *Analisi* → **Analisi & Report**, si apre
`localhost:8778`.

- [ ] Il menu **Auto / Pista** mostra le tue combo.
- [ ] Le dieci schede si aprono tutte: *Com'è andata*, *Il giro spiegato*,
      *Allenamento*, *Sessione*, *Passo gara*, *Confronto*, *Traiettoria*,
      *Settori*, *Dinamica*, *Andamento*. Si aprono anche coi tasti **1-9 e 0**.
- [ ] In *Confronto*: grafici delta / velocità / gas-freno, il **crosshair** che
      segue il mouse, e i pulsanti **⬇ CSV / ⬇ JSON**.
- [ ] Una scheda senza abbastanza dati deve **dire quanti giri mancano**, mai
      restare vuota.

## 7. Ingegnere di pista

- [ ] *Setup* → **Ingegnere di pista** (o §5 se Coach Live è acceso).
- [ ] La pagina sa dirti auto e pista anche a gioco spento.
- [ ] ⚠️ ACC crea la cartella degli assetti **solo quando ne salvi uno**: se la
      pagina dice che non trova setup, salvane uno dal gioco e riprova. Non è un
      difetto dell'app.

## 8. Il pacchetto dei log — fallo sempre, prima di segnalare

- [ ] `python accoach_main.py logs --zip` (o `HONE.exe logs --zip`).
- [ ] Stampa il percorso dello ZIP **e** un riassunto di cosa c'è dentro.
- [ ] **Leggi quel riassunto prima di mandarlo a qualcuno.** I log entrano non
      filtrati: contengono percorsi col tuo nome utente di Windows, una riga
      datata per ogni volta che hai avviato HONE, i tuoi tempi sul giro e i
      rapporti di crash. È scritto anche in `contesto.txt` dentro lo ZIP.
- [ ] `logs` senza `--zip` continua ad aprire solo la cartella.

## 9. Le soglie ancora fragili — annota i falsi allarmi

Queste non sono ancora tarate su tutto. Durante il §4, segnala quando il coach
si sbaglia: è l'unico modo per tararle.

- [ ] **Sovrasterzo** su una curva pulita, senza scivolare.
- [ ] **Sottosterzo** («entra più piano») mentre sei al limite e vai bene.
- [ ] **Pressioni / temperature gomme**: i bersagli di default sono da **GT3**,
      su altre auto i consigli psi/°C possono essere sbagliati.
- [ ] **Assi G**: `verify-g` è confermato su AC; in ACC va rifatto.
- [ ] **Formula e Stradali**: 24 delle 58 prove del piano `/test` non hanno
      ancora un esito, e sono tutte lì. Se guidi quelle classi, sei tu il primo.

---

## L'ordine consigliato

Demo (§2) → self test voce (§3) → eventi (§4a) → giro completo e coaching di
curva (§4c) → focus (§4d) → scambio al backend (§5) → analisi web (§6) →
pacchetto log (§8).

Se una cosa non funziona, la domanda utile non è «funziona?» ma **«cosa hai
visto e cosa ti aspettavi di vedere?»** — con il pacchetto dei log allegato.
