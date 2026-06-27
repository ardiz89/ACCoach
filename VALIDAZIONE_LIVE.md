# Validazione live ACCoach

Checklist da fare **una volta**, col gioco avviato e tu **in pista in una sessione LIVE**
(non menu, non replay, non in pausa). Conferma che ACCoach legga bene la shared
memory del gioco vero. Lancia i comandi dalla root del progetto.

Ogni strumento si ferma con **Ctrl+C**, che stampa il verdetto.

---

## 1. Assi G — `verify-g`
```
python -m accoach verify-g
```
In rettilineo: **frena forte** alcune volte. Poi: tieni una **curva costante** (senza freno).
Ctrl+C → atteso `✓ accel_g mapping CONFIRMED`.
Se ✗ → gli assi accG in `reader.py`/`lap.py` vanno rivisti.

## 2. Segno dello yaw — `verify-yaw`
```
python -m accoach verify-yaw
```
Fai un paio di **curve pulite a sinistra e a destra** (fuori dai freni, senza slide) —
servono ≥10 frame per lato, quindi bilancia bene sinistra/destra.
Ctrl+C → su questo gioco lo yaw è segnato all'opposto dello sterzo, quindi il
risultato atteso è il ramo `✗ ... Set _YAW_SIGN = -1.0` — che **conferma** il valore
già impostato in `balance.py` (serve per il rilevamento sovrasterzo).
Validato live 2026-06-28: 157/157 frame a segno opposto → `-1.0` confermato.

## 3. Livelli aiuti (solo ACC) — `verify-aids`
```
python -m accoach verify-aids
```
In auto, **ruota le manopole**: TC, ABS, mappa motore, brake bias.
Ogni valore deve **muoversi** e combaciare con l'HUD in-car.
Valori fermi a `-1` → offset graphics in `structs.py` da correggere.

## 4. Settori reali — `verify-sectors`  ⬅️ il nuovo
```
python -m accoach verify-sectors
```
Guida **un giro intero e pulito** (meglio due).
Ogni cambio settore stampa posizione + tempo del confine. Ctrl+C → verdetto:
- `✓ settori OK` → la vista **Settori** userà gli split reali del gioco
- `✗ current_sector sempre -1` → offset `currentSectorIndex` sbagliato → fallback ai terzi
- `? sector_count 0` → i confini funzionano comunque (dalle transizioni)

## 5. Registra un giro vero (valida Mappa + Settori sui dati reali)
```
python -m accoach recorder      # registra e basta
# oppure: python -m accoach live   (coach + overlay) — gioco in BORDERLESS, non fullscreen esclusivo
```
Guida qualche giro valido, poi chiudi. I giri finiscono in
`~/Documents/ACCoach/laps`.

## 6. Controlla nel report (browser)
```
python -m accoach web
```
Si apre `http://127.0.0.1:8778`. Seleziona auto+pista, poi:
- **Mappa** → il tracciato disegnato deve avere la forma giusta del circuito,
  con linea colorata per delta e punti di frenata (i giri **nuovi** hanno le coordinate).
- **Settori** → in alto deve dire **"reali della pista"** e i tempi settore devono
  avere senso; controlla il **Giro ideale**.

---

### Note
- Mappa e Settori reali compaiono solo sui giri registrati **dopo** gli aggiornamenti
  di oggi (schema v4). I 9 giri Imola vecchi restano senza mappa / a terzi.
- Gioco in modalità **borderless** se usi l'overlay (le finestre trasparenti non si
  disegnano sopra il fullscreen esclusivo).
- Se qualcosa è ✗, segna quale e lo sistemiamo: di solito è un offset in
  `telemetry/structs.py`.
