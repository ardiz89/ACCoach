"use strict";
// Engineer page: live diagnosis (WebSocket) + setup editor (REST /api/setup/*).
// Vanilla JS, no libraries — same constraint as the analysis app.

const WS_PORT = 8777;            // the live backend; the page itself is on 8778
const $ = (id) => document.getElementById(id);

const state = {
  car: null, track: null,
  setupPath: null, setupName: null,
  params: [],                    // from /api/setup/current
  base: {},                      // key "param#slot" -> original click
  pending: {},                   // key "param#slot" -> delta (clicks)
  autoSelected: false,
  lastWritten: null,             // file name written this session (box reminder)
};

const slotKey = (param, i) => `${param}#${i}`;

async function api(url, opts) {
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
    sel.innerHTML = '<option value="">(nessun setup trovato)</option>';
    return;
  }
  // Group the (potentially many) cars by engineer class for a usable dropdown.
  const groups = { GT3: [], Formula: [], Stradale: [] };
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
  return "Stradale";
}

async function onComboChange() {
  const opt = $("combo").selectedOptions[0];
  if (!opt || !opt.dataset.car) return;
  state.car = opt.dataset.car; state.track = opt.dataset.track;
  loadClass(state.car);
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
  $("prof-name").textContent = `Ingegnere ${info.profile.name}`;
  $("prof-phases").textContent = info.profile.phases.join(" → ");
  $("prof-alvolo").textContent = info.profile.al_volo.join(", ");
  $("eng-profile").hidden = false;
}

async function onSetupChange() {
  const opt = $("setup").selectedOptions[0];
  if (!opt || !opt.dataset.path) { $("setup-body").innerHTML =
    '<div class="empty2">Nessun setup.</div>'; return; }
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

function renderParam(p) {
  const row = document.createElement("div");
  row.className = "param";
  const label = document.createElement("div");
  label.className = "param-label";
  label.innerHTML = `${p.label}${p.note ? `<span class="note">${p.note}</span>` : ""}`;
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

  const minus = document.createElement("button");
  minus.textContent = "−"; minus.title = "−1 click";
  minus.onclick = () => bump(p.key, i, -1);

  const val = document.createElement("div");
  val.className = "val";
  const physTxt = delta ? "" : `<span class="phys">${s.physical}</span>`;
  val.innerHTML = `${cur}${physTxt}`;

  const plus = document.createElement("button");
  plus.textContent = "+"; plus.title = "+1 click";
  plus.onclick = () => bump(p.key, i, +1);

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
    showToast(missing
      ? "Modifica preparata (alcuni parametri non sono in questo setup)."
      : "Modifica preparata nell'editor — controlla e premi “Scrivi setup”.");
  } else {
    showToast("Il parametro proposto non è in questo setup.", true);
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
      `<span class="d">${c.delta > 0 ? "+" : ""}${c.delta} click</span>`;
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
  } catch (e) { return showToast("Errore anteprima: " + e.message, true); }

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
  if (!name) { showModalError("Inserisci un nome file."); return; }
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
    try {
      fetch(`http://${location.hostname}:${WS_PORT}/engineer/applied`,
            { method: "POST" });
    } catch (e) { /* backend not running — diagnosis just keeps proposing */ }
    await onComboChange();              // refresh setup list (new file appears)
    showToast("✓ " + res.reload_hint);
  } catch (e) {
    showModalError(e.message.includes("esiste già")
      ? "Esiste già un setup con questo nome — scegline un altro."
      : "Errore scrittura: " + e.message);
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
    showToast("✓ Setup ripristinato dall'ultimo backup");
  } catch (e) {
    showToast(e.message.includes("backup")
      ? "Nessun backup da ripristinare per questo setup."
      : "Errore ripristino: " + e.message, true);
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

function applyLive(st) {
  const badge = $("live-badge");
  if (!st.connected) {
    badge.dataset.state = "off"; $("live-text").textContent = "telemetria offline";
    $("live-car").textContent = "In attesa della telemetria…";
    return;
  }
  badge.dataset.state = st.in_pit ? "pit" : "on";
  $("live-text").textContent = st.in_pit ? "ai box" : "in pista";
  $("live-car").textContent = `${st.car || "?"} · ${st.track || "?"}`;
  $("live-car").classList.remove("muted");
  $("g-speed").textContent = Math.round(st.speed_kmh);
  $("g-gear").textContent = st.gear;
  $("g-tc").textContent = AID(st.aids && st.aids.tc);
  $("g-abs").textContent = AID(st.aids && st.aids.abs);
  $("g-map").textContent = AID(st.aids && st.aids.engine_map);

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
    $("es-cat").textContent = "";
    conf.hidden = false; conf.textContent = eng.confidence || "media";
    conf.dataset.c = eng.confidence || "media";
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
    $("es-msg").textContent = "—"; $("es-cat").textContent = "";
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
    $("focus-msg").textContent = "Scaldando… guida qualche giro pulito.";
    drill.hidden = true; target.hidden = true;
    return;
  }
  const meta = FOCUS_KIND[f.kind] || FOCUS_KIND.assess;
  box.dataset.kind = meta.state;
  $("focus-icon").textContent = meta.icon;
  $("focus-msg").textContent = f.message || "—";

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
    el.innerHTML = `🅿️ Sei ai box: MFD → <b>Setup</b> → carica ` +
      `<b>${state.lastWritten}</b> → esci dai box per applicarlo.`;
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
    $("live-text").textContent = "telemetria offline";
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

loadCombos().catch((e) => showToast("Errore caricamento setup: " + e.message, true));
connectWS();
