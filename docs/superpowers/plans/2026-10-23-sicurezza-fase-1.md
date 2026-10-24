# Sicurezza, fase 1: chiudere le porte — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una pagina web malevola nel browser del pilota, o un dispositivo sul suo Wi-Fi, non possono più leggere i suoi dati né scrivere assetti attraverso i due server di HONE.

**Architecture:** un middleware ASGI unico (`accoach/guard.py`) messo davanti alla app web (8778) e al backend live (8777): controlla l'Host, chiede una chiave a chi non è il PC stesso, e per le scritture pretende JSON dichiarato e un'Origin di casa. Sopra, si chiudono le due iniezioni di codice (guida, nomi curva) e si aggiunge una Content-Security-Policy che lascia girare solo gli script di HONE.

**Tech Stack:** Python 3.11+, FastAPI/Starlette (middleware ASGI puro), JS ES5 per il tablet (Safari 9), ES2020 per le altre pagine.

**Spec:** non c'è un documento a parte. Le decisioni stanno qui sotto (sezione «Decisioni»); le falle da chiudere sono quelle confermate dalla revisione del 23/10 (rete H1-H4, M1, M2; pagine F1-F3; distribuzione n. 4).

## Decisioni

1. **Host ammessi**: `localhost`, `127.0.0.1`, `::1`, `[::1]`, più `netinfo.local_addresses()` e `socket.gethostname()` (minuscolo). La porta nell'Host non conta. Ricalcolati al più ogni 30 s (l'IP di rete cambia col DHCP). Un Host fuori lista → **403** testo `host not allowed`. È la difesa contro il DNS rebinding.
2. **Chi è il PC**: un client è locale se il suo IP è in `local_addresses()` (dentro c'è anche l'IP di rete del PC). I client locali non portano chiavi.
3. **La chiave per il Wi-Fi**: una per installazione, **persistente** (un segnalibro sul tablet deve reggere un riavvio), 32 caratteri da `secrets.token_urlsafe(24)`, nel file `paths.base_dir() / "lan-key.txt"`, creato al primo uso in modo atomico. Un client non locale passa se porta la chiave in uno di questi: cookie `hone_key`, parametro `?k=`, header `X-HONE-Key`. Altrimenti **401** con una pagina breve: «Apri HONE dal codice QR dell'hub.» / «Open HONE from the hub's QR code.». Un GET con `?k=` giusto imposta il cookie `hone_key` (`Path=/; Max-Age=31536000; SameSite=Lax`, **non** HttpOnly: le pagine lo leggono per parlare con la 8777, dove il cookie della 8778 non viaggia con le richieste cross-origin).
4. **Scritture** (metodo diverso da GET, HEAD, OPTIONS), da chiunque: `Content-Type` deve cominciare con `application/json` (**415** altrimenti) e, se c'è l'header `Origin`, il suo host deve essere fra quelli ammessi e la porta quella delle pagine (8778, `cfg.web.port`) (**403** altrimenti). Un `fetch(..., {mode:"no-cors", body: Blob})` o un form da un altro sito cadono qui.
5. **WebSocket** (`/ws` della 8777): Host come sopra; `Origin`, se c'è, come al punto 4; un client non locale porta la chiave (in pratica `?k=`). I client Python (overlay, hub) non mandano Origin e sono locali: passano.
6. **OPTIONS** (preflight): solo il controllo dell'Host. Il browser non manda credenziali nel preflight.
7. **CORS della 8777**: niente più `*`. `allow_origin_regex` per `http://<qualsiasi>:<porta pagine>`; l'host lo filtra il guardiano (punto 1 e 4). `allow_headers` = `Content-Type`, `X-HONE-Key`.
8. **CSP** sulle pagine HTML servite dalla 8778 (`/`, `/engineer`, `/tablet`, `/test`, `/guida`):
   `default-src 'self'; script-src 'self' 'nonce-<N>' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws://<host>:<live> http://<host>:<live>; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`
   con `<host>` l'hostname dell'Host della richiesta e `<live>` la porta live (`cfg.server.port`). `'unsafe-inline'` accanto al nonce è voluto: i browser CSP2 lo ignorano quando c'è un nonce, Safari 9 (CSP1) no e senza resterebbe senza script inline. Su tutte le risposte della 8778: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`.
9. **Niente `new Function`**: la prova «questo browser regge la pagina completa?» diventa uno script esterno `web/modern.js` con `async function` e `??` che imposta `window.HONE_MODERN = true`; su un browser vecchio non si analizza e la bandierina resta assente.
10. **Nomi curva e riferimenti di frenata**: il server rifiuta `< > & " '` con **400** (`detail` in lingua: «Il nome non può contenere < > & " '.»). Le pagine li mostrano comunque come testo.

## Global Constraints

- Il tablet è un iPad 3 con **iOS 9.3.6 / Safari 9**: `tablet.html`/`tablet.js` restano ES5 (template string ammesse), niente `fetch`, niente `.forEach` in `tablet.js`; il controllo è `tests/safari9.py`.
- I test non toccano mai `%USERPROFILE%\Documents\ACCoach`: `tests/conftest.py` isola già config e log; il file della chiave va isolato allo stesso modo (Task 1).
- Mai importare o chiamare `accoach.config` contro la casa vera fuori dai test isolati.
- Commenti in italiano, che dicono il perché; commit in italiano che finiscono con `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Testi per il pilota: frasi brevi col «tu», virgola decimale, niente slogan, niente due punti a effetto, niente emoji; vale `tests/test_tono.py`.
- Suite intera (`python -m pytest -q -p no:cacheprovider`) verde prima di ogni commit.

## Review Focus

1. **Il tablet sul Wi-Fi dopo il QR**: apre `/tablet?k=…`, poi passa a `/engineer` con un link senza `k`. Deve funzionare grazie al cookie, e le chiamate alla 8777 (WebSocket, `/engineer/applied`) devono portare la chiave. Test nel Task 2.
2. **Il PC che apre la pagina col proprio IP di rete** (`http://192.168.x.y:8778`): è un client locale, nessuna chiave, Host ammesso. Test nel Task 1.
3. **I client Python** (overlay su `ws://127.0.0.1:8777/ws`, pannello dell'hub su `/health`): niente Origin, niente chiave, devono continuare a funzionare. Test nel Task 1.
4. **I nomi già salvati** in `corner-names.json` con caratteri ora vietati: non devono far cadere il report; si mostrano come testo. Test nel Task 3.
5. **Le pagine sotto CSP**: nessuno script inline senza nonce, nessun `onclick=` nell'HTML, nessun `new Function` rimasto. Un test cerca questi tre nei file serviti (Task 4).

---

### Task 1: il guardiano

**Files:**
- Create: `src/accoach/guard.py`
- Modify: `src/accoach/api.py` (`create_api`, ~riga 907), `src/accoach/server.py` (`create_app`, CORS a riga ~176), `tests/conftest.py`
- Test: `tests/test_guard.py`

**Interfaces:**
- Produces:
  - `guard.key_path() -> Path` (= `paths.base_dir() / "lan-key.txt"`), `guard.lan_key() -> str` (lo crea se manca).
  - `guard.allowed_hosts() -> frozenset[str]`, `guard.is_local_client(ip: str | None) -> bool`.
  - `class GuardMiddleware` ASGI puro: `GuardMiddleware(app, *, page_port: int)`; copre gli scope `http` e `websocket`.
  - `guard.COOKIE = "hone_key"`, `guard.HEADER = "x-hone-key"`, `guard.QUERY = "k"`.

- [ ] **Step 1: isolare la chiave nei test.** In `tests/conftest.py` una fixture autouse che punta `guard.key_path` a un file in una cartella temporanea, e che fa ammettere l'Host `testserver` e il client `testclient` di `TestClient` (monkeypatch di `guard.allowed_hosts` e `guard.is_local_client` che delegano alla funzione vera e aggiungono quei due nomi). I test del guardiano usano `TestClient(app, base_url=..., client=(ip, porta))` per simulare gli altri casi.
- [ ] **Step 2: scrivere `tests/test_guard.py`, che fallisce.** Una app FastAPI minima con `GET /x`, `POST /w` (JSON), `websocket /ws` e il middleware, più gli stessi casi contro `create_api(...)` e `server.create_app(...)` veri. Casi, con lo stato atteso:
  - Host `evil.example` → 403, su GET, POST e WebSocket, su tutte e due le app.
  - client `192.168.1.50` senza chiave → 401, con il testo del QR nella lingua; con `?k=<chiave>` → 200 e `set-cookie` con `hone_key=<chiave>` e `SameSite=Lax`; poi col solo cookie → 200; con `X-HONE-Key` → 200; con una chiave sbagliata → 401.
  - client uguale all'IP di rete del PC (monkeypatch di `netinfo.lan_ip` a `192.168.1.23`, Host `192.168.1.23:8778`) senza chiave → 200.
  - POST senza `Content-Type` → 415; con `text/plain` → 415; con `application/json` → 200; con `Origin: http://evil.example` → 403; con `Origin: http://127.0.0.1:8778` → 200; con `Origin: http://127.0.0.1:9999` → 403.
  - OPTIONS da un client non locale senza chiave, Host ammesso → non 401.
  - WebSocket con `Origin: http://evil.example` → rifiutato; senza Origin da client locale → accettato.
  - la 8777 vera: `POST /engineer/applied` da `Origin: http://evil.example` → 403 e `mark_setup_applied` non chiamato; la risposta a un preflight da `http://127.0.0.1:8778` porta `access-control-allow-origin: http://127.0.0.1:8778`, non `*`.
  - `lan_key()` due volte → stesso valore, lungo 32; il file sta dove dice `key_path()`.
- [ ] **Step 3: verificare che fallisca.** `python -m pytest -q -p no:cacheprovider tests/test_guard.py` → errori di import di `accoach.guard`.
- [ ] **Step 4: scrivere `guard.py`** secondo le Decisioni 1-7. Il confronto della chiave con `hmac.compare_digest`. La risposta 401 è HTML minimo con la frase del punto 3, nella lingua di `i18n.current_language()`. Aggiungere `GuardMiddleware(page_port=cfg.web.port)` come middleware più esterno in `create_api` e in `create_app` (in `create_app` dopo il CORS, così il guardiano lo avvolge); sostituire il CORS `*` della 8777 come al punto 7. Le porte arrivano da `load_config()` già letto in quelle funzioni, o dal parametro esistente.
- [ ] **Step 5: suite intera verde.** Se dei test esistenti mandano POST senza JSON (per esempio `content=` senza header), correggere il test, non il guardiano.
- [ ] **Step 6: commit** «Guardiano dei server: Host, chiave per il Wi-Fi, scritture solo JSON da casa».

### Task 2: le pagine e il QR portano la chiave

**Files:**
- Create: `src/accoach/web/lankey.js` (ES3)
- Modify: `src/accoach/web/engineer.html`, `tablet.html`, `test.html` (includere `lankey.js` prima degli script di pagina), `engineer.js` (righe ~878, ~1380, ~1528, ~1557), `tablet.js` (righe ~382, ~794), `test.js` (~239), `src/accoach/netinfo.py` (`device_urls`), `src/accoach/launcher.py` (chi chiama `device_urls`), `GUIDA.md`, `docs/FAQ.md` (la parte sul tablet e sul Wi-Fi)
- Test: `tests/test_guard_pagine.py`

**Interfaces:**
- Consumes: `guard.lan_key()`, `guard.COOKIE`, `guard.QUERY` (Task 1).
- Produces: `window.honeLive(url: string) -> string` in `lankey.js`: se il cookie `hone_key` c'è, aggiunge `k=<chiave>` (con `?` o `&`) all'URL e lo restituisce; altrimenti lo restituisce uguale. `netinfo.device_urls(port, ip=None, key=None)`: con `key`, ogni URL finisce con `?k=<key>`.

- [ ] **Step 1: test che falliscono** in `tests/test_guard_pagine.py`:
  - `device_urls(8778, ip="192.168.1.23", key="abc")["tablet"] == "http://192.168.1.23:8778/tablet?k=abc"`, e così per le altre tre; senza `key` gli URL restano quelli di oggi.
  - il launcher costruisce i QR con `key=guard.lan_key()` (test sul punto in cui chiama `device_urls`, leggendo il sorgente o con un monkeypatch, come fanno i test del launcher esistenti).
  - ogni URL verso la porta live in `engineer.js`, `tablet.js`, `test.js` passa da `honeLive(` (test che legge i file e cerca ogni `WS_PORT`/`LIVE_PORT` usato in un URL).
  - ogni `POST` verso `/engineer/applied` manda `Content-Type: application/json` e un corpo `{}`.
  - `lankey.js`, `tablet.js` passano `tests/safari9.py`.
  - con `TestClient(client=("192.168.1.50", 1))`: `GET /tablet?k=<chiave>` e poi `GET /engineer` col solo cookie → 200 tutti e due (Review Focus 1).
- [ ] **Step 2: verificare che falliscano.**
- [ ] **Step 3: implementare.** `lankey.js` legge `document.cookie` (niente regex con lookbehind: Safari 9). Nelle guide, una frase dove si spiega il QR: il link del QR porta una chiave, e chi non ce l'ha sul Wi-Fi non entra; se il tablet dice «Apri HONE dal codice QR dell'hub.», lo si inquadra di nuovo.
- [ ] **Step 4: suite intera verde.**
- [ ] **Step 5: commit** «Il QR e le pagine portano la chiave del Wi-Fi».

### Task 3: le due iniezioni di codice

**Files:**
- Modify: `src/accoach/guide.py` (`render_page` ~415, `_PAGE` ~292, link Markdown ~95), `src/accoach/cornernames.py` (`put` ~202, `put_mark` ~213), `src/accoach/api.py` (le rotte che li chiamano, ~947-1001: trasformare l'errore in 400 con `detail` tradotto), `src/accoach/web/app.js`, `src/accoach/web/engineer.js`, `src/accoach/i18n.py` (la frase del rifiuto)
- Test: `tests/test_xss.py`

**Interfaces:**
- Produces: `cornernames.FORBIDDEN = set('<>&"\'')`; `put`/`put_mark` sollevano `ValueError` se il testo ne contiene uno. In `app.js` ed `engineer.js` una `esc(s)` che sostituisce `& < > " '` (in `app.js` può prendere il posto di `escAttr`, aggiungendo `'`).

- [ ] **Step 1: test che falliscono** in `tests/test_xss.py`:
  - `GET /guida?lang="><script>alert(1)</script>` → 200 e `<script>alert(1)` non è nel corpo; `lang=xx` → la pagina esce con `lang="it"` (o la lingua predefinita).
  - `render_markdown("[x](javascript:alert(1))")` non contiene `href="javascript:`; `[x](https://a.b)`, `[x](#s)` e `[x](FAQ.md)` restano link.
  - `POST /api/corner-name` con nome `<img src=x onerror=alert(1)>` → 400 e niente scritto; con `Curva "Villeneuve"` → 400; con `Tamburello` → 200. Lo stesso per il riferimento di frenata.
  - un `corner-names.json` già sporco (scritto a mano nel test) non fa fallire `/api/analysis` (Review Focus 4).
  - test sul sorgente: nei punti elencati dalla revisione (`app.js` 551, 740, 779, 800, 1363, 1374, 1950, 1965, 1996, 2041, 2067-2069, 2134, 4421, 4510, 4757, 5547, 5586; `engineer.js` 757, 1465, 1489) ogni nome, `where`, `message`, `label`, `theme` o errore che entra in un template destinato a `innerHTML` passa da `esc(`. Il test cerca gli interpolati `${…name}`, `${…where}`, `${…message}`, `${…label}`, `${…theme}` dentro stringhe che finiscono in `innerHTML` e pretende `esc(` attorno; i numeri formattati (`fmt…`) restano fuori.
- [ ] **Step 2: verificare che falliscano.**
- [ ] **Step 3: implementare.** In `render_page` la lingua fuori da `i18n.LANGUAGES` diventa `i18n.DEFAULT_LANGUAGE`, e ogni valore che entra in `_PAGE.format` è escapato tranne quelli già HTML (`body`, `toc`, `header`, `css`). I link Markdown ammessi: `http:`, `https:`, `mailto:`, `#…`, relativi senza schema; gli altri diventano testo. Nel JS, `esc()` ovunque c'è un dato; dove l'HTML serve davvero (un `<b>` attorno), si escapa il dato e non il contorno.
- [ ] **Step 4: suite intera verde; `tests/test_tono.py` sulla frase nuova.**
- [ ] **Step 5: commit** «Guida e nomi curva: niente più codice che entra nelle pagine».

### Task 4: CSP e l'elenco degli assetti

**Files:**
- Create: `src/accoach/web/modern.js`, `src/accoach/web/modern-gate.js`
- Modify: `src/accoach/api.py` (`_serve` ~2395, `guide_page` ~2472), `src/accoach/guide.py` (lo script inline del sommario ~309 prende il nonce), `src/accoach/guard.py` (helper `csp(host_header: str, nonce: str, live_port: int) -> str`), `src/accoach/web/engineer.html` (righe 8-15), `tablet.html`, `tablet.js` (`fullPageWorks` ~73), `test.html` (riga 69), `test.js`, `src/accoach/setup/web_api.py` (`setup_list` ~274)
- Test: `tests/test_csp.py`

**Interfaces:**
- Consumes: `GuardMiddleware` (Task 1) per `nosniff` e `X-Frame-Options` su tutte le risposte della 8778.
- Produces: `guard.csp(...)` come al punto 8; `window.HONE_MODERN` da `modern.js`.

- [ ] **Step 1: test che falliscono** in `tests/test_csp.py`:
  - `GET /`, `/engineer`, `/tablet`, `/test`, `/guida` → header `content-security-policy` con `script-src 'self' 'nonce-` e `object-src 'none'` e `frame-ancestors 'none'`; ogni `<script>` inline nel corpo ha `nonce="<lo stesso del header>"`; il nonce cambia fra due richieste; `connect-src` contiene `ws://<host della richiesta>:<porta live>`.
  - tutte le risposte della 8778 (anche un JSON) hanno `x-content-type-options: nosniff`.
  - nessun file in `src/accoach/web/` contiene `new Function`, e nessun `.html` contiene attributi `on…=` (Review Focus 5).
  - `engineer.html` carica `/static/modern.js` e poi `/static/modern-gate.js`, che fa `location.replace("/tablet")` se `window.HONE_MODERN` manca; `tablet.js` `fullPageWorks` legge `window.HONE_MODERN`; `tablet.html` carica `modern.js`. `modern-gate.js` e `tablet.js` passano `tests/safari9.py`.
  - `GET /api/setup/list?car=..&track=x`, `car=C:/x`, `track=a/b`, `track=a\b`, `track=.` → 400; un `car`/`track` normale → come oggi.
- [ ] **Step 2: verificare che falliscano.**
- [ ] **Step 3: implementare.** Il nonce: `secrets.token_urlsafe(16)` per risposta, scritto nell'header e negli script inline che `_serve` e la guida generano. Il test dell'ES moderno di oggi confronta lo stesso testo fra `engineer.html` e `tablet.js`: va aggiornato perché ora la prova è `modern.js`. La chiusura del glossario in `test.html` passa a un `addEventListener` in `test.js`.
- [ ] **Step 4: suite intera verde.**
- [ ] **Step 5: commit** «CSP sulle pagine e l'elenco degli assetti resta nelle cartelle del gioco».
