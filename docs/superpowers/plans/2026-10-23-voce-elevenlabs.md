# La voce del coach con ElevenLabs — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ogni frase italiana che coach e ingegnere dicono a voce è un elenco chiuso, senza numeri di dettaglio, generato una volta con ElevenLabs in due voci (MarcoTrox predefinita, Tiziana), e un test impedisce che una frase cada su SAPI5.

**Architecture:** gli avvisi con valori (pressioni, temperature, ABS/TC) portano una forma a voce senza numeri accanto al testo a schermo; l'ingegnere dice prefisso e leva come due WAV, con le frasi delle leve scritte a mano in una tabella; un modulo `coaching/spoken.py` elenca dal codice tutte le frasi dette; `tools/render_voice.py` le genera via API e scrive WAV + manifest + una pagina d'ascolto; il test di copertura confronta l'elenco col manifest.

**Tech Stack:** Python 3.11+, pytest, `urllib` (nessuna dipendenza nuova), ElevenLabs Text to Speech API (`eleven_multilingual_v2`, `pcm_22050`).

**Spec:** `docs/superpowers/specs/2026-10-23-voce-elevenlabs-design.md`

## Global Constraints

- Voce maschile: `voice_id` `W71zT1VwIFFx3mMGH2uZ` (MarcoTrox); femminile: `RXoaSpLaWTEckJgPUBG3` (Tiziana). Modello `eleven_multilingual_v2`. Impostazioni per entrambe: `speed` 1.10, `stability` 0.30, `similarity_boost` 0.70, `style` 0.0. Formato `pcm_22050` (PCM 16 bit mono 22 050 Hz, senza intestazione: lo script aggiunge il RIFF).
- Cartelle: maschile `src/accoach/voice_cues_male/`, femminile `src/accoach/voice_cues/` (stessi nomi di oggi), `manifest.json` = `{testo detto: file}`; nome file `cue_<sha1(testo)[:10]>.wav` come oggi.
- `voice.male` predefinito `true` (oggi `false`). Nessuna migrazione del `config.toml` esistente.
- La voce non dice numeri di dettaglio, salvo «Qui perdi N decimi» (1-25) e «Benzina per circa N giri» (1-3), che restano. Lo schermo tiene i numeri.
- Ogni frase a voce: tono del 21/10 (`tests/tono.py`, superficie `coach`, al massimo 8 parole per frase), vera sul codice, stesso significato e direzione della frase col numero.
- La chiave dell'API: variabile d'ambiente `ELEVENLABS_API_KEY` o il file `%USERPROFILE%\.elevenlabs-key` (fuori dal repo). Mai stampata, mai nei log, mai nel repo. I test non chiamano mai la rete.
- Mai scrivere in `%USERPROFILE%\Documents\ACCoach`; mai importare `accoach.config` fuori dai test isolati.
- Inglese: invariato (SAPI5). `diagnostics.py` «Self test completato.» resta su SAPI5 di proposito.
- Commenti nello stile dei file vicini (italiano, il perché).

## Review Focus

1. Una frase generalizzata che dice la direzione sbagliata (gonfie/sgonfie, calde/fredde, alza/abbassa, ammorbidisci/irrigidisci). Test nei Task 1 e 2.
2. Una leva di un profilo (GT3, Formula, Road, più le 4 della pressione) senza frase a voce: cadrebbe su SAPI5. Test nel Task 2.
3. Il focus attivo: la parola d'innesco resta la voce, la frase generale non la scavalca. Test nel Task 1.
4. Una frase cambiata dopo la generazione: deve risultare «da rigenerare», non usare il WAV vecchio di un testo diverso. Test nel Task 4.
5. La chiave che finisce in un messaggio d'errore o in un log. Test nel Task 4.

---

### Task 1: Gli avvisi dicono a voce la frase generale, lo schermo tiene i numeri

**Files:** Modify `src/accoach/coaching/cue.py` (`Cue` aggiunge `voice: str | None = None`), `coaching/pressure.py`, `coaching/tyretemp.py`, `coaching/advisor.py`, `src/accoach/engine.py` (`_spoken_forms`), `src/accoach/i18n.py` (`_CUE_EN`/`_CUE_EN_PATTERNS` se servono). Test: `tests/test_voce_generale.py`.

**Interfaces — Produces:** `Cue.voice` (testo italiano detto a voce; `None` = uguale a `message`). `_spoken_forms(cue, focus_theme, lang) -> (voice, screen)`: con focus attivo e parola d'innesco → la parola; altrimenti `cue.voice or cue.message` a voce (in italiano; in inglese la voce resta la traduzione di `message`, come oggi), `message` a schermo.

Frasi a voce (significato fissato; la forma esatta la scrive l'implementatore col tono, ≤ 8 parole per frase, e la riporta nel rapporto):
- pressione alta: anteriori/posteriori «troppo gonfie», togli pressione a freddo; bassa: «troppo sgonfie», aggiungi pressione a freddo (4 frasi);
- temperatura: troppo calde, guida più fluido; troppo fredde, spingi per scaldarle (2 frasi, senza °C);
- ABS: blocchi davanti in più curve, alza l'ABS di uno; TC: pattini in uscita in più punti, alza il TC di uno (2 frasi, senza «dal N al N+1»; la frase «ABS già alto … bilanciamento freni» resta com'è).

- [ ] Test che falliscono: per ognuno dei 4 casi di pressione, 2 di temperatura, ABS e TC (livello noto e ignoto): `cue.message` contiene ancora il numero di oggi; `cue.voice` non contiene cifre e dice la direzione giusta (asserzioni su parole chiave: «gonfie»/«sgonfie», «calde»/«fredde», «togli»/«aggiungi», «alza»); `_spoken_forms` senza focus restituisce `(cue.voice, cue.message)`, con focus e parola d'innesco `(parola, cue.message)` (Review Focus 3); in inglese la voce è il testo tradotto di oggi; `tono.violations` vuoto sulle frasi nuove.
- [ ] Implementa; `python -m pytest tests/test_voce_generale.py tests/test_voice*.py tests/test_*pressure* tests/test_*tyretemp* tests/test_*advisor* -q`; suite intera; commit «La voce dice la regola, lo schermo il numero».

### Task 2: L'ingegnere dice il prefisso e la leva, senza click

**Files:** Create `src/accoach/engineer/voice_levers.py`. Modify `src/accoach/engine.py` (`_announce_engineer`). Test: `tests/test_voce_leve.py`.

**Interfaces — Produces:** `voice_lever(change: ProposedChange) -> str | None` (frase italiana a voce della leva, senza numeri; `None` se manca); `all_voice_levers() -> list[str]` (tutte le frasi della tabella, per il Task 3). La tabella è a mano, una voce per ogni leva distinta che i profili possono proporre: chiave = (`param`, gruppo di slot o asse, segno del passo), costruita da `ProposedChange.changes`. Coprire: ogni `remedy(...)` in `engineer/profiles/gt3.py`, `formula.py`, `road.py`, `_common.py`, più le 4 di `pressure_remedy` (su/giù × anteriore/posteriore). `_announce_engineer` dice due frasi: il prefisso (`_ENG_VOICE_PREFIX`, invariato) e `voice_lever(change)` (o `_ENG_VOICE_REVERT` per un ripristino); in inglese come oggi. Se `voice_lever` è `None` in italiano: si dice il testo di oggi senza il numero dei click e si scrive un warning nel log (non deve succedere: lo impedisce il test).

- [ ] Test che falliscono: per ogni profilo, ogni builder di rimedio (costruito con un sintomo e una fase finti come fanno i test esistenti dei profili: `grep -rn "remedy(" tests | head`) ha una `voice_lever` non vuota, senza cifre, ≤ 8 parole (Review Focus 2); la direzione è coerente col segno del passo (per esempio una leva col passo negativo su `aRBFront` dice «ammorbidisci», quella positiva «irrigidisci» — scrivi i casi a mano dalla tabella, Review Focus 1); le 4 pressioni; `_announce_engineer` in italiano chiama `voice.say` due volte (prefisso, leva) con un `Voice` finto; il ripristino dice prefisso + «Riporta l'assetto com'era.»; `tono.violations` vuoto su tutta la tabella.
- [ ] Implementa; i test del file + `tests/test_engineer*.py tests/test_engine*.py`; suite intera; commit «L'ingegnere a voce: prefisso e leva, senza click».

### Task 3: L'elenco delle frasi dette e la voce maschile predefinita

**Files:** Create `src/accoach/coaching/spoken.py`. Modify `src/accoach/config.py` (`male: bool = True`, testo del modello del config), `tools/render_cues.py` (se resta, legge l'elenco da `spoken.py`), `GUIDA.md`/`docs/FAQ.md` (la riga sulla voce maschile/femminile). Test: `tests/test_spoken_catalogue.py`.

**Interfaces — Consumes:** `Cue.voice` (Task 1), `all_voice_levers()` e i prefissi/ripristino (Task 2). **Produces:** `spoken_phrases() -> list[str]`: tutte le frasi italiane che `Voice.say` può ricevere da `engine.py`, senza duplicati, ordinate. Fonti: le frasi statiche di oggi (le stesse che `tools/render_cues.static_cue_messages()` trova), le enumerate («Qui perdi N decimi» 1-25, «Benzina per circa N giri» 1-3), le forme `voice` del Task 1, le parole d'innesco italiane (`cue.TRIGGER`), i prefissi e il ripristino e le leve del Task 2.

- [ ] Test che falliscono: `spoken_phrases()` contiene tutte e 59 le chiavi del `manifest.json` di oggi che non contengono numeri di dettaglio (cioè tutte quelle di oggi: verificalo), le 8 frasi del Task 1, tutte le leve del Task 2, i 4 prefissi e il ripristino; nessuna frase ha una cifra salvo i decimi e la benzina; un test «di chiusura» che simula il percorso vero per ogni sorgente dinamica (pressione/temperatura/advisor/ingegnere con frame finti) e verifica che il testo passato a `voice.say` sia in `spoken_phrases()` (Review Focus 2); `Config().voice.male is True`; il testo del modello scrive `male = true`.
- [ ] Implementa; i test del file + `tests/test_voice*.py tests/test_config*.py tests/test_tono.py`; suite intera; commit «L'elenco di quello che la voce dice; voce maschile predefinita».

### Task 4: Lo script che genera le voci

**Files:** Create `tools/render_voice.py`. Test: `tests/test_render_voice.py`.

**Interfaces — Consumes:** `spoken_phrases()` (Task 3). **Produces:** comando `python tools/render_voice.py [--voice male|female|both] [--dry-run] [--only "<frase>" …] [--listen]`:
- `--dry-run`: stampa quante frasi e quanti caratteri mancano per voce e il totale, senza rete e senza chiave;
- senza `--dry-run`: legge la chiave (Global Constraints), genera solo le frasi che mancano o il cui sidecar (`render.json` nella cartella: per frase voce, modello, impostazioni) è diverso (Review Focus 4), `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_22050` con `{"text", "model_id", "voice_settings": {"stability", "similarity_boost", "style", "speed"}, "language_code": "it"}`, aggiunge l'intestazione WAV, scrive `cue_<sha1[:10]>.wav`, aggiorna `manifest.json` e `render.json`; toglie dal manifest e dalla cartella le frasi che non sono più nell'elenco;
- `--only`: rigenera solo quelle frasi (i ritocchi dopo l'ascolto);
- `--listen`: scrive `voice_listen.html` (in una cartella temporanea, non nel repo) con ogni frase in entrambe le voci passata da `accoach.coaching.radio.radioize_wav`, per l'ascolto del pilota.
- Errori: un 401/402/429 si ferma con un messaggio chiaro **senza la chiave** (Review Focus 5); un errore su una frase non lascia un WAV rotto né un manifest a metà (scrittura atomica).

- [ ] Test che falliscono, con un server HTTP finto o `urllib.request.urlopen` sostituito (nessuna rete): il dry-run conta i caratteri giusti su un elenco piccolo; la generazione scrive WAV validi (RIFF, 22 050 Hz, mono, 16 bit; `radioize_wav` li legge) e il manifest; una seconda corsa non richiama l'API; cambiando `speed` nel sidecar la frase si rigenera; una frase tolta dall'elenco sparisce; un 401 produce un messaggio senza la chiave (la chiave finta è una stringa riconoscibile: il test verifica che non compaia in stdout, stderr né nei file scritti); `--only` richiama solo quelle.
- [ ] Implementa; i test del file; suite intera; commit «Lo script che genera le voci con ElevenLabs».

### Dopo i task (chi coordina, col pilota)

1. `python tools/render_voice.py --dry-run` → il conto dei caratteri al pilota; il pilota fa l'abbonamento Starter (o Creator se il conto lo chiede) e mette la chiave nel file o nella variabile (istruzioni passo passo, la chiave mai in chat).
2. Generazione delle due voci; `--listen`; la pagina d'ascolto al pilota (artifact); ritocchi con `--only`.
3. Test di copertura: aggiungere `tests/test_voice_coverage.py` che verifica che ogni `spoken_phrases()` abbia un WAV in entrambe le cartelle e che il manifest non abbia frasi fuori elenco; suite intera; commit dei WAV.
4. Revisione d'insieme, registro `docs/superpowers/ledgers/2026-10-23-voce-elevenlabs.md`, fusione nel main locale.
