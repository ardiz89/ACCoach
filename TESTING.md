# ACCoach — Piano di test

Guida pratica per testare tutto. Spunta man mano. Per ogni problema annota:
**cosa facevi**, **cosa è successo**, **cosa ti aspettavi** (e auto/pista se live).

---

## 0. Prerequisiti

- [ ] Gioco impostato in **Borderless / Windowed** (NON fullscreen esclusivo),
      altrimenti l'overlay non si disegna sopra (la voce funziona comunque).
- [ ] Volume di sistema su (la voce del coach è già al massimo).
- [ ] I dati vivono in **`C:\Users\<tu>\Documents\ACCoach\laps`** (creata al 1° giro salvato).

## 1. Avvio / Launcher

- [ ] Doppio click su **`ACCoach.bat`** (o `dist\ACCoach\ACCoach.exe`).
- [ ] Si apre la finestra **Launcher** con i pulsanti: Coach Live, Coach Live DEMO,
      Analisi & Report, Debrief, Monitor, Coach vocale, Verifica assi G.
- [ ] Atteso: finestra leggibile, pulsanti cliccabili.

## 2. Demo senza gioco (verifica veloce overlay + voce)

- [ ] Launcher → **Coach Live — DEMO**.
- [ ] Atteso: overlay in alto-centro con **delta bar** che si muove (~+0.4s),
      header PB/PRED, e **voce** che dice cue ("Bloccaggio…", "Porta più velocità…").
- [ ] Verifica che la voce suoni **neurale** (più umana), non robotica.
- [ ] Chiudi la finestra/overlay quando hai visto.

## 3. Voce — self test

- [ ] Da terminale: `dist\ACCoach\ACCoach.exe selftest` (o `python -m accoach selftest`).
- [ ] Ascolta: prima frase **neurale** ("Puoi frenare più tardi"), poi SAPI5 ("Self test completato").
- [ ] Il report è in `%TEMP%\accoach_selftest.json`: deve avere `is_audio: true`,
      `prerendered_cues: 41`.

## 4. Coach Live — il cuore (con AC o ACC)

**Setup:** avvia il gioco, Launcher → **Coach Live**, entra in una sessione (Practice/Hotlap).

### 4a. Eventi immediati (anche al 1° giro, senza riferimento)
Fai **apposta** questi errori e verifica che il coach parli (voce + pillola overlay):
- [ ] **Bloccaggio**: frena fortissimo → "Bloccaggio, alleggerisci il freno".
- [ ] **Pattinamento**: gas brusco in uscita lenta → "Pattini in uscita, meno gas".
- [ ] **Sottosterzo**: entra troppo forte, l'anteriore scivola → "L'anteriore scivola, entra più piano".
- [ ] **Sovrasterzo**: fai scivolare il posteriore → "Sovrasterzo, sii più dolce col gas". ⚠️ vedi §8.
- [ ] **Marcia lunga / limiter**: tieni una marcia troppo alta / resta sul limitatore.
- [ ] **Coasting**: lascia un buco tra freno e gas → "Stai veleggiando…".

### 4b. Stato overlay senza riferimento
- [ ] Overlay mostra "REC ● sto imparando il riferimento…" finché non completi un giro.

### 4c. Coaching per curva (dal 2° giro)
- [ ] **Completa un giro valido** (intero, senza tagli) → diventa il riferimento.
- [ ] Da lì la **delta bar si muove** (rosso = più lento, verde = più veloce).
- [ ] Cue di curva **anticipati prima della curva**: "Puoi frenare più tardi",
      "Più gas qui", "Porta più velocità in curva", "Stai perdendo N decimi qui".
- [ ] Quando **sistemi** una curva, il coach **smette** di ripeterti quel consiglio.

### 4d. Carburante (giri lunghi)
- [ ] Con poca benzina: "Benzina per circa N giri." → "Ultimo giro, rientra ai box!".

### 4e. Stati / robustezza
- [ ] **Box**: entra ai box → il coach tace, overlay si calma.
- [ ] **Disconnessione**: chiudi/esci dalla sessione → overlay "in attesa del gioco…".
- [ ] Riconnessione automatica quando rientri in pista.

## 5. App Analisi & Report (browser)

Dopo aver registrato **qualche giro reale**:
- [ ] Launcher → **Analisi & Report** → si apre il browser su `localhost:8778`.
- [ ] Menu **Auto / Pista**: mostra le tue combo coi giri registrati.
- [ ] **Tab Confronto**: seleziona "Giro da rivedere" e "Confronta con"; verifica
      grafici **delta / velocità (tu vs confronto) / gas-freno** con bande curva.
- [ ] **Crosshair**: muovi il mouse sui grafici → barra coi valori punto-per-punto.
- [ ] **Export**: pulsanti ⬇ CSV / ⬇ JSON → scaricano il file del giro selezionato.
- [ ] **Tab Andamento**: trend tempi nel tempo, costanza (σ/spread), errori ricorrenti.

## 6. Debrief

- [ ] Launcher → **Debrief** (o `ACCoach.exe debrief`) → riepilogo testuale
      dell'ultimo giro: curve peggiori + causa + costanza.

## 7. Multi-gioco

- [ ] Ripeti il §4 con **Assetto Corsa Competizione** (oltre ad AC) — stessa
      shared memory, dovrebbe funzionare uguale; in ACC compaiono anche i dati TC/ABS.
- [ ] (Altri giochi: non supportati ancora.)

## 8. Calibrazioni ancora da validare ⚠️ (annota i falsi positivi)

Queste soglie/segni sono **provvisori**: durante i test §4, segnala se senti
allarmi **sbagliati** — sono il feedback per tararli.
- [ ] **Sovrasterzo**: se in una curva **pulita** (senza scivolare) dice "Sovrasterzo",
      annotalo (il segno yaw o la soglia vanno aggiustati).
- [ ] **Sottosterzo**: se dice "entra più piano" mentre sei al limite e vai bene, annotalo.
- [ ] **Pressioni / temperature gomme**: i target di default sono da **GT3** → su
      altre auto i consigli psi/°C possono essere sbagliati; annota.
- [ ] **Assi G** (`Verifica assi G` / `verify-g`): rifallo in **ACC** se testi ACC
      (in AC è già confermato).
- [ ] **Livelli aid TC/ABS**: vanno validati in **ACC con una GT3** (l'HUD mostra i
      livelli) — chiedimi la cattura `calib_yaw_aids` quando sei pronto.

---

## Riepilogo rapido (ordine consigliato)

1. Demo (§2) → 2. Self test voce (§3) → 3. Coach Live eventi (§4a) →
4. Giro completo + coaching curva (§4c) → 5. Analisi web (§5) → 6. Debrief (§6) →
7. ACC (§7) → 8. Annota i falsi positivi (§8).

Riportami cosa funziona e cosa no: per i problemi di coaching, dimmi auto/pista,
il cue sbagliato e cosa stavi facendo.
