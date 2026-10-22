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
  function mode(st) {
    if (!st || !st.connected) return "off";
    if (st.at_box) return "box";
    var eng = st.engineer;
    if (eng && eng.tag === "BOX" && eng.change && eng.change.length && !eng.applied
        && (eng.kind === "propose" || eng.kind === "reverted")) return "call";
    return "track";
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

  // La proposta al volo resta in pista, col suo «Fatto» dove la pagina
  // completa lo mostra: solo dove il gioco non pubblica la manopola (AC), se
  // no il motore la vede girare e chiude da solo.
  function renderAv(eng) {
    var box = $("t-av");
    if (eng && eng.tag === "AV" && eng.change) {
      box.hidden = false;
      $("t-av-msg").textContent = eng.rationale || eng.message || "";
      $("t-av-done").hidden = !!eng.watched || !!eng.applied;
    } else {
      box.hidden = true;
    }
  }

  function renderCall(eng, m) {
    if (m !== "call") return;
    var restore = eng.kind === "reverted";
    $("t-call-msg").textContent = t(restore ? "tablet.callRestore" : "tablet.call");
    $("t-call-why").textContent = restore ? (eng.message || eng.rationale || "")
                                          : (eng.rationale || eng.message || "");
  }

  // Lo stesso endpoint di `afterWrite` e di `av-done` della pagina completa:
  // quello che l'ingegnere aveva chiesto e' sulla macchina. Senza fetch su
  // Safari 9, quindi XMLHttpRequest. Best-effort: a motore spento si riprova.
  function postApplied() {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "http://" + location.hostname + ":" + WS_PORT + "/engineer/applied");
      xhr.send();
    } catch (e) { /* motore spento: l'ingegnere continua a proporre */ }
  }

  var last = null;

  function render(st) {
    last = st;
    var m = mode(st);
    $("tablet").setAttribute("data-mode", m);
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
  function connect() {
    var ws;
    try { ws = new WebSocket("ws://" + location.hostname + ":" + WS_PORT + "/ws"); }
    catch (e) { setTimeout(connect, 3000); return; }
    ws.onmessage = function (ev) {
      try { render(JSON.parse(ev.data)); } catch (e) { /* un frame rotto non ferma la vista */ }
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
      $("t-av-done").hidden = true;
      postApplied();
    };
    // Cambio di lingua dalla pagina: i testi fissi li rifa' i18n.js, quelli
    // scritti da qui si rifanno col frame che c'era.
    window.HoneI18nRerender = function () { render(last); };
    if (window.HoneI18n) window.HoneI18n.applyStatic();
    window.addEventListener("resize", function () { traceDraw(); });
    render(null);
    connect();
  }

  window.HoneTablet = { mode: mode, render: render };

  // In node (i test) non c'e' la pagina: si carica solo `mode`.
  if (typeof document !== "undefined" && document && document.getElementById("tablet")) boot();
})();
