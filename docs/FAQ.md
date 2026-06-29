# ACCoach — Domande frequenti

Indice rapido: [Requisiti](#requisiti) · [Installazione](#installazione) ·
[SmartScreen e verifica SHA-256](#smartscreen-e-sicurezza) · [Privacy](#privacy) ·
[Overlay](#overlay) · [Free vs Pro](#free-vs-pro) · [Problemi comuni](#problemi-comuni)

---

## Requisiti

- **Windows.** AC e ACC pubblicano la telemetria via shared memory, che esiste
  solo su Windows.
- **Assetto Corsa** oppure **Assetto Corsa Competizione**.
- Per l'overlay: gioco in modalità **Borderless** (finestra senza bordi).
- Solo se esegui **da sorgente**: Python 3.11+ e `pip install -r requirements.txt`.
  Con l'eseguibile non serve nulla.

## Installazione

### Eseguibile (consigliato)

1. Scarica `ACCoach.exe` (o lo zip) dalla pagina
   [Releases](https://github.com/ardiz89/ACCoach/releases).
2. Avvialo. Al primo avvio Windows può mostrare un avviso SmartScreen
   (vedi sotto).
3. Scegli la modalità dal launcher, oppure da terminale:
   `ACCoach.exe live`, `ACCoach.exe web`, ecc.

### Da sorgente

```powershell
git clone https://github.com/ardiz89/ACCoach.git
cd ACCoach
pip install -r requirements.txt
python -m accoach live        # coach + overlay
python -m accoach             # elenca tutti i comandi
```

## SmartScreen e sicurezza

Al primo avvio Windows può dire *"Windows ha protetto il PC"* (Microsoft
Defender SmartScreen). **È normale e non significa che il file sia infetto.**

Succede perché l'eseguibile non è firmato con un certificato di code-signing a
pagamento (centinaia di euro l'anno): senza "reputazione" accumulata, SmartScreen
avvisa per qualsiasi app nuova di un autore indipendente.

Per avviarlo: clicca **"Ulteriori informazioni"** → **"Esegui comunque"**.

### Verificare l'integrità del file (SHA-256)

Ogni release pubblica l'hash SHA-256 dell'eseguibile. Confrontalo con quello del
file che hai scaricato: se coincidono, il file è esattamente quello pubblicato.

In PowerShell:

```powershell
Get-FileHash .\ACCoach.exe -Algorithm SHA256
```

Confronta la stringa con quella indicata nella release. Se sono diverse, **non
eseguire il file** e riscarica dalla pagina ufficiale delle Releases.

## Privacy

ACCoach è **100% offline**. Concretamente:

- Nessun account, nessun login.
- Nessuna connessione di rete in uscita: la telemetria, i giri e le analisi non
  lasciano mai il tuo PC.
- I dati sono salvati localmente in `Documenti\ACCoach\` (giri in `laps\`,
  log in `logs\`, configurazione in `config.toml`).
- I server locali (`web` su `127.0.0.1:8778`, backend su `127.0.0.1:8777`) sono
  in ascolto solo su `localhost` — la tua macchina — e servono a far parlare le
  varie parti dell'app tra loro, non a Internet.

Puoi cancellare tutto in qualsiasi momento svuotando la cartella `Documenti\ACCoach\`.

## Overlay

L'overlay è trasparente, sempre in primo piano e *click-through* (non ruba i clic
al gioco).

- **Non si vede sopra il gioco?** Imposta il gioco in **Borderless**. Un overlay
  trasparente non può disegnare sopra il *fullscreen esclusivo* — stesso vincolo
  di SimHub e Crew Chief.
- **Spostarlo o chiuderlo:** avvialo con `--interactive`, oppure chiudi il
  terminale che l'ha lanciato (`Ctrl+C`).

## Free vs Pro

Modello **freemium one-time** (nessun abbonamento). Oggi è tutto disponibile
gratis mentre il prodotto cresce con la community.

| Funzione | Free | Pro (in arrivo) |
|---|:---:|:---:|
| Coach a voce + overlay | ✅ | ✅ |
| Debrief col "perché" + analisi web | ✅ | ✅ |
| Ingegnere di pista (setup AI) | — | ✅ |
| Focus/Lesson (piano di allenamento) | — | ✅ |
| Reference PRO importabili | — | ✅ |

Il Pro sarà un acquisto una tantum. Il modello potrà cambiare prima del lancio.

## Problemi comuni

**"In attesa del gioco…" e non si connette.**
Avvia AC/ACC ed entra in una sessione (prova/hotlap/gara). ACCoach si collega
appena il gioco inizia a pubblicare la telemetria.

**Non ho un giro di riferimento.**
Guida almeno un giro valido: diventa il riferimento. Oppure importa un giro PRO
come seme: `python -m accoach import-reference <file.lap.json.gz>`.

**La voce non parla.**
Avvia con la voce attiva (default) anziché `--silent`. Le frasi fisse usano una
voce neurale pre-renderizzata; quelle numeriche ripiegano sulla voce di sistema.

**Dove sono i log se qualcosa va storto?**
`python -m accoach logs` apre la cartella con log e crash report.

---

Altre domande? Apri una [issue su GitHub](https://github.com/ardiz89/ACCoach/issues).
