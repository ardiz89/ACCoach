# Sessione in pista del 2026-08-07 — interrotta, si riprende domani

ACC · McLaren 720S GT3 Evo · Monza (più tre giri a Zolder prima che cominciassimo
a guardare). Sessione fermata dal pilota per spegnere il PC, **non** perché
qualcosa fosse finito: metà del programma è ancora da fare, e sta in fondo.

Era la prima sessione dopo il 2026-08-02, quindi la prima volta che un pilota in
movimento vedeva le quattro cose spedite fra il 05 e il 07 agosto: il riquadro
per curva (#80), l'avviso di rientro ai box (#83), i decimi sulle cifre
visualizzate (#82) e il rail della reportistica (#79).

---

## Come è stata condotta

Vale la pena scriverlo perché ha cambiato il modo di raccogliere le prove.

Le istruzioni sono arrivate **a voce** (`tools/voce/`, parola «ehi copilota»),
com'è regola dal 02/08. Ma a metà sessione il pilota ha posto un problema che la
regola non copriva: *«non riesco a dirti cosa c'è scritto sullo schermo mentre
guido — puoi capirlo tu dalla telemetria?»*. Ed era giusto: leggere l'overlay e
riferirlo è esattamente il genere di compito che la regola vieta.

Da lì la sessione è passata a **osservazione diretta**: screenshot della finestra
dell'overlay via computer-use, senza rubare il fuoco al gioco (il provider
Windows non ha nemmeno la capacità di focus, quindi non può disturbarlo), più
letture in sola lettura della shared memory. Il pilota guida e basta.

Questo è il motivo per cui i due risultati migliori della serata sono **un
fotogramma** e **una riga di telemetria**, e non un racconto.

---

## Cosa è stato dimostrato

### ✅ #83 — l'avviso di rientro sopravvive al traguardo

Uno screenshot preso subito dopo la linea, su un giro appena chiuso e senza
rientro, mostra la pastiglia `▶ RIENTRA AI BOX` **ancora accesa**. È l'asserzione
della PR: `_calling` è una *condizione*, non un evento per giro, e
`pitcall.py:138-142` lo motiva con «un avviso che scade col giro scade
esattamente quando è ancora vero». I test in suite coprivano la logica; questo
copre il fatto che arrivi fino ai pixel.

### ✅ #80 — il riquadro per curva, primo avvistamento in movimento

Nello stesso fotogramma: `Parabolica  −0.21`, in giallo. Nome giusto (è l'ultima
curva chiusa prima della linea), segno dal punto di vista del pilota, e colore
coerente col semaforo — 210 ms cade nella banda `warn`, fra i 120 ms della soglia
di parola e i 250 della lode (`analyzer.corner_level`). Il riquadro sopravvive al
traguardo e mostra la curva *precedente* alla linea, che è il comportamento
voluto.

### ✅ Il Focus concorda con un ricalcolo indipendente, alla cifra

L'overlay scriveva `FOCUS · TRAZIONE · LESMO 2 −0.14s`. Ricostruendo a tavolino
il debrief del terzo giro contro il riferimento eletto, la Lesmo 2 esce a
**+136 ms**. Due strade diverse, stesso numero.

### ✅ I sette complessi di Monza sono nominati bene

`Variante del Rettifilo · Curva Grande · Variante della Roggia · Lesmo 1 ·
Lesmo 2 · Variante Ascari · Parabolica`. Sette e non undici è corretto: sono i
complessi di frenata, non i numeri ufficiali.

### ✅ `verify-aids` su ACC — la semantica, chiusa di sbieco

`TARATURE-ACC.md:67` chiedeva un controllo mai fatto su ACC: non l'aritmetica
degli offset (già corroborata da `isValidLap` a 1408), ma che i numeri
**seguano la manopola**. Leggendo i livelli per sapere se l'ABS era stato
abbassato, si è visto `abs_level` passare da **6** (registrato nel primo giro
della serata) a **0** dopo che il pilota l'ha girato. `brake_bias = 0.75`,
`tc_level = 6` invariato. La semantica segue. Casella chiusa senza spendere un
minuto di pista apposta.

### ✅ `in_pit_lane` si comporta bene nelle due direzioni

`1` da fermo nella piazzola, `0` appena rientrato in pista a 50 km/h.

---

## ❌ Il difetto: il briefing ai box non può nascere su ACC

**Sintomo.** Il pilota rientra ai box dopo la chiamata dell'ingegnere, si ferma,
e non sente niente. Sull'overlay non compare nessuna pastiglia.

**Misura.** Con l'auto **ferma a 0.0 km/h nella piazzola**, letto in sola lettura
dalla shared memory:

```
conn=True  status=2  in_pit=False  in_pit_lane=True  v=0.0  pos=0.040
```

**Causa.** Il briefing sta dietro a `pitcall.py:240`:

```python
if s.in_pit:
    ...
    return [self._cue(CueCategory.PIT_BRIEFING, _BRIEFING, s.lap_position)]
if s.in_pit_lane:
    return []                      # on the way in: nothing left to say
```

La prima condizione non scatta mai durante un pit stop, la seconda esce subito, e
il cue **non viene mai prodotto**. Non è la voce che l'ha mangiato.

**Perché fa male.** Il progetto sapeva già questa cosa. `reader.py:318-336`:

> `isInPit` only covers standing in the garage […] `isInPitLane` is True anywhere
> in the pit lane — the whole corridor, not just the box.

Quella riga esiste perché il 21/07 lo stesso campo aveva ingannato la validità
dei giri (l'in-lap triplicava σ), e da lì nacque `_in_pit_lane`. `pitcall.py` è
stato scritto **dopo**, ha riusato `in_pit` per dire «fermo ai box», e la lezione
non l'ha seguito. Il suo docstring dice *«once stopped in the box»*; il campo che
legge dice *«in garage»*. È la famiglia di difetti di sempre: **un percorso che
dimentica quello che hanno imparato gli altri.**

**L'offset è corroborato, non assunto.** Dump della pagina graphics durante la
misura:

```
completedLaps      off=132   = 9
iLastTime          off=144   = 119770
iBestTime          off=148   = 114700     ← 1:54.700, il PB della sessione, al ms
distanceTraveled   off=156   = 0.4976
isInPit            off=160   = 0          ← qui
currentSectorIndex off=164   = 0
isInPitLane        off=1236  = 1
```

`iBestTime` che cade esattamente sul tempo del giro migliore è la prova che
l'allineamento è giusto: sbagliato di un solo campo, quel numero non sarebbe lì.

**Il limite di questo dato, dichiarato.** `isInPit` è stato letto `0` sia fermi
nella piazzola sia dopo che il pilota ha riferito di essere tornato in garage.
Ma **fra le due letture non è cambiato nulla** — stessa posizione 0.040, stessa
velocità, stesso settore — quindi non c'è prova indipendente che il gioco sia
passato in uno stato diverso. La frase sostenibile è *«in tutto ciò che si è
potuto osservare su ACC, `isInPit` non si accende mai»*, **non** *«ACC non lo
accende mai»*. Chi domani chiuderà questo difetto non usi la seconda.

**La correzione proposta (non scritta).** Non serve quel campo. «Fermo ai box» si
scrive con due cose che leggiamo già bene: `in_pit_lane` (che vale 1,
correttamente) e `speed_kmh` (che vale 0.0). E `pitcall.py` ha già
`_MOVING_KMH = 25.0` per dire «questa macchina non sta guidando»: riusarlo è una
soglia sola invece di un terzo criterio inventato — la stessa disciplina di
`corner_level`, che riusa le soglie del coach per non contraddirlo.

Da fare col test che oggi manca: **un test che fallisca su un fotogramma
`in_pit=False, in_pit_lane=True, v=0`**, cioè il fotogramma vero misurato stasera.

### Rischio secondario, non confermato

`fuel.py:54` arma `_pit_this_lap` **solo** su `in_pit`. Se quel campo non si
accende mai su ACC, un giro con rifornimento non viene escluso dal calcolo del
consumo. Lo salva la banda `_PLAUSIBLE_BURN_L`, che rifiuta una bruciatura
negativa — quindi è un rischio residuo, non un difetto osservato. Da guardare
quando si farà lo stint benzina.

---

## Incidente sfiorato, e la protezione che è mancata

All'avvio ho lanciato `live` dal worktree `whelk` **mentre il pilota ne aveva già
uno acceso** dal launcher nel worktree primario. Due `CoachEngine` sulla stessa
shared memory **salvano ogni giro due volte**, e la copia è indistinguibile da un
giro vero in più. Spento entro tre minuti, prima che un giro si chiudesse.

`launcher.py:72` protegge da questo *dentro il launcher* (`("server",)` è escluso
da `_LIVE_SAFE_KEYS` apposta), ma non esiste niente che protegga da **due
processi avviati da due strade diverse**. Un lucchetto tipo quello di
`tools/voce/voce.bat` — un solo posto, PID verificato vivo — sarebbe la stessa
medicina.

**Verificato che il danno non c'è stato**: i due giri Zolder con tempo identico
(`1m36s300` entrambi) *non* sono duplicati — 873 contro 881 campioni, primi e
ultimi valori diversi, 97 secondi di distanza. Sono due giri veri con lo stesso
tempo al millisecondo.

---

## I giri registrati stasera

| Giro | Tempo | Note |
|---|---|---|
| Zolder ×3 | 1:41.690 · 1:36.300 · 1:36.300 | prima che cominciassimo a guardare |
| Monza | 1:56.052 | perdeva 899 ms alla Variante del Rettifilo, 695 dei quali all'apice |
| Monza | 1:55.182 | diventa il riferimento |
| Monza | 1:54.700 | **PB**; più veloce del riferimento di 482 ms *e insieme* 476 ms persi alla Roggia |
| Monza | 1:57.555 | il giro del fotogramma con l'avviso box |

Il 1:54.700 è il caso che il riquadro per curva esiste per servire: la delta bar
dice «verde, vai bene» e il riquadro dice dove stai lasciando i soldi.

Nota: il riferimento eletto per le condizioni di stasera (asfalto 37.8 °C) era il
**1:55.902 del 02/08**, non il 1:53.712 in archivio — cioè l'elezione per
condizioni ha fatto il suo mestiere.

---

## Da dove si riprende domani

Il pilota era sul giro di riscaldamento del **Blocco 2** quando si è fermato.
ABS già a **0**, TC a **6**, freno bias 0.75.

1. **Blocco 2 — gli errori voluti**, uno per volta e annunciati a voce:
   tre frenate volutamente bloccate (chiude anche il **burst lock**, fermo dal
   02/08 per evento mancato e non per soglia) · pattinamento in uscita con
   **TC a 0** · sottosterzo in Ascari · coasting. I falsi positivi valgono quanto
   i veri: un giro annunciato pulito su cui il coach parla è un dato.
2. **Blocco 3 bis — il briefing**, da rifare dopo la correzione, non prima.
   La proposta dell'ingegnere resta in sospeso finché non la si *scrive*, quindi
   il richiamo si riarma da solo uscendo dal box.
3. **Stint benzina** (~20 min): giri costanti, **setup e aiuti fissi**, dal pieno
   fino a scendere. Sblocca il coefficiente s/litro, che non è estraibile
   dall'archivio.
4. **Campi pioggia ACC** (~10 min): `find-rain`, poi alzare la pioggia dal menu
   senza fermarlo.
5. **AC + SF25 al Red Bull Ring** se avanza tempo, per `yaw_baseline` Formula —
   con la periferica delle sessioni del 02/08 (passo sterzo 0.0004).
6. **Parola di attivazione**: 8 risvegli su 10 fatti, **tutti presi al primo
   colpo**. Le storpiature sono tutte nella *domanda*, mai nell'attivazione
   («mi autorizzi» → «ne autorizzi», «ABS» → «la via si»). Mancano due risvegli
   e poi si legge `assistente-udito.jsonl`.

## Prima di ripartire, tre note operative

- **Un solo motore.** Se il launcher ha già Coach Live acceso, non avviarne un
  altro da riga di comando. Controllo: `Get-CimInstance Win32_Process` filtrando
  su `live`.
- **La porta 8778** era occupata dal server della sessione «mappa nel Confronto»
  nel worktree primario. Per rivedere i giri di stasera su `main` va fermato,
  altrimenti si guarda un altro build.
- **Il canale voce** vive solo nel worktree primario: venv e modello vosk da
  88 MB stanno lì (`C:\Users\undrg\progetti\ACCoach`), non in `whelk`.
