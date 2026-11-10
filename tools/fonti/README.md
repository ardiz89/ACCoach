# Fonti pubbliche per pista

Questo strumento raccoglie video e post su una pista di ACC. Ne tira fuori i fatti curva
per curva e tiene solo quelli che reggono. Il risultato finisce in
`src/accoach/trackfacts/<pista>.json`, più una pagina di controllo per te.

Lavora tutto offline, tranne due comandi: `check-actors` e `collect` parlano con Apify.

## Prima di cominciare

### Il token Apify

Il token si legge in quest'ordine, e vince il primo che trovi.

1. La variabile d'ambiente `APIFY_API_TOKEN`.
2. Il file che passi con `--env-file`. Vale la riga `APIFY_API_TOKEN=...` e anche
   `export APIFY_API_TOKEN=...`, con o senza virgolette.
3. Il file `.apify-key` nella tua cartella utente.

Il token sta su una riga sola. Niente spazi dentro, solo caratteri ASCII. Se il file ha
due righe, per esempio una chiave nuova e una vecchia, il comando si ferma. Non stampa
mai il token, nemmeno quando si ferma.

### Il database

Ogni comando, tranne `check-actors`, vuole `--db`. Gli passi una cartella o un file.
Non c'è un valore predefinito. Tienilo fuori dal repository.

## L'ordine dei comandi

Negli esempi `F` sta per `python tools/fonti/fonti.py --db <cartella>`. Il piano di
Imola è `tools/fonti/piani/imola.json`.

1. Controlla il piano contro lo schema degli attori. È gratis, non avvia nessuna corsa.

   ```
   python tools/fonti/fonti.py check-actors --plan tools/fonti/piani/imola.json
   ```

   Ti dice le chiavi che l'attore non conosce e i valori non ammessi. Correggi il piano
   finché dice «Nessun problema».

2. Guarda cosa costerà. Ogni voce ha il suo `cost_per_item_usd`, moltiplicato per
   `max_items`.

   ```
   F collect --track imola --plan tools/fonti/piani/imola.json --dry-run
   ```

3. Raccogli.

   ```
   F collect --track imola --plan tools/fonti/piani/imola.json
   ```

   - Ogni voce ha una quota fissa del tetto di 2 USD. La quota è quanto resta diviso le
     voci ancora da fare.
   - L'id della corsa si salva prima di aspettare. Se Apify ci mette troppo, rilancia lo
     stesso comando. Riprende la corsa e non la paga di nuovo.
   - Gli elementi grezzi si salvano in `raw_items` prima di leggerli. Un elemento guasto
     si salta, gli altri restano.
   - Una voce che non dà nemmeno un testo non si segna finita. Il comando te lo dice.
     Controlla l'input con `check-actors`, poi rifai solo quella voce con
     `--force --only N`. I numeri delle voci partono da 1, come nel dry-run.
   - Una corsa finita con stato FAILED, ABORTED o TIMED-OUT non si segna finita. Il
     comando dice lo stato. Gli elementi arrivati restano in `raw_items`.
   - Per YouTube il comando dice da quale campo ha letto i sottotitoli: `srt`, `vtt`,
     `plaintext` o `text`. Se non ne trova nessuno, elenca le chiavi che ha visto.

4. Guarda quante righe hai.

   ```
   F status
   ```

5. Estrai i fatti.

   ```
   F pending --kind extract --track imola --out <cartella lavori>
   F ingest --model <modello> <risposte>
   ```

   I lavori si scrivono solo per i testi che nominano almeno una curva.

6. Valuta chi parla.

   ```
   F pending --kind rate --track imola --out <cartella lavori>
   F ingest --model <modello> <risposte>
   ```

   Il rate viene dopo l'estrazione. Si scrive solo per i testi il cui autore ha già un
   fatto, perché serve solo a pesare un fatto.

7. Guarda il consenso.

   ```
   F consensus --track imola
   ```

   Frenata e marcia votano solo con le fonti GT3. Gli altri tipi contano tutte le fonti
   ACC.

   - La classe la dà solo il titolo. GT3 Cup, Trofeo, GT2, M2, TCX e i modelli GT4 non
     sono GT3.
   - Descrizione e flair non danno la classe. Se nominano un'altra classe, la tolgono.
   - Una fonte che non nomina nessuna classe è «GT3 presunta» e vota come la GT3. In ACC
     la classe di base è la GT3: l'ha deciso il pilota il 10/11.
   - Il gioco lo dicono il titolo o il sottoreddit. La descrizione vale solo col nome
     intero o con «in ACC», e se non nomina un altro gioco.
   - Un commento che dice un'altra classe, per esempio «gt4», ha la sua classe.
   - Un canale YouTube con un tempo sul giro nel titolo, per esempio «Imola 1:39.2», è un
     pilota con tempo, quindi affidabile per le frenate. Conta solo la forma coi due punti.
   - Le altre classi non votano. Se dicono un valore diverso, la voce diventa contesa.

8. Fai controllare i fatti verificati.

   ```
   F pending --kind factcheck --track imola --out <cartella lavori>
   F ingest --model <modello> <risposte>
   ```

   Un fatto senza nessun testo indipendente non dà un lavoro. Il comando lo dice.

9. Esporta e guarda la pagina.

   ```
   F export --track imola
   F review --track imola --out <file .html>
   ```

   Esce solo un verificato con almeno un controllo `confermato` e nessun `respinto`.

## Lavori e risposte

- `pending` scrive un file per lavoro, per esempio `extract-97ee69d68d55.job.json`.
  Toglie dalla cartella i lavori della stessa pista che non servono più.
- Le istruzioni per l'agente stanno in `tools/fonti/prompts/`, un file per tipo.
- Per ogni lavoro ci vuole un file di risposta, con lo stesso nome e `.answer.json` al
  posto di `.job.json`. Per esempio `extract-97ee69d68d55.answer.json`.
- Se dai un gruppo di lavori a un subagente, lui scrive un file di risposta per ognuno.
  Mai due risposte nello stesso file.
- La risposta è un solo oggetto JSON. Un solo recinto ```` ```json ```` attorno va bene,
  `ingest` lo toglie. Testo prima o dopo, o due recinti, e la risposta si rifiuta.
- `--model` è il nome del modello che ha risposto, per esempio `claude-opus-5-5`. Usa
  sempre lo stesso nome per lo stesso modello. Due modelli diversi sono due risposte
  diverse, e una risposta si congela una volta sola per modello.
- `ingest` va avanti anche se un file si rifiuta, e alla fine esce con 1. Per ogni file
  stampa i fatti, il ruolo o il verdetto.

## Cambiare un prompt

La prima riga di ogni prompt è `prompt_version: N`.

- Se cambi il senso di un prompt, alza `N`.
- Il `pending` dopo l'aumento ripropone tutti i lavori di quel tipo.
- Da quel momento consenso ed esportazione ignorano le risposte della versione vecchia.
  Fino a quando non hai congelato le nuove, quei fatti spariscono dalla pagina e
  dall'esportazione.
- Non alzare la versione a metà di una corsa. Se lo fai, rifai tutti i lavori di quel
  tipo prima di esportare.
