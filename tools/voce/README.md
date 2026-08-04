# Parlare con Claude mentre guidi

Un canale a due vie fra il pilota al volante e Claude Code: tu dici una parola
di attivazione e la domanda, Claude risponde a voce. **Non è una funzione di
HONE** — l'app non lo avvia, non lo bundla e non lo conosce. È uno strumento da
sviluppo, e sta in `tools/` come gli altri spike, fuori dal pacchetto.

Nasce da un incidente vero il 2026-08-02, e dalla regola che ne è uscita: quello
che serve in movimento si dice a voce.

## Avviare

```powershell
tools\voce\voce.bat            # avvia
tools\voce\voce.bat stato      # sta girando?
tools\voce\voce.bat stop       # ferma
```

Il `.bat` esiste per due motivi, e nessuno dei due è la comodità.

Il primo: il comando giusto usa il python del **venv**, e quello di sistema qui
non ha `vosk` né `sounddevice` — sbagliarlo dà un `ModuleNotFoundError` che
leggi quando sei già seduto in macchina. Il secondo: **due assistenti accesi si
contendono il microfono** e nessuno dei due sente bene, quindi c'è un solo posto
e non si parte due volte. Un PID rimasto da un processo morto non blocca
l'avvio: quello sarebbe il modo peggiore di fallire, cioè lasciarti senza
assistente e convinto di averlo.

A mano, se serve: `.venv\Scripts\python.exe tools\voce\assistente.py`.

## Come mi arriva, e perché passa da un file

`Monitor` osserva lo **stdout di un comando che lancio io**, quindi un processo
avviato dal `.bat` in una finestra sua sarebbe muto per me. Per questo il `.bat`
gli redirige l'uscita su `tools/voce/voce.log`, e io leggo quello:

```
tail -F tools/voce/voce.log | grep -E --line-buffered "DOMANDA|ERRORE|PRONTO"
```

I due pezzi diventano così indipendenti, che è il punto: l'assistente sopravvive
a un `Monitor` fermato, e un `Monitor` può attaccarsi a un assistente già
acceso. `tail -F` e non `-f` perché il log si riscrive a ogni avvio — provato:
con `-F` la riga `PRONTO` del riavvio arriva lo stesso.

Poi: **«ehi copilota»**, pausa breve, la domanda. Riserva: **«ehi tecnico»**.

Il processo stampa una riga per domanda e **non esce mai**; è Claude a leggerlo
con il tool `Monitor` in modalità `persistent`. Se nessuno lo sta leggendo, il
microfono è aperto per niente — quindi chiediglielo prima di salire in macchina.

Opzioni che contano:

| | |
|---|---|
| `--parola "ehi tecnico"` | l'altra parola misurata |
| `--silenzio 6` | secondi di quiete che chiudono la domanda. È la rete di sicurezza, non il criterio |
| `--massimo 30` | tetto di durata di una domanda |
| `--mic brio` | quale microfono |
| `--tutto` | **vedi l'avvertenza in fondo** |

Claude risponde con `di.py`, che parla con la **voce neurale Piper**
(`it_IT-paola-medium`, la stessa dei cue del coach): **~500 ms** misurati di
sintesi per frase, in locale, contro SAPI5 che è istantaneo e sembra un
navigatore del 2005. Su un canale dove fai una domanda e aspetti la risposta,
mezzo secondo non lo nota nessuno. Se Piper non c'è si ripiega su SAPI5, così
su una macchina appena clonata parla lo stesso.

È la stessa voce con cui sono renderizzati i cue del coach, quindi viene
**abbassata del 15%** per non essere la stessa persona in pista. Costa 37 ms.

**Chatterbox no, per questo canale.** È la voce di marca scelta il 02/07 e resta
giusta per i cue del coach, che si renderizzano *in build*. Qui si sintetizza
mentre aspetti la risposta, e misurato: 7 s di caricamento modello + 13.6 s per
tre secondi di parlato, 3-5× il tempo reale. Una risposta breve arriverebbe dopo
venti secondi di silenzio.

`di.py` crea `parla.lock` mentre parla. Finché quel
file esiste l'assistente butta via l'audio: senza, la risposta rientra dal
microfono e il turno dopo l'assistente risponde a se stesso.

## Il modello vocale, che non è qui

`assistente.py` cerca `tools/voce/vosk-model-small-it-0.22/`. Il modello pesa
**88 MB** e non sta nel repo: è un artefatto scaricabile, e un binario di quella
taglia entra nella storia di git e non ne esce più.

Si scarica da <https://alphacephei.com/vosk/models> (*vosk-model-small-it-0.22*)
e si scompatta qui dentro, così com'è. Il `.gitignore` lo copre già.

## La parola di attivazione è misurata, non scelta

Vale la pena saperlo prima di cambiarla, perché il modo in cui sbaglia è
silenzioso.

vosk saprebbe fare da rilevatore di parola chiave con una **grammatica**, che
costerebbe meno CPU. Ma una grammatica accetta solo parole **presenti nel
vocabolario del modello** — e questo è il modello italiano. Una parola fuori
vocabolario dentro una grammatica non dà errore: semplicemente **non scatta
mai**. Quindi qui si trascrive tutto e si cerca la parola nel testo.

`taratura_sveglia.py` sintetizza una frase e la ridà a vosk. Cosa ha misurato:

| detto | trascritto |
|---|---|
| hey dev | **egli deve** |
| ehi hone | ehi non |
| ehi ingegnere | e ingegneri |
| **ehi copilota** | ehi copilota |
| **ehi tecnico** | ehi tecnico |

Le parole fuori vocabolario vengono rifuse in qualcos'altro ogni volta; quelle
dentro tornano identiche, anche con una domanda intera attaccata. Una lista di
18 varianti *indovinate* per «hey dev» fallì tutte e 18 — da cui la regola: la
parola di attivazione dev'essere fatta di **parole italiane vere**, e ogni
candidata si passa da `taratura_sveglia.py` prima di fidarsene.

Limite noto della stessa prova: i **nomi propri di curva si storpiano**
(«roggia» → «loggia»). Le domande passano; i nomi vanno letti con indulgenza.

## Cosa manca ancora, e si misura solo in pista

La sintesi vocale serve a **bocciare**, non a promuovere. «ehi copilota» torna
esatta quando la dice una voce sintetica con una dizione perfetta — non quando
la dice il pilota, in abitacolo, con il motore acceso. Il protocollo è nella
roadmap: **dieci risvegli a motore acceso**, poi si legge
`assistente-udito.jsonl` e si aggiungono le forme che il modello ha davvero
scritto.

## Avvertenza: `--tutto`

Con `--tutto` il diario raccoglie **ogni** trascrizione, non solo le domande:
le telefonate, e chi passa di lì. Quel file esiste perché Claude lo legga per
tarare le varianti — e in quel momento due ore di parlato altrui entrano nel suo
contesto, senza che nessuno di quegli altri abbia acconsentito.

Per questo **non è il default**: di norma il diario tiene solo le domande. La
registrazione completa è un'operazione dichiarata, che si accende per una
taratura e si spegne dopo.

L'audio comunque non lascia questa macchina: vosk gira in locale e non registra
niente su file.
