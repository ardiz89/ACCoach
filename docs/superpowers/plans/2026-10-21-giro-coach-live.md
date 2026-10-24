# Il giro di Coach Live — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nel pannello «In pista» dell'hub, una procedura passo passo che accompagna il pilota da «Avvia Coach Live» al collegamento del tablet alla pagina Ingegnere, alla guida, e con un clic alla Pagella della sessione appena guidata.

**Architecture:** Il backend di Coach Live (#104) espone in `/health` anche i client remoti e il giro; un modulo puro (`livepanel.py`) trasforma la serie di risposte di `/health` e lo stato del processo nello stato del pannello; un widget Qt (`livepanel_ui.py`) interroga `/health` senza bloccare l'interfaccia e disegna i tre momenti; il report onora `?view=pagella&car=…&track=…`.

**Tech Stack:** Python 3, PySide6 (QtNetwork per le richieste), FastAPI/uvicorn (backend esistente), JavaScript vanilla.

**Spec:** `docs/superpowers/specs/2026-10-21-giro-coach-live-design.md`

## Global Constraints

- Ramo `feat/giro-coach-live` = `main` locale + PR #104: non toccare il comportamento di #104 oltre `/health`.
- L'hub non si blocca mai: niente richieste HTTP sul thread dell'interfaccia; si interroga `/health` solo mentre Coach Live è acceso, ogni ~2 s.
- «Tablet collegato» = client websocket con indirizzo diverso da 127.0.0.1, ::1 e da ogni indirizzo di questo PC.
- «ACC chiuso» = `connected` falso per almeno 60 s dopo essere stato vero nella stessa corsa di Coach Live. Tre risposte mancate di fila a `/health` = «il coach non risponde».
- Coach Live non si ferma da solo; il motore del coach non cambia.
- Ogni testo nuovo in italiano e inglese, col tono deciso col pilota: frasi brevi col tu; numeri con la virgola e l'unità; niente slogan, niente due punti a effetto, niente emoji (✓ ▶ come icone di stato sono ammessi); mai la stessa frase in due posti; prima il fatto, poi cosa fare.
- Mai scrivere in `%USERPROFILE%\Documents\ACCoach`; le prove usano una casa finta.
- Ogni test nuovo deve fallire se si toglie la cosa che prova (mutazione verificata).

## Review Focus

- Coach Live acceso ma ACC mai partito: il pannello resta al passo 3, «Sessione finita» non compare, «Ho finito» apre il report senza parametri e lo dice.
- La pagina Ingegnere aperta sul PC stesso via indirizzo di rete: il passo del tablet non si spunta.
- `/health` lento o morto: l'interfaccia resta reattiva; dopo tre mancate il pannello lo dice, e torna normale quando risponde.
- `cfg.lan` spento: niente QR inutilizzabile; una riga e il collegamento alla pagina «Dispositivi».
- Il pilota esce dalla pagina «In pista» e rientra: lo stato non riparte da capo.

---

### Task 1: `/health` dice chi è collegato e a che giro sei

**Files:**
- Modify: `src/accoach/netinfo.py` (funzione nuova), `src/accoach/server.py` (`/health`)
- Test: `tests/test_health_remote.py`

**Interfaces:**
- Produces: `netinfo.local_addresses() -> set[str]` (sempre `127.0.0.1` e `::1`, più `lan_ip()` e gli indirizzi di `socket.gethostbyname_ex(socket.gethostname())`, best-effort, mai eccezioni); in `/health` le chiavi nuove `remote_clients: int` (client websocket il cui `ws.client.host` non è in `local_addresses()`), `laps_done: int | None` (dal giro dell'ultimo stato, `lap.completed`), `best: str | None` (`lap.best` formattato, `None` se non c'è).

- [ ] **Step 1: test che falliscono**

```python
def test_local_addresses_always_has_loopback():
    a = local_addresses()
    assert {"127.0.0.1", "::1"} <= a

def test_health_counts_only_clients_from_other_machines(monkeypatch):
    # create_app(engine finto); due websocket: uno da 127.0.0.1, uno da 192.168.1.50
    # (monkeypatch di local_addresses -> {"127.0.0.1", "::1", "192.168.1.23"})
    # -> /health: clients == 2, remote_clients == 1
def test_the_pc_own_lan_address_is_not_a_tablet(monkeypatch):
    # client da 192.168.1.23 (indirizzo del PC) -> remote_clients == 0
def test_health_reports_the_lap(): # ultimo stato con lap.completed=7, lap.best="1:41.882"
    # -> laps_done == 7, best == "1:41.882"; senza stato -> None, None
```

Il TestClient di Starlette usa l'host «testclient»: per gli indirizzi veri, controlla `ws.client.host` tramite una funzione separata `_is_remote(host: str, local: set[str]) -> bool` testata direttamente, e nel test dell'endpoint monkeypatcha l'host o la funzione.

- [ ] **Step 2:** `python -m pytest tests/test_health_remote.py -q` → FAIL.
- [ ] **Step 3:** implementa; `local_addresses()` si calcola una volta per richiesta a `/health`, non per client.
- [ ] **Step 4:** stesso comando → PASS; `python -m pytest tests/test_backend_spettatore.py tests/test_live_serve_ingegnere.py -q` → PASS.
- [ ] **Step 5:** commit `"Il backend dice se il tablet e' collegato e a che giro sei"`.

---

### Task 2: lo stato del pannello, senza Qt

**Files:**
- Create: `src/accoach/livepanel.py`
- Test: `tests/test_livepanel.py`

**Interfaces:**
- Consumes: le chiavi di `/health` (Task 1).
- Produces:
  - `SILENT_AFTER = 3`, `CLOSED_AFTER_S = 60.0`, `POLL_S = 2.0`
  - `@dataclass Health: connected: bool | None; car: str | None; track: str | None; saved_laps: int | None; laps_done: int | None; best: str | None; remote_clients: int`
  - `parse_health(d: dict | None) -> Health | None` (risposta mancante o malformata → `None`)
  - `@dataclass PanelState: phase: str  # "idle" | "before" | "driving" | "finished" | "silent"`; `tablet_done: bool; tablet_now: bool; car: str | None; track: str | None; saved_laps: int | None; laps_done: int | None; best: str | None`
  - `class LiveTracker:` `feed(health: Health | None, now: float, live_running: bool) -> PanelState`; `skip_tablet() -> None`; `dismiss_finished() -> None` («Resto in pista»)
  - `report_url(base: str, car: str | None, track: str | None) -> str` → `base + "?view=pagella&car=<enc>&track=<enc>"` con entrambi presenti, altrimenti `base`.

- [ ] **Step 1: test che falliscono** (ogni regola della spec, con `now` fornito dal test):
  - `test_not_running_is_idle`
  - `test_running_without_telemetry_stays_before_and_never_finishes` (connected False per 10 minuti → `before`)
  - `test_telemetry_makes_it_driving`
  - `test_acc_closed_for_60s_after_driving_is_finished` (59 s → `driving`; 60 s → `finished`)
  - `test_three_missed_answers_is_silent_and_it_recovers` (2 `None` → fase precedente; 3 → `silent`; una risposta → torna)
  - `test_tablet_latches_for_the_run_but_now_follows_the_socket` (remote 1 → `tablet_done` e `tablet_now`; poi 0 → `tablet_done` vero, `tablet_now` falso)
  - `test_skip_ticks_the_tablet_step`
  - `test_a_new_run_starts_clean` (live_running False poi True → `tablet_done` falso, telemetria non vista)
  - `test_resto_in_pista_returns_to_driving_view` (dopo `dismiss_finished`, fase `driving` finché la telemetria non torna o non passano altri 60 s)
  - `test_report_url_encodes_and_falls_back`: `report_url("http://127.0.0.1:8778/", "mclaren_720s_gt3_evo", "Imola")` contiene `view=pagella&car=mclaren_720s_gt3_evo&track=Imola`; con `track=None` → `"http://127.0.0.1:8778/"`; spazi e `&` codificati.
- [ ] **Step 2:** `python -m pytest tests/test_livepanel.py -q` → FAIL.
- [ ] **Step 3:** implementa (nessun import Qt in questo modulo).
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** commit `"Lo stato del pannello In pista si ricava da /health, passo per passo"`.

---

### Task 3: il report apre la Pagella che gli chiedi

**Files:**
- Modify: `src/accoach/web/app.js` (`init`, dove oggi si leggono `savedView`/`savedCombo`/`openPagellaIfNew`)
- Test: `tests/test_web_pagella.py` (aggiunte)

**Interfaces:**
- Consumes: `?view=pagella&car=…&track=…` (Task 2 `report_url`).
- Produces: con quei parametri, il report sceglie la combo `car`/`track` (confronto senza maiuscole, come `sameName`), apre la Pagella, salva la combo come ricordata, segna come vista la sessione più recente di quella combo (`hone_seen_session:<car>|<track>`), e toglie i parametri dall'indirizzo (`history.replaceState`) così un ricarica normale non li riapplica. Combo inesistente → comportamento di oggi.

- [ ] **Step 1: test statici che falliscono:** `init` legge `URLSearchParams(location.search)` con `view`, `car`, `track`; il ramo dei parametri chiama `showView("pagella")`, salva `_COMBO_KEY` e la chiave `seenKey`, e chiama `history.replaceState`; e viene prima di `savedView()`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. **Step 4:** test + `node --check src/accoach/web/app.js` → PASS.
- [ ] **Step 5:** commit `"Il report apre la Pagella dell'auto e della pista che gli indichi"`.

---

### Task 4: il pannello «In pista»

**Files:**
- Create: `src/accoach/livepanel_ui.py` (il widget)
- Modify: `src/accoach/launcher.py` (`_build_live_page`, avvio di `web`, «Ho finito»), `src/accoach/i18n.py` (testi `live.*`)
- Test: `tests/test_livepanel_ui.py`

**Interfaces:**
- Consumes: `LiveTracker`, `parse_health`, `report_url`, `POLL_S` (Task 2); `/health` (Task 1); `netinfo.device_urls`, `netinfo.qr_png`, `netinfo.port_open`; `LapCatalog.load_advice(car, track)` e `coaching.howto.defect_name(key, lang)` per «Stai seguendo»; `MainWindow._live_running`, `_stop_live_and_wait`, `_spawn`.
- Produces: `class LivePanel(QWidget)` con `__init__(self, hub: "MainWindow")`, `render_state(state: PanelState) -> None` (pubblico per i test), `retranslate() -> None`; il polling usa `QNetworkAccessManager` su `http://127.0.0.1:{cfg.server.port}/health` con timeout ~1,5 s, un `QTimer` a `POLL_S` acceso solo mentre Coach Live gira.

Comportamento (dalla spec, sezioni «Cosa è stato approvato» e «Scelte mie»):
- Coach Live spento: i bottoni di oggi (Avvia, Demo) e sotto l'anteprima dei tre passi.
- Avvio di Coach Live: se `cfg.lan` è attivo e `port_open(cfg.web.port)` è falso, l'hub avvia `["web"]` senza console.
- `before`: passi 1-3; passo 2 con QR + indirizzo (`device_urls(cfg.web.port)["engineer"]`), «Apri su questo PC» (`http://127.0.0.1:{web.port}/engineer`), «Salta, guido senza»; con `cfg.lan` spento una riga e un bottone che porta alla pagina «Dispositivi»; se il report non parte entro ~5 s, una riga che lo dice.
- `driving`: tablet (stato di adesso), pista · auto, giro e miglior tempo, «Stai seguendo: <nome difetto>» solo se c'è un consiglio `active`, il bottone grande «Ho finito, mostrami com'è andata» e, piccolo, «Ferma senza aprire il report».
- `finished`: giri salvati, «Mostrami com'è andata», «Resto in pista».
- `silent`: una riga «il coach non risponde» al posto dei dati, bottoni invariati.
- «Ho finito» / «Mostrami com'è andata»: `_stop_live_and_wait(5.0)`; se `port_open(web.port)` falso avvia `["web"]` e aspetta fino a ~5 s che la porta risponda (senza bloccare l'interfaccia: un `QTimer` che riprova); poi `webbrowser.open(report_url("http://127.0.0.1:{web.port}/", car, track))`. Senza auto/pista o con zero giri salvati, una riga che lo dice.

- [ ] **Step 1: test che falliscono** (con `QT_QPA_PLATFORM=offscreen`, `pytest.importorskip("PySide6")`, un hub finto o il `MainWindow` vero come nei test esistenti del launcher):
  - `test_each_state_renders_and_fits` — per `idle`, `before`, `driving`, `finished`, `silent`: `render_state(...)`, render in `QPixmap`, `widget.sizeHint()` ≤ dimensione della pagina dell'hub, nessuna chiave i18n grezza nei testi visibili (cerca `"live."` nel testo dei `QLabel`).
  - `test_the_qr_is_there_only_with_lan_on`
  - `test_following_line_only_with_an_active_advice` (catalogo in `tmp_path` con un consiglio `active` → la riga contiene il nome del difetto; senza → assente)
  - `test_finish_stops_coach_then_opens_the_pagella` (monkeypatch di `_stop_live_and_wait`, `port_open`→True, `webbrowser.open` registrato: chiamati in quest'ordine, URL con `view=pagella&car=…&track=…`)
  - `test_finish_without_a_combo_opens_the_plain_report`
  - `test_polling_runs_only_while_coach_live_runs` (timer attivo/fermo)
  - `test_no_http_on_the_ui_thread` — il modulo non importa `urllib`/`requests`/`http.client` (le richieste passano da QtNetwork)
  - i18n: ogni chiave `live.*` nuova ha `it` e `en` (vedi come lo verificano i test esistenti di `i18n.py`).
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** implementa. Riusa lo stile dell'hub (`_section`, `_hint`, i ruoli `good`/`bad`/`muted` del QSS). Il QR si fa come in `_qr_col` della pagina «Dispositivi» (fattorizza un helper invece di copiarlo).
- [ ] **Step 4:** → PASS; `python -m pytest tests/test_launcher*.py tests/test_hubgate.py -q` → PASS; suite intera.
- [ ] **Step 5:** salva in PNG i cinque stati nello scratchpad e allegali al report (prova visiva per il controllore).
- [ ] **Step 6:** commit `"Il pannello In pista accompagna dal via alla Pagella"`.

---

### Task 5: la procedura nella guida e nel primo avvio

**Files:**
- Modify: `src/accoach/i18n.py` (passo del wizard su Coach Live: `wiz.s2` o quello che parla di Coach Live — verificare), `GUIDA.md` (§2 «Avvio in 30 secondi» e la parte su Coach Live), `docs/FAQ.md`
- Test: suite esistente (`tests/test_guide.py`, test del wizard)

- [ ] **Step 1:** il passo del wizard su Coach Live dice che il pannello «In pista» ti guida: tablet col QR, poi ACC, e alla fine «Ho finito» apre la Pagella. Una o due frasi, tono della spec.
- [ ] **Step 2:** GUIDA.md e FAQ.md: la procedura in tre momenti (prima di partire, in pista, fine) con i nomi dei bottoni esatti come in `i18n.py`.
- [ ] **Step 3:** `python -m pytest -q` → PASS.
- [ ] **Step 4:** commit `"La guida e il primo avvio raccontano il giro di Coach Live"`.

---

### Task 6: prova vera (controllore)

- [ ] Casa finta, Coach Live in demo dal codice del ramo, hub vero: i passi si spuntano con la telemetria finta; un client websocket da un altro indirizzo (o il tablet del pilota) spunta il tablet; «Ho finito» ferma il coach e apre la Pagella giusta. Screenshot dei tre momenti. Nessuna porta lasciata aperta, nessuna scrittura in `Documents\ACCoach`.
