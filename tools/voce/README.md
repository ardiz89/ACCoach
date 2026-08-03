# Parlare con Claude mentre guidi

Un canale a due vie fra il pilota al volante e Claude Code: tu dici una parola
di attivazione e la domanda, Claude risponde a voce. **Non è una funzione di
HONE** — l'app non lo avvia, non lo bundla e non lo conosce. È uno strumento da
sviluppo, e sta in `tools/` come gli altri spike, fuori dal pacchetto.

Nasce da un incidente vero il 2026-08-02, e dalla regola che ne è uscita: quello
che serve in movimento si dice a voce.

## Avviare

```powershell
pip install vosk sounddevice pyttsx3        # una volta
python tools/voce/assistente.py
```

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

Claude risponde con `di.py`, che crea `parla.lock` mentre parla. Finché quel
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
