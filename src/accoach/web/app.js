"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (s) => (s >= 0 ? "+" : "") + s.toFixed(3);

let CURRENT = null;   // current combo {car, track}
let DATA = null;      // last /api/analysis payload
let VIEW = "compare"; // "compare" | "progress"
let HOVER_WIRED = false;

function fmtMs(ms) {
  if (!ms || ms <= 0) return "--:--.---";
  const m = Math.floor(ms / 60000);
  const s = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
  return `${m}:${s}`;
}

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function init() {
  let combos;
  try { combos = await getJSON("/api/combos"); } catch (e) { combos = []; }
  if (!combos.length) { document.body.classList.add("no-data"); return; }
  const sel = $("combo");
  sel.innerHTML = "";
  for (const c of combos) {
    const o = document.createElement("option");
    o.value = JSON.stringify({ car: c.car, track: c.track });
    o.textContent = `${c.car} · ${c.track}  (${c.laps} laps, best ${c.best})`;
    sel.appendChild(o);
  }
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
  if (window.HoneTour) window.HoneTour.auto(TOUR_STEPS, "hone_tour_analysis");
}

// Guided tour (vanilla coachmarks — see tour.js). Selectors are real elements
// in index.html; missing/hidden ones are skipped by the tour engine.
const TOUR_STEPS = [
  { sel: "#combo", title: "Pick a lap",
    text: "Choose the car and track. HONE compares your laps for this combo." },
  { sel: ".tabs", title: "Four views",
    text: "Compare two laps, see them on the Map, split by Sectors, or follow Trends over time." },
  { sel: "#c-delta", title: "Delta",
    text: "Where you're gaining or losing vs your reference, across the lap. Green (below the line) is faster." },
  { sel: "#vmin", title: "Min speed per corner",
    text: "Apex speed in every corner vs the reference — green means you carried more speed." },
  { sel: "#debrief", title: "Where to improve",
    text: "Your biggest time losses, corner by corner, with the likely cause and a fix." },
  { sel: ".export", title: "Take it with you",
    text: "Export the lap as CSV or JSON for deeper analysis." },
];

function wireTour() {
  const btn = document.querySelector(".tour-help");
  if (btn && window.HoneTour) {
    btn.onclick = () => window.HoneTour.start(TOUR_STEPS, "hone_tour_analysis");
  }
}

function wireTabs() {
  for (const b of document.querySelectorAll(".tab")) {
    b.onclick = () => {
      for (const x of document.querySelectorAll(".tab")) x.classList.toggle("active", x === b);
      VIEW = b.dataset.view;
      $("view-compare").classList.toggle("hidden", VIEW !== "compare");
      $("view-map").classList.toggle("hidden", VIEW !== "map");
      $("view-sectors").classList.toggle("hidden", VIEW !== "sectors");
      $("view-progress").classList.toggle("hidden", VIEW !== "progress");
      if (VIEW === "progress" && CURRENT) loadProgress(CURRENT);
      if (VIEW === "map" && DATA) drawMap(DATA, null);
      if (VIEW === "sectors" && CURRENT) loadSectors();
    };
  }
}

async function loadProgress(combo) {
  let p;
  try { p = await getJSON("/api/progress?" + new URLSearchParams({ car: combo.car, track: combo.track })); }
  catch (e) {
    $("prog-summary").innerHTML = "";
    $("levels").innerHTML = ""; $("trends").innerHTML = "";
    $("recurring").innerHTML =
      `<div class="clean">Couldn't load progress — is the analysis backend running?</div>`;
    return;
  }

  const c = p.consistency || {};
  const item = (k, v) => `<div class="item"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  $("prog-summary").innerHTML = c.n
    ? item("Valid laps", c.n) + item("Best", fmtMs(c.best_ms)) +
      item("Average", fmtMs(c.mean_ms)) + item("Spread", (c.spread_ms / 1000).toFixed(3) + "s") +
      item("σ", (c.std_ms / 1000).toFixed(3) + "s")
    : item("—", "no valid lap");

  drawProgress(p);
  renderLevels(p.levels);
  renderTrends(p.trends);

  const el = $("recurring");
  if (!p.recurring.length) {
    el.innerHTML = `<div class="clean">No recurring mistakes — nice consistency!</div>`;
  } else {
    el.innerHTML = p.recurring.map((r) =>
      `<div class="recur"><span class="count">${r.count}×</span>` +
      `<span class="msg">${r.message}</span>` +
      `<span class="where">Corners: ${r.corners.join(", ")}</span></div>`).join("");
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
      gap = `<span class="lvl-gap base">your reference</span>`;
    } else if (lv.gain_s > 0) {
      const hint = lv.key === "ideal" ? "consistency on the table" : "gap to PRO";
      gap = `<span class="lvl-gap faster">−${lv.gain_s.toFixed(3)}s</span>` +
            `<span class="lvl-hint">${hint}</span>`;
    } else {
      const ahead = Math.abs(lv.gain_s).toFixed(3);
      gap = `<span class="lvl-gap done">✓ already beaten</span>` +
            `<span class="lvl-hint">+${ahead}s vs PRO</span>`;
    }
    rows += `<div class="lvl" data-key="${lv.key}">` +
      `<span class="lvl-label">${lv.label}</span>` +
      `<span class="lvl-time">${lv.lap_time}</span>` +
      gap + `</div>`;
  }
  el.innerHTML = `<h3>Levels <small>(best → ideal → PRO · gap = time available)</small></h3>` +
    `<div class="ladder">${rows}</div>`;
}

// Per-corner weaknesses: systematic (train it) vs sporadic (one-off).
function renderTrends(trends) {
  const el = $("trends");
  if (!el) return;
  if (!trends || !trends.length) {
    el.innerHTML = `<div class="clean">No recurring weak points — nice consistency!</div>`;
    return;
  }
  el.innerHTML = trends.map((t) => {
    const sys = t.systematic;
    const badge = sys
      ? `<span class="wk-badge on">Systematic</span>`
      : `<span class="wk-badge off">Sporadic</span>`;
    const tag = sys ? "to train" : "one-off";
    return `<div class="weak ${sys ? "sys" : ""}">` +
      `<div class="weak-head">` +
      `<span class="corner">${t.name}</span>${badge}` +
      `<span class="lost">−${t.total_s.toFixed(3)}s</span></div>` +
      `<div class="detail">${tag} · ` +
      `median −${t.median_s.toFixed(3)}s · ${t.occurrences}/${t.laps} laps</div>` +
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
    item("Comparison", s.baseline.lap_time) +
    item("Lap", s.review.lap_time) +
    item("Gap", fmt(gap) + "s", gap > 0 ? "slower" : "faster") +
    item("Sectors", s.real ? "real track sectors" : "thirds (position)");

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
      `<h3>Ideal lap</h3>` +
      `<div class="ideal-time">${s.ideal.ideal}` +
      (gain > 0 ? ` <span class="faster">potential −${gain.toFixed(3)}s</span>` : "") +
      `</div><div class="ideal-from">${from}</div>` +
      `<div class="muted small">Your best sectors so far, stitched together.</div>`;
  } else {
    $("ideal").innerHTML = "";
  }
}

// --- track map ------------------------------------------------------------
function deltaColor(d, m) {
  // slower (d>0) -> Delta Red, faster (d<0) -> Delta Green, near-zero -> pale.
  // Colour is doubled up with segment width (see drawMap) so the read survives
  // red/green colour-blindness — the line gets THICKER the more time is lost.
  const t = Math.max(-1, Math.min(1, d / (m || 1)));
  if (t >= 0) return `rgb(255,${Math.round(220 - 143 * t)},${Math.round(225 - 131 * t)})`; // pale -> #FF4D5E
  return `rgb(${Math.round(232 + 180 * t)},${224},${Math.round(228 + 90 * t)})`;            // pale -> #34E08A
}

function drawMap(a, cx) {
  const missing = $("map-missing"), canvas = $("c-map");
  if (!a.has_map) {
    missing.classList.remove("hidden");
    canvas.style.display = "none";
    return;
  }
  missing.classList.add("hidden");
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
  const X = (x) => (x - minX) * s + offX;
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

  // Your line: colour each segment by the delta AND scale its width by |delta|,
  // so the read survives red/green colour-blindness (thicker = more time lost).
  let mx = 0.05;
  for (const v of d.delta_s) mx = Math.max(mx, Math.abs(v));
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (let i = 1; i < rv.x.length; i++) {
    const dv = d.delta_s[i] || 0;
    const t = Math.min(1, Math.abs(dv) / (mx || 1));
    ctx.lineWidth = 2 + 5 * t;   // 2px at parity -> 7px at biggest swing
    ctx.beginPath();
    ctx.moveTo(X(rv.x[i - 1]), Y(rv.z[i - 1]));
    ctx.lineTo(X(rv.x[i]), Y(rv.z[i]));
    ctx.strokeStyle = deltaColor(dv, mx);
    ctx.stroke();
  }

  // Braking points: where your brake first crosses onset.
  const br = rv.brake;
  ctx.fillStyle = "#FFB020";
  for (let i = 1; i < br.length; i++) {
    if (br[i] >= 0.3 && br[i - 1] < 0.3) {
      const px = X(rv.x[i]), py = Y(rv.z[i]);
      ctx.beginPath();
      ctx.moveTo(px, py - 6); ctx.lineTo(px - 5, py - 14); ctx.lineTo(px + 5, py - 14);
      ctx.closePath(); ctx.fill();
    }
  }

  // Corner labels at each apex.
  ctx.fillStyle = "rgba(255,255,255,0.85)"; ctx.font = "11px Segoe UI";
  for (const c of a.corners || []) {
    const i = nearest(rv.pos, c.apex);
    ctx.fillText("T" + (c.index + 1), X(rv.x[i]) + 6, Y(rv.z[i]) - 4);
  }

  // Start/finish.
  ctx.fillStyle = "#22D3CE";
  ctx.beginPath(); ctx.arc(X(rv.x[0]), Y(rv.z[0]), 4, 0, 6.283); ctx.fill();

  // Hover marker.
  if (cx != null) {
    const i = nearest(rv.pos, cx);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(X(rv.x[i]), Y(rv.z[i]), 6, 0, 6.283); ctx.stroke();
  }
}

function reloadSelection() {
  loadCombo(CURRENT, $("lap").value, $("baseline").value);
}

function exportData(fmt) {
  if (!CURRENT) return;
  const q = new URLSearchParams({ car: CURRENT.car, track: CURRENT.track, fmt });
  const lap = $("lap").value;
  if (lap) q.set("lap", lap);
  window.location = "/api/export?" + q.toString();
}

async function loadCombo(combo, lapPath, baselinePath) {
  CURRENT = combo;
  const q = new URLSearchParams({ car: combo.car, track: combo.track });
  if (lapPath) q.set("lap", lapPath);
  if (baselinePath) q.set("baseline", baselinePath);
  let a;
  try { a = await getJSON("/api/analysis?" + q.toString()); }
  catch (e) {
    $("summary").innerHTML =
      `<div class="item"><div class="v">—</div><div class="k">Couldn't load this lap.</div></div>`;
    return;
  }
  DATA = a;
  fillLaps(a);
  drawSummary(a);
  drawCornerSpeeds(a);
  drawDebrief(a);
  redraw(null);
  if (VIEW === "map") drawMap(a, null);
  if (VIEW === "sectors") loadSectors();
  wireHover();
}

function fillLaps(a) {
  const key = a.car + a.track;
  if ($("lap").dataset.for === key) return;  // keep selections within a combo
  $("lap").dataset.for = key;

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
      o.textContent = `${star}${l.lap_time}${l.valid ? "" : " (invalid)"}${pro}`;
      if (l.path === selectedPath) o.selected = true;
      sel.appendChild(o);
    }
  };
  fill("lap", a.review.path);
  fill("baseline", a.reference.path);
}

function drawSummary(a) {
  const gap = (a.review.lap_time_ms - a.reference.lap_time_ms) / 1000;
  const c = a.consistency || {};
  const item = (k, v, cls) =>
    `<div class="item"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  $("summary").innerHTML =
    item("Comparison", a.reference.lap_time) +
    item("Lap", a.review.lap_time) +
    item("Gap", fmt(gap) + "s", gap > 0 ? "slower" : "faster") +
    (c.n >= 2 ? item("Consistency", `σ ${(c.std_ms / 1000).toFixed(3)}s · ${c.n} laps`) : "");
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
    `<h3>Min speed per corner <small>(km/h · green = faster than reference)</small></h3>` +
    `<table class="vmin-table"><thead><tr>` +
    `<th>Corner</th><th>You</th><th>Ref</th><th>Δ</th>` +
    `</tr></thead><tbody>${body}</tbody></table>`;
}

function cornerLegend(a) {
  if (!a.corners || !a.corners.length) return "";
  return `<div class="legend">` + a.corners.map((c) =>
    `<span><b>T${c.index + 1}</b>${c.name}</span>`).join("") + `</div>`;
}

function drawDebrief(a) {
  const el = $("debrief");
  const legend = cornerLegend(a);
  if (!a.losses.length) {
    el.innerHTML = `<h3>Where to improve</h3>${legend}` +
      `<div class="clean">Clean lap — no significant time lost per corner.</div>`;
    return;
  }
  let html = `<h3>Where to improve</h3>${legend}`;
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
  updateReadout(DATA, cx);
}

function drawDelta(a, cx) {
  const { ctx, w, h } = setup($("c-delta"));
  const d = a.review.delta;
  let m = 0.05;
  for (const v of d.delta_s) m = Math.max(m, Math.abs(v));
  ctx.fillStyle = "rgba(255,59,48,0.10)"; ctx.fillRect(0, 0, w, h / 2);
  ctx.fillStyle = "rgba(34,221,102,0.10)"; ctx.fillRect(0, h / 2, w, h / 2);
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

// --- hover / readout ------------------------------------------------------
function nearest(posArr, p) {
  let lo = 0, hi = posArr.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (posArr[mid] < p) lo = mid + 1; else hi = mid; }
  if (lo > 0 && Math.abs(posArr[lo - 1] - p) < Math.abs(posArr[lo] - p)) return lo - 1;
  return lo;
}

function updateReadout(a, p) {
  const el = $("readout");
  if (p == null) { el.innerHTML = "Hover over the charts for point-by-point values…"; return; }
  const rv = a.review.channels, rf = a.reference.channels, d = a.review.delta;
  const iv = nearest(rv.pos, p), ir = nearest(rf.pos, p), id = nearest(d.pos, p);
  const yv = rv.speed[iv], rfv = rf.speed[ir], dv = yv - rfv, dl = d.delta_s[id];
  const corner = (a.corners || []).find((c) => p >= c.entry && p <= c.exit);
  const where = corner ? `<b class="muted">${corner.name}</b> &nbsp;·&nbsp; ` : "";
  el.innerHTML = where +
    `<b>Pos ${Math.round(p * 100)}%</b> &nbsp;·&nbsp; ` +
    `Speed <b>${yv.toFixed(0)}</b> <span class="muted">(ref ${rfv.toFixed(0)}, ${dv >= 0 ? "+" : ""}${dv.toFixed(0)})</span> &nbsp;·&nbsp; ` +
    `Δ <b class="${dl > 0 ? "slower" : "faster"}">${dl >= 0 ? "+" : ""}${dl.toFixed(3)}s</b> &nbsp;·&nbsp; ` +
    `Throttle <b>${Math.round(rv.throttle[iv] * 100)}%</b>  Brake <b>${Math.round(rv.brake[iv] * 100)}%</b> &nbsp;·&nbsp; ` +
    `Gear <b>${rv.gear[iv]}</b>`;
}

function wireHover() {
  if (HOVER_WIRED) return;
  HOVER_WIRED = true;
  const canvases = ["c-delta", "c-speed", "c-inputs"].map($);
  const onMove = (e) => {
    const rect = canvases[0].getBoundingClientRect();
    const p = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    redraw(p);
  };
  const onLeave = () => redraw(null);
  for (const cv of canvases) {
    cv.addEventListener("mousemove", onMove);
    cv.addEventListener("mouseleave", onLeave);
  }
}

// Debounced so a resize drag fires once at rest, not per pixel. Compare/Map
// just redraw from the in-memory payload (no refetch, no flicker or response
// race); Sectors/Progress re-run their loader once at the end.
let _resizeTimer = null;
window.addEventListener("resize", () => {
  if (!CURRENT) return;
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    if (VIEW === "map") { if (DATA) drawMap(DATA, null); }
    else if (VIEW === "sectors") loadSectors();
    else if (VIEW === "progress") loadProgress(CURRENT);
    else redraw(null);                 // compare: redraw from DATA
  }, 150);
});
wireTour();
init();
