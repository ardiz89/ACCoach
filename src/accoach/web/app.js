"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (s) => (s >= 0 ? "+" : "") + s.toFixed(3);
// i18n: translate a chrome string (defensive if i18n.js failed to load).
const t = (k) => (window.HoneI18n ? window.HoneI18n.t(k) : k);
const LANG = () => (window.HoneI18n ? window.HoneI18n.lang : "en");

let CURRENT = null;   // current combo {car, track}
let DATA = null;      // last /api/analysis payload
let COMBOS = [];      // last /api/combos payload (kept for re-labelling on lang switch)
let LAST_HOVER = null; // last hover position, so a re-render keeps the readout
let VIEW = "compare"; // "compare" | "progress"
let HOVER_WIRED = false;
let MAP_HIT = null;   // {rv, X, Y} screen transform captured by drawMap, for map hover
let MINI_HIT = null;  // same, for the Compare-view mini map
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
  // Pass the active language so backend-generated content arrives localised
  // (the backend ignores &lang until it handles it — harmless today).
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
    loadCombo(combo);
    if (VIEW === "progress") loadProgress(combo);
  };
  $("lap").onchange = reloadSelection;
  $("baseline").onchange = reloadSelection;
  $("exp-csv").onclick = () => exportData("csv");
  $("exp-json").onclick = () => exportData("json");
  wireTabs();
  await loadCombo(JSON.parse(sel.value));
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
  return [
    { sel: "#combo", title: t("tour.a1.t"), text: t("tour.a1.x") },
    { sel: ".tabs", title: t("tour.a2.t"), text: t("tour.a2.x") },
    { sel: "#c-delta", title: t("tour.a3.t"), text: t("tour.a3.x") },
    { sel: "#vmin", title: t("tour.a4.t"), text: t("tour.a4.x") },
    { sel: "#debrief", title: t("tour.a5.t"), text: t("tour.a5.x") },
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
// compare/map; sectors/progress re-run their loader). Shared by resize + the
// colour-blind toggle.
function redrawCurrentView() {
  if (VIEW === "map") { if (DATA) drawMap(DATA, null); }
  else if (VIEW === "dynamics") { if (DATA) drawDynamics(LAST_HOVER); }
  else if (VIEW === "sectors") { if (CURRENT) loadSectors(); }
  else if (VIEW === "progress") { if (CURRENT) loadProgress(CURRENT); }
  else if (DATA) redraw(LAST_HOVER);   // compare
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

function wireTabs() {
  for (const b of document.querySelectorAll(".tab")) {
    b.onclick = () => {
      for (const x of document.querySelectorAll(".tab")) x.classList.toggle("active", x === b);
      VIEW = b.dataset.view;
      $("view-compare").classList.toggle("hidden", VIEW !== "compare");
      $("view-map").classList.toggle("hidden", VIEW !== "map");
      $("view-sectors").classList.toggle("hidden", VIEW !== "sectors");
      $("view-dynamics").classList.toggle("hidden", VIEW !== "dynamics");
      $("view-progress").classList.toggle("hidden", VIEW !== "progress");
      if (VIEW === "progress" && CURRENT) loadProgress(CURRENT);
      if (VIEW === "map" && DATA) drawMap(DATA, null);
      if (VIEW === "dynamics" && DATA) drawDynamics(null);
      if (VIEW === "sectors" && CURRENT) loadSectors();
    };
  }
}

async function loadProgress(combo) {
  setPanelLoading("prog-summary", t("load.trends"));
  let p;
  try { p = await getJSON("/api/progress?" + new URLSearchParams({ car: combo.car, track: combo.track })); }
  catch (e) {
    $("prog-summary").innerHTML = "";
    $("levels").innerHTML = ""; $("trends").innerHTML = "";
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
  drawTyres(p);
  renderLevels(p.levels);
  renderTrends(p.trends);
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

  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px Segoe UI";
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

  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px Segoe UI";
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
  const lap = $("lap").value, base = $("baseline").value;
  if (lap) q.set("lap", lap);
  if (base) q.set("baseline", base);
  setPanelLoading("sec-summary", t("load.sectors"));
  let s;
  try { s = await getJSON("/api/sectors?" + q.toString()); }
  catch (e) {
    $("sec-summary").innerHTML = `<div class="item"><div class="v">—</div><div class="k">${e.message}</div></div>`;
    $("sectors").innerHTML = ""; $("ideal").innerHTML = "";
    return;
  }
  drawSectors(s);
}

function drawSectors(s) {
  const gap = (s.review.lap_time_ms - s.baseline.lap_time_ms) / 1000;
  const item = (k, v, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  $("sec-summary").innerHTML =
    item(t("lbl.comparison"), s.baseline.lap_time) +
    item(t("lbl.lap"), s.review.lap_time) +
    item(t("lbl.gap"), fmt(gap) + "s", gap > 0 ? "slower" : "faster") +
    item(t("lbl.sectors"), s.real ? t("sec.real") : t("sec.thirds"));

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

// Full track map (its own tab). Wrapper around drawMapTo that also publishes the
// screen transform for the map's own hover.
function drawMap(a, cx) {
  const hit = drawMapTo($("c-map"), $("map-missing"), a, cx);
  if (hit) MAP_HIT = hit;
}

// Mini map shown inside the Compare view, driven by the shared crosshair so it
// highlights wherever you're hovering on the traces (and vice versa).
function drawMiniMap(a, cx) {
  const wrap = $("minimap-wrap");
  if (!wrap) return;
  if (!a || !a.has_map) { wrap.classList.add("hidden"); return; }
  wrap.classList.remove("hidden");
  const hit = drawMapTo($("c-minimap"), null, a, cx);
  if (hit) MINI_HIT = hit;
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

  // Corner labels at each apex.
  ctx.fillStyle = "rgba(255,255,255,0.85)"; ctx.font = "11px Segoe UI";
  for (const c of a.corners || []) {
    const i = nearest(rv.pos, c.apex);
    ctx.fillText("T" + (c.index + 1), X(rv.x[i]) + 6, Y(rv.z[i]) - 4);
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
  ctx.font = "bold 11px Segoe UI";
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

function reloadSelection() {
  loadCombo(CURRENT, $("lap").value, $("baseline").value);
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
  if (VIEW === "map") $("map-readout").innerHTML = t("load.lap");
  let a;
  try { a = await getJSON("/api/analysis?" + q.toString()); }
  catch (e) {
    $("summary").innerHTML =
      `<div class="item"><div class="v">—</div><div class="k">${t("err.lap")}</div></div>`;
    return;
  }
  DATA = a;
  fillLaps(a);
  drawSummary(a);
  drawCornerSpeeds(a);
  drawWaterfall(a);
  drawDebrief(a);
  redraw(null);
  if (VIEW === "map") { $("map-readout").innerHTML = MAP_READOUT_DEFAULT(); drawMap(a, null); }
  if (VIEW === "dynamics") drawDynamics(null);
  if (VIEW === "sectors") loadSectors();
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
  // Skip if already filled for this combo — unless forced (e.g. language switch
  // needs to relabel "(invalid)" while keeping the current selection).
  if (!force && $("lap").dataset.for === key) return;
  $("lap").dataset.for = key;
  const keepLap = force ? $("lap").value : null;
  const keepBase = force ? $("baseline").value : null;

  // Find the fastest valid lap so we can star it in the dropdowns.
  let bestPath = null, bestMs = Infinity;
  for (const l of a.laps) {
    if (l.valid && l.lap_time_ms > 0 && l.lap_time_ms < bestMs) {
      bestMs = l.lap_time_ms; bestPath = l.path;
    }
  }

  const fill = (id, selectedPath) => {
    const sel = $(id);
    sel.innerHTML = "";
    for (const l of a.laps) {
      const o = document.createElement("option");
      o.value = l.path;
      const star = l.path === bestPath ? "★ " : "";
      const pro = l.source === "pro" ? " [PRO]" : "";
      const clock = lapClock(l.recorded_utc);
      o.textContent = `${star}${l.lap_time}${l.valid ? "" : " " + t("lap.invalid")}${clock ? " · " + clock : ""}${pro}`;
      if (l.path === selectedPath) o.selected = true;
      sel.appendChild(o);
    }
  };
  fill("lap", keepLap || a.review.path);
  fill("baseline", keepBase || a.reference.path);
}

function drawSummary(a) {
  const gap = (a.review.lap_time_ms - a.reference.lap_time_ms) / 1000;
  const c = a.consistency || {};
  const item = (k, v, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  $("summary").innerHTML =
    item(t("lbl.comparison"), a.reference.lap_time) +
    item(t("lbl.lap"), a.review.lap_time) +
    item(t("lbl.gap"), fmt(gap) + "s", gap > 0 ? "slower" : "faster") +
    (c.n >= 2 ? item(t("sum.consistency"), `σ ${(c.std_ms / 1000).toFixed(3)}s · ${c.n} ${t("lbl.laps")}`) : "");
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
    return `<div class="cons-row">` +
      `<span class="corner">${l.label}</span>` +
      `<span class="cons-track"><span class="cons-fill" style="width:${w}%;background:${lossColor(sev)}"></span></span>` +
      `<span class="cons-nums"><b>−${l.lost_s.toFixed(3)}s</b> · ${l.message}</span>` +
      `</div>`;
  }).join("");
  el.innerHTML = `<h3>${t("wf.title")}</h3>` + rows;
}

function drawDebrief(a) {
  const el = $("debrief");
  const legend = cornerLegend(a);
  if (!a.losses.length) {
    el.innerHTML = `<h3>${t("debrief.title")}</h3>${legend}` +
      `<div class="clean">${t("debrief.clean")}</div>`;
    return;
  }
  let html = `<h3>${t("debrief.title")}</h3>${legend}`;
  for (const l of a.losses) {
    const major = l.lost_s >= 0.2 ? "major" : "";
    html += `<div class="loss ${major}">` +
      `<div class="loss-head"><span class="corner">${l.label}</span>` +
      `<span class="lost">−${l.lost_s.toFixed(3)}s</span></div>` +
      `<div class="cause">${l.message}</div>` +
      (l.detail ? `<div class="detail">${l.detail}</div>` : "") +
      (l.fix ? `<div class="fix">💡 ${l.fix}</div>` : "") +
      `</div>`;
  }
  el.innerHTML = html;
}

// --- canvas drawing -------------------------------------------------------
function setup(cv) {
  const r = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * r; cv.height = h * r;
  const ctx = cv.getContext("2d");
  ctx.setTransform(r, 0, 0, r, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

function cornerBands(ctx, w, h, corners) {
  ctx.fillStyle = "rgba(120,140,170,0.10)";
  for (const c of corners) ctx.fillRect(c.entry * w, 0, (c.exit - c.entry) * w, h);
  ctx.fillStyle = "rgba(255,255,255,0.35)";
  ctx.font = "10px Segoe UI";
  for (const c of corners) ctx.fillText("T" + (c.index + 1), c.apex * w - 6, 11);
}

function line(ctx, w, h, pos, vals, lo, hi, color, lw) {
  ctx.beginPath();
  const span = hi - lo || 1;
  for (let i = 0; i < pos.length; i++) {
    const x = pos[i] * w, y = h - ((vals[i] - lo) / span) * h;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.strokeStyle = color; ctx.lineWidth = lw || 1.5; ctx.stroke();
}

function crosshair(ctx, w, h, cx) {
  if (cx == null) return;
  const x = cx * w;
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
}

function axisLabel(ctx, w, top, bottom) {
  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px Segoe UI";
  ctx.fillText(top, w - 62, 12); ctx.fillText(bottom, w - 62, 145);
}

function redraw(cx) {
  if (!DATA) return;
  drawDelta(DATA, cx);
  drawSpeed(DATA, cx);
  drawInputs(DATA, cx);
  drawSteer(DATA, cx);
  drawMiniMap(DATA, cx);
  updateReadout(DATA, cx);
}

function drawDelta(a, cx) {
  const { ctx, w, h } = setup($("c-delta"));
  const d = a.review.delta;
  let m = 0.05;
  for (const v of d.delta_s) m = Math.max(m, Math.abs(v));
  const tint = (c) => `rgba(${c[0]},${c[1]},${c[2]},0.10)`;
  ctx.fillStyle = tint(PAL.slow); ctx.fillRect(0, 0, w, h / 2);
  ctx.fillStyle = tint(PAL.fast); ctx.fillRect(0, h / 2, w, h / 2);
  cornerBands(ctx, w, h, a.corners);
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, d.pos, d.delta_s, -m, m, "#ffffff", 2);
  axisLabel(ctx, w, `+${m.toFixed(2)}s`, `-${m.toFixed(2)}s`);
  crosshair(ctx, w, h, cx);
}

function drawSpeed(a, cx) {
  const { ctx, w, h } = setup($("c-speed"));
  const rv = a.review.channels, rf = a.reference.channels;
  let lo = Infinity, hi = -Infinity;
  for (const v of rv.speed.concat(rf.speed)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  lo = Math.floor(lo - 5); hi = Math.ceil(hi + 5);
  cornerBands(ctx, w, h, a.corners);
  line(ctx, w, h, rf.pos, rf.speed, lo, hi, "#3fd0e0", 1.5);
  line(ctx, w, h, rv.pos, rv.speed, lo, hi, "#ffffff", 1.5);
  axisLabel(ctx, w, hi + " km/h", lo + " km/h");
  crosshair(ctx, w, h, cx);
}

function drawInputs(a, cx) {
  const { ctx, w, h } = setup($("c-inputs"));
  const rv = a.review.channels, rf = a.reference.channels;
  cornerBands(ctx, w, h, a.corners);
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
    ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.font = "11px Segoe UI";
    ctx.fillText("No steering data for this lap.", 10, h / 2);
    return;
  }
  let m = 0.1;
  for (const v of sv) m = Math.max(m, Math.abs(v));
  if (Array.isArray(sf)) for (const v of sf) m = Math.max(m, Math.abs(v));
  cornerBands(ctx, w, h, a.corners);
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
  axisLabel(ctx, w, "left", "right");
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
  if (!anyData) {
    if (miss) miss.classList.remove("hidden");
    if (main) main.classList.add("hidden");
    if (coast) coast.innerHTML = "";
    $("dyn-tyres").classList.add("hidden");
    $("dyn-balance-wrap").classList.add("hidden");
    $("dyn-readout").innerHTML = t("dyn.readout");
    DYN_GG = null; DYN_BAL_HIT = null;
    return;
  }
  if (miss) miss.classList.add("hidden");
  if (main) main.classList.remove("hidden");
  drawCoasting(DATA);
  DYN_GG = drawGG(DATA, cx);
  drawSlip(DATA, cx);
  drawLineOffset(DATA, cx);
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
  ctx.font = "10px Segoe UI"; ctx.lineWidth = 1;
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
  ctx.fillStyle = "rgba(255,255,255,0.5)"; ctx.font = "10px Segoe UI";
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
function drawSlip(a, cx) {
  const cv = $("c-slip");
  if (!cv) return;
  const { ctx, w, h } = setup(cv);
  const c = a.review.channels;
  const sf = c.slip_front || [], sr = c.slip_rear || [], pos = c.pos || [];
  let m = 0.15;
  for (const v of sf) m = Math.max(m, Math.abs(v));
  for (const v of sr) m = Math.max(m, Math.abs(v));
  cornerBands(ctx, w, h, a.corners);
  // Zero line.
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, pos, sr, -m, m, "#FFB020", 1.4);   // rear
  line(ctx, w, h, pos, sf, -m, m, "#22D3CE", 1.5);   // front
  axisLabel(ctx, w, t("dyn.slip.spin"), t("dyn.slip.lock"));
  crosshair(ctx, w, h, cx);
}

// Line deviation: signed metres off the reference line, over the position axis.
// Above zero = one side, below = the other — where you run wide or tight. Hidden
// when the lap (or its reference) has no map coordinates.
function drawLineOffset(a, cx) {
  const wrap = $("lineoff-wrap");
  const off = a.review.line_offset;
  if (!wrap) return;
  if (!Array.isArray(off) || !off.length) { wrap.classList.add("hidden"); return; }
  wrap.classList.remove("hidden");
  const { ctx, w, h } = setup($("c-lineoff"));
  const pos = a.review.channels.pos;
  let m = 1.0;
  for (const v of off) m = Math.max(m, Math.abs(v));
  cornerBands(ctx, w, h, a.corners);
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, pos, off, -m, m, "#c58cff", 1.6);
  axisLabel(ctx, w, `+${m.toFixed(1)}m`, `-${m.toFixed(1)}m`);
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
  let ms = 0.1, my = 0.1;
  for (const v of st) ms = Math.max(ms, Math.abs(v));
  for (const v of yw) my = Math.max(my, Math.abs(v));
  cornerBands(ctx, w, h, a.corners);
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
  line(ctx, w, h, pos, yw.map((v) => -v), -my, my, "#FFB020", 1.4);
  line(ctx, w, h, pos, st, -ms, ms, "#ffffff", 1.5);
  axisLabel(ctx, w, "left", "right");
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
  for (const v of rpm) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const rlo = lo, rhi = hi;
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
  cornerBands(ctx, w, h, a.corners);
  line(ctx, w, h, pos, rpm, lo, hi, "#34E08A", 1.4);
  const gnum = (g) => { const n = parseInt(g, 10); return isNaN(n) ? null : n; };
  for (let i = 1; i < gear.length; i++) {
    const g0 = gnum(gear[i - 1]), g1 = gnum(gear[i]);
    if (g0 == null || g1 == null || g0 === g1) continue;
    const x = pos[i] * w, up = g1 > g0, y = up ? 10 : h - 4;
    ctx.fillStyle = up ? "#22D3CE" : "#FFB020";
    ctx.beginPath();
    if (up) { ctx.moveTo(x, y - 6); ctx.lineTo(x - 4, y); ctx.lineTo(x + 4, y); }
    else { ctx.moveTo(x, y); ctx.lineTo(x - 4, y - 6); ctx.lineTo(x + 4, y - 6); }
    ctx.closePath(); ctx.fill();
  }
  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px Segoe UI";
  ctx.fillText(Math.round(rhi) + "", w - 46, 12);
  ctx.fillText(Math.round(rlo) + "", w - 46, h - 4);
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
  ctx.fillStyle = "rgba(255,255,255,0.45)"; ctx.font = "10px Segoe UI";
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
    `<b>${t("ro.pos")} ${Math.round(p * 100)}%</b> &nbsp;·&nbsp; ` +
    `${t("dyn.ro.g")} <b>${gt.toFixed(2)}g</b> <span class="muted">(${t("dyn.ro.lat")} ${gl.toFixed(2)}, ${t("dyn.ro.lon")} ${gL.toFixed(2)})</span> &nbsp;·&nbsp; ` +
    `${t("dyn.ro.slipF")} <b>${sf.toFixed(2)}</b>  ${t("dyn.ro.slipR")} <b>${sr.toFixed(2)}</b>` + extra;
}

function updateDynReadout(a, p) {
  LAST_HOVER = p;
  const el = $("dyn-readout");
  if (!el) return;
  if (p == null) { el.innerHTML = t("dyn.readout"); return; }
  el.innerHTML = dynReadoutHTML(a, p);
}

// --- hover / readout ------------------------------------------------------
function nearest(posArr, p) {
  let lo = 0, hi = posArr.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (posArr[mid] < p) lo = mid + 1; else hi = mid; }
  if (lo > 0 && Math.abs(posArr[lo - 1] - p) < Math.abs(posArr[lo] - p)) return lo - 1;
  return lo;
}

// Point-by-point readout markup at lap position p (0..1). Shared by the Compare
// charts and the Map hover so both reuse the same nearest() lookup.
function readoutHTML(a, p) {
  const rv = a.review.channels, rf = a.reference.channels, d = a.review.delta;
  const iv = nearest(rv.pos, p), ir = nearest(rf.pos, p), id = nearest(d.pos, p);
  const yv = rv.speed[iv], rfv = rf.speed[ir], dv = yv - rfv, dl = d.delta_s[id];
  const corner = (a.corners || []).find((c) => p >= c.entry && p <= c.exit);
  const where = corner ? `<b class="muted">${corner.name}</b> &nbsp;·&nbsp; ` : "";
  return where +
    `<b>${t("ro.pos")} ${Math.round(p * 100)}%</b> &nbsp;·&nbsp; ` +
    `${t("ro.speed")} <b>${yv.toFixed(0)}</b> <span class="muted">(${t("ro.ref")} ${rfv.toFixed(0)}, ${dv >= 0 ? "+" : ""}${dv.toFixed(0)})</span> &nbsp;·&nbsp; ` +
    `Δ <b class="${dl > 0 ? "slower" : "faster"}">${dl >= 0 ? "+" : ""}${dl.toFixed(3)}s</b> &nbsp;·&nbsp; ` +
    `${t("ro.throttle")} <b>${Math.round(rv.throttle[iv] * 100)}%</b>  ${t("ro.brake")} <b>${Math.round(rv.brake[iv] * 100)}%</b> &nbsp;·&nbsp; ` +
    `${t("ro.gear")} <b>${rv.gear[iv]}</b>`;
}

function updateReadout(a, p) {
  LAST_HOVER = p;
  const el = $("readout");
  if (p == null) { el.innerHTML = t("readout.hint"); return; }
  el.innerHTML = readoutHTML(a, p);
}

function wireHover() {
  if (HOVER_WIRED) return;
  HOVER_WIRED = true;
  const canvases = ["c-delta", "c-speed", "c-inputs", "c-steer"].map($);
  const onMove = (e) => {
    const rect = canvases[0].getBoundingClientRect();
    const p = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    redraw(p);
  };
  const onLeave = () => redraw(null);
  for (const cv of canvases) {
    if (!cv) continue;
    cv.addEventListener("mousemove", onMove);
    cv.addEventListener("mouseleave", onLeave);
  }

  // Map / mini-map hover: the x-axis isn't position, so find the nearest track
  // sample in screen space (transform captured when the map was drawn) and reuse
  // its pos to drive the shared crosshair + readout.
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
      if (p == null) return;
      drawMap(DATA, p);
      $("map-readout").innerHTML = readoutHTML(DATA, p);
    });
    map.addEventListener("mouseleave", () => {
      $("map-readout").innerHTML = MAP_READOUT_DEFAULT();
      if (DATA) drawMap(DATA, null);
    });
  }

  // Mini-map (Compare view) hover drives the chart crosshairs + readout too, so
  // it's bidirectional with the traces.
  const mini = $("c-minimap");
  if (mini) {
    mini.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const p = nearestPos(MINI_HIT, mini, e);
      if (p != null) redraw(p);
    });
    mini.addEventListener("mouseleave", () => redraw(null));
  }

  // Dynamics tab: the slip trace is on the position axis (same as the Compare
  // charts), the G-G scatter isn't — so slip hover reads cursor→position, while
  // G-G hover finds the nearest dot in screen space and reuses its position.
  const slip = $("c-slip");
  if (slip) {
    slip.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const rect = slip.getBoundingClientRect();
      const p = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      drawDynamics(p);
    });
    slip.addEventListener("mouseleave", () => { if (DATA) drawDynamics(null); });
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
      if (best >= 0) drawDynamics(pts[best].pos);
    });
    gg.addEventListener("mouseleave", () => { if (DATA) drawDynamics(null); });
  }
  const ribbon = $("c-balance");
  if (ribbon) {
    ribbon.addEventListener("mousemove", (e) => {
      if (!DATA) return;
      const p = nearestPos(DYN_BAL_HIT, ribbon, e);
      if (p != null) drawDynamics(p);
    });
    ribbon.addEventListener("mouseleave", () => { if (DATA) drawDynamics(null); });
  }
}

// Debounced so a resize drag fires once at rest, not per pixel. Compare/Map
// just redraw from the in-memory payload (no refetch, no flicker or response
// race); Sectors/Progress re-run their loader once at the end.
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
  fillCombos();
  if (DATA) fillLaps(DATA, true);
  if (VIEW === "compare") {
    if (DATA) {
      drawSummary(DATA);
      drawCornerSpeeds(DATA);
      drawWaterfall(DATA);
      drawDebrief(DATA);
      redraw(LAST_HOVER);
    }
  } else if (VIEW === "map") {
    if (DATA) { $("map-readout").innerHTML = MAP_READOUT_DEFAULT(); drawMap(DATA, null); }
  } else if (VIEW === "dynamics") {
    if (DATA) drawDynamics(LAST_HOVER);
  } else if (VIEW === "sectors") {
    if (CURRENT) loadSectors();
  } else if (VIEW === "progress") {
    if (CURRENT) loadProgress(CURRENT);
  }
};

wireTour();
wireCbToggle();
init();
