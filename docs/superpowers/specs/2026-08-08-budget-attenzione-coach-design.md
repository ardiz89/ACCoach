# Il budget di attenzione del coach vocale

Spec del 2026-08-08. Nasce da `COACHING-PRO.md`, priorità 1.

## Il problema

Tre coach professionisti indipendenti impongono lo stesso limite: **due o tre temi per sessione**,
cinque-sei giri ciascuno, e in pista **solo parole-innesco di una-tre parole**, concordate prima.
Il motivo è dichiarato ed è sempre lo stesso: la banda passante del pilota che guida è finita.

Il nostro coach vocale ha un limite di **frequenza** — `CueScheduler` impone 4 secondi fra un
consiglio e l'altro e sopprime per 20 secondi lo stesso consiglio nello stesso punto — ma **nessun
limite di argomenti**. Nulla impedisce dodici temi diversi in una sessione.

## Quello che già abbiamo, e che nessuno usa

`coaching/focus.py` implementa esattamente il rituale del coach: raccoglie qualche giro pulito
(`_MIN_LAPS = 3`), elegge **una** debolezza ricorrente, la lavora, la dichiara migliorata o la
parcheggia dopo sei giri (`_PATIENCE = 6`), e passa alla successiva. È agganciato al motore
(`engine.py:703`).

**Il coach vocale non lo sa.** Il focus vive in un pannello; la voce continua a commentare tutto.

Quindi questo lavoro non costruisce un budget. **Collega la voce al budget che già scegliamo.**

## La decisione

Deciso col pilota:

- Quando un focus è attivo, in pista si parla **solo del tema del focus**, su tutta la pista — non
  solo nella curva eletta. I coach lavorano il *pattern* («sta facendo lo stesso errore in ogni
  curva»), non una curva sola.
- Fanno eccezione **sicurezza e strategia** (bloccaggio, pattinamento, benzina, le tre chiamate
  box): non sono temi da allenare, sono eventi.
- Tutto il resto **tace in pista e resta nel debrief**, che è calcolato dal giro e non dipende da
  cosa è stato pronunciato.
- **Quando un focus non c'è ancora** (fase di valutazione), il coach parla **come oggi**. Il
  silenzio d'osservazione dei coach veri è stato valutato e scartato: il rischio che l'app sembri
  rotta nei primi giri non vale il guadagno.

## L'architettura

```
FocusCoach (elegge il tema)  ──set_focus(tema)──>  CueScheduler  ──> Voce
       ▲                                                │
       └── debrief per giro                             └── il resto tace
                                                            (e resta nel debrief)
```

Il filtro sta in `CueScheduler` perché è già «il cancello fra ciò che si potrebbe dire e ciò che si
dice» — lo dichiara il suo docstring. Non nasce un componente nuovo.

## I componenti

### 1. Un tema per ogni categoria — `coaching/focus.py`

`_THEME` oggi mappa 6 categorie su quattro temi (frenata, trazione, percorrenza, linea); tutte le
altre cadono nel default «guida». Va esteso a **ogni categoria che può parlare**, con una mappa
sola: due mappe che dissentono sono lo stesso difetto che `phases.py` evita con «una parola vuol
dire un posto solo».

**Verificato prima di toccarla, non assunto**: `_theme_key` alimenta anche il titolo del debrief, ma
aggrega su `CornerLoss.category`, che riceve `cue.category` da `classify_corner`
(`debrief.py:772`), e `classify_corner` può emettere **solo** `BRAKE_LATER`, `CARRY_SPEED`, `GOOD`,
`LESS_BRAKE`, `MORE_THROTTLE`, `TIME_LOSS`. Le categorie live non raggiungono mai `CornerLoss`,
quindi estendere `_THEME` non può cambiare il titolo del debrief.

### 2. Chi parla sempre — `coaching/cue.py`

`engine.py:66-74` contiene già l'insieme esatto (`_SAFETY_CATEGORIES`: `LOCKED`, `WHEELSPIN`,
`FUEL`, `PIT_IN`, `PIT_APPROACH`, `PIT_BRIEFING`) per un altro cancello che significa la stessa
cosa — «questo non è un consiglio di guida rimandabile». Va spostato in `cue.py` come definizione
unica, importata da entrambi.

**Fuori perimetro, ma da non perdere**: l'audit ha trovato che `UNDERSTEER` e `OVERSTEER` sono
classificati acuti ma non stanno in quell'insieme, quindi tacciono su out-lap, ai box e oltre i 3
secondi di delta — cioè quando l'auto si comporta peggio. È la priorità 2 di `COACHING-PRO.md` e
**non** va corretta qui: cambierebbe due comportamenti in una volta.

### 3. Le parole-innesco — `coaching/cue.py`

Una tabella `TRIGGER: dict[CueCategory, dict[str, str]]`, una-tre parole per categoria, in italiano
e in inglese. In pista si pronuncia quella; la frase intera continua ad andare all'overlay e al
debrief.

Il patto col pilota lo fa il `FocusCoach`: il messaggio che annuncia il focus aggiunge *«in pista ti
dirò solo parole sulla frenata, tipo «meno freno»»*. È il modo in cui i coach concordano le parole
prima di scendere, e senza il patto una parola sola non vuol dire niente.

**Correzione dalla revisione finale (2026-08-09).** Qui c'era scritto *«in pista ti dirò solo:
freno»*, cioè il patto prometteva **una** parola mentre il filtro è **per tema** (§«La decisione»):
con `braking` attivo il pilota sente anche «rilascia», «più tardi», «prima» — parole mai concordate,
e la promessa si rompeva al secondo giro. Deciso col pilota di ammorbidire la promessa, non di
stringere il filtro: il patto nomina il **tema** e dà la parola come esempio.

### 4. Il filtro — `coaching/scheduler.py`

`CueScheduler` riceve `set_focus(theme: str | None)` dal motore quando `FocusCoach` cambia focus, e
nel ciclo di eleggibilità di `poll()` scarta i consigli il cui tema non è quello attivo, a meno che
la categoria sia fra quelle che parlano sempre. Con `focus_theme` a `None` il comportamento è
identico a oggi.

**Il tema che viaggia è la chiave inglese**, quella che `_theme_key` già usa per aggregare
(`debrief.py:473-477`), mai la stringa tradotta. Un confronto fra temi che cambia esito con la
lingua dell'interfaccia sarebbe un difetto invisibile in italiano e visibile solo in inglese —
e questo progetto ne ha già trovati due di quella famiglia.

Nota d'ordine: il filtro va applicato **nella scelta**, non alla `submit`, così un consiglio fuori
tema non consuma la coda e non altera la soppressione dei ripetuti.

## Cosa NON tocchiamo

**La cadenza di ripetizione resta 20 secondi.** I coach col metronomo ripetono molto più spesso
(«light light light light»), ma non esiste un numero misurato per la nostra situazione, e uno
inventato qui deciderebbe quanto è assillante il coach. Si misura in pista, come le tarature ACC.

## I test

- Il filtro: tema che combacia parla; tema diverso tace; categoria d'eccezione parla comunque;
  `focus_theme=None` si comporta come oggi.
- **Un test che fallisce quando si aggiunge una categoria senza tema.** Il progetto ha già preso
  questa famiglia di difetti (una categoria con titolo, grafico ed esercizio e nessun produttore).
- **Un test che pretende la parola-innesco in entrambe le lingue.** L'audit ha trovato due messaggi
  che escono in italiano in modalità inglese: è un difetto ricorrente, non un'ipotesi.
- Che il debrief continui a riportare anche ciò che è stato taciuto (è indipendente per costruzione,
  ma il test lo àncora).

## I rischi

1. **Le frasi nuove cadono su SAPI5** finché non sono pre-sintetizzate: `Voice` prova prima i WAV
   Piper e poi SAPI5 (`voice.py`, docstring). `tools/render_cues.py` esiste; la resa va fatta e
   verificata, altrimenti la parola-innesco suona peggio della frase che sostituisce.
2. **Il pilota potrebbe non gradire il silenzio** sui temi fuori focus. È reversibile: basta non
   chiamare `set_focus`.
3. **Un focus su una curva marginale** rende il coach quasi muto per sei giri. `_PATIENCE = 6` lo
   limita già nel tempo; da osservare in pista prima di aggiungere altre valvole.

## Fuori perimetro

Il secondo tema («massimo 3 item» di Bentley), la varianza per curva come indice, il margine di
rumore dichiarato: sono le priorità 3 e 4 di `COACHING-PRO.md` e hanno vita propria.
