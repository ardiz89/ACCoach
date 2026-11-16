# Fonti pubbliche per pista — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una pipeline ripetibile che porta da YouTube e Reddit, via Apify, una
base dati di fatti per curva verificati e citati per Imola su ACC, più una
pagina di controllo.

**Architecture:**
- **Il pacchetto** è `tools/fonti/`, fuori dal bundle dell'app. Ha un
  database SQLite delle fonti fuori dal repository, e un comando
  `python tools/fonti/fonti.py <sottocomando>`.
- **I passi deterministici** sono raccolta, verifica, consenso, esportazione e
  pagina, e sono codice Python.
- **I passi con l'AI** sono estrazione, valutazione e fact-check. Li fanno
  subagenti di Claude Code: leggono file di lavoro scritti da `pending` e
  scrivono JSON che `ingest` controlla e congela.

**Tech Stack:**
- Python 3.12, solo libreria standard: `sqlite3`, `urllib`, `hashlib`,
  `json`, `html`.
- L'API REST di Apify v2.
- pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-fonti-pista-design.md`

## Global Constraints

- **Test e privacy.**
  - Test senza rete. Apify si finge con un oggetto HTTP iniettato e le
    risposte degli agenti sono file JSON in `tests/fixtures/fonti/`.
  - Test con la casa finta (`USERPROFILE`/`HOME` puntati a una cartella
    finta), `QT_QPA_PLATFORM=offscreen` e `PYTHONPATH=src`. Mai
    `Documents\ACCoach` vero.
  - Il token Apify non compare mai in stampa, log, eccezioni, file del
    repository o database.
  - Il nome dell'account Windows non compare nei file del repository, come
    impone `tests/test_privacy_repo.py`.
- **Dati e contenuti.**
  - Il database delle fonti sta in una cartella passata con `--db`. Non ha
    un valore predefinito dentro il repository o dentro `Documents\ACCoach`.
  - Il testo grezzo delle fonti non entra mai nel repository. Nel file
    esportato le citazioni sono al massimo di 15 parole.
  - Contano solo le fonti su ACC. Le altre si salvano marcate
    `game != "acc"` e non entrano mai nel consenso né nell'esportazione.
- **Determinismo.**
  - A parità di database l'esportazione è identica byte per byte: ordinamento
    fisso, `json.dumps(..., sort_keys=True, ensure_ascii=False, indent=1)` e
    fine riga `\n`.
  - Un risultato degli agenti si congela per (`sha256` del testo, `kind`,
    `prompt_version`, `model`). Un secondo `ingest` della stessa chiave si
    rifiuta.
- **Costi.** Tetto Apify per pista `CAP_USD = 2.0` per Imola. La spesa si
  misura come differenza di `monthlyUsageUsd` su `/v2/users/me/limits`
  rispetto alla base salvata alla prima raccolta della pista.
- **Lavoro sul repository.**
  - Testi in italiano col tu, frasi brevi e virgola decimale nella pagina di
    controllo.
  - Commit con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e
    `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`.
  - Niente push, niente fusione: le fa il controllore.

## Review Focus

1. **Sottotitoli automatici con nomi storpiati**, come «tamburelo», «acqua
   minerale» o «the rivazza». La curva va trovata tramite gli alias e non
   scartata (Task 3, `test_alias_storpiati`).
2. **Una citazione quasi uguale**, con un apostrofo tipografico, doppi spazi o
   un a capo, deve passare. Una citazione con una parola cambiata deve essere
   scartata (Task 3, `test_citazione_normalizzata_e_parola_cambiata`).
3. **Lo stesso autore su due video o due commenti** conta come una fonte sola
   (Task 5, `test_stesso_autore_una_fonte`).
4. **La raccolta interrotta a metà** e poi rilanciata non duplica i testi e
   non spende due volte per gli stessi elementi (Task 2,
   `test_raccolta_rilanciata_non_duplica`).
5. **Un JSON degli agenti malformato o con campi in più** viene rifiutato
   intero, con il motivo, e non viene congelato a metà (Task 4,
   `test_json_malformato_rifiutato_intero`).

---

### Task 1: Database delle fonti e comando

**Files:**
- Create: `tools/fonti/__init__.py`, `tools/fonti/db.py`, `tools/fonti/fonti.py`
- Test: `tests/test_fonti_db.py`

**Interfaces:**
- Produces:
  - `db.open_db(path: Path) -> sqlite3.Connection`. Crea lo schema se manca
    e imposta `PRAGMA user_version = 1`.
  - Tabelle e colonne minime:
    - `sources(id INTEGER PK, platform TEXT CHECK IN ('youtube','reddit'), url TEXT UNIQUE, author TEXT, title TEXT, published TEXT, game TEXT, track TEXT, meta_json TEXT)`;
    - `texts(sha256 TEXT PK, source_id INT, kind TEXT CHECK IN ('transcript','post','comment'), author TEXT, body TEXT, segments_json TEXT, collected_at TEXT)`, dove `segments_json` è la lista `[{"start_s": float, "text": str}]` per i sottotitoli;
    - `results(id PK, sha256, kind TEXT CHECK IN ('extract','rate','factcheck'), prompt_version TEXT, model TEXT, payload_json TEXT, frozen_at TEXT, UNIQUE(sha256, kind, prompt_version, model))`;
    - `facts(id PK, result_id, track, corner, type, value, quote, offset INT, start_s REAL NULL, author, source_id)`;
    - `rejects(id PK, result_id, reason TEXT, item_json TEXT)`;
    - `spend(track TEXT PK, baseline_usd REAL, last_usd REAL, cap_usd REAL)`.
  - `db.add_text(conn, source_id, kind, author, body, segments=None) -> tuple[str, bool]`. Restituisce `(sha256, nuovo)` e calcola lo `sha256` sul `body` in UTF-8.
  - `fonti.py` contiene `argparse` con il parametro globale obbligatorio
    `--db PATH` e i sottocomandi `status`, `collect`, `pending`, `ingest`,
    `consensus`, `export` e `review`. Il comando `status` stampa quante righe
    ha ogni tabella. Gli altri sottocomandi arrivano nei task successivi.

- [ ] **Step 1: test.**
  - `test_schema_creato`: `open_db` su un file nuovo produce tutte le tabelle e `user_version == 1`.
  - `test_add_text_idempotente`: lo stesso `body` due volte dà lo stesso `sha256`, con `nuovo` uguale a `True` la prima volta e `False` la seconda, e una sola riga.
  - `test_db_obbligatorio`: `fonti.py status` senza `--db` esce con un codice diverso da 0.
- [ ] **Step 2:** lancia i test e controlla che falliscano.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** lancia i test e controlla che passino.
- [ ] **Step 5:** commit «Fonti: il database e il comando».

### Task 2: Apify, token, tetto di spesa e raccolta

**Files:**
- Create: `tools/fonti/apify.py`, `tools/fonti/collect.py`
- Test: `tests/test_fonti_apify.py`, `tests/test_fonti_collect.py`, fixtures `tests/fixtures/fonti/apify_youtube.json`, `apify_reddit.json`

**Interfaces:**
- Consumes: `db.open_db` e `db.add_text` (Task 1).
- Produces:
  - `apify.load_token(env_file: Path | None) -> str`. Cerca nell'ordine:
    1. la variabile `APIFY_API_TOKEN`;
    2. la riga `APIFY_API_TOKEN=` di `env_file`;
    3. `~/.apify-key`.

    Se non trova niente solleva `TokenMissing`, con un messaggio che non
    contiene il token.
  - `class Apify(token, http=None)`, con questi metodi:
    - `usage_usd() -> float`, che legge `/users/me/limits` e restituisce
      `current.monthlyUsageUsd`;
    - `run(actor_id, run_input, max_items) -> list[dict]`, che chiama
      `POST /acts/{actor}/run-sync-get-dataset-items` con `maxItems`.

    Il parametro `http` è un callable `(method, url, headers, body) -> (status, bytes)`, sostituibile nei test.
  - `apify.guard(conn, client, track, cap_usd) -> float`. La prima volta
    salva in `spend` la base. Restituisce quanto resta, e solleva
    `CapReached` se il resto è ≤ 0.
  - `collect.collect(conn, client, track, plan) -> dict`. Il parametro `plan`
    è una lista di `{"actor": str, "input": dict, "max_items": int, "platform": "youtube"|"reddit"}`.
    - Chiama `guard` prima di ogni voce.
    - Salva `sources` e `texts`: per YouTube un testo `transcript` per video
      con i suoi segmenti, per Reddit un testo `post` più uno per ogni
      `comment` con il suo autore.
    - Imposta `game` con la regola deterministica `collect.game_of(title, description, subreddit) -> str`.
      Vale `"acc"` se il testo contiene, ignorando le maiuscole, `assetto corsa competizione` oppure la parola intera `acc`, o se il subreddit è `ACCompetizione`. Altrimenti vale `"altro"`.
    - Restituisce `{"sources": n_nuove, "texts": n_nuovi, "spent_usd": x}`.
  - Gli attori e gli input per Imola li sceglie l'implementatore. Si parte da
    `streamers/youtube-scraper` con i sottotitoli, mentre per Reddit si usa
    un attore pubblico di Reddit. La scelta si scrive in
    `tools/fonti/piani/imola.json`, che contiene solo dati e niente segreti.
  - Il sottocomando `fonti.py collect --track imola --plan tools/fonti/piani/imola.json [--env-file PATH] [--dry-run]`.
    Con `--dry-run` stampa le voci e il resto del budget senza chiamare
    `run`.

- [ ] **Step 1: test.**
  - `test_token_ordine_e_mai_stampato`: la variabile vince sul file. Il messaggio di `TokenMissing` e il `repr` di `Apify` non contengono il token di prova.
  - `test_guard_base_e_tetto`: base 0,54 e cap 2,0. Con uso 1,50 resta 1,04. Con uso 2,54 viene sollevato `CapReached`.
  - `test_game_of`, con casi:
    - «ACC Imola hotlap 720S» → acc;
    - «Assetto Corsa Competizione guide» → acc;
    - «iRacing Imola» → altro;
    - «accelerate» → altro, perché serve la parola intera;
    - subreddit `ACCompetizione` → acc.
  - `test_raccolta_da_fixture`: con l'`http` finto che restituisce le fixture, i testi e gli autori risultano salvati.
  - `test_raccolta_rilanciata_non_duplica`: due `collect` di fila danno al secondo giro `texts == 0`, e il numero di righe non cambia.
- [ ] **Step 2:** lancia i test e controlla che falliscano.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** lancia i test e controlla che passino.
- [ ] **Step 5:** commit «Fonti: la raccolta da Apify col tetto di spesa».

### Task 3: Vocabolario, alias delle curve e verificatore

**Files:**
- Create: `tools/fonti/vocab.py`, `tools/fonti/verify.py`
- Test: `tests/test_fonti_verify.py`

**Interfaces:**
- Produces:
  - `vocab.CORNERS["imola"]` è un dizionario da nome canonico a lista di
    alias, sempre in minuscolo. I nomi canonici sono i sette di
    `accoach.trackdata._CORNERS["imola"]`. Gli alias comprendono i numeri
    di curva usati nelle guide ACC, per esempio «turn 2», «t2» e
    «tamburello chicane», e le storpiature dei sottotitoli. L'elenco lo
    scrive l'implementatore, guardando le fixture.
  - `vocab.normalize(type, quote) -> str | None`. È deterministica, in
    italiano e in inglese, e restituisce `None` se non riconosce niente. I
    tipi di fatto sono:
    - `brake`, che restituisce `"board:<n>"` con n tra 50, 100, 150, 200,
      250 e 300, oppure `"object:<slug>"` da una lista chiusa in `vocab.OBJECTS`;
    - `gear`, che restituisce `"1"`..`"6"` da cifre, ordinali e parole, come
      «third», «3rd», «terza» e «in 3»;
    - `apex`, che restituisce `"early"`, `"middle"` oppure `"late"`;
    - `kerb`, che restituisce `"entry"`, `"apex"`, `"exit"` oppure `"none"`;
    - `line` e `mistake`, che restituiscono sempre `None` perché sono
      descrittivi.
  - `verify.norm_text(s) -> str`. Mette tutto in minuscolo, converte gli
    apostrofi e le virgolette tipografiche in quelli dritti e riduce ogni
    sequenza di spazi a uno.
  - `verify.check_fact(track, fact: dict, body: str) -> str | None`.
    Restituisce `None` se il fatto è valido, altrimenti uno di questi
    motivi: `"citazione_assente"`, `"numero_non_citato"`, `"curva_non_trovata"`,
    `"valore_non_normalizzabile"`, `"valore_diverso"` o `"tipo_ignoto"`.
    - Il fatto ha la forma `{"corner","type","value","quote","offset"}`.
    - La citazione si cerca dopo `norm_text`, e ogni numero del valore deve
      comparire nella citazione.
    - La curva si cerca nella citazione oppure entro 300 caratteri prima di
      `offset`.
    - Per i tipi con vocabolario vale `normalize(type, quote) == value`.

- [ ] **Step 1: test.**
  - `test_fatto_valido`: `quote="brake at the 100 board into acque minerali"`, `value="board:100"` → None.
  - `test_citazione_normalizzata_e_parola_cambiata`: una citazione con «’» e doppio spazio passa, mentre con «150» al posto di «100» dà `citazione_assente`.
  - `test_numero_non_citato`: `value="board:150"`, con una citazione che dice 100 → `valore_diverso`, oppure `numero_non_citato` se 150 non compare.
  - `test_alias_storpiati`: «tamburelo», «acqua minerale», «the rivazza» e «t7» vengono riconosciuti come curve canoniche.
  - `test_curva_nel_contesto`: il nome della curva sta 200 caratteri prima della citazione → None. A 400 caratteri → `curva_non_trovata`.
  - `test_gear_parole`: «third gear», «3rd», «in terza» e «down to 3» danno tutti `"3"`.
  - `test_descrittivi_non_votati`: per `line` e `mistake`, `check_fact` controlla solo la citazione e la curva.
- [ ] **Step 2:** lancia i test e controlla che falliscano.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** lancia i test e controlla che passino.
- [ ] **Step 5:** commit «Fonti: il vocabolario e il verificatore».

### Task 4: Il lavoro degli agenti (pending, istruzioni, ingest)

**Files:**
- Create:
  - `tools/fonti/agents.py`;
  - `tools/fonti/prompts/estrai.md`, `valuta.md`, `factcheck.md`, ciascuno
    con una riga `prompt_version: 1` in testa.
- Test: `tests/test_fonti_agents.py`, fixtures `tests/fixtures/fonti/risposta_estrai.json`, `risposta_valuta.json`, `risposta_factcheck.json`

**Interfaces:**
- Consumes: `db` (Task 1) e `verify.check_fact` (Task 3).
- Produces:
  - `agents.pending(conn, kind, track, out_dir: Path) -> list[Path]`. Per
    ogni lavoro ancora da fare scrive `out_dir/<kind>-<sha256[:12]>.job.json`,
    con dentro `{"kind","sha256","track","prompt_version","body","segments","meta","corners"}`.
    - Per `extract` e `rate` lo fa solo per i testi con `game == "acc"`
      privi di un risultato congelato per quella chiave.
    - Per `factcheck` prende i fatti nello stato verificato del Task 5, e
      il job contiene il fatto, le sue citazioni e i testi ACC di quella
      curva.
  - `agents.ingest(conn, answer_path: Path, model: str) -> dict`. Accetta il
    JSON solo se ha esattamente le chiavi di schema per `kind`:
    - `extract`: `{"sha256","kind","facts":[{"corner","type","value","quote","offset"}]}`;
    - `rate`: `{"sha256","kind","speaker":{"name","role":"pilota|coach|anonimo"},"lap_time":str|null,"car":str|null,"reasons":[{"claim","quote","offset"}]}`;
    - `factcheck`: `{"fact_key","kind","verdict":"confermato|respinto","reason","quote","offset"}`.

    Se lo schema è sbagliato o il JSON è malformato, solleva
    `AnswerRejected(reason)` e non scrive niente. Se va bene, in una sola
    transazione:
    - congela il `results`;
    - passa ogni fatto o ragione per `check_fact` (le citazioni di `rate` e
      `factcheck` si controllano solo con `citazione_assente`);
    - salva i fatti in `facts` e gli altri in `rejects` col motivo.

    Una chiave già congelata dà `AnswerRejected("gia_congelato")`.
    Restituisce `{"facts": n, "rejects": m}`.
  - Le istruzioni (`prompts/*.md`) dicono all'agente di restituire solo lo
    schema e di citare le parole esatte. Gli dicono anche di non dedurre,
    di non tradurre la citazione e di lasciare `facts` vuoto se il testo non
    parla di Imola su ACC.
  - Il sottocomando `fonti.py pending --kind extract|rate|factcheck --track imola --out DIR` e
    `fonti.py ingest --model MODEL FILE...`.

- [ ] **Step 1: test.**
  - `test_pending_solo_acc_e_non_congelati`: dopo un `ingest`, `pending` non ripropone quel testo, e un testo `altro` non viene mai proposto.
  - `test_ingest_fixture`: la fixture `risposta_estrai.json` contiene un fatto buono e uno con citazione inventata. Risultano 1 fatto e 1 scarto con `citazione_assente`.
  - `test_json_malformato_rifiutato_intero`: un JSON troncato e uno con una chiave in più danno `AnswerRejected`, e le tabelle restano invariate.
  - `test_gia_congelato`: un secondo `ingest` dello stesso file dà `AnswerRejected("gia_congelato")`.
  - `test_prompt_version_letta_dal_file`: la versione nel job è quella della prima riga del prompt.
- [ ] **Step 2:** lancia i test e controlla che falliscano.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** lancia i test e controlla che passino.
- [ ] **Step 5:** commit «Fonti: il lavoro degli agenti si congela solo se citato».

### Task 5: Consenso

**Files:**
- Create: `tools/fonti/consensus.py`
- Test: `tests/test_fonti_consensus.py`

**Interfaces:**
- Consumes: le tabelle `facts`, `sources` e `results(kind='rate')`.
- Produces:
  - `consensus.build(conn, track) -> list[dict]`. Restituisce una voce per
    ogni (`corner`, `type`), ordinata per l'ordine delle curve in
    `vocab.CORNERS` e poi per `type`. Ogni voce ha la forma
    `{"corner","type","state","values":[{"value","authors":[...],"sources":[{"url","start_s","quote"}]}],"fact_key"}`.
    - **Autori indipendenti.** L'autore si identifica con `platform:author`
      in minuscolo.
    - **Lo stato `verificato`** si dà a un tipo con vocabolario quando un
      solo valore ha almeno 2 autori indipendenti e nessun altro valore ha
      almeno 2 autori.
    - **Le frenate** (`brake`) richiedono in più che almeno un autore
      abbia, nella sua valutazione `rate` più recente, `role` uguale a
      `pilota` o `coach` con `name` non vuoto.
    - **Lo stato `conteso`** si dà quando due valori diversi hanno ciascuno
      almeno 2 autori, oppure quando un valore ha 2 autori e un altro ne
      ha 1 affidabile.
    - **Lo stato `singolo`** vale in tutti gli altri casi.
    - **I tipi descrittivi** (`line`, `mistake`) hanno sempre lo stato
      `descrittivo`.
    - **Il `fact_key`** è `sha256` di `track|corner|type|value` per le voci
      verificate, e `None` per le altre.
  - Solo i fatti con `game == "acc"` entrano. Un fatto respinto dal
    fact-check non cambia lo stato, che resta del consenso: lo legge
    l'esportazione.

- [ ] **Step 1: test.**
  - `test_due_autori_verificato`: 2 autori su `gear` «3» alle Acque Minerali danno `verificato`. Su `brake` «board:100» serve che uno dei due sia `coach` con un nome.
  - `test_pending_factcheck_usa_verificati`: `agents.pending(kind="factcheck")` scrive un job per ogni voce `verificato`, e nessuno per `singolo` e `conteso`. Questo pinna la parte di `pending` del Task 4 che dipende da `consensus.build`, importato dentro la funzione.
  - `test_brake_senza_affidabile_resta_singolo`: due anonimi su `brake` danno `singolo`.
  - `test_stesso_autore_una_fonte`: lo stesso canale su due video dà `singolo`.
  - `test_conteso`: 2 autori su 100 e 2 su 150 danno `conteso`, con entrambi i valori presenti.
  - `test_non_acc_escluso`: i fatti da fonti `altro` non contano.
  - `test_ordinamento_deterministico`: un inserimento in ordine diverso dà un output identico.
- [ ] **Step 2:** lancia i test e controlla che falliscano.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** lancia i test e controlla che passino.
- [ ] **Step 5:** commit «Fonti: il consenso fra autori indipendenti».

### Task 6: Esportazione e pagina di controllo

**Files:**
- Create: `tools/fonti/export.py`, `tools/fonti/review.py`, `src/accoach/trackfacts/__init__.py` (vuoto)
- Test: `tests/test_fonti_export.py`

**Interfaces:**
- Consumes: `consensus.build` (Task 5) e i `results(kind='factcheck')`.
- Produces:
  - `export.export(conn, track, out: Path) -> int`. Scrive
    `src/accoach/trackfacts/<track>.json` nella forma
    `{"track","version":1,"facts":[{"corner","type","value","sources":[{"url","start_s","quote"}]}]}`.
    - Esporta solo le voci `verificato` il cui `fact_key` ha un factcheck
      `confermato` e nessun `respinto`.
    - Le citazioni vengono tagliate a 15 parole.
    - Il JSON è deterministico, come dicono i Global Constraints.
    - Restituisce il numero di fatti esportati.
  - `review.render(conn, track, out: Path) -> Path`. Scrive una pagina HTML
    statica, senza script esterni. Per ogni curva, nell'ordine, ci sono
    quattro sezioni: «Verificati», «Contesi», «Una fonte sola» e «Respinti
    dal controllo», ciascuna con la sua ragione. Ogni sezione mostra
    valore, citazione breve, autore e link con il minuto, con
    `&t=<s>s` per YouTube.
    - In testa compaiono il conteggio degli scarti per motivo e la spesa
      Apify della pista.
    - Testi in italiano col tu.
  - I sottocomandi `fonti.py export --track imola` e `fonti.py review --track imola --out FILE`.

- [ ] **Step 1: test.**
  - `test_export_solo_confermati`: un verificato con factcheck confermato viene esportato, uno respinto no, e un singolo non viene mai esportato.
  - `test_export_identico_due_volte`: due esportazioni danno gli stessi byte.
  - `test_citazione_15_parole`: una citazione di 30 parole esce con 15.
  - `test_review_sezioni_e_link`: la pagina contiene le quattro intestazioni, `&t=95s` per `start_s=95.4` e nessun testo grezzo intero.
- [ ] **Step 2:** lancia i test e controlla che falliscano.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** lancia i test e controlla che passino.
- [ ] **Step 5:** lancia la suite completa con la casa finta. Deve passare
  tutto, compresi `test_privacy_repo` e `test_tono` se toccano i nuovi
  file.
- [ ] **Step 6:** commit «Fonti: l'esportazione e la pagina di controllo».

### Task 7 (controllore, non subagente): la corsa su Imola

Questo task lo fa il controllore della sessione. Spende soldi veri e lancia
gli agenti.

- [ ] Esegui `collect --dry-run` e riferisci al pilota le voci, la stima e
  il resto del budget. Si procede solo entro i 2 dollari.
- [ ] Esegui `collect` per davvero.
- [ ] Per `rate`, `extract` e `factcheck`, in quest'ordine:
  - esegui `pending`;
  - dai un subagente per gruppo di job, con il prompt del file e un modello
    fissato e annotato;
  - fai `ingest` delle risposte.

  Il passo `factcheck` va fatto dopo un primo `consensus`.
- [ ] Esegui `export` e `review`, poi il commit del solo
  `src/accoach/trackfacts/imola.json`.
- [ ] Riferisci al pilota:
  - i fatti per curva, con le Acque Minerali in testa;
  - i contesi;
  - gli scarti per motivo;
  - la spesa reale.

  Mandagli anche la pagina di controllo.
