"use strict";
// La vista tablet: la parte della pagina Ingegnere che serve in macchina, su
// un iPad 3 con Safari 9. Per questo e' ES5: niente let/const, funzioni
// freccia, fetch, e nessun `.forEach` (su Safari 9 la NodeList non ce l'ha, e
// qui non si rischia: solo cicli `for`). Il controllo sta in tests/safari9.py.
//
// Lo stato si legge a ogni frame dal vivo (`mode`): spento, in pista, avviso
// di rientro, fermo ai box. Le regole sono quelle che il motore e la pagina
// completa usano gia'; qui non se ne inventano. Acceso, si vede una delle due
// linguette, Telemetria o Assetto (`pickTab`): la sceglie lo stato ai box, e
// il pilota col dito.
(function () {
  var WS_PORT = 8777;            // il motore dal vivo; la pagina sta sulla 8778
  // Ogni URL verso il motore passa da qui: sul Wi-Fi porta la chiave del QR
  // (lankey.js). Il cookie varrebbe anche sulla 8777 (i cookie non guardano
  // la porta), ma un XHR cross-origin senza credenziali non lo manda.
  function liveUrl(u) { return window.honeLive ? window.honeLive(u) : u; }

  function t(k) { return window.HoneI18n ? window.HoneI18n.t(k) : k; }
  // Il `tf` di engineer.js, senza le forme plurali che qui non servono.
  function tf(k, vals) {
    var s = t(k);
    for (var n in vals) {
      if (Object.prototype.hasOwnProperty.call(vals, n)) s = s.split("{" + n + "}").join(vals[n]);
    }
    return s;
  }
  function fmtN(v, d, unit) {
    if (window.HoneI18n) return window.HoneI18n.fmtNum(v, d, unit);
    return v.toFixed(d) + (unit ? " " + unit : "");
  }
  function $(id) { return document.getElementById(id); }
  function num(v) { return v != null && v !== "" && isFinite(Number(v)); }

  // ---- lo stato della schermata -------------------------------------------
  // `at_box` lo calcola il motore (la regola del briefing ai box, che su ACC
  // vede anche l'auto ferma nella piazzola): la pagina non la ricalcola.
  // L'avviso di rientro e' la stessa condizione per cui la pagina completa
  // accende «Prepara la modifica»: una proposta o un ripristino ai box, con
  // le leve, non ancora scritto.
  function boxChange(eng) {
    return !!(eng && eng.tag === "BOX" && eng.change && eng.change.length && !eng.applied
              && (eng.kind === "propose" || eng.kind === "reverted"));
  }

  function mode(st) {
    if (!st || !st.connected) return "off";
    if (st.at_box) return "box";
    return boxChange(st.engineer) ? "call" : "track";
  }

  // La linguetta: Telemetria («track») o Assetto («setup»). Il cambio e'
  // automatico solo quando cambia lo stato ai box: fermo ai box apre Assetto,
  // ripartire torna a Telemetria. Un tocco del pilota vale fino al prossimo di
  // questi cambi, cosi' il frame dopo (15 al secondo) non gli toglie la
  // schermata, e la vista non resta su Assetto quando riparte.
  // `prev` = {tab, atBox} del frame prima, `manual` = la linguetta toccata in
  // questo giro o null.
  function pickTab(prev, st, manual) {
    var atBox = !!(st && st.at_box);
    if (manual === "track" || manual === "setup") return manual;
    if (!prev || atBox !== !!prev.atBox) return atBox ? "setup" : "track";
    return prev.tab;
  }

  // Spento ha due facce. Senza frame (il socket chiuso, o mai aperto) il
  // motore non c'e'; con un frame `connected: false` il motore c'e' ma il gioco
  // no: e' chiuso, o non e' ancora partito (il reader e' connesso appena esiste
  // la memoria condivisa del gioco, menu compresi). Dire «il coach
  // non e' acceso» al pilota che ce l'ha acceso lo manda a cercare il guasto
  // sbagliato.
  function offKey(st) { return st ? "tablet.waiting" : "tablet.off"; }

  // La stessa prova di engineer.html: la bandierina di modern.js, che si
  // alza solo dove `async` e `??` si leggono. Dove non c'e' la pagina
  // completa non parte e rimanda qui, e un link che ci porta farebbe solo un
  // giro a vuoto. Prima compilava una stringa, e la CSP non lo lascia passare.
  function fullPageWorks() {
    return window.HONE_MODERN === true;
  }

  // ---- gomme ----------------------------------------------------------------
  // Le finestre di engineer.js (slick GT3 generiche), stessi colori.
  var TYRES = ["t-fl", "t-fr", "t-rl", "t-rr"];
  function tempClass(v) {
    if (!num(v)) return "";
    return v < 80 ? "cold" : (v <= 100 ? "ok" : "hot");
  }
  function psiClass(v) {
    if (!num(v)) return "";
    return v < 26.5 ? "low" : (v <= 28.5 ? "ok" : "high");
  }
  function renderTyres(tyres) {
    var temps = (tyres && tyres.temp) || [], press = (tyres && tyres.pressure) || [];
    for (var i = 0; i < TYRES.length; i++) {
      var tv = temps[i], pv = press[i];
      var te = $(TYRES[i] + "-t"), pe = $(TYRES[i] + "-p");
      te.textContent = num(tv) ? fmtN(Math.round(tv), 0, "°C") : "–";
      pe.textContent = num(pv) ? fmtN(Number(pv), 1, "psi") : "–";
      te.className = "tt " + tempClass(tv);
      pe.className = "tp " + psiClass(pv);
    }
  }

  function aid(v) { return v == null || v < 0 ? "–" : String(v); }

  // ---- pedali e sterzo ------------------------------------------------------
  // tracePush/traceDraw di engineer.js, in ES5 e coi colori scritti per esteso
  // (Safari 9 non ha le variabili CSS da cui la pagina completa li legge).
  var TRACE_WINDOW_MS = 8000;
  var TRACE_STEER_FLOOR = 0.3;
  var trace = { hist: [], steerScale: TRACE_STEER_FLOOR };
  function now() {
    return (window.performance && performance.now) ? performance.now() : Date.now();
  }

  function traceReset() {
    trace.hist = [];
    trace.steerScale = TRACE_STEER_FLOOR;
    var ids = ["tr-thr", "tr-brk", "tr-steer"];
    for (var i = 0; i < ids.length; i++) $(ids[i]).textContent = "–";
    traceDraw();
  }

  function pct(f) { return fmtN(Math.round(f * 100), 0, "%"); }

  function tracePush(st) {
    var thr = Number(st.throttle), brk = Number(st.brake);
    if (st.throttle == null || st.brake == null || !isFinite(thr) || !isFinite(brk)) return;
    var steer = isFinite(Number(st.steer)) ? Number(st.steer) : 0;
    var t0 = now();
    trace.hist.push([t0, thr, brk, steer]);
    trace.steerScale = Math.max(trace.steerScale, Math.abs(steer));
    var cutoff = t0 - TRACE_WINDOW_MS, drop = 0;
    while (drop < trace.hist.length && trace.hist[drop][0] < cutoff) drop++;
    if (drop) trace.hist.splice(0, drop);
    $("tr-thr").textContent = pct(thr);
    $("tr-brk").textContent = pct(brk);
    // Positivo a sinistra (serialize.py). Quasi dritto: solo il numero.
    var v = pct(Math.abs(steer));
    $("tr-steer").textContent = steer > 0.02 ? tf("trace.steerLeft", { v: v })
                              : (steer < -0.02 ? tf("trace.steerRight", { v: v }) : v);
    traceDraw(t0);
  }

  function traceDraw(t1) {
    var cv = $("t-trace");
    // Nascosta (su Assetto): la storia intanto si aggiorna.
    if (!cv || !cv.offsetWidth) return;
    var dpr = window.devicePixelRatio || 1;
    var w = cv.offsetWidth, h = cv.offsetHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    }
    var ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    var pad = 4, ph = h - 2 * pad;
    function y(v) { return pad + ph * (1 - Math.max(0, Math.min(1, v))); }
    // griglia 0 / 50 / 100 %; la riga di mezzo e' anche lo sterzo dritto
    ctx.strokeStyle = "#232B35";
    ctx.lineWidth = 1;
    var grid = [0, 0.5, 1];
    for (var g = 0; g < grid.length; g++) {
      var gy = Math.round(y(grid[g])) + 0.5;
      ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
    }
    var hist = trace.hist;
    if (hist.length < 2) return;
    var end = t1 == null ? now() : t1;
    var k = 0.5 / trace.steerScale;
    function x(ts) { return w * (1 - (end - ts) / TRACE_WINDOW_MS); }
    function draw(pick, colour, width) {
      ctx.strokeStyle = colour; ctx.lineWidth = width;
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.beginPath();
      for (var i = 0; i < hist.length; i++) {
        var px = x(hist[i][0]), py = y(pick(hist[i]));
        if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
      }
      ctx.stroke();
    }
    // lo sterzo per primo, cosi' i pedali gli restano sopra
    draw(function (s) { return 0.5 + s[3] * k; }, "#E8EDF2", 1.5);
    draw(function (s) { return s[2]; }, "#FF4D5E", 2.5);
    draw(function (s) { return s[1]; }, "#34E08A", 2.5);
  }

  // ---- l'ingegnere ----------------------------------------------------------
  // La riga della fase, come `renderEngineer`: cosa fare in questa fase, che
  // il messaggio di decisione da solo non dice.
  function renderPhase(eng) {
    var el = $("t-phase");
    if (eng && eng.phase && eng.phase.key) {
      var k = "eng.do." + eng.phase.key;
      var txt = t(k);
      if (txt === k) txt = t("eng.do.default");   // t() rende la chiave se manca
      el.innerHTML = "";
      var b = document.createElement("b");
      b.textContent = tf("eng.phaseNow", { label: eng.phase.label || "" });
      el.appendChild(b);
      el.appendChild(document.createTextNode(" " + txt));
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  }

  // ---- la strada dell'ingegnere --------------------------------------------
  // Le tappe e la frase del passo, da `engineer.progress` (lo calcola il
  // motore, `RaceEngineer.progress`): qui non si indovina niente dai testi.
  // La gemella e' `stripText` di engineer.js, con le stesse chiavi e le stesse
  // regole (un test le confronta caso per caso). Senza un `progress` che si
  // legge la striscia non c'e': null, e la pagina la nasconde.
  // `changeTag` e' il `tag` della modifica in attesa (`engineer.tag`), non
  // quello della fase: una fase «dal volante» propone anche leve da box, e il
  // ricontrollo delle pressioni propone ai box in qualunque fase.
  // `kind` e' quello dell'ultima decisione (`engineer.kind`).
  function stripText(p, changeTag, kind) {
    if (!p || typeof p !== "object" || !Array.isArray(p.phases) || !p.phases.length) return null;
    var idx = Number(p.index), done = p.stage === "done";
    // Le fasi che il motore ha passato senza chiuderle (cieche, o senza niente
    // da correggere): dietro di noi, ma senza la spunta di una fase fatta.
    var skipped = Array.isArray(p.skipped) ? p.skipped : [];
    var steps = [];
    for (var i = 0; i < p.phases.length; i++) {
      var ph = p.phases[i] || {};
      // Finito, nessuna tappa resta accesa: l'indice e' oltre l'ultima.
      var past = done || i < idx;
      steps.push({ label: String(ph.label || ph.key || ""),
                   state: past ? (skipped.indexOf(i) !== -1 ? "skipped" : "done")
                               : (i === idx ? "now" : "next") });
    }
    // Il contatore solo dove il motore conta giri verso una soglia; senza i
    // suoi numeri la frase non se ne inventa uno.
    var counted = num(p.have) && num(p.need);
    var line = "", why = "";
    if (kind === "stand_down") {
      // Il motore si e' tirato indietro (bagnato, fase cieca, leva che non sa
      // scrivere): «giri puliti per la base» o «decido a fine giro» qui
      // sarebbero falsi. Il perche' lo dice il suo messaggio.
      line = t("eng.road.standDown");
    } else if (p.stage === "baseline" || p.stage === "test") {
      if (counted) {
        line = tf(p.stage === "test" ? "eng.road.test" : "eng.road.base",
                  { have: p.have, need: p.need });
        why = t("eng.road.why");
      }
    } else if (p.stage === "change") {
      line = t(changeTag === "AV" ? "eng.road.changeAv"
               : (changeTag === "BOX" ? "eng.road.changeBox" : "eng.road.change"));
    } else if (p.stage === "restore") {
      line = t("eng.road.restore");
    } else if (p.stage === "diagnose") {
      line = t("eng.road.diagnose");
    } else if (done) {
      line = t("eng.road.done");
    }
    return { steps: steps, line: line, why: why };
  }

  // La striscia si riscrive solo quando cambia: il frame arriva 15 volte al
  // secondo e quasi sempre dice la stessa cosa.
  var roadKey = null;
  function renderRoad(eng) {
    var s = stripText(eng && eng.progress, eng && eng.tag, eng && eng.kind);
    var key = s ? JSON.stringify(s) : "";
    if (key === roadKey) return;
    roadKey = key;
    var box = $("t-road");
    if (!s) { box.hidden = true; return; }
    var ol = $("t-road-steps");
    ol.innerHTML = "";
    for (var i = 0; i < s.steps.length; i++) {
      var li = document.createElement("li");
      li.className = "t-road-step " + s.steps[i].state;
      var b = document.createElement("span");
      b.className = "t-road-name";
      b.textContent = s.steps[i].label;
      li.appendChild(b);
      ol.appendChild(li);
    }
    $("t-road-line").textContent = s.line;
    $("t-road-why").textContent = s.why;
    $("t-road-why").hidden = !s.why;
    box.hidden = false;
  }

  // Il messaggio del motore quando non c'e' una modifica in mano. Su raccolta
  // e prova la strada dice gia' i giri contati: del messaggio resta solo la
  // coda (`engineer.tail`: perche' l'ultimo giro non conta, il sospetto sulle
  // uscite), se no lo stesso numero si leggeva due volte con due frasi. Senza
  // `tail` il messaggio si legge intero. Gemella di `msgText` in engineer.js.
  function msgText(eng) {
    if (!eng || !eng.message) return "";
    var p = eng.progress;
    var counted = !!(p && (p.stage === "baseline" || p.stage === "test")
                     && num(p.have) && num(p.need));
    if (counted && eng.kind !== "stand_down" && typeof eng.tail === "string") {
      return eng.tail.trim();
    }
    return String(eng.message);
  }

  // Quale proposta e': il tocco su «Fatto» vale per questa e non per la
  // prossima.
  function avKey(eng) {
    return eng ? String(eng.kind) + "|" + JSON.stringify(eng.change || null) : "";
  }
  // Il bottone resta nascosto dopo il tocco finche' il motore non segna la
  // modifica come fatta: i frame arrivano a 15 Hz, e un bottone che ricompare
  // subito chiede un secondo tocco. Una proposta diversa lo rimette.
  function avDoneHidden(eng, tapped) {
    return !!eng.watched || !!eng.applied || (tapped != null && tapped === avKey(eng));
  }
  var avTapped = null;          // avKey della proposta su cui hai toccato «Fatto»

  // La proposta al volo resta in pista, col suo «Fatto» dove la pagina
  // completa lo mostra: solo dove il gioco non pubblica la manopola (AC), se
  // no il motore la vede girare e chiude da solo.
  function renderAv(eng) {
    var box = $("t-av");
    if (eng && eng.tag === "AV" && eng.change) {
      if (avTapped !== null && avTapped !== avKey(eng)) avTapped = null;
      box.hidden = false;
      $("t-av-msg").textContent = eng.rationale || eng.message || "";
      $("t-av-done").hidden = avDoneHidden(eng, avTapped);
      $("t-av-done").setAttribute("data-key", avKey(eng));
    } else {
      avTapped = null;
      box.hidden = true;
    }
  }

  // Il testo dell'avviso: un ripristino non e' una modifica nuova.
  function callKey(eng) {
    return eng && eng.kind === "reverted" ? "tablet.callRestore" : "tablet.call";
  }

  function renderCall(eng, m) {
    if (m !== "call") return;
    var restore = eng.kind === "reverted";
    $("t-call-msg").textContent = t(callKey(eng));
    $("t-call-why").textContent = restore ? (eng.message || eng.rationale || "")
                                          : (eng.rationale || eng.message || "");
  }

  // ---- richieste ------------------------------------------------------------
  // Senza fetch su Safari 9: XMLHttpRequest, con `cb(err, dati)`. Come `api`
  // di engineer.js, alle /api/ si passa la lingua, cosi' etichette e riga del
  // garage arrivano tradotte; e l'errore porta il `detail` di FastAPI, perche'
  // il 409 «already exists» si riconosce da li'.
  function lang() { return window.HoneI18n ? window.HoneI18n.lang : "en"; }
  function xhr(method, url, body, cb) {
    if (url.indexOf("/api/") === 0) {
      url += (url.indexOf("?") === -1 ? "?" : "&") + "lang=" + encodeURIComponent(lang());
    }
    function done(err, data) {
      if (!cb) return;
      try { cb(err, data); } catch (e) { logOnce(e); }
    }
    try {
      var r = new XMLHttpRequest();
      r.open(method, url);
      if (body != null) r.setRequestHeader("Content-Type", "application/json");
      r.onreadystatechange = function () {
        if (r.readyState !== 4) return;
        var data = null;
        try { data = JSON.parse(r.responseText); } catch (e) {}
        if (r.status >= 200 && r.status < 300) { done(null, data); return; }
        // Un 401 e' il guardiano che non trova la chiave: la sua pagina e'
        // HTML, e senza questa riga il pilota leggeva «Unauthorized».
        var detail = r.status === 401 ? t("lan.fromQr")
                   : data && data.detail != null ? data.detail
                   : (r.statusText || "HTTP " + r.status);
        if (typeof detail !== "string") detail = JSON.stringify(detail);
        done({ status: r.status, detail: detail }, data);
      };
      r.send(body == null ? null : JSON.stringify(body));
    } catch (e) {
      done({ status: 0, detail: String((e && e.message) || e) }, null);
    }
  }

  // Lo stesso endpoint di `afterWrite` e di `av-done` della pagina completa:
  // quello che l'ingegnere aveva chiesto e' sulla macchina. Best-effort: a
  // motore spento l'ingegnere continua a proporre.
  // Motore spento resta silenzio, come prima. Un 401 no: il motore non ha
  // saputo della modifica e riproporra' la stessa, quindi lo si dice dove il
  // pilota guarda gli errori dei box.
  function appliedRefused(err) {
    if (err && err.status === 401) { bx.err = err.detail; paintBox(); }
  }
  function postApplied() {
    // Il corpo `{}` fa dichiarare JSON a `xhr`: senza, il guardiano dice 415.
    xhr("POST", liveUrl("http://" + location.hostname + ":" + WS_PORT + "/engineer/applied"), {}, appliedRefused);
  }

  // ---- la schermata dei box -------------------------------------------------
  // Il nome della via corta di engineer.js (`nextAutoName`): HONE_1, HONE_2…,
  // uno piu' del piu' alto gia' nella cartella. Ai box non si digita un nome.
  function nextName(names) {
    var max = 0;
    for (var i = 0; i < names.length; i++) {
      var m = /^HONE_(\d+)$/i.exec(String(names[i]).trim());
      if (m) max = Math.max(max, parseInt(m[1], 10));
    }
    return "HONE_" + (max + 1);
  }

  // Le leve come le vuole /api/setup/*. Uno `slot` nullo e' una leva sola per
  // tutta la macchina: la prima, come in `prepareChange`.
  function changesFor(eng) {
    var out = [], ch = (eng && eng.change) || [];
    for (var i = 0; i < ch.length; i++) {
      out.push({ param: ch[i].param, slot: ch[i].slot == null ? 0 : ch[i].slot,
                 delta_clicks: ch[i].delta_clicks });
    }
    return out;
  }

  // Quello che la schermata dei box sa oltre al frame. Base e anteprima si
  // chiedono solo quando cambia quello da cui dipendono, mai a ogni frame; i
  // numeri di sequenza scartano una risposta arrivata dopo una piu' nuova
  // (le leve di un file sotto il nome di un altro).
  var bx = {
    car: "", track: "", combo: null,
    baseSeq: 0, base: null, baseErr: "",
    chosen: null,         // il file scelto dalla tendina; null = quello del server
    pvKey: null, pvSeq: 0, pvChanges: null, preview: null, pvErr: "",
    confirm: null,        // {key, path, name, changes, av}: cio' che la conferma nomina
    writing: false,
    done: null,           // {name, hint, key} dopo una scrittura, fino a che riparti
    err: "",
    restoredKey: null     // avKey del ripristino su cui hai toccato «L'ho gia' rimesso»
  };
  // La schermata Assetto lavora (chiede base e anteprima, si dipinge) quando
  // la linguetta e' Assetto, o quando sei fermo ai box anche su Telemetria:
  // tornando su Assetto la modifica e' gia' pronta.
  var bxOn = false;
  var wasAtBox = false;

  function setText(el, s) { if (el.textContent !== s) el.textContent = s; }
  function setHidden(el, h) { if (el.hidden !== h) el.hidden = h; }
  function setDisabled(el, d) { if (el.disabled !== d) el.disabled = d; }

  // Il file si scrive, e il motore si avvisa, solo da fermo ai box. Avvisare
  // il motore (`/engineer/applied`) apre la prova della modifica, o rifa' la
  // base dopo un ripristino; in pista la macchina ha ancora l'assetto di
  // prima, perche' un file si carica solo dal garage, e i giri di prova
  // sarebbero guidati con l'assetto sbagliato. Lo stesso vale per «L'ho gia'
  // rimesso com'era»: il file di prima si ricarica ai box, e il motore
  // svuota la finestra e rifa' la base da quel momento.
  function atBoxNow() { return !!(last && last.connected && last.at_box); }

  function basePath() {
    if (bx.chosen) return bx.chosen;
    return (bx.base && bx.base.base) || null;
  }
  function setupNames() {
    var out = [], s = (bx.base && bx.base.setups) || [];
    for (var i = 0; i < s.length; i++) out.push(s[i].name);
    return out;
  }

  function loadBase() {
    var seq = ++bx.baseSeq;
    xhr("GET", "/api/setup/base?car=" + encodeURIComponent(bx.car)
        + "&track=" + encodeURIComponent(bx.track), null, function (err, data) {
      if (seq !== bx.baseSeq) return;
      bx.base = err ? null : data;
      bx.baseErr = err ? t("eng.loadErr") + err.detail : "";
      // Un file scelto che non c'e' piu' non resta nominato.
      var still = false, s = (bx.base && bx.base.setups) || [];
      for (var i = 0; i < s.length; i++) if (s[i].path === bx.chosen) still = true;
      if (!still) bx.chosen = null;
      fillSelect();
      paintBox();
    });
  }

  // La tendina si rifa' solo quando arriva l'elenco, non a ogni frame: il dito
  // che la sta aprendo la perderebbe.
  function fillSelect() {
    var sel = $("t-base"), s = (bx.base && bx.base.setups) || [], cur = basePath();
    sel.innerHTML = "";
    for (var i = 0; i < s.length; i++) {
      var o = document.createElement("option");
      o.value = s[i].path;
      o.textContent = s[i].name;
      if (s[i].path === cur) o.selected = true;
      sel.appendChild(o);
    }
  }

  function loadPreview(path, changes, key) {
    var seq = ++bx.pvSeq;
    xhr("POST", "/api/setup/preview", { path: path, changes: changes }, function (err, data) {
      if (seq !== bx.pvSeq || key !== bx.pvKey) return;
      bx.preview = err ? null : data;
      bx.pvErr = err ? t("eng.previewErr") + err.detail : "";
      drawLevers($("t-levers"));
      paintBox();
    });
  }

  // Il valore fisico arriva dal formato del file come testo, «26.2 psi» o
  // «11» (AC, senza unita'): `physParse` ne tira fuori numero, decimali e
  // unita'. Quello che non e' «numero [unita']» (su ACC «11 click (~0.1psi/click)»)
  // non si legge, e la riga va in click.
  function physParse(s) {
    var m = /^(-?\d+)(?:\.(\d+))?(?: ([^\d]+))?$/.exec(s == null ? "" : String(s));
    if (!m) return null;
    return { v: parseFloat(m[1] + "." + (m[2] || "0")), d: m[2] ? m[2].length : 0,
             unit: m[3] || "" };
  }

  // Il testo di una leva dopo il nome. I click sono la verita' (sono quello
  // che si scrive); il valore fisico si mostra solo quando dice qualcosa in
  // piu': non quando e' in click, non quando non si legge, non quando e' lo
  // stesso numero dei click. Allora «11 → 9 click»; se no come il riepilogo
  // della pagina completa, «26,8 psi → 27,0 psi (+2 click)», i due valori coi
  // decimali del piu' preciso, se no «27» accanto a «26,8» sembra un'altra
  // misura. Il meno dei click e' quello di `fmtNum`, come quello dei valori.
  function leverText(d) {
    var clicks = d.old_click + " → " + d.new_click + " " + t("eng.click");
    var a = physParse(d.old_phys), b = physParse(d.new_phys);
    if (!a || !b || a.unit !== b.unit || a.unit === "click"
        || (a.v === Number(d.old_click) && b.v === Number(d.new_click))) return clicks;
    var dec = Math.max(a.d, b.d);
    var delta = Number(d.new_click) - Number(d.old_click);
    return fmtN(a.v, dec, a.unit) + " → " + fmtN(b.v, dec, b.unit)
           + " (" + (delta > 0 ? "+" : (delta < 0 ? "−" : "")) + Math.abs(delta)
           + " " + t("eng.click") + ")";
  }

  // Ogni leva in una riga: nome, ruota o lato, il valore da a.
  function drawLevers(ul) {
    ul.innerHTML = "";
    var lines = [];
    if (bx.pvErr) lines.push([null, bx.pvErr]);
    else if (bx.preview && !bx.preview.ok) {
      var errs = bx.preview.errors || [];
      for (var e = 0; e < errs.length; e++) lines.push([null, String(errs[e])]);
    } else if (bx.preview) {
      var diff = bx.preview.diff || [];
      for (var i = 0; i < diff.length; i++) {
        var d = diff[i];
        lines.push([d.label + (d.slot ? " " + d.slot : ""), leverText(d)]);
      }
    }
    for (var k = 0; k < lines.length; k++) {
      var li = document.createElement("li");
      if (lines[k][0] != null) {
        var b = document.createElement("b");
        b.textContent = lines[k][0];
        li.appendChild(b);
        li.appendChild(document.createTextNode(" " + lines[k][1]));
      } else {
        li.className = "t-bad";
        li.textContent = lines[k][1];
      }
      ul.appendChild(li);
    }
  }

  // Le regole, a ogni frame: chiedere la base entrando in Assetto (o ai box) o
  // se cambiano auto e pista, l'anteprima se cambiano file o leve. Poi si
  // dipinge.
  function boxFrame(st, m, tab) {
    var atBox = m !== "off" && !!st.at_box;
    // Riparti dai box: il file scritto e l'errore erano di quella sosta.
    // Spento non conta come partenza ne' come sosta: box, spento, pista e'
    // ripartire lo stesso.
    if (m !== "off") {
      if (wasAtBox && !atBox) { bx.done = null; bx.err = ""; }
      wasAtBox = atBox;
    }
    var on = m !== "off" && (tab === "setup" || atBox);
    var entering = on && !bxOn;
    bxOn = on;
    // L'errore di una scrittura non resta per la prossima volta che apri
    // Assetto; il file scritto si' (e' il nome da caricare ai box).
    if (entering) bx.err = "";
    if (!on) {
      // Lasci Assetto: la conferma aperta non resta per la prossima volta.
      // Una scrittura gia' partita invece finisce, e avvisa il motore lo stesso.
      // Ripartire dai box porta sempre qui (`pickTab` torna a Telemetria):
      // e' questo che toglie la conferma a chi riparte, e `confirmWrite`
      // ricontrolla i box lo stesso.
      if (!bx.writing) bx.confirm = null;
      return;
    }
    var eng = st.engineer || null;
    // Una proposta nuova: il file scritto per quella di prima non e' piu'
    // la notizia.
    if (bx.done && boxChange(eng) && avKey(eng) !== bx.done.key) bx.done = null;
    var car = String(st.car || ""), track = String(st.track || "");
    var combo = car + "|" + track;
    if (combo !== bx.combo) {
      bx.combo = combo; bx.car = car; bx.track = track;
      bx.chosen = null; bx.base = null;
      // Il file scritto e l'errore erano di un'altra auto o pista.
      bx.done = null; bx.err = "";
      fillSelect();
      loadBase();
    } else if (entering) {
      loadBase();
    }
    var changes = boxChange(eng) ? changesFor(eng) : [];
    var path = basePath();
    var key = changes.length && path ? path + "\n" + JSON.stringify(changes) : null;
    if (key !== bx.pvKey) {
      bx.pvKey = key; bx.pvChanges = changes;
      bx.preview = null; bx.pvErr = "";
      drawLevers($("t-levers"));
      if (key) loadPreview(path, changes, key);
    }
    // La conferma nomina un file e delle leve: se cambiano, non vale piu'.
    if (bx.confirm && !bx.writing && bx.confirm.key !== bx.pvKey) bx.confirm = null;
    paintBox();
  }

  function paintBox() {
    if (!bxOn) return;
    var eng = (last && last.engineer) || null;
    var has = boxChange(eng);
    var restore = has && eng.kind === "reverted";
    setHidden($("t-change"), !has);
    if (has) {
      setText($("t-why"), restore ? (eng.message || eng.rationale || "")
                                  : (eng.rationale || eng.message || ""));
      // Un ripristino non e' una stima: niente grado di fiducia.
      var c = eng.confidence || "medium";
      setHidden($("t-conf"), restore);
      setText($("t-conf"), t("eng.conf." + c));
      $("t-conf").setAttribute("data-c", c);
      setHidden($("t-lowconf"), restore || c !== "low");
      setText($("t-lowconf"), t("eng.lowConf"));
    }
    var msg = !has ? msgText(eng) : "";
    setText($("t-msg"), msg);
    setHidden($("t-msg"), !msg);

    var setups = (bx.base && bx.base.setups) || [];
    setHidden($("t-base-row"), !has);
    setHidden($("t-base"), !setups.length);
    setHidden($("t-nobase"), !bx.base || setups.length > 0);

    var ready = !!(bx.preview && bx.preview.ok && basePath());
    var atBox = atBoxNow();
    setHidden($("t-actions"), !has || !!bx.confirm);
    setText($("t-write"), t(restore ? "tablet.writeRestore" : "tablet.write"));
    setDisabled($("t-write"), !ready || bx.writing || !atBox);
    setHidden($("t-restored"), !restore || bx.restoredKey === avKey(eng));
    setDisabled($("t-restored"), !atBox);
    // In pista la modifica si legge, e una riga dice perche' i bottoni sono
    // spenti.
    setHidden($("t-atbox"), !has || atBox);

    setHidden($("t-confirm"), !bx.confirm);
    var err = bx.err || bx.baseErr;
    setText($("t-err"), err);
    setHidden($("t-err"), !err);
    setHidden($("t-done"), !bx.done);
    if (bx.done) {
      // Il nome da cercare nel gioco, grande; la frase intorno la dice gia'
      // `reload_hint` («Ho scritto «HONE_2». Ai box apri…»), non si ripete.
      setText($("t-done-name"), bx.done.name);
      setText($("t-done-hint"), bx.done.hint);
    }
  }

  // Il primo tocco: la conferma con le leve e il nome del file nuovo. Quello
  // che si scrive e' quello che la conferma nomina, preso qui e non al tocco
  // dopo, cosi' un frame che arriva nel mezzo non cambia il file sotto il dito.
  function openConfirm() {
    if (!bx.preview || !bx.preview.ok || bx.writing || !basePath() || !atBoxNow()) return;
    bx.confirm = { key: bx.pvKey, path: basePath(), changes: bx.pvChanges,
                   name: nextName(setupNames()), av: avKey(last && last.engineer) };
    bx.err = "";
    $("t-confirm-msg").textContent = tf("tablet.confirm", { name: bx.confirm.name });
    drawLevers($("t-confirm-list"));
    $("t-confirm-ok").disabled = false;
    paintBox();
  }

  // Il secondo tocco scrive. Il bottone si spegne subito, prima della
  // richiesta: un doppio tocco scriverebbe due file.
  function confirmWrite() {
    var c = bx.confirm;
    if (!c || bx.writing || !atBoxNow()) return;
    $("t-confirm-ok").disabled = true;
    bx.writing = true;
    bx.err = "";
    writeAttempt(c, c.name, 0);
  }

  // La regola di `applyNow`: l'elenco e' la nostra idea dei nomi presi, il
  // disco la sa meglio. Un 409 «already exists» non e' un errore da mostrare,
  // si prova il nome dopo; quattro tentativi al massimo.
  function writeAttempt(c, name, attempt) {
    xhr("POST", "/api/setup/apply",
        { path: c.path, as_name: name, confirm: true, changes: c.changes },
        function (err, res) {
      if (!err) { afterWrite(res, c); return; }
      var taken = err.status === 409 && err.detail.indexOf("already exists") !== -1;
      if (taken && attempt + 1 < 4) {
        writeAttempt(c, "HONE_" + (parseInt(name.split("_").pop(), 10) + 1), attempt + 1);
        return;
      }
      bx.writing = false;
      bx.err = taken ? tf("eng.writeErrName", { name: name }) : t("tablet.writeErr") + err.detail;
      $("t-confirm-ok").disabled = false;
      paintBox();
    });
  }

  // Come `afterWrite` di engineer.js: si avvisa il motore (se no l'ingegnere
  // ripropone la stessa modifica a ogni giro), e il file appena scritto
  // diventa la base, perche' e' quello che ti dice di caricare.
  function afterWrite(res, c) {
    bx.writing = false;
    bx.confirm = null;
    bx.done = { name: (res && res.name) || "", hint: (res && res.reload_hint) || "",
                key: c.av };
    bx.chosen = null;
    postApplied();
    loadBase();
    paintBox();
  }

  // «L'ho gia' rimesso com'era» (`confirmRestored`): chi ripristina caricando
  // nel gioco il file di prima non scrive niente, e il motore aspetta lo stesso.
  function confirmRestored() {
    if (!atBoxNow()) return;
    var eng = last && last.engineer;
    bx.restoredKey = avKey(eng);
    $("t-restored").hidden = true;
    postApplied();
  }

  var last = null;
  var tabPrev = null;           // {tab, atBox} del frame prima, per pickTab
  var tabTapped = null;         // la linguetta toccata, consumata dal frame dopo
  var tapping = false;          // il ridisegno di un tocco: non e' un frame nuovo

  function setAttr(el, k, v) { if (el.getAttribute(k) !== v) el.setAttribute(k, v); }

  // Le linguette e il segno su Assetto: c'e' una modifica da fare ai box
  // (con l'avviso di rientro, o gia' fermo).
  function renderTabs(tab, mark) {
    setAttr($("t-tab-track"), "aria-selected", tab === "track" ? "true" : "false");
    setAttr($("t-tab-setup"), "aria-selected", tab === "setup" ? "true" : "false");
    setAttr($("t-tab-setup"), "data-mark", mark ? "1" : "0");
  }

  function render(st) {
    last = st;
    var m = mode(st);
    var tab = tabPrev ? tabPrev.tab : "track";
    if (m !== "off") {
      tab = pickTab(tabPrev, st, tabTapped);
      tabPrev = { tab: tab, atBox: !!st.at_box };
    }
    tabTapped = null;
    $("tablet").setAttribute("data-mode", m);
    $("tablet").setAttribute("data-tab", tab);
    renderTabs(tab, m !== "off" && (m === "call" || boxChange(st.engineer)));
    boxFrame(st, m, tab);
    if (m === "off") {
      var wait = offKey(st) === "tablet.waiting";
      setHidden($("t-off-closed"), wait || keyRefused || noKey);
      setHidden($("t-off-key"), wait || !keyRefused);
      setHidden($("t-off-pc"), wait || !noKey);
      setHidden($("t-off-wait"), !wait);
      traceReset();
      return;
    }
    var eng = st.engineer || null;
    $("t-speed").textContent = num(st.speed_kmh) ? fmtN(Math.round(st.speed_kmh), 0) : "–";
    $("t-gear").textContent = st.gear == null ? "–" : String(st.gear);
    $("t-tc").textContent = aid(st.aids && st.aids.tc);
    $("t-abs").textContent = aid(st.aids && st.aids.abs);
    $("t-map").textContent = aid(st.aids && st.aids.engine_map);
    renderTyres(st.tyres);
    // Il ridisegno di un tocco rifa' l'ultimo frame: un campione in piu' dei
    // pedali, con l'ora di adesso, sarebbe inventato.
    if (!tapping) tracePush(st);
    renderRoad(eng);
    renderPhase(eng);
    renderAv(eng);
    renderCall(eng, m);
  }

  // ---- collegamento ---------------------------------------------------------
  // Un frame che non si disegna non ferma la vista, ma lascia traccia: senza,
  // un elemento che manca congelerebbe la schermata a meta' in silenzio. Una
  // volta per messaggio, non quindici al secondo.
  var logged = {};
  function logOnce(e) {
    var msg = String((e && e.message) || e);
    if (logged[msg]) return;
    logged[msg] = true;
    try { console.error("HONE tablet: un frame non si disegna", e); } catch (e2) {}
  }

  // Un WebSocket rifiutato dal guardiano si chiude come un motore spento, e il
  // perche' non lo dice. Lo si chiede alla 8777 con una richiesta normale: un
  // 401 e' la chiave che manca, e la schermata dice del QR invece di «coach
  // spento». Un 503 e' il PC che non ha potuto salvare la chiave, e lo dice.
  // Motore spento (nessuna risposta) resta «coach spento».
  var keyRefused = false;
  var noKey = false;
  function probeKey() {
    xhr("GET", liveUrl("http://" + location.hostname + ":" + WS_PORT + "/health"), null,
        function (err) {
          keyRefused = !!(err && err.status === 401);
          noKey = !!(err && err.status === 503);
          if (!last) render(null);
        });
  }

  function connect() {
    var ws;
    try { ws = new WebSocket(liveUrl("ws://" + location.hostname + ":" + WS_PORT + "/ws")); }
    catch (e) { setTimeout(connect, 3000); return; }
    ws.onmessage = function (ev) {
      keyRefused = false;
      noKey = false;
      try { render(JSON.parse(ev.data)); } catch (e) { logOnce(e); }
    };
    // Il motore spento o riavviato: la schermata lo dice e si ricollega da sola.
    ws.onclose = function () {
      render(null);
      probeKey();
      setTimeout(connect, 3000);
    };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }

  // Il tocco su una linguetta si vede subito, col frame che c'era: non si
  // aspetta il prossimo dal motore.
  function tapTab(tab) {
    tabTapped = tab;
    if (!last) return;
    redraw();
  }

  // Ridisegna l'ultimo frame (un tocco, un altro file, la lingua): non e' un
  // frame nuovo, quindi niente campione dei pedali.
  function redraw() {
    tapping = true;
    try { render(last); } finally { tapping = false; }
  }

  function boot() {
    $("t-tab-track").onclick = function () { tapTab("track"); };
    $("t-tab-setup").onclick = function () { tapTab("setup"); };
    // L'avviso di rientro porta ad Assetto: la modifica si legge prima di
    // entrare.
    $("t-call").onclick = function () { tapTab("setup"); };
    $("t-av-done").onclick = function () {
      avTapped = $("t-av-done").getAttribute("data-key");
      $("t-av-done").hidden = true;
      postApplied();
    };
    $("t-write").onclick = openConfirm;
    $("t-confirm-ok").onclick = confirmWrite;
    $("t-confirm-no").onclick = function () {
      if (bx.writing) return;
      bx.confirm = null;
      paintBox();
    };
    $("t-restored").onclick = confirmRestored;
    // Un altro file di partenza: l'anteprima si rifa' al frame dopo.
    $("t-base").onchange = function () {
      bx.chosen = $("t-base").value || null;
      if (last) redraw();
    };
    // Cambio di lingua dalla pagina: i testi fissi li rifa' i18n.js, quelli
    // scritti da qui si rifanno col frame che c'era.
    // L'anteprima arriva tradotta dal server: si richiede nella lingua nuova.
    window.HoneI18nRerender = function () {
      bx.pvKey = null;
      if (bx.confirm) $("t-confirm-msg").textContent = tf("tablet.confirm", { name: bx.confirm.name });
      redraw();
    };
    if (window.HoneI18n) window.HoneI18n.applyStatic();
    if (!fullPageWorks()) $("t-full").hidden = true;
    window.addEventListener("resize", function () { traceDraw(); });
    render(null);
    connect();
  }

  window.HoneTablet = { mode: mode, pickTab: pickTab, render: render, callKey: callKey,
                        avKey: avKey, avDoneHidden: avDoneHidden,
                        nextName: nextName, changesFor: changesFor,
                        offText: function (st) { return t(offKey(st)); },
                        leverText: leverText, fullPageWorks: fullPageWorks,
                        stripText: stripText, msgText: msgText };

  // In node (i test) non c'e' la pagina: si carica solo `mode`.
  if (typeof document !== "undefined" && document && document.getElementById("tablet")) boot();
})();
