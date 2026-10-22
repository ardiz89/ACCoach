"use strict";
// La vista tablet: la parte della pagina Ingegnere che serve in macchina, su
// un iPad 3 con Safari 9. Per questo e' ES5: niente let/const, funzioni
// freccia, fetch, e nessun `.forEach` (su Safari 9 la NodeList non ce l'ha, e
// qui non si rischia: solo cicli `for`). Il controllo sta in tests/safari9.py.
//
// La schermata cambia da sola a ogni frame dal vivo (`mode`): spento, in
// pista, avviso di rientro, fermo ai box. Le regole sono quelle che il motore
// e la pagina completa usano gia'; qui non se ne inventano.
(function () {
  var WS_PORT = 8777;            // il motore dal vivo; la pagina sta sulla 8778

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
      pe.textContent = num(pv) ? fmtN(Number(pv), 1) : "–";
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
    // Nascosta (ai box): la storia intanto si aggiorna.
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
        var detail = data && data.detail != null ? data.detail
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
  function postApplied() {
    xhr("POST", "http://" + location.hostname + ":" + WS_PORT + "/engineer/applied", null, null);
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
    confirm: null,        // {key, path, name, changes}: cio' che la conferma nomina
    writing: false,
    done: null,           // {name, hint} dopo una scrittura, fino a che riparti
    err: "",
    restoredKey: null     // avKey del ripristino su cui hai toccato «L'ho gia' rimesso»
  };
  var lastMode = "off";

  function setText(el, s) { if (el.textContent !== s) el.textContent = s; }
  function setHidden(el, h) { if (el.hidden !== h) el.hidden = h; }

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

  // Il valore fisico arriva dal formato del file come testo, «26.2 psi»: il
  // numero si riscrive con la regola della pagina (`fmtNum`, la virgola in
  // italiano), con gli stessi decimali. Quello che non e' «numero unita'» resta
  // com'e'.
  function physText(s) {
    s = s == null ? "" : String(s);
    var m = /^(-?\d+)(?:\.(\d+))?(?: ([^\d]+))?$/.exec(s);
    if (!m) return s;
    return fmtN(parseFloat(m[1] + "." + (m[2] || "0")), m[2] ? m[2].length : 0, m[3] || "");
  }

  // Ogni leva in una riga: nome, ruota o lato, il valore da a, e i clic.
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
        lines.push([d.label + (d.slot ? " " + d.slot : ""),
                    physText(d.old_phys) + " → " + physText(d.new_phys)
                    + " (" + d.old_click + " → " + d.new_click + " " + t("eng.click") + ")"]);
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

  // Le regole, a ogni frame in box: chiedere la base entrando o se cambiano
  // auto e pista, l'anteprima se cambiano file o leve. Poi si dipinge.
  function boxFrame(st, m) {
    var entering = m === "box" && lastMode !== "box";
    lastMode = m;
    if (m !== "box") {
      // Riparti: la conferma aperta non resta per la prossima sosta. Una
      // scrittura gia' partita invece finisce, e avvisa il motore lo stesso.
      if (!bx.writing) bx.confirm = null;
      return;
    }
    if (entering) { bx.done = null; bx.err = ""; }
    var car = String(st.car || ""), track = String(st.track || "");
    var combo = car + "|" + track;
    if (combo !== bx.combo) {
      bx.combo = combo; bx.car = car; bx.track = track;
      bx.chosen = null; bx.base = null;
      fillSelect();
      loadBase();
    } else if (entering) {
      loadBase();
    }
    var eng = st.engineer || null;
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
    if (lastMode !== "box") return;
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
    var msg = !has && eng && eng.message ? eng.message : "";
    setText($("t-msg"), msg);
    setHidden($("t-msg"), !msg);

    var setups = (bx.base && bx.base.setups) || [];
    setHidden($("t-base-row"), !has);
    setHidden($("t-base"), !setups.length);
    setHidden($("t-nobase"), !bx.base || setups.length > 0);

    var ready = !!(bx.preview && bx.preview.ok && basePath());
    setHidden($("t-actions"), !has || !!bx.confirm);
    setText($("t-write"), t(restore ? "tablet.writeRestore" : "tablet.write"));
    $("t-write").disabled = !ready || bx.writing;
    setHidden($("t-restored"), !restore || bx.restoredKey === avKey(eng));

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
    if (!bx.preview || !bx.preview.ok || bx.writing || !basePath()) return;
    bx.confirm = { key: bx.pvKey, path: basePath(), changes: bx.pvChanges,
                   name: nextName(setupNames()) };
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
    if (!c || bx.writing) return;
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
      if (!err) { afterWrite(res); return; }
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
  function afterWrite(res) {
    bx.writing = false;
    bx.confirm = null;
    bx.done = { name: (res && res.name) || "", hint: (res && res.reload_hint) || "" };
    bx.chosen = null;
    postApplied();
    loadBase();
    paintBox();
  }

  // «L'ho gia' rimesso com'era» (`confirmRestored`): chi ripristina caricando
  // nel gioco il file di prima non scrive niente, e il motore aspetta lo stesso.
  function confirmRestored() {
    var eng = last && last.engineer;
    bx.restoredKey = avKey(eng);
    $("t-restored").hidden = true;
    postApplied();
  }

  var last = null;

  function render(st) {
    last = st;
    var m = mode(st);
    $("tablet").setAttribute("data-mode", m);
    boxFrame(st, m);
    if (m === "off") {
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
    tracePush(st);
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

  function connect() {
    var ws;
    try { ws = new WebSocket("ws://" + location.hostname + ":" + WS_PORT + "/ws"); }
    catch (e) { setTimeout(connect, 3000); return; }
    ws.onmessage = function (ev) {
      try { render(JSON.parse(ev.data)); } catch (e) { logOnce(e); }
    };
    // Il motore spento o riavviato: la schermata lo dice e si ricollega da sola.
    ws.onclose = function () {
      render(null);
      setTimeout(connect, 3000);
    };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }

  function boot() {
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
      if (last) render(last);
    };
    // Cambio di lingua dalla pagina: i testi fissi li rifa' i18n.js, quelli
    // scritti da qui si rifanno col frame che c'era.
    // L'anteprima arriva tradotta dal server: si richiede nella lingua nuova.
    window.HoneI18nRerender = function () {
      bx.pvKey = null;
      if (bx.confirm) $("t-confirm-msg").textContent = tf("tablet.confirm", { name: bx.confirm.name });
      render(last);
    };
    if (window.HoneI18n) window.HoneI18n.applyStatic();
    window.addEventListener("resize", function () { traceDraw(); });
    render(null);
    connect();
  }

  window.HoneTablet = { mode: mode, render: render, callKey: callKey,
                        avKey: avKey, avDoneHidden: avDoneHidden,
                        nextName: nextName, changesFor: changesFor };

  // In node (i test) non c'e' la pagina: si carica solo `mode`.
  if (typeof document !== "undefined" && document && document.getElementById("tablet")) boot();
})();
