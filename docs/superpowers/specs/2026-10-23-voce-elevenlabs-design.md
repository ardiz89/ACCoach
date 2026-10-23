# La voce del coach con ElevenLabs — design

Data: 2026-10-23. Parte dal main locale `d96e6f1`.

## Il perché

Il pilota trova la voce del coach poco naturale. Oggi:

- 59 frasi italiane sono WAV pre-registrati con Piper (`src/accoach/voice_cues/`
  e `voice_cues_male/`, chiave = testo esatto in `manifest.json`), fatti da
  `tools/render_cues.py` al momento della build;
- tutto il resto va sulla voce di sistema di Windows (SAPI5), molto più
  robotica: pressioni («Gomme anteriori a 27,4 psi, troppo alte. Togli circa
  0,8 psi a freddo.»), temperature, livelli di ABS e TC, le proposte
  dell'ingegnere (~80 frasi di leva del tipo «Ammorbidisci la barra antirollio
  anteriore di 1 click»), e tutto l'inglese.

Il pilota il 22/10 ha ascoltato campioni via filtro radio e ha scelto ElevenLabs.
È disposto a pagare un servizio una tantum.

## Deciso col pilota

1. **Voce maschile: ElevenLabs «MarcoTrox - Warm, Balanced and Polished»**,
   modello **Eleven Multilingual v2**, velocità **1,10**, stabilità **30 %**,
   similarità **70 %**, style exaggeration **0** («grinta media»).
2. **Due voci, maschile e femminile; la maschile è quella predefinita.** Oggi la
   predefinita è la femminile (`voice.male = false`): si rovescia.
3. **La voce non dice i numeri di dettaglio.** «Basta generalizzare: quando vado
   ai box vedo dal setup visivo cosa c'è da fare.» Le frasi con pressioni,
   temperature, livelli e click dicono cosa succede e cosa fare; i valori restano
   su schermo, sul tablet e sulla pagina Ingegnere.
4. **L'inglese serve solo a piloti futuri.** Si registra adesso solo l'italiano;
   l'inglese resta su SAPI5 finché non serve, ma lo script sa già generarlo.
5. In pista tutto resta **offline**: si genera una volta, i WAV vanno nel repo e
   nel pacchetto come oggi.

## Obiettivi

- In italiano, in pista, nessuna frase detta da SAPI5: ogni frase che il coach e
  l'ingegnere possono dire ha il suo WAV in entrambe le voci.
- Un controllo automatico lo garantisce: se qualcuno aggiunge una frase senza WAV,
  un test fallisce.
- Un comando rigenera tutto con ElevenLabs con le impostazioni scelte, così le
  frasi nuove di domani si aggiungono senza rifare il lavoro.

## Non obiettivi

- Voce in inglese registrata (resta SAPI5).
- Generare audio mentre si guida (niente rete in pista).
- Cambiare cosa dice il coach o quando lo dice, salvo togliere i numeri dalle
  frasi che oggi li hanno.

## Anti-obiettivi

- Una frase che dice un numero o una direzione sbagliata dopo la generalizzazione
  (es. «troppo gonfie» quando sono sgonfie).
- Una frase rimasta con un numero che non ha WAV e cade su SAPI5 in silenzio.
- La chiave dell'API in chat, nei log, nel repo o in un file del progetto.
- Audio generato col piano gratuito messo nel pacchetto (non è per uso
  commerciale).
- Testi che rompono il tono del 21/10 (`tests/tono.py`).

## Le frasi

L'elenco chiuso delle frasi italiane è la somma di:

- le frasi statiche di oggi (le raccoglie `tools/render_cues.py`);
- le frasi enumerate di oggi: «Qui perdi N decimi» per N da 1 a 25 e «Benzina
  per circa N giri» per N da 1 a 3. **Restano col numero**: sono già un insieme
  chiuso, e il numero è il consiglio stesso (scelta mia);
- le frasi oggi dinamiche, riscritte senza numeri (decisione 3):
  - pressioni (`coaching/pressure.py`): asse (anteriori/posteriori) × troppo
    alte/troppo basse, con cosa fare a freddo, senza valori;
  - temperature (`coaching/tyretemp.py`): troppo calde/troppo fredde, senza °C;
  - ABS/TC (`coaching/advisor.py`): «alza l'ABS di uno» / «alza il TC di uno»
    senza «dal N al N+1»;
  - l'ingegnere (`engine.py` `_announce_engineer`): il prefisso (4 frasi fisse)
    e l'azione della leva **senza il numero di click** («Ammorbidisci la barra
    antirollio anteriore»), più «Riporta l'assetto com'era.». Le leve dette a
    voce sono **24** (la parte dopo «quindi» nei `remedy(...)` dei profili) più
    le 4 della pressione (`pressure_remedy`: su/giù × anteriore/posteriore). Il
    numero di click è dentro la frase, non in coda: toglierlo a macchina dà
    italiano rotto («Togli di ala posteriore»), quindi le frasi a voce si
    scrivono a mano, una per leva, vere e col tono del 21/10. Prefisso e azione
    si dicono come **due WAV in fila** (scelta mia: ~1 000 caratteri contro
    ~8 000 per le frasi intere); se all'ascolto lo stacco disturba, si passa
    alle frasi intere, che stanno comunque nel piano Starter;
- ogni altra frase che `Voice.say` riceve in italiano. I chiamanti sono
  `engine.py` (avvisi e ingegnere) e `diagnostics.py` (il «Self test
  completato.» dell'autodiagnosi, che resta su SAPI5 di proposito: è il test
  della voce di sistema).

**Lo schermo tiene i numeri.** Oggi il testo dell'avviso è lo stesso a voce e a
schermo (`cue.message`). Si separa, come già fanno le parole d'innesco
(`_spoken_forms`): a voce la frase generale, a schermo quella col valore (scelta
mia; il pilota ha detto che i valori li guarda a schermo). La chiave del
manifest è il testo detto a voce.

Ogni frase riscritta resta vera: stesso significato, stessa direzione, solo
senza il valore.

Il controllo «nessuna frase senza WAV» non può più appoggiarsi solo alla
scansione di `tools/render_cues.py`, che non vede le frasi costruite a runtime:
serve un elenco delle frasi dette a voce costruito dal codice stesso (le tabelle
delle frasi, le leve dei profili, i prefissi), da cui partono sia la
generazione sia il test.

## La generazione

- Uno script in `tools/` (il successore di `tools/render_cues.py`, che resta per
  Piper o viene sostituito: scelta del costruttore) chiama l'API **Text to
  Speech** di ElevenLabs per ogni frase dell'elenco, per le due voci, col modello
  e le impostazioni sopra, formato **PCM 22 050 Hz mono 16 bit** (`pcm_22050`; il
  player e il filtro radio di HONE leggono già questo formato), e scrive i WAV e
  il `manifest.json` come oggi.
- La chiave dell'API la mette il pilota in un file fuori dal progetto (per
  esempio `%USERPROFILE%\.elevenlabs-key`, creato a mano con Blocco note) o in una
  variabile d'ambiente; lo script la legge da lì e non la stampa mai.
- Lo script conta i caratteri prima di chiamare l'API e lo dice, e rigenera solo
  le frasi che mancano o sono cambiate (per non pagare due volte).
- Le voci si identificano per `voice_id`. Lo script li trova per nome fra le
  voci dell'account (`GET /v1/voices`) e, se mancano, si ferma dicendo al pilota
  di aggiungere MarcoTrox e Tiziana a «My voices» dalla libreria (un clic
  ciascuna); poi li scrive nello script.
- L'API restituisce PCM grezzo: lo script aggiunge l'intestazione WAV (il player
  e `radioize_wav` vogliono un RIFF).
- Accanto al manifest un file con voce, modello e impostazioni per ogni frase:
  se cambia un'impostazione, la frase si rigenera; altrimenti no.
- **Ascolto e ritocco.** Con stabilità al 30 % ogni registrazione è diversa, e le
  parole singole (le parole d'innesco: «gas», «prima», «scala») possono venire
  male. Dopo la generazione: una pagina d'ascolto con tutte le frasi via filtro
  radio, il pilota segna quelle che non vanno, un comando rigenera solo quelle.
- Prima del rendering vero: il pilota fa l'abbonamento al piano **Starter**
  (include la licenza commerciale; 30 000 crediti al mese) solo se l'elenco
  conta meno di ~25 000 caratteri per le due voci; altrimenti **Creator**. Lo
  decide il conto esatto dei caratteri, fatto prima di pagare.

## Il default maschile

`voice.male` passa a `true` nella configurazione di base. Il `config.toml` del
pilota ha già `male = false` scritto dal vecchio modello, che non si distingue da
una scelta: niente migrazione automatica (scelta mia). Il pilota attiva la voce
maschile una volta dall'hub, o lo faccio io su sua richiesta.

## Il conto

Contato sul codice: ~3 000 caratteri per voce con prefisso e azione separati,
~6 000 per le due voci (~20 000 con le frasi intere). Il piano **Starter** basta,
con margine per i ritocchi.

## Vincoli

- Mai scrivere in `C:\Users\undrg\Documents\ACCoach`; mai importare
  `accoach.config` fuori dai test isolati.
- La chiave non passa mai dalla chat né dai log.
- I test non chiamano mai l'API (rete finta).
- Il tono del 21/10 per ogni frase nuova (`tests/tono.py` superficie `coach`,
  massimo 8 parole per la voce).

## Scelte mie

1. **Voce femminile: Tiziana** («Smart, Balanced and Credible»), stesse
   impostazioni di MarcoTrox. Il pilota ha detto «per me è uguale».
2. «Qui perdi N decimi» e «Benzina per circa N giri» **restano col numero**.
3. Si registra solo l'italiano; l'inglese resta SAPI5.
4. La chiave in un file fuori dal progetto o in una variabile d'ambiente.
5. Il piano: Starter (conto sopra).
6. Prefisso e azione dell'ingegnere come due WAV in fila.
7. Lo schermo tiene i numeri; solo la voce li toglie.
8. Le frasi delle leve senza click le scrivo io, a mano.
9. Niente migrazione automatica del `male = false` già scritto.
