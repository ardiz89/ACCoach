"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (s) => (s >= 0 ? "+" : "") + s.toFixed(3);
// i18n: translate a chrome string (defensive if i18n.js failed to load).
const t = (k) => (window.HoneI18n ? window.HoneI18n.t(k) : k);
const LANG = () => (window.HoneI18n ? window.HoneI18n.lang : "en");

let CURRENT = null;   // current combo {car, track}
let DATA = null;      // last /api/analysis payload
let DIST = null;      // {pos[], m[], total} — the reviewed lap in metres (see buildDistance)
let COMBOS = [];      // last /api/combos payload (kept for re-labelling on lang switch)
let LAST_HOVER = null; // last hover position, so a re-render keeps the readout
let VIEW = "recap";   // whichever tab is `active` in index.html
let HOVER_WIRED = false;
// Did the driver pick the comparison lap by hand, or is it just whatever the
// page elected last time? The difference matters now that the election depends
// on the lap being reviewed: the picker is filled with the elected reference, so
// passing its value back on every reload pinned the page to a reference chosen
// for a *different* lap's conditions — and, because the page was then no longer
// showing the elected lap, it also swallowed the note explaining why.
let BASELINE_PINNED = false;
let MAP_HIT = null;   // {rv, X, Y} screen transform captured by drawMap, for map hover
let DYN_GG = null;    // {pts:[{px,py,pos}]} screen points captured by drawGG, for its hover
let DYN_BAL_HIT = null; // {rv, X, Y} transform captured by the balance ribbon, for its hover
const MAP_READOUT_DEFAULT = () => t("map.readout");

// Delta palette, read from the CSS --red/--green vars so the colour-blind toggle
// (header ◑) reaches the canvas-drawn map line and delta-chart tints too, not
// just the CSS surfaces. Refreshed on load and whenever the toggle flips.
let PAL = { slow: [255, 77, 94], fast: [52, 224, 138] };
function _hexRgb(s) {
  const m = (s || "").trim().match(/^#?([0-9a-fA-F]{6})$/);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function refreshPalette() {
  const cs = getComputedStyle(document.body);
  PAL.slow = _hexRgb(cs.getPropertyValue("--red")) || PAL.slow;
  PAL.fast = _hexRgb(cs.getPropertyValue("--green")) || PAL.fast;
}
// Apply the saved preference before first paint, then load the active palette.
document.body.classList.toggle("cb-safe", localStorage.getItem("hone_cb") === "1");
refreshPalette();

// A value that rounds to nothing prints as "0", never "-0.0": a minus sign in
// front of a zero reads as a measurement, and there isn't one.
function fixz(v, d) {
  return (Math.abs(v) < 0.5 * Math.pow(10, -d) ? 0 : v).toFixed(d);
}

// Text going into an HTML attribute (a tooltip): the debrief writes prose, and
// prose contains apostrophes and quotes in both our languages.
function escAttr(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;")
                        .replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtMs(ms) {
  if (!ms || ms <= 0) return "--:--.---";
  const m = Math.floor(ms / 60000);
  const s = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
  return `${m}:${s}`;
}

// Drop a "Loading…" placeholder into a .summary panel while a fetch is in
// flight; the success/error handler overwrites it when the response lands.
function setPanelLoading(id, msg) {
  const el = $(id);
  if (el) el.innerHTML = `<div class="item"><div class="v">…</div><div class="k">${msg}</div></div>`;
}

async function getJSON(url) {
  // Pass the active language so backend-generated content arrives localised:
  // the debrief, the corner names and the guided flow are all written server
  // side. A language switch therefore has to re-request, not just repaint.
  const u = url + (url.indexOf("?") === -1 ? "?" : "&") + "lang=" + encodeURIComponent(LANG());
  const r = await fetch(u);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function init() {
  let combos;
  try { combos = await getJSON("/api/combos"); } catch (e) { combos = []; }
  if (!combos.length) { document.body.classList.add("no-data"); return; }
  COMBOS = combos;
  fillCombos();
  const sel = $("combo");
  sel.onchange = () => {
    const combo = JSON.parse(sel.value);
    try { localStorage.setItem(_COMBO_KEY, sel.value); } catch (e) {}
    BASELINE_PINNED = false;   // a new car+track elects its own reference
    SESSION = null;
    SHEET = null;         // another car+track has other braking points
    SESSION_I = 0;        // a different car+track has different sessions
    STINT = null;         // …and different stints, on a different tank
    STINT_I = 0;
    TRAINING = null;      // and its own plan, drills and readiness
    loadCombo(combo);
    if (VIEW === "progress") loadProgress(combo);
    if (VIEW === "session" || VIEW === "recap") loadSession(combo, 0);
    if (VIEW === "stint") loadStint(combo, 0);
    if (VIEW === "training") loadTraining(combo);
  };
  $("lap").onchange = reloadSelection;
  $("baseline").onchange = () => { BASELINE_PINNED = true; reloadSelection(); };
  $("exp-csv").onclick = () => exportData("csv");
  $("exp-json").onclick = () => exportData("json");
  wireTabs();
  wireKeys();
  wireHints();
  wireFlow();
  // Trends still computes the weak points a plan is picked from; the plan
  // itself is one tab away, so it says so and takes you there.
  const goTrain = $("go-training");
  if (goTrain) goTrain.onclick = () => {
    rememberView("training");
    showView("training");
  };
  // Same reason, same shape: the tyre charts left Trends because the span they
  // were drawn over was the whole archive while the heading said "stint".
  const goStint = $("go-stint");
  if (goStint) goStint.onclick = () => {
    rememberView("stint");
    showView("stint");
  };
  // E lo stesso per lo scostamento dalla traiettoria, che era disegnato due
  // volte: qui e in Traiettoria, stesso canale e stessa scala, ma solo là la
  // didascalia dice da che parte.
  const goLine = $("go-line");
  if (goLine) goLine.onclick = () => {
    rememberView("line");
    showView("line");
  };
  // Pick up where you left off — but only if that car+track is still in the
  // archive (a lap store can be moved or cleared between two runs).
  const combo = savedCombo();
  if (combo) sel.value = combo;
  // Prima di `loadCombo`, non dopo: `loadCombo` disegna `renderFlow`/`redraw`
  // in modo sincrono appena il fetch risponde, e quei disegni leggono
  // `cv.clientWidth` — che dipende dalla classe `railed` su <body>. Se
  // scattasse dopo, il primo disegno che un pilota vede (VIEW è ancora
  // quella di partenza marcata `active` in HTML: il caso più comune, prima
  // visita, localStorage vuoto) sarebbe a larghezza piena, senza che nessun
  // ridisegno lo seguisse. Se poi `showView(view)` qui sotto porta su
  // un'altra scheda, richiama da sé `applyRailed` seguita da
  // `redrawCurrentView()`, quindi non va ripetuta dopo.
  applyRailed(VIEW);
  await loadCombo(JSON.parse(sel.value));
  const view = savedView();
  if (view && view !== VIEW) showView(view);
  // No saved view (first visit) or the saved view IS the landing tab: neither
  // branch of `showView` above runs, so nothing else has fetched the session
  // this landing tab depends on. `loadCombo` renders "flow" unconditionally
  // for the same reason — a landing view can't wait for a tab click to load.
  else loadSession(CURRENT, SESSION_I);
  // First visit: pop the tour once data is on screen (so #vmin/#debrief exist).
  if (window.HoneTour) window.HoneTour.auto(tourSteps(), "hone_tour_analysis");
}

// Build the combo dropdown from COMBOS, preserving the current selection so a
// language switch can relabel "laps"/"best" without losing the user's place.
function fillCombos() {
  const sel = $("combo");
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = "";
  for (const c of COMBOS) {
    const o = document.createElement("option");
    o.value = JSON.stringify({ car: c.car, track: c.track });
    o.textContent = `${c.car} · ${c.track}  (${c.laps} ${t("combo.laps")}, ${t("combo.best")} ${c.best})`;
    sel.appendChild(o);
  }
  if (prev) sel.value = prev;
}

// Guided tour (vanilla coachmarks — see tour.js). Selectors are real elements
// in index.html; missing/hidden ones are skipped by the tour engine.
// Built lazily so each step's text follows the active language at start time.
function tourSteps() {
  // `before` puts the step's target on screen. Most of these live in the
  // Compare view, which stopped being the landing tab when the guided flow
  // arrived — without the hook the tour would quietly shrink to the three
  // steps that happened to still be visible.
  const flow = () => showView("flow");
  const compare = () => showView("compare");
  const recap = () => showView("recap");
  return [
    { sel: "#combo", title: t("tour.a1.t"), text: t("tour.a1.x") },
    { sel: ".tabs", title: t("tour.a2.t"), text: t("tour.a2.x") },
    // "Start here" now belongs to the door, not the guided flow — targeted at
    // #recap-phases-sec (the static <section>, not #recap-head or the
    // #recap-phases div it wraps). #recap-head goes empty on a run with
    // nothing measurable yet; #recap-phases starts empty on EVERY run, filled
    // only once loadSession's fetch resolves — and tour.js checks visibility
    // synchronously right after `before()` runs, before that fetch can ever
    // land, so a step pointed at a JS-filled div is always invisible and
    // silently ends the tour. #recap-phases-sec has the h3 already in the
    // markup, so it has height before any JS runs.
    { sel: "#recap-phases-sec", title: t("tour.a12.t"), text: t("tour.a12.x"), before: recap },
    { sel: "#flow-card", title: t("tour.a9.t"), text: t("tour.a9.x"), before: flow },
    { sel: "#train-steps", title: t("tour.a11.t"), text: t("tour.a11.x"),
      before: () => showView("training") },
    { sel: "#c-delta", title: t("tour.a3.t"), text: t("tour.a3.x"), before: compare },
    { sel: "#vmin", title: t("tour.a4.t"), text: t("tour.a4.x"), before: compare },
    { sel: "#debrief", title: t("tour.a5.t"), text: t("tour.a5.x"), before: compare },
    { sel: "#debrief", title: t("tour.a7.t"), text: t("tour.a7.x"), before: compare },
    { sel: "#c-corner", title: t("tour.a10.t"), text: t("tour.a10.x"),
      before: () => showView("line") },
    { sel: "#combo", title: t("tour.a8.t"), text: t("tour.a8.x") },
    { sel: ".export", title: t("tour.a6.t"), text: t("tour.a6.x") },
  ];
}

function wireTour() {
  const btn = document.querySelector(".tour-help");
  if (btn && window.HoneTour) {
    btn.onclick = () => window.HoneTour.start(tourSteps(), "hone_tour_analysis");
  }
}

// Redraw whatever view is on screen from the in-memory payload (no refetch for
// compare; sectors/progress re-run their loader). Shared by resize + the
// colour-blind toggle.
function redrawCurrentView() {
  if (VIEW === "line") { LINE ? renderLine(null) : loadLine(); }
  else if (VIEW === "dynamics") { if (DATA) drawDynamics(LAST_HOVER); }
  else if (VIEW === "sectors") { if (CURRENT) loadSectors(); }
  else if (VIEW === "progress") { if (CURRENT) loadProgress(CURRENT); }
  // Refetched rather than repainted: every word of the programme is written by
  // the backend, so a cached payload would still be in the language you left.
  else if (VIEW === "training") { if (CURRENT) loadTraining(CURRENT); }
  else if (VIEW === "flow") { if (DATA) renderFlow(DATA); }
  // "recap" shares this fetch with "session" — same /api/sessions payload,
  // one carries current.recap and the other carries everything below it.
  else if (VIEW === "session" || VIEW === "recap") { if (CURRENT) loadSession(CURRENT, SESSION_I); }
  // Refetched, like Training: the notes strip is written by the backend in the
  // requested language, so repainting a cached payload would leave the one
  // paragraph on the tab in the language you just left.
  else if (VIEW === "stint") { if (CURRENT) loadStint(CURRENT, STINT_I); }
  // Il Confronto: i grafici a sinistra E la mappa a destra, che stanno sullo
  // stesso schermo e quindi si ridisegnano insieme. Il ramo è nominato invece
  // di restare l'`else` finale muto: era l'`else` a raccogliere anche la vista
  // Mappa quando esisteva, e un ramo senza nome è un ramo che nessuno rilegge.
  // Il resize passa di qui, ed è così che il canvas della mappa riprende la
  // misura della colonna: `setup()` legge `clientWidth` a ogni disegno.
  else if (VIEW === "compare") {
    if (DATA) { redraw(LAST_HOVER); drawMap(DATA, null); }
    SHEET ? renderBrakeSheet(SHEET) : loadBraking();
  }
  // Il rail non appartiene a nessuna vista, quindi non sta in nessun ramo. Fuori
  // dallo switch è l'unico posto dove il cambio scheda e il resize lo trovano
  // entrambi: `redrawCurrentView` è ciò che il gestore di resize (debounced,
  // in fondo al file) chiama, e ciò che `showView` chiama in coda.
  drawRail();
  drawRailList();
}

// Colour-blind palette toggle, dropped next to the tour "?" button. Persisted in
// localStorage and applied before first paint (see top of file); clicking flips
// the body class, reloads the palette and repaints the canvases.
function wireCbToggle() {
  const help = document.querySelector(".tour-help");
  if (!help || !help.parentNode) return;
  if (document.querySelector(".cb-toggle")) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "cb-toggle";
  btn.textContent = "◑";
  const label = () => (window.HoneI18n ? window.HoneI18n.t("cb.label") : "Colour-blind palette");
  btn.title = label();
  btn.setAttribute("aria-label", label());
  btn.setAttribute("aria-pressed", document.body.classList.contains("cb-safe") ? "true" : "false");
  btn.onclick = () => {
    const on = !document.body.classList.contains("cb-safe");
    document.body.classList.toggle("cb-safe", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    try { localStorage.setItem("hone_cb", on ? "1" : "0"); } catch (e) {}
    refreshPalette();
    redrawCurrentView();
  };
  help.parentNode.insertBefore(btn, help.nextSibling);
}

// Le cinque schede che parlano di UN GIRO, e quindi di una curva. Le altre
// cinque stanno sopra il giro nella gerarchia (una sessione, uno stint, lo
// storico, un piano): lì il rail mostrerebbe un giro che non c'entra con quello
// che leggi, e cliccare una curva non cambierebbe niente. Un comando che non
// risponde è peggio di un comando assente.
const RAIL_VIEWS = ["flow", "compare", "line", "sectors", "dynamics"];

// The characters `e.key` reports for the row above the letters, in the order
// a tab picks them — NOT their physical position, which moves between
// keyboard layouts. Every one of these keys sends its printed character
// regardless of layout, with no modifier, so all ten tabs stay reachable
// everywhere. One shared constant — `wireKeys()` reads it to route the
// keypress, `wireTabs()` reads it to show the tooltip — so the two cannot
// drift the way the tab count and this row's length silently did before.
//
// Lunga ESATTAMENTE quanto le schede, non «abbastanza». Il vincolo storico
// chiedeva solo `tabs <= len(KEY_ROW)`, quindi un carattere di troppo sarebbe
// restato verde — e non rompe niente (`wireKeys` fa `if (b)`, `wireTabs` cicla
// sulle schede vere, quindi nessun suggerimento sballato e nessun errore): è
// semplicemente un tasto che il pilota preme e che non fa NIENTE, in silenzio.
// È lo stesso principio per cui il rail non vive sulle schede dove cliccare una
// curva non cambierebbe niente. Con undici schede la riga finiva in "-"; con
// dieci finisce in "0", che è il tasto della decima. Quando torna un'undicesima
// scheda si rimette "-".
const KEY_ROW = "1234567890";

// Non dentro `showView` da sola: al primo caricamento `init()` non ci passa
// affatto quando la vista salvata coincide con quella già attiva in HTML (o
// non ce n'è una salvata), quindi la scheda di partenza — spesso `flow`, che
// ha il rail — restava senza la classe finché non si cliccava un tab
// qualsiasi. Estratta così la chiamano sia `showView` sia `init`.
function applyRailed(name) {
  document.body.classList.toggle("railed", RAIL_VIEWS.indexOf(name) >= 0);
}

// Switch to a view by name, as if its tab had been clicked. Used by the tabs
// themselves and by the "show me the whole chart" button in the guided flow.
function showView(name) {
  VIEW = name;
  for (const x of document.querySelectorAll(".tab")) {
    x.classList.toggle("active", x.dataset.view === name);
  }
  // Derived from the DOM, not from a hand-written list: adding a view used to
  // mean remembering it in three places, and forgetting one leaves two panels
  // stacked on top of each other.
  for (const p of document.querySelectorAll("[id^='view-']")) {
    p.classList.toggle("hidden", p.id !== "view-" + name);
  }
  applyRailed(name);
  redrawCurrentView();
}

// Which tab you were on, and which car and track, across reloads. The page
// reopens a dozen times in an evening — after a lap, after a language switch,
// after the hub relaunches it — and it always came back to the landing tab and
// the first combo in the list, so you re-navigated every time. Stored, never
// trusted: a saved view whose panel no longer exists, or a combo no longer in
// the archive, is ignored rather than left to blank the page.
const _VIEW_KEY = "hone_view", _COMBO_KEY = "hone_combo";

function rememberView(name) {
  try { localStorage.setItem(_VIEW_KEY, name); } catch (e) {}
}

function savedView() {
  let v = null;
  try { v = localStorage.getItem(_VIEW_KEY); } catch (e) {}
  return v && document.getElementById("view-" + v) ? v : null;
}

function savedCombo() {
  let v = null;
  try { v = localStorage.getItem(_COMBO_KEY); } catch (e) {}
  if (!v) return null;
  return [...$("combo").options].some((o) => o.value === v) ? v : null;
}

function wireTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  for (const b of tabs) {
    // The shortcut is on the tooltip because a keyboard shortcut nobody can find
    // is the same as no shortcut. Every tab KEY_ROW can reach gets one shown —
    // it used to stop at the ninth, which silently left the tenth tab's real,
    // working shortcut with no tooltip; now the eleventh would have repeated it.
    const i = tabs.indexOf(b);
    if (i < KEY_ROW.length) b.title = `${t("kbd.tab")} ${KEY_ROW[i]}`;
    b.onclick = () => { rememberView(b.dataset.view); showView(b.dataset.view); };
  }
}

// Where the lap shortcut is written down: on the picker it drives.
function wireHints() {
  const sel = $("lap");
  if (sel) sel.title = t("kbd.lap");
}

// Keyboard: the digit row picks a tab, [ and ] step through this car+track's laps.
// Ignored while a form control has focus — the lap and baseline pickers are
// <select>s, where every key already means something.
function wireKeys() {
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const el = document.activeElement;
    if (el && el.matches("input, select, textarea")) return;
    if (document.querySelector(".tour-pop")) return;   // the tour owns the keys
    const tabs = [...document.querySelectorAll(".tab")];
    // KEY_ROW (module scope, see its own comment) is shared with wireTabs()'s
    // tooltip so the two cannot name two different keys for the same tab.
    if (e.key.length === 1 && KEY_ROW.indexOf(e.key) >= 0) {
      const b = tabs[KEY_ROW.indexOf(e.key)];
      if (b) { e.preventDefault(); b.click(); }
      return;
    }
    if (e.key === "[" || e.key === "]") {
      const sel = $("lap");
      if (!sel || sel.options.length < 2) return;
      const next = sel.selectedIndex + (e.key === "]" ? 1 : -1);
      if (next < 0 || next >= sel.options.length) return;
      e.preventDefault();
      sel.selectedIndex = next;
      sel.onchange();
    }
  });
}

async function loadProgress(combo) {
  setPanelLoading("prog-summary", t("load.trends"));
  let p;
  try { p = await getJSON("/api/progress?" + new URLSearchParams({ car: combo.car, track: combo.track })); }
  catch (e) {
    $("prog-summary").innerHTML = "";
    $("levels").innerHTML = ""; $("trends").innerHTML = "";
    const cs = $("corner-sessions"); if (cs) cs.innerHTML = "";
    $("recurring").innerHTML =
      `<div class="clean">${t("err.progress")}</div>`;
    return;
  }

  const c = p.consistency || {};
  const item = (k, v) => `<div class="item"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  $("prog-summary").innerHTML = c.n
    ? item(t("prog.validLaps"), c.n) + item(t("prog.best"), fmtMs(c.best_ms)) +
      item(t("prog.average"), fmtMs(c.mean_ms)) + item(t("prog.spread"), (c.spread_ms / 1000).toFixed(3) + "s") +
      item(t("prog.sigma"), (c.std_ms / 1000).toFixed(3) + "s")
    : item(t("prog.dash"), t("prog.noValid"));

  drawProgress(p);
  // The tyre charts are drawn by the Race pace tab now, over one tank. They
  // were here, over every lap ever recorded for this car and track, under a
  // heading that said "across the stint" — different evenings, different track
  // temperatures, refuels in between.
  renderLevels(p.levels);
  renderTrends(p.trends);
  renderCornerSessions(p.corner_sessions);
  renderCornerConsistency(p.corner_consistency);

  const el = $("recurring");
  if (!p.recurring.length) {
    el.innerHTML = `<div class="clean">${t("recur.none")}</div>`;
  } else {
    el.innerHTML = p.recurring.map((r) =>
      `<div class="recur"><span class="count">${r.count}×</span>` +
      `<span class="msg">${r.message}</span>` +
      `<span class="where">${t("recur.corners")}${r.corners.join(", ")}</span></div>`).join("");
  }
}

// --- the Training tab ------------------------------------------------------
// The one tab that answers "so what do I actually do?". Everything on it is
// decided server-side (coaching/training.py): which drill, in what order, with
// which of your numbers in it. The code below only draws.
//
// The plan lives here now rather than under Trends. It is the same plan and the
// same storage — what changed is that its goals are no longer listed twice: a
// goal *is* a step, and the step carries the drill that closes it.

let TRAINING = null;

async function loadTraining(combo) {
  setPanelLoading("train-gap", t("load.training"));
  let b;
  try {
    b = await getJSON("/api/training?" +
      new URLSearchParams({ car: combo.car, track: combo.track }));
  } catch (e) {
    TRAINING = null;
    $("train-gap").innerHTML = "";
    $("train-steps").innerHTML = `<div class="clean">${t("err.training")}</div>`;
    $("train-session").innerHTML = "";
    return;
  }
  TRAINING = b;
  renderTraining(b);
}

function renderTraining(b) {
  const gate = $("train-gate");
  if (!gate) return;
  // Not enough laps yet: the whole tab is the sentence that says so, and the
  // panels below are emptied rather than left showing another combo's plan.
  const ready = b && b.ready;
  gate.classList.toggle("hidden", !!ready);
  for (const id of ["train-intro", "train-gap", "plan", "train-steps",
                    "train-session", "train-words"]) {
    const el = $(id);
    if (el) el.classList.toggle("hidden", !ready);
  }
  if (!ready) {
    const r = (b && b.readiness) || {};
    gate.innerHTML = `<h2 class="empty-title">${t("train.locked")}</h2>` +
      `<p class="empty-hint">${r.reason || ""}</p>` +
      (r.laps_needed
        ? `<p class="train-countdown">${r.laps_needed === 1
            ? t("train.countdown1")
            : tf("train.countdown", { n: r.laps_needed })}</p>`
        : "");
    return;
  }

  renderGap(b.gap);
  renderPlanBar(b.plan);
  // The plan's per-goal progress is joined onto its step by corner: the bar
  // that says "2 of the 3 laps it takes" belongs next to the drill that gets
  // you there, not in a second list of the same corners.
  const prog = {};
  for (const g of ((b.plan && b.plan.goals) || [])) {
    if (g.progress) prog[g.corner_index] = g.progress;
  }
  const saved = !!(b.plan && b.plan.saved);
  $("train-steps").innerHTML =
    (b.steps || []).map((s) => trainStep(s, prog[s.corner_index], saved)).join("");
  renderRunPlan(b.session);
  renderWords(b.glossary);
}

// The glossary. Closed it shows the words themselves, not the label "Glossary":
// a driver scanning a row of terms can see whether one of them is a word they
// don't know, and open it for that. A box labelled "Glossary" only says "you
// don't know these things", and gets skipped by exactly the people it's for.
function renderWords(entries) {
  const el = $("train-words");
  if (!el) return;
  if (!entries || !entries.length) { el.innerHTML = ""; return; }
  el.innerHTML =
    `<details class="words"><summary><span class="words-lead">${t("train.words")}</span>` +
    `<span class="words-list">${entries.map((e) => e.term).join(" · ")}</span></summary>` +
    `<dl>${entries.map((e) =>
      `<dt>${e.term}</dt><dd>${e.definition}</dd>`).join("")}</dl></details>`;
}

function renderGap(gap) {
  const el = $("train-gap");
  if (!el) return;
  if (!gap) { el.innerHTML = ""; return; }
  const bars = (gap.sectors || []).map((s) => {
    const worst = s.number === gap.worst_sector;
    return `<div class="gap-sec${worst ? " worst" : ""}">` +
      `<span class="k">${tf("train.sector", { n: s.number })}</span>` +
      `<span class="v">${fmtMs(s.your_ms)}</span>` +
      `<span class="d">${s.gap_ms > 0 ? "−" + (s.gap_ms / 1000).toFixed(3) + "s" : "—"}</span></div>`;
  }).join("");
  el.innerHTML = `<h3>${t("train.gap.title")}</h3>` +
    `<p class="gap-head">${gap.headline}</p>` +
    (bars ? `<div class="gap-secs">${bars}</div>` : "") +
    (gap.note ? `<p class="gap-note">${gap.note}</p>` : "");
}

// The plan's identity strip: since when, on how many laps, and the one button.
function renderPlanBar(plan) {
  const el = $("plan");
  if (!el) return;
  if (!plan || !plan.goals.length) {
    // No systematic weakness is a real answer, and a good one: say it rather
    // than showing an empty box that looks like something failed to load.
    el.innerHTML = `<h3>${t("plan.title")}</h3>` +
      `<div class="clean">${t("plan.none")}</div>`;
    return;
  }
  const head = plan.saved
    ? `<span class="plan-since">${tf("plan.since", { when: fmtWhen(plan.created_utc) })}` +
      (plan.laps_since ? ` · ${tf("plan.laps_since", { n: plan.laps_since })}` : "") + `</span>` +
      `<button type="button" id="plan-drop" class="mini-btn">${t("plan.change")}</button>`
    : `<span class="plan-since">${t("plan.proposed")}</span>` +
      `<button type="button" id="plan-start" class="mini-btn primary">${t("plan.start")}</button>`;
  el.innerHTML = `<h3>${t("plan.title")} ${head}</h3>`;

  const start = $("plan-start");
  if (start) start.onclick = async () => {
    start.disabled = true;
    try {
      await fetch("/api/plan", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ car: CURRENT.car, track: CURRENT.track,
                               goals: plan.goals }),
      });
    } finally { loadTraining(CURRENT); }
  };
  const drop = $("plan-drop");
  if (drop) drop.onclick = async () => {
    drop.disabled = true;
    const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track });
    try { await fetch("/api/plan?" + q.toString(), { method: "DELETE" }); }
    finally { loadTraining(CURRENT); }
  };
}

function trainStep(s, progress, saved) {
  const d = s.drill || {};
  // Only the current step is opened. The others are a heading and a reason —
  // a page that unrolls three drills at once is the list of weak points again.
  const open = s.status === "now";
  const body = open
    ? `<ol class="drill-steps">${(d.steps || []).map((x) => `<li>${x}</li>`).join("")}</ol>` +
      `<div class="drill-focus">` +
      `<span class="watch">👁 ${t("train.watch")} ${d.watch || ""}</span>` +
      `<span class="ignore">✕ ${t("train.ignore")} ${d.ignore || ""}</span></div>` +
      `<div class="drill-done">${s.done_when}</div>` +
      // Only the corner steps are plan goals, so only they carry the plan's
      // own progress. The consistency step is measured against the ideal lap,
      // and borrowing the goal bar for it would report the wrong thing.
      (s.kind === "corner" ? planBar(progress, saved) : "")
    : "";
  return `<article class="train-step ${s.status}">` +
    `<header class="step-head">` +
    `<span class="n">${s.order}</span>` +
    `<span class="where">${s.where || t("train.wholelap")}</span>` +
    `<span class="badge">${t("train.status." + s.status)}</span></header>` +
    (s.what ? `<div class="cause">${s.what}</div>` : "") +
    `<div class="why">${s.why}</div>` +
    `<div class="goal-target">🎯 ${s.target}</div>` +
    (d.title ? `<div class="drill-title"><span class="drill-badge">${tf("train.drill", { n: d.laps })}</span>${d.title}</div>` : "") +
    body + `</article>`;
}

function planBar(p, saved) {
  // The bar fills with laps that met the target, not with time: "2 of the 3
  // laps it takes" is a thing you can act on tonight, a percentage isn't.
  // A plan you haven't accepted has no "since", so it can't be missing laps
  // either: it says what will be measured once you do.
  if (!p) return `<div class="plan-prog muted">${t(saved ? "plan.nolaps" : "plan.willmeasure")}</div>`;
  return `<div class="plan-bar"><span style="width:${Math.min(100, (p.hits / Math.max(1, p.needed)) * 100).toFixed(0)}%"></span></div>` +
    `<div class="plan-prog">${tf("plan.hits", { hits: p.hits, needed: p.needed })}` +
    ` · ${tf("plan.now", { s: p.median_s.toFixed(2) })}` +
    ` · ${tf("plan.best", { s: p.best_s.toFixed(2) })}</div>`;
}

// `renderRunPlan`, not `renderSession`: the Session tab already owns that name,
// and a second declaration of it silently replaced the first — the run plan
// simply never appeared, with nothing in the console to say so.
function renderRunPlan(ses) {
  const el = $("train-session");
  if (!el) return;
  if (!ses) { el.innerHTML = ""; return; }
  el.innerHTML = `<h3>${t("train.session")} <small>${tf("train.session.laps", { n: ses.laps })}</small></h3>` +
    `<ol class="ses-plan">${(ses.lines || []).map((x) => `<li>${x}</li>`).join("")}</ol>`;
}

// Benchmark ladder: best -> ideal (consistency) -> PRO (skill ceiling).
function renderLevels(levels) {
  const el = $("levels");
  if (!el) return;
  if (!levels || !levels.length) { el.innerHTML = ""; return; }
  let rows = "";
  for (const lv of levels) {
    let gap;
    if (lv.key === "best") {
      gap = `<span class="lvl-gap base">${t("lvl.yourRef")}</span>`;
    } else if (lv.gain_s > 0) {
      const hint = lv.key === "ideal" ? t("lvl.consistency") : t("lvl.gapPro");
      gap = `<span class="lvl-gap faster">−${lv.gain_s.toFixed(3)}s</span>` +
            `<span class="lvl-hint">${hint}</span>`;
    } else {
      const ahead = Math.abs(lv.gain_s).toFixed(3);
      gap = `<span class="lvl-gap done">${t("lvl.beaten")}</span>` +
            `<span class="lvl-hint">+${ahead}s ${t("lvl.vsPro")}</span>`;
    }
    rows += `<div class="lvl" data-key="${lv.key}">` +
      `<span class="lvl-label">${lv.label}</span>` +
      `<span class="lvl-time">${lv.lap_time}</span>` +
      gap + `</div>`;
  }
  el.innerHTML = `<h3>${t("lvl.header")}</h3>` +
    `<div class="ladder">${rows}</div>`;
}

// Per-corner weaknesses: systematic (train it) vs sporadic (one-off).
function renderTrends(trends) {
  const el = $("trends");
  if (!el) return;
  if (!trends || !trends.length) {
    el.innerHTML = `<div class="clean">${t("trends.none")}</div>`;
    return;
  }
  // NB: local var renamed to `w` so it doesn't shadow the global `t` (translate).
  el.innerHTML = trends.map((w) => {
    const sys = w.systematic;
    const badge = sys
      ? `<span class="wk-badge on">${t("badge.systematic")}</span>`
      : `<span class="wk-badge off">${t("badge.sporadic")}</span>`;
    const tag = sys ? t("trends.toTrain") : t("trends.oneOff");
    return `<div class="weak ${sys ? "sys" : ""}">` +
      `<div class="weak-head">` +
      `<span class="corner">${w.name}</span>${badge}` +
      `<span class="lost">−${w.total_s.toFixed(3)}s</span></div>` +
      `<div class="detail">${tag} · ` +
      `${t("trends.median")} −${w.median_s.toFixed(3)}s · ${w.occurrences}/${w.laps} ${t("lbl.laps")}</div>` +
      `</div>`;
  }).join("");
}

// La stessa curva, sessione per sessione: dove stavi e dove sei. Ogni punto è
// una mediana su un'uscita — le sessioni senza abbastanza giri su quella curva
// non ci sono, invece di essere disegnate a zero (uno zero vuol dire "presa
// bene", ed è la bugia più facile da disegnare qui).
function renderCornerSessions(rows) {
  const el = $("corner-sessions");
  if (!el) return;
  if (!rows || !rows.length) {
    el.innerHTML = `<div class="clean">${t("ses.none")}</div>`;
    return;
  }
  el.innerHTML = rows.map((r) => {
    let mx = 0.05;
    for (const p of r.points) mx = Math.max(mx, p.median_s);
    const first = r.points[0].median_s, last = r.points[r.points.length - 1].median_s;
    const delta = first - last;
    const verdict = delta === 0 ? "" :
      `<span class="ses-verdict ${delta > 0 ? "better" : "worse"}">` +
      `${Math.abs(delta).toFixed(3)}s ${delta > 0 ? t("ses.better") : t("ses.worse")}</span>`;
    const bars = r.points.map((p) => {
      const w = (Math.min(p.median_s / mx, 1) * 100).toFixed(0);
      const day = (p.started || "").slice(0, 10);
      const hm = (p.started || "").slice(11, 16);
      return `<div class="ses-row">` +
        `<span class="ses-when">${day} ${hm}</span>` +
        `<span class="ses-track"><span class="ses-fill" style="width:${w}%"></span></span>` +
        `<span class="ses-nums">−${p.median_s.toFixed(3)}s · ${p.laps} ${t("ses.laps")}</span>` +
        `</div>`;
    }).join("");
    return `<div class="weak sys"><div class="weak-head">` +
      `<span class="corner">${r.name}</span>${verdict}</div>${bars}</div>`;
  }).join("");
}

// Per-corner consistency: a spread bar per corner (min-speed range across the
// recent laps), worst-first. Wide bar = a corner you don't repeat — where to
// work on rhythm, distinct from the systematic time-loss the weak-points list
// already flags.
function renderCornerConsistency(rows) {
  const el = $("corner-consistency");
  if (!el) return;
  if (!rows || !rows.length) {
    el.innerHTML = `<div class="clean">${t("cons.none")}</div>`;
    return;
  }
  let mx = 0.1;
  for (const r of rows) mx = Math.max(mx, r.spread_kmh);
  el.innerHTML = rows.map((r) => {
    const w = (Math.min(r.spread_kmh / mx, 1) * 100).toFixed(0);
    return `<div class="cons-row">` +
      `<span class="corner">${r.name}</span>` +
      `<span class="cons-track"><span class="cons-fill" style="width:${w}%"></span></span>` +
      `<span class="cons-nums">${t("cons.spread")} <b>${r.spread_kmh.toFixed(1)}</b> km/h · ` +
      `σ ${r.std_kmh.toFixed(1)} · ${r.n} ${t("lbl.laps")}</span>` +
      `</div>`;
  }).join("");
}

function drawProgress(p) {
  const { ctx, w, h } = setup($("c-progress"));
  const laps = p.laps;
  if (!laps.length) return;
  const times = laps.map((l) => l.lap_time_ms);
  const realLo = Math.min(...times), realHi = Math.max(...times);
  let lo = realLo, hi = realHi;
  if (hi === lo) hi = lo + 1000;
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const n = laps.length;
  const X = (i) => (n === 1 ? w / 2 : (i / (n - 1)) * (w - 20) + 10);
  const Y = (t) => ((t - lo) / (hi - lo)) * (h - 20) + 10;  // best near the top

  let m = Infinity; const rb = times.map((t) => (m = Math.min(m, t)));
  ctx.beginPath();
  for (let i = 0; i < n; i++) { const x = X(i), y = Y(times[i]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.strokeStyle = "rgba(255,255,255,0.25)"; ctx.lineWidth = 1; ctx.stroke();
  ctx.beginPath();
  for (let i = 0; i < n; i++) { const x = X(i), y = Y(rb[i]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.strokeStyle = "#22dd66"; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = "#ffffff";
  for (let i = 0; i < n; i++) { ctx.beginPath(); ctx.arc(X(i), Y(times[i]), 3, 0, 6.283); ctx.fill(); }

  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px " + MONO;
  ctx.fillText(fmtMs(realLo), w - 70, Y(realLo) - 4);
  ctx.fillText(fmtMs(realHi), w - 70, Y(realHi) + 12);
}

// --- tyres over time ------------------------------------------------------
// Four wheels, encoded axle-by-colour + side-by-dash so it stays readable for
// colour-blind users (front = cyan, rear = amber; left solid, right dashed).
const TYRE_SERIES = [
  { key: "fl", color: "#22D3CE", dash: [] },
  { key: "fr", color: "#22D3CE", dash: [5, 4] },
  { key: "rl", color: "#FFB020", dash: [] },
  { key: "rr", color: "#FFB020", dash: [5, 4] },
];

function drawTyres(p) {
  const sec = $("tyres");
  if (!sec) return;
  const tyres = (p && p.tyres) || [];
  const anyTemp = tyres.some((l) => l.temp);
  const anyPress = tyres.some((l) => l.press);
  if (!tyres.length || (!anyTemp && !anyPress)) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");

  // Legend: a short line sample (dashed for the right-side wheels) + label.
  $("tyre-legend").innerHTML = TYRE_SERIES.map((s) =>
    `<span class="tl"><span class="sw" style="border-top:2px ${s.dash.length ? "dashed" : "solid"} ${s.color}"></span>` +
    `${t("tyre." + s.key)}</span>`).join("");

  $("tyre-temp-wrap").classList.toggle("hidden", !anyTemp);
  $("tyre-press-wrap").classList.toggle("hidden", !anyPress);
  if (anyTemp) drawTyreLines($("c-tyre-temp"), tyres, "temp", 0, "°");
  if (anyPress) drawTyreLines($("c-tyre-press"), tyres, "press", 1, "");

  // Drift readout: per-axle change from the first to the last lap that carries
  // data (the heat build-up / pressure creep a driver feels over a stint).
  const firstT = tyres.find((l) => l.temp), lastT = [...tyres].reverse().find((l) => l.temp);
  const firstP = tyres.find((l) => l.press), lastP = [...tyres].reverse().find((l) => l.press);
  const axle = (v, a, b) => (v[a] + v[b]) / 2;
  const sgn = (x, d, u) => (x >= 0 ? "+" : "") + x.toFixed(d) + u;
  const bits = [];
  if (firstT && lastT && firstT !== lastT) {
    const df = axle(lastT.temp, 0, 1) - axle(firstT.temp, 0, 1);
    const dr = axle(lastT.temp, 2, 3) - axle(firstT.temp, 2, 3);
    bits.push(`<b>${t("tyre.tempLabel")}</b> ${t("tyre.front")} ${sgn(df, 0, "°")} · ${t("tyre.rear")} ${sgn(dr, 0, "°")}`);
  }
  if (firstP && lastP && firstP !== lastP) {
    const df = axle(lastP.press, 0, 1) - axle(firstP.press, 0, 1);
    const dr = axle(lastP.press, 2, 3) - axle(firstP.press, 2, 3);
    bits.push(`<b>${t("tyre.pressLabel")}</b> ${t("tyre.front")} ${sgn(df, 1, "")} · ${t("tyre.rear")} ${sgn(dr, 1, "")} psi`);
  }
  $("tyre-drift").innerHTML = bits.length
    ? `<span class="muted">${t("tyre.driftLead")}:</span> ${bits.join("  ·  ")}`
    : "";
}

// One tyre chart: four wheel lines over the laps that carry ``field`` (temp or
// press). Returns false and leaves the canvas blank if no lap has the channel.
function drawTyreLines(cv, tyres, field, digits, unit) {
  const { ctx, w, h } = setup(cv);
  const pts = [];
  tyres.forEach((l, i) => { if (l[field]) pts.push({ i, v: l[field] }); });
  if (!pts.length) return false;
  let lo = Infinity, hi = -Infinity;
  for (const p of pts) for (const v of p.v) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const rlo = lo, rhi = hi;
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.15; lo -= pad; hi += pad;
  const n = tyres.length;
  const X = (i) => (n === 1 ? w / 2 : (i / (n - 1)) * (w - 46) + 10);
  const Y = (v) => h - (((v - lo) / (hi - lo)) * (h - 24) + 12);

  TYRE_SERIES.forEach((s, wi) => {
    ctx.beginPath();
    ctx.setLineDash(s.dash);
    let started = false;
    for (const p of pts) {
      const x = X(p.i), y = Y(p.v[wi]);
      started ? ctx.lineTo(x, y) : ctx.moveTo(x, y); started = true;
    }
    ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = s.color;
    for (const p of pts) { ctx.beginPath(); ctx.arc(X(p.i), Y(p.v[wi]), 2.5, 0, 6.283); ctx.fill(); }
  });

  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px " + MONO;
  ctx.fillText(rhi.toFixed(digits) + unit, w - 44, Y(rhi) + 10);
  ctx.fillText(rlo.toFixed(digits) + unit, w - 44, Y(rlo) - 3);
  return true;
}

// --- sectors --------------------------------------------------------------
function fmtSec(ms) {
  if (ms == null) return "--";
  const m = Math.floor(ms / 60000);
  const s = (ms % 60000) / 1000;
  return m ? `${m}:${s.toFixed(3).padStart(6, "0")}` : s.toFixed(3);
}

async function loadSectors() {
  if (!CURRENT) return;
  const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track });
  const lap = $("lap").value, base = pinnedBaseline();
  if (lap) q.set("lap", lap);
  if (base) q.set("baseline", base);
  $("sectors").innerHTML = `<div class="muted">${t("load.sectors")}</div>`;
  let s;
  try { s = await getJSON("/api/sectors?" + q.toString()); }
  catch (e) {
    $("sectors").innerHTML = `<div class="muted">${e.message}</div>`;
    $("ideal").innerHTML = ""; $("sec-table").innerHTML = "";
    return;
  }
  drawSectors(s);
}

function drawSectors(s) {
  // Lap / reference / gap moved to the lap bar, on every tab. What was left of
  // this view's own summary was one fact — whether these splits are the sim's
  // own sectors or our thirds — and a whole banner to say it in. It belongs on
  // the column it describes.
  const kind = $("sec-kind");
  if (kind) kind.textContent = s.real ? t("sec.real") : t("sec.thirds");

  // Diverging delta bars, scaled to the worst sector (min 0.05s).
  let mx = 0.05;
  for (const sec of s.sectors) mx = Math.max(mx, Math.abs(sec.delta_ms) / 1000);
  const half = 50; // % of the bar track for one side
  let rows = "";
  for (const sec of s.sectors) {
    const d = sec.delta_ms / 1000;
    const slower = d > 0;
    const w = (Math.min(Math.abs(d) / mx, 1) * half).toFixed(1);
    const fill = slower
      ? `<div class="fill slow" style="left:50%;width:${w}%"></div>`
      : `<div class="fill fast" style="right:50%;width:${w}%"></div>`;
    rows += `<div class="secrow">` +
      `<div class="seclabel">S${sec.index + 1}${sec.is_best ? ' <span class="star">★</span>' : ""}</div>` +
      `<div class="sectimes"><b>${fmtSec(sec.review_ms)}</b> <span class="muted">${fmtSec(sec.baseline_ms)}</span></div>` +
      `<div class="secbar"><div class="mid"></div>${fill}` +
      `<span class="secd ${slower ? "slower" : "faster"}">${d >= 0 ? "+" : ""}${d.toFixed(3)}</span></div>` +
      `</div>`;
  }
  $("sectors").innerHTML = rows;

  if (s.ideal) {
    const lapTime = (p) => {
      const l = (s.laps || []).find((x) => x.path === p);
      return l ? l.lap_time : "?";
    };
    const gain = s.ideal.gain_ms / 1000;
    const from = s.ideal.best_from
      .map((p, i) => `S${i + 1} ← <b>${lapTime(p)}</b>`).join(" · ");
    $("ideal").innerHTML =
      `<h3>${t("ideal.title")}</h3>` +
      `<div class="ideal-time">${s.ideal.ideal}` +
      (gain > 0 ? ` <span class="faster">${t("ideal.potential")} −${gain.toFixed(3)}s</span>` : "") +
      `</div><div class="ideal-from">${from}</div>` +
      `<div class="muted small">${t("ideal.from")}</div>`;
  } else {
    $("ideal").innerHTML = "";
  }
  drawSectorTable(s);
}

// Every lap of this car+track, sector by sector, best of each column marked.
//
// The ideal lap above says a 2:03.412 is in there somewhere; this is where you
// see *which* laps it is made of — and whether the sector you're proud of was
// one good lap or a habit. Same numbers as the ideal (the backend times every
// lap against the same spans), so the star here and the "S2 ← 2:03.732" up
// there can't disagree.
function drawSectorTable(s) {
  const el = $("sec-table");
  if (!el) return;
  const rows = (s.per_lap || []);
  // One lap is not a table: with nothing to compare, the bars above already say
  // everything this would.
  if (rows.length < 2) { el.innerHTML = ""; return; }
  const n = s.n;
  const best = [];
  for (let i = 0; i < n; i++) best.push(Math.min(...rows.map((r) => r.ms[i])));
  let body = "";
  for (const r of rows) {
    const clock = lapClock(r.recorded_utc);
    const mark = r.path === s.review.path ? " on" : "";
    const off = r.off_track ? ` <span class="off-track" title="${t("lap.offTrack.why")}">${t("lap.offTrack")}</span>` : "";
    body += `<tr class="${mark.trim()}"><td class="vc">${r.lap_time}${off}` +
      (clock ? ` <span class="muted">${clock}</span>` : "") + `</td>` +
      r.ms.map((v, i) =>
        `<td class="vn${v === best[i] ? " best" : ""}">${fmtSec(v)}</td>`).join("") +
      `</tr>`;
  }
  let head = `<th>${t("sec.t.lap")}</th>`;
  for (let i = 0; i < n; i++) head += `<th>S${i + 1}</th>`;
  el.innerHTML =
    `<h3>${t("sec.t.title")}</h3>` +
    `<table class="vmin-table wide"><thead><tr>${head}</tr></thead>` +
    `<tbody>${body}</tbody></table>` +
    `<div class="muted small">${t("sec.t.hint")}</div>`;
}

// --- track map ------------------------------------------------------------
// The p-th percentile of |vals|, clamped to [lo, hi]. Used to scale the map
// heatmap so outliers (a spin's huge speed gap) don't collapse the colour range.
function robustScale(vals, p, lo, hi) {
  const a = [];
  for (const v of vals) a.push(Math.abs(v || 0));
  if (!a.length) return lo;
  a.sort((x, y) => x - y);
  const q = a[Math.min(a.length - 1, Math.floor((p / 100) * a.length))];
  return Math.max(lo, Math.min(hi, q));
}

function deltaColor(d, m) {
  // slower (d>0) -> Delta Red, faster (d<0) -> Delta Green, near-zero -> pale.
  // Colour is doubled up with segment width (see drawMap) so the read survives
  // red/green colour-blindness — the line gets THICKER the bigger the gap.
  const t = Math.max(-1, Math.min(1, d / (m || 1)));
  // Near-zero delta is neutral grey, not a faint "slower" tint: a segment where
  // you neither gain nor lose shouldn't read as a (tiny) loss.
  if (Math.abs(t) < 0.04) return "rgb(150,156,166)";
  // Interpolate pale -> the active palette colour (slow/fast), so the colour-
  // blind toggle changes this too. Colour is doubled with width (see drawMap).
  const c = t > 0 ? PAL.slow : PAL.fast;
  const f = Math.abs(t), pale = 235;
  const mix = (x) => Math.round(pale + (x - pale) * f);
  return `rgb(${mix(c[0])},${mix(c[1])},${mix(c[2])})`;
}

// Balance ribbon palette: understeer (v<0) = blue, oversteer (v>0) = red,
// near-neutral = pale grey. Distinct hues (not red/green) so it reads on its own.
function balanceColor(v) {
  const x = Math.max(-1, Math.min(1, v || 0));
  if (Math.abs(x) < 0.06) return "rgb(150,156,166)";
  const c = x > 0 ? [255, 90, 60] : [88, 150, 255];
  const f = Math.abs(x), pale = 210;
  const mix = (k) => Math.round(pale + (k - pale) * f);
  return `rgb(${mix(c[0])},${mix(c[1])},${mix(c[2])})`;
}

// The road as the game's own collision model has it: one closed ring per piece
// of surface, already cropped to this corner (see trackmesh.py). Asphalt first,
// then the kerbs on top of it — which is the order they exist in.
//
// The kerbs are the reason this is worth the trouble. They are the thing a
// driver aims at, and no amount of widening a racing line invents one.
// Nell'ordine in cui stanno per terra: prima le vie di fuga, poi la pista che ci
// sta sopra, poi i cordoli che stanno sopra la pista. I colori sono spenti
// apposta — devono dire "qui non sei più in pista" senza rubare l'occhio alle
// due linee, che restano la ragione per cui si guarda questo disegno.
//
// L'asfalto però era spento *troppo*: bianco al 15% sotto un'erba al 30% e dei
// cordoli al 55%, cioè la cosa meno visibile del disegno era il suo soggetto —
// al Red Bull Ring non si capiva dove finisse la strada. Adesso è un grigio
// neutro abbastanza sostenuto da leggersi come suolo, e resta comunque sotto la
// linea guidata e il riferimento, che sono opachi.
// L'ordine è quello in cui le superfici stanno per terra, e deve combaciare con
// `trackmesh.DRAW_ORDER` — un test tiene allineate le due liste, perché sono
// due copie della stessa decisione in due linguaggi.
const SURFACE_PAINT = [
  ["grass",    "rgba(74,124,89,0.30)"],
  ["gravel",   "rgba(176,146,96,0.30)"],
  ["concrete", "rgba(150,155,165,0.20)"],
  // Più spenta dell'asfalto: la corsia box è accanto alla pista, non è pista, e
  // dipinta uguale farebbe sembrare il tracciato largo il doppio dove si stacca.
  ["pitlane",  "rgba(150,155,165,0.16)"],
  ["road",     "rgba(188,196,208,0.34)"],
  ["kerb",     "rgba(226,86,96,0.55)"],
];

function drawSurfaces(ctx, shapes, X, Y) {
  const fill = (rings, colour) => {
    if (!rings || !rings.length) return;
    ctx.beginPath();
    for (const ring of rings) {
      ring.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1]))
                                : ctx.moveTo(X(p[0]), Y(p[1]))));
      ctx.closePath();
    }
    ctx.fillStyle = colour;
    // Even-odd, so a piece of surface with a hole in it — the infield of a
    // hairpin — comes out with the hole instead of filled solid.
    ctx.fill("evenodd");
  };
  ctx.save();
  for (const [key, colour] of SURFACE_PAINT) fill(shapes[key], colour);
  ctx.restore();
}

// The asphalt, from the game's own track data (see trackedges.py). Filled dark
// and edged with a hairline: the ribbon has to read as GROUND, not as a third
// racing line competing with the two drawn on top of it.
//
// ``road.runs`` is a list because the track data can have holes in it — where it
// does, the ribbon has to stop rather than join up across them.
function drawRoad(ctx, road, X, Y, hair) {
  if (!road || !Array.isArray(road.runs)) return;
  ctx.save();
  // The surface is laid down as one quad per step, all in a single path filled
  // once. Tracing the two edges as one big outline instead looks simpler and
  // isn't: on a hairpin the inner edge folds back through itself, and on a
  // closed circuit the shape has to be an annulus rather than a polygon. A
  // strip of quads has neither problem — overlaps merge, and the fill is the
  // ground actually covered.
  ctx.beginPath();
  for (const r of road.runs) {
    for (let i = 1; i < r.left.length; i++) {
      const a = r.left[i - 1], b = r.left[i], c = r.right[i], d = r.right[i - 1];
      ctx.moveTo(X(a[0]), Y(a[1]));
      ctx.lineTo(X(b[0]), Y(b[1]));
      ctx.lineTo(X(c[0]), Y(c[1]));
      ctx.lineTo(X(d[0]), Y(d[1]));
      ctx.closePath();
    }
  }
  // Misurato: al 6% su un pannello #151A21 l'asfalto sposta il fondo di 14
  // livelli su 255 — c'e' ma non LEGGE come una strada, e il disegno resta
  // "due linee nel vuoto" invece di "una pista vista dall'alto".
  ctx.fillStyle = "rgba(255,255,255,0.14)";
  ctx.fill();
  // Each run is stroked on its own and never closed: where the track data has a
  // hole the ribbon stops, instead of taking a shortcut across the circuit.
  ctx.strokeStyle = "rgba(255,255,255,0.55)";
  ctx.lineWidth = hair;
  for (const r of road.runs) {
    for (const side of [r.left, r.right]) {
      ctx.beginPath();
      side.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1]))
                                : ctx.moveTo(X(p[0]), Y(p[1]))));
      ctx.stroke();
    }
  }
  ctx.restore();
}

// Full track map (the right-hand column of Compare). Wrapper around drawMapTo
// that also publishes the screen transform for the map's own hover.
function drawMap(a, cx) {
  const hit = drawMapTo($("c-map"), $("map-missing"), a, cx);
  if (hit) MAP_HIT = hit;
  // The readout and the legend describe the drawing, and they are NOT inside
  // the canvas — they are sibling elements in the column (see index.html) —
  // so drawMapTo() turning the canvas off does nothing for them. Without this
  // they stayed lit above `#map-missing`, captioning a picture that wasn't
  // there. The h3 title is left alone on purpose: it names the column, and
  // reads as a heading with the reason underneath once these two are gone.
  const ro = $("map-readout");
  if (ro) ro.classList.toggle("hidden", !a.has_map);
  const legend = $("map-legend");
  if (legend) legend.classList.toggle("hidden", !a.has_map);
  // The cross is on the drawing only on a lap that was actually thrown away. A
  // legend entry for a mark that isn't there sends the reader hunting for it,
  // so the entry comes and goes with the mark.
  const lost = $("leg-lost");
  if (lost) lost.classList.toggle("hidden", a.review.lost_at == null);
  // Il readout si scrive QUI, non in ognuno dei chiamanti (`loadCombo`,
  // `redrawCurrentView`, `hoverTo`): la pastiglia della finestra mancava a
  // riposo sul disegno del giro perché due dei tre la anteponevano da soli e il
  // terzo — il cambio scheda, che passa da `redrawCurrentView` a `drawMap`
  // senza toccare il readout — no. La stessa forma del difetto già chiuso per
  // `hoverTo`: se la pastiglia va scritta a mano in N punti, il punto N+1 se
  // la dimentica. Scritta una sola volta, dentro la funzione che disegna la
  // mappa, nessun chiamante può più dimenticarla.
  if (ro) { ro.innerHTML = mapReadoutHTML(cx); wireRangeClear(ro); }
}

// La mappa del rail. Sempre a GIRO INTERO, anche con la finestra accesa: il rail
// è il «dove sono», e uno zoom lo trasformerebbe in una seconda copia del
// grafico che stai già guardando. La finestra si legge come un tratto acceso.
let RAIL_HIT = null;   // {rv, X, Y}, il trasformo schermo, per l'hover

// `p` di default è `LAST_HOVER`: chi ridisegna la vista intera (cambio scheda,
// resize, nuovo giro) non ha un punto fresco in mano e vuole l'ultimo noto. Chi
// invece risponde a un hover vero (`hoverTo`) passa il punto esplicito — così il
// mirino del rail non dipende dall'ordine in cui `LAST_HOVER` viene scritto.
function drawRail(p = LAST_HOVER) {
  // Su una scheda senza rail il canvas ha larghezza zero e `setup` disegnerebbe
  // su una tela di 0 px: lavoro sprecato, e un hit test tarato su niente.
  //
  // La classe `railed` da sola non basta a saperlo: sotto i 1100px
  // (style.css) `.rail` torna `display: none` per un vincolo di spazio, ma la
  // classe sul <body> resta — dipende dalla scheda, non dalla finestra. Senza
  // il controllo sulla larghezza vera, ogni cambio scheda e ogni resize sotto
  // quella soglia disegnavano comunque, su una tela 0×0.
  if (!DATA || !document.body.classList.contains("railed")) return;
  if (!$("rail") || !$("rail").offsetWidth) return;
  RAIL_HIT = drawMapTo($("c-rail"), $("rail-nomap"), DATA, p);
  if (RAIL_HIT && RANGE) railWindow(RAIL_HIT);
}

// Il tratto scelto, acceso sopra la mappa già disegnata. Ridisegnare con lo
// stesso contesto è legittimo: `setup` lascia sul canvas la trasformazione del
// device pixel ratio, e `X`/`Y` restituiti da `drawMapTo` sono in pixel CSS —
// gli stessi in cui si ragiona qui.
function railWindow(hit) {
  const ctx = $("c-rail").getContext("2d");
  const rv = hit.rv;
  ctx.save();
  ctx.strokeStyle = "#22D3CE"; ctx.lineWidth = 4;
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < rv.x.length; i++) {
    const p = rv.pos[i];
    if (p < RANGE.from || p > RANGE.to) { started = false; continue; }
    const px = hit.X(rv.x[i]), py = hit.Y(rv.z[i]);
    started ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    started = true;
  }
  ctx.stroke();
  ctx.restore();
}

// Le curve del rail in due gruppi. Sopra la classifica — chi è costato di più,
// per primo: è il waterfall promosso a navigazione, l'unica cosa in tutta l'app
// che mostri la DISTRIBUZIONE della perdita invece di una conclusione. Sotto, in
// ordine di pista e senza barretta, le curve dove non hai perso niente: un
// selettore che non le elenca non è un selettore, è una classifica.
function railRows(a) {
  const byIndex = new Map();
  for (const l of (a.losses || [])) if (l.lost_s > 0) byIndex.set(l.index, l);
  const hot = Array.from(byIndex.values()).sort((x, y) => y.lost_s - x.lost_s);
  const cold = (a.corners || []).filter((c) => !byIndex.has(c.index));
  return { hot: hot, cold: cold };
}

function drawRailList() {
  const el = $("rail-list");
  if (!el || !DATA) return;
  const corners = DATA.corners || [];
  const at = (i) => corners.filter((c) => c.index === i)[0];
  const rows = railRows(DATA);
  let mx = 0.05;
  for (const l of rows.hot) mx = Math.max(mx, l.lost_s);
  const sel = RANGE && RANGE.corner != null ? RANGE.corner : null;

  // «Tutto il giro» è il primo elemento e non uno stato assente: finché non è
  // scritto, tornare indietro dalla curva sembra impossibile.
  let html = `<button type="button" class="rail-row whole${RANGE ? "" : " on"}" data-whole="1">` +
             `${t("rail.whole")}</button>`;
  for (const l of rows.hot) {
    const w = (Math.min(l.lost_s / mx, 1) * 100).toFixed(0);
    const sev = Math.min(1, l.lost_s / Math.max(mx, 0.3));
    html += `<button type="button" class="rail-row${sel === l.index ? " on" : ""}" ` +
            `data-i="${l.index}" title="${escAttr(l.message || "")}">` +
            `<span class="n">T${l.index + 1}</span>` +
            `<span class="nm">${l.label}</span>` +
            `<span class="bar"><span class="fill" style="width:${w}%;` +
            `background:${lossColor(sev)}"></span></span>` +
            `<span class="s">−${l.lost_s.toFixed(2)}</span></button>`;
  }
  if (rows.cold.length && rows.hot.length) {
    html += `<div class="rail-sep">${t("rail.clean")}</div>`;
  }
  for (const c of rows.cold) {
    html += `<button type="button" class="rail-row cold${sel === c.index ? " on" : ""}" ` +
            `data-i="${c.index}"><span class="n">T${c.index + 1}</span>` +
            `<span class="nm">${c.name}</span></button>`;
  }
  el.innerHTML = html;

  for (const b of el.querySelectorAll(".rail-row[data-i]")) {
    b.onclick = () => {
      const c = at(parseInt(b.dataset.i, 10));
      if (!c) return;
      setRange(cornerWindow(c));
      redrawCurrentView();
    };
  }
  const whole = el.querySelector(".rail-row[data-whole]");
  if (whole) whole.onclick = () => { setRange(null); redrawCurrentView(); };
}

// Render the delta-coloured racing line + braking points to ``canvas``; returns
// the screen transform {rv, X, Y} so a hover can map cursor → nearest sample,
// or null when there's no map. ``missing`` (optional) is a placeholder element
// to toggle when the lap has no coordinates.
function drawMapTo(canvas, missing, a, cx, mode) {
  mode = mode || "delta";
  if (!canvas) return null;
  if (!a.has_map) {
    if (missing) missing.classList.remove("hidden");
    canvas.style.display = "none";
    return null;
  }
  if (missing) missing.classList.add("hidden");
  canvas.style.display = "";

  const { ctx, w, h } = setup(canvas);
  const rv = a.review.channels, rf = a.reference.channels;
  const d = a.review.delta;

  // Fit both lines into the canvas, equal scale (true geometry), 24px margin.
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  const scan = (xs, zs) => {
    for (let i = 0; i < xs.length; i++) {
      minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i]);
      minZ = Math.min(minZ, zs[i]); maxZ = Math.max(maxZ, zs[i]);
    }
  };
  scan(rv.x, rv.z); scan(rf.x, rf.z);
  const m = 24, spanX = maxX - minX || 1, spanZ = maxZ - minZ || 1;
  const s = Math.min((w - 2 * m) / spanX, (h - 2 * m) / spanZ);
  const offX = (w - spanX * s) / 2, offZ = (h - spanZ * s) / 2;
  // AC/ACC world coordinates are left-handed, so a raw top-down (x, -z) view
  // comes out mirrored left-right (Suzuka T1 would bend the wrong way). Flip X
  // too so the map matches what you see from the cockpit. Braking points, start
  // and the hover marker all go through X()/Y(), so they stay in register.
  const X = (x) => (maxX - x) * s + offX;
  const Y = (z) => h - ((z - minZ) * s + offZ);   // flip so +z is up

  // NO ASPHALT HERE, and it is a decision rather than an omission. Drawing the
  // road under the whole lap was tried on 2026-08-04 and taken straight back
  // out: at this zoom the fit is 0.869 px per metre, so the Red Bull Ring's
  // 11.9 m of track is 10.3 px — and the reviewed line is 2 to 7 px wide,
  // because its thickness carries the speed gap. A line two thirds as wide as
  // the road, centred on a racing line that uses the kerb, spills past a road
  // drawn to scale, and the picture says the car was off the track on corners
  // where it measurably was not (0-2% of samples outside the ribbon, worst
  // 0.4 m).
  //
  // The zoomed corner keeps its asphalt because there the scale is real: a
  // corner fills the box and the line is a thread across it. Same rule as the
  // magnified gap — a drawing that overstates is worse than one that omits.

  // Reference racing line: faint dashed.
  ctx.save();
  ctx.setLineDash([5, 4]);
  ctx.strokeStyle = "rgba(255,255,255,0.4)"; ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < rf.x.length; i++) {
    const px = X(rf.x[i]), py = Y(rf.z[i]);
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke();
  ctx.restore();

  // Your line: in "delta" mode colour each segment by the delta AND scale its
  // width by |delta| (thicker = more time lost, so the read survives red/green
  // colour-blindness). In "balance" mode colour by handling (blue understeer /
  // red oversteer) at constant width — the balance ribbon.
  const bal = rv.balance || [];
  // Heatmap signal: the LOCAL speed gap vs the reference at each point (km/h),
  // + = faster here, - = slower. Not the cumulative time delta — that only grows
  // through the lap and washed the whole first half to near-white. Scale to the
  // biggest gap on this lap (floored so a near-identical lap doesn't saturate).
  const sd = d.speed_delta || [];
  // Robust scale: the 90th percentile of |gap|, clamped to a sane km/h band, so a
  // single spike (a spin can read -150 km/h vs the reference) can't wash the whole
  // lap out the way scaling to the raw max did — the outlier just clamps to full
  // red while normal corner gaps still span the gradient.
  const mx = robustScale(sd, 90, 12, 45);
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (let i = 1; i < rv.x.length; i++) {
    ctx.beginPath();
    ctx.moveTo(X(rv.x[i - 1]), Y(rv.z[i - 1]));
    ctx.lineTo(X(rv.x[i]), Y(rv.z[i]));
    if (mode === "balance") {
      ctx.lineWidth = 3;
      ctx.strokeStyle = balanceColor(bal[i] || 0);
    } else {
      const dv = sd[i] || 0;        // + = faster than ref here, - = slower
      const tt = Math.min(1, Math.abs(dv) / (mx || 1));
      ctx.lineWidth = 2 + 5 * tt;   // 2px at parity -> 7px at biggest gap
      // deltaColor treats +t as "slow" (red): slower here means dv<0, so negate.
      ctx.strokeStyle = deltaColor(-dv, mx);
    }
    ctx.stroke();
  }

  // Braking points: where the brake first crosses onset (rising edge).
  // Yours = amber down-triangle on your line; reference = cyan hollow ring on
  // the reference line, so you can read at a glance how much earlier/later the
  // reference brakes geometrically. Defensive: channels may be missing.
  const br = rv.brake;
  if (Array.isArray(br)) {
    ctx.fillStyle = "#FFB020";
    for (let i = 1; i < br.length; i++) {
      if (br[i] >= 0.3 && br[i - 1] < 0.3) {
        const px = X(rv.x[i]), py = Y(rv.z[i]);
        ctx.beginPath();
        ctx.moveTo(px, py - 6); ctx.lineTo(px - 5, py - 14); ctx.lineTo(px + 5, py - 14);
        ctx.closePath(); ctx.fill();
      }
    }
  }
  const rbk = rf.brake;
  if (Array.isArray(rbk) && Array.isArray(rf.x) && Array.isArray(rf.z)) {
    ctx.strokeStyle = "#22D3CE"; ctx.lineWidth = 2;
    for (let i = 1; i < rbk.length; i++) {
      if (rbk[i] >= 0.5 && rbk[i - 1] < 0.5) {
        const px = X(rf.x[i]), py = Y(rf.z[i]);
        ctx.beginPath(); ctx.arc(px, py, 4.5, 0, 6.283); ctx.stroke();
      }
    }
  }

  // Where the lap stopped counting. The page already says *which corner* it was
  // and has never shown *where*, which on a map is the one thing a map is for:
  // "off track at Ascari" is a sentence, a cross on the drawing is a place.
  // Only ever drawn from a recorded position — laps before schema v8 carry
  // none, and never recorded is not "at the start line".
  if (a.review.lost_at != null && Array.isArray(rv.pos)) {
    const i = nearest(rv.pos, a.review.lost_at);
    const px = X(rv.x[i]), py = Y(rv.z[i]);
    ctx.save();
    ctx.strokeStyle = "#FF4D5E"; ctx.lineWidth = 2.5; ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(px - 6, py - 6); ctx.lineTo(px + 6, py + 6);
    ctx.moveTo(px + 6, py - 6); ctx.lineTo(px - 6, py + 6);
    ctx.stroke();
    ctx.restore();
  }

  // Corner labels at each apex — by NAME, which is what the corner is called
  // everywhere else on this page.
  //
  // This drew "T" + the detector's index, and both halves of that were wrong.
  // The name was ignored outright, so the map said "T1" while hovering the very
  // same apex said "Curva Niki Lauda" — one screen contradicting itself. And
  // the number was the detector's count of what it found on *this* lap, which
  // is exactly the sliding number `cornermap` exists to stop: a lap that
  // detected one corner fewer renumbered every label after it.
  //
  // Degrada come `cornerBands` (nome intero, poi «T7», poi niente), ma qui
  // NON con la distanza fra gli apici — trovata sbagliata il 2026-08-05
  // guardando la mappa grande vera (1036px, Monza): un apice a un centinaio
  // di pixel dal vicino faceva scartare un nome che non avrebbe mai toccato
  // nulla, perché quello che collide non sono i punti, sono i RETTANGOLI di
  // testo. La verifica è quella vera: il rettangolo del nome intero contro i
  // rettangoli già scritti; se ne tocca uno, la forma corta; se non ci sta
  // nemmeno quella, niente.
  //
  // Tre cose da tenere a mente:
  // - la collisione da sola non basta. Misurato il 2026-08-05 sul rail
  //   (220px): «Variante della Roggia» (109px) non toccava nessun'altra
  //   etichetta e passava il test — ma da sola copriva METÀ della tela,
  //   cancellando il disegno del giro che il rail esiste per mostrare. La
  //   proporzione è una condizione IN PIÙ, verificata PRIMA: se il nome
  //   intero sfora una frazione della larghezza della tela, non si prova
  //   nemmeno a scriverlo — si passa dritti alla forma corta. Una frazione,
  //   non un numero di pixel fisso: la stessa funzione disegna una mappa da
  //   220px e una da quasi 1000, e un valore assoluto sarebbe tarato su una
  //   delle due (a 1/4 di tela, il nome più lungo di Monza è al 50% sul
  //   rail e all'11% sulla mappa grande — la soglia degrada solo dove
  //   serve).
  // - il risultato dipende dall'ORDINE in cui le curve vengono scritte (la
  //   prima etichetta arrivata si prende il posto): qui è l'ordine di
  //   `a.corners`, cioè l'ordine di pista — una scelta, non un caso.
  // - il confronto è in coordinate schermo (dopo X()/Y()), le stesse in cui
  //   `fillText` scrive: un confronto in metri o in `pos` normalizzato
  //   ignorerebbe lo zoom del canvas.
  ctx.fillStyle = "rgba(255,255,255,0.85)"; ctx.font = "11px " + UI_FONT;
  const placedLabels = [];
  const maxLabelW = w * 0.25;
  for (const c of a.corners || []) {
    const i = nearest(rv.pos, c.apex);
    const lx = X(rv.x[i]) + 6, ly = Y(rv.z[i]) - 4;
    // Il rettangolo del testo così come `fillText` lo scrive: da (lx, ly) in
    // avanti in larghezza, e verso l'alto in altezza (`textBaseline` è quello
    // di default, "alphabetic": il testo sta SOPRA `ly`, non sotto).
    const rectOf = (text) => {
      const tw = ctx.measureText(text).width;
      return { x0: lx, y0: ly - 11, x1: lx + tw, y1: ly + 3 };
    };
    const overlaps = (r) => placedLabels.some((p) =>
      r.x0 < p.x1 && p.x0 < r.x1 && r.y0 < p.y1 && p.y0 < r.y1);
    const full = c.name || ("T" + (c.index + 1)), short = "T" + (c.index + 1);
    let label = null, rect = null;
    if (ctx.measureText(full).width < maxLabelW) {
      const rFull = rectOf(full);
      if (!overlaps(rFull)) { label = full; rect = rFull; }
    }
    if (!label) {
      const rShort = rectOf(short);
      if (!overlaps(rShort)) { label = short; rect = rShort; }
    }
    if (label) { ctx.fillText(label, lx, ly); placedLabels.push(rect); }
  }

  // Start/finish + direction of travel. A white dot with an "S/F" label (kept
  // distinct from the cyan reference-braking rings) and a short arrow along the
  // first few samples, so the lap's orientation and which way it runs are
  // unambiguous at a glance.
  const sx = X(rv.x[0]), sy = Y(rv.z[0]);
  const k = Math.min(8, rv.x.length - 1);
  let ux = X(rv.x[k]) - sx, uy = Y(rv.z[k]) - sy;
  const ulen = Math.hypot(ux, uy) || 1; ux /= ulen; uy /= ulen;
  // direction arrow (begins just ahead of the dot)
  ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
  const tipX = sx + ux * 26, tipY = sy + uy * 26;
  ctx.beginPath(); ctx.moveTo(sx + ux * 8, sy + uy * 8); ctx.lineTo(tipX, tipY); ctx.stroke();
  const ah = 6, px = -uy, py = ux;   // perpendicular for the arrowhead
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.moveTo(tipX, tipY);
  ctx.lineTo(tipX - ux * ah + px * ah * 0.6, tipY - uy * ah + py * ah * 0.6);
  ctx.lineTo(tipX - ux * ah - px * ah * 0.6, tipY - uy * ah - py * ah * 0.6);
  ctx.closePath(); ctx.fill();
  // start/finish dot + label
  ctx.beginPath(); ctx.arc(sx, sy, 5, 0, 6.283); ctx.fill();
  ctx.font = "bold 11px " + UI_FONT;
  ctx.fillText("S/F", sx - ux * 14 - 6, sy - uy * 14 + 4);

  // Hover marker.
  if (cx != null) {
    const i = nearest(rv.pos, cx);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(X(rv.x[i]), Y(rv.z[i]), 6, 0, 6.283); ctx.stroke();
  }

  // Hand back the screen transform so a hover can find the nearest sample.
  return { rv, X, Y };
}

// The comparison lap, but only when the driver actually chose it. Unpinned, the
// backend elects one for the lap under review (and for its track temperature).
function pinnedBaseline() {
  return BASELINE_PINNED ? $("baseline").value : "";
}

function reloadSelection() {
  loadCombo(CURRENT, $("lap").value, pinnedBaseline());
}

function exportData(fmt) {
  if (!CURRENT) return;
  const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track, fmt, lang: LANG() });
  const lap = $("lap").value;
  if (lap) q.set("lap", lap);
  window.location = "/api/export?" + q.toString();
}

async function loadCombo(combo, lapPath, baselinePath) {
  CURRENT = combo;
  const q = new URLSearchParams({ car: combo.car, track: combo.track });
  if (lapPath) q.set("lap", lapPath);
  if (baselinePath) q.set("baseline", baselinePath);
  setPanelLoading("summary", t("load.lap"));
  $("readout").innerHTML = t("load.lap");
  if (VIEW === "compare") {
    // Riaccenderlo fa parte dello scrivere dentro: dal giro della legenda
    // `#map-readout` può essere `hidden` (giro uscente senza coordinate), e una
    // riga di caricamento scritta in un elemento spento è un buco muto — solo
    // il titolo «Track map» e sotto il vuoto, per tutta la durata della
    // richiesta. `drawMap()` rimette la classe giusta a dati arrivati, quindi
    // qui basta accendere: chi decide se il readout va mostrato resta lui.
    $("map-readout").classList.remove("hidden");
    $("map-readout").innerHTML = t("load.lap");
  }
  // I tre «questo giro non ha…» parlano del giro che sta per essere sostituito:
  // si spengono QUI, non quando il disegno nuovo arriva. Finché portavano
  // `.empty` erano invisibili comunque e la cosa non si vedeva; ora si vede, e
  // quello che si vedeva era una frase FALSA sopra un disegno giusto per tutta
  // la durata della richiesta (misurato: ~1,5 s passando da un giro senza
  // coordinate a uno che le ha, sulla Traiettoria). Nessun buco muto al loro
  // posto: ognuna delle tre viste scrive la propria riga di caricamento.
  for (const id of ["map-missing", "line-missing", "dyn-missing"]) $(id).classList.add("hidden");
  let a;
  try { a = await getJSON("/api/analysis?" + q.toString()); }
  catch (e) {
    $("summary").innerHTML =
      `<div class="item"><div class="v">—</div><div class="k">${t("err.lap")}</div></div>`;
    return;
  }
  DATA = a;
  buildDistance(a);       // this lap's metres, for every chart's x-axis
  FLOW_STEP = 0;          // a new lap is a new explanation, from the top
  fillLaps(a);
  drawLapBar(a);
  drawSummary(a);
  drawCornerSpeeds(a);
  drawWaterfall(a);
  drawDebrief(a);
  renderFlow(a);
  redraw(null);
  drawRail();
  drawRailList();
  // The sheet is per car+track, not per lap: it survives a lap change and is
  // only dropped when the combo does (see the combo picker).
  //
  // La mappa e la scheda frenate stanno accanto ai grafici, quindi si aggiornano
  // sulla stessa scheda e non su una loro. `redraw(a)` sopra è già passato: qui
  // manca solo la colonna destra.
  if (VIEW === "compare") {
    // Il readout lo scrive `drawMap` stessa (vedi il commento lì): niente da
    // duplicare qui.
    drawMap(a, null);
    if (!SHEET) loadBraking();
  }
  if (VIEW === "dynamics") drawDynamics(null);
  if (VIEW === "sectors") loadSectors();
  // The line view is its own request (the zoomed corners need the lap at full
  // resolution), so a new lap invalidates it whether or not the tab is open.
  LINE = null;
  if (VIEW === "line") loadLine();
  wireHover();
}

// Local time-of-day (HH:MM) a lap was recorded, so laps with identical times
// stay distinguishable in the dropdowns. Empty for laps with no timestamp
// (e.g. bundled PRO reference laps).
function lapClock(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fillLaps(a, force) {
  const key = a.car + a.track;
  // The starred lap can move without the combo changing: the reference is
  // elected for the conditions of the lap you're reviewing, so picking a lap
  // from a cold morning moves the star to a cold reference. Repainting only on
  // a combo change would leave the star on a lap the page is no longer using.
  const star = a.best_path || "";
  if (!force && $("lap").dataset.for === key && $("lap").dataset.star === star) return;
  $("lap").dataset.for = key;
  $("lap").dataset.star = star;
  const keepLap = force ? $("lap").value : null;
  const keepBase = force ? $("baseline").value : null;

  // Star the elected reference, not the fastest lap. They differ: a lap driven
  // off track is time you can't repeat, so it's excluded from the reference while
  // still being the fastest in the list — the old rule starred a lap the coach
  // had already rejected. The server sends the elected one so the two can't drift
  // apart, and it isn't a.reference.path: that follows the "compare with" picker.
  const bestPath = a.best_path || null;

  const fill = (id, selectedPath) => {
    const sel = $(id);
    sel.innerHTML = "";
    for (const l of a.laps) {
      const o = document.createElement("option");
      o.value = l.path;
      const star = l.path === bestPath ? "★ " : "";
      const pro = l.source === "pro" ? " [PRO]" : "";
      const clock = lapClock(l.recorded_utc);
      // Text, not colour: <option> styling isn't reliable across browsers and a
      // colour on a closed dropdown is invisible anyway.
      const off = l.off_track ? " · " + t("lap.offTrack") : "";
      // Track temp, when the lap carries it: two laps at 18° and 40° are two
      // different circuits, and until now the dropdown let you compare them
      // side by side with nothing to warn you.
      const temp = l.road_temp ? ` · ${l.road_temp}°` : "";
      o.textContent = `${star}${l.lap_time}${l.valid ? "" : " " + t("lap.invalid")}${off}${temp}${clock ? " · " + clock : ""}${pro}`;
      if (l.path === selectedPath) o.selected = true;
      sel.appendChild(o);
    }
  };
  fill("lap", keepLap || a.review.path);
  fill("baseline", keepBase || a.reference.path);
}

// The identity of what's on screen — lap, reference, gap, track temperature —
// as a strip under the tabs, on every view. It used to be three items inside
// Compare's own summary, which meant the landing tab explained a lap without
// ever naming it, and the Trajectory and Sectors tabs showed numbers you had to
// change tab to identify.
function drawLapBar(a) {
  const el = $("lapbar");
  if (!el) return;
  const gap = (a.review.lap_time_ms - a.reference.lap_time_ms) / 1000;
  const bit = (k, v, cls) =>
    `<div class="bit"><span class="k">${k}</span><span class="v ${cls || ""}">${v}</span></div>`;
  const temp = a.review.road_temp != null
    ? bit(t("lbl.road"), `${a.review.road_temp}°`) : "";
  el.innerHTML =
    bit(t("lbl.lap"), a.review.lap_time + offTrackBadge(a)) +
    bit(t("lbl.comparison"), a.reference.lap_time) +
    bit(t("lbl.gap"), fmt(gap) + "s", gap > 0 ? "slower" : "faster") +
    temp;
  // The window title, so three windows open on three tracks are three different
  // things in the taskbar instead of three "HONE · Analysis". The distinguishing
  // part goes first: a tab strip only shows the first few characters.
  document.title = `${a.track} · ${a.review.lap_time} — HONE`;
}

// Amber, not red: going off track isn't an app error and isn't the game's own
// invalidation either — it's a fact about the lap that explains why it can't be
// the reference. The tooltip is where that "why" lives. …and WHERE, when the lap
// carries it: "off track" alone names a fact the driver can't act on, the corner
// is the part they can go and work on. Absent on laps recorded before the field
// existed, so the badge degrades to the bare wording rather than to an empty
// parenthesis.
function offTrackBadge(a) {
  const rev = (a.laps || []).find((l) => l.path === a.review.path);
  if (!(rev && rev.off_track)) return "";
  const where = a.review.lost_at_corner
    ? ` ${t("lap.offTrack.at")} ${a.review.lost_at_corner}`
    : "";
  return ` <span class="off-track" title="${t("lap.offTrack.why")}">` +
         `${t("lap.offTrack")}${where}</span>`;
}

// What's left for Compare's own summary once the lap bar owns the identity: the
// three notes that are about *this comparison* rather than about the lap. Often
// all three are empty, and then the band hides itself (.summary:empty).
function drawSummary(a) {
  const c = a.consistency || {};
  const item = (k, v, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  // The setup each lap was on, when the two differ. A gap you're reading as
  // "I drove worse" can be a brake-bias click, and until now the page gave you
  // no way to tell. Only shown when it changes the story: same setup, no note.
  const setupNote = setupDelta(a.reference.setup, a.review.setup);
  // Why the benchmark isn't your fastest lap, when the answer is the weather.
  // Without it a slower baseline reads as a broken app; the backend only sends
  // this when conditions really are the reason (see api._conditions_note).
  const condNote = conditionsNote(a.reference.by_conditions);
  // The label follows the reason: "chosen for conditions" over a sentence about
  // track limits would name the wrong cause, which is the one thing this note
  // must never do.
  const condLabel = (a.reference.by_conditions || {}).reason === "unjudged"
    ? t("sum.cond.unj") : t("sum.cond");
  $("summary").innerHTML =
    (c.n >= 2 ? item(t("sum.consistency"), `σ ${(c.std_ms / 1000).toFixed(3)}s · ${c.n} ${t("lbl.laps")}`) : "") +
    (condNote ? item(condLabel, condNote, "warn") : "") +
    (setupNote ? item(t("sum.setup_diff"), setupNote, "warn") : "");
}

// Which condition made a slower lap the benchmark, in words. The backend
// decides *whether* there is a reason and *which* one — it holds the rule that
// says the tyre outranks the temperature and the temperature outranks the grip.
// This only writes the sentence.
function conditionsNote(c) {
  if (!c) return "";
  if (c.reason === "unjudged") {
    return tf("sum.cond.unjt", { time: c.faster_lap_time });
  }
  if (c.reason === "compound") {
    return tf("sum.cond.tyre", {
      tyre: c.compound, time: c.faster_lap_time,
      ftyre: c.faster_compound || t("sum.cond.unknown"),
    });
  }
  if (c.reason === "grip") {
    // Grip is a 0..1 fraction in the sim; nobody reads it that way.
    const pct = (v) => Math.round(v * 100) + "%";
    return tf(c.faster_grip == null ? "sum.cond.gripx" : "sum.cond.grip", {
      grip: pct(c.grip), time: c.faster_lap_time,
      fgrip: c.faster_grip == null ? "" : pct(c.faster_grip),
    });
  }
  return tf(c.faster_road_temp == null ? "sum.cond.vx" : "sum.cond.v", {
    temp: c.road_temp, time: c.faster_lap_time, ftemp: c.faster_road_temp,
  });
}

// A one-line summary of how two laps' setups differ, or "" if they match / are
// unknown. Reads "BB 54% → 53% · TC 3 → 2": reference on the left, this lap on
// the right, so it lines up with how the rest of the summary is written.
function setupDelta(ref, rev) {
  if (!ref || !rev) return "";
  const bits = [];
  const num = (k, label, suffix) => {
    if (ref[k] === undefined || rev[k] === undefined || ref[k] === rev[k]) return;
    bits.push(`${label} ${ref[k]}${suffix || ""} → ${rev[k]}${suffix || ""}`);
  };
  num("brake_bias", "BB", "%");
  num("tc", "TC", "");
  num("abs", "ABS", "");
  num("engine_map", "Map", "");
  return bits.join(" · ");
}

// Min-speed-per-corner table: how fast you carry through each apex vs the
// reference. Δ>0 = you're faster (green), Δ<0 = slower (red). Defensive: the
// field may be absent (older backend) or empty.
function drawCornerSpeeds(a) {
  const el = $("vmin");
  if (!el) return;
  const rows = (a && Array.isArray(a.corner_speeds)) ? a.corner_speeds : [];
  if (!rows.length) { el.innerHTML = ""; return; }
  const num = (v) => (v == null || !isFinite(v)) ? "–" : Math.round(v);
  let body = "";
  for (const c of rows) {
    const d = (c.delta == null || !isFinite(c.delta)) ? null : c.delta;
    const cls = d == null || d === 0 ? "" : (d > 0 ? "faster" : "slower");
    const dTxt = d == null ? "–" : (d > 0 ? "+" : "") + Math.round(d);
    const name = c.name || ("T" + ((c.index ?? 0) + 1));
    body += `<tr><td class="vc">${name}</td>` +
      `<td class="vn">${num(c.vmin_live)}</td>` +
      `<td class="vn ref">${num(c.vmin_ref)}</td>` +
      `<td class="vn ${cls}">${dTxt}</td></tr>`;
  }
  el.innerHTML =
    `<h3>${t("vmin.header")}</h3>` +
    `<table class="vmin-table"><thead><tr>` +
    `<th>${t("vmin.corner")}</th><th>${t("vmin.you")}</th><th>${t("vmin.ref")}</th><th>${t("vmin.delta")}</th>` +
    `</tr></thead><tbody>${body}</tbody></table>`;
}

function cornerLegend(a) {
  if (!a.corners || !a.corners.length) return "";
  return `<div class="legend">` + a.corners.map((c) =>
    `<span><b>T${c.index + 1}</b>${c.name}</span>`).join("") + `</div>`;
}

// Waterfall: the corner time losses ranked biggest-first as proportional bars —
// the "what to fix first" glance. Reuses the losses the debrief already computed
// (no backend), so it stays in sync with the mini-lessons below it.
function lossColor(sev) {
  const hot = [255, 90, 60], mild = [255, 190, 80];
  const mix = (i) => Math.round(mild[i] + (hot[i] - mild[i]) * sev);
  return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}

function drawWaterfall(a) {
  const el = $("waterfall");
  if (!el) return;
  const losses = (a.losses || []).filter((l) => l.lost_s > 0)
    .sort((x, y) => y.lost_s - x.lost_s);
  if (!losses.length) { el.innerHTML = ""; return; }
  let mx = 0.05;
  for (const l of losses) mx = Math.max(mx, l.lost_s);
  const rows = losses.map((l) => {
    const w = (Math.min(l.lost_s / mx, 1) * 100).toFixed(0);
    const sev = Math.min(1, l.lost_s / Math.max(mx, 0.3));
    // A corner whose loss was inherited gets a mark pointing back at the one
    // that caused it: the waterfall is the "what do I fix first" glance, and
    // without this it points at the wrong corner precisely when it matters.
    const from = l.inherited_from >= 0
      ? `<span class="chain-chip" title="${escAttr(l.inherited)}">↩ T${l.inherited_from + 1}</span>`
      : "";
    return `<div class="cons-row">` +
      `<span class="corner">${l.label}${from}</span>` +
      `<span class="cons-track"><span class="cons-fill" style="width:${w}%;background:${lossColor(sev)}"></span></span>` +
      `<span class="cons-nums"><b>−${l.lost_s.toFixed(3)}s</b> · ${l.message}</span>` +
      `</div>`;
  }).join("");
  el.innerHTML = `<h3>${t("wf.title")}</h3>` + rows;
}

// Where inside the corner the time went, as one bar cut into its parts.
// Deliberately one hue in four strengths rather than four colours: this is one
// loss split up, not four things being compared, and a four-colour bar with no
// legend is a puzzle. Segments carry their own label when there's room — the
// same rule the guided flow uses for corner names — and a tooltip always.
const _PHASE_TINT = { entry: 0.95, apex: 0.75, exit: 0.55, after: 0.35 };

// The bar when the loss is split across the corner, the sentence when it all
// happened in one place. Never both: they are the same fact, and a card that
// says it twice reads as two findings.
function phaseBlock(loss) {
  const bar = phaseBar(loss);
  if (bar) return bar;
  return loss.phase_note ? `<div class="detail">${loss.phase_note}</div>` : "";
}

function phaseBar(loss) {
  const parts = (loss.phases || []).filter((p) => p.lost_s > 0.005);
  if (parts.length < 2 || !(loss.lost_s > 0)) return "";
  const total = parts.reduce((a, p) => a + p.lost_s, 0);
  if (total <= 0) return "";
  const seg = parts.map((p) => {
    const pct = (p.lost_s / total) * 100;
    const label = t("phase." + p.phase);
    return `<span class="ph" style="width:${pct.toFixed(1)}%;` +
      `background:rgba(255,176,32,${_PHASE_TINT[p.phase] || 0.5})" ` +
      `title="${escAttr(label + " · " + p.lost_s.toFixed(2) + "s")}">` +
      `${pct >= 18 ? label : ""}</span>`;
  }).join("");
  return `<div class="phase-bar">${seg}</div>`;
}

// Lap-wide findings, above the corner list because that's the order a human
// coach uses them: "you lift on the Kemmel straight" comes before turn 7.
function noteBlocks(a) {
  return (a.notes || []).map((n) =>
    `<div class="loss note">` +
    `<div class="loss-head"><span class="corner">${n.message}</span>` +
    (n.lost_s > 0 ? `<span class="lost">−${n.lost_s.toFixed(3)}s</span>` : "") +
    `</div>` +
    (n.detail ? `<div class="detail">${n.detail}</div>` : "") +
    `</div>`).join("");
}

function drawDebrief(a) {
  const el = $("debrief");
  const legend = cornerLegend(a);
  const notes = noteBlocks(a);
  if (!a.losses.length) {
    el.innerHTML = `<h3>${t("debrief.title")}</h3>${legend}${notes}` +
      (notes ? "" : `<div class="clean">${t("debrief.clean")}</div>`);
    return;
  }
  // The theme, above everything, when the driver is far enough off the pace
  // that the corner list is the wrong lens. Distinct look — it reframes the
  // whole debrief rather than adding to it.
  const head = a.headline
    ? `<div class="headline">${a.headline}</div>` : "";
  let html = `<h3>${t("debrief.title")}</h3>${legend}${head}${notes}`;
  for (const l of a.losses) {
    const major = l.lost_s >= 0.2 ? "major" : "";
    html += `<div class="loss ${major}">` +
      `<div class="loss-head"><span class="corner">${l.label}</span>` +
      `<span class="lost">−${l.lost_s.toFixed(3)}s</span></div>` +
      `<div class="cause">${l.message}</div>` +
      // The link to the corner before, when there is one. Above the numbers
      // because it changes *which corner* the driver should go and work on —
      // there is no point reading this corner's figures first.
      (l.inherited ? `<div class="chain">↩ ${l.inherited}</div>` : "") +
      phaseBlock(l) +
      (l.detail ? `<div class="detail">${l.detail}</div>` : "") +
      (l.fix ? `<div class="fix">💡 ${l.fix}</div>` : "") +
      `</div>`;
  }
  el.innerHTML = html;
}

// --- the lap explained, one step at a time --------------------------------
// The findings and their order are decided server-side in coaching/flow.py —
// what to say first and what to leave out is a rule about the driver's
// attention, and rules like that belong where they can be tested. Everything
// below is presentation: the card, the step you're on, and a chart cropped to
// the stretch of lap the step is talking about.

let FLOW_STEP = 0;

function tf(key, vals) {
  let s = t(key);
  // `{chiave|singolare|plurale}` sceglie la forma in base al valore di `chiave`.
  // Serve perché senza si legge «1 giri · 1 che contano», e una sessione da un
  // giro solo è il caso normale, non il caso limite: capita a ogni out-lap.
  // Una chiave non passata resta tale e quale, così un errore di battitura si
  // vede invece di scegliere in silenzio il plurale.
  s = s.replace(/\{(\w+)\|([^|{}]*)\|([^{}]*)\}/g,
                (whole, k, one, many) =>
                  (k in vals ? (Number(vals[k]) === 1 ? one : many) : whole));
  for (const k in vals) s = s.split("{" + k + "}").join(vals[k]);
  return s;
}

function flowSteps() {
  return (DATA && DATA.flow) || [];
}

function renderFlow(a) {
  const steps = a.flow || [];
  const card = $("flow-card");
  if (!card) return;
  if (!steps.length) {
    card.innerHTML = `<p class="flow-empty">${t("flow.empty")}</p>`;
    $("flow-count").textContent = "";
    $("flow-dots").innerHTML = "";
    return;
  }
  FLOW_STEP = Math.max(0, Math.min(FLOW_STEP, steps.length - 1));
  const s = steps[FLOW_STEP];

  $("flow-count").textContent = tf("flow.step",
    { n: FLOW_STEP + 1, total: steps.length });
  $("flow-dots").innerHTML = steps.map((_, i) =>
    `<span class="dot${i === FLOW_STEP ? " on" : ""}"></span>`).join("");

  // The cost line is phrased as a superlative only on the first step — it is
  // the biggest thing only once, and repeating the claim would make it false.
  const cost = s.lost_s > 0
    ? `<p class="flow-cost">${tf(FLOW_STEP === 0 ? "flow.cost" : "flow.cost_more",
                                { s: s.lost_s.toFixed(2) })}</p>`
    : "";
  card.innerHTML =
    (s.where ? `<span class="flow-where">${s.where}</span>` : "") +
    cost +
    `<h2 class="flow-title">${s.title}</h2>` +
    (s.body ? `<p class="flow-body">${s.body}</p>` : "") +
    (s.detail ? `<p class="flow-detail">${s.detail}</p>` : "") +
    (s.fix ? `<div class="flow-fix"><span class="tag">${t("flow.fix")}</span>${s.fix}</div>` : "");

  const hasChart = s.kind !== "clean";
  const wrap = $("c-flow").parentNode;
  wrap.classList.toggle("hidden", !hasChart);
  $("flow-chart-title").textContent = hasChart ? t("flow.chart." + s.chart) : "";
  if (hasChart) drawFlowChart(a, s);
  drawFlowMap(a, hasChart ? s : null);

  $("flow-prev").disabled = FLOW_STEP === 0;
  $("flow-next").disabled = FLOW_STEP >= steps.length - 1;
}

function wireFlow() {
  const step = (d) => { FLOW_STEP += d; if (DATA) renderFlow(DATA); };
  $("flow-prev").onclick = () => step(-1);
  $("flow-next").onclick = () => step(+1);
  $("flow-whole").onclick = () => showView("compare");
}

// A chart cropped to one stretch of lap. Deliberately its own drawing path
// rather than a `window` parameter threaded through the shared primitives:
// those are used by five other charts that all draw the whole lap, and adding
// an option to each of them to serve one caller is how they stop being simple.
// Where on the track this step is.
//
// The trace beside the card says what happened; it doesn't say *where*, and the
// landing view is the one place a driver has no map to fall back on — the corner
// name in the card is a name, not a place. This is the same delta-coloured line
// the map beside Compare draws (same function, so the two can't disagree about
// which way round the track is), with the step's own stretch traced over it in
// the accent.
//
// Nothing is invented here: the colours are the speed gap the map already
// computes, and the highlighted span is the window the step's chart is zoomed
// to. A lap with no coordinates hides the panel rather than drawing an empty box.
function drawFlowMap(a, step) {
  const cv = $("c-flow-map");
  if (!cv) return;
  const wrap = cv.parentNode;
  wrap.classList.toggle("hidden", !a.has_map);
  // A step about the whole lap (the opening headline) has the whole lap as its
  // window, and lighting up every metre of track says nothing while hiding the
  // one thing the map is for. No highlight there — and the caption has to say so
  // too, or it promises a stretch that isn't drawn.
  const spot = !!step && (step.to - step.from) <= 0.6;
  const title = $("flow-map-title");
  if (title) title.textContent = a.has_map ? t(spot ? "flow.map" : "flow.map.all") : "";
  if (!a.has_map) return;
  const hit = drawMapTo(cv, null, a, null);
  if (!hit || !spot) return;

  const { rv, X, Y } = hit;
  const ctx = cv.getContext("2d");
  ctx.save();
  // Drawn BEHIND what's already on the canvas: a fat band on top would bury the
  // delta colours under a cyan smear, and those colours are the map's whole
  // point. `destination-over` only paints where the canvas is still transparent,
  // so this comes out as a halo around the line, not a coat of paint over it.
  ctx.globalCompositeOperation = "destination-over";
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.strokeStyle = "rgba(34,211,206,0.85)"; ctx.lineWidth = 14;
  ctx.beginPath();
  let drawing = false;
  for (let i = 0; i < rv.pos.length; i++) {
    if (rv.pos[i] < step.from || rv.pos[i] > step.to) { drawing = false; continue; }
    const px = X(rv.x[i]), py = Y(rv.z[i]);
    drawing ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    drawing = true;
  }
  ctx.stroke();
  ctx.restore();
}

function drawFlowChart(a, step) {
  const cv = $("c-flow");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const lo = step.from, hi = step.to;
  const span = (hi - lo) || 1;
  // La proiezione condivisa, con la finestra del passo invece di `RANGE`.
  const X = (p) => projX(p, w, { from: lo, to: hi });

  // The corners inside the window, so the stretch is placeable on the track.
  // The label degrades with the room available — full name, then "T7", then
  // nothing. Real corner names are long ("Variante della Roggia") and on a wide
  // window they overlap into an unreadable smear, which is worse than a band
  // with no caption.
  ctx.font = "10px " + MONO;
  for (const c of a.corners) {
    if (c.exit < lo || c.entry > hi) continue;
    const x0 = X(c.entry), band = X(c.exit) - x0;
    ctx.fillStyle = "rgba(120,140,170,0.10)";
    ctx.fillRect(x0, 0, band, h);

    const full = c.name || "T" + (c.index + 1);
    const short = "T" + (c.index + 1);
    const label = ctx.measureText(full).width + 6 <= band ? full
                : ctx.measureText(short).width + 4 <= band ? short : null;
    if (label) {
      ctx.fillStyle = "rgba(255,255,255,0.45)";
      ctx.fillText(label, x0 + (band - ctx.measureText(label).width) / 2, 11);
    }
  }

  const win = (pos, vals) => {
    const p = [], v = [];
    for (let i = 0; i < pos.length; i++) {
      if (pos[i] >= lo && pos[i] <= hi) { p.push(pos[i]); v.push(vals[i]); }
    }
    return { p, v };
  };
  const trace = (pos, vals, min, max, color, lw, dash) => {
    const { p, v } = win(pos, vals);
    if (p.length < 2) return;
    ctx.save();
    if (dash) { ctx.setLineDash(dash); ctx.globalAlpha = 0.65; }
    ctx.beginPath();
    const range = (max - min) || 1;
    for (let i = 0; i < p.length; i++) {
      const x = X(p[i]), y = h - ((v[i] - min) / range) * h;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.stroke();
    ctx.restore();
  };

  const rv = a.review.channels, rf = a.reference.channels;
  if (step.chart === "speed") {
    let min = Infinity, max = -Infinity;
    for (const src of [win(rv.pos, rv.speed).v, win(rf.pos, rf.speed).v]) {
      for (const x of src) { min = Math.min(min, x); max = Math.max(max, x); }
    }
    if (!isFinite(min)) return;
    min = Math.floor(min - 5); max = Math.ceil(max + 5);
    trace(rf.pos, rf.speed, min, max, "#3fd0e0", 1.5);
    trace(rv.pos, rv.speed, min, max, "#ffffff", 2);
    axisLabel(ctx, w, h, max + " km/h", min + " km/h");
  } else if (step.chart === "inputs") {
    trace(rf.pos, rf.throttle, 0, 1, "#1d8f43", 1, [4, 3]);
    trace(rf.pos, rf.brake, 0, 1, "#9e2a22", 1, [4, 3]);
    trace(rv.pos, rv.throttle, 0, 1, "#22dd66", 2);
    trace(rv.pos, rv.brake, 0, 1, "#ff3b30", 2);
  } else {
    const d = a.review.delta;
    let m = 0.05;
    for (const x of win(d.pos, d.delta_s).v) m = Math.max(m, Math.abs(x));
    ctx.strokeStyle = "rgba(255,255,255,0.25)";
    ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
    trace(d.pos, d.delta_s, -m, m, "#ffffff", 2);
    axisLabel(ctx, w, h, `+${m.toFixed(2)}s`, `-${m.toFixed(2)}s`);
  }
}

// --- one run of laps, as it was driven -----------------------------------
// Everything else on this page is lap-centric: pick two laps, compare them.
// That's the right shape for studying a lap and the wrong one for the question
// you have when you get up from the wheel, which is how the run went.

let SESSION = null;      // last /api/sessions payload
let SESSION_I = 0;       // which run of that payload is on screen

async function loadSession(combo, index) {
  if (!combo) return;
  const q = new URLSearchParams({ car: combo.car, track: combo.track,
                                  index: index || 0 });
  let s;
  try { s = await getJSON("/api/sessions?" + q.toString()); }
  catch (e) { s = { sessions: [], current: null }; }
  SESSION = s;
  SESSION_I = s.index || 0;
  renderSession(s);
}

// The page's language, not the browser's. `undefined` here meant the month name
// came from Chrome's locale, so an English page read "since 31 lug · 13:58" on
// an Italian machine — the one word on the strip that hadn't switched.
function fmtWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(LANG(), { day: "numeric", month: "short" }) +
         " · " + d.toLocaleTimeString(LANG(), { hour: "2-digit", minute: "2-digit" });
}

function renderSession(s) {
  const cur = s && s.current;
  // One fetch, two tabs: `current.recap` rides on the same /api/sessions
  // payload as everything below, so the door screen and the Session tab never
  // disagree about which run they're describing.
  renderRecap(cur);
  const pick = $("ses-select");
  if (!cur) {
    $("ses-when").textContent = "";
    $("ses-sub").textContent = "";
    $("ses-numbers").innerHTML = `<div class="nothing">${t("ses.none")}</div>`;
    $("ses-laps").innerHTML = "";
    $("ses-changed").innerHTML = "";
    pick.innerHTML = "";
    return;
  }

  pick.innerHTML = s.sessions.map((x, i) =>
    `<option value="${i}"${i === s.index ? " selected" : ""}>` +
    `${fmtWhen(x.started_utc)} · ${x.laps} ${t("lbl.laps")}` +
    `${x.best ? " · " + x.best : ""}</option>`).join("");
  pick.onchange = () => loadSession(CURRENT, parseInt(pick.value, 10));

  $("ses-when").textContent = fmtWhen(cur.started_utc);
  const bits = [tf("ses.sub", { laps: cur.laps, valid: cur.valid,
                               mins: Math.max(1, Math.round(cur.duration_s / 60)) })];
  if (cur.road_temp_from != null) {
    bits.push(tf("ses.sub_temp", { from: cur.road_temp_from.toFixed(1),
                                   to: cur.road_temp_to.toFixed(1) }));
  }
  $("ses-sub").textContent = bits.join("  ·  ");

  const item = (k, v, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  const c = cur.consistency || {};
  const prev = cur.previous;
  let numbers = "";
  if (cur.best) {
    numbers += item(t("ses.best"), cur.best);
    if (c.n >= 2) {
      numbers += item(t("ses.mean"), fmtMs(c.mean_ms));
      numbers += item(t("ses.spread"), `σ ${(c.std_ms / 1000).toFixed(3)}s`);
    }
    if (prev && prev.delta_ms != null) {
      const d = prev.delta_ms / 1000;
      numbers += item(t("ses.vsprev"), (d > 0 ? "+" : "") + d.toFixed(3) + "s",
                      d > 0 ? "slower" : "faster");
    }
    // Measured, not modelled — and absent on laps recorded before the tank was
    // written down, which is why it's a conditional item and not a dash.
    if (cur.fuel_per_lap != null) {
      numbers += item(t("ses.fuel"), `${cur.fuel_per_lap.toFixed(2)} L`);
    }
  } else {
    numbers = `<div class="nothing">${t("ses.nobest")}</div>`;
  }
  $("ses-numbers").innerHTML = numbers;

  // Every lap of the run in the order driven, cut ones included: leaving them
  // out would show a session you didn't have. The bar length is the gap to the
  // best of the run, so the shape of the list is the shape of the evening.
  const times = cur.laps_detail.map((l) => l.lap_time_ms).filter((x) => x > 0);
  const floor = Math.min.apply(null, times.concat([Infinity]));
  const worst = Math.max.apply(null, times.concat([0]));
  const span = Math.max(1, worst - floor);
  $("ses-laps").innerHTML = `<h3>${t("ses.laps")}</h3>` +
    cur.laps_detail.map((l) => {
      const w = 6 + 94 * ((l.lap_time_ms - floor) / span);
      const tags = (l.is_best ? `<span class="tag best">${t("ses.lap_best")}</span>` : "") +
        (!l.valid ? `<span class="tag out">${t("ses.lap_out")}</span>` : "") +
        (l.off_track ? `<span class="tag cut">${t("ses.lap_cut")}</span>` : "") +
        (l.fuel_used != null
          ? `<span class="tag fuel" title="${escAttr(t("ses.fuel"))}">${l.fuel_used.toFixed(2)} L</span>`
          : "");
      return `<button type="button" class="ses-lap${l.is_best ? " is-best" : ""}" ` +
             `data-path="${l.path}" title="${t("ses.open")}">` +
             `<span class="time">${l.lap_time}</span>` +
             `<span class="bar"><i style="width:${w.toFixed(1)}%"></i></span>` +
             `<span class="tags">${tags}</span></button>`;
    }).join("");
  for (const b of $("ses-laps").querySelectorAll(".ses-lap")) {
    b.onclick = () => openLapInCompare(b.dataset.path);
  }

  // What moved since the run before. Both directions, because a session where
  // you gained three tenths overall and lost half a second in one corner is a
  // different evening from one where everything crept forward.
  if (!prev) {
    $("ses-changed").innerHTML =
      `<h3>${t("ses.changed")}</h3><div class="nothing">${t("ses.first")}</div>`;
  } else {
    const rows = (list, cls) => list.map((x) =>
      `<div class="move ${cls}"><span class="corner">${x.label}</span>` +
      `<span class="amount">${cls === "up" ? "−" : "+"}${x.gain_s.toFixed(2)}s</span>` +
      `${x.message ? `<span class="why">${x.message}</span>` : ""}</div>`).join("");
    const any = prev.improved.length + prev.regressed.length;
    $("ses-changed").innerHTML = `<h3>${t("ses.changed")}</h3>` + (any
      ? (prev.improved.length ? `<h4>${t("ses.improved")}</h4>` + rows(prev.improved, "up") : "") +
        (prev.regressed.length ? `<h4>${t("ses.regressed")}</h4>` + rows(prev.regressed, "down") : "")
      : `<div class="nothing">${t("ses.nomoves")}</div>`);
  }
}

// --- "How it went": the door onto the report -----------------------------
// Dove è finito il tempo di un'uscita, in decimi che sommano al numero in
// testa. Le barre sono in scala sulla fase peggiore di QUESTA sessione: non
// c'è nessuna soglia, e nessun colore che voglia dire "bravo". `cur` è
// `current` da /api/sessions.
function renderRecap(cur) {
  const head = $("recap-head"), ph = $("recap-phases"), lp = $("recap-laps");
  const lpSec = $("recap-laps-sec");
  const note = $("recap-where-note");
  if (!head || !ph || !lp) return;
  const r = cur && cur.recap;
  if (!r) {
    head.innerHTML = "";
    // La promessa del titolo — «media per giro · le parti sommano al numero
    // qui sopra» — se ne va col recap. Qui sopra non c'è nessun numero
    // (`#recap-head` resta vuoto e `.summary:empty` lo toglie) e qui sotto non
    // c'è nessuna parte: la frase nominerebbe due cose che non ci sono. Se ne
    // va la promessa, non la sezione: nasconderla — come si fa con
    // `#recap-laps-sec`, che di statico non ha niente da mostrare — ucciderebbe
    // la visita guidata, che su questa sezione ha il suo «Parti da qui» e su un
    // bersaglio invisibile chiama `finish()`, non «salta».
    if (note) note.textContent = "";
    // Tre casi, tre frasi: `!cur` è lo stesso fatto che il pannello Sessione
    // scrive sullo stesso payload ("nessun giro registrato");
    // `recap_clock_broken` è l'unica delle sette cause che sia MISURATA (la
    // guardia in trends.py: l'orologio del miglior giro non copre il giro), e
    // arriva già decisa dal payload — qui non si rifà nessun controllo; tutto
    // il resto resta la frase generica, perché nominare una causa fra le altre
    // sei sarebbe quasi sempre nominare quella sbagliata.
    // Le tre chiamate restano scritte per esteso, con la chiave letterale
    // dentro, perché è così che test_web_i18n_keys le vede: una chiave a pezzi non
    // la controlla nessuno, ed è come i pulsanti del tour sono rimasti in
    // inglese per mesi.
    const msg = !cur ? t("recap.nolaps")
              : cur.recap_clock_broken ? t("recap.clock") : t("recap.none");
    ph.innerHTML = `<div class="nothing">${msg}</div>`;
    lp.innerHTML = "";
    // Un titolo («Giro per giro») sopra il vuoto si legge come rotto: la
    // sezione sparisce con lui, non solo la lista sotto.
    if (lpSec) lpSec.classList.add("hidden");
    return;
  }
  if (lpSec) lpSec.classList.remove("hidden");
  // C'è un recap: il titolo può promettere. La chiave sta scritta per esteso
  // dentro la chiamata, come le tre frasi del vuoto qui sopra, perché è così
  // che test_web_i18n_keys la vede.
  if (note) note.textContent = t("recap.wherenote");
  const item = (k, v) => `<div class="item"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  // Una sola convenzione di segno su tutta la scheda: `fmtLoss` gira il segno
  // una volta sola, qui, per il totale come per le cinque fasi sotto e per il
  // gap di ogni riga giro — sommare le cinque righe a mano deve ridare questo
  // numero, segno compreso, non il suo opposto.
  head.innerHTML = item(t("recap.best"), `${r.reference} <small>(${t("recap.yardstick")})</small>`) +
                   item(t("recap.gain"), fmtLoss(r.gain_avg_s));

  let mx = 0.05;
  for (const p of r.phases) mx = Math.max(mx, p.avg_s);
  ph.innerHTML = r.phases.map((p) => {
    const w = (Math.min(Math.max(p.avg_s, 0) / mx, 1) * 100).toFixed(0);
    return `<div class="ses-row">` +
      `<span class="ses-when">${t("recap.phase." + p.phase)}</span>` +
      `<span class="ses-track"><span class="ses-fill" style="width:${w}%"></span></span>` +
      `<span class="ses-nums">${fmtLoss(p.avg_s)}</span></div>`;
  }).join("");

  lp.innerHTML = r.laps.map((l) =>
    `<div class="recap-lap" data-path="${l.path}">` +
    `<span class="lap-time">${l.lap_time}</span>` +
    `<span class="lap-gap">${fmtLoss(l.gap_s)}</span>` +
    `<span class="corner">${l.corner}</span></div>`).join("");
  // A click opens the lap in Compare — same mechanism the Session tab's own
  // lap rows already use, not a second way to jump to a lap.
  for (const el of lp.querySelectorAll(".recap-lap")) {
    el.onclick = () => openLapInCompare(el.dataset.path);
  }
}

// Il segno dal punto di vista del pilota: perdere è meno tempo tuo. Meno
// tipografico, come il resto del report.
function fmtLoss(s) {
  return (s > 0 ? "−" : s < 0 ? "+" : "") + Math.abs(s).toFixed(3) + "s";
}

// --- race pace: one run on one tank --------------------------------------
// A session and a stint are not the same cut. The session view is right about
// "one sitting" and blind to the refuel that can sit inside it; this tab asks
// the question a race asks, and every number on it is a NET number — the tank
// emptying and the tyres giving up pull opposite ways and this archive cannot
// separate them. The notes strip at the bottom is not decoration: without it a
// median reads as a degradation figure, which is the one thing it is not.

let STINT = null;        // last /api/stint payload
let STINT_I = 0;         // which stint of that payload is on screen

async function loadStint(combo, index) {
  if (!combo) return;
  const q = new URLSearchParams({ car: combo.car, track: combo.track,
                                  index: index || 0 });
  let s;
  try { s = await getJSON("/api/stint?" + q.toString()); }
  catch (e) { s = { stints: [], current: null }; }
  STINT = s;
  STINT_I = s.index || 0;
  renderStint(s);
}

function renderStint(s) {
  const cur = s && s.current;
  const pick = $("st-select");
  if (!pick) return;
  if (!cur) {
    $("st-when").textContent = "";
    $("st-sub").textContent = "";
    $("st-numbers").innerHTML = `<div class="nothing">${t("st.none")}</div>`;
    $("st-laps").innerHTML = "";
    $("st-notes").innerHTML = "";
    $("tyres").classList.add("hidden");
    pick.innerHTML = "";
    return;
  }

  // A stint nobody could check is still offered — it is the best reading there
  // is — but the picker says so, because a pre-fuel-channel run may hide a
  // refuel and the split would never know.
  pick.innerHTML = s.stints.map((x, i) =>
    `<option value="${i}"${i === s.index ? " selected" : ""}>` +
    `${fmtWhen(x.started_utc)} · ${x.laps} ${t("lbl.laps")}` +
    `${x.fuel_used != null ? " · " + x.fuel_used.toFixed(1) + " L" : ""}` +
    `${x.verified ? "" : " · " + t("st.unverified")}</option>`).join("");
  pick.onchange = () => loadStint(CURRENT, parseInt(pick.value, 10));

  $("st-when").textContent = fmtWhen(cur.started_utc);
  const mins = minutesBetween(cur.started_utc, cur.ended_utc);
  const bits = [tf("st.sub", { laps: cur.laps, counted: cur.counted, mins })];
  if (cur.fuel.start != null && cur.fuel.end != null) {
    bits.push(tf("st.sub_fuel", { from: cur.fuel.start.toFixed(1),
                                  to: cur.fuel.end.toFixed(1) }));
  }
  $("st-sub").textContent = bits.join("  ·  ");

  const item = (k, v, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  let numbers = "";
  if (cur.median_ms != null) {
    numbers += item(t("st.pace"), cur.median);
    numbers += item(t("st.best"), cur.best);
    numbers += item(t("st.spread"), `${(cur.spread_ms / 1000).toFixed(3)}s`);
    // The drift reads "flat" rather than a number whenever the slope sits
    // inside its own error bar. Printing ±0.26 there would be handing over a
    // finding that the data does not contain.
    if (cur.trend) {
      const v = cur.trend.significant
        ? (cur.trend.slope_ms > 0 ? "+" : "−") +
          (Math.abs(cur.trend.slope_ms) / 1000).toFixed(3) + "s"
        : t("st.flat");
      numbers += item(t("st.drift"), v,
                      cur.trend.significant
                        ? (cur.trend.slope_ms > 0 ? "slower" : "faster") : "");
    }
    if (cur.fuel.per_lap != null) {
      numbers += item(t("st.fuel"), `${cur.fuel.per_lap.toFixed(2)} L`);
    }
    if (cur.fuel.range_laps != null) {
      numbers += item(t("st.range"), String(cur.fuel.range_laps));
    }
  } else {
    numbers = `<div class="nothing">${t("st.nopace")}</div>`;
  }
  $("st-numbers").innerHTML = numbers;

  drawStintPace(cur);
  drawTyres({ tyres: (cur.tyres && cur.tyres.wheels) || [] });

  // Every lap of the stint in the order driven. The ones that weren't running a
  // pace stay on the list and lose their weight, rather than disappearing: a
  // stint drawn one lap shorter than the one you drove is a different stint.
  // Scaled to the laps that were a pace, and the rest max out. Scaled to every
  // lap instead, one 3:25 spin owns the full width and the nine laps of racing
  // beside it are nine identical stubs — the list stops having a shape.
  const paced = cur.laps_detail.filter((l) => l.counted)
                              .map((l) => l.lap_time_ms).filter((x) => x > 0);
  const times = paced.length ? paced
    : cur.laps_detail.map((l) => l.lap_time_ms).filter((x) => x > 0);
  const floor = Math.min.apply(null, times.concat([Infinity]));
  const worst = Math.max.apply(null, times.concat([0]));
  const span = Math.max(1, worst - floor);
  $("st-laps").innerHTML = `<h3>${t("st.laps")}</h3>` +
    cur.laps_detail.map((l) => {
      const w = Math.min(100, 6 + 94 * ((l.lap_time_ms - floor) / span));
      const tags = (l.counted ? "" : `<span class="tag out">${t("st.lap_off")}</span>`) +
        (l.off_track ? `<span class="tag cut">${t("ses.lap_cut")}</span>` : "") +
        (l.fuel_used != null
          ? `<span class="tag fuel" title="${escAttr(t("st.fuel"))}">${l.fuel_used.toFixed(2)} L</span>`
          : "") +
        (l.tyre_c != null
          ? `<span class="tag tyre" title="${escAttr(t("tyre.temp"))}">${l.tyre_c.toFixed(0)}°</span>`
          : "");
      return `<button type="button" class="ses-lap${l.counted ? "" : " not-pace"}" ` +
             `data-path="${l.path}" title="${t("ses.open")}">` +
             `<span class="time">${l.lap_time}</span>` +
             `<span class="bar"><i style="width:${w.toFixed(1)}%"></i></span>` +
             `<span class="tags">${tags}</span></button>`;
    }).join("");
  for (const b of $("st-laps").querySelectorAll(".ses-lap")) {
    b.onclick = () => openLapInCompare(b.dataset.path);
  }

  $("st-notes").innerHTML = `<h3>${t("st.notes")}</h3>` +
    cur.notes.map((n) => `<p class="note">${mdBold(n)}</p>`).join("");
}

function minutesBetween(a, b) {
  if (!a || !b) return 1;
  return Math.max(1, Math.round((new Date(b) - new Date(a)) / 60000));
}

// The backend writes the notes, and marks the load-bearing phrase with **…**.
// Escaped first — escAttr over-escapes quotes for text content, which costs
// nothing and covers the day one of these strings carries a car name a driver
// typed rather than one we wrote.
function mdBold(s) {
  return escAttr(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
}

function drawStintPace(cur) {
  const { ctx, w, h } = setup($("c-stint"));
  const laps = cur.laps_detail || [];
  if (!laps.length) return;

  // Scaled to the laps that were running a pace, not to every lap: one 3:25 spin
  // squashes eight laps of racing into a single flat line at the top.
  const paced = laps.filter((l) => l.counted).map((l) => l.lap_time_ms);
  const base = paced.length ? paced : laps.map((l) => l.lap_time_ms);
  let lo = Math.min(...base), hi = Math.max(...base);
  if (hi === lo) hi = lo + 1000;
  const pad = (hi - lo) * 0.18; lo -= pad; hi += pad;
  const n = laps.length;
  const X = (i) => (n === 1 ? w / 2 : (i / (n - 1)) * (w - 30) + 15);
  const rawY = (ms) => ((ms - lo) / (hi - lo)) * (h - 24) + 12;
  // Clamped, and the clamping is the feature. Scaled to the pace, a 3:25 spin
  // lands a long way under the floor of the canvas: unclamped the polyline dives
  // out of the frame and climbs back, which draws two vertical lines to nowhere
  // and no point at all. Pinned to the edge it reads as what it is — a lap that
  // was off this chart — and the tag on its row says why.
  const Y = (ms) => Math.max(6, Math.min(h - 6, rawY(ms)));
  const offScale = (ms) => rawY(ms) !== Y(ms);

  // The fitted drift, drawn only when it was believed. A regression line over a
  // slope that failed its own significance test would be the picture of a
  // finding the numbers refused to state.
  if (cur.trend && cur.trend.significant && paced.length) {
    const xs = laps.map((l, i) => (l.counted ? i : null)).filter((x) => x !== null);
    const mx = xs.reduce((a, b) => a + b, 0) / xs.length;
    const my = paced.reduce((a, b) => a + b, 0) / paced.length;
    const at = (x) => my + cur.trend.slope_ms * (x - mx);
    ctx.beginPath();
    ctx.moveTo(X(xs[0]), Y(at(xs[0])));
    ctx.lineTo(X(xs[xs.length - 1]), Y(at(xs[xs.length - 1])));
    ctx.strokeStyle = "#FFB020"; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
    ctx.stroke(); ctx.setLineDash([]);
  }

  ctx.beginPath();
  laps.forEach((l, i) => {
    const x = X(i), y = Y(l.lap_time_ms);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = "rgba(255,255,255,0.20)"; ctx.lineWidth = 1; ctx.stroke();

  laps.forEach((l, i) => {
    const off = offScale(l.lap_time_ms);
    ctx.beginPath();
    ctx.arc(X(i), Y(l.lap_time_ms), l.counted ? 4 : 3, 0, 6.283);
    if (off) {
      // Hollow: a filled dot on the edge would claim to be a reading, and this
      // one is only "further than the frame goes".
      ctx.strokeStyle = "rgba(255,255,255,0.45)"; ctx.lineWidth = 1.5;
      ctx.stroke();
    } else {
      ctx.fillStyle = l.counted ? "#ffffff" : "rgba(255,255,255,0.28)";
      ctx.fill();
    }
  });

  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px " + MONO;
  if (paced.length) {
    const fastest = Math.min(...paced), slowest = Math.max(...paced);
    ctx.fillText(fmtMs(fastest), w - 74, Y(fastest) - 5);
    ctx.fillText(fmtMs(slowest), w - 74, Y(slowest) + 13);
  }
}

function openLapInCompare(path) {
  const sel = $("lap");
  if ([...sel.options].some((o) => o.value === path)) {
    sel.value = path;
    reloadSelection();
  }
  showView("compare");
}

// --- canvas drawing -------------------------------------------------------
// Canvas doesn't inherit the page's font stack, so every chart was drawing in
// the system UI face while everything around it used the brand ones. Numbers go
// in the mono face for the same reason the CSS puts them there: a column of
// figures that shifts sideways as the digits change is hard to compare.
const UI_FONT = '"Inter", system-ui, "Segoe UI", sans-serif';
const MONO = '"JetBrains Mono", ui-monospace, Consolas, monospace';

function setup(cv) {
  const r = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * r; cv.height = h * r;
  const ctx = cv.getContext("2d");
  ctx.setTransform(r, 0, 0, r, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

// L'etichetta degrada con lo spazio: nome intero, poi «T7», poi niente.
//
// Prima scriveva sempre e solo «T7», mentre la mappa scrive il nome e il grafico
// del flusso scrive il nome degradandolo. Tre convenzioni per la stessa curva
// sulla stessa schermata: il pilota leggeva «Variante Ascari» su un disegno e
// «T7» su quello sotto, e doveva dedurre da solo che fossero la stessa cosa.
// Questa è la versione del flusso, promossa a unica — fattorizzata in
// `degradeLabel` perché la mappa (coordinate 2D) misura lo spazio in un modo
// diverso da un grafico lineare (una fascia lungo un asse), ma la SOGLIA con
// cui si decide fra nome intero, «T7» e niente dev'essere la stessa soglia,
// non una sua copia con margini propri che un domani divergono.
function degradeLabel(ctx, full, short, avail) {
  if (ctx.measureText(full).width + 6 <= avail) return full;
  if (ctx.measureText(short).width + 4 <= avail) return short;
  return null;
}

function cornerBands(ctx, w, h, corners) {
  ctx.fillStyle = "rgba(120,140,170,0.10)";
  for (const c of corners) {
    const x0 = projX(c.entry, w);
    ctx.fillRect(x0, 0, projX(c.exit, w) - x0, h);
  }
  ctx.fillStyle = "rgba(255,255,255,0.35)";
  ctx.font = "10px " + UI_FONT;
  for (const c of corners) {
    const x0 = projX(c.entry, w), band = projX(c.exit, w) - x0;
    const label = degradeLabel(ctx, c.name || "T" + (c.index + 1), "T" + (c.index + 1), band);
    if (label) ctx.fillText(label, x0 + (band - ctx.measureText(label).width) / 2, 11);
  }
}

// Horizontal reference lines with their value, drawn INSIDE the plot against the
// left edge. Every trace on this page maps x straight from track position
// (`pos * w`), and so do the crosshair and both hover handlers — a proper axis
// gutter would mean re-deriving all of that in eight places. A label on a dark
// chip costs nothing and answers the question the charts couldn't: not "is this
// high" but "how high". `fmt` returning "" draws the lines without a scale,
// which is what a channel in radians wants.
function gridY(ctx, w, h, lo, hi, fmt, ticks) {
  ticks = ticks || 4;
  ctx.save();
  ctx.font = "10px " + MONO;
  for (let i = 0; i <= ticks; i++) {
    const y = Math.round((i / ticks) * h) + 0.5;
    if (i > 0 && i < ticks) {
      ctx.strokeStyle = "rgba(255,255,255,0.07)";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    const label = fmt(hi - (i / ticks) * (hi - lo));
    if (!label) continue;
    // Keep the top and bottom labels inside the box rather than half-clipped.
    const ty = i === 0 ? 11 : (i === ticks ? h - 4 : y + 3.5);
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = "rgba(11,14,18,0.72)";
    ctx.fillRect(3, ty - 9, tw + 6, 12);
    ctx.fillStyle = "rgba(255,255,255,0.5)";
    ctx.fillText(label, 6, ty);
  }
  ctx.restore();
}

// --- the lap in metres ------------------------------------------------------
// Every chart on this page has the lap as its x-axis, and until now that axis
// was labelled in per cent — "50%" is a number you have to convert before you
// can go and drive to it. The backend now sends the metres actually covered at
// each plotted frame (`dist_m`, measured on the recorded coordinates), so the
// axis can say "1500 m". Laps with no coordinates send zeros and keep per cent:
// a wrong scale is worse than an abstract one.
function buildDistance(a) {
  DIST = null;
  const ch = a && a.review && a.review.channels;
  const d = ch && ch.dist_m;
  if (!Array.isArray(d) || d.length < 2 || !Array.isArray(ch.pos)) return;
  // Drop the pre-line wrap frame the same way the backend does (see
  // strip_leading_wrap): the first sample of a lap can still read pos≈1.0, and
  // a lookup table seeded at 1.0 answers every later position wrongly.
  let i = 0;
  while (i < ch.pos.length - 1 && ch.pos[i] > 0.5 && ch.pos[i] > ch.pos[i + 1]) i++;
  const pos = [], m = [];
  for (; i < d.length; i++) {
    if (pos.length && ch.pos[i] <= pos[pos.length - 1]) continue;   // strictly forward
    pos.push(ch.pos[i]); m.push(d[i]);
  }
  const total = m.length ? m[m.length - 1] : 0;
  // Under 100 m there is no lap here — an all-zero distance channel (a lap
  // recorded before the coordinates existed) lands exactly on this.
  if (pos.length < 2 || total < 100) return;
  DIST = { pos, m, total };
}

// Metres covered at a track position, linearly between the two frames around it.
function metresAt(p) {
  if (!DIST) return null;
  const i = nearest(DIST.pos, p);
  const j = DIST.pos[i] > p ? i - 1 : i + 1;
  if (j < 0 || j >= DIST.pos.length) return DIST.m[i];
  const lo = Math.min(i, j), hi = Math.max(i, j);
  const span = DIST.pos[hi] - DIST.pos[lo];
  if (!span) return DIST.m[lo];
  const f = Math.max(0, Math.min(1, (p - DIST.pos[lo]) / span));
  return DIST.m[lo] + (DIST.m[hi] - DIST.m[lo]) * f;
}

// The inverse: where along the lap (0..1) a distance mark falls, so a round
// number of metres can be drawn as a gridline.
function posAtMetres(v) {
  if (!DIST) return null;
  const i = nearest(DIST.m, v);
  const j = DIST.m[i] > v ? i - 1 : i + 1;
  if (j < 0 || j >= DIST.m.length) return DIST.pos[i];
  const lo = Math.min(i, j), hi = Math.max(i, j);
  const span = DIST.m[hi] - DIST.m[lo];
  if (!span) return DIST.pos[lo];
  const f = Math.max(0, Math.min(1, (v - DIST.m[lo]) / span));
  return DIST.pos[lo] + (DIST.pos[hi] - DIST.pos[lo]) * f;
}

// Round distance marks along the lap — 5 to 8 of them, at a step read off a pit
// board rather than at whatever a tenth of the lap happens to be. Null when the
// lap has no coordinates, and the axis falls back to per cent.
function distanceTicks() {
  if (!DIST) return null;
  // I passi fini in testa servono alla finestra ritagliata che sta arrivando: su
  // 200 m di curva il passo più corto era 100 m, cioè **una tacca sola**, e sotto
  // i 100 m nessuna — e allora il `return out.length ? out : null` qui sotto
  // ricadeva sui decimi del GIRO INTERO, disegnando tacche fuori dalla finestra.
  // Sul giro intero non cambia niente: nessun giro reale sta sotto gli 800 m.
  // I metri agli estremi della finestra, non del giro: con `RANGE` nullo sono
  // 0 e la lunghezza, cioè esattamente il comportamento di prima.
  const from = RANGE ? metresAt(RANGE.from) : 0;
  const to = RANGE ? metresAt(RANGE.to) : DIST.total;
  if (from == null || to == null || !(to > from)) return null;
  const span = to - from;
  const step = [10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000]
    .find((s) => span / s <= 8) || 5000;
  const out = [];
  const first = Math.ceil((from + step * 0.3) / step) * step;
  for (let v = first; v < to - step * 0.3; v += step) {
    out.push({ at: posAtMetres(v), m: v });
  }
  // A lap too short for even one mark keeps the tenths of a lap: a chart with no
  // gridlines at all is a worse answer than an abstract one.
  return out.length ? out : null;
}

// A position for the readouts: metres when we know them, per cent when we don't.
function posLabel(p) {
  const m = metresAt(p);
  return m == null ? Math.round(p * 100) + "%" : Math.round(m) + " m";
}

// --- la finestra ------------------------------------------------------------
//
// **Una finestra, non una curva selezionata**, ed è la differenza che decide se
// questo lavoro va rifatto o no. Modellare «la curva 4 è selezionata» come un
// indice sembra più semplice e chiude la porta a tutto il resto: il trascinamento
// su un tratto, un settore, «i 400 m prima della staccata». Sono tutti produttori
// della stessa cosa — un intervallo — e se l'intervallo è il modello, ognuno di
// loro costa mezza giornata invece di una riscrittura.
//
// `source` non è decorazione: serve a intitolare la finestra. «Curva 4» quando
// arriva da un chip, «1240-1480 m» quando arriva da un trascinamento.
//
// La proiezione ritagliata non è nuova: era già scritta, verificata a schermo e
// chiusa dentro `drawFlowChart`, che ritaglia da mesi per mostrare un passo alla
// volta. Qui viene **promossa**, non riscritta, e il flusso resta il suo primo
// consumatore — così se si rompe si rompe subito, in una vista che si guarda.
let RANGE = null;     // {from, to, source} — null = giro intero

// Con `RANGE` nullo deve dare **esattamente** `p * w`: nessun ramo separato,
// nessuna deriva possibile sul percorso normale, che è quello che vedono tutti.
// `win` esplicita per chi ha una finestra propria che non è `RANGE`: è il caso
// del grafico del flusso, che ritaglia sul passo che sta spiegando. Passandogliela
// resta il primo consumatore di questa proiezione invece di averne una sua — che
// era il punto: se si rompe, si rompe subito e in una vista che si guarda.
function projX(p, w, win) {
  const r = win === undefined ? RANGE : win;
  return r ? ((p - r.from) / ((r.to - r.from) || 1)) * w : p * w;
}

// L'inversa, per gli hover. Senza, il mirino si stacca dal dito appena zoomi:
// sintomo confuso, causa ovvia.
function posAtX(x, w) {
  const q = Math.max(0, Math.min(1, x / (w || 1)));
  return RANGE ? RANGE.from + q * (RANGE.to - RANGE.from) : q;
}

// L'unico modo di cambiare finestra, perché c'è una cosa da non dimenticare:
// il mirino **non sopravvive** al cambio. `LAST_HOVER` è pensato per durare fra
// un ridisegno e l'altro (ed è giusto così, vedi `redrawCurrentView`), ma se la
// finestra si stringe attorno a un punto che ne sta fuori il mirino resta
// incollato al bordo, indicando un posto che non è più sotto al dito.
// La finestra di una curva, con un margine per lato.
//
// Il margine non è estetica: senza, l'ingresso e l'uscita cadono esattamente sul
// bordo della tela e quello che il pilota deve giudicare — dove comincia a
// frenare, dove riapre — resta tagliato a metà. Un quarto della curva per lato
// tiene dentro la staccata e il tratto di lancio senza far rientrare la curva
// accanto.
function cornerWindow(c) {
  if (!c) return null;
  const pad = Math.max(0.004, (c.exit - c.entry) * 0.25);
  return { from: Math.max(0, c.entry - pad), to: Math.min(1, c.exit + pad),
           source: "corner", label: c.name || ("T" + (c.index + 1)),
           // Il numero, non il nome: il rail deve accendere LA riga giusta, e su
           // una pista senza nomi curati le curve si chiamano tutte «Corner N».
           corner: c.index };
}

function setRange(r) {
  RANGE = r || null;
  if (LAST_HOVER != null && RANGE
      && (LAST_HOVER < RANGE.from || LAST_HOVER > RANGE.to)) {
    LAST_HOVER = null;
  }
}

// I valori dentro la finestra, per l'autoscala.
//
// È il passo che porta il valore analitico: senza, zoomare su una curva lascia
// il delta piatto in mezzo a una scala da giro intero e non hai guadagnato
// niente. Se la finestra non contiene campioni si torna alla serie intera — una
// scala degenere è peggio di una scala larga.
function winVals(pos, vals) {
  if (!RANGE || !pos) return vals;
  const out = [];
  for (let i = 0; i < pos.length; i++) {
    if (pos[i] >= RANGE.from && pos[i] <= RANGE.to) out.push(vals[i]);
  }
  return out.length ? out : vals;
}

// Vertical hairlines along the lap, so a feature can be placed on the track
// without counting corner bands. Where the distance is known they fall on round
// metre marks instead of every 10%, so the gridlines and the labels agree. Only
// the chart at the bottom of a stack asks for `labels` — repeating the same axis
// under every trace is noise.
function gridX(ctx, w, h, labels) {
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  const ticks = distanceTicks();
  // Il ripiego in percentuale è **del giro**: sotto finestra andrebbe fuori
  // schermo, quindi lì si ripiega su frazioni della finestra stessa.
  const frac = (q) => (RANGE ? RANGE.from + q * (RANGE.to - RANGE.from) : q);
  const xs = ticks ? ticks.map((k) => k.at)
                   : [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9].map(frac);
  for (const p of xs) {
    const x = Math.round(projX(p, w)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  if (labels) {
    ctx.font = "10px " + MONO;
    ctx.fillStyle = "rgba(255,255,255,0.4)";
    const marks = ticks ? ticks.map((k) => ({ at: k.at, s: k.m + " m" }))
                        : [0.25, 0.5, 0.75].map((q) => ({
                            at: frac(q),
                            s: RANGE ? Math.round(frac(q) * 100) + "%"
                                     : Math.round(q * 100) + "%" }));
    for (const k of marks) {
      ctx.fillText(k.s, projX(k.at, w) - ctx.measureText(k.s).width / 2, h - 4);
    }
  }
  ctx.restore();
}

function line(ctx, w, h, pos, vals, lo, hi, color, lw) {
  ctx.beginPath();
  const span = hi - lo || 1;
  // I punti fuori finestra si proiettano comunque e finiscono fuori dalla tela,
  // che li ritaglia da sola: la traccia resta continua ai bordi invece di
  // interrompersi al primo campione dentro. Ritagliare la serie serve alla
  // *scala* (vedi `winVals`), non al disegno.
  for (let i = 0; i < pos.length; i++) {
    const x = projX(pos[i], w), y = h - ((vals[i] - lo) / span) * h;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.strokeStyle = color; ctx.lineWidth = lw || 1.5; ctx.stroke();
}

// La curva in esame, accesa sopra la traccia — ma **solo se aggiunge qualcosa**.
//
// Quando la finestra contiene già soltanto quella curva, il velo non dice niente
// di nuovo e non è nemmeno neutro: un ciano al 10% steso su tutta la tela sposta
// ogni colore del grafico, e lo fa esattamente quando sei zoomato al massimo e
// stai giudicando una sfumatura.
//
// La condizione è sulla **geometria**, non sull'origine della finestra: un
// trascinamento che finisce sopra una curva riceverebbe comunque il velo se
// guardassimo solo `source`.
function cornerVeil(ctx, w, h, corner) {
  if (!corner) return;
  if (RANGE && corner.entry <= RANGE.from && corner.exit >= RANGE.to) return;
  const x0 = projX(corner.entry, w);
  ctx.fillStyle = "rgba(34,211,206,0.10)";
  ctx.fillRect(x0, 0, projX(corner.exit, w) - x0, h);
}

function crosshair(ctx, w, h, cx) {
  if (cx == null) return;
  const x = projX(cx, w);
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
}

// Semantic captions in the top-right / bottom-right corners ("left" / "right",
// "spin" / "lock") — the two ends of an axis whose *units* mean nothing to a
// driver. Where the number is the point, use gridY instead.
// Takes the height: the bottom caption used to be pinned at y=145, which is
// right for exactly one chart size and silently wrong for every other.
function axisLabel(ctx, w, h, top, bottom) {
  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px " + UI_FONT;
  ctx.fillText(top, w - 62, 12); ctx.fillText(bottom, w - 62, h - 5);
}

function redraw(cx) {
  if (!DATA) return;
  drawDelta(DATA, cx);
  drawSpeed(DATA, cx);
  drawInputs(DATA, cx);
  drawSteer(DATA, cx);
  updateReadout(DATA, cx);
}

function drawDelta(a, cx) {
  const { ctx, w, h } = setup($("c-delta"));
  const d = a.review.delta;
  let m = 0.05;
  for (const v of winVals(d.pos, d.delta_s)) m = Math.max(m, Math.abs(v));
  const tint = (c) => `rgba(${c[0]},${c[1]},${c[2]},0.10)`;
  ctx.fillStyle = tint(PAL.slow); ctx.fillRect(0, 0, w, h / 2);
  ctx.fillStyle = tint(PAL.fast); ctx.fillRect(0, h / 2, w, h / 2);
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h);
  gridY(ctx, w, h, -m, m, (v) => (v > 0 ? "+" : "") + fixz(v, 2) + "s");
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, d.pos, d.delta_s, -m, m, "#ffffff", 2);
  crosshair(ctx, w, h, cx);
}

function drawSpeed(a, cx) {
  const { ctx, w, h } = setup($("c-speed"));
  const rv = a.review.channels, rf = a.reference.channels;
  let lo = Infinity, hi = -Infinity;
  for (const v of winVals(rv.pos, rv.speed).concat(winVals(rf.pos, rf.speed))) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  lo = Math.floor(lo - 5); hi = Math.ceil(hi + 5);
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h);
  gridY(ctx, w, h, lo, hi, (v) => Math.round(v) + "");
  line(ctx, w, h, rf.pos, rf.speed, lo, hi, "#3fd0e0", 1.5);
  line(ctx, w, h, rv.pos, rv.speed, lo, hi, "#ffffff", 1.5);
  crosshair(ctx, w, h, cx);
}

function drawInputs(a, cx) {
  const { ctx, w, h } = setup($("c-inputs"));
  const rv = a.review.channels, rf = a.reference.channels;
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h);
  gridY(ctx, w, h, 0, 1, (v) => Math.round(v * 100) + "%");
  // Reference inputs (faint, dashed) — see where it braked / got on the gas.
  ctx.save();
  ctx.setLineDash([4, 3]);
  ctx.globalAlpha = 0.6;
  line(ctx, w, h, rf.pos, rf.throttle, 0, 1, "#1d8f43", 1);
  line(ctx, w, h, rf.pos, rf.brake, 0, 1, "#9e2a22", 1);
  ctx.restore();
  // Your inputs (solid, bright).
  line(ctx, w, h, rv.pos, rv.throttle, 0, 1, "#22dd66", 1.5);
  line(ctx, w, h, rv.pos, rv.brake, 0, 1, "#ff3b30", 1.5);
  crosshair(ctx, w, h, cx);
}

// Steering trace, symmetric around zero (left = up, right = down). Scale is
// ±max|steer| across both laps so the two traces share an axis. Defensive:
// the channel may be absent on older laps.
function drawSteer(a, cx) {
  const cv = $("c-steer");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const rv = a.review.channels, rf = a.reference.channels;
  const sv = rv && rv.steer, sf = rf && rf.steer;
  if (!Array.isArray(sv) || !sv.length) {
    ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.font = "11px " + UI_FONT;
    ctx.fillText("No steering data for this lap.", 10, h / 2);
    return;
  }
  let m = 0.1;
  for (const v of sv) m = Math.max(m, Math.abs(v));
  if (Array.isArray(sf)) for (const v of sf) m = Math.max(m, Math.abs(v));
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h, true);      // the bottom chart of the Compare stack: label it
  gridY(ctx, w, h, -m, m, () => "");
  // Zero line.
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  // Reference steering (cyan, faint dashed).
  if (Array.isArray(sf) && sf.length) {
    ctx.save();
    ctx.setLineDash([4, 3]); ctx.globalAlpha = 0.6;
    line(ctx, w, h, rf.pos, sf, -m, m, "#22D3CE", 1.2);
    ctx.restore();
  }
  // Your steering (white, solid).
  line(ctx, w, h, rv.pos, sv, -m, m, "#ffffff", 1.5);
  axisLabel(ctx, w, h, "left", "right");
  crosshair(ctx, w, h, cx);
}

// --- dynamics tab (G-G · lock/spin · coasting) ----------------------------
// All three read channels that were recorded since v6/v7 but never plotted:
// g_lat/g_long (grip envelope) and per-axle slip_ratio (lock/spin). Old laps
// carry all-zero here, so hasDynamics() gates the tab behind a "no data" note.
function _anyNonZero(arr) {
  return Array.isArray(arr) && arr.some((v) => Math.abs(v) > 0.001);
}
function hasDynamics(a) {
  const c = a && a.review && a.review.channels;
  if (!c) return false;
  return _anyNonZero(c.g_lat) || _anyNonZero(c.g_long) ||
    _anyNonZero(c.slip_front) || _anyNonZero(c.slip_rear);
}
function hasBalance(a) {
  const c = a && a.review && a.review.channels;
  return !!(a && a.has_map && c && _anyNonZero(c.balance));
}

function drawDynamics(cx) {
  if (!DATA) return;
  const miss = $("dyn-missing"), main = $("dyn-charts"), coast = $("dyn-coasting");
  const hasOff = Array.isArray(DATA.review.line_offset);
  const anyData = hasDynamics(DATA) || hasOff || DATA.review.tyres || hasBalance(DATA);
  // Il rimando «lo scostamento vive sotto Traiettoria» era figlio diretto di
  // #view-dynamics e fratello dei grafici: nessun ramo lo toccava, quindi su un
  // giro senza dinamica restava a schermo un bottone che manda in Traiettoria a
  // vedere lo scostamento — su un giro pre-v6 che quasi certamente non ha
  // nemmeno le coordinate, cioè un comando che non risponde. `toggle`, non
  // `add`: deve tornare quando il giro i dati ce li ha.
  $("dyn-elsewhere").classList.toggle("hidden", !anyData);
  if (!anyData) {
    if (miss) miss.classList.remove("hidden");
    if (main) main.classList.add("hidden");
    if (coast) coast.innerHTML = "";
    $("dyn-tyres").classList.add("hidden");
    $("dyn-balance-wrap").classList.add("hidden");
    // #dyn-readout passa da un solo punto, che antepone sempre `rangeChip()`.
    // Questo ramo lo chiamava con `null` APPOSTA — non per la frase, ma per
    // tenere raggiungibile la ✕ della finestra attiva, che altrimenti da qui
    // non si annulla più. Il difetto era la frase che veniva con lei: «passa il
    // mouse sui grafici per i valori punto per punto», stampata sopra la riga
    // che dice che quei grafici non ci sono. Si spegne quindi la FRASE, non la
    // scatola — e non scrivendo `#dyn-readout` da qui, che rifarebbe il difetto
    // già pagato (due punti che scrivono la stessa fascia, e uno si dimentica
    // la pastiglia): il terzo argomento dice a `updateDynReadout` che grafici
    // da leggere non ce ne sono, e lui delega a `emptyReadout`.
    updateDynReadout(DATA, null, true);
    DYN_GG = null; DYN_BAL_HIT = null;
    return;
  }
  if (miss) miss.classList.add("hidden");
  if (main) main.classList.remove("hidden");
  drawCoasting(DATA);
  DYN_GG = drawGG(DATA, cx);
  drawSlip(DATA, cx);
  drawYaw(DATA, cx);
  drawShift(DATA, cx);
  drawDynTyres(DATA, cx);
  drawBalanceRibbon(DATA, cx);
  updateDynReadout(DATA, cx);
}

// Coasting = time with neither brake nor throttle (dead time between releasing
// the brake and getting back on the gas). Trail-braking = overlap of the two.
// Samples are ~uniform in time (evenly downsampled from a 50 Hz capture), so a
// fraction of samples ≈ a fraction of the lap time — good enough for a readout.
function drawCoasting(a) {
  const el = $("dyn-coasting");
  if (!el) return;
  const c = a.review.channels;
  const thr = c.throttle || [], brk = c.brake || [];
  const n = Math.min(thr.length, brk.length);
  if (!n) { el.innerHTML = ""; return; }
  let coast = 0, trail = 0;
  for (let i = 0; i < n; i++) {
    const gas = thr[i] > 0.05, on = brk[i] > 0.05;
    if (!gas && !on) coast++;
    if (gas && on) trail++;
  }
  const lapS = (a.review.lap_time_ms || 0) / 1000;
  const coastPct = (coast / n) * 100, trailPct = (trail / n) * 100;
  const coastS = lapS * coast / n;
  let gmax = 0;
  const gl = c.g_lat || [], gL = c.g_long || [];
  for (let i = 0; i < gl.length; i++) gmax = Math.max(gmax, Math.hypot(gl[i], gL[i]));
  // Steering reversals: how many times the wheel crosses centre (a smoothness
  // proxy — lots of reversals = chasing the car / sawing at the wheel).
  const st = c.steer || [];
  let reversals = 0, prevSign = 0;
  for (let i = 0; i < st.length; i++) {
    const sign = st[i] > 0.02 ? 1 : (st[i] < -0.02 ? -1 : 0);
    if (sign !== 0) {
      if (prevSign !== 0 && sign !== prevSign) reversals++;
      prevSign = sign;
    }
  }
  const item = (k, v, sub) =>
    `<div class="item"><div class="k">${k}</div><div class="v">${v}</div>` +
    (sub ? `<div class="k">${sub}</div>` : "") + `</div>`;
  el.innerHTML =
    item(t("dyn.coasting"), `${coastPct.toFixed(0)}% · ~${coastS.toFixed(2)}s`, t("dyn.hint")) +
    item(t("dyn.trail"), `${trailPct.toFixed(0)}% ${t("dyn.ofLap")}`) +
    item(t("dyn.gmax"), `${gmax.toFixed(2)} g`) +
    item(t("dyn.smooth"), reversals, t("dyn.smoothUnit"));
}

// G-G scatter (friction circle): lateral G on X, longitudinal on Y (accel up,
// brake down). Distance from centre = grip used; a full "circle" of dots means
// the driver blends braking and cornering, a "cross" means they brake straight
// then turn (grip left on the table). Returns the screen points for the hover.
function drawGG(a, cx) {
  const cv = $("c-gg");
  if (!cv) return null;
  const { ctx, w, h } = setup(cv);
  const c = a.review.channels;
  const gx = c.g_lat || [], gy = c.g_long || [], pos = c.pos || [];
  const n = Math.min(gx.length, gy.length);
  const cx0 = w / 2, cy0 = h / 2, m = 26;
  const R = Math.min(w, h) / 2 - m;
  let gmax = 1.0, peak = 0;
  for (let i = 0; i < n; i++) {
    gmax = Math.max(gmax, Math.abs(gx[i]), Math.abs(gy[i]));
    peak = Math.max(peak, Math.hypot(gx[i], gy[i]));
  }
  gmax = Math.ceil(gmax * 2) / 2;                 // round up to a clean 0.5g grid
  const unit = R / gmax;
  const PX = (v) => cx0 + v * unit, PY = (v) => cy0 - v * unit;

  // Reference grid rings at each 1g, faint, with a value label.
  ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.fillStyle = "rgba(255,255,255,0.35)";
  ctx.font = "10px " + MONO; ctx.lineWidth = 1;
  for (let g = 1; g <= gmax + 0.01; g += 1) {
    ctx.beginPath(); ctx.arc(cx0, cy0, g * unit, 0, 6.283); ctx.stroke();
    ctx.fillText(g + "g", cx0 + 2, cy0 - g * unit + 11);
  }
  // Axes.
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(cx0 - R, cy0); ctx.lineTo(cx0 + R, cy0);
  ctx.moveTo(cx0, cy0 - R); ctx.lineTo(cx0, cy0 + R); ctx.stroke();

  // Points, coloured by whether the car is braking (red-ish) or on power
  // (green-ish); alpha low so density reads. Highlighted point drawn after.
  for (let i = 0; i < n; i++) {
    const px = PX(gx[i]), py = PY(gy[i]);
    const c2 = gy[i] < -0.05 ? PAL.slow : (gy[i] > 0.05 ? PAL.fast : [150, 156, 166]);
    ctx.fillStyle = `rgba(${c2[0]},${c2[1]},${c2[2]},0.40)`;
    ctx.beginPath(); ctx.arc(px, py, 1.8, 0, 6.283); ctx.fill();
  }
  // Peak-grip ring (how much of the circle the driver actually reaches).
  if (peak > 0) {
    ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx0, cy0, peak * unit, 0, 6.283); ctx.stroke();
    ctx.setLineDash([]);
  }
  // Axis captions.
  ctx.fillStyle = "rgba(255,255,255,0.5)"; ctx.font = "10px " + MONO;
  ctx.fillText(t("dyn.gg.accel"), cx0 + 4, cy0 - R + 10);
  ctx.fillText(t("dyn.gg.brake"), cx0 + 4, cy0 + R - 3);
  ctx.fillText(t("dyn.gg.lat"), cx0 + R - 34, cy0 - 4);

  // Highlighted moment (from the shared hover position).
  const pts = [];
  for (let i = 0; i < n; i++) pts.push({ px: PX(gx[i]), py: PY(gy[i]), pos: pos[i] });
  if (cx != null && n) {
    const i = nearest(pos, cx);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(PX(gx[i]), PY(gy[i]), 5, 0, 6.283); ctx.stroke();
  }
  return { pts };
}

// Per-axle slip ratio over the lap: front (cyan) and rear (amber), symmetric
// around zero. Below zero = the axle is locking (braking); above = spinning
// (power). Shares the position x-axis, so the crosshair lines up with the map
// and the other traces.
// Una barretta continua nei tratti in cui un aiuto elettronico sta intervenendo.
// Disegnata e non scritta: la domanda a cui risponde è «dove», e un tratto
// evidenziato la risponde senza far leggere una percentuale al pilota. Se il
// canale non c'è (giri anteriori alla v6, o un gioco che non lo espone) non
// disegna niente — meglio l'assenza di una barra sempre spenta, che si
// leggerebbe come «l'elettronica non è mai intervenuta».
function electronicsBand(ctx, w, h, pos, ch, y, colour) {
  if (!ch || !ch.length || !pos || pos.length !== ch.length) return;
  ctx.save();
  ctx.strokeStyle = colour;
  ctx.globalAlpha = 0.55;
  ctx.lineWidth = 3;
  ctx.beginPath();
  let drawing = false;
  for (let i = 0; i < ch.length; i++) {
    const on = ch[i] > 0.05;
    const x = projX(pos[i], w);
    if (on && !drawing) { ctx.moveTo(x, y); drawing = true; }
    else if (on) ctx.lineTo(x, y);
    else drawing = false;
  }
  ctx.stroke();
  ctx.restore();
}

function drawSlip(a, cx) {
  const cv = $("c-slip");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const c = a.review.channels;
  const sf = c.slip_front || [], sr = c.slip_rear || [], pos = c.pos || [];
  let m = 0.15;
  for (const v of winVals(pos, sf)) m = Math.max(m, Math.abs(v));
  for (const v of winVals(pos, sr)) m = Math.max(m, Math.abs(v));
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h);
  gridY(ctx, w, h, -m, m, (v) => (Math.abs(v) < 1e-9 ? "0" : v.toFixed(2)));
  // Dove l'elettronica sta lavorando, PRIMA delle tracce, così la barretta sta
  // sotto e non le copre. Senza, questo grafico mente per omissione: col TC
  // attivo lo slip posteriore resta piatto perché è il TC a tenercelo, e un
  // pilota che vede la traccia a zero conclude che ha trazione da vendere.
  // Non è una diagnosi, è il contesto senza cui l'altra non si legge.
  electronicsBand(ctx, w, h, pos, c.tc, h - 6, "#FFB020");
  electronicsBand(ctx, w, h, pos, c.abs, h - 11, "#22D3CE");
  // Zero line.
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, pos, sr, -m, m, "#FFB020", 1.4);   // rear
  line(ctx, w, h, pos, sf, -m, m, "#22D3CE", 1.5);   // front
  axisLabel(ctx, w, h, t("dyn.slip.spin"), t("dyn.slip.lock"));
  crosshair(ctx, w, h, cx);
}

// Rotation vs steering: the steering input (white) and the car's yaw/rotation
// (orange), each scaled to its own range so they overlay. Yaw is flipped by the
// title's sign convention (see balance _YAW_SIGN) so a clean corner has the two
// tracking together; where yaw lags the wheel = understeer, leads it = oversteer.
function drawYaw(a, cx) {
  const cv = $("c-yaw");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const c = a.review.channels;
  const pos = c.pos, st = c.steer || [], yw = c.yaw || [];
  // **Una scala sola per due tracce che il titolo dice di confrontare.**
  //
  // Prima ognuna era normalizzata al proprio picco. Sembra ragionevole e
  // distrugge esattamente l'unica cosa che questo grafico esiste per mostrare:
  // normalizzando separatamente, un giro con sottosterzo cronico — sterzo molto
  // più grande della rotazione che ne segue — disegna due curve che si seguono
  // benissimo. Sopravviveva solo lo sfasamento, e la frase «dovrebbero
  // seguirsi» era falsa per costruzione.
  //
  // Lo sterzo è la grandezza di riferimento perché è l'input: la rotazione è
  // portata sulla sua scala dal rapporto fra i due picchi, così a
  // proporzionalità perfetta le tracce coincidono e ogni scostamento è
  // l'ampiezza che manca. Il fattore è dichiarato sotto, perché una scala
  // implicita è la stessa bugia di prima detta più piano.
  let ms = 1e-6, my = 1e-6;
  for (const v of winVals(pos, st)) ms = Math.max(ms, Math.abs(v));
  for (const v of winVals(pos, yw)) my = Math.max(my, Math.abs(v));
  const k = ms / my;                       // yaw -> unità di sterzo
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h);
  gridY(ctx, w, h, -ms, ms, (v) => (Math.abs(v) < 1e-9 ? "0" : v.toFixed(2)));
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, pos, yw.map((v) => -v * k), -ms, ms, "#FFB020", 1.4);
  line(ctx, w, h, pos, st, -ms, ms, "#ffffff", 1.5);
  axisLabel(ctx, w, h, "left", "right");
  crosshair(ctx, w, h, cx);
}

// Revs & shift points: rpm over the lap with up/down-shift markers where the
// gear number changes (▲ upshift near the top, ▼ downshift near the bottom).
function drawShift(a, cx) {
  const cv = $("c-rpm");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const c = a.review.channels;
  const pos = c.pos, rpm = c.rpm || [], gear = c.gear || [];
  if (!rpm.length) return;
  let lo = Infinity, hi = -Infinity;
  for (const v of winVals(pos, rpm)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
  cornerBands(ctx, w, h, a.corners);
  gridX(ctx, w, h, true);
  gridY(ctx, w, h, lo, hi, (v) => Math.round(v / 100) * 100 + "");
  line(ctx, w, h, pos, rpm, lo, hi, "#34E08A", 1.4);
  const gnum = (g) => { const n = parseInt(g, 10); return isNaN(n) ? null : n; };
  for (let i = 1; i < gear.length; i++) {
    const g0 = gnum(gear[i - 1]), g1 = gnum(gear[i]);
    if (g0 == null || g1 == null || g0 === g1) continue;
    const x = projX(pos[i], w), up = g1 > g0, y = up ? 10 : h - 4;
    ctx.fillStyle = up ? "#22D3CE" : "#FFB020";
    ctx.beginPath();
    if (up) { ctx.moveTo(x, y - 6); ctx.lineTo(x - 4, y); ctx.lineTo(x + 4, y); }
    else { ctx.moveTo(x, y); ctx.lineTo(x - 4, y - 6); ctx.lineTo(x + 4, y - 6); }
    ctx.closePath(); ctx.fill();
  }
  crosshair(ctx, w, h, cx);
}

// Tyres across THIS lap (not the stint): core temp and pressure per wheel over
// the position axis, so heat build-up and pressure swings show corner by corner.
// Reuses the stint view's axle-by-colour + side-by-dash encoding (TYRE_SERIES).
function drawDynTyres(a, cx) {
  const sec = $("dyn-tyres");
  const ty = a.review.tyres;
  if (!sec) return;
  if (!ty) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");
  $("dyn-tyre-legend").innerHTML = TYRE_SERIES.map((s) =>
    `<span class="tl"><span class="sw" style="border-top:2px ${s.dash.length ? "dashed" : "solid"} ${s.color}"></span>` +
    `${t("tyre." + s.key)}</span>`).join("");
  const pos = a.review.channels.pos;
  drawTyreOverLap($("c-dtyre-temp"), ty.temp, pos, a.corners, cx, "°");
  drawTyreOverLap($("c-dtyre-press"), ty.press, pos, a.corners, cx, "");
}

function drawTyreOverLap(cv, wheels, pos, corners, cx, unit) {
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  let lo = Infinity, hi = -Infinity;
  for (const s of TYRE_SERIES) for (const v of (wheels[s.key] || [])) {
    lo = Math.min(lo, v); hi = Math.max(hi, v);
  }
  if (!isFinite(lo)) return;
  const rlo = lo, rhi = hi;
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.15; lo -= pad; hi += pad;
  cornerBands(ctx, w, h, corners);
  for (const s of TYRE_SERIES) {
    const vals = wheels[s.key] || [];
    if (!vals.length) continue;
    ctx.save(); ctx.setLineDash(s.dash);
    line(ctx, w, h, pos, vals, lo, hi, s.color, 1.4);
    ctx.restore();
  }
  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px " + MONO;
  ctx.fillText(rhi.toFixed(unit ? 0 : 1) + unit, w - 44, 12);
  ctx.fillText(rlo.toFixed(unit ? 0 : 1) + unit, w - 44, h - 4);
  crosshair(ctx, w, h, cx);
}

// Balance ribbon: the racing line coloured by handling (blue understeer / red
// oversteer). Reuses drawMapTo in "balance" mode. Hidden unless the lap has a
// map and a non-flat balance signal (yaw recorded from v6).
function drawBalanceRibbon(a, cx) {
  const wrap = $("dyn-balance-wrap");
  if (!wrap) return;
  if (!hasBalance(a)) { wrap.classList.add("hidden"); DYN_BAL_HIT = null; return; }
  wrap.classList.remove("hidden");
  const hit = drawMapTo($("c-balance"), null, a, cx, "balance");
  if (hit) DYN_BAL_HIT = hit;
}

function dynReadoutHTML(a, p) {
  const c = a.review.channels;
  const i = nearest(c.pos, p);
  const corner = (a.corners || []).find((x) => p >= x.entry && p <= x.exit);
  const where = corner ? `<b class="muted">${corner.name}</b> &nbsp;·&nbsp; ` : "";
  const gl = (c.g_lat || [])[i] || 0, gL = (c.g_long || [])[i] || 0;
  const gt = Math.hypot(gl, gL);
  const sf = (c.slip_front || [])[i] || 0, sr = (c.slip_rear || [])[i] || 0;
  let extra = "";
  if (Array.isArray(a.review.line_offset)) {
    const off = a.review.line_offset[i] || 0;
    extra += ` &nbsp;·&nbsp; ${t("dyn.ro.off")} <b>${off >= 0 ? "+" : ""}${off.toFixed(1)}m</b>`;
  }
  return where +
    `<b>${t("ro.pos")} ${posLabel(p)}</b> &nbsp;·&nbsp; ` +
    `${t("dyn.ro.g")} <b>${gt.toFixed(2)}g</b> <span class="muted">(${t("dyn.ro.lat")} ${gl.toFixed(2)}, ${t("dyn.ro.lon")} ${gL.toFixed(2)})</span> &nbsp;·&nbsp; ` +
    `${t("dyn.ro.slipF")} <b>${sf.toFixed(2)}</b>  ${t("dyn.ro.slipR")} <b>${sr.toFixed(2)}</b>` + extra;
}

function updateDynReadout(a, p, bare) {
  const el = $("dyn-readout");
  if (!el) return;
  // `bare`: i grafici non sono in vista (il ramo «nessun dato di dinamica»).
  // Non è `p == null`, che vuol dire «i grafici ci sono e nessuno ci sta sopra
  // col mouse» — lì l'invito a passarci sopra è valido. Vedi `emptyReadout`.
  if (bare) { emptyReadout(el); return; }
  // Il verso di ritorno: qui i grafici ci sono, quindi la fascia torna accesa
  // anche se il giro di prima l'aveva spenta.
  el.classList.remove("hidden");
  const chip = rangeChip();
  // Guardia `p != null`, come in `hoverTo`: `drawDynamics(cx)` la richiama con
  // `cx` nullo a ogni ridisegno di vista intera (cambio scheda, resize), e
  // un'assegnazione incondizionata qui azzererebbe `LAST_HOVER` un attimo dopo
  // che quella guardia l'aveva protetto — la scheda Dinamica non manterrebbe
  // mai il mirino congelato.
  if (p != null) LAST_HOVER = p;
  if (p == null) { el.innerHTML = chip + t("dyn.readout"); wireRangeClear(el); return; }
  el.innerHTML = chip + dynReadoutHTML(a, p);
  wireRangeClear(el);
}

// --- your braking points --------------------------------------------------
// The community's most upvoted braking reference is a static sheet of Monza,
// and its own author lists the holes: the points move between cars and between
// a cold track and a hot one. This one is measured from your own recent laps in
// one temperature band, so it has none of them — and it says so in its header,
// because a sheet that doesn't state its conditions is the static one again.

let SHEET = null;       // last /api/braking payload

async function loadBraking() {
  if (!CURRENT) return;
  const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track });
  let b;
  try { b = await getJSON("/api/braking?" + q.toString()); }
  // Non svuotare: `renderBrakeSheet(null)` ha già il testo per «nessuna riga»,
  // due righe più sotto. Era l'unico punto del codice dove un errore produceva
  // **silenzio assoluto** — pannello a stringa vuota, zero testo, zero motivo —
  // ed è il caso normale di chi su ACC tocca i limiti a ogni giro, perché
  // /api/braking fa 404 finché non c'è un giro valido e pulito.
  catch (e) { SHEET = null; renderBrakeSheet(null); return; }
  SHEET = b;
  renderBrakeSheet(b);
}

function renderBrakeSheet(b) {
  const el = $("brakesheet");
  if (!el) return;
  if (!b || !b.rows.length) {
    el.innerHTML = `<h3>${t("brk.title")}</h3>` +
      `<div class="clean muted">${t("brk.none")}</div>`;
    return;
  }
  const temps = (b.road_temp_from != null)
    ? tf(b.road_temp_from === b.road_temp_to ? "brk.temp1" : "brk.temp",
         { from: b.road_temp_from.toFixed(1), to: b.road_temp_to.toFixed(1) })
    : t("brk.noTemp");

  let body = "";
  for (const r of b.rows) {
    // The spread is the number a static sheet can't have: whether you have a
    // braking point at all, or a different one every lap. Shown in km/h (what
    // the dash says) with the metres it works out to (what the sheets people
    // share are written in) — approximate, and marked as such.
    const spread = r.spread_kmh
      ? `±${r.spread_kmh}` + (r.spread_m ? ` <span class="muted">≈ ${r.spread_m} m</span>` : "")
      : `<span class="muted">${t("brk.repeatable")}</span>`;
    body += `<tr>` +
      `<td class="vc">${r.name}</td>` +
      `<td class="vn big">${r.speed_kmh}<span class="muted"> km/h</span></td>` +
      `<td class="vn">${r.gear}</td>` +
      // Editable, and this is roadmap item 2 arriving from the only place it
      // could. The positions have been measured for a while; the words could
      // not be sourced — two guides contradict each other on almost every Imola
      // corner, and no measurement arbitrates between a 50 m board and a 100 m
      // one. The driver is looking at the thing.
      `<td class="ref"><button type="button" class="mark" data-pos="${r.pos}" ` +
      `data-typed="${r.typed ? 1 : 0}" title="${escAttr(t("brk.mark.edit"))}">` +
      (r.landmark ? escAttr(r.landmark)
                  : `<span class="muted">– <span class="pencil">✎</span></span>`) +
      `</button></td>` +
      `<td class="vn">${r.distance_m ? r.distance_m + " m" : "–"}</td>` +
      `<td class="vn">${r.vmin_kmh}<span class="muted"> / ${r.gear_min}</span></td>` +
      `<td class="vn">${spread}</td></tr>`;
  }
  el.innerHTML =
    `<h3>${t("brk.title")} ` +
    `<button type="button" id="brk-csv" class="mini-btn" title="${t("brk.csv.title")}">⬇ CSV</button>` +
    `<button type="button" id="brk-print" class="mini-btn" title="${t("brk.print.title")}">🖨</button>` +
    `</h3>` +
    `<div class="sheet-sub">${tf("brk.sub", { laps: b.laps })} · ${temps}</div>` +
    `<table class="vmin-table wide"><thead><tr>` +
    `<th>${t("brk.c.corner")}</th><th>${t("brk.c.speed")}</th><th>${t("brk.c.gear")}</th>` +
    `<th>${t("brk.c.landmark")}</th><th>${t("brk.c.zone")}</th>` +
    `<th>${t("brk.c.vmin")}</th><th>${t("brk.c.spread")}</th>` +
    `</tr></thead><tbody>${body}</tbody></table>` +
    `<p class="sheet-note">${t("brk.note")}</p>`;

  for (const btn of el.querySelectorAll("button.mark")) {
    btn.onclick = () => editMark(btn);
  }
  $("brk-csv").onclick = () => {
    const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track,
                                    fmt: "csv", lang: LANG() });
    window.location = "/api/braking?" + q.toString();
  };
  // Printing is the point: the sheet people shared was printed and taped up.
  // The print stylesheet hides everything but this section.
  $("brk-print").onclick = () => window.print();
}

// One cell of the braking sheet, turned into a field. The row already knows
// where it brakes; what it is missing is what you look at when you do.
function editMark(btn) {
  const cell = btn.parentElement;
  const pos = btn.dataset.pos;
  const typed = btn.dataset.typed === "1";
  // Pre-filled only with a phrase the driver typed, never with one we ship:
  // otherwise one Save with nothing changed adopts our wording as theirs, where
  // it then outranks the table it came from. Same rule as the corner names.
  const now = typed ? btn.textContent.trim() : "";
  cell.innerHTML =
    `<input type="text" class="mark-in" maxlength="80" value="${escAttr(now)}" ` +
    `placeholder="${escAttr(t("brk.mark.hint"))}">` +
    `<button type="button" class="chip on save">${t("line.name.save")}</button>` +
    (typed ? `<button type="button" class="chip drop">${t("line.name.drop")}</button>` : "");
  const box = cell.querySelector("input");
  box.focus(); box.select();
  const send = async (text) => {
    try {
      const r = await fetch("/api/braking-reference", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track: CURRENT.track, pos: parseFloat(pos), text }),
      });
      if (!r.ok) throw new Error(r.status);
    } catch (e) {
      cell.innerHTML = `<span class="warn">${t("line.name.err")}</span>`;
      return;
    }
    // Re-fetch the sheet rather than patch the cell: the same phrase is spoken
    // by the debrief, so a screen where only this cell changed is the app
    // disagreeing with itself.
    SHEET = null;
    await loadBraking();
  };
  box.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); send(box.value); }
    if (e.key === "Escape") renderBrakeSheet(SHEET);
  };
  cell.querySelector(".save").onclick = () => send(box.value);
  const drop = cell.querySelector(".drop");
  if (drop) drop.onclick = () => send("");
}

// --- the line you drove ---------------------------------------------------
// The map beside Compare draws two lines over a whole lap and leaves the reading
// to the eye. This one takes a corner at a time and answers the questions the eye
// can't: how far off the reference line you were, in metres and on which side;
// where your slowest point sits compared with the reference's; how tight an arc
// you actually drove. Every number arrives from /api/trajectory already decided
// and already worded (see trajectory.py) — the code below is drawing.

let LINE = null;        // last /api/trajectory payload
let LINE_I = 0;         // which corner is on screen
let LINE_HIT = null;    // screen transform of the zoomed corner, for its hover
// How much the gap between the two lines is exaggerated on the zoomed map.
// At true scale a corner is 200 m across and a good driver's line sits 1-2 m
// off the reference: a few pixels, which is a real answer to a question nobody
// can read. So the gap can be blown up — and when it is, the canvas says so and
// the scale bar keeps measuring real ground, because an unlabelled exaggeration
// is just a wrong drawing.
//
// ×5 was here too and was removed on 2026-08-04, measured on 293 corner-lap
// pairs in the archive. The widest gap inside a corner is 0.02 m at the 25th
// percentile, 1.00 m at the median and 2.54 m at the 75th, and a typical corner
// crop is 124 m across — 5.75 px/m. So ×3 is what earns its place: it takes the
// median from 6 px, a thread, to 17, which is where a shape reads. ×5 helped
// neither end. On the laps too close together to see it was still invisible
// (0.6 px — no magnification saves 2 cm), and on an ordinary lap it drew 2.5 m
// as 73 px, a quarter of the canvas: past there the picture stops resembling
// the corner, and both settings pay the same price of hiding the road.
let LINE_MAG = 1;

async function loadLine() {
  if (!CURRENT) return;
  const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track });
  const lap = $("lap").value, base = pinnedBaseline();
  if (lap) q.set("lap", lap);
  if (base) q.set("baseline", base);
  setPanelLoading("line-summary", t("load.line"));
  let L;
  try { L = await getJSON("/api/trajectory?" + q.toString()); }
  catch (e) {
    LINE = null;
    $("line-summary").innerHTML =
      `<div class="item"><div class="v">—</div><div class="k">${t("err.line")}</div></div>`;
    $("line-chips").innerHTML = ""; $("line-facts").innerHTML = "";
    $("line-table").innerHTML = "";
    return;
  }
  LINE = L;
  if (LINE_I >= L.corners.length) LINE_I = 0;
  renderLine(null);
}

// Metres, signed, with the side named in words. A bare "-1.4 m" needs a legend
// every time it's read; "1.4 m outside" doesn't.
function offWord(m, corner) {
  if (m == null || !isFinite(m)) return "–";
  const v = Math.abs(m);
  if (v < 0.15) return t("line.same");
  // Where there is no single inside we say which side of the LINE instead of
  // guessing which side of the road. Two cases: a corner the detector couldn't
  // classify (no coordinates on the baseline), and a chicane — whose inside is
  // on the right for one half and on the left for the other, so any single
  // answer is confidently wrong about half the corner.
  const known = corner && corner.sided !== false && corner.direction;
  const word = known ? (m > 0 ? t("line.in") : t("line.out"))
                     : (m > 0 ? t("line.right") : t("line.left"));
  return `${v.toFixed(1)} m ${word}`;
}

function renderLine(cx) {
  const L = LINE;
  const shell = [$("line-chips"), $("line-facts"), $("line-table")];
  const grid = document.querySelector(".line-grid");
  const charts = document.querySelector("#view-line main");
  if (!L || !L.corners.length) {
    // Two different nothings, and they need different words: a lap recorded
    // before the map existed has no geometry at all, while a lap of a track
    // where no corner was detected has geometry we simply can't cut up.
    const noMap = !L || !L.has_map;
    $("line-missing").classList.toggle("hidden", !noMap);
    if (grid) grid.classList.add("hidden");
    if (charts) charts.classList.add("hidden");
    // La riga di lettura non era in questo elenco, e non la riscriveva nessuno:
    // se il giro di prima aveva le coordinate e ci si era passato il mouse, i
    // suoi numeri punto per punto restavano sopra «questi giri non hanno
    // coordinate», veri di un altro giro e per sempre.
    emptyReadout($("line-readout"));
    for (const el of shell) if (el) el.innerHTML = "";
    $("line-summary").innerHTML = (L && !noMap)
      ? `<div class="item"><div class="v">—</div><div class="k">${t("line.none")}</div></div>` : "";
    return;
  }
  $("line-missing").classList.add("hidden");
  if (grid) grid.classList.remove("hidden");
  if (charts) charts.classList.remove("hidden");
  LINE_I = Math.max(0, Math.min(LINE_I, L.corners.length - 1));

  // Il rail sceglie una curva per NUMERO (`RANGE.corner`, il campo `index` di
  // `/api/analysis`), la Traiettoria per POSIZIONE nel proprio elenco
  // (`LINE_I`, indice dentro `L.corners`, da `/api/trajectory` — un elenco che
  // può essere diverso). Quando la finestra arriva da fuori questa vista (dal
  // rail, non da un chip qui sotto) va tradotta cercando la curva con lo
  // stesso `index`; se non c'è — le due liste possono divergere — nessun chip
  // finge di seguirla: la finestra resta accesa, la Traiettoria resta dov'era.
  let railSynced = false;
  if (RANGE && RANGE.corner != null) {
    const pos = L.corners.findIndex((cc) => cc.index === RANGE.corner);
    if (pos >= 0) { LINE_I = pos; railSynced = true; }
  }

  const lap = L.lap;
  const item = (k, v, sub, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div>` +
    (sub ? `<div class="k">${sub}</div>` : "") + `</div>`;
  const extra = lap.extra_m;
  $("line-summary").innerHTML =
    item(t("line.extra"), `${extra >= 0 ? "+" : ""}${extra.toFixed(1)} m`,
         tf("line.extraHint", { you: lap.path_m, ref: lap.ref_path_m }),
         extra > 0 ? "warn" : "") +
    item(t("line.mean"), `${lap.mean_off_m.toFixed(2)} m`) +
    item(t("line.worst"), `${lap.max_off_m.toFixed(1)} m`, lap.max_off_where) +
    item(t("line.corners"), L.corners.length);

  // «Tutto il giro» è il primo chip e non uno stato assente: finché la finestra
  // non esiste il pilota deve poterci tornare con lo stesso gesto con cui ne è
  // uscito, e uno stato che si raggiunge solo deselezionando non si trova.
  $("line-chips").innerHTML =
    `<button type="button" class="chip${RANGE ? "" : " on"}" data-whole="1">` +
    `${t("line.whole")}</button>` +
    L.corners.map((c, i) =>
      `<button type="button" class="chip${railSynced && i === LINE_I ? " on" : ""}" data-i="${i}">` +
      `T${c.index + 1}</button>`).join("") +
    `<span class="chip-group"><span class="chip-label">${t("line.mag")}</span>` +
    [1, 3].map((z) =>
      `<button type="button" class="chip mag${z === LINE_MAG ? " on" : ""}" ` +
      `data-mag="${z}">×${z}</button>`).join("") + `</span>`;
  for (const b of $("line-chips").querySelectorAll(".chip[data-i]")) {
    b.onclick = () => {
      LINE_I = parseInt(b.dataset.i, 10);
      setRange(cornerWindow(L.corners[LINE_I]));
      // Non renderLine(null) diretto: questa scelta aggiorna anche RANGE, e il
      // rail — fuori da questa vista — deve accorgersene (riga accesa, mirino
      // sulla mappa). redrawCurrentView ridisegna la Traiettoria come prima E
      // poi il rail, invece di lasciarlo con la riga di un'altra curva accesa.
      redrawCurrentView();
    };
  }
  const whole = $("line-chips").querySelector(".chip[data-whole]");
  if (whole) whole.onclick = () => { setRange(null); redrawCurrentView(); };
  for (const b of $("line-chips").querySelectorAll(".chip[data-mag]")) {
    b.onclick = () => { LINE_MAG = parseInt(b.dataset.mag, 10); renderLine(null); };
  }

  const c = L.corners[LINE_I];
  const shape = [c.direction ? t("line.dir." + c.direction) : "",
                 c.kind ? t("line.kind." + c.kind) : ""].filter(Boolean).join(" · ");
  renderCornerTitle(L, c, shape);

  // The road is in the legend only when it is on the drawing — and it is named
  // "asphalt", never "track limits": a clean lap uses the kerbs and sits a
  // couple of metres past this line (see SPIKE-BORDI.md).
  const legRoad = $("leg-road");
  if (legRoad) {
    const mesh = LINE_MAG > 1 ? null : (L.corners[LINE_I] || {}).line;
    const surf = mesh && mesh.road;
    const road = LINE_MAG > 1 ? null : L.edges;
    legRoad.classList.toggle("hidden", !(surf || road));
    if (surf) {
      // Con le superfici del gioco i cordoli CI SONO: dire il contrario
      // sarebbe una didascalia che contraddice il proprio disegno.
      $("leg-road-text").textContent = t("line.leg.mesh");
    } else if (road) {
      $("leg-road-text").textContent = tf("line.leg.road", { m: road.width_m });
    }
  }

  renderLineFacts(c);
  renderLineTable(L);
  LINE_HIT = drawCornerZoom(L, c, cx);
  drawOffsetTrace(L, c, cx);
  drawCurvature(L, c, cx);
  updateLineReadout(L, cx);
}

// Naming a corner, which is the only route onto the circuits nobody could
// curate. Fourteen of the twenty-six bundled circuits have a name table, and
// ten ACC circuits have no bundled geometry at all — on those, the driver is
// the only source there is.
//
// It lives HERE, on the zoomed corner, and not in a settings page with a list
// of positions: you are looking at the corner's shape while you name it, so
// there is no way to name the wrong one by mistyping a number.
let LINE_EDIT = -1;     // which corner is being renamed, -1 for none

function renderCornerTitle(L, c, shape) {
  const el = $("line-corner-title");
  if (!el) return;
  if (LINE_EDIT !== LINE_I) {
    el.innerHTML =
      `<b>${escAttr(c.name)}</b>${shape ? ` <small>${shape}</small>` : ""}` +
      `<button type="button" class="rename" id="corner-rename" ` +
      `title="${escAttr(t("line.name.edit"))}" ` +
      `aria-label="${escAttr(t("line.name.edit"))}">✎</button>`;
    $("corner-rename").onclick = () => { LINE_EDIT = LINE_I; renderLine(null); };
    return;
  }
  // Pre-filled only when the name on screen is one the driver typed. Filling it
  // with "Corner 1" — the detector's count, not a name — means one Save with
  // nothing changed stores that number *as* a name, where it then outranks
  // every curated table and looks identical to the fallback it replaced.
  el.innerHTML =
    `<input type="text" id="corner-name" maxlength="40" ` +
    `value="${c.typed ? escAttr(c.name) : ""}" ` +
    `placeholder="${escAttr(t("line.name.hint"))}">` +
    `<button type="button" class="chip on" id="corner-save">${t("line.name.save")}</button>` +
    // "Remove" only where there is something to remove: on a corner still
    // called "Corner 1" it offers to undo a thing that never happened.
    (c.typed
      ? `<button type="button" class="chip" id="corner-drop">${t("line.name.drop")}</button>`
      : "");
  const box = $("corner-name");
  box.focus();
  box.select();
  // Enter saves and Escape gives up, because a two-button row that only works
  // with the mouse is a form, and this is a caption.
  box.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); saveCornerName(box.value); }
    if (e.key === "Escape") { LINE_EDIT = -1; renderLine(null); }
  };
  $("corner-save").onclick = () => saveCornerName(box.value);
  // "Remove" is the undo, and it is the same gesture as naming: whoever typed
  // a name onto the wrong apex must not have to go and find a JSON file.
  if ($("corner-drop")) $("corner-drop").onclick = () => saveCornerName("");
}

async function saveCornerName(name) {
  const L = LINE;
  if (!L || !L.corners[LINE_I]) return;
  const c = L.corners[LINE_I];
  try {
    const r = await fetch("/api/corner-name", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track: L.track, pos: c.apex, name: name }),
    });
    if (!r.ok) throw new Error(r.status);
  } catch (e) {
    $("line-readout").innerHTML = `<span class="warn">${t("line.name.err")}</span>`;
    return;
  }
  LINE_EDIT = -1;
  // Re-fetch rather than patch the one label on screen. The name is used by the
  // debrief, the losses, the braking sheet and the coach's voice, and a screen
  // where only the title changed is an app disagreeing with itself — the
  // failure `laps_dir` already shipped once.
  SHEET = null;                       // the braking sheet re-fetches on its tab
  await loadLine();
  if (CURRENT) await loadCombo(CURRENT, $("lap").value, pinnedBaseline());
}

// Where your apex is against the reference's — or why that question has no
// answer here.
//
// Two cases the plain number got wrong, both measured across the archive before
// this existed. Through a long corner the bottom of the speed trace is flat for
// ~100 m (Fagnes, Casio Triangle, Tamburello), so two identical laps could be
// reported 60 m apart — a difference to go and chase that isn't there. And on a
// lap that spun, the "apex" moved 174 m because the car nearly stopped somewhere
// else, which is a true number and a false sentence.
function apexWord(c) {
  // A dash, with the reason on hover: the chip above already says it in full,
  // and a sentence in a right-aligned number column wrecks the row it sits in.
  if (c.off_here) return `<span title="${escAttr(t("line.apexOff"))}">–</span>`;
  if (c.apex_flat_m > 0) {
    return `${t("line.sameSpot")} <span class="muted">${
      tf("line.apexFlat", { m: Math.round(c.apex_flat_m) })}</span>`;
  }
  const shift = c.apex_shift_m;
  if (Math.abs(shift) < 0.5) return t("line.sameSpot");
  return `${Math.abs(shift).toFixed(0)} m ${shift < 0 ? t("line.earlier") : t("line.later")}`;
}

function renderLineFacts(c) {
  const el = $("line-facts");
  if (!el) return;
  const row = (k, v, sub) =>
    `<div class="fact"><span class="fk">${k}</span><span class="fv">${v}</span>` +
    (sub ? `<span class="fs">${sub}</span>` : "") + `</div>`;
  const apex = apexWord(c);
  const arc = (c.radius_m && c.radius_ref_m)
    ? `${Math.round(c.radius_m)} m <span class="muted">${t("line.f.vs")} ${Math.round(c.radius_ref_m)} m</span>`
    : "–";
  const dist = `${c.extra_m >= 0 ? "+" : ""}${c.extra_m.toFixed(1)} m`;
  el.innerHTML =
    (c.tags.length
      ? `<div class="tagrow">` + c.tags.map((x) => `<span class="ltag">${x}</span>`).join("") + `</div>`
      : `<div class="tagrow"><span class="ltag ok">${t("line.same")}</span></div>`) +
    row(t("line.f.apex"), apex) +
    row(t("line.f.entry"), offWord(c.entry_m, c)) +
    row(t("line.f.apexoff"), offWord(c.apex_m, c)) +
    row(t("line.f.exit"), offWord(c.exit_m, c)) +
    // `widest_m` is the biggest excursion on the minus side — the outside of a
    // corner, or simply the LEFT of the line where there is no single inside.
    row(t("line.f.widest"), c.widest_m
        ? `${c.widest_m.toFixed(1)} m ${c.sided === false ? t("line.left") : t("line.out")}`
        : t("line.same")) +
    row(t("line.f.radius"), arc) +
    row(t("line.f.extra"), dist) +
    row(t("line.f.vmin"), `${c.vmin} <span class="muted">${t("line.f.vs")} ${c.vmin_ref} km/h</span>`) +
    row(t("line.f.vexit"), `${c.vexit} <span class="muted">${t("line.f.vs")} ${c.vexit_ref} km/h</span>`);
}

// The dataset behind the view: one row per corner, the selected one highlighted,
// clickable. Sorted by corner number rather than by severity — this is the table
// you read alongside a lap, and a table whose rows move around between two laps
// is one you have to re-read every time.
function renderLineTable(L) {
  const el = $("line-table");
  if (!el) return;
  const cell = (m, c) => {
    const cls = m == null || Math.abs(m) < 0.15 ? "" : (m > 0 ? "in" : "out");
    return `<td class="vn ${cls}">${offWord(m, c)}</td>`;
  };
  let body = "";
  L.corners.forEach((c, i) => {
    // A dash, not a zero: "no answer here" and "the apex didn't move" are the
    // same cell in a table, and only the tooltip can tell them apart.
    const quiet = c.off_here || c.apex_flat_m > 0 || Math.abs(c.apex_shift_m) < 0.5;
    const why = c.off_here ? t("line.apexOff")
              : (c.apex_flat_m > 0 ? tf("line.apexFlat", { m: Math.round(c.apex_flat_m) })
                                   : t("line.sameSpot"));
    const shift = quiet
      ? `<span title="${escAttr(why)}">–</span>`
      : `${c.apex_shift_m > 0 ? "+" : "−"}${Math.abs(c.apex_shift_m).toFixed(0)} m`;
    const dv = c.vmin - c.vmin_ref;
    body += `<tr class="${i === LINE_I ? "on" : ""}" data-i="${i}">` +
      `<td class="vc">${c.name}` +
      (c.off_here ? ` <span class="off-track" title="${escAttr(t("line.apexOff"))}">!</span>` : "") +
      `</td>` +
      `<td class="vn">${shift}</td>` +
      cell(c.entry_m, c) + cell(c.apex_m, c) + cell(c.exit_m, c) +
      `<td class="vn">${c.radius_m ? Math.round(c.radius_m) : "–"}` +
      `<span class="muted"> / ${c.radius_ref_m ? Math.round(c.radius_ref_m) : "–"}</span></td>` +
      `<td class="vn">${c.extra_m >= 0 ? "+" : ""}${c.extra_m.toFixed(1)}</td>` +
      `<td class="vn ${dv > 0 ? "faster" : (dv < 0 ? "slower" : "")}">` +
      `${c.vmin}<span class="muted"> / ${c.vmin_ref}</span></td></tr>`;
  });
  el.innerHTML =
    `<h3>${t("line.table")} <button type="button" id="line-csv" class="mini-btn" ` +
    `title="${t("line.csv.title")}">${t("line.csv")}</button></h3>` +
    `<table class="vmin-table wide"><thead><tr>` +
    `<th>${t("line.t.corner")}</th><th>${t("line.t.apex")}</th>` +
    `<th>${t("line.t.entry")}</th><th>${t("line.t.apexoff")}</th><th>${t("line.t.exit")}</th>` +
    `<th>${t("line.t.radius")}</th><th>${t("line.t.extra")}</th><th>${t("line.t.vmin")}</th>` +
    `</tr></thead><tbody>${body}</tbody></table>`;
  for (const tr of el.querySelectorAll("tbody tr")) {
    tr.onclick = () => { LINE_I = parseInt(tr.dataset.i, 10); renderLine(null); };
  }
  const btn = $("line-csv");
  if (btn) btn.onclick = () => {
    const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track,
                                    fmt: "csv", lang: LANG() });
    if ($("lap").value) q.set("lap", $("lap").value);
    if (pinnedBaseline()) q.set("baseline", pinnedBaseline());
    window.location = "/api/trajectory?" + q.toString();
  };
}

// One corner, zoomed. The two lines with the area between them shaded: the band
// IS the difference, which is the one thing a driver wants from this picture and
// the one thing two overlaid lines at track scale never show.
function drawCornerZoom(L, c, cx) {
  const cv = $("c-corner");
  if (!cv) return null;
  const { ctx, w, h } = setup(cv);
  const you = c.line.you;
  let ref = c.line.ref;
  if (!you.x.length || !ref.x.length) return null;

  // Pair each of your points with the reference point at the same track
  // position — a running pointer, since both crops are sorted by position.
  const pair = [];
  let j = 0;
  for (let i = 0; i < you.pos.length; i++) {
    while (j + 1 < ref.pos.length &&
           Math.abs(ref.pos[j + 1] - you.pos[i]) < Math.abs(ref.pos[j] - you.pos[i])) j++;
    pair.push(j);
  }
  // Your line as drawn: the real one at ×1, otherwise pushed away from the
  // reference by the magnification. The difference between paired points is
  // almost entirely lateral (they're matched by track position), so blowing up
  // the whole vector reads as "further off line" and not as "further round the
  // corner".
  let yx = [], yz = [];
  for (let i = 0; i < you.x.length; i++) {
    const k = pair[i];
    yx.push(ref.x[k] + (you.x[i] - ref.x[k]) * LINE_MAG);
    yz.push(ref.z[k] + (you.z[i] - ref.z[k]) * LINE_MAG);
  }

  // The road, when the game's own track data could be read and matched to this
  // lap (see trackedges.py). It joins the fit so the picture is framed on the
  // asphalt rather than on the two lines: a corner where you ran wide should
  // show the edge you ran past, not crop it out.
  // …but not while the gap is magnified. At ×3 the line drawn is deliberately
  // not where the car was, and a real edge under a fake line would read as an
  // excursion that never happened. Real ground, or no ground.
  let road = LINE_MAG > 1 ? null : c.line.edges;

  // Everything that has to fit inside the box.
  let shapes = LINE_MAG > 1 ? null : c.line.road;

  // DUE insiemi, e la distinzione è il punto.
  //
  // `real` è la curva com'è davvero: la tua linea non gonfiata, il riferimento,
  // l'asfalto. Decide **l'angolo**, cioè come la curva viene girata per stare
  // grande nel riquadro. `draw` è ciò che finisce a schermo, linea gonfiata
  // compresa, e decide solo **quanto** zoomare perché nulla resti fuori.
  //
  // Prima l'angolo lo decideva `draw`. Effetto: passando da ×1 a ×3 la curva
  // veniva anche **ruotata**, e siccome a ×3 il fondo sparisce (vedi sopra) non
  // restava un solo appiglio per riconoscerla — due disegni della stessa curva
  // che non si somigliano. E il pulsante serve proprio a confrontare i due.
  const real = [];
  const draw = [];
  for (let i = 0; i < you.x.length; i++) real.push([you.x[i], you.z[i]]);
  for (let i = 0; i < yx.length; i++) draw.push([yx[i], yz[i]]);
  for (let i = 0; i < ref.x.length; i++) { real.push([ref.x[i], ref.z[i]]); draw.push([ref.x[i], ref.z[i]]); }
  const ground = c.line.edges;
  if (ground) for (const r of ground.runs) for (const side of [r.left, r.right]) {
    for (const p of side) { real.push([p[0], p[1]]); if (road) draw.push([p[0], p[1]]); }
  }
  // Solo pista e cordoli entrano nell'inquadratura: l'erba attorno a una curva
  // arriva fin dove le si e' chiesto, e farla decidere il riquadro vorrebbe dire
  // rimpicciolire la curva per mostrare del prato.
  const groundShapes = c.line.road;
  if (groundShapes) for (const k of ["road", "kerb"]) for (const ring of (groundShapes[k] || [])) {
    for (const p of ring) { real.push([p[0], p[1]]); if (shapes) draw.push([p[0], p[1]]); }
  }
  const pool = real;

  // The box is wide and short; a corner is whatever shape it is. Drawn in the
  // world's own axes, a corner that happens to run north-south uses a fifth of
  // the width and the driver gets a stamp in the middle of an empty panel.
  //
  // So the picture is TURNED — the whole thing, by one angle, chosen as the one
  // that lets it be drawn biggest. A rotation moves no point relative to any
  // other: the shape, the widths and the metres are exactly what they were, and
  // the scale bar still measures the same 25 m. It is the same corner, held up
  // at a better angle, which is all "seen from above" ever meant.
  const m = 34;
  const cx0 = pool.reduce((a, p) => a + p[0], 0) / pool.length;
  const cz0 = pool.reduce((a, p) => a + p[1], 0) / pool.length;
  let best = null;
  for (let deg = 0; deg < 180; deg += 3) {
    const a = deg * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
    let lx = Infinity, hx = -Infinity, lz = Infinity, hz = -Infinity;
    for (const p of pool) {
      const dx = p[0] - cx0, dz = p[1] - cz0;
      const rx = dx * ca - dz * sa, rz = dx * sa + dz * ca;
      if (rx < lx) lx = rx; if (rx > hx) hx = rx;
      if (rz < lz) lz = rz; if (rz > hz) hz = rz;
    }
    const sX = (hx - lx) || 1, sZ = (hz - lz) || 1;
    const scale = Math.min((w - 2 * m) / sX, (h - 2 * m) / sZ);
    if (!best || scale > best.scale) best = { ca, sa, lx, hx, lz, hz, scale };
  }

  // Scelto l'angolo sulla curva vera, il riquadro si allarga su ciò che verrà
  // davvero disegnato — altrimenti a ×3 la tua linea uscirebbe dal bordo.
  // L'angolo resta quello: è la parte che rende i due disegni confrontabili.
  {
    let lx = Infinity, hx = -Infinity, lz = Infinity, hz = -Infinity;
    for (const p of draw) {
      const dx = p[0] - cx0, dz = p[1] - cz0;
      const rx = dx * best.ca - dz * best.sa, rz = dx * best.sa + dz * best.ca;
      if (rx < lx) lx = rx; if (rx > hx) hx = rx;
      if (rz < lz) lz = rz; if (rz > hz) hz = rz;
    }
    const sX = (hx - lx) || 1, sZ = (hz - lz) || 1;
    best = { ...best, lx, hx, lz, hz,
             scale: Math.min((w - 2 * m) / sX, (h - 2 * m) / sZ) };
  }

  // The turn is applied to the DATA, once, so everything downstream — the
  // lines, the band, the markers, the hover — keeps working in one flat
  // coordinate system and cannot drift out of register with the road.
  const turn = (x, z) => {
    const dx = x - cx0, dz = z - cz0;
    return [dx * best.ca - dz * best.sa, dx * best.sa + dz * best.ca];
  };
  const turnPair = (xs, zs) => {
    const ox = [], oz = [];
    for (let i = 0; i < xs.length; i++) {
      const r = turn(xs[i], zs[i]);
      ox.push(r[0]); oz.push(r[1]);
    }
    return [ox, oz];
  };
  [yx, yz] = turnPair(yx, yz);
  ref = { ...ref, ...(([a, b]) => ({ x: a, z: b }))(turnPair(ref.x, ref.z)) };
  if (road) {
    road = { ...road, runs: road.runs.map((r) => ({
      left: r.left.map((p) => turn(p[0], p[1])),
      right: r.right.map((p) => turn(p[0], p[1])),
    })) };
  }
  if (shapes) {
    const t = {};
    for (const k of Object.keys(shapes)) {
      t[k] = shapes[k].map((ring) => ring.map((p) => turn(p[0], p[1])));
    }
    shapes = t;
  }

  const minX = best.lx, maxX = best.hx, minZ = best.lz;
  const sc = best.scale;
  const spanX = (best.hx - best.lx) || 1, spanZ = (best.hz - best.lz) || 1;
  const offX = (w - spanX * sc) / 2, offZ = (h - spanZ * sc) / 2;
  // Mirrored like the track map (AC/ACC world coords are left-handed), so a
  // corner still bends the way it does from the cockpit.
  const X = (x) => (maxX - x) * sc + offX;
  const Y = (z) => h - ((z - minZ) * sc + offZ);

  // The asphalt first, so everything else is drawn ON the road rather than
  // beside it. Two sources, and the better one wins: the game's own collision
  // model gives the road as a POLYGON with its kerbs, while the AI spline can
  // only give a corridor around the AI's own line — which on a chicane is a
  // smoothed-out version of a road that is not smooth.
  if (shapes) drawSurfaces(ctx, shapes, X, Y);
  else drawRoad(ctx, road, X, Y, 1.5);

  // The band between the lines.
  ctx.beginPath();
  for (let i = 0; i < yx.length; i++) {
    const px = X(yx[i]), py = Y(yz[i]);
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  for (let i = yx.length - 1; i >= 0; i--) {
    const k = pair[i];
    ctx.lineTo(X(ref.x[k]), Y(ref.z[k]));
  }
  ctx.closePath();
  ctx.fillStyle = "rgba(255,176,32,0.16)";
  ctx.fill();

  // Reference line: faint dashed, like the map's.
  ctx.save();
  ctx.setLineDash([6, 5]);
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < ref.x.length; i++) {
    const px = X(ref.x[i]), py = Y(ref.z[i]);
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke();
  ctx.restore();

  // Your line, thick and solid.
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.strokeStyle = "#22D3CE"; ctx.lineWidth = 3;
  ctx.beginPath();
  for (let i = 0; i < yx.length; i++) {
    const px = X(yx[i]), py = Y(yz[i]);
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke();

  // The two pedals, same encoding as the track map: yours filled, the
  // reference's a hollow ring. On a zoomed corner this is where "brake later"
  // stops being an abstraction — and it is what turns "your line is wider at
  // entry" into a diagnosis, because a wider entry next to a later brake point
  // is a different mistake from a wider entry next to the same one.
  //
  // The thresholds are the ones the rest of the app already measures with:
  // BRAKE_ON is `coaching.analyzer._BRAKE_ON` and THROTTLE_ON is
  // `coaching.diagnosis._THROTTLE_ON`, which is where the exit phase begins.
  // This drew at 0.3, a number from nowhere, so the triangle could sit some way
  // from the "brakes at" row of the braking sheet on this same page — two
  // answers to one question. `test_web_views` pins the two sides together.
  // ONE of each per corner, not every crossing. Drawn per crossing first, and
  // the screen said no: three green triangles appeared in one Red Bull Ring
  // corner because the throttle is modulated through it and crosses 20% three
  // times. All three were true and the picture was unreadable — "where you got
  // back on the power" is one place.
  //
  // So: the first braking of the corner, and the first throttle *after the
  // apex*. Those are not new definitions — they are the ones the braking sheet
  // and the phase split already use, which is also why they line up with the
  // numbers under this drawing.
  // …and it is the first sample OVER the threshold, not the first rising edge
  // through it. The rising edge was tried and drew nothing at all on a corner
  // taken with the throttle never below 20%: there is no edge to cross, and
  // "you were already on the power at the apex" is an answer, not an absence.
  // Both channels use the same test the Python side uses (`braking_points`
  // takes the first sample above `_BRAKE_ON` inside the corner).
  const BRAKE_ON = 0.15, THROTTLE_ON = 0.20;
  const firstAt = (s, chan, lim, from) => {
    const v = s[chan];
    if (!v) return -1;
    for (let i = 0; i < v.length; i++) {
      if (from != null && s.pos[i] < from) continue;
      if (v[i] >= lim) return i;
    }
    return -1;
  };
  const tri = (px, py, up) => {
    ctx.beginPath();
    if (up) { ctx.moveTo(px, py + 6); ctx.lineTo(px - 5, py + 14); ctx.lineTo(px + 5, py + 14); }
    else { ctx.moveTo(px, py - 6); ctx.lineTo(px - 5, py - 14); ctx.lineTo(px + 5, py - 14); }
    ctx.closePath(); ctx.fill();
  };
  const ring = (px, py) => {
    ctx.beginPath(); ctx.arc(px, py, 4.5, 0, 6.283); ctx.stroke();
  };
  const yb = firstAt(you, "brake", BRAKE_ON, null);
  const yt = firstAt(you, "throttle", THROTTLE_ON, c.apex_you || c.apex);
  const rb = firstAt(ref, "brake", BRAKE_ON, null);
  const rt = firstAt(ref, "throttle", THROTTLE_ON, c.apex_ref || c.apex);
  if (yb >= 0) { ctx.fillStyle = "#FFB020"; tri(X(yx[yb]), Y(yz[yb]), false); }
  if (yt >= 0) { ctx.fillStyle = "#3EE08A"; tri(X(yx[yt]), Y(yz[yt]), true); }
  ctx.lineWidth = 2;
  if (rb >= 0) {
    ctx.strokeStyle = "rgba(255,176,32,0.85)"; ring(X(ref.x[rb]), Y(ref.z[rb]));
  }
  if (rt >= 0) {
    ctx.strokeStyle = "rgba(62,224,138,0.85)"; ring(X(ref.x[rt]), Y(ref.z[rt]));
  }

  // The two apexes (slowest point of each line through this corner).
  const at = (s, pos) => {
    let best = 0, bd = Infinity;
    for (let i = 0; i < s.pos.length; i++) {
      const d = Math.abs(s.pos[i] - pos);
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  };
  const ai = at(you, c.apex_you), ri = at(ref, c.apex_ref);
  ctx.fillStyle = "#22D3CE";
  ctx.beginPath(); ctx.arc(X(yx[ai]), Y(yz[ai]), 5, 0, 6.283); ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(X(ref.x[ri]), Y(ref.z[ri]), 5.5, 0, 6.283); ctx.stroke();

  // Direction of travel, from the first samples of your line.
  const k = Math.min(6, yx.length - 1);
  let ux = X(yx[k]) - X(yx[0]), uy = Y(yz[k]) - Y(yz[0]);
  const ul = Math.hypot(ux, uy) || 1; ux /= ul; uy /= ul;
  const sx = X(yx[0]), sy = Y(yz[0]);
  const tipX = sx + ux * 22, tipY = sy + uy * 22;
  ctx.strokeStyle = "rgba(255,255,255,0.75)"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(tipX, tipY); ctx.stroke();
  const ah = 6, nx = -uy, ny = ux;
  ctx.fillStyle = "rgba(255,255,255,0.75)";
  ctx.beginPath();
  ctx.moveTo(tipX, tipY);
  ctx.lineTo(tipX - ux * ah + nx * ah * 0.6, tipY - uy * ah + ny * ah * 0.6);
  ctx.lineTo(tipX - ux * ah - nx * ah * 0.6, tipY - uy * ah - ny * ah * 0.6);
  ctx.closePath(); ctx.fill();

  // Scale bar — without it the zoom level is unknowable and "2 m wide" has no
  // size on screen. Rounded to a number a human reads off a ruler.
  const want = 90 / sc;
  const nice = [1, 2, 5, 10, 20, 25, 50, 100, 200].reduce(
    (a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a));
  const px0 = 14, py0 = h - 14, len = nice * sc;
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(px0, py0 - 4); ctx.lineTo(px0, py0); ctx.lineTo(px0 + len, py0);
  ctx.lineTo(px0 + len, py0 - 4); ctx.stroke();
  ctx.fillStyle = "rgba(255,255,255,0.55)"; ctx.font = "11px " + MONO;
  ctx.fillText(nice + " m", px0 + len + 6, py0 + 1);
  // The magnification caveat sits with the scale bar, not in the top-left
  // corner: they are the same warning ("what you see is not the ground"), and
  // the top of the canvas now carries the sentence about the corner.
  if (LINE_MAG > 1) {
    ctx.fillStyle = "#FFB020"; ctx.font = "11px " + UI_FONT;
    ctx.fillText(tf("line.mag.note", { n: LINE_MAG }), px0, py0 - 14);
  }

  cornerNote(ctx, w, c);
  insetMap(ctx, w, h, c, cx);

  // Hover marker.
  if (cx != null) {
    const i = at(you, cx);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(X(yx[i]), Y(yz[i]), 7, 0, 6.283); ctx.stroke();
  }
  return { pos: you.pos, X: (i) => X(yx[i]), Y: (i) => Y(yz[i]) };
}

// One line of canvas text, cut with an ellipsis rather than run off the edge.
function clipText(ctx, s, maxw) {
  s = String(s || "");
  if (ctx.measureText(s).width <= maxw) return s;
  while (s.length > 1 && ctx.measureText(s + "…").width > maxw) s = s.slice(0, -1);
  return s.replace(/[\s,;:.]+$/, "") + "…";
}

// The sentence that belongs to this drawing.
//
// The debrief already wrote it — this corner's diagnosis, in the driver's own
// language — and until now you had to leave the picture and go and find it on
// another tab. It is copied verbatim from the analysis payload and never
// re-derived here: two modules writing about the same corner is exactly how they
// end up disagreeing (see the note at the top of trajectory.py).
//
// Nothing is drawn when this corner cost nothing, which is itself a reading: the
// line you are looking at is not where the lap went.
function cornerNote(ctx, w, corner) {
  const l = ((DATA && DATA.losses) || []).find((x) => x.index === corner.index);
  if (!l || !l.message) return;
  const maxw = w - 28;
  ctx.save();
  ctx.font = "12px " + UI_FONT;
  const head = `${(l.lost_s || 0).toFixed(2)} s · ${l.message}`;
  // A backdrop, because this text lies over a drawing: the two lines cross the
  // whole canvas and a bare label on top of them is unreadable at the crossing.
  const sub = l.inherited || l.phase_note || "";
  const lines = sub ? 2 : 1;
  ctx.fillStyle = "rgba(11,14,18,0.72)";
  ctx.fillRect(0, 0, w, 12 + lines * 15);
  ctx.fillStyle = "#FFB020";
  ctx.fillText(clipText(ctx, head, maxw), 14, 20);
  if (sub) {
    ctx.font = "11px " + UI_FONT;
    ctx.fillStyle = "rgba(255,255,255,0.6)";
    ctx.fillText(clipText(ctx, (l.inherited ? "↩ " : "") + sub, maxw), 14, 35);
  }
  ctx.restore();
}

// "You are here": the whole lap, small, with the corner on screen lit up.
//
// The zoomed corner is the one picture on this page with no context at all —
// two hairpins on the same track draw the same shape, and which one you clicked
// is something you had to remember. The outline costs nothing: it is the same
// coordinates the track map is already drawn from.
function insetMap(ctx, w, h, corner, cx) {
  const ch = DATA && DATA.has_map && DATA.review && DATA.review.channels;
  if (!ch || !Array.isArray(ch.x) || ch.x.length < 3) return;
  // Too small a canvas and the inset would cover the corner it is placing.
  if (w < 260 || h < 200) return;
  const side = Math.max(64, Math.min(132, Math.min(w, h) * 0.34));
  const pad = 10, x0 = w - side - pad, y0 = h - side - pad;

  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (let i = 0; i < ch.x.length; i++) {
    minX = Math.min(minX, ch.x[i]); maxX = Math.max(maxX, ch.x[i]);
    minZ = Math.min(minZ, ch.z[i]); maxZ = Math.max(maxZ, ch.z[i]);
  }
  const spanX = (maxX - minX) || 1, spanZ = (maxZ - minZ) || 1;
  const inner = side - 16;
  const s = Math.min(inner / spanX, inner / spanZ);
  const ox = x0 + (side - spanX * s) / 2, oz = y0 + (side - spanZ * s) / 2;
  // Same mirrored projection as the track map and as the zoom above it: three
  // pictures of the same lap that disagree about left and right are worse than
  // two of them not existing.
  const X = (x) => (maxX - x) * s + ox;
  const Y = (z) => y0 + side - ((z - minZ) * s + oz - y0);

  ctx.save();
  ctx.fillStyle = "rgba(11,14,18,0.72)";
  ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.rect(x0 + 0.5, y0 + 0.5, side, side);
  ctx.fill(); ctx.stroke();

  ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1.4;
  ctx.beginPath();
  for (let i = 0; i < ch.x.length; i++) {
    const px = X(ch.x[i]), py = Y(ch.z[i]);
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke();

  // The stretch you are looking at, in the same accent as your line above. Drawn
  // fat on purpose: a corner is a per cent of a lap, so at this size it is three
  // pixels of track and a hairline would read as nothing.
  ctx.strokeStyle = "#22D3CE"; ctx.lineWidth = 5;
  ctx.beginPath();
  let drawing = false;
  for (let i = 0; i < ch.x.length; i++) {
    if (ch.pos[i] < corner.entry || ch.pos[i] > corner.exit) { drawing = false; continue; }
    const px = X(ch.x[i]), py = Y(ch.z[i]);
    drawing ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    drawing = true;
  }
  ctx.stroke();

  // A ring around the corner, because at this size the highlighted stretch is a
  // few pixels of a whole lap: the ring is what the eye lands on, the stretch is
  // what tells it how much of the track that is.
  const aj = nearest(ch.pos, corner.apex_you);
  ctx.strokeStyle = "rgba(34,211,206,0.75)"; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(X(ch.x[aj]), Y(ch.z[aj]), 11, 0, 6.283); ctx.stroke();

  // The dot: where the cursor is when you're hovering, the apex when you're not.
  // Small, with a dark hairline rather than a filled halo — a fat marker here
  // covers the very stretch it is marking.
  const i = cx != null ? nearest(ch.pos, cx) : aj;
  ctx.beginPath(); ctx.arc(X(ch.x[i]), Y(ch.z[i]), 3, 0, 6.283);
  ctx.fillStyle = "#ffffff"; ctx.fill();
  ctx.strokeStyle = "rgba(11,14,18,0.85)"; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.restore();
}

// The whole lap's distance from the reference line, with the corner you're
// looking at picked out. Reuses the analysis payload's line_offset rather than
// asking the backend for the same numbers twice.
function drawOffsetTrace(L, corner, cx) {
  const cv = $("c-offset");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const off = DATA && DATA.review && DATA.review.line_offset;
  const pos = DATA && DATA.review && DATA.review.channels.pos;
  if (!Array.isArray(off) || !off.length) return;
  let m = 1.0;
  for (const v of winVals(pos, off)) m = Math.max(m, Math.abs(v));
  cornerBands(ctx, w, h, (DATA && DATA.corners) || []);
  cornerVeil(ctx, w, h, corner);
  gridX(ctx, w, h);
  gridY(ctx, w, h, -m, m, (v) => fixz(v, 1) + " m");
  ctx.strokeStyle = "rgba(255,255,255,0.3)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, pos, off, -m, m, "#c58cff", 1.6);
  crosshair(ctx, w, h, cx);
}

// Curvature: how tight the arc under the car is, yours against the reference's.
// Plotted with the sign flipped so left is up, matching the steering trace — the
// two are read together (steering is what you asked for, this is what you got).
function drawCurvature(L, corner, cx) {
  const cv = $("c-curv");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const you = L.curvature.you, ref = L.curvature.ref;
  if (!you.k.length) return;
  // Scaled to a high percentile, not the maximum: one kerb strike would
  // otherwise flatten the whole lap into a line through the middle.
  const all = you.k.concat(ref.k).map(Math.abs).sort((a, b) => a - b);
  const m = Math.max(0.002, all[Math.floor(all.length * 0.98)] || 0.01);
  cornerBands(ctx, w, h, (DATA && DATA.corners) || []);
  cornerVeil(ctx, w, h, corner);
  gridX(ctx, w, h, true);   // the bottom chart of the Trajectory stack: label it
  // Gridlines with no scale on purpose: curvature is in 1/m, which nobody feels,
  // and labelling the ticks with the radius they stand for prints the same two
  // numbers mirrored either side of a middle that means "straight". The radius
  // in metres is where a driver reads it — the facts panel, the table and the
  // hover readout, one corner at a time.
  gridY(ctx, w, h, -m, m, () => "");
  ctx.strokeStyle = "rgba(255,255,255,0.3)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  // Flipped so left is up (matching the steering trace, which is read with it)
  // and clamped to the box: the scale is a percentile, so a kerb strike would
  // otherwise draw a spike straight through the chart below.
  const flip = (a) => a.map((v) => Math.max(-m, Math.min(m, -v)));
  line(ctx, w, h, ref.pos, flip(ref.k), -m, m, "#3fd0e0", 1.3);
  line(ctx, w, h, you.pos, flip(you.k), -m, m, "#ffffff", 1.5);
  axisLabel(ctx, w, h, t("line.left"), t("line.right"));
  crosshair(ctx, w, h, cx);
}

function updateLineReadout(L, p) {
  const el = $("line-readout");
  if (!el) return;
  // Il verso di ritorno di `emptyReadout` (vedi il ramo «niente curve» di
  // `renderLine`): con le curve in vista la fascia torna accesa.
  el.classList.remove("hidden");
  const chip = rangeChip();
  if (p == null) { el.innerHTML = chip + t("line.readout"); wireRangeClear(el); return; }
  LAST_HOVER = p;
  const c = L.corners[LINE_I];
  const off = DATA && DATA.review && DATA.review.line_offset;
  const pos = DATA && DATA.review && DATA.review.channels.pos;
  let bits = `<b class="muted">${c.name}</b> &nbsp;·&nbsp; ` +
             `<b>${t("ro.pos")} ${posLabel(p)}</b>`;
  if (Array.isArray(off) && pos) {
    const i = nearest(pos, p);
    bits += ` &nbsp;·&nbsp; ${t("line.ro.off")} <b>${offWord(off[i] * (c.sided !== false && c.direction === "left" ? -1 : 1), c)}</b>`;
  }
  const ki = nearest(L.curvature.you.pos, p);
  const k = Math.abs(L.curvature.you.k[ki] || 0);
  if (k > 0.001) bits += ` &nbsp;·&nbsp; ${t("line.ro.radius")} <b>${Math.round(1 / k)} m</b>`;
  if (DATA) {
    const rv = DATA.review.channels, rf = DATA.reference.channels;
    const iv = nearest(rv.pos, p), ir = nearest(rf.pos, p);
    bits += ` &nbsp;·&nbsp; ${t("ro.speed")} <b>${rv.speed[iv].toFixed(0)}</b> ` +
            `<span class="muted">(${t("ro.ref")} ${rf.speed[ir].toFixed(0)})</span>`;
  }
  el.innerHTML = chip + bits;
  wireRangeClear(el);
}

// --- hover / readout ------------------------------------------------------
function nearest(posArr, p) {
  let lo = 0, hi = posArr.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (posArr[mid] < p) lo = mid + 1; else hi = mid; }
  if (lo > 0 && Math.abs(posArr[lo - 1] - p) < Math.abs(posArr[lo] - p)) return lo - 1;
  return lo;
}

// Point-by-point readout markup at lap position p (0..1). Shared by the Compare
// charts and the hover on the map beside them, so both reuse the same nearest()
// lookup.
function readoutHTML(a, p) {
  const rv = a.review.channels, rf = a.reference.channels, d = a.review.delta;
  const iv = nearest(rv.pos, p), ir = nearest(rf.pos, p), id = nearest(d.pos, p);
  const yv = rv.speed[iv], rfv = rf.speed[ir], dv = yv - rfv, dl = d.delta_s[id];
  const corner = (a.corners || []).find((c) => p >= c.entry && p <= c.exit);
  // Non ripetere il nome che la pastiglia della finestra ha già detto due
  // centimetri più a sinistra: «Curva 1 ✕ · Curva 1 · Pos 1294 m» è esattamente
  // il tipo di eco che rende la pagina più lunga senza dire niente di nuovo.
  const named = RANGE && RANGE.label && corner && RANGE.label === corner.name;
  const where = corner && !named ? `<b class="muted">${corner.name}</b> &nbsp;·&nbsp; ` : "";
  return where +
    `<b>${t("ro.pos")} ${posLabel(p)}</b> &nbsp;·&nbsp; ` +
    `${t("ro.speed")} <b>${yv.toFixed(0)}</b> <span class="muted">(${t("ro.ref")} ${rfv.toFixed(0)}, ${dv >= 0 ? "+" : ""}${dv.toFixed(0)})</span> &nbsp;·&nbsp; ` +
    `Δ <b class="${dl > 0 ? "slower" : "faster"}">${dl >= 0 ? "+" : ""}${dl.toFixed(3)}s</b> &nbsp;·&nbsp; ` +
    `${t("ro.throttle")} <b>${Math.round(rv.throttle[iv] * 100)}%</b>  ${t("ro.brake")} <b>${Math.round(rv.brake[iv] * 100)}%</b> &nbsp;·&nbsp; ` +
    `${t("ro.gear")} <b>${rv.gear[iv]}</b>`;
}

// Uscendo dal grafico il valore si **congela**, non si azzera.
//
// Prima tornava al suggerimento «passa il mouse sui grafici…», che è la frase
// che nessuno legge dopo il primo giorno e che cancellava il numero appena
// letto. Il gesto in cui fa più male è proprio quello utile: sposti il mouse
// fuori dalla tela per andare a cliccare qualcos'altro — un chip, una riga di
// tabella — e perdi il valore nel gesto stesso di cambiare inquadratura.
// È il comportamento di i2: l'ultimo punto resta, smorzato, finché non ne
// scegli un altro. Il suggerimento si vede solo finché non hai mai passato il
// mouse, che è l'unico momento in cui serve davvero.
// L'etichetta della finestra, con la via d'uscita accanto.
//
// Serve perché la finestra è **globale**: la imposti in Traiettoria e anche
// Confronto e Dinamica si ritagliano. Senza un'etichetta il pilota si ritrova i
// grafici zoomati su una scheda dove non ha toccato niente, e senza il bottone
// non ha modo di tornare indietro se non ripassando da dove era partito. Una
// modalità che non si annuncia e non si annulla è una trappola, non una
// funzione.
function rangeChip() {
  if (!RANGE) return "";
  const from = metresAt(RANGE.from), to = metresAt(RANGE.to);
  const what = RANGE.source === "corner" && RANGE.label ? RANGE.label
             : from != null && to != null
               ? `${Math.round(from)}–${Math.round(to)} m`
               : `${Math.round(RANGE.from * 100)}–${Math.round(RANGE.to * 100)}%`;
  return `<span class="range-chip"><b>${what}</b>` +
         `<button type="button" class="range-clear" title="${t("range.clear")}">✕</button>` +
         `</span> &nbsp;·&nbsp; `;
}

// La ✕ della pastiglia vive ora su quattro readout (Confronto, Mappa,
// Traiettoria, Dinamica: vedi `rangeChip`). Un `id="range-clear"` ripetuto
// funzionerebbe solo per il primo che `getElementById` incontra — gli altri
// tre bottoni resterebbero muti. Il bottone si cerca dentro il contenitore
// appena scritto, non con un id globale condiviso.
function wireRangeClear(el) {
  const b = el && el.querySelector(".range-clear");
  if (b) b.onclick = () => { setRange(null); redrawCurrentView(); };
}

// La fascia di lettura quando i grafici NON ci sono — che non è il caso `p ==
// null`, dove i grafici ci sono e semplicemente nessuno ci sta sopra col mouse,
// e «passa il mouse sui grafici» è un invito valido.
//
// Qui i grafici sono spenti, e restano due modi di mentire. Il primo: i numeri
// del giro PRECEDENTE, veri di un altro giro e permanenti, perché nessun ramo
// li riscrive — la Traiettoria li teneva punto per punto sopra «questi giri non
// hanno coordinate». Il secondo: la didascalia stessa, che invita a un gesto
// senza bersaglio sopra la frase che dice che il bersaglio non c'è.
//
// Resta solo la pastiglia della finestra attiva, perché la sua ✕ è l'unica via
// per annullarla da questa scheda (è il motivo per cui il ramo senza dinamica
// chiamava `updateDynReadout` invece di non fare niente). Senza pastiglia non
// resta una striscia vuota: la fascia si spegne del tutto.
function emptyReadout(el) {
  if (!el) return;
  const chip = rangeChip();
  // La pastiglia finisce con « · » perché di solito ha qualcosa dopo. Qui non
  // ha niente, e un separatore che non separa è la stessa cosa in piccolo:
  // punteggiatura per un testo che non c'è. Misurato a schermo: «Tamburello ✕ ·».
  el.innerHTML = chip.replace(/\s*&nbsp;·&nbsp;\s*$/, "");
  el.classList.remove("frozen");
  el.classList.toggle("hidden", !chip);
  wireRangeClear(el);
}

// Testo del readout della mappa, a riposo (`p` nullo, la legenda) o sotto il
// mouse (`p`, punto per punto) — sempre con la pastiglia della finestra
// davanti. Chiamata da un solo posto, `drawMap` (vedi il suo commento): prima
// ogni chiamante di `drawMap` scriveva anche il readout per conto proprio, e
// il cambio scheda — che disegna la mappa senza passare da nessuno degli
// altri due — se n'era dimenticato.
function mapReadoutHTML(p) {
  return rangeChip() + (p == null ? MAP_READOUT_DEFAULT() : readoutHTML(DATA, p));
}

function updateReadout(a, p) {
  const el = $("readout");
  const chip = rangeChip();
  if (p == null) {
    if (LAST_HOVER == null) { el.innerHTML = chip + t("readout.hint"); wireRangeClear(el); return; }
    el.classList.add("frozen");           // il valore resta, spento
    return;
  }
  LAST_HOVER = p;
  el.classList.remove("frozen");
  el.innerHTML = chip + readoutHTML(a, p);
  wireRangeClear(el);
}

// Il punto unico di ingresso per OGNI hover della pagina, non solo quello del
// rail: ogni scheda ha un modo diverso di mostrare «sei qui», e con un rail che
// vive su sei schede senza questo instradamento servirebbe un `if` per scheda
// dentro ciascun gestore. Così era nata la minimappa cablata alla sola vista
// Confronto — e così, se un gestore chiamasse di nuovo la funzione di vista
// direttamente invece che passare da qui, il rail tornerebbe a essere a senso
// unico: sorgente di mirino ma mai destinazione.
//
// Le schede senza un consumatore di mirino (il flusso guidato, i settori) non
// fanno NIENTE, di proposito: il rail muove il proprio marcatore e basta. Meglio
// un gesto che non risponde di un gesto che ridisegna una vista che non è a
// schermo.
function hoverTo(p) {
  if (!DATA) return;
  // Solo su un punto vero: `updateReadout` (vista Confronto) confronta
  // `LAST_HOVER` con `null` per decidere se il readout va congelato (l'ultimo
  // valore, spento) o svuotato al suggerimento — e quel confronto vale solo se
  // qui non lo si azzera già in anticipo. Uscire dal rail deve congelare il
  // readout esattamente come uscire dai grafici, non cancellarlo.
  if (p != null) LAST_HOVER = p;
  // Sul Confronto il mirino attraversa lo schermo: i grafici a sinistra E il
  // disegno a destra. Un mirino che vive su metà schermata è peggio di nessun
  // mirino — è il difetto della minimappa cablata a una vista sola, di nuovo.
  // Il readout della mappa lo scrive `drawMap` stessa (vedi il commento lì):
  // niente da duplicare qui.
  if (VIEW === "compare") { redraw(p); drawMap(DATA, p); }
  else if (VIEW === "dynamics") drawDynamics(p);
  else if (VIEW === "line") { if (LINE) renderLine(p); }
  drawRail(p);
}

function wireHover() {
  if (HOVER_WIRED) return;
  HOVER_WIRED = true;
  const canvases = ["c-delta", "c-speed", "c-inputs", "c-steer"].map($);
  const onMove = (e) => {
    const rect = canvases[0].getBoundingClientRect();
    const p = posAtX(e.clientX - rect.left, rect.width);
    hoverTo(p);
  };
  const onLeave = () => hoverTo(null);
  for (const cv of canvases) {
    if (!cv) continue;
    cv.addEventListener("mousemove", onMove);
    cv.addEventListener("mouseleave", onLeave);
  }

  // Hover di mappa e rail: l'asse x non è la posizione in pista, quindi si
  // cerca il campione più vicino nello spazio schermo (la trasformazione
  // catturata quando la mappa è stata disegnata) e si riusa il suo `pos` per
  // pilotare mirino e readout condivisi.
  function nearestPos(hit, canvas, e) {
    if (!hit) return null;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const rv = hit.rv;
    let best = -1, bd = Infinity;
    for (let i = 0; i < rv.x.length; i++) {
      const dx = hit.X(rv.x[i]) - mx, dy = hit.Y(rv.z[i]) - my;
      const dd = dx * dx + dy * dy;
      if (dd < bd) { bd = dd; best = i; }
    }
    return best >= 0 ? rv.pos[best] : null;
  }

  const map = $("c-map");
  if (map) {
    map.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const p = nearestPos(MAP_HIT, map, e);
      if (p != null) hoverTo(p);
    });
    map.addEventListener("mouseleave", () => hoverTo(null));
  }

  // Il rail: stesso gesto della vecchia minimappa di Confronto, ma su sei schede
  // — quindi instradato invece che cablato a una.
  const rail = $("c-rail");
  if (rail) {
    rail.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const p = nearestPos(RAIL_HIT, rail, e);
      if (p != null) hoverTo(p);
    });
    rail.addEventListener("mouseleave", () => hoverTo(null));
  }

  // Dynamics tab: the slip trace is on the position axis (same as the Compare
  // charts), the G-G scatter isn't — so slip hover reads cursor→position, while
  // G-G hover finds the nearest dot in screen space and reuses its position.
  // Tutte le tracce di questa scheda che stanno sull'asse posizione, non solo
  // lo slip: `yaw` e `rpm` erano disegnate con il mirino addosso (`style.css`
  // dà `cursor: crosshair` a ogni canvas) e non rispondevano al mouse. Una
  // pagina che promette un gesto e non lo fa insegna a non provarlo più.
  for (const id of ["c-slip", "c-yaw", "c-rpm"]) {
    const cv = $(id);
    if (!cv) continue;
    cv.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const rect = cv.getBoundingClientRect();
      const p = posAtX(e.clientX - rect.left, rect.width);
      hoverTo(p);
    });
    cv.addEventListener("mouseleave", () => { if (DATA) hoverTo(null); });
  }
  const gg = $("c-gg");
  if (gg) {
    gg.addEventListener("mousemove", (e) => {
      if (!DATA || !DYN_GG) return;
      const rect = gg.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      let best = -1, bd = Infinity;
      const pts = DYN_GG.pts;
      for (let i = 0; i < pts.length; i++) {
        const dx = pts[i].px - mx, dy = pts[i].py - my, dd = dx * dx + dy * dy;
        if (dd < bd) { bd = dd; best = i; }
      }
      if (best >= 0) hoverTo(pts[best].pos);
    });
    gg.addEventListener("mouseleave", () => { if (DATA) hoverTo(null); });
  }
  // The zoomed corner: x isn't track position, so find the nearest point of
  // your line in screen space and reuse its position, like the map does.
  const corner = $("c-corner");
  if (corner) {
    corner.addEventListener("mousemove", (e) => {
      if (!LINE || !LINE_HIT) return;
      const rect = corner.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      let best = -1, bd = Infinity;
      for (let i = 0; i < LINE_HIT.pos.length; i++) {
        const dx = LINE_HIT.X(i) - mx, dy = LINE_HIT.Y(i) - my, dd = dx * dx + dy * dy;
        if (dd < bd) { bd = dd; best = i; }
      }
      if (best >= 0) hoverTo(LINE_HIT.pos[best]);
    });
    corner.addEventListener("mouseleave", () => { if (LINE) hoverTo(null); });
  }
  // Le due tracce di questa scheda condividono l'asse posizione: erano cablate
  // a metà, e la curvatura restava muta col mirino disegnato sopra.
  for (const id of ["c-offset", "c-curv"]) {
    const cv = $(id);
    if (!cv) continue;
    cv.addEventListener("mousemove", (e) => {
      if (!LINE) return;
      const rect = cv.getBoundingClientRect();
      hoverTo(posAtX(e.clientX - rect.left, rect.width));
    });
    cv.addEventListener("mouseleave", () => { if (LINE) hoverTo(null); });
  }

  const ribbon = $("c-balance");
  if (ribbon) {
    ribbon.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const p = nearestPos(DYN_BAL_HIT, ribbon, e);
      if (p != null) hoverTo(p);
    });
    ribbon.addEventListener("mouseleave", () => { if (DATA) hoverTo(null); });
  }
}

// Debounced so a resize drag fires once at rest, not per pixel. Compare just
// redraws from the in-memory payload — charts AND the map beside them, which is
// how the map's canvas picks up the column's new width (no refetch, no flicker
// or response race); Sectors/Progress re-run their loader once at the end.
let _resizeTimer = null;
window.addEventListener("resize", () => {
  if (!CURRENT) return;
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(redrawCurrentView, 150);
});
// Live language switch: i18n.js already re-applied the static chrome; here we
// re-render the dynamic, JS-built parts in the new language without a reload,
// keeping the current combo/lap selection and hover position.
window.HoneI18nRerender = function () {
  const cb = document.querySelector(".cb-toggle");
  if (cb && window.HoneI18n) {
    cb.title = window.HoneI18n.t("cb.label");
    cb.setAttribute("aria-label", window.HoneI18n.t("cb.label"));
  }
  wireTabs();          // the tabs carry their shortcut in their tooltip
  wireHints();
  fillCombos();
  // Re-FETCH, not just re-draw. The debrief, the corner names, the lap-wide
  // notes and every word of the guided flow are written by the backend in the
  // language the request asked for, so repainting the cached payload leaves all
  // of it in the language you just left. Only the chrome was ever translated
  // here, and the comment at `getJSON` claiming the backend ignores `&lang` has
  // been wrong since the debrief learned to speak Italian.
  if (!CURRENT) return;
  // `reloadSelection` refetches the *lap*, and with it Compare, Map, Line,
  // Sectors and the guided flow. It has never touched the views that are per
  // car+track rather than per lap — so switching language left Trends, Session
  // and the braking sheet sitting in the language you just left, chrome in one
  // language and content in the other. Found on the Training tab, but it was
  // never only there.
  SHEET = null;          // the braking sheet carries the landmark wording
  TRAINING = null;       // the drills are prose, written server-side
  reloadSelection();
  if (VIEW === "progress") loadProgress(CURRENT);
  if (VIEW === "session" || VIEW === "recap") loadSession(CURRENT, SESSION_I);
  if (VIEW === "training") loadTraining(CURRENT);
};

wireTour();
wireCbToggle();
init();
