"use strict";
// Engineer page: live diagnosis (WebSocket) + setup editor (REST /api/setup/*).
// Vanilla JS, no libraries — same constraint as the analysis app.

const WS_PORT = 8777;            // the live backend; the page itself is on 8778
const $ = (id) => document.getElementById(id);
// i18n: translate a chrome string (defensive if i18n.js failed to load).
const t = (k) => (window.HoneI18n ? window.HoneI18n.t(k) : k);
const LANG = () => (window.HoneI18n ? window.HoneI18n.lang : "en");

const state = {
  car: null, track: null,
  setupPath: null, setupName: null,
  params: [],                    // from /api/setup/current
  base: {},                      // key "param#slot" -> original click
  pending: {},                   // key "param#slot" -> delta (clicks)
  autoSelected: false,
  lastWritten: null,             // file name written this session (box reminder)
  lastLive: null,                // last live payload, for re-render on lang switch
};

const slotKey = (param, i) => `${param}#${i}`;

async function api(url, opts) {
  // Pass the active language so backend-generated content arrives localised
  // (the backend ignores &lang until it handles it — harmless today).
  if (url.indexOf("/api/") === 0) {
    url += (url.indexOf("?") === -1 ? "?" : "&") + "lang=" + encodeURIComponent(LANG());
  }
  const r = await fetch(url, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch (e) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json();
}

// ---- combos / setup loading ----------------------------------------------

async function loadCombos() {
  const combos = await api("/api/setup/combos");
  const sel = $("combo");
  sel.innerHTML = "";
  if (!combos.length) {
    sel.innerHTML = `<option value="">${t("eng.noSetupOpt")}</option>`;
    return;
  }
  // Group the (potentially many) cars by engineer class for a usable dropdown.
  const groups = { GT3: [], Formula: [], Road: [] };
  for (const c of combos) groups[classOf(c.car)].push(c);
  for (const [cls, items] of Object.entries(groups)) {
    if (!items.length) continue;
    const og = document.createElement("optgroup");
    og.label = `${cls} (${items.length})`;
    for (const c of items) {
      const o = document.createElement("option");
      o.textContent = `${c.car}  ·  ${c.track}  (${c.count})`;
      o.dataset.car = c.car; o.dataset.track = c.track;
      og.appendChild(o);
    }
    sel.appendChild(og);
  }
  await onComboChange();
}

// Client-side mirror of engineer.classmap (avoids 77 API calls to group cars).
function classOf(car) {
  const k = (car || "").toLowerCase();
  const formula = ["formula", "f1_", "_f1", "f2_", "f3_", "f3000", "312t",
                   "_98t", "indycar", "open_wheel", "tatuus", "dallara_f",
                   "rss_formula", "lotus_98t", "lotus_exos"];
  if (formula.some((m) => k.includes(m))) return "Formula";
  if (["gt3", "gt4", "gt2", "gte", "gt_"].some((m) => k.includes(m))) return "GT3";
  return "Road";
}

async function onComboChange() {
  const opt = $("combo").selectedOptions[0];
  if (!opt || !opt.dataset.car) return;
  state.car = opt.dataset.car; state.track = opt.dataset.track;
  await loadClass(state.car);   // sets state.alVolo before the setup renders
  const list = await api(`/api/setup/list?car=${encodeURIComponent(state.car)}` +
                         `&track=${encodeURIComponent(state.track)}`);
  const sel = $("setup");
  sel.innerHTML = "";
  for (const s of list) {
    const o = document.createElement("option");
    o.textContent = s.name; o.dataset.path = s.path;
    sel.appendChild(o);
  }
  await onSetupChange();
}

async function loadClass(car) {
  let info;
  try { info = await api(`/api/setup/class?car=${encodeURIComponent(car)}`); }
  catch (e) { return; }
  const chip = $("class-chip");
  chip.textContent = info.class;
  chip.dataset.cls = info.class;
  chip.hidden = false;
  $("prof-name").textContent = `${t("eng.engPrefix")}${info.profile.name}`;
  $("prof-phases").textContent = info.profile.phases.join(" → ");
  $("prof-alvolo").textContent = info.profile.al_volo.join(", ");
  $("eng-profile").hidden = false;
  // Remember which adjustments are tweakable on track (vs pit-only) so the
  // editor can badge them — the rest only take effect when you reload at the box.
  state.alVolo = (info.profile.al_volo || []).map((s) => s.toLowerCase());
}

// Shown when a car/track has no setup files at all — explain where HONE looks
// so the contradiction ("choose a setup" with an empty dropdown) is resolved.
const noSetupHTML = () => `<div class="empty2">${t("eng.noSetupBody")}</div>`;

async function onSetupChange() {
  const opt = $("setup").selectedOptions[0];
  if (!opt || !opt.dataset.path) { $("setup-body").innerHTML = noSetupHTML(); return; }
  state.setupPath = opt.dataset.path;
  const data = await api(`/api/setup/current?path=${encodeURIComponent(state.setupPath)}`);
  state.setupName = data.name;
  state.params = data.params;
  state.pending = {};
  state.base = {};
  for (const p of data.params) {
    p.slots.forEach((s, i) => { state.base[slotKey(p.key, i)] = s.click; });
  }
  $("setup-car").textContent = `· ${data.car} · ${data.name}`;
  renderSetup(data);
  renderTray();
}

// ---- rendering -----------------------------------------------------------

function renderSetup(data) {
  const body = $("setup-body");
  body.innerHTML = "";
  for (const g of data.groups) {
    const wrap = document.createElement("div");
    wrap.className = "grp";
    const title = document.createElement("div");
    title.className = "grp-title"; title.textContent = g;
    wrap.appendChild(title);
    for (const p of data.params.filter((x) => x.group === g)) {
      wrap.appendChild(renderParam(p));
    }
    body.appendChild(wrap);
  }
}

// A parameter is "al volo" (adjustable on track, no pit stop) when its group or
// label is in the active profile's al-volo set — typically brake bias, TC, ABS,
// engine map. Everything else only takes effect after reloading the setup at the
// box, so the badge tells the driver which levers they can also pull live.
function isAlVolo(p) {
  const av = state.alVolo || [];
  const g = (p.group || "").toLowerCase(), l = (p.label || "").toLowerCase();
  return av.some((a) =>
    a === g || a === l ||
    // short electronic codes ("tc") should also catch their numbered slots ("tc1", "tc2")
    (l.startsWith(a) && /^\d/.test(l.slice(a.length))));
}

function renderParam(p) {
  const row = document.createElement("div");
  row.className = "param";
  const label = document.createElement("div");
  label.className = "param-label";
  label.innerHTML = `${p.label}${p.note ? `<span class="note">${p.note}</span>` : ""}`;
  if (isAlVolo(p)) {
    const tag = document.createElement("span");
    tag.className = "av-tag";
    tag.textContent = t("eng.alvoloTag");
    tag.title = t("eng.alvoloHint");
    label.appendChild(tag);
  }
  row.appendChild(label);

  const slots = document.createElement("div");
  slots.className = "slots";
  p.slots.forEach((s, i) => slots.appendChild(renderSlot(p, s, i)));
  row.appendChild(slots);
  return row;
}

function renderSlot(p, s, i) {
  const key = slotKey(p.key, i);
  const delta = state.pending[key] || 0;
  const cur = state.base[key] + delta;

  const el = document.createElement("div");
  el.className = "slot" + (delta ? " changed" : "");
  el.dataset.key = key;          // lets refocusSlot find this node after rerender

  // The slot itself is the keyboard control (a spinbutton): one tab stop, the
  // -/+ buttons are mouse affordances kept out of the tab order (see below).
  el.tabIndex = 0;
  el.setAttribute("role", "spinbutton");
  el.setAttribute("aria-valuenow", String(cur));
  const where = s.slot ? ` ${s.slot}` : "";
  el.setAttribute("aria-label", `${p.label}${where}: ${cur}`);
  el.onkeydown = (ev) => onSlotKey(ev, p.key, i);

  const minus = document.createElement("button");
  minus.type = "button"; minus.tabIndex = -1;
  minus.textContent = "−"; minus.title = "−1 click (hold to go faster)";
  minus.setAttribute("aria-hidden", "true");
  wireHold(minus, p.key, i, -1);

  const val = document.createElement("div");
  val.className = "val";
  const physTxt = delta ? "" : `<span class="phys">${s.physical}</span>`;
  val.innerHTML = `${cur}${physTxt}`;

  const plus = document.createElement("button");
  plus.type = "button"; plus.tabIndex = -1;
  plus.textContent = "+"; plus.title = "+1 click (hold to go faster)";
  plus.setAttribute("aria-hidden", "true");
  wireHold(plus, p.key, i, +1);

  if (s.slot) {
    const sl = document.createElement("div");
    sl.className = "sl"; sl.textContent = s.slot;
    el.appendChild(sl);
  }
  el.appendChild(minus); el.appendChild(val); el.appendChild(plus);
  if (delta) {
    const d = document.createElement("div");
    d.className = "delta"; d.textContent = (delta > 0 ? "+" : "") + delta;
    el.appendChild(d);
  }
  return el;
}

// Keyboard handling for a focused slot. A rerender() rebuilds the DOM, so after
// a bump we restore focus to the slot at the same param/index position.
function onSlotKey(ev, param, i) {
  let dir = 0, page = false;
  switch (ev.key) {
    case "ArrowUp": case "ArrowRight": case "+": case "=": dir = 1; break;
    case "ArrowDown": case "ArrowLeft": case "-": case "−": dir = -1; break;
    case "PageUp": dir = 1; page = true; break;
    case "PageDown": dir = -1; page = true; break;
    default: return;            // leave Tab and everything else to the browser
  }
  ev.preventDefault();
  if (page) { bump(param, i, dir * 5); refocusSlot(param, i); return; }
  // Holding the key auto-repeats: accelerate just like holding a +/- button. A
  // fresh press (ev.repeat false) resets the ramp; no keyup handler needed.
  _kbCount = ev.repeat ? _kbCount + 1 : 0;
  bump(param, i, dir * rampStep(_kbCount));
  refocusSlot(param, i);
}

// rerender() replaces the slots' DOM nodes, so find the freshly-built slot for
// this param/index and re-focus it. Defensive: do nothing if it's gone.
function refocusSlot(param, i) {
  const sel = `.slot[data-key="${cssEscape(slotKey(param, i))}"]`;
  const el = document.querySelector(sel);
  if (el && typeof el.focus === "function") el.focus();
}

function cssEscape(v) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(v);
  return String(v).replace(/["\\]/g, "\\$&");   // enough for our "param#slot" keys
}

function bump(param, slot, step) {
  addDelta(param, slot, step);
  rerender();
}

function addDelta(param, slot, step) {
  const key = slotKey(param, slot);
  if (state.base[key] === undefined) return false;   // param not in this setup
  const cur = state.base[key] + (state.pending[key] || 0);
  if (cur + step < 0) return false;           // clicks can't go negative
  const delta = (state.pending[key] || 0) + step;
  if (delta === 0) delete state.pending[key];
  else state.pending[key] = delta;
  return true;
}

// --- press-and-hold to accelerate -----------------------------------------
// Holding a +/- button (mouse/touch) or an arrow key ramps the step up the
// longer you hold, so a big setup swing doesn't need dozens of taps. A quick
// tap is still exactly one click. During a hold we update just the held slot in
// place (a full rerender() would replace the very button you're holding); one
// rerender() on release syncs the tray and badges.
const _STEP_RAMP = [1, 1, 1, 2, 2, 3, 5];   // step by tick #, saturates at the end
const rampStep = (n) => _STEP_RAMP[Math.min(n, _STEP_RAMP.length - 1)];

const _hold = { timer: null, interval: null, count: 0, param: null, i: null, dir: 0 };
let _kbCount = 0;   // consecutive auto-repeat keydowns, for keyboard acceleration

function _holdTick() {
  const ok = addDelta(_hold.param, _hold.i, _hold.dir * rampStep(_hold.count));
  _hold.count++;
  updateSlotView(_hold.param, _hold.i);
  if (!ok) stopHold();            // hit the floor (clicks can't go below 0)
}

function startHold(param, i, dir) {
  stopHold();
  Object.assign(_hold, { param, i, dir, count: 0 });
  _holdTick();                    // first step is immediate (so a tap = 1 click)
  _hold.timer = setTimeout(() => { _hold.interval = setInterval(_holdTick, 90); }, 350);
}

function stopHold() {
  if (_hold.timer) clearTimeout(_hold.timer);
  if (_hold.interval) clearInterval(_hold.interval);
  const active = _hold.param !== null;
  _hold.timer = _hold.interval = null;
  _hold.param = null;
  if (active) rerender();         // one rebuild to sync tray / delta badges
}

function wireHold(btn, param, i, dir) {
  btn.onpointerdown = (ev) => {
    ev.preventDefault();
    try { btn.setPointerCapture(ev.pointerId); } catch (e) { /* older browsers */ }
    startHold(param, i, dir);
  };
  btn.onpointerup = stopHold;
  btn.onpointercancel = stopHold;
}

// In-place refresh of one slot's value / aria / delta badge during a hold,
// without the full rerender() that would tear down the held button.
function updateSlotView(param, i) {
  const key = slotKey(param, i);
  const el = document.querySelector(`.slot[data-key="${cssEscape(key)}"]`);
  if (!el) return;
  const delta = state.pending[key] || 0;
  const cur = state.base[key] + delta;
  el.classList.toggle("changed", !!delta);
  el.setAttribute("aria-valuenow", String(cur));
  const val = el.querySelector(".val");
  if (val) val.textContent = String(cur);   // phys hint is dropped while changed
  let badge = el.querySelector(".delta");
  if (delta) {
    if (!badge) { badge = document.createElement("div"); badge.className = "delta"; el.appendChild(badge); }
    badge.textContent = (delta > 0 ? "+" : "") + delta;
  } else if (badge) {
    badge.remove();
  }
}

function rerender() {
  renderSetup({ groups: groupsOf(state.params), params: state.params });
  renderTray();
}

// Take the engine's proposed change and pre-fill the editor's +/- with it.
function prepareChange(changes) {
  let applied = 0, missing = 0;
  for (const c of changes) {
    const slot = c.slot == null ? 0 : c.slot;
    if (addDelta(c.param, slot, c.delta_clicks)) applied++;
    else missing++;
  }
  rerender();
  if (applied) {
    $("setup-body").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast(missing ? t("eng.prepared.some") : t("eng.prepared.ok"));
  } else {
    showToast(t("eng.prepared.none"), true);
  }
}

function groupsOf(params) {
  const out = [];
  for (const p of params) if (!out.includes(p.group)) out.push(p.group);
  return out;
}

// ---- pending tray --------------------------------------------------------

function pendingChanges() {
  // -> [{param, slot, slotLabel, label, delta}]
  const out = [];
  for (const p of state.params) {
    p.slots.forEach((s, i) => {
      const d = state.pending[slotKey(p.key, i)];
      if (d) out.push({ param: p.key, slot: i, slotLabel: s.slot,
                        label: p.label, delta: d });
    });
  }
  return out;
}

function renderTray() {
  const changes = pendingChanges();
  const tray = $("tray");
  if (!changes.length) { tray.hidden = true; return; }
  tray.hidden = false;
  $("tray-count").textContent = `(${changes.length})`;
  const list = $("tray-list");
  list.innerHTML = "";
  for (const c of changes) {
    const span = document.createElement("span");
    span.className = "ch";
    const where = c.slotLabel ? ` [${c.slotLabel}]` : "";
    span.innerHTML = `<b>${c.label}${where}</b> ` +
      `<span class="d">${c.delta > 0 ? "+" : ""}${c.delta} ${t("eng.click")}</span>`;
    list.appendChild(span);
  }
}

// ---- write flow (preview -> confirm -> apply) ----------------------------

function changesPayload() {
  return pendingChanges().map((c) => ({
    param: c.param, slot: c.slot, delta_clicks: c.delta }));
}

async function openWriteModal() {
  const changes = changesPayload();
  if (!changes.length) return;
  let res;
  try {
    res = await api("/api/setup/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: state.setupPath, changes }),
    });
  } catch (e) { return showToast(t("eng.previewErr") + e.message, true); }

  const box = $("modal-diff");
  if (!res.ok) {
    box.innerHTML = `<div class="modal-error">${res.errors.join("<br>")}</div>`;
  } else {
    box.innerHTML = "";
    let g = null;
    for (const d of res.diff) {
      if (d.group !== g) {
        const h = document.createElement("div");
        h.className = "g"; h.textContent = d.group; box.appendChild(h); g = d.group;
      }
      const line = document.createElement("div");
      const where = d.slot ? ` [${d.slot}]` : "";
      line.textContent = `${d.label}${where}: ${d.old_click} → ${d.new_click} ` +
        `(${d.delta > 0 ? "+" : ""}${d.delta} click)  ${d.old_phys} → ${d.new_phys}`;
      box.appendChild(line);
    }
  }
  $("modal-name").value = `${state.setupName}_ACCoach`;
  $("modal-error").hidden = true;
  $("modal").hidden = false;
}

async function confirmWrite() {
  const name = $("modal-name").value.trim();
  if (!name) { showModalError(t("eng.enterName")); return; }
  const body = { path: state.setupPath, as_name: name, confirm: true,
                 changes: changesPayload() };
  try {
    const res = await api("/api/setup/apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("modal").hidden = true;
    state.pending = {};
    state.lastWritten = res.name;       // drives the "ricarica ai box" reminder
    // Tell the live backend the proposed setup was written, so the engineer
    // advances its convergence re-test. Best-effort: the backend may be off.
    // Best-effort; .catch handles the async rejection (a sync try/catch wouldn't),
    // so a backend that's off doesn't raise an Uncaught (in promise).
    fetch(`http://${location.hostname}:${WS_PORT}/engineer/applied`,
          { method: "POST" }).catch(() => { /* backend off — keeps proposing */ });
    await onComboChange();              // refresh setup list (new file appears)
    showToast("✓ " + res.reload_hint);
  } catch (e) {
    showModalError(e.message.includes("already exists")
      ? t("eng.exists")
      : t("eng.writeErr") + e.message);
  }
}

function showModalError(msg) {
  const el = $("modal-error"); el.textContent = msg; el.hidden = false;
}

async function undoSetup() {
  if (!state.setupPath) return;
  try {
    await api("/api/setup/undo", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: state.setupPath }),
    });
    await onSetupChange();              // reload the restored values
    showToast(t("eng.restored"));
  } catch (e) {
    showToast(e.message.includes("backup")
      ? t("eng.noBackup")
      : t("eng.restoreErr") + e.message, true);
  }
}

let toastTimer = null;
function showToast(msg, isError) {
  const t = $("toast");
  t.textContent = msg; t.hidden = false;
  t.style.borderColor = isError ? "var(--red)" : "var(--green)";
  t.style.borderLeftColor = isError ? "var(--red)" : "var(--green)";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 6000);
}

// ---- live telemetry (WebSocket) ------------------------------------------

const AID = (v) => (v == null || v < 0 ? "–" : String(v));

// Tyres: optimal windows for generic GT3 slicks (good enough across classes).
const TYRE_IDS = ["tyre-fl", "tyre-fr", "tyre-rl", "tyre-rr"];

function tyreTempClass(t) {
  if (t == null || !isFinite(t)) return "";
  if (t < 80) return "t-cold";          // cold  → cyan
  if (t <= 100) return "t-ok";          // ok    → green
  return "t-hot";                       // hot   → red
}
function tyrePsiClass(p) {
  if (p == null || !isFinite(p)) return "";
  if (p < 26.5) return "p-low";         // low   → amber
  if (p <= 28.5) return "p-ok";         // ok    → green
  return "p-high";                      // high  → amber
}

function updateTyres(tyres) {
  const temps = (tyres && Array.isArray(tyres.temp)) ? tyres.temp : [];
  const press = (tyres && Array.isArray(tyres.pressure)) ? tyres.pressure : [];
  TYRE_IDS.forEach((id, i) => {
    const cell = $(id);
    if (!cell) return;
    const tEl = cell.querySelector(".tt"), pEl = cell.querySelector(".tp");
    const t = temps[i], p = press[i];
    tEl.textContent = (t == null || !isFinite(t)) ? "–" : Math.round(t) + "°";
    pEl.textContent = (p == null || !isFinite(p)) ? "–" : p.toFixed(1);
    tEl.className = "tt " + tyreTempClass(t);
    pEl.className = "tp " + tyrePsiClass(p);
  });
}

function resetTyres() {
  TYRE_IDS.forEach((id) => {
    const cell = $(id);
    if (!cell) return;
    const tEl = cell.querySelector(".tt"), pEl = cell.querySelector(".tp");
    tEl.textContent = "–"; tEl.className = "tt";
    pEl.textContent = "–"; pEl.className = "tp";
  });
}

function applyLive(st) {
  state.lastLive = st;             // remembered so a language switch can re-render
  const badge = $("live-badge");
  if (!st.connected) {
    badge.dataset.state = "off"; $("live-text").textContent = t("live.offline");
    $("live-car").textContent = t("eng.waiting");
    // Don't leave the gauges, proposal, focus and pit reminder frozen with the
    // last live values (you could "Prepare change" on a stale proposal). Reset.
    for (const id of ["g-speed", "g-gear", "g-tc", "g-abs", "g-map"]) {
      $(id).textContent = "–";
    }
    resetTyres();
    renderEngineer({});
    renderFocus({});
    renderPitReminder({});
    return;
  }
  badge.dataset.state = st.in_pit ? "pit" : "on";
  $("live-text").textContent = st.in_pit ? t("live.inpit") : t("live.ontrack");
  $("live-car").textContent = `${st.car || "?"} · ${st.track || "?"}`;
  $("live-car").classList.remove("muted");
  $("g-speed").textContent = Math.round(st.speed_kmh);
  $("g-gear").textContent = st.gear;
  $("g-tc").textContent = AID(st.aids && st.aids.tc);
  $("g-abs").textContent = AID(st.aids && st.aids.abs);
  $("g-map").textContent = AID(st.aids && st.aids.engine_map);
  updateTyres(st.tyres);

  renderEngineer(st);
  renderFocus(st);
  renderPitReminder(st);

  // Auto-pick the matching combo once, if the user hasn't chosen yet.
  maybeAutoSelect(st.car, st.track);
}

// Render the structured engineer block (st.engineer) — proposal + at-the-wheel
// advice. Falls back to the live coach cue until the diagnosis block exists.
function renderEngineer(st) {
  const eng = st.engineer;
  const av = $("av-now");
  if (eng && eng.tag === "AV" && eng.change) {
    av.hidden = false;
    $("av-msg").textContent = eng.rationale || eng.message || "";
  } else {
    av.hidden = true;
  }

  const says = $("engineer-says");
  const conf = $("es-conf"), prep = $("es-prepare");
  const boxProposal = eng && eng.kind === "propose" && eng.tag === "BOX" && eng.change;

  if (boxProposal) {
    $("es-msg").textContent = eng.rationale || eng.message;
    // Anchor the proposal to the corners it's based on — the evidence a driver
    // needs before writing a setup ("Corners 7, 9").
    const cz = Array.isArray(eng.corners) && eng.corners.length
      ? t("eng.corners") + eng.corners.join(", ") : "";
    $("es-cat").textContent = cz;
    conf.hidden = false; conf.textContent = eng.confidence || "medium";
    conf.dataset.c = eng.confidence || "medium";
    prep.hidden = false;
    prep.onclick = () => prepareChange(eng.change);
    says.classList.add("active");
  } else if (eng && eng.message) {
    $("es-msg").textContent = eng.message;      // evaluating / accepted / done…
    $("es-cat").textContent = "";
    conf.hidden = true; prep.hidden = true;
    says.classList.remove("active");
  } else if (st.cue && st.cue.message) {
    $("es-msg").textContent = st.cue.message;   // fallback: live coach cue
    $("es-cat").textContent = st.cue.category || "";
    conf.hidden = true; prep.hidden = true;
    says.classList.add("active");
  } else {
    $("es-msg").textContent = t("eng.dash"); $("es-cat").textContent = "";
    conf.hidden = true; prep.hidden = true;
    says.classList.remove("active");
  }
}

// Render the Focus/Lesson block (st.focus) — the driving coach working one
// weakness at a time. Twin of the engineer box, but about the driver, not the car.
const FOCUS_KIND = {
  assess:   { icon: "…", state: "idle" },
  brief:    { icon: "🎯", state: "warn" },
  drill:    { icon: "🎯", state: "warn" },
  improved: { icon: "✅", state: "good" },
  stuck:    { icon: "⏸", state: "idle" },
  clean:    { icon: "✨", state: "good" },
};

function renderFocus(st) {
  const f = st.focus;
  const box = $("focus-says");
  const drill = $("focus-drill"), target = $("focus-target");
  if (!f) {
    box.dataset.kind = "";
    $("focus-icon").textContent = "…";
    $("focus-msg").textContent = t("focus.warmup");
    drill.hidden = true; target.hidden = true;
    return;
  }
  const meta = FOCUS_KIND[f.kind] || FOCUS_KIND.assess;
  box.dataset.kind = meta.state;
  $("focus-icon").textContent = meta.icon;
  $("focus-msg").textContent = f.message || t("eng.dash");

  if (f.drill) { drill.hidden = false; drill.textContent = f.drill; }
  else { drill.hidden = true; }

  if (f.focus) {
    const t = f.focus;
    const base = t.baseline_ms ? ` · <span class="t-gap">−${(t.baseline_ms / 1000).toFixed(3)}s</span>` : "";
    target.hidden = false;
    target.innerHTML = `<b>${t.name}</b> · ${t.theme}${base}`;
  } else {
    target.hidden = true;
  }
}

function renderPitReminder(st) {
  const el = $("pit-reminder");
  if (state.lastWritten && st.in_pit) {
    el.hidden = false;
    el.innerHTML = t("eng.pit1") + state.lastWritten + t("eng.pit2");
  } else {
    el.hidden = true;
  }
}

function maybeAutoSelect(car, track) {
  if (state.autoSelected || !car) return;
  const sel = $("combo");
  for (const o of sel.options) {
    if (o.dataset.car === car &&
        (o.dataset.track || "").toLowerCase() === (track || "").toLowerCase()) {
      sel.value = o.value; state.autoSelected = true;
      onComboChange();
      return;
    }
  }
}

function connectWS() {
  let ws;
  try { ws = new WebSocket(`ws://${location.hostname}:${WS_PORT}/ws`); }
  catch (e) { setTimeout(connectWS, 3000); return; }
  ws.onmessage = (ev) => { try { applyLive(JSON.parse(ev.data)); } catch (e) {} };
  ws.onclose = () => {
    $("live-badge").dataset.state = "off";
    $("live-text").textContent = "telemetry offline";
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

// ---- wiring --------------------------------------------------------------

$("combo").onchange = () => { state.autoSelected = true; onComboChange(); };
$("setup").onchange = onSetupChange;
$("btn-reset").onclick = () => { state.pending = {};
  renderSetup({ groups: groupsOf(state.params), params: state.params }); renderTray(); };
$("btn-write").onclick = openWriteModal;
$("btn-undo").onclick = undoSetup;
$("modal-cancel").onclick = () => { $("modal").hidden = true; };
$("modal-ok").onclick = confirmWrite;

// ---- guided tour ---------------------------------------------------------
// Coachmarks (vanilla — see tour.js). These panels exist statically in
// engineer.html, so they're visible on load even before telemetry/setup arrive.
// Built lazily so each step's text follows the active language at start time.
function tourSteps() {
  return [
    { sel: "#gauges", title: t("tour.e1.t"), text: t("tour.e1.x") },
    { sel: "#tyres", title: t("tour.e2.t"), text: t("tour.e2.x") },
    { sel: "#engineer-says", title: t("tour.e3.t"), text: t("tour.e3.x") },
    { sel: "#focus-says", title: t("tour.e4.t"), text: t("tour.e4.x") },
    { sel: ".eng-setup", title: t("tour.e5.t"), text: t("tour.e5.x") },
  ];
}

const tourBtn = document.querySelector(".tour-help");
if (tourBtn && window.HoneTour) {
  tourBtn.onclick = () => window.HoneTour.start(tourSteps(), "hone_tour_engineer");
}

// Live language switch: re-render the dynamic, JS-built parts in the new
// language (i18n.js has already re-applied the static chrome).
window.HoneI18nRerender = function () {
  if (state.setupPath) {
    renderSetup({ groups: groupsOf(state.params), params: state.params });
    renderTray();
  } else {
    $("setup-body").innerHTML = noSetupHTML();
  }
  // Re-render the live block from the last payload (or the offline state).
  applyLive(state.lastLive || { connected: false });
};

loadCombos()
  .then(() => { if (window.HoneTour) window.HoneTour.auto(tourSteps(), "hone_tour_engineer"); })
  .catch((e) => showToast(t("eng.loadErr") + e.message, true));
connectWS();
