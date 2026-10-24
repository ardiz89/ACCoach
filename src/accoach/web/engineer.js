"use strict";
// Engineer page: live diagnosis (WebSocket) + setup editor (REST /api/setup/*).
// Vanilla JS, no libraries — same constraint as the analysis app.

// The live backend's port: the server writes the configured one into the page
// (`hone-live-port`), because a port changed in config.toml left this page
// knocking on 8777 and saying the coach was off while it ran.
const WS_PORT = livePort();
function livePort() {
  const m = document.querySelector('meta[name="hone-live-port"]');
  const n = m ? parseInt(m.getAttribute("content"), 10) : NaN;
  return n > 0 && n < 65536 ? n : 8777;
}
// Ogni URL verso il motore passa da qui: sul Wi-Fi porta la chiave (lankey.js).
// Il cookie varrebbe anche sulla 8777 (i cookie non guardano la porta), ma una
// fetch cross-origin senza credenziali non lo manda. Senza lankey.js l'URL
// resta com'e', e sul PC funziona lo stesso.
const liveUrl = (u) => (window.honeLive ? window.honeLive(u) : u);
const $ = (id) => document.getElementById(id);
// A car or track name as a person reads it; the raw id stays in `dataset`.
const dn = (s) => (window.HoneI18n && window.HoneI18n.displayName
                   ? window.HoneI18n.displayName(s) : s);
// i18n: translate a chrome string (defensive if i18n.js failed to load).
const t = (k) => (window.HoneI18n ? window.HoneI18n.t(k) : k);
// …e la stessa con i segnaposto riempiti. Gemella di quella in app.js: le due
// pagine hanno script separati e ognuna si porta il proprio `t`, quindi anche
// questa. Quattro righe duplicate costano meno di un modulo condiviso per due.
const tf = (k, vals) => {
  let s = t(k);
  // `{n|giro|giri}` sceglie la forma col valore di `n`, come il `tf` del report.
  s = s.replace(/\{(\w+)\|([^|{}]*)\|([^{}]*)\}/g,
                (whole, k, one, many) =>
                  (k in vals ? (Number(vals[k]) === 1 ? one : many) : whole));
  for (const n in vals) s = s.split("{" + n + "}").join(vals[n]);
  return s;
};
const LANG = () => (window.HoneI18n ? window.HoneI18n.lang : "en");
// Ogni dato che entra in un template destinato a `innerHTML` passa da qui: i
// nomi e le etichette degli assetti vengono da file che il pilota può aver
// scaricato, i nomi curva li scrive lui, e la revisione di sicurezza del 23/10
// li ha trovati in `innerHTML` senza escape. Gemella di quella in app.js. Con
// `tf` si escapano i valori prima di passarli, non la frase tradotta.
function esc(s) {
  return (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
// Un numero per il pilota: virgola in italiano, spazio prima dell'unita'. La
// regola sta in `HoneI18n.fmtNum`; il ripiego serve solo se i18n.js non c'e'.
function fmtN(v, d, unit) {
  if (window.HoneI18n) return window.HoneI18n.fmtNum(v, d, unit);
  return v.toFixed(d) + (unit ? " " + unit : "");
}

const state = {
  car: null, track: null,
  setupPath: null, setupName: null,
  params: [],                    // from /api/setup/current
  base: {},                      // key "param#slot" -> original click
  pending: {},                   // key "param#slot" -> delta (clicks)
  autoSelected: false,
  lastWritten: null,             // file name written this session (box reminder)
  lastLive: null,                // last live payload, for re-render on lang switch
  // Quale auto/pista crediamo tu stia guidando, e da dove lo sappiamo:
  // "live" (telemetria) batte "archive" (ultimo giro registrato). Serve perché
  // la pagina si apre spesso PRIMA del motore, e senza questo sceglieva la
  // prima voce della tendina — cioè l'assetto di un'altra pista, senza dirlo.
  live: null,                    // {car, track, source}
  missing: null,                 // {car, track} quando quella combo non esiste
};

const slotKey = (param, i) => `${param}#${i}`;
const sameName = (a, b) => (a || "").toLowerCase() === (b || "").toLowerCase();

// Le tre chiamate a `/engineer/applied` sono best-effort: a motore spento si
// tace. Un 401 invece vuol dire che il motore non ha saputo della modifica e
// la riproporra': lo si dice.
function liveRefused(r) {
  if (r && r.status === 401) showToast(t("lan.fromQr"), true);
}

async function api(url, opts) {
  // Pass the active language so backend-generated content arrives localised.
  // The setup routes honour it (labels, groups, notes, the engineer's phases and
  // the reload hint); routes that don't yet just ignore the param.
  if (url.indexOf("/api/") === 0) {
    url += (url.indexOf("?") === -1 ? "?" : "&") + "lang=" + encodeURIComponent(LANG());
  }
  const r = await fetch(url, opts);
  // Un 401 e' il guardiano senza chiave: la sua risposta e' una pagina HTML, e
  // il pilota leggeva «Unauthorized». Gli si dice cosa fare.
  if (r.status === 401) throw new Error(t("lan.fromQr"));
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
    // Il `return` salta `onComboChange()`, quindi saltava anche `noSetupHTML()`
    // — che esiste apposta per questo caso — e restava il testo statico
    // dell'HTML: «Scegli un'auto/pista qui sopra», sotto una tendina che dice
    // «(nessun setup trovato)». Una contraddizione, e proprio al primo avvio:
    // un'installazione ACC nuova ha la cartella dei setup **vuota** finché non
    // ne salvi uno dal gioco.
    $("setup-body").innerHTML = noSetupHTML();
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
      o.textContent = `${dn(c.car)}  ·  ${dn(c.track)}  (${c.count})`;
      o.dataset.car = c.car; o.dataset.track = c.track;
      og.appendChild(o);
    }
    sel.appendChild(og);
  }
  await bootstrapSelection();
}

// ---- chi stai guidando ----------------------------------------------------
//
// Il 2026-08-12 il pilota ha aperto questa pagina girando a Monza con la 720S e
// si è trovato davanti l'assetto di **brands_hatch**, senza un avviso. Non era
// un difetto della preselezione: la cartella `<auto>/monza` non esisteva
// proprio, perché ACC la crea solo quando salvi un assetto da lì, e la tendina
// si costruisce dalle cartelle che contengono file. Non c'era niente da
// selezionare, e la pagina è rimasta sulla prima voce in ordine alfabetico.
//
// Da qui in poi la pagina risponde a due domande separate, e non le confonde
// più: *cosa stai guidando* (telemetria, oppure l'ultimo giro in archivio) e
// *ho un assetto per quello* (le cartelle su disco). Quando la seconda dice no,
// lo dice — non ripiega su un'altra pista.

function findComboOption(car, track) {
  for (const o of $("combo").options) {
    if (sameName(o.dataset.car, car) && sameName(o.dataset.track, track)) return o;
  }
  return null;
}

async function selectCombo(car, track) {
  const o = findComboOption(car, track);
  if (!o) return false;
  dropMissingOption();
  $("combo").value = o.value;
  state.missing = null;
  await onComboChange();
  return true;
}

// La voce fantasma per l'auto/pista che stai guidando e che non ha assetti.
// Non è selezionabile come le altre (non ha `dataset.car`), quindi sceglierla
// da tastiera non apre niente: esiste solo perché l'intestazione dica la
// stessa cosa del pannello.
const MISSING_ID = "combo-missing";

function dropMissingOption() {
  const old = document.getElementById(MISSING_ID);
  if (old) old.remove();
}

function showComboAsMissing(car, track) {
  const sel = $("combo");
  dropMissingOption();
  const o = document.createElement("option");
  o.id = MISSING_ID;
  o.textContent = `${car}  ·  ${track}  (${t("eng.miss.optNone")})`;
  sel.insertBefore(o, sel.firstChild);
  sel.value = o.value;
}

// L'ultimo giro registrato, per quando la telemetria è spenta. `/api/combos` è
// già ordinato per giro più recente, quindi la prima riga è l'ultima uscita.
async function lastDrivenCombo() {
  try {
    const rows = await api("/api/combos");
    return rows.length ? { car: rows[0].car, track: rows[0].track } : null;
  } catch (e) {
    return null;                   // niente archivio: si ripiega sotto
  }
}

async function bootstrapSelection() {
  const last = await lastDrivenCombo();
  if (!last) {
    await onComboChange();         // nessun giro in archivio: com'era prima
    return;
  }
  state.live = { car: last.car, track: last.track, source: "archive" };
  if (!await selectCombo(last.car, last.track)) showMissingCombo(last.car, last.track);
}

// ---- la pista che non ha assetti -----------------------------------------

async function showMissingCombo(car, track) {
  state.missing = { car, track };
  // La tendina va portata d'accordo col pannello. Lasciandola sull'ultima voce
  // scelta, l'intestazione diceva `brands_hatch` mentre sotto c'era scritto
  // «stai guidando monza»: cioè la stessa contraddizione di prima, ridotta a
  // due righe che si smentiscono a mezzo schermo di distanza. Visto a schermo,
  // non nei test — nessuna asserzione guarda cosa dice la `<select>`.
  showComboAsMissing(car, track);
  // L'editor non deve restare aperto su un file che non c'entra: mostrarlo
  // sarebbe di nuovo il difetto, con sopra un cartello.
  state.setupPath = null; state.setupName = null;
  state.params = []; state.pending = {}; state.base = {};
  $("btn-undo").disabled = true;
  renderTray();
  $("setup-car").textContent = "";
  $("setup").innerHTML = "";
  renderMissing();
  let sources = [];
  try {
    sources = await api(`/api/setup/elsewhere?car=${encodeURIComponent(car)}` +
                        `&track=${encodeURIComponent(track)}`);
  } catch (e) { /* niente sorgenti: resta il testo "salvane uno tu" */ }
  if (state.missing && sameName(state.missing.car, car)) renderMissing(sources);
}

function renderMissing(sources) {
  if (!state.missing) return;
  const { car, track } = state.missing;
  const body = $("setup-body");
  body.innerHTML = "";
  const box = document.createElement("div");
  box.className = "miss";

  const h = document.createElement("div");
  h.className = "miss-title";
  h.textContent = t("eng.miss.title");
  box.appendChild(h);

  // I nomi vengono dal gioco e dal disco: vanno messi come testo, non come
  // markup, e in grande — è l'unica riga che risponde a "sto guardando la
  // macchina giusta?", che è la domanda con cui questa pagina si apre.
  const who = document.createElement("div");
  who.className = "miss-who";
  // «Stai guidando <auto · pista> (ultimo giro registrato)»: una frase sola,
  // senza i due punti dopo l'etichetta, e la fonte in coda.
  const lbl = document.createElement("span");
  lbl.className = "muted";
  lbl.textContent = t("eng.miss.driving") + " ";
  who.appendChild(lbl);
  const strong = document.createElement("b");
  strong.textContent = `${car} · ${track}`;
  who.appendChild(strong);
  if (state.live && state.live.source === "archive") {
    const from = document.createElement("span");
    from.className = "muted";
    from.textContent = ` (${t("eng.fromArchive")})`;
    who.appendChild(from);
  }
  box.appendChild(who);

  const why = document.createElement("p");
  why.className = "miss-why";
  why.textContent = t("eng.miss.why");
  box.appendChild(why);

  if (sources === undefined) {
    body.appendChild(box);
    return;                        // le sorgenti stanno ancora arrivando
  }

  if (!sources.length) {
    const none = document.createElement("p");
    none.className = "miss-why";
    none.textContent = t("eng.miss.none");
    box.appendChild(none);
  } else {
    const head = document.createElement("div");
    head.className = "miss-seed-head";
    head.textContent = t("eng.miss.seedHead");
    box.appendChild(head);

    const list = document.createElement("div");
    list.className = "miss-seeds";
    sources.forEach((s, i) => {
      const row = document.createElement("label");
      row.className = "miss-seed";
      const radio = document.createElement("input");
      radio.type = "radio"; radio.name = "miss-seed"; radio.value = s.path;
      if (i === 0) radio.checked = true;
      row.appendChild(radio);
      const txt = document.createElement("span");
      txt.textContent = `${dn(s.track)} · ${s.name}`;
      row.appendChild(txt);
      list.appendChild(row);
    });
    box.appendChild(list);

    const seedBtn = document.createElement("button");
    seedBtn.type = "button"; seedBtn.className = "primary small";
    seedBtn.textContent = t("eng.miss.seedBtn");
    seedBtn.onclick = () => {
      const picked = box.querySelector("input[name=miss-seed]:checked");
      if (picked) seedFrom(picked.value, track);
    };
    box.appendChild(seedBtn);

    // Detto PRIMA di premere, non dopo: un assetto di un'altra pista messo qui
    // è un punto di partenza, e chiamarlo proposta sarebbe una bugia comoda.
    const caveat = document.createElement("p");
    caveat.className = "miss-caveat";
    caveat.innerHTML = t("eng.miss.caveat");
    box.appendChild(caveat);
  }

  const again = document.createElement("button");
  again.type = "button"; again.className = "ghost small miss-reload";
  again.textContent = t("eng.miss.reload");
  again.onclick = () => loadCombos().catch((e) => showToast(e.message, true));
  box.appendChild(again);

  body.appendChild(box);
}

async function seedFrom(sourcePath, track) {
  let res;
  try {
    res = await api("/api/setup/seed", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: sourcePath, track }),
    });
  } catch (e) { return showToast(t("eng.miss.seedErr") + e.message, true); }
  state.missing = null;
  await loadCombos();
  await selectCombo(res.car, res.track);
  showToast(tf("eng.miss.seeded", { from: `${res.from_track} · ${res.from_name}` }));
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

// ``prefer`` è il nome del file su cui restare dopo aver ricostruito la lista.
// Senza, dopo una scrittura la pagina tornava sulla PRIMA voce in ordine
// alfabetico: scriveva HONE_2, diceva «carica HONE_2» e apriva HONE_1. La
// modifica successiva sarebbe partita dal file sbagliato, buttando via quella
// appena fatta. Visto a schermo alla seconda scrittura di fila — la prima non
// poteva mostrarlo, perché HONE_1 *era* la prima voce.
async function onComboChange(prefer) {
  const opt = $("combo").selectedOptions[0];
  if (!opt || !opt.dataset.car) return;
  state.missing = null;            // si sta aprendo una combo che esiste
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
    if (prefer && s.name === prefer) sel.value = o.value;
  }
  await onSetupChange();
  loadRecord();                 // best-effort: il registro non blocca la pagina
}

// ---- il registro: quante modifiche hanno davvero funzionato ---------------
//
// L'unico numero di questa pagina che non è una nostra affermazione: è contato
// su prove che il pilota ha guidato, e può darci torto. Restava su disco, dietro
// un endpoint che nessuno chiamava.

// Sotto questa soglia si mostrano solo i conteggi. Un tasso di riuscita su tre
// campioni è rumore travestito da percentuale — lo dice il modulo che lo calcola.
const REC_MIN_TESTS = 8;

async function loadRecord() {
  const box = $("eng-record");
  let r;
  try {
    r = await api(`/api/setup/record?car=${encodeURIComponent(state.car)}` +
                  `&track=${encodeURIComponent(state.track)}`);
  } catch (e) { box.hidden = true; return; }
  box.hidden = false;
  if (!r.tests) {
    $("rec-head").textContent = "";
    $("rec-note").textContent = t("rec.none");
    $("rec-tables").innerHTML = "";
    return;
  }
  let head = tf("rec.counts", { kept: r.kept, tests: r.tests });
  if (r.tests >= REC_MIN_TESTS && r.hit_rate != null) {
    head += tf("rec.rate", { rate: Math.round(r.hit_rate * 100) });
  }
  if (r.median_gain_ms != null) {
    // Col segno: «−0,120 s» e' piu' veloce, «+0,080 s» piu' lento.
    const g = r.median_gain_ms / 1000;
    head += tf("rec.gain", { gain: (g > 0 ? "+" : "") + fmtN(g, 3, "s") });
  }
  $("rec-head").innerHTML = head;
  $("rec-note").textContent = r.tests < REC_MIN_TESTS ? t("rec.thin") : "";

  const rows = (title, entries) => {
    if (!entries.length) return "";
    const li = entries.map(([k, v]) =>
      `<div class="rec-row"><span>${esc(k)}</span><span>${v}</span></div>`).join("");
    return `<div class="rec-block"><div class="rec-sub">${esc(title)}</div>${li}</div>`;
  };
  // Il nome della leva come nell'editor; la chiave solo se il server non lo sa.
  const name = (k) => (r.labels && r.labels[k]) || k;
  const kept = (o) => Object.entries(o).map(
    ([k, v]) => [name(k), tf("rec.kept_of", { kept: v.kept, tests: v.tests })]);
  $("rec-tables").innerHTML =
    rows(t("rec.byparam"), kept(r.by_param || {})) +
    rows(t("rec.byrank"), Object.entries(r.by_rank || {}).map(
      ([n, v]) => [tf("rec.rank", { n: Number(n) + 1 }),
                   tf("rec.kept_of", { kept: v.kept, tests: v.tests })])) +
    rows(t("rec.side"), (r.side_effects || []).map(
      (s) => [`${s.label || s.param} → ${s.words || s.symptom}`,
              tf("rec.seen", { n: s.seen })]));
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
  if (!opt || !opt.dataset.path) {
    $("setup-body").innerHTML = noSetupHTML();
    $("btn-undo").disabled = true;
    return;
  }
  state.setupPath = opt.dataset.path;
  const data = await api(`/api/setup/current?path=${encodeURIComponent(state.setupPath)}`);
  // Acceso solo con un backup da cui ripristinare.
  $("btn-undo").disabled = !data.has_backup;
  state.setupName = data.name;
  state.params = data.params;
  state.pending = {};
  state.base = {};
  for (const p of data.params) {
    p.slots.forEach((s, i) => { state.base[slotKey(p.key, i)] = s.click; });
  }
  $("setup-car").textContent = `· ${dn(data.car)} · ${data.name}`;
  renderSetup(data);
  renderTray();
}

// ---- rendering -----------------------------------------------------------

function renderSetup(data) {
  const body = $("setup-body");
  body.innerHTML = "";
  for (const g of data.groups) {
    const params = data.params.filter((x) => x.group === g);
    const wrap = document.createElement("div");
    // A group with per-wheel rows needs the whole width (label + four steppers
    // measures ~1000px); one with single-value levers needs a third of that.
    // Marking it here lets the CSS pack the narrow groups side by side instead
    // of running all eight of them down one column — measured before this
    // existed: 16 of 29 rows ended at 1189px of a 2560px screen, and the page
    // still scrolled for 2020px.
    const wide = params.some((p) => (p.slots || []).length > 2);
    wrap.className = "grp" + (wide ? " wide" : "");
    const title = document.createElement("div");
    title.className = "grp-title"; title.textContent = g;
    wrap.appendChild(title);
    for (const p of params) wrap.appendChild(renderParam(p));
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
  // Per-wheel rows take the full width of their group; single-value levers sit
  // two or three abreast (see .grp.wide in engineer.css).
  row.className = "param" + ((p.slots || []).length > 2 ? " wide" : "");
  const label = document.createElement("div");
  label.className = "param-label";
  label.innerHTML = `${esc(p.label)}${p.note ? `<span class="note">${esc(p.note)}</span>` : ""}`;
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
  const suggested = state.suggested && state.suggested.has(key);
  el.className = "slot" + (delta ? " changed" : "") + (suggested ? " suggested" : "");
  el.dataset.key = key;          // lets refocusSlot find this node after rerender

  // The slot itself is the keyboard control (a spinbutton): one tab stop, the
  // -/+ buttons are mouse affordances kept out of the tab order (see below).
  el.tabIndex = 0;
  el.setAttribute("role", "spinbutton");
  el.setAttribute("aria-valuenow", String(cur));
  el.setAttribute("aria-label", `${p.label}${s.slot ? ` ${s.slot}` : ""}: ${cur}`);
  el.onkeydown = (ev) => onSlotKey(ev, p.key, i);

  const minus = document.createElement("button");
  minus.type = "button"; minus.tabIndex = -1;
  minus.textContent = "−"; minus.title = "−1 click. " + t("eng.stepHint");
  minus.setAttribute("aria-hidden", "true");
  wireHold(minus, p.key, i, -1);

  const val = document.createElement("div");
  val.className = "val";
  const physTxt = delta ? "" : `<span class="phys">${esc(s.physical)}</span>`;
  val.innerHTML = `${cur}${physTxt}`;

  const plus = document.createElement("button");
  plus.type = "button"; plus.tabIndex = -1;
  plus.textContent = "+"; plus.title = "+1 click. " + t("eng.stepHint");
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
    // Sugli schermi stretti l'editor sta nell'altra scheda: ci si va, se no la
    // modifica si prepara dove non la vedi.
    setTab("setup");
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
  // Il numero sulla scheda Setup: dalla diagnosi il vassoio non si vede.
  const badge = $("tab-count");
  badge.hidden = !changes.length;
  badge.textContent = String(changes.length);
  if (!changes.length) { tray.hidden = true; return; }
  tray.hidden = false;
  paintWriteLock();
  $("tray-count").textContent = `(${changes.length})`;
  const list = $("tray-list");
  list.innerHTML = "";
  for (const c of changes) {
    const span = document.createElement("span");
    span.className = "ch";
    const slotHTML = c.slotLabel ? ` [${esc(c.slotLabel)}]` : "";
    span.innerHTML = `<b>${esc(c.label)}${slotHTML}</b> ` +
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
    box.innerHTML = `<div class="modal-error">${res.errors.map(esc).join("<br>")}</div>`;
  } else {
    box.innerHTML = "";
    let g = null;
    for (const d of res.diff) {
      if (d.group !== g) {
        const h = document.createElement("div");
        h.className = "g"; h.textContent = d.group; box.appendChild(h); g = d.group;
      }
      const line = document.createElement("div");
      line.textContent = `${d.label}${d.slot ? ` [${d.slot}]` : ""} · ` +
        `${d.old_click} → ${d.new_click} ` +
        `(${d.delta > 0 ? "+" : ""}${d.delta} click) · ${d.old_phys} → ${d.new_phys}`;
      box.appendChild(line);
    }
  }
  $("modal-name").value = `${state.setupName}_ACCoach`;
  $("modal-error").hidden = true;
  $("modal").hidden = false;
}

// ---- la via corta: un tasto, un nome che non devi pensare ----------------
//
// Nel box il pilota ha il motore acceso e i secondi contati, e la via lunga gli
// chiedeva di digitare un nome file — che poi la seconda volta era già preso e
// glielo faceva rifare. Qui il nome è progressivo (HONE_1, HONE_2, …) e lo
// sceglie la pagina. La via lunga resta accanto, per quando vuoi vedere il
// diff in psi e millimetri prima di scrivere.

const AUTO_PREFIX = "HONE";

function nextAutoName() {
  let max = 0;
  for (const o of $("setup").options) {
    const m = /^HONE_(\d+)$/i.exec(o.textContent.trim());
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return `${AUTO_PREFIX}_${max + 1}`;
}

// Si scrive l'assetto solo da fermo ai box. Scrivere avvisa il motore
// (`/engineer/applied`) e da li' l'ingegnere conta i giri di verifica: in pista
// il file nuovo non e' ancora sulla macchina (si carica dal garage), quei giri
// sarebbero guidati con l'assetto vecchio e il verdetto «la tengo / la rimetto»
// sarebbe sbagliato. La vista tablet lo sapeva gia' (tablet.js, `atBoxNow`).
//
// Ma la pagina serve anche senza guidare, per preparare un assetto col gioco
// spento o nei menu: li' scrivere resta possibile. Si blocca solo se l'ultimo
// frame dice «stai guidando e non sei fermo ai box». PAUSE conta come guida: in
// pausa ACC sei fermo in pista, non ai box, e l'assetto non si carica lo stesso.
// REPLAY e OFF no: non c'e' una macchina in pista a cui mancherebbe il file.
function inPista(st) {
  return !!st && st.connected === true
    && (st.status === "LIVE" || st.status === "PAUSE") && !st.at_box;
}
function writeLocked() { return inPista(state.lastLive); }

// Spegne i quattro bottoni che scrivono e dice perche'. Chiamata a ogni frame e
// quando il vassoio o il riquadro dell'ingegnere si ridisegnano.
function paintWriteLock() {
  const lock = writeLocked();
  for (const id of ["btn-apply", "btn-write", "modal-ok", "es-restored"]) {
    const el = $(id);
    if (el) el.disabled = lock;
  }
  const line = $("write-lock");
  if (line) {
    line.hidden = !lock;
    line.textContent = lock ? t("tablet.writeAtBox") : "";
  }
  // Il vassoio non c'e' quando la modifica e' un ripristino: la riga la porta
  // anche il bottone «L'ho già rimesso», che altrimenti sarebbe spento a vuoto.
  const rl = $("restored-lock");
  if (rl) {
    const on = lock && !$("es-restored").hidden;
    rl.hidden = !on;
    rl.textContent = on ? t("tablet.writeAtBox") : "";
  }
}

async function applyNow() {
  // Seconda guardia: il bottone e' spento, ma un frame puo' arrivare fra il
  // tocco e qui.
  if (writeLocked()) return;
  const changes = changesPayload();
  if (!changes.length || !state.setupPath) return;
  // La tendina è la nostra unica idea di quali nomi sono presi; un file scritto
  // in un'altra scheda non c'è. Un 409 quindi non è un errore da mostrare: è il
  // disco che sa il numero meglio di noi, e si prova il successivo.
  let name = nextAutoName();
  let tried = name;
  for (let attempt = 0; attempt < 4; attempt++) {
    tried = name;
    try {
      const res = await api("/api/setup/apply", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: state.setupPath, as_name: name,
                               confirm: true, changes }),
      });
      await afterWrite(res);
      return;
    } catch (e) {
      if (!e.message.includes("already exists")) {
        return showToast(t("eng.writeErr") + e.message, true);
      }
      name = `${AUTO_PREFIX}_${parseInt(name.split("_").pop(), 10) + 1}`;
    }
  }
  showToast(tf("eng.writeErrName", { name: tried }), true);
}

// Quello che succede dopo una scrittura riuscita, per tutt'e due le vie. Vive
// in un posto solo di proposito: la via corta che dimentica di avvisare il
// motore lascerebbe l'ingegnere a riproporre la stessa modifica per sempre.
async function afterWrite(res) {
  state.pending = {};
  state.lastWritten = res.name;         // drives the "ricarica ai box" reminder
  // Tell the live backend the proposed setup was written, so the engineer
  // advances its convergence re-test. Best-effort: the backend may be off.
  // .catch handles the async rejection (a sync try/catch wouldn't), so a
  // backend that's off doesn't raise an Uncaught (in promise).
  // JSON anche senza niente da dire: il guardiano rifiuta (415) ogni
  // scrittura che non lo dichiara.
  fetch(liveUrl(`http://${location.hostname}:${WS_PORT}/engineer/applied`),
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
    .then(liveRefused)
    .catch(() => { /* backend off — keeps proposing */ });
  // Il file appena scritto è quello che il messaggio ti dice di caricare, ed è
  // quello su cui deve poggiare la modifica dopo.
  await onComboChange(res.name);
  showToast(res.reload_hint);
}

async function confirmWrite() {
  if (writeLocked()) { showModalError(t("tablet.writeAtBox")); return; }
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
    await afterWrite(res);
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
    // Zero non e' una misura (vedi `tyreVal` in tablet.js): «–» come il vuoto.
    const ok = (v) => v != null && isFinite(v) && v > 0;
    const t = ok(temps[i]) ? temps[i] : null, p = ok(press[i]) ? press[i] : null;
    tEl.textContent = t == null ? "–" : fmtN(Math.round(t), 0, "°C");
    pEl.textContent = p == null ? "–" : fmtN(p, 1);
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
    traceReset();
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
    paintWriteLock();
    return;
  }
  badge.dataset.state = st.at_box ? "pit" : "on";
  $("live-text").textContent = st.at_box ? t("live.inpit") : t("live.ontrack");
  $("live-car").textContent = `${dn(st.car) || "?"} · ${dn(st.track) || "?"}`;
  $("live-car").classList.remove("muted");
  $("g-speed").textContent = Math.round(st.speed_kmh);
  $("g-gear").textContent = st.gear;
  $("g-tc").textContent = AID(st.aids && st.aids.tc);
  $("g-abs").textContent = AID(st.aids && st.aids.abs);
  $("g-map").textContent = AID(st.aids && st.aids.engine_map);
  updateTyres(st.tyres);
  tracePush(st);

  renderEngineer(st);
  renderFocus(st);
  renderPitReminder(st);
  paintWriteLock();               // dopo renderEngineer: conta se `es-restored` e' visibile
  updateSuggested(st.engineer);   // highlight the proposed levers in the editor

  // Auto-pick the matching combo once, if the user hasn't chosen yet.
  maybeAutoSelect(st.car, st.track);
}

// ---- pedals and steering trace -------------------------------------------
// Gli ultimi secondi di gas, freno e sterzo, che scorrono verso sinistra. Lo
// sterzo e' centrato (dritto a meta', sinistra in alto, come nel Confronto del
// report) e la sua scala e' il volante piu' girato visto nella sessione, mai
// sotto TRACE_STEER_FLOOR: sui giri veri la GT3 sta fra 0.33 e 0.9 e la Formula
// arriva a 1.0. Cresce e basta, cosi' la linea non cambia scala a ogni curva.
// Gemella della striscia dell'overlay (overlay.py, _draw_pedals).

const TRACE_WINDOW_MS = 8000;
const TRACE_STEER_FLOOR = 0.3;
const trace = { hist: [], steerScale: TRACE_STEER_FLOOR };

function traceReset() {
  trace.hist = [];
  trace.steerScale = TRACE_STEER_FLOOR;
  for (const id of ["tr-thr", "tr-brk", "tr-steer"]) $(id).textContent = "–";
  traceDraw();
}

function tracePush(st) {
  const thr = Number(st.throttle), brk = Number(st.brake);
  if (st.throttle == null || st.brake == null || !isFinite(thr) || !isFinite(brk)) return;
  const steer = isFinite(Number(st.steer)) ? Number(st.steer) : 0;
  const now = performance.now();
  trace.hist.push([now, thr, brk, steer]);
  trace.steerScale = Math.max(trace.steerScale, Math.abs(steer));
  const cutoff = now - TRACE_WINDOW_MS;
  let drop = 0;
  while (drop < trace.hist.length && trace.hist[drop][0] < cutoff) drop++;
  if (drop) trace.hist.splice(0, drop);
  const pct = (f) => fmtN(Math.round(f * 100), 0, "%");
  $("tr-thr").textContent = pct(thr);
  $("tr-brk").textContent = pct(brk);
  // Positivo a sinistra (serialize.py). Quasi dritto: solo il numero.
  const v = pct(Math.abs(steer));
  $("tr-steer").textContent = steer > 0.02 ? tf("trace.steerLeft", { v })
                            : steer < -0.02 ? tf("trace.steerRight", { v }) : v;
  traceDraw(now);
}

function traceDraw(now) {
  const cv = $("trace-canvas");
  // Nascosto (l'altra scheda): niente da disegnare, la storia intanto si
  // aggiorna e al ritorno si vede tutta.
  if (!cv || !cv.offsetWidth) return;
  const dpr = window.devicePixelRatio || 1;
  const w = cv.offsetWidth, h = cv.offsetHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const col = (n, d) => (css.getPropertyValue(n).trim() || d);
  const pad = 4, ph = h - 2 * pad;
  const y = (v) => pad + ph * (1 - Math.max(0, Math.min(1, v)));
  // griglia 0 / 50 / 100 %; la riga di mezzo e' anche lo sterzo dritto
  ctx.strokeStyle = col("--line", "#232B35");
  ctx.lineWidth = 1;
  for (const f of [0, 0.5, 1]) {
    const gy = Math.round(y(f)) + 0.5;
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
  }
  const hist = trace.hist;
  if (hist.length < 2) return;
  const t1 = now == null ? performance.now() : now;
  const x = (t0) => w * (1 - (t1 - t0) / TRACE_WINDOW_MS);
  const k = 0.5 / trace.steerScale;
  const draw = (pick, colour, width) => {
    ctx.strokeStyle = colour; ctx.lineWidth = width;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.beginPath();
    hist.forEach((s, i) => {
      const px = x(s[0]), py = y(pick(s));
      if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    });
    ctx.stroke();
  };
  // lo sterzo per primo, cosi' i pedali gli restano sopra
  draw((s) => 0.5 + s[3] * k, col("--text", "#E8EDF2"), 1.5);
  draw((s) => s[2], col("--red", "#FF4D5E"), 2);
  draw((s) => s[1], col("--green", "#34E08A"), 2);
}

// ---- tabs (narrow screens) -------------------------------------------------
// Sotto i 1440 px diagnosi e assetto sono due schede (engineer.css); sopra sono
// affiancate e questa logica non cambia niente di visibile. Si apre sempre
// sulla telemetria: e' quella che serve in pista, l'assetto si apre ai box.

function setTab(name) {
  document.documentElement.dataset.tab = name;
  for (const b of document.querySelectorAll(".eng-tab")) {
    b.setAttribute("aria-selected", String(b.dataset.tab === name));
  }
  if (name === "live") traceDraw();
}

const narrow = window.matchMedia("(max-width: 1439px)");

for (const b of document.querySelectorAll(".eng-tab")) {
  b.onclick = () => setTab(b.dataset.tab);
}

// Lo scorrimento col dito. Dito verso sinistra = la scheda a destra (Setup),
// verso destra = la telemetria. Deve essere netto e soprattutto orizzontale,
// se no e' uno scorrimento della pagina. Non parte dai comandi dell'editor:
// i bottoni +/- si tengono premuti e un dito che scivola li' non vuole
// cambiare scheda.
(function wireSwipe() {
  const area = $("eng-layout");
  let start = null;
  area.addEventListener("touchstart", (ev) => {
    start = null;
    if (!narrow.matches || ev.touches.length !== 1) return;
    if (ev.target.closest(".slot, button, input, select, textarea")) return;
    const p = ev.touches[0];
    start = { x: p.clientX, y: p.clientY };
  }, { passive: true });
  area.addEventListener("touchend", (ev) => {
    if (!start) return;
    const p = ev.changedTouches[0];
    const dx = p.clientX - start.x, dy = p.clientY - start.y;
    start = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < 1.5 * Math.abs(dy)) return;
    setTab(dx < 0 ? "setup" : "live");
  }, { passive: true });
  area.addEventListener("touchcancel", () => { start = null; }, { passive: true });
})();

window.addEventListener("resize", () => traceDraw());

// Highlight, in cyan, the slots the engineer is currently proposing to change —
// distinct from the amber "you changed it" state. Updated in place (the live
// feed ticks ~15 Hz, so a full rerender would churn and fight an open edit) and
// only when the proposed set actually changes.
function updateSuggested(eng) {
  const next = new Set();
  if (eng && eng.change && (eng.tag === "BOX" || eng.tag === "AV")) {
    for (const c of eng.change) next.add(slotKey(c.param, c.slot == null ? 0 : c.slot));
  }
  const prev = state.suggested || new Set();
  if (next.size === prev.size && [...next].every((k) => prev.has(k))) return;
  state.suggested = next;
  document.querySelectorAll(".slot").forEach((el) => {
    el.classList.toggle("suggested", next.has(el.dataset.key));
  });
}

// La strada dell'ingegnere: le tappe e la frase del passo, da
// `engineer.progress` (lo calcola il motore). Gemella di `stripText` in
// tablet.js, che resta ES5 per Safari 9: stesse chiavi, stesse regole, e un
// test confronta le due caso per caso (tests/test_engineer_strip.py). Senza un
// `progress` che si legge, null: la striscia si nasconde. `changeTag` e' il
// `tag` della modifica in attesa (`engineer.tag`), non quello della fase: una
// fase «dal volante» propone anche leve da box, e il ricontrollo delle
// pressioni propone ai box in qualunque fase. `kind` e' quello dell'ultima
// decisione (`engineer.kind`).
function stripText(p, changeTag, kind) {
  if (!p || typeof p !== "object" || !Array.isArray(p.phases) || !p.phases.length) return null;
  const idx = Number(p.index), done = p.stage === "done";
  // Le fasi che il motore ha passato senza chiuderle (cieche, o senza niente da
  // correggere): dietro di noi, ma senza la spunta di una fase fatta.
  const skipped = Array.isArray(p.skipped) ? p.skipped : [];
  const steps = p.phases.map((ph, i) => ({
    label: String((ph && (ph.label || ph.key)) || ""),
    // Finito, nessuna tappa resta accesa: l'indice e' oltre l'ultima.
    state: (done || i < idx) ? (skipped.includes(i) ? "skipped" : "done")
                             : (i === idx ? "now" : "next"),
  }));
  // Il contatore solo dove il motore conta giri verso una soglia; senza i suoi
  // numeri la frase non se ne inventa uno.
  const isNum = (v) => v != null && v !== "" && isFinite(Number(v));
  const counted = isNum(p.have) && isNum(p.need);
  let line = "", why = "";
  if (kind === "stand_down") {
    // Il motore si e' tirato indietro (bagnato, fase cieca, leva che non sa
    // scrivere): «giri puliti per la base» o «decido a fine giro» qui sarebbero
    // falsi. Il perche' lo dice il suo messaggio.
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
  return { steps, line, why };
}

// Il messaggio del motore quando non c'e' una modifica in mano. Su raccolta e
// prova la strada dice gia' i giri contati: del messaggio resta solo la coda
// (`engineer.tail`: perche' l'ultimo giro non conta, il sospetto sulle
// uscite), se no lo stesso numero si leggeva due volte con due frasi. Senza
// `tail` il messaggio si legge intero. Gemella di `msgText` in tablet.js.
function msgText(eng) {
  if (!eng || !eng.message) return "";
  const p = eng.progress;
  const isNum = (v) => v != null && v !== "" && isFinite(Number(v));
  const counted = !!(p && (p.stage === "baseline" || p.stage === "test")
                     && isNum(p.have) && isNum(p.need));
  if (counted && eng.kind !== "stand_down" && typeof eng.tail === "string") {
    return eng.tail.trim();
  }
  return String(eng.message);
}

// La striscia si riscrive solo quando cambia: il frame arriva molte volte al
// secondo e quasi sempre dice la stessa cosa.
let roadKey = null;
function renderRoad(eng) {
  const s = stripText(eng && eng.progress, eng && eng.tag, eng && eng.kind);
  const key = s ? JSON.stringify(s) : "";
  if (key === roadKey) return;
  roadKey = key;
  const box = $("es-road");
  if (!box) return;
  if (!s) { box.hidden = true; return; }
  const ol = $("es-road-steps");
  ol.innerHTML = "";
  for (const st of s.steps) {
    const li = document.createElement("li");
    li.className = "es-road-step " + st.state;
    const name = document.createElement("span");
    name.className = "es-road-name";
    name.textContent = st.label;
    li.appendChild(name);
    ol.appendChild(li);
  }
  $("es-road-line").textContent = s.line;
  $("es-road-why").textContent = s.why;
  $("es-road-why").hidden = !s.why;
  box.hidden = false;
}

// Render the structured engineer block (st.engineer) — proposal + at-the-wheel
// advice. Falls back to the live coach cue until the diagnosis block exists.
function renderEngineer(st) {
  const eng = st.engineer;
  const av = $("av-now");
  if (eng && eng.tag === "AV" && eng.change) {
    av.hidden = false;
    $("av-msg").textContent = eng.rationale || eng.message || "";
    // The button is the fallback, not the route. Where the game publishes the
    // dial (ACC) the engine sees it move and closes the loop by itself, and
    // asking a driver to click something at 250 km/h would be the wrong answer.
    // Where it doesn't (AC: every aid level reads -1) this is the only way an
    // "al volo" change can ever be marked applied — without it the engineer
    // re-proposes the same click every lap and the phase never closes.
    $("av-done").hidden = !!eng.watched || !!eng.applied;
  } else {
    av.hidden = true;
  }

  const says = $("engineer-says");
  const conf = $("es-conf"), prep = $("es-prepare"), hint = $("es-hint");
  const boxProposal = eng && eng.kind === "propose" && eng.tag === "BOX" && eng.change;
  // Una modifica bocciata è lavoro da fare ai box quanto una proposta: i click
  // per rimetterla com'era stanno in `eng.change`, e il motore continua a
  // mandarli finché non gli si dice che è fatto (`applied`). Fino al 13/10 qui
  // contava solo `propose`: il pilota leggeva «ripristino» e non aveva un
  // bottone per farlo.
  const boxRestore = eng && eng.kind === "reverted" && eng.tag === "BOX"
    && eng.change && !eng.applied;
  // Chi ripristina ricaricando in gioco il file di prima non scrive niente da
  // qui, e allora nessuno avvisa il motore — che adesso aspetta davvero.
  const done = $("es-restored");
  done.hidden = !boxRestore;
  done.onclick = boxRestore ? confirmRestored : null;

  renderRoad(eng);

  // Persistent "what to do in this phase" line: the decision message alone
  // ("phase done → moving to X") never says what the driver should now do.
  const phaseEl = $("es-phase");
  if (eng && eng.phase && eng.phase.key) {
    const k = "eng.do." + eng.phase.key;
    let txt = t(k);
    if (txt === k) txt = t("eng.do.default");   // t() falls back to the key if missing
    phaseEl.hidden = false;
    // `txt` è una frase nostra (i18n); l'etichetta della fase arriva dal server
    // e si escapa lo stesso: «fidata» oggi è una promessa su un altro file.
    phaseEl.innerHTML = `<b>${tf("eng.phaseNow", { label: esc(eng.phase.label) })}</b> ${txt}`;
  } else {
    phaseEl.hidden = true;
  }

  // Default: no low-confidence caution; the proposal branch re-arms it.
  hint.hidden = true;
  says.removeAttribute("data-conf");
  renderPrediction(eng);
  renderOutcome(eng);

  if (boxProposal) {
    $("es-msg").textContent = eng.rationale || eng.message;
    // Anchor the proposal to the corners it's based on — the evidence a driver
    // needs before writing a setup ("Corners 7, 9").
    const cz = Array.isArray(eng.corners) && eng.corners.length
      ? t("eng.corners") + eng.corners.join(", ") : "";
    $("es-cat").textContent = cz;
    const confidence = eng.confidence || "medium";
    // La parola del motore («medium») resta nel dataset per il colore; a
    // schermo va quella della pagina.
    conf.hidden = false; conf.textContent = t("eng.conf." + confidence);
    conf.dataset.c = confidence;
    // Low confidence: warn the driver not to over-trust it (few laps / weak
    // signal) and flag the whole box, so a tentative call gets a second look
    // before they write the setup.
    says.dataset.conf = confidence;
    if (confidence === "low") { hint.hidden = false; hint.textContent = t("eng.lowConf"); }
    prep.hidden = false;
    prep.onclick = () => prepareChange(eng.change);
    says.classList.add("active");
  } else if (boxRestore) {
    // Il perché (il verdetto) e il cosa (la riga del ripristino). Niente grado
    // di fiducia: un ripristino non è una stima.
    $("es-msg").textContent = eng.message || eng.rationale || "";
    $("es-cat").textContent = eng.rationale || "";
    conf.hidden = true;
    prep.hidden = false;
    prep.onclick = () => prepareChange(eng.change);
    says.classList.add("active");
  } else if (eng && eng.message) {
    $("es-msg").textContent = msgText(eng);     // evaluating / accepted / done…
    $("es-cat").textContent = "";
    conf.hidden = true; prep.hidden = true;
    says.classList.remove("active");
  } else if (st.cue && st.cue.message) {
    $("es-msg").textContent = st.cue.message;   // fallback: live coach cue
    $("es-cat").textContent = st.cue.category || "";
    conf.hidden = true; prep.hidden = true;
    says.classList.add("active");
  } else {
    // Un trattino è un silenzio che non dice perché tace, dentro un riquadro
    // intitolato «Il tecnico suggerisce». Nei primi giri l'ingegnere non ha
    // ancora una base, e appena il primo giro si chiude la strada lo dice
    // («Giri puliti per la base, 1 di 3»): mancava solo prima.
    $("es-msg").textContent = st.connected ? t("eng.warmup") : t("eng.dash");
    $("es-cat").textContent = "";
    conf.hidden = true; prep.hidden = true;
    says.classList.remove("active");
  }
}

// «L'ho già rimesso com'era.» Stesso endpoint della scrittura dell'assetto e di
// `av-done`, perché è lo stesso evento: quello che l'ingegnere aveva chiesto è
// sulla macchina. Best-effort come gli altri due.
function confirmRestored() {
  if (writeLocked()) return;
  $("es-restored").hidden = true;
  fetch(liveUrl(`http://${location.hostname}:${WS_PORT}/engineer/applied`),
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
    .then(liveRefused)
    .catch(() => { /* backend off — resta da fare */ });
}

// The acceptance bar, shown while the change is still a proposal and while it
// is being re-tested. It is the engine's own rule said out loud (see
// engineer/core.py `Prediction`): not a second test, but the difference between
// being judged and being able to check the judge.
function renderPrediction(eng) {
  const el = $("es-predict");
  if (!el) return;
  const p = eng && eng.prediction;
  const show = p && p.text && (eng.kind === "propose" || eng.kind === "evaluating");
  el.hidden = !show;
  el.textContent = show ? p.text : "";
}

// The verdict, with the numbers on both sides — and the symptoms that moved
// while nobody was looking at them. Those are measured, never predicted.
function renderOutcome(eng) {
  const el = $("es-outcome");
  if (!el) return;
  const o = eng && eng.outcome;
  if (!o) { el.hidden = true; el.innerHTML = ""; return; }
  const dt = (o.time_after_ms - o.time_before_ms) / 1000;
  const bits = [
    `<span class="oc-verdict" data-kept="${o.kept}">` +
    `${o.kept ? t("eng.oc.kept") : t("eng.oc.reverted")}</span>`,
    `<span class="oc-num">${tf("eng.oc.laps", { n: o.laps })}</span>`,
    `<span class="oc-num">${dt >= 0 ? "+" : ""}${fmtN(dt, 2, "s")}</span>`,
  ];
  if (o.score_before || o.score_after) {
    bits.splice(1, 0, `<span class="oc-num">${fmtN(o.score_before, 2)}` +
      ` → ${fmtN(o.score_after, 2)}</span>`);
  }
  let side = "";
  if (Array.isArray(o.side_effects) && o.side_effects.length) {
    side = `<div class="oc-side"><span class="oc-side-label">${t("eng.oc.side")}</span> · ` +
      o.side_effects.map((s) =>
        `${esc(s.words || s.symptom)} ${s.delta >= 0 ? "+" : ""}${fmtN(s.delta, 2)}`).join(" · ") +
      `</div>`;
  }
  el.innerHTML = bits.join("") + side;
  el.hidden = false;
}

// Render the Focus/Lesson block (st.focus) — the driving coach working one
// weakness at a time. Twin of the engineer box, but about the driver, not the car.
// Lo stato si legge dal colore del riquadro (`data-kind`), non da un'emoji:
// le icone 🎯 ✅ ⏸ ✨ sono uscite col tono nuovo, resta solo l'attesa.
const FOCUS_KIND = {
  assess:   { icon: "…", state: "idle" },
  brief:    { icon: "", state: "warn" },
  drill:    { icon: "", state: "warn" },
  improved: { icon: "", state: "good" },
  stuck:    { icon: "", state: "idle" },
  clean:    { icon: "", state: "good" },
};

function renderFocus(st) {
  const f = st.focus;
  const box = $("focus-says");
  const drill = $("focus-drill"), target = $("focus-target");
  if (!f) {
    box.dataset.kind = "";
    $("focus-icon").textContent = "…";
    $("focus-icon").hidden = false;
    $("focus-msg").textContent = t("focus.warmup");
    drill.hidden = true; target.hidden = true;
    return;
  }
  const meta = FOCUS_KIND[f.kind] || FOCUS_KIND.assess;
  box.dataset.kind = meta.state;
  // Un'icona vuota non lascia lo spazio davanti al titolo.
  $("focus-icon").textContent = meta.icon;
  $("focus-icon").hidden = !meta.icon;
  $("focus-msg").textContent = f.message || t("eng.dash");

  if (f.drill) { drill.hidden = false; drill.textContent = f.drill; }
  else { drill.hidden = true; }

  if (f.focus) {
    // `fc` e non `t`: col nome della traduzione addosso, un `t(...)` scritto
    // qui un giorno chiamerebbe l'oggetto.
    const fc = f.focus;
    const base = fc.baseline_ms ? ` · <span class="t-gap">−${fmtN(fc.baseline_ms / 1000, 3, "s")}</span>` : "";
    target.hidden = false;
    target.innerHTML = `<b>${esc(fc.name)}</b> · ${esc(fc.theme)}${base}`;
  } else {
    target.hidden = true;
  }
}

function renderPitReminder(st) {
  const el = $("pit-reminder");
  if (!st.at_box) { el.hidden = true; return; }
  // Stopped in the box with a garage change still unwritten. The voice has just
  // sent the driver to this page (coaching/pitcall.py); the page has to say what
  // to do here, or the trip in was for nothing. Checked BEFORE the "go load it"
  // reminder because a proposal that arrived after the last write is the newer
  // instruction — `applied` is what tells the two apart (the engineer re-emits
  // the same proposal until the next completed lap, so its mere presence
  // doesn't).
  const e = st.engineer;
  if (e && e.change && e.tag === "BOX" && !e.applied) {
    el.hidden = false;
    el.innerHTML = t("eng.pitTodo");
    return;
  }
  if (state.lastWritten) {
    el.hidden = false;
    el.innerHTML = tf("eng.pit", { name: esc(state.lastWritten) });
    return;
  }
  el.hidden = true;
}

// La telemetria batte l'archivio: quando arriva un frame, è LEI a dire cosa
// stai guidando. Chiamata a ogni frame, quindi deve costare niente quando non
// c'è nulla da fare — la guardia sotto è quella.
//
// Il confronto sull'auto era esatto sulle maiuscole mentre quello sulla pista
// no. In archivio il gioco scrive `Zolder` e `Imola` maiuscoli accanto a
// `monza` minuscolo: oggi le due grafie coincidono, ma è la stessa famiglia di
// difetto — due metà che decidono la stessa cosa con due regole.
function maybeAutoSelect(car, track) {
  if (state.autoSelected || !car) return;
  const cur = state.live;
  if (cur && cur.source === "live"
      && sameName(cur.car, car) && sameName(cur.track, track)) return;
  state.live = { car, track, source: "live" };
  selectCombo(car, track).then((ok) => { if (!ok) showMissingCombo(car, track); });
}

function onWsClose() {
  $("live-badge").dataset.state = "off";
  // Tradotto come tutto il resto: era l'unica scritta inglese su una pagina
  // in italiano, e stava proprio sul distintivo che il pilota guarda per
  // capire se il coach è acceso.
  // Rifiutato al giro prima: si ridice il QR, non si fa lampeggiare «offline»
  // ogni 3 s in attesa della risposta di `probeKey`.
  $("live-text").textContent = offlineText();
  // Senza motore non c'e' un ultimo frame da fidarsi: se restasse quello «in
  // pista», i bottoni resterebbero spenti per sempre proprio col gioco chiuso,
  // il caso in cui scrivere un assetto deve restare possibile.
  state.lastLive = { connected: false };
  paintWriteLock();
  probeKey();
  setTimeout(connectWS, 3000);
}

// Un WebSocket rifiutato dal guardiano si chiude come un motore spento, e il
// perche' non lo dice: lo si chiede alla 8777 con una fetch. Un 401 e' la
// chiave che manca, e il distintivo dice del QR invece di «offline».
let keyRefused = false;
let noKey = false;   // 503: il PC non ha potuto salvare la chiave
function offlineText() {
  return t(keyRefused ? "lan.fromQr" : noKey ? "lan.noKey" : "live.offline");
}
function probeKey() {
  fetch(liveUrl(`http://${location.hostname}:${WS_PORT}/health`))
    .then((r) => {
      keyRefused = !!(r && r.status === 401);
      noKey = !!(r && r.status === 503);
      if (state.lastLive && !state.lastLive.connected) {
        $("live-text").textContent = offlineText();
      }
    })
    .catch(() => {
      // motore spento: «offline»
      keyRefused = false;
      noKey = false;
      if (state.lastLive && !state.lastLive.connected) $("live-text").textContent = t("live.offline");
    });
}

function connectWS() {
  let ws;
  try { ws = new WebSocket(liveUrl(`ws://${location.hostname}:${WS_PORT}/ws`)); }
  catch (e) { setTimeout(connectWS, 3000); return; }
  ws.onmessage = (ev) => { try { applyLive(JSON.parse(ev.data)); } catch (e) {} };
  ws.onclose = onWsClose;
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

// ---- wiring --------------------------------------------------------------

$("combo").onchange = () => {
  state.autoSelected = true;
  // La voce fantasma ("… — nessun assetto") non apre un editor, perché non c'è
  // niente da aprire: rimette il pannello che spiega perché.
  if ($("combo").selectedOptions[0] === document.getElementById(MISSING_ID)) {
    const m = state.missing || state.live;
    if (m) showMissingCombo(m.car, m.track);
    return;
  }
  onComboChange();
};
$("setup").onchange = onSetupChange;
// "I've turned the dial." Same endpoint the setup writer calls, because it is
// the same event: the change the engineer proposed is now on the car, so the
// re-test window can start. Best-effort like the other one — a backend that
// isn't running just means the engineer keeps proposing.
// Niente guardia: la modifica «dal volante» si fa guidando, ed e' giusto che
// avvisi subito.
function confirmAvDone() {
  $("av-done").hidden = true;
  // JSON anche senza niente da dire: il guardiano rifiuta (415) ogni
  // scrittura che non lo dichiara.
  fetch(liveUrl(`http://${location.hostname}:${WS_PORT}/engineer/applied`),
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
    .then(liveRefused)
    .catch(() => { /* backend off — keeps proposing */ });
}
$("av-done").onclick = confirmAvDone;

$("btn-reset").onclick = () => { state.pending = {};
  renderSetup({ groups: groupsOf(state.params), params: state.params }); renderTray(); };
$("btn-write").onclick = openWriteModal;
$("btn-apply").onclick = applyNow;
$("btn-undo").onclick = undoSetup;
$("modal-cancel").onclick = () => { $("modal").hidden = true; };
$("modal-ok").onclick = confirmWrite;

// ---- guided tour ---------------------------------------------------------
// Coachmarks (vanilla — see tour.js). These panels exist statically in
// engineer.html, so they're visible on load even before telemetry/setup arrive.
// Built lazily so each step's text follows the active language at start time.
// Sugli schermi stretti diagnosi e assetto sono due schede, e il giro guidato
// salta i passi la cui scheda non si vede: il `before` porta sulla scheda
// giusta (sopra i 1440 px non cambia niente di visibile). Non su #av-now, che
// spesso non c'e' proprio: col `before` il giro si chiuderebbe li'.
function tourSteps() {
  const live = () => setTab("live"), setup = () => setTab("setup");
  return [
    { sel: "#gauges", title: t("tour.e1.t"), text: t("tour.e1.x"), before: live },
    { sel: "#tyres", title: t("tour.e2.t"), text: t("tour.e2.x"), before: live },
    // Only appears when there IS an "al volo" proposal — the tour engine skips
    // hidden targets, so it costs nothing on the sessions without one.
    { sel: "#av-now", title: t("tour.e6.t"), text: t("tour.e6.x") },
    { sel: "#engineer-says", title: t("tour.e3.t"), text: t("tour.e3.x"), before: live },
    { sel: "#focus-says", title: t("tour.e4.t"), text: t("tour.e4.x"), before: live },
    { sel: ".eng-setup", title: t("tour.e5.t"), text: t("tour.e5.x"), before: setup },
  ];
}

const tourBtn = document.querySelector(".tour-help");
if (tourBtn && window.HoneTour) {
  tourBtn.onclick = () => window.HoneTour.start(tourSteps(), "hone_tour_engineer");
}

// Live language switch: re-render the dynamic, JS-built parts in the new
// language (i18n.js has already re-applied the static chrome).
window.HoneI18nRerender = async function () {
  if (state.missing) {
    // Il pannello "questa pista non ha assetti" è testo nostro, quindi va
    // ridisegnato: senza, cambiare lingua lasciava in piedi la pagina
    // precedente proprio dove si spiega cosa fare.
    showMissingCombo(state.missing.car, state.missing.track);
    if (state.car) await loadClass(state.car);
    applyLive(state.lastLive || { connected: false });
    return;
  }
  if (state.setupPath) {
    // The editor's text (group, label, note, slot) is rendered by the backend in
    // the requested language, so a switch has to RE-FETCH it — repainting
    // state.params would just draw the previous language again.
    //
    // Deliberately not onSetupChange(): that resets state.pending, and dropping
    // someone's unapplied clicks because they changed language would be a nasty
    // surprise. Only the text differs here — the click values are identical — so
    // pending edits and their baseline carry over untouched.
    try {
      const data = await api(
        `/api/setup/current?path=${encodeURIComponent(state.setupPath)}`);
      state.params = data.params;
    } catch (e) {
      // Backend unreachable: keep the labels we have. Stale language beats a
      // blank editor with the user's edits still in it.
    }
    renderSetup({ groups: groupsOf(state.params), params: state.params });
    renderTray();
  } else {
    $("setup-body").innerHTML = noSetupHTML();
  }
  // The engineer profile (phases, al-volo levers) is backend text too.
  if (state.car) await loadClass(state.car);
  // Re-render the live block from the last payload (or the offline state).
  applyLive(state.lastLive || { connected: false });
};

loadCombos()
  .then(() => { if (window.HoneTour) window.HoneTour.auto(tourSteps(), "hone_tour_engineer"); })
  .catch((e) => showToast(t("eng.loadErr") + e.message, true));
connectWS();
