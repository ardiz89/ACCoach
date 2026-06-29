# ACCoach

**Il coach di guida in tempo reale per Assetto Corsa e ACC — in italiano, 100% offline.**

ACCoach legge la telemetria mentre guidi, capisce *dove* perdi tempo e soprattutto
*perché*, te lo dice a voce e con un overlay a schermo, poi a fine sessione ti
spiega ogni curva e — quando vuoi — ti riscrive il setup dell'auto, giro dopo giro.

> 🏁 Gratis e completo. Gira tutto sul tuo PC: nessun account, nessun cloud,
> nessun dato che lascia la tua macchina.

<!-- TODO: GIF "wow" qui — overlay + voce durante un giro, poi il debrief col "perché". -->
<!-- ![ACCoach in azione](docs/assets/demo.gif) -->

---

## Perché ACCoach è diverso

Esistono ottimi strumenti per il sim racing (overlay, spotter, analisi cloud).
ACCoach non compete su quelli: punta su tre cose che gli altri non fanno insieme.

1. **Ti dice il *perché*, non solo il *cosa*.** Non "freni tardi" e basta, ma
   *"l'auto sottosterza all'apex in curva lenta: porta più velocità in ingresso"*.
   Diagnosi causale del comportamento (sotto/sovrasterzo × ingresso/apex/uscita ×
   velocità), frenata scomposta (di quanti metri anticipi, picco freno), e perdita
   sul rettilineo attribuita alla curva che l'ha causata.

2. **Un vero ingegnere di pista, anche sulle stradali.** Chiude il loop
   *telemetria → diagnosi → consiglio di setup → modifica → ri-test*: propone una
   modifica alla volta, la rivaluti in pista, la tiene solo se migliora davvero.
   Tre profili (Formula, GT3, stradali) — non solo ACC.

3. **Italiano e completamente offline.** Voce neurale in italiano, tutto sul tuo
   PC, gratis. Niente abbonamenti, niente connessione, niente telemetria spedita
   a un server.

E ti fa allenare con un **piano**: una debolezza ricorrente alla volta
(briefing → drill → progresso misurato → lode), invece di rovesciarti addosso
ogni errore insieme.

## Cosa fa

- 🎙️ **Coach a voce in tempo reale** — il suggerimento più utile, al momento
  giusto, senza parlarti sopra. Bloccaggi e pattinamenti chiamati all'istante.
- 📺 **Overlay a schermo** — barra del delta, tempo previsto, cue del momento e
  il focus su cui stai lavorando, sopra il gioco (modalità Borderless).
- 🔧 **Ingegnere di pista** — consigli di setup concreti, una leva alla volta,
  con loop di convergenza e gestione gomme/pressioni/elettronica.
- 🧠 **Focus/Lesson** — un punto debole alla volta, allenato con lode misurata
  ("Curva 4: da 0.30s a 0.07s").
- 📊 **App di analisi nel browser** — traccia, settori, mappa, debrief col perché,
  andamento nel tempo, confronto multi-livello (tuo best → ideale teorico → PRO)
  e punti deboli **sistematici** vs **sporadici**.
- 🗣️ **Debrief post-sessione** — le curve peggiori, la causa di ognuna, la tua
  costanza.

## Avvio rapido

**Con l'eseguibile (consigliato):** scarica `ACCoach.exe` dalla pagina
[Releases](https://github.com/ardiz89/ACCoach/releases), avvialo, scegli la
modalità. Nessun Python necessario. (Vedi le [FAQ](docs/FAQ.md) per l'avviso
SmartScreen al primo avvio e la verifica dell'hash.)

**Da sorgente:**

```powershell
pip install -r requirements.txt   # la prima volta (PySide6 per overlay/GUI)
python -m accoach live            # coach + overlay in un'unica finestra
python -m accoach live --demo     # provalo con un giro sintetico, senza gioco
python -m accoach                 # elenca tutti i comandi
```

Imposta il gioco in **Borderless** perché l'overlay ci si disegni sopra.
`--silent` disattiva la voce.

## Requisiti

- **Windows** (la shared memory di AC/ACC è solo Windows).
- **Assetto Corsa** o **Assetto Corsa Competizione**, in modalità **Borderless**
  per l'overlay.
- Solo da sorgente: **Python 3.11+**.

## Privacy

ACCoach è **100% offline**. Tutto — telemetria, giri registrati, analisi, voce —
resta sul tuo PC. Niente account, niente connessione di rete, niente dati inviati
a terzi. I giri sono salvati in `Documenti\ACCoach\`. Dettagli nelle
[FAQ](docs/FAQ.md#privacy).

## Free vs Pro

ACCoach segue (a regime) un modello **freemium one-time** — nessun abbonamento.
Oggi è tutto disponibile gratis mentre il prodotto matura con la community.

| | Free | Pro (in arrivo) |
|---|---|---|
| Coach a voce + overlay | ✅ | ✅ |
| Debrief col "perché" + analisi web | ✅ | ✅ |
| Ingegnere di pista (setup AI) | | ✅ |
| Focus/Lesson (piano di allenamento) | | ✅ |
| Reference PRO importabili | | ✅ |

> Il Pro sarà un acquisto una tantum, non un abbonamento. Il modello potrà
> cambiare prima del lancio: i feedback della community contano.

## Licenza

**Source-available** sotto [PolyForm Noncommercial 1.0.0](LICENSE): libero per
uso personale e non commerciale; l'uso commerciale (rivendita, prodotti/servizi a
pagamento) richiede una licenza dall'autore. Il codice è visibile per trasparenza
e studio.

## Per sviluppatori

Documentazione tecnica nel repo:

- [`GUIDA.md`](GUIDA.md) — guida d'uso completa.
- [`ENGINEER.md`](ENGINEER.md) — architettura dell'ingegnere di pista.
- [`TESTING.md`](TESTING.md) — come girano i test (`python -m pytest -q`).
- [`PIANO-CALIBRAZIONI.md`](PIANO-CALIBRAZIONI.md) — taratura delle soglie.

Struttura: il codice è in `src/accoach/` (telemetria → recording → comparison →
coaching → engine → server/overlay/web). `python -m accoach` è l'unico punto
d'ingresso; `build_exe.bat` produce l'eseguibile.
