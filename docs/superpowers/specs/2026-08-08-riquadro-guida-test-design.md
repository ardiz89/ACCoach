# Il riquadro che guida i test in pista

**Data:** 2026-08-08 · **Stato:** progetto approvato, da implementare

## Il problema

Durante la sessione del 07/08 il pilota ha detto la frase che dà origine a questo
lavoro: *«non mi ricordo a memoria tutti questi passaggi»*. Il protocollo di test
lo guidavo io a voce, un passo alla volta, e funzionava — ma fra un passo e
l'altro il pilota non aveva **nessun posto dove guardare** per ricordarsi cosa
stava facendo, con quali impostazioni e quanto mancava.

Il vincolo che rende il problema non banale è la regola nata da un incidente vero
il 02/08 (`TARATURE-ACC.md:280-287`): quello che serve in movimento si dice **a
voce**; quello che richiede una risposta si fa da **fermi**. Il pilota non può
leggere una chat né riferire cosa vede mentre guida. Un riquadro sullo schermo
non viola la regola solo se è un **promemoria** e non un canale: deve essere
leggibile con la coda dell'occhio e non deve mai chiedere niente.

## Cosa costruiamo

Una finestra piccola, in alto a sinistra dello schermo centrale, che mostra il
passo di protocollo in corso: dove sei, cosa fare, con quali impostazioni,
quanto manca. A passo finito diventa verde e resta verde finché non arriva il
successivo.

```
┌──────────────────────────────────┐      ┌──────────────────────────────────┐
│ PASSO 3 / 7                      │      │ PASSO 3 / 7                      │
│ BLOCCAGGI                        │  →   │ ✓ FATTO — BLOCCAGGI              │
│ Frena fortissimo in staccata,    │      │ Aspetta il prossimo passo        │
│ fino a far raschiare le ruote    │      │                                  │
│ ABS 0 · TC 6 · gomme calde       │      │                                  │
│ ⏱ 12:47                          │      │                                  │
└──────────────────────────────────┘      └──────────────────────────────────┘
```

## Decisione di fondo: il riquadro è uno schermo, non un giudice

Il riquadro **non contiene nessuna regola di protocollo**. Non sa cos'è un
bloccaggio, non conta i giri, non decide quando un passo è finito. Testo e
avanzamento li scrive Claude da fuori, che durante la sessione sta già guardando
telemetria, giri e schermo.

La conseguenza è che il riquadro funziona per **qualsiasi** test, compreso uno
inventato lì per lì — che è esattamente com'è andata il 07/08, quando la
semantica di `verify-aids` su ACC è stata chiusa di sbieco perché il pilota stava
girando una manopola per un altro motivo.

L'alternativa scartata era far misurare al codice le condizioni di completamento.
Costa regole nuove per ogni test, copre solo ciò che sappiamo misurare, e
soprattutto non sa rispondere alla domanda che conta davvero in un test —
*«era un falso allarme?»*.

## Architettura

```
    Claude                                 pilota
      │                                       ▲
      │ scrive                                │ guarda
      ▼                                       │
~/Documents/ACCoach/test_step.json      ┌─────────────┐
      │                                 │  riquadro   │
      └──────────  legge  ─────────────►│ in alto a   │
            ogni 500 ms                 │  sinistra   │
                                        └─────────────┘
```

Un modulo nuovo, `src/accoach/testpanel.py`, e un comando `test-panel` in
`__main__.py`. **Un processo a sé.**

Perché un processo separato e non una finestra dentro Coach Live:

* **Non apre la memoria condivisa.** Il 07/08 abbiamo sfiorato l'incidente di due
  `CoachEngine` accesi contemporaneamente, con ogni giro salvato due volte e la
  copia indistinguibile da un giro vero. Un processo che non legge telemetria non
  può ripetere quell'errore, comunque venga lanciato.
* **Spegnerlo è chiuderlo.** Il pilota ha chiesto che a fine test l'overlay si
  disabiliti. Senza opzione da ricordare non c'è opzione che resti accesa per
  sbaglio nella sessione di un pilota qualunque.
* **Non tocca il percorso che salva i giri.** Se il riquadro si pianta, si pianta
  da solo.

Il codice sarebbe lo stesso ospitato dentro `live`: quella resta una strada
disponibile dopo, non una scelta da fare ora.

### La finestra

Stessa ricetta dell'HUD, che è già dimostrata sull'impianto del pilota:
`FramelessWindowHint | WindowStaysOnTopHint | Qt.Tool`, sfondo traslucido,
`WindowTransparentForInput` + `WA_TransparentForMouseEvents`. **Non deve mai
rubare il fuoco al gioco**: un riquadro che intercetta un clic in staccata è
peggio di un riquadro che non c'è.

La scala si legge da `overlay.scale` nella configurazione, così i due riquadri
hanno la stessa taglia di carattere e crescono insieme.

### Posizione

Lo schermo di riferimento è quello **sotto il centro del desktop virtuale** —
la stessa regola con cui `Overlay._place_top_center()` trova «quello di mezzo».
Non se ne introduce una seconda: se i monitor vengono riordinati, le due finestre
si spostano insieme invece di litigare su quale sia il centrale.

Misurato sull'impianto del pilota l'08/08: tre display **separati** da 2560×1440,
il centrale è il primario (X da 0 a 2560, Y 0). Il riquadro va a (24, 24) di
quello schermo; l'HUD parte a ~1000 px, quindi non si sovrappongono — **a scala
1.0**.

**Limite dichiarato:** se i tre monitor venissero uniti in una superficie sola
(Eyefinity/Surround), Windows ne riporterebbe uno largo 7680 e questa regola
atterrerebbe sul pannello di sinistra, fuori dal campo visivo. Non è il caso
attuale e non viene gestito.

**Limite dichiarato:** il non-sovrapporsi vale solo alla scala misurata. Le due
finestre leggono la **stessa** manopola (`overlay.scale`): il bordo sinistro
dell'HUD sta a `1280 − 280·s`, il bordo destro del riquadro a `24 + 440·s`, e si
toccano oltre `s ≈ 1.74`. Un pilota che alzasse la scala oltre quella soglia si
troverebbe il riquadro sopra il delta — il numero che questa stessa specifica
dice non deve muoversi sotto l'occhio. Non è il caso attuale e non viene
gestito.

## Il file di un passo

`~/Documents/ACCoach/test_step.json`, in `paths.base_dir()` — la stessa cartella
che vale identica da sorgente e da exe congelato.

```json
{
  "step": 3,
  "of": 7,
  "title": "BLOCCAGGI",
  "do": "Frena fortissimo in staccata,\nfino a far raschiare le ruote",
  "specs": "ABS 0 · TC 6 · gomme calde",
  "ends_at": 1754683200,
  "done": false,
  "done_msg": "Aspetta il prossimo passo"
}
```

Questo passo è a tempo. Uno a ripetizioni porta `note: "1 di 3"` al posto di
`ends_at` — mai i due insieme, vedi sotto.

Solo `title` è obbligatorio. Ogni altro campo, se manca, semplicemente non
disegna la sua riga: un passo senza orologio non mostra la riga dell'orologio.

| campo | cosa fa |
|---|---|
| `step` / `of` | «PASSO 3 / 7» — dove sei nel protocollo |
| `title` | il titolo, la cosa che si legge in un colpo d'occhio |
| `do` | cosa fare, **massimo due righe** |
| `specs` | le condizioni da tenere, **una riga sola** di parole corte |
| `ends_at` | scadenza in **epoch assoluto**, non una durata |
| `note` | conteggio di ripetizioni («1 di 3»), riscritto a mano |
| `done` | forza il riquadro verde per un passo senza orologio |
| `done_msg` | la riga sotto il verde |

### Perché una scadenza assoluta e non una durata

Il pilota ha scelto un conto alla rovescia che **si muove da solo**: il tempo
deve scorrere anche quando Claude non sta scrivendo niente. Scrivendo l'ora in
cui il passo scade invece dei minuti che restano, il conto è ancorato fuori dal
riquadro: se la finestra si chiude e riapre, riprende dal punto giusto invece di
ricominciare da capo.

Il rovescio, ed è dichiarato: **l'orologio non si ferma se ti fermi.** Se il
pilota rientra ai box a metà di uno stint da venti minuti, il conto continua a
scalare. Quando succede, Claude riscrive `ends_at` più in là.

### Orologio e ripetizioni non convivono

O `ends_at` o `note`, mai tutt'e due sullo schermo insieme. Sono due risposte
alla stessa domanda — «quanto manca» — e in staccata se ne legge una sola. Se il
file le contiene entrambe, vince l'orologio.

### L'altezza è fissa

Il testo che non ci sta viene **tagliato**, non mandato a capo. Un riquadro che
si allunga sposta la riga dell'orologio a ogni cambio di passo, e l'orologio si
cerca con la coda dell'occhio in un punto che deve restare lo stesso. È lo stesso
motivo per cui il box del delta nell'HUD è più alto dei numeri che ci mette
dentro (`overlay.py`, `_DELTA_BOX_H`).

## Il completamento

**Quando `ends_at` è passato, il riquadro annuncia da sé la fine del passo.** Un
contatore che si muove da solo deve sapersi anche fermare da solo: se restasse a
`00:00` aspettando che Claude scriva qualcosa, il pilota vedrebbe per dieci
secondi esattamente quello che vedrebbe se l'app fosse morta. Per i passi senza
orologio l'annuncio arriva da `done: true`.

Tre proprietà del riquadro verde:

**Non se ne va da solo.** Resta finché il passo successivo non lo sostituisce. Un
messaggio che sparisce dopo tre secondi è un messaggio che, se in quel momento
eri all'apice della Parabolica, non hai mai ricevuto.

**Dice «fatto», non «superato».** Il riquadro sa che il passo è finito; non sa se
HONE si è comportato bene. Quel giudizio è di Claude e va nel verbale della
sessione. Un verde che dicesse «OK» sarebbe lo schermo che afferma una cosa che
non ha misurato.

**Non sostituisce la voce.** Claude continua a dire a voce cosa fare e quando è
finita. Il riquadro risolve il problema del *ricordare*, non quello
dell'*informare*: se un giorno non partisse, la sessione si farebbe lo stesso.

L'ultimo passo chiude con `PROTOCOLLO COMPLETATO` — che non è uno stato speciale
del riquadro, è solo l'ultimo passo scritto con quel titolo. Poi il processo si
chiude e lo schermo torna com'era.

## Le due letture che possono ingannare

**Un file letto mentre lo si sta scrivendo è un file rotto.** Per una frazione di
secondo il JSON è mezzo scritto. Se il riquadro lo leggesse e si svuotasse, il
pilota vedrebbe il protocollo sparire in curva. Regola: **se la lettura non torna
un passo valido, resta quello di prima.** Il riquadro si svuota solo quando
glielo si dice, mai per un incidente di lettura.

**Il fantasma di ieri.** Il file resta sul disco a fine sessione. Se il riquadro
partisse prima che il primo passo sia scritto, il pilota si troverebbe davanti il
passo 3 della sera prima, col suo verde già acceso, e ci crederebbe. Regola: **un
file più vecchio di dodici ore vale come assente** e il riquadro mostra «in
attesa». Le dodici ore sono un numero **scelto**, non misurato: nessuna sessione
dura mezza giornata, e un riavvio a metà serata rilegge correttamente il passo in
corso.

Senza file, o con file scaduto, il riquadro mostra una pastiglia «in attesa» —
come fa l'HUD quando il motore non c'è.

## Verifica

Si segue la ricetta già usata per l'avviso box (`tests/test_overlay_pit_due.py`):
si dipinge **il widget vero** fuori schermo (`QT_QPA_PLATFORM=offscreen`) e si
guarda cosa ha chiesto al pennello. L'orologio non è sostituito da un finto: in
`render_step` `now` è un parametro esplicito, non letto da `time.time()` dentro
la funzione, quindi il test lo sceglie passandolo — niente monkeypatch, niente
finto che avanza, e nessun modo per un test di dimenticare di farlo avanzare.

Cosa dimostrano i test:

1. **L'orologio scade e il verde arriva** — si salta oltre `ends_at`, compare
   `FATTO`; si salta di un'altra mezz'ora e **è ancora lì**.
2. **Mai due risposte alla stessa domanda** — con `ends_at` non compare `note`, e
   un file che contiene entrambi mostra l'orologio.
3. **L'orologio non si sposta** — si dipinge un passo da una riga e uno da due, e
   la riga dell'orologio cade sullo **stesso pixel**. Non «il riquadro è alto
   uguale»: «l'orologio non si è mosso sotto l'occhio».
4. **Il testo troppo lungo viene tagliato**, non mandato su una terza riga.
5. **Il file rotto non svuota niente** — passo buono, poi mezzo JSON, e sullo
   schermo c'è ancora il passo buono.
6. **Il fantasma di ieri** — un file con mtime di dodici ore fa vale come
   assente.
7. **Un controllo a pixel sul verde.** Nel progetto è già successo che una
   stringa venisse chiesta correttamente e finisse invisibile: chiedere non è
   mostrare.
8. **Il comando è registrato** — `test-panel` compare nella dispatch di
   `__main__.py` (`tests/test_cli.py`).

Cosa i test **non** possono dimostrare, e va fatto in pista:

* che la finestra atterri sullo schermo centrale — Qt in CI non ha schermi veri,
  ne inventa uno;
* che non rubi il fuoco ad ACC;
* che sia **leggibile con la coda dell'occhio a 200 all'ora**, che è l'unica
  domanda che conta e su cui nessun test ha voce.

Si verificano con gli screenshot della finestra via computer-use, come il 07/08:
lo schermo lo guarda Claude, il pilota guida. In questo progetto è vero sempre —
i difetti veri li hanno trovati lo schermo su giri reali e la revisione
d'insieme, mai la suite.

## Fuori scopo

* Nessuna condizione di completamento misurata dal codice.
* Nessun legame con `web/test_plan.json`: quello è il piano del tablet, si legge
  da fermi, e ha un pubblico diverso.
* Nessuna interazione: il riquadro non ha bottoni, non si clicca, non si sposta.
* Nessuna opzione in `config.toml`: il riquadro esiste quando il processo gira.
