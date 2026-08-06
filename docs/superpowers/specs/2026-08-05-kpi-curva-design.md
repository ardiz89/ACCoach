# Il numero della curva: un KPI misurato, in pista e nel tempo

**Data:** 2026-08-05 · **Stato:** approvato, da pianificare

## Da dove nasce

Il pilota ha visto **RTSA di Trophi.ai** e ne ha chiesto una nostra versione. Le
sue parole: «gestione della valutazione delle performance tramite **semplici KPI
visivi** monitorabili **in tempo reale**», e «vedere il **miglioramento di questi
KPI nel corso del tempo**».

Cosa fa RTSA, dalla loro pagina: **un voto 0-100 per curva appena la esci**
(«Each corner you drive becomes a number»), semaforo verde/giallo/rosso, un cue
direzionale («too early, too late, too low, perfect») e una **barra di
completamento** (le curve che fanno 60+). Solo tempo reale. Il confronto è
**frame per frame contro un giro di riferimento** che è **della community, un
datapack o un giro ufficiale Trophi** — mai il tuo. Overlay Windows, account e
abbonamento. Non dicono come si pesano i sette-e-più aspetti nel voto, né come
mostrano il miglioramento nel tempo.

## Quanto eravamo lontani: molto meno di quanto sembri

Misurato sul nostro codice, non stimato:

- `coaching/analyzer.py` divide già la pista in **zone che sono le curve vere**
  rilevate dal riferimento, accumula il confronto con la telemetria del
  riferimento a ogni frame e, **all'uscita di ogni curva**, calcola quanto hai
  perso lì (`_finalize` → `lost_ms = delta_last - delta_start`) e la causa più
  probabile;
- `/api/progress` calcola già, per curva, la **mediana** della perdita, le
  occorrenze e se è **sistematica o sporadica** — è la stessa struttura da cui il
  piano di allenamento pesca i suoi obiettivi.

**Il dato che loro trasformano in un numero, noi lo calcoliamo già.** Non lo
mostriamo, e per scelta documentata non lo diciamo all'uscita della curva: lo
teniamo e lo diciamo a voce **all'approccio della stessa curva al giro dopo**,
perché «un coach vero non ti parla di una curva che hai già fatto — è brontolare
sul passato».

## Le decisioni, e perché

**Niente voto 0-100.** La scala, i pesi fra gli aspetti e la soglia del 60
sarebbero **tarati da noi** e non verificabili da nessuno. Vale la regola che
questo progetto si è dato e che ha già salvato due analisi: *se la risposta si
muove con una nostra impostazione, non è misurata — è tarata*. Mostriamo i
**decimi persi in quella curva**, che sono misurati e ricalcolabili a mano.

**Il numero all'uscita, la voce invariata al giro dopo.** Un consuntivo muto e un
consiglio parlato non si pestano i piedi: il primo è informazione, il secondo può
ancora cambiare quello che fai.

**Ogni curva, anche quelle giuste.** È ciò che rende un cruscotto tale: la curva
verde ti dice che quella l'hai presa bene — informazione che oggi non hai mai. Il
silenzio resta dov'è e conta, ma è il silenzio della **voce**, non del numero.

Conseguenza sul codice: oggi `classify_corner` **scarta** `lost_ms` quando la
curva è nella norma (fra −250 e +120 ms non produce nulla). Il KPI ha bisogno di
quel valore sempre.

**I colori riusano le soglie già tarate in pista**: 120 ms è già «hai perso
qualcosa che vale dirtelo» (`_LOSS_MS`), 250 ms di guadagno è già una lode
(`_GAIN_MS`). Riusarle fa **concordare colore e voce**: se il coach parla, il
colore non è verde. Due metà della stessa app che si contraddicono sono il
difetto che abbiamo già dovuto togliere due volte (il debrief contro
Allenamento; la pastiglia contro il rail).

**Fuori perimetro:** la barra di completamento (gamification su una scala
nostra) e il cue direzionale a schermo (la voce lo dice già, e meglio).

## Cosa si spedisce

### 1. In pista

L'analyzer espone l'esito dell'ultima curva chiusa — **indice, nome, millisecondi
persi** — sempre, mentre voce e feed-forward restano identici a oggi: è
un'**uscita in più**, non un cambio di comportamento.

Il dato viaggia in `EngineState` come blocco opzionale, accanto a `engineer` e
`focus` che hanno già quella forma; il server lo serializza, l'overlay lo legge
in `apply_state`.

L'overlay disegna un riquadro fisso:

```
T6 Ascari   ●  −0.31
```

Resta finché non chiudi la curva successiva — **nessun timer da tarare**, e
l'occhio trova sempre il numero nello stesso posto.

**Non compare affatto** in tre casi: senza riferimento (prima sessione su una
macchina o pista nuova: non c'è niente contro cui confrontare), in out-lap o giro
anomalo (riusando il gate `quiet` che già esiste), e prima della prima curva
chiusa. **Assente, non un trattino**: un valore che non abbiamo non si finge.

Colori, dalle soglie esistenti:

| esito | colore |
|---|---|
| guadagni ≥ 0,25 s | verde acceso |
| fra −0,25 s e +0,12 s | verde |
| perdi 0,12–0,30 s | giallo |
| perdi > 0,30 s | rosso |

### 2. Nel tempo

Nella scheda **Andamento**, sotto i punti deboli per curva che già ci sono: la
mediana della perdita **per sessione**, per ogni curva sistematica.

La sessione è l'unità in cui ci si allena davvero ed è già un oggetto del sistema
(`sessions.py`). Due uscite nello stesso pomeriggio restano distinte, e questo
conta: se cambi qualcosa fra l'una e l'altra, lo vedi.

**Non si registra niente di nuovo**: la serie si ricalcola dai giri già salvati.

## I limiti, dichiarati

- Il numero è relativo al **tuo** riferimento eletto per le condizioni. Se il tuo
  miglior giro è lento, un verde non dice che sei veloce: dice che sei costante.
  Va scritto dove il pilota lo legge, non solo nel codice.
- La **soglia dei colori è tarata**, il numero no. Va nella guida, accanto alle
  altre soglie già spiegate.
- Sui primi giri con una macchina o una pista nuova il riquadro non c'è. È
  corretto, ma va capito: la guida deve dirlo, altrimenti sembra rotto.

## Test

- L'analyzer espone la carta della curva **anche quando `classify_corner`
  restituisce `None`** — è il caso «curva presa bene», cioè metà del valore della
  funzione, ed è quello che oggi viene buttato;
- voce e feed-forward **non cambiano**: gli stessi cue di prima, negli stessi
  momenti (test di non-regressione sul comportamento esistente);
- il riquadro non compare senza riferimento, in out-lap e su giro anomalo;
- i colori seguono le soglie **esistenti**, e il test le legge dalle costanti
  invece di riscriverle — due definizioni della stessa soglia sono una che
  invecchia;
- la serie per sessione: una curva migliorata su tre sessioni dà una serie
  decrescente, e una sessione senza quella curva non produce un buco a zero.

## Fuori perimetro

Barra di completamento, voto sintetico, cue direzionale a schermo, confronto con
giri di altri (community/datapack), e qualunque forma di account o servizio
remoto: restiamo offline.
