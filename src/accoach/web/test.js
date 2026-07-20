/* HONE on-track test checklist (tablet).
 *
 * Reads the live engine feed from the `server` backend over WebSocket
 * (ws://<host>:8777/ws) and, while you sit on a test, auto-captures every cue
 * HONE fires — category, text and a telemetry snapshot of the moment — plus the
 * lap you just recorded. Verdicts + notes + captures are saved to the PC as JSON
 * (POST /api/test/save) for later threshold calibration.
 */
(() => {
  "use strict";
  const LIVE_PORT = 8777;
  const $ = (id) => document.getElementById(id);
  const round = (x, n = 0) => (x == null ? null : Number(x.toFixed(n)));

  const S = {
    plan: null,
    runId: null,
    started: null,
    sim: "ACC",
    category: null,
    car: "",
    track: "",
    index: 0,
    results: {},        // testId -> {outcome, notes, captured_cues[], lap}
  };
  let lastCueKey = null;
  let saveTimer = null;

  // --- persistence -----------------------------------------------------
  const LS = "hone_testrun_v1";
  function persist() {
    try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) {}
  }
  function restore() {
    try {
      const raw = localStorage.getItem(LS);
      if (!raw) return false;
      Object.assign(S, JSON.parse(raw));
      return true;
    } catch (e) { return false; }
  }
  function newRunId() {
    return new Date().toISOString().replace(/[:.]/g, "").slice(0, 15);
  }

  // --- current test helpers -------------------------------------------
  function cat() { return S.plan.categories.find((c) => c.id === S.category); }
  function tests() { return cat() ? cat().tests : []; }
  function curTest() { return tests()[S.index] || null; }
  function result(id) {
    if (!S.results[id]) S.results[id] = { outcome: null, notes: "", captured_cues: [], lap: null };
    return S.results[id];
  }

  // --- render ----------------------------------------------------------
  function render() {
    const t = curTest();
    const list = tests();
    // Every category carries its own intro in the plan; show the current one.
    $("intro").textContent = cat() ? (cat().intro || "") : "";
    const done = list.filter((x) => result(x.id).outcome).length;
    $("p-text").textContent = `${done} / ${list.length}`;
    $("p-bar").style.width = list.length ? `${(done / list.length) * 100}%` : "0";
    $("prev").disabled = S.index <= 0;
    $("next").textContent = S.index >= list.length - 1 ? "Fine" : "Avanti ›";

    if (!t) { $("card").innerHTML = "<p>Nessun test in questa categoria.</p>"; return; }
    const r = result(t.id);
    $("card").innerHTML = `
      <div class="num">Test ${t.n} · ${S.category}</div>
      <h2>${esc(stripNum(t.what))}</h2>
      ${t.how ? blk("Come farlo", t.how) : ""}
      ${t.expected ? blk("Cosa deve fare HONE", t.expected, "expected") : ""}
      <div class="verdicts">
        ${vbtn("pass", "✓ OK", r)}${vbtn("partial", "⚠ Parziale", r)}
        ${vbtn("fail", "✗ NO", r)}${vbtn("skip", "— Salta", r)}
      </div>
      <div class="block">
        <div class="lab">Cosa hai visto / note</div>
        <textarea id="notes" placeholder="note libere…">${esc(r.notes)}</textarea>
      </div>
      ${lapChip(r)}
      <div class="captured">
        <div class="lab"><span>Cue catturati dal vivo (${r.captured_cues.length})</span>
          <button type="button" id="clearCues">azzera</button></div>
        ${cueList(r)}
      </div>`;

    $$(".verdict").forEach((b) => b.onclick = () => setVerdict(t.id, b.dataset.v));
    $("notes").oninput = (e) => { result(t.id).notes = e.target.value; persist(); scheduleSave(); };
    $("clearCues").onclick = () => { result(t.id).captured_cues = []; persist(); render(); scheduleSave(); };
  }

  const blk = (lab, txt, cls = "") =>
    `<div class="block ${cls}"><div class="lab">${lab}</div>${esc(txt)}</div>`;
  const vbtn = (v, label, r) =>
    `<button class="verdict ${r.outcome === v ? "sel" : ""}" data-v="${v}">${label}</button>`;
  function cueList(r) {
    if (!r.captured_cues.length)
      return `<div class="cue-empty">Nessun cue ancora — guida la manovra del test.</div>`;
    return `<ul class="cue-list">${r.captured_cues.map((c) => `
      <li><span class="cat">${esc(c.category)}</span> — ${esc(c.message)}
      <div class="tel">${fmtTel(c.tel)}</div></li>`).join("")}</ul>`;
  }
  function lapChip(r) {
    if (!r.lap) return `<div class="lapchip">Nessun giro agganciato ancora.</div>`;
    return `<div class="lapchip">Giro agganciato: <b>${esc(r.lap.lap_time || "?")}</b>
      · ${esc(r.lap.car || "")} @ ${esc(r.lap.track || "")}
      ${r.lap.valid ? "" : "· <i>non valido</i>"}</div>`;
  }
  function fmtTel(tel) {
    if (!tel) return "";
    const p = [];
    if (tel.spd != null) p.push(`${tel.spd} km/h`);
    if (tel.br != null) p.push(`freno ${Math.round(tel.br * 100)}%`);
    if (tel.th != null) p.push(`gas ${Math.round(tel.th * 100)}%`);
    if (tel.gear) p.push(`m${tel.gear}`);
    if (tel.pos != null) p.push(`pos ${tel.pos.toFixed(2)}`);
    return p.join(" · ");
  }

  // --- actions ---------------------------------------------------------
  function setVerdict(id, v) {
    const r = result(id);
    r.outcome = (r.outcome === v) ? null : v;   // tap again to clear
    persist();
    render();
    if (r.outcome) attachLatestLap(id);
    scheduleSave();
  }

  async function attachLatestLap(id) {
    try {
      const res = await fetch("/api/test/latest_lap");
      const data = await res.json();
      if (data && data.lap) { result(id).lap = data.lap; persist(); render(); scheduleSave(); }
    } catch (e) { /* offline / no web server — ignore */ }
  }

  function scheduleSave() {
    setSaveState("salvo…", false);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveRun, 800);
  }
  // "Fine": skip the debounce and persist immediately, with a clear confirmation.
  async function saveNow() {
    clearTimeout(saveTimer);
    setSaveState("salvo…", false);
    await saveRun();
  }
  async function saveRun() {
    const payload = {
      run_id: S.runId, started: S.started, app: "HONE test",
      sim: S.sim, category: S.category,
      category_title: cat() ? cat().title : S.category,
      car: S.car, track: S.track,
      saved: new Date().toISOString(),
      results: tests().map((t) => {
        const r = result(t.id);
        return {
          id: t.id, n: t.n, what: stripNum(t.what), expected: t.expected,
          outcome: r.outcome, notes: r.notes,
          captured_cues: r.captured_cues, lap: r.lap,
        };
      }),
    };
    try {
      const res = await fetch("/api/test/save", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setSaveState(data.ok ? "salvato ✓" : "errore salvataggio", data.ok);
    } catch (e) {
      setSaveState("salvataggio non riuscito", false);
    }
  }
  function setSaveState(txt, ok) {
    const el = $("savestate");
    el.textContent = txt; el.classList.toggle("ok", !!ok);
  }

  // --- live feed (WebSocket) ------------------------------------------
  function connectLive() {
    const url = `ws://${location.hostname}:${LIVE_PORT}/ws`;
    let ws;
    try { ws = new WebSocket(url); } catch (e) { retry(); return; }
    ws.onopen = () => setDot("on");
    ws.onclose = () => { setDot("off"); retry(); };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
    ws.onmessage = (ev) => { try { onState(JSON.parse(ev.data)); } catch (e) {} };
    function retry() { setTimeout(connectLive, 2000); }
  }
  function setDot(cls) {
    const d = $("dot"); d.className = "dot" + (cls ? " " + cls : "");
  }

  function onState(st) {
    setDot(st.connected ? "on" : "off");
    $("l-car").textContent = st.car || "—";
    $("l-track").textContent = st.track || "—";
    $("l-speed").textContent = st.speed_kmh != null ? Math.round(st.speed_kmh) : "—";
    $("l-delta").textContent = st.delta ? st.delta.text : "—";
    // Auto-fill session fields the first time the game tells us what we're in.
    if (st.car && !S.car) { S.car = st.car; $("car").value = st.car; persist(); }
    if (st.track && !S.track) { S.track = st.track; $("track").value = st.track; persist(); }

    const cue = st.cue;
    const chip = $("l-cue");
    if (cue && cue.message) {
      chip.textContent = cue.message; chip.classList.add("hot");
    } else {
      chip.textContent = "nessun avviso"; chip.classList.remove("hot");
    }
    captureCue(cue, st);
  }

  function captureCue(cue, st) {
    if (!cue || !cue.message) { lastCueKey = null; return; }
    const key = cue.category + "|" + cue.message;
    if (key === lastCueKey) return;      // same firing still active — don't dup
    lastCueKey = key;
    const t = curTest();
    if (!t) return;
    const r = result(t.id);
    r.captured_cues.push({
      t: new Date().toISOString(),
      category: cue.category, message: cue.message, segment: cue.segment,
      tel: {
        spd: round(st.speed_kmh), br: round(st.brake, 2), th: round(st.throttle, 2),
        gear: st.gear, pos: st.lap_position,
        tc: st.aids ? st.aids.tc : null, abs: st.aids ? st.aids.abs : null,
        tyre_temp: st.tyres ? st.tyres.temp : null,
        tyre_press: st.tyres ? st.tyres.pressure : null,
      },
    });
    if (r.captured_cues.length > 60) r.captured_cues.shift();
    persist();
    if (t.id === curTest()?.id) render();
    scheduleSave();
  }

  // --- setup wiring ----------------------------------------------------
  function fillCategories() {
    const sel = $("category");
    sel.innerHTML = S.plan.categories
      .map((c) => `<option value="${c.id}">${esc(c.title || c.id)}</option>`).join("");
    if (!S.category) S.category = S.plan.categories[0].id;
    sel.value = S.category;
    sel.onchange = () => { S.category = sel.value; S.index = 0; persist(); render(); };
  }
  function fillGlossary() {
    $("glossBody").innerHTML = (S.plan.glossary || [])
      .map((g) => `<dt>${esc(g.term)}</dt><dd>${esc(g.meaning)}</dd>`).join("");
    $("glossBtn").onclick = () => $("glossDlg").showModal();
  }

  // --- guided tour (vanilla coachmarks — see tour.js) -------------------
  // Says what to *do*, not what each control is: you arrive here from a QR code
  // with a helmet on, not looking for a UI reference. Targets that aren't on
  // screen are skipped by the tour engine, so the card steps are safe even when
  // a category has no tests.
  function tourSteps() {
    return [
      { sel: ".setup", title: "Dimmi cosa stai provando",
        text: "Scegli la categoria dell'auto e il simulatore. Auto e pista li riconosco da " +
              "solo appena vai in pista." },
      { sel: "#card", title: "Una prova alla volta",
        text: "Leggi come farla e cosa dovrei fare io. Ripetila due o tre volte prima di " +
              "darmi un giudizio." },
      { sel: ".verdicts", title: "Dimmi se ho azzeccato l'avviso",
        text: "Tocca il verdetto dopo la prova. Mi serve per capire se un avviso parte " +
              "quando non deve — non è un voto sulla tua guida." },
      { sel: ".captured", title: "Quello che dico lo segno io",
        text: "Ogni avviso che do mentre guidi finisce qui con la telemetria del momento. " +
              "Tu pensa a guidare." },
      { sel: "#savestate", title: "Salvo da solo, sul tuo PC",
        text: "Non devi premere niente: puoi chiudere la pagina e riprendere quando vuoi." },
    ];
  }
  // This page is Italian-only (it doesn't load i18n.js), so the tour buttons
  // have to be told their labels — tour.js defaults to English.
  const TOUR_LABELS = {
    skip: "Salta", back: "Indietro", next: "Avanti", done: "Ho capito", step: "Passo",
  };
  function wireTour() {
    if (!window.HoneTour) return;
    $("tourBtn").onclick =
      () => window.HoneTour.start(tourSteps(), "hone_tour_test", TOUR_LABELS);
  }
  function wireSetup() {
    $("car").value = S.car; $("track").value = S.track;
    $("car").oninput = (e) => { S.car = e.target.value; persist(); scheduleSave(); };
    $("track").oninput = (e) => { S.track = e.target.value; persist(); scheduleSave(); };
    $$("#sim button").forEach((b) => b.onclick = () => {
      S.sim = b.dataset.sim; persist();
      $$("#sim button").forEach((x) => x.classList.toggle("sel", x === b));
      scheduleSave();
    });
    $$("#sim button").forEach((x) => x.classList.toggle("sel", x.dataset.sim === S.sim));
    $("prev").onclick = () => { if (S.index > 0) { S.index--; persist(); render(); } };
    $("next").onclick = () => {
      if (S.index < tests().length - 1) { S.index++; persist(); render(); }
      else { saveNow(); }   // on the last step the button is "Fine": force a save now
    };
  }

  // --- utils -----------------------------------------------------------
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  const stripNum = (s) => String(s || "").replace(/^\s*\d+\)\s*/, "");

  // --- boot ------------------------------------------------------------
  async function boot() {
    const had = restore();
    const res = await fetch("/static/test_plan.json");
    S.plan = await res.json();
    if (!had || !S.runId) { S.runId = newRunId(); S.started = new Date().toISOString(); }
    fillCategories();
    fillGlossary();
    wireSetup();
    wireTour();
    render();
    connectLive();
    // First visit only: pop the tour once the card is on screen so its steps
    // have something to point at.
    if (window.HoneTour) window.HoneTour.auto(tourSteps(), "hone_tour_test", TOUR_LABELS);
  }
  boot();
})();
