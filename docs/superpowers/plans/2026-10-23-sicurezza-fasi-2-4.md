# Sicurezza fasi 2-4: irrobustire, distribuzione dell'EXE, privacy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere i punti dell'audit del 23/10 rimasti dopo la fase 1: limiti e file rotti (fase 2), una build dell'EXE che non si può avvelenare e un firewall che non cambia la rete da solo (fase 3), niente nome dell'account nel repo e nel pacchetto dei log (fase 4).

**Architecture:** Il guardiano (`src/accoach/guard.py`) prende anche il tetto alla dimensione delle richieste. I controlli sui nomi stanno dove i nomi entrano (`setup/store.py`, `trackedges.py`, `setup/ac_steps.py`). I parser dei file esterni (`trackmesh.py`, `setup/acc_format.py`, `setup/ac_format.py`) trasformano ogni file rotto in un errore loro. La build si fissa con un lock con le impronte e con le azioni di GitHub fissate al commit. La privacy si difende con un test che scansiona i file del repo.

**Tech Stack:** Python 3.11+ (sviluppo su 3.14), FastAPI/Starlette ASGI, JS vanilla (tablet.js ES5 per Safari 9), GitHub Actions su windows-latest, PowerShell 5.1, pip-tools per il lock.

**Spec:** non c'è uno spec scritto. L'autorità è il piano presentato al pilota e approvato («ok»), più i quattro rapporti dell'audit del 23/10 (riassunti qui dentro), più «Passa alle altre fasi» del pilota. Le decisioni prese senza spec sono nella sezione Decisioni, ciascuna col suo costo.

## Global Constraints

- Mai toccare `%USERPROFILE%\Documents\ACCoach` né `%USERPROFILE%\progetti\ACCoach` (è l'installazione da cui il pilota guida). I test usano la casa finta della `tests/conftest.py`.
- Mai leggere `%USERPROFILE%\.elevenlabs-key`. Mai lanciare `tools/render_voice.py` se non con `--dry-run`.
- Mai eseguire `tools/setup_firewall.ps1` né altro che cambi impostazioni di Windows, rete o firewall. Quello script si prova solo leggendone il testo.
- Mai push, PR, tag o `workflow_dispatch`: si lavora sul ramo `fix/sicurezza-fasi-2-4` e basta.
- Nessun nome di account Windows vero in un file nuovo o modificato: negli esempi `%USERPROFILE%`, `C:\Users\<account>` o `C:\Users\pilot`.
- Testi per il pilota: italiano e inglese tutti e due (`src/accoach/i18n.py`, `src/accoach/web/i18n.js`). Frasi brevi col «tu», virgola decimale, niente slogan, niente due punti a effetto, niente emoji, prima il fatto e poi cosa fare, mai la stessa frase in due posti.
- `src/accoach/web/tablet.js` resta ES5: niente arrow function, `let`/`const`, template string (lo controlla `tests/test_safari9.py`).
- TDD: il test nuovo fallisce prima della correzione e passa dopo. Suite intera (`python -m pytest -q -p no:cacheprovider`) verde prima di ogni commit.
- Commenti in italiano, che dicono il perché, con la densità del codice intorno. Commit in italiano che finiscono con:
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`
- Le guide sono due (`GUIDA.md` italiano, `docs/FAQ.md` inglese): se cambi un comportamento descritto, cambi tutte e due.

## Decisioni

1. **I percorsi assoluti nelle risposte normali restano.** Il piano diceva «percorsi relativi nelle risposte». Dopo la fase 1 quelle risposte arrivano solo al PC e a chi ha la chiave, e il JS rimanda indietro proprio quei percorsi a `/api/setup/current|preview|apply|undo`. Rifarli relativi tocca decine di route e tre pagine per un difetto LOW che la chiave ha già chiuso. Si tolgono invece i percorsi dai messaggi d'errore (Task 3) e dal pacchetto dei log (Task 9). Costo se sbagliato: un giro in più più avanti, con un chiave-portatore che vede il nome dell'account.
2. **`HONE.bat` continua a installare da `requirements.txt`.** Il lock si fa per Python 3.12, la versione della build. Chi parte dal sorgente può avere da 3.11 a 3.14, e un lock con le impronte che non si installa bloccherebbe il primo avvio. Il lock vale per la release e per il giro 3.12 della CI. Costo se sbagliato: chi usa il sorgente resta esposto a una release avvelenata su PyPI, come oggi.
3. **I nomi degli assetti rifiutano solo quello che Windows non sa scrivere**, non tutto quello che non è ASCII: un assetto si chiama anche «Monza qualifica è». Si rifiutano `< > : " / \ | ? *`, i caratteri di controllo, il punto o lo spazio in fondo, `.` e `..`, e i nomi di dispositivo (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, anche con un'estensione). Costo se sbagliato: un nome strano che Windows accetta e un'altra app no.
4. **Il firewall non cambia mai il profilo della rete in `-Auto`.** A mano lo chiede, e la risposta di default è no. La regola resta su Private e Domain. Costo se sbagliato: su una rete Public il tablet non entra finché il pilota non lancia lo script a mano e risponde sì.
5. **Il pacchetto dei log sostituisce la cartella di casa con `%USERPROFILE%`.** Il pacchetto resta «senza filtri» per tutto il resto: un log ripulito non serve a trovare un difetto (la guida lo dice già). La sostituzione è dichiarata nel pacchetto. Costo se sbagliato: nessuno per il debug, perché è reversibile.
6. **La storia di git non si riscrive.** Il nome dell'account è già nei 700 commit pubblici e non è un segreto.
7. **La release si divide in due job.** `build` ha solo `contents: read`. `publish` gira solo sui tag, ha `contents: write`, `id-token: write`, `attestations: write`, scarica lo ZIP da `build`, ne attesta la provenienza e pubblica. Costo se sbagliato: il primo tag dopo questa modifica potrebbe fallire, e lo si scopre solo su GitHub. Per questo il pilota va avvisato di provare prima un `workflow_dispatch` quando si pubblica.

## Review Focus

1. Un tablet o una pagina che manda un assetto vero (ACC, 5-15 KB) o un salvataggio della prova in pista deve passare sotto il tetto di 1 MB. Il test del Task 2 manda 200 KB e deve passare.
2. Un nome di assetto con lettere accentate o con lo spazio in mezzo deve continuare a salvarsi (Task 3).
3. Una pista vera installata, con i suoi `.kn5`, deve continuare a disegnare i bordi come prima: le correzioni del Task 4 non devono rifiutare file sani. Il Task 4 lo pinna con il fixture kn5 sano che i test hanno già.
4. Il pacchetto dei log di un utente la cui casa non è sotto `C:\Users` (per esempio `D:\Utenti\x`) deve sostituire comunque la sua casa, perché si parte da `Path.home()` e non da una stringa fissa (Task 9).
5. Un file del repo che cita `C:\Users\<account>` o `%USERPROFILE%` come esempio non deve far cadere il test della privacy (Task 8).

---

## Fase 2 — irrobustire

### Task 1: La chiave che non si crea, o non si legge per un attimo

Restano tre casi dalla fase 1 (`src/accoach/guard.py`):
- se `lan_key()` fallisce, ritenta a ogni richiesta, anche a quelle del PC, e con l'Accesso controllato alle cartelle ogni tentativo è una notifica di Defender;
- con il 503, il tablet e la pagina Ingegnere dicono «coach spento»;
- un file chiave valido che non si legge per un attimo (antivirus, backup) viene preso per rovinato e sostituito, e il tablet perde la chiave.

**Files:**
- Modify: `src/accoach/guard.py` (`lan_key`, `_leggi`)
- Modify: `src/accoach/web/tablet.js`, `src/accoach/web/tablet.html`, `src/accoach/web/engineer.js`, `src/accoach/web/i18n.js`
- Test: `tests/test_guard.py`, `tests/test_tablet_box.py`, `tests/test_engineer_scrive_ai_box.py`

**Interfaces:**
- Produces: `guard._RIPROVA_S = 60.0`; dopo un `OSError`, `lan_key()` per 60 s solleva di nuovo l'errore senza toccare il disco. `guard._dimentica()` svuota anche questo ricordo.
- Produces: chiave i18n JS `lan.noKey`, testo uguale a `_MESSAGGIO_503` di `guard.py` (it ed en).

- [ ] **Step 1: test che falliscono**

```python
def test_una_chiave_che_non_si_crea_non_si_ritenta_a_ogni_richiesta(chiave_impossibile, monkeypatch):
    # conta le scritture: tre richieste dal tablet, un solo tentativo
    ...
    assert tentativi == 1
    # passati 60 s (si sposta il tempo del ricordo), si riprova
    ...
    assert tentativi == 2

def test_una_chiave_valida_che_non_si_legge_per_un_attimo_non_si_cambia(monkeypatch):
    key = guard.lan_key(); guard._dimentica()
    # read_text solleva PermissionError una volta
    with pytest.raises(OSError):
        guard.lan_key()
    assert guard.key_path().read_text(encoding="utf-8").strip() == key
    guard._dimentica()
    assert guard.lan_key() == key
```

Più due test node, come quelli delle sonde del 401 già presenti nei due file: su un 503 di `/health` il tablet mostra `#t-off-pc` (nascosti `#t-off-closed` e `#t-off-key`), e il distintivo della pagina Ingegnere dice la frase di `lan.noKey`.

- [ ] **Step 2:** lanciali e verifica che falliscono per il motivo giusto.
- [ ] **Step 3:** In `_leggi`, `FileNotFoundError` dà `""`, ogni altro `OSError` risale. `lan_key()` ricorda l'errore per `_RIPROVA_S` in `_cache`. In tablet e pagina Ingegnere la sonda distingue 401, 503 e il resto. Nel tablet c'è un nuovo `<span id="t-off-pc" data-i18n="lan.noKey" hidden>`.
- [ ] **Step 4:** test e suite verdi.
- [ ] **Step 5:** commit.

### Task 2: Un tetto alle richieste e ai file che crescono

L'audit ha salvato 5 MB in `/api/test/save`. Con `run_id` diversi nascono file sempre nuovi. `corner-names.json` cresce senza limite con chiavi `track` nuove.

**Files:**
- Modify: `src/accoach/guard.py` (`GuardMiddleware.__call__`)
- Modify: `src/accoach/api.py` (`/api/test/save` ~2582), `src/accoach/cornernames.py` (`put`, `put_mark`)
- Test: `tests/test_guard.py`, `tests/test_limiti.py` (nuovo)

**Interfaces:**
- Produces: `guard.MAX_BODY = 1_048_576`. Sulle richieste HTTP non `GET/HEAD/OPTIONS`, se `Content-Length` supera il tetto la risposta è 413 subito. Se manca, il guardiano legge il corpo fino a `MAX_BODY + 1` byte: oltre, 413; sotto, lo ripassa all'app con un `receive` che lo rigioca. Il 413 porta il CORS come gli altri rifiuti (`_nega(..., origin)`).
- Produces: `api.MAX_TEST_RUNS = 200`. Un salvataggio che creerebbe il file numero 201 in `test_runs` risponde 409 con `detail` «too many saved test runs». Sovrascrivere un file che c'è già resta permesso.
- Produces: `cornernames.MAX_TRACK = 80` e `cornernames.MAX_TRACKS = 500`. `put` e `put_mark` sollevano `ValueError` (che le route già traducono in 400) per una `track` più lunga o per una pista nuova oltre la 500esima.

- [ ] **Step 1: test che falliscono**

```python
def test_un_corpo_oltre_il_tetto_e_413_con_o_senza_content_length(): ...
    # 1_048_577 byte con Content-Length → 413; stessa cosa in chunk senza Content-Length → 413
def test_un_assetto_vero_e_una_prova_da_200_kb_passano(): ...   # Review Focus 1
def test_test_save_si_ferma_a_200_file_ma_riscrive_quelli_che_ci_sono(): ...
def test_corner_name_con_track_troppo_lunga_o_pista_501_e_400(): ...
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** implementa le interfacce sopra. Il body si bufferizza solo quando non c'è `Content-Length`: i corpi veri sono piccoli.
- [ ] **Step 4:** test e suite verdi.
- [ ] **Step 5:** commit.

### Task 3: Nomi che Windows non sa scrivere, e percorsi fuori dalle cartelle

**Files:**
- Modify: `src/accoach/setup/store.py` (`save` ~82-106), `src/accoach/setup/web_api.py` (`_safe`, il 404 «setup unreadable» a :170)
- Modify: `src/accoach/trackedges.py` (`spline_path`), `src/accoach/setup/ac_steps.py` (`_car_folder`)
- Modify: `tools/render_voice.py` (`_prune`)
- Test: `tests/test_nomi_assetti.py` (nuovo), `tests/test_render_voice.py`

**Interfaces:**
- Produces: `store.valid_name(name: str) -> bool`, con le regole della Decisione 3. `save` la usa al posto del controllo su `/ \ :`, e solleva lo stesso `ValueError("not a plain setup name: ...")` di oggi.
- Produces: `_safe` rifiuta (403, come oggi fuori dalle radici) ogni percorso che ha una parte uguale a `store._BACKUP_DIR`. Vale per `apply`, `seed` e `undo` come destinazione e per `current` e `preview` come sorgente.
- Produces: il 404 di :170 dice `setup unreadable: <nome del file>` senza cartella e senza il testo dell'eccezione.
- Produces: `spline_path(track)` e `_car_folder(car)` danno `None` (cioè «non trovato», come oggi) per un nome con `/`, `\` o `:`, o uguale a `.` o `..`.
- Produces: `_prune` cancella solo `d / Path(f).name`, e solo se il percorso risolto sta dentro `d`.

- [ ] **Step 1: test che falliscono**

```python
@pytest.mark.parametrize("nome", ["CON", "con.backup", "LPT9", "a*b", 'a"b', "a|b", "a?", "fine.", "fine ", "..", "a\x01b"])
def test_nomi_rifiutati(nome): assert not store.valid_name(nome)

@pytest.mark.parametrize("nome", ["Monza qualifica è", "HONE_3", "gara-2 (bagnato)", "v1.2"])
def test_nomi_veri_passano(nome): assert store.valid_name(nome)   # Review Focus 2

def test_apply_con_as_name_CON_e_400_non_500_e_non_scrive(...): ...
def test_apply_dentro_accoach_backup_e_403(...): ...
def test_setup_illeggibile_non_dice_la_cartella(...): assert str(tmp_path) not in r.text
def test_spline_path_e_car_folder_rifiutano_le_risalite(...): ...
def test_prune_non_esce_dalla_cartella(...): ...   # un manifest con "../../x.wav" non tocca il file fuori
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** test e suite verdi.
- [ ] **Step 5:** commit.

### Task 4: File di mod rotti o malevoli

Il PoC dell'audit: un `.kn5` di 93 byte con `nchild=0x7fffffff` fa allocare circa 17 GB e blocca `is_physics_model` per 35 s. Su un PC con meno RAM solleva un `MemoryError` che `trackmesh.py:229` non prende. Un indice di vertice fuori misura dà un `IndexError` non preso. Un assetto ACC con `"tyrePressure": ["x", ...]`, un JSON annidato 100 000 volte o un `.ini` di AC con `VALUE=1e400` danno 500.

**Files:**
- Modify: `src/accoach/trackmesh.py` (lettura dei nodi ~180-230, raccolta ~273)
- Modify: `src/accoach/setup/acc_format.py` (~206-264), `src/accoach/setup/ac_format.py` (~116-140)
- Test: `tests/test_file_rotti.py` (nuovo)

**Interfaces:**
- Produces: ogni conteggio letto dal kn5 (`nchild`, vertici, indici, texture, materiali) si confronta coi byte che restano nel file prima di allocare: un conteggio che non può starci rende il file illeggibile, con lo stesso esito di un file troncato oggi. `MemoryError` e `IndexError` si prendono insieme a `OSError, ValueError, struct.error`. Un indice `>= nv` rende il file illeggibile.
- Produces: in `acc_format` e `ac_format` ogni foglia numerica non intera o non finita, ogni lista con elementi non interi, `RecursionError` e `OverflowError` diventano `SetupError`. Le route li rispondono già come errore dell'assetto, cioè 4xx e non 500.

- [ ] **Step 1: test che falliscono**

```python
def test_kn5_con_nchild_enorme_si_rifiuta_subito():
    t0 = time.monotonic(); assert not trackmesh.is_physics_model(kn5_93_byte)
    assert time.monotonic() - t0 < 1.0
def test_kn5_con_indice_fuori_misura_e_illeggibile_non_IndexError(): ...
def test_kn5_sano_si_legge_come_prima(): ...   # Review Focus 3, col fixture che i test usano gia'
@pytest.mark.parametrize("corpo", [tyrePressure_stringhe, json_annidato_100000, ...])
def test_assetto_acc_malformato_e_4xx_non_500(corpo): ...
def test_assetto_ac_con_1e400_e_4xx_non_500(): ...
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** implementa.
- [ ] **Step 4:** test e suite verdi.
- [ ] **Step 5:** commit.

## Fase 3 — la distribuzione dell'EXE

### Task 5: Dipendenze bloccate per versione e impronta

**Files:**
- Create: `requirements-build.in` (le righe di `requirements.txt` più `pyinstaller`), `requirements.lock` (generato)
- Modify: `.github/workflows/release.yml`, `.github/workflows/ci.yml`, `requirements.txt` (solo un commento che rimanda al lock)
- Test: `tests/test_lock.py` (nuovo)

**Interfaces:**
- Produces: `requirements.lock`, generato con `pip-compile --generate-hashes --allow-unsafe` sotto Python 3.12 (`py -3.12 -m venv <scratchpad>/lockenv`, poi `pip install pip-tools` dentro). In testa al lock c'è il comando esatto per rigenerarlo. Ogni pacchetto ha `==` e almeno un `--hash=sha256:`. PySide6 resta sotto 6.12. Le dipendenze di tutto si scaricano solo da PyPI.
- Produces: in `release.yml` si installa con `pip install --require-hashes -r requirements.lock`, e niente `cache: pip`.
- Produces: in `ci.yml` il giro 3.12 installa dal lock e poi `pip install pytest`; il giro 3.11 resta su `requirements.txt` e prova il pavimento.
- `HONE.bat` non cambia (Decisione 2).

- [ ] **Step 1: test che falliscono** (`tests/test_lock.py`)

```python
def test_ogni_riga_del_lock_ha_versione_e_impronta(): ...
def test_ogni_dipendenza_di_requirements_txt_e_nel_lock(): ...   # nomi normalizzati PEP 503
def test_pyinstaller_e_nel_lock_e_pyside6_sotto_612(): ...
def test_la_release_installa_dal_lock_con_le_impronte_e_senza_cache(): ...
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** genera il lock. Poi verifica che si installa davvero, in un venv 3.12 nuovo nella scratchpad: `pip install --require-hashes -r requirements.lock` e `python -m pytest -q -p no:cacheprovider` sul ramo. Nel rapporto scrivi le due uscite.
- [ ] **Step 4:** test e suite verdi (sulla 3.14 di sviluppo).
- [ ] **Step 5:** commit.

### Task 6: Le azioni di GitHub fissate e la provenienza dell'EXE

**Files:**
- Modify: `.github/workflows/release.yml`, `.github/workflows/ci.yml`, `HONE.spec` (`upx=False` in tutti e due i punti), `GUIDA.md`, `docs/FAQ.md` (come verificare la provenienza)
- Test: `tests/test_workflows.py` (nuovo)

**Interfaces:**
- Produces: ogni `uses:` è `owner/repo@<40 hex>  # vX.Y.Z`. Lo SHA si ricava con `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, dereferenziando i tag annotati con `gh api repos/<owner>/<repo>/git/tags/<sha>`. Azioni: `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`, `actions/download-artifact`, `actions/attest-build-provenance`, `softprops/action-gh-release`, ciascuna all'ultima release della major in uso (per `attest-build-provenance` l'ultima major). Nel rapporto metti la tabella azione → tag → SHA.
- Produces: `permissions: contents: read` in testa ai due workflow. La release ha due job (Decisione 7):
  - `build`, read-only, fa quello che c'è oggi fino all'upload dello ZIP, ed espone `zip` e `sha` come output del job;
  - `publish`, con `needs: build`, `if: startsWith(github.ref, 'refs/tags/')` e i permessi `contents: write`, `id-token: write`, `attestations: write`, scarica lo ZIP, lo attesta con `attest-build-provenance` (`subject-path`) e pubblica.
- Produces: nessun `${{ ... }}` dentro un blocco `run:`. Il ref passa da `env: REF_NAME: ${{ github.ref_name }}` e `$ref = $env:REF_NAME -replace '[^A-Za-z0-9._-]', '-'`.
- Produces: il corpo della release aggiunge, dopo l'impronta, `gh attestation verify <zip> --repo ardiz89/ACCoach`. Le due guide spiegano in una riga che cosa prova questo comando.

- [ ] **Step 1: test che falliscono** (`tests/test_workflows.py`, leggendo il testo dei `.yml` senza dipendenze nuove)

```python
def test_ogni_uses_e_fissato_a_uno_sha(): ...        # regex @[0-9a-f]{40}
def test_nessuna_espressione_dentro_run(): ...       # nei blocchi run: niente "${{"
def test_permessi_minimi_in_testa_e_scrittura_solo_su_publish(): ...
def test_publish_solo_sui_tag_e_con_attestazione(): ...
def test_upx_spento_nello_spec(): ...
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** implementa. Se c'è `actionlint` usalo, se no scrivi nel rapporto che i workflow si provano solo su GitHub.
- [ ] **Step 4:** test e suite verdi (anche `tests/test_verify_bundle.py` e `tests/test_bundle_contents.py`).
- [ ] **Step 5:** commit.

### Task 7: Lo script del firewall non cambia la rete da solo

Oggi `tools/setup_firewall.ps1`, lanciato da `HONE.bat` con `-Auto` quando `lan = true`, dopo un prompt UAC generico porta la rete attiva da Public a Private (righe ~152-156). Così allenta tutte le altre regole Private su quella rete, condivisione file compresa.

**Files:**
- Modify: `tools/setup_firewall.ps1`, `GUIDA.md`, `docs/FAQ.md`
- Test: `tests/test_firewall_script.py` (nuovo, solo lettura del testo)

**Interfaces:**
- Produces: `Set-NetConnectionProfile` compare una volta sola, dentro un ramo che richiede `-not $Auto` e una risposta `y` a una domanda con `Read-Host` la cui risposta di default è no.
- Produces: in `-Auto` su rete Public lo script crea la regola com'è oggi (Private, Domain, LocalSubnet), poi dice in due righe che su una rete Public il tablet non entra e che per cambiarla va lanciato a mano. Il controllo «c'è già tutto?» di `-Auto` non conta più un profilo Public come cosa mancante, così non chiede l'elevazione a ogni avvio.
- Produces: `.DESCRIPTION` e le guide dicono il comportamento nuovo.

- [ ] **Step 1: test che falliscono**

```python
def test_il_profilo_si_cambia_solo_a_mano_e_dopo_un_si(): ...
def test_in_auto_una_rete_public_non_chiede_l_elevazione(): ...   # sul ramo del controllo iniziale
def test_la_regola_resta_private_domain_localsubnet(): ...
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** implementa. Lo script non si esegue mai, nemmeno con `-WhatIf`.
- [ ] **Step 4:** test e suite verdi.
- [ ] **Step 5:** commit.

## Fase 4 — privacy

### Task 8: Niente nome dell'account nel repo, e un `.gitignore` che regge

**Files:**
- Modify: `.gitignore`
- Modify: ogni file tracciato che contiene `C:\Users\<nome vero>` o `C:/Users/<nome vero>` (l'audit ne ha contati 13 in 11 file: `HANDOFF-sessione-pista-2026-08-07.md`, `tests/test_logs_zip.py`, i piani, gli spec e i registri sotto `docs/superpowers/`). Trovali con `git grep -n -i -E "users[\\\\/]+[a-z0-9._-]+"` e guarda caso per caso.
- Test: `tests/test_privacy_repo.py` (nuovo)

**Interfaces:**
- Produces: `.gitignore` aggiunge `tools/.dl/`, `.superpowers/`, `.env*`, `*.key`, `.elevenlabs-key`, `*elevenlabs*key*`, `config.toml`, `*.db`, `*.sqlite*`, ciascuno con una riga di commento sul perché, come le voci che ci sono già.
- Produces: `tests/test_privacy_repo.py` legge i file di `git ls-files` (salta i binari) e cerca `[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s"'<>%`*]+)`. Il nome catturato deve stare in un elenco ammesso dichiarato nel test (`<account>`, `<user>`, `pilot`, `Public`, `Default`, `runneradmin`, più quelli di esempio che trovi nei file e che non sono nomi veri). Il test **non contiene il nome vero**, nemmeno spezzato. Un secondo test verifica che `git check-ignore` ignori `tools/.dl/x`, `.superpowers/x`, `config.toml` e `a.key`.
- Nei file sostituisci con `%USERPROFILE%` quando è una cartella di casa, con `C:\Users\pilot` nei test che vogliono un percorso realistico.

- [ ] **Step 1:** scrivi i due test e verifica che falliscono (il primo trova i 13 casi).
- [ ] **Step 2:** sostituisci e aggiorna `.gitignore`.
- [ ] **Step 3:** test e suite verdi; `git status` mostra solo i file voluti (`tools/.dl/` sparisce dagli untracked).
- [ ] **Step 4:** commit.

### Task 9: Il pacchetto dei log senza la cartella di casa

**Files:**
- Modify: `src/accoach/support.py` (`build_log_zip`, `_disclosure`, `short_notice`)
- Modify: `GUIDA.md` (riga `logs --zip`, ~934), `docs/FAQ.md` (~1071)
- Test: `tests/test_logs_zip.py`

**Interfaces:**
- Produces: `support.redact_home(text: str, home: Path | None = None) -> str`. Sostituisce con `%USERPROFILE%` ogni occorrenza della casa di `Path.home()`: forma con `\` e con `/`, senza distinguere maiuscole e minuscole, e anche raddoppiata `\\` come esce da un `repr`. Si applica a ogni membro di testo dello ZIP. I file che non sono UTF-8 si leggono con `errors="replace"` solo per sostituire, se no entrano come sono.
- Produces: il testo che accompagna il pacchetto, e le due guide, dicono che la cartella di casa è sostituita da `%USERPROFILE%` e che il resto entra com'è (Decisione 5).

- [ ] **Step 1: test che falliscono**

```python
@pytest.mark.parametrize("casa", [r"C:\Users\pilota-finto", r"D:\Utenti\pilota-finto"])   # Review Focus 4
def test_il_pacchetto_non_contiene_la_casa(tmp_path, monkeypatch, casa): ...
def test_redact_home_prende_slash_maiuscole_e_doppie_barre(): ...
def test_il_resto_del_log_resta_com_e(): ...
```

- [ ] **Step 2:** lanciali e verifica che falliscono.
- [ ] **Step 3:** implementa e aggiorna le guide.
- [ ] **Step 4:** test e suite verdi.
- [ ] **Step 5:** commit.
