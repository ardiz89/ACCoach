"""I rimandi: il consiglio in corso nel frontend, la riga e il segno.

Statici sul markup e sul sorgente, piu' un harness node (come
`test_web_pagella.py`) che esegue le funzioni vere di app.js: la regola che
decide se una curva e' del consiglio non si legge, si prova.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"
_HTML = (WEB / "index.html").read_text(encoding="utf-8")
_APPJS = (WEB / "app.js").read_text(encoding="utf-8")
_I18NJS = (WEB / "i18n.js").read_text(encoding="utf-8")
_CSS = (WEB / "style.css").read_text(encoding="utf-8")

VIEWS = ["compare", "line", "sectors", "dynamics", "progress"]

# I testi esatti della tabella del piano (Task 2).
TEXTS = {
    "adv.compare.brake_early": (
        "On the brake chart, look at where your trace starts compared with the reference. The braking sheet has your braking point lap by lap.",
        "Nel grafico del freno guarda dove parte la tua traccia rispetto al riferimento. La scheda frenate ha il punto di stacco giro per giro."),
    "adv.compare.brake_late": (
        "Read the brake and speed charts together. A later braking point that lowers your minimum speed doesn't pay off.",
        "Guarda freno e velocità insieme. Una staccata più tarda che abbassa la velocità minima non paga."),
    "adv.compare.over_brake": (
        "Compare how high your brake trace goes, and how long it stays there, with the reference.",
        "Guarda quanto in alto arriva la tua traccia del freno e quanto ci resta, rispetto al riferimento."),
    "adv.compare.throttle_late": (
        "On the throttle chart, look at when you get back on the power on the way out, compared with the reference.",
        "Nel grafico del gas guarda quando torni a spingere in uscita, rispetto al riferimento."),
    "adv.compare.min_speed": (
        "Look at the lowest point of the speed trace. The minimum speed table gives it in numbers.",
        "Guarda il punto più basso della velocità. La tabella delle velocità minime lo dà in numeri."),
    "adv.compare.lift": (
        "The straight-line notes in the debrief show where you lift and what it costs you.",
        "Le note sul dritto nel debrief dicono dove alzi il gas e quanto ti costa."),
    "adv.line.brake_early": (
        "The brake marker shows where you start braking and where the reference does.",
        "Il segno del freno mostra dove stacchi tu e dove stacca il riferimento."),
    "adv.line.brake_late": (
        "Compare the braking point with the line through mid-corner. If you brake late and run wide, the line shows it.",
        "Confronta il punto di stacco con la linea a centro curva. Se stacchi tardi e allarghi, la linea lo mostra."),
    "adv.line.throttle_late": (
        "The throttle marker shows where you get back on the power, you and the reference.",
        "Il segno del gas mostra dove torni a spingere, tu e il riferimento."),
    "adv.line.min_speed": (
        "Look at where your minimum speed falls and how tight your line is compared with the reference.",
        "Guarda dove cade la velocità minima e quanto è stretta la tua linea rispetto al riferimento."),
    "adv.sectors.one": (
        "It's in sector {n}. That sector's time tells you whether the work on the corner reaches your lap time.",
        "È nel settore {n}. Il tempo di quel settore ti dice se il lavoro sulla curva arriva al giro."),
    "adv.sectors.same": (
        "They're in sector {n}. That sector's time tells you whether the work on these corners reaches your lap time.",
        "Sono nel settore {n}. Il tempo di quel settore ti dice se il lavoro su queste curve arriva al giro."),
    "adv.sectors.many": (
        "They're in sectors {list}. Those sectors' times tell you whether the work on these corners reaches your lap time.",
        "Sono nei settori {list}. I tempi di quei settori ti dicono se il lavoro su queste curve arriva al giro."),
    "adv.dynamics.coasting": (
        "The coasting box shows how long you spend off both pedals.",
        "Il riquadro del veleggio dice quanto tempo passi senza gas né freno."),
    "adv.dynamics.over_brake": (
        "Look at wheel slip under braking. A spike the reference doesn't have is too much brake.",
        "Guarda lo slittamento delle ruote in frenata. Un picco che il riferimento non ha è freno di troppo."),
    "adv.dynamics.throttle_late": (
        "On the way out, look at rear wheel slip. If it stays low, you have room to get on the throttle earlier.",
        "In uscita guarda lo slittamento delle ruote posteriori. Se resta basso, hai margine per tornare prima sul gas."),
    "adv.progress.corners": (
        "In the fault history, the marked row is your advice. Further down, the cards for these corners show how it goes session by session.",
        "Nello storico dei difetti la riga segnata è il tuo consiglio. Più sotto, le schede di queste curve dicono come va sessione per sessione."),
    "adv.progress.lap": (
        "In the fault history, the marked row is the advice you're following, session by session.",
        "Nello storico dei difetti la riga segnata è il consiglio che segui, sessione per sessione."),
    "adv.goto": ("Show me", "Vai al punto"),
    "adv.mark.title": ("Corner in the advice you're following",
                       "Curva del consiglio che segui"),
}


def _entry(key):
    m = re.search(rf'"{re.escape(key)}"\s*:\s*\{{\s*en:\s*`([^`]*)`,\s*it:\s*`([^`]*)`\s*\}}',
                  _I18NJS)
    assert m, f"{key} non e' nel catalogo con inglese e italiano"
    return m.group(1), m.group(2)


def _body_of(head: str) -> str:
    assert head in _APPJS, f"manca {head!r} in app.js"
    return _APPJS.split(head, 1)[1].split("\n}", 1)[0]


# --- il markup --------------------------------------------------------------

@pytest.mark.parametrize("view", VIEWS)
def test_each_view_opens_with_its_hidden_advice_line(view):
    m = re.search(rf'<div id="view-{view}"[^>]*>\s*(<\w+[^>]*>)', _HTML)
    assert m, view
    first = m.group(1)
    assert f'id="adv-line-{view}"' in first, f"{view}: la riga non e' il primo figlio"
    assert "hidden" in re.findall(r"[\w-]+", first), first


def test_the_line_takes_no_space_when_hidden():
    # `.hidden` e' `display:none` a specificita' di una classe: una `.adv-line`
    # con un suo `display` scritta dopo la riaccenderebbe, vuota, sopra ogni vista.
    rules = re.findall(r"(?m)^\.adv-line\s*\{([^}]*)\}", _CSS)
    assert rules, ".adv-line non ha stile"
    assert not any("display" in r for r in rules)
    assert "--adv:" in _CSS


# --- i testi ----------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(TEXTS))
def test_the_texts_are_the_table_word_for_word(key):
    assert _entry(key) == TEXTS[key]


def test_no_emoji_no_slogan_colon_and_no_repeated_sentence():
    seen = {}
    for key in TEXTS:
        for lang, text in zip(("en", "it"), _entry(key)):
            assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", text), (key, text)
            assert not re.search(r"^[^:]{1,30}:\s", text), (key, text)
            assert (lang, text) not in seen, (key, seen.get((lang, text)))
            seen[(lang, text)] = key


# --- il sorgente ------------------------------------------------------------

def test_loadAdvice_runs_on_combo_change_and_after_every_plan_action():
    assert "loadAdvice(" in _body_of("async function loadCombo(")
    assert "loadAdvice(" in _body_of("async function adviceAction(")


def test_loadAdvice_checks_stale_before_it_assigns():
    body = _body_of("async function loadAdvice(")
    assert "stale(" in body
    assert body.index("stale(") < body.index("ADVICE = ")


def test_the_scroll_waits_for_the_figures_and_reads_their_span():
    load = _body_of("async function loadHowto(")
    # dopo il disegno delle figure, non subito dopo renderHowto
    assert "scrollHowtoToApex(" in load
    assert load.index("scrollHowtoToApex(") > load.index("drawHowtoFigures(")
    assert "scrollHowtoToApex(" not in load.split("renderHowto(h);")[1].split("drawHowtoFigures(")[0]
    scroll = _body_of("function scrollHowtoToApex(")
    assert "data-entry" in scroll and "scrollIntoView" in scroll
    assert scroll.index("HOWTO_APEX = null") > scroll.index("= HOWTO_APEX")
    assert 'data-entry="' in _body_of("function renderHowto(") or "data-entry" in _APPJS
    assert "function openHowto(defect, apex)" in _APPJS


def test_two_advice_requests_in_one_epoch_cannot_land_out_of_order():
    body = _body_of("async function loadAdvice(")
    assert "const req = ++ADV_REQ;" in body
    assert re.search(r"if \(stale\(seen\) \|\| req !== ADV_REQ\) return;", body)
    assert body.index("req !== ADV_REQ") < body.index("ADVICE = ")


# --- le funzioni vere, eseguite in node -------------------------------------

_NODE = shutil.which("node")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(head) {
  const i = src.indexOf(head);
  if (i < 0) throw new Error("manca " + head);
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
function grabConst(head) {
  const i = src.indexOf(head);
  if (i < 0) throw new Error("manca " + head);
  return src.slice(i, src.indexOf("\n};", i) + 3);
}
const CAT = JSON.parse(process.env.CAT);
const t = (k) => CAT[k] || k;
function tf(key, vals) {
  let s = t(key);
  for (const k in vals) s = s.split("{" + k + "}").join(vals[k]);
  return s;
}
const escAttr = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;");
let ADVICE = null;
const els = {};
const $ = (id) => els[id] || null;
function fakeEl() {
  const el = { _html: "", nodes: {}, cls: new Set(["hidden"]), classList: {
    add: (c) => el.cls.add(c), remove: (c) => el.cls.delete(c),
    contains: (c) => el.cls.has(c) } };
  Object.defineProperty(el, "innerHTML", { configurable: true, get: () => el._html, set: (v) => {
    el._html = v; el.nodes = {}; } });
  el.querySelectorAll = (sel) => {
    const attr = sel.match(/\[([\w-]+)\]/)[1];
    if (!el.nodes[attr]) {
      const re = new RegExp("<button[^>]*" + attr + '(?:="([^"]*)")?', "g");
      el.nodes[attr] = [...el._html.matchAll(re)].map((m) => ({
        dataset: { advI: m[1] }, onclick: null }));
    }
    return el.nodes[attr];
  };
  el.querySelector = (sel) => el.querySelectorAll(sel)[0] || null;
  return el;
}
eval(grabConst("const ADVICE_VIEWS").replace("const ", "var "));
eval(grab("function adviceApexIn("));
eval(grab("function adviceRelevant("));
eval(grab("function advMarkHTML("));
eval(grab("function adviceLineModel("));
eval(grab("function renderAdviceLine("));
eval(grab("function howtoFigIndex("));
eval(grab("function cornerOfIndex("));
eval(grab("function adviceLiftWithoutNote("));
let ADV_ROW = null;
eval(grab("function brakeRowOpen("));
eval(grab("function fmtSec("));
const lapClock = () => "";
eval(grab("function drawSectorTable("));
eval(grab("function drawSectors("));
function gotoAdviceSector() {}
eval(grab("function adviceCornersInSector("));
eval(grab("function adviceSectorsModel("));
eval(grab("function sectorMarkHTML("));
eval(grab("function lineChipHTML("));
eval(grab("function lineNameHTML("));
eval(grab("function cornerWindow("));
eval(grab("function gotoAdviceLine("));
let LINE = null, LINE_I = 0;
const CALLS = [];
function setRange(r) { CALLS.push(["range", r]); }
function redrawCurrentView() { CALLS.push(["redraw"]); }
const OPENED = [];
function openHowto(d, a) { OPENED.push([d, a]); }
// Task 5: Dinamica e Andamento. Tolleranti: se una funzione manca fallisce il
// test che la usa, non tutta la suite.
function tryGrab(head) { try { return grab(head); } catch (e) { if (!/^manca/.test(e.message)) throw e; return ""; } }
const SCROLLS = [];
const DOC = { exist: [], asked: [] };
const document = {
  querySelectorAll: () => [],
  querySelector: (sel) => {
    DOC.asked.push(sel);
    if (!DOC.exist.includes(sel)) return null;
    return { classList: { add() {}, remove() {} }, scrollIntoView: () => SCROLLS.push(sel) };
  },
  body: {},
};
const getComputedStyle = () => ({ getPropertyValue: () => "#C792EA" });
const UI_FONT = "sans";
const _anyNonZero = (a) => (a || []).some((v) => v !== 0);
const projX = (p, w) => p * w;
eval(grab("function degradeLabel("));
eval(grab("function drawAdvMark("));
eval(grab("function cornerBands("));
eval(tryGrab("function dynamicsAdviceHidden("));
eval(tryGrab("function gotoAdviceDynamics("));
eval(tryGrab("function progressAdviceCorners("));
eval(tryGrab("function gotoAdviceProgress("));
eval(tryGrab("function renderCornerSessions("));
eval(tryGrab("function renderCornerConsistency("));
eval(tryGrab("function renderDefectHistory("));
const fmtSecs = (v) => String(v), sparkBars = () => "", dhDates = () => "", fmtWhen = () => "";
const LANG = () => "en", DH_H = 44;
const job = JSON.parse(fs.readFileSync(0, "utf8"));
const out = [];
for (const step of job) {
  if ("advice" in step) ADVICE = step.advice;
  if ("adv_row" in step) ADV_ROW = step.adv_row;
  if (step.call === "apex") out.push(adviceApexIn(step.arg));
  else if (step.call === "relevant") out.push(adviceRelevant(step.arg));
  else if (step.call === "figidx") out.push(howtoFigIndex(step.figs, step.apex));
  else if (step.call === "brakerows") {
    out.push(step.rows.map((r) => {
      const adv = adviceApexIn(r);
      return brakeRowOpen(adv);
    }));
  }
  else if (step.call === "analysismark") {
    out.push(step.indices.map((i) => adviceApexIn(cornerOfIndex(step.a, i)) !== null));
  }
  else if (step.call === "sectable") {
    for (const id of ["sec-kind", "sectors", "ideal", "sec-table"]) els[id] = fakeEl();
    els["adv-line-sectors"] = fakeEl();
    drawSectors(step.s);
    const cnt = (h) => (h.match(/adv-mark/g) || []).length;
    out.push({ bars: cnt(els["sectors"].innerHTML), table: cnt(els["sec-table"].innerHTML),
               line: els["adv-line-sectors"].cls.has("hidden") ? 0 : 1 });
  }
  else if (step.call === "stale") {
    const el = els["adv-line-" + step.view] = fakeEl();
    const seen = [];
    renderAdviceLine(step.view, step.corners, (c) => seen.push(["old", c]), step.opts);
    renderAdviceLine(step.view, JSON.parse(JSON.stringify(step.corners)),
                     (c) => seen.push(["new", c]), step.opts);
    for (const b of el.querySelectorAll("[data-adv-i]")) b.onclick();
    out.push(seen);
  }
  else if (step.call === "secmodel") {
    out.push(adviceSectorsModel(step.sectors));
  }
  else if (step.call === "secmarks") {
    out.push(step.sectors.map((sec, i) =>
      sectorMarkHTML(sec, i === step.sectors.length - 1) !== ""));
  }
  else if (step.call === "linemarks") {
    out.push({ chips: step.corners.map((c, i) => lineChipHTML(c, i, false).includes("adv-mark")),
               names: step.corners.map((c) => lineNameHTML(c).includes("adv-mark")) });
  }
  else if (step.call === "gotoline") {
    LINE = { corners: step.corners }; LINE_I = 0; CALLS.length = 0;
    const picked = step.corners[step.pick];
    if (step.reload) LINE = { corners: step.reload };
    gotoAdviceLine(picked);
    out.push({ i: LINE_I, calls: CALLS.slice() });
  }
  else if (step.call === "bands") {
    const arcs = [];
    const ctx = new Proxy({ arc: (x, y) => arcs.push([x, y]) },
      { get: (o, k) => (k in o ? o[k] : (k === "measureText" ? () => ({ width: 10 }) : () => {})),
        set: () => true });
    cornerBands(ctx, 1000, 150, step.corners);
    out.push(arcs);
  }
  else if (step.call === "dynhidden") {
    out.push(dynamicsAdviceHidden({ review: { channels: step.channels } }));
  }
  else if (step.call === "gotodyn") {
    CALLS.length = 0; SCROLLS.length = 0;
    els["dyn-coasting"] = { scrollIntoView: () => SCROLLS.push("dyn-coasting") };
    els["c-slip"] = { scrollIntoView: () => SCROLLS.push("c-slip") };
    gotoAdviceDynamics(step.corner);
    out.push({ calls: CALLS.slice(), scrolls: SCROLLS.slice() });
  }
  else if (step.call === "progcorners") {
    out.push(progressAdviceCorners(step.p));
  }
  else if (step.call === "gotoprog") {
    DOC.exist = step.exist; DOC.asked.length = 0; SCROLLS.length = 0;
    gotoAdviceProgress(step.corner);
    out.push({ asked: DOC.asked.slice(), scrolls: SCROLLS.slice() });
  }
  else if (step.call === "progcards") {
    els["corner-sessions"] = fakeEl(); els["corner-consistency"] = fakeEl();
    renderCornerSessions(step.rows); renderCornerConsistency(step.rows);
    // quali schede (per corner_index) portano il segno
    const marked = (id) => els[id].innerHTML.split('data-corner="').slice(1)
      .map((seg) => [Number(seg.split('"')[0]), seg.includes("adv-mark")]);
    out.push({ sessions: marked("corner-sessions"), cons: marked("corner-consistency") });
  }
  else if (step.call === "dhrows") {
    els["dh-body"] = fakeEl(); els["dh-ref"] = fakeEl(); els["dh-note"] = fakeEl();
    renderDefectHistory(step.h);
    const rows = els["dh-body"].innerHTML.split('class="dh-row"').slice(1);
    out.push(rows.map((r) => [(r.match(/data-howto="([^"]*)"/) || [])[1],
                              r.includes("adv-mark")]));
  }
  else if (step.call === "relines") {
    // lo stesso elemento, riscritto piu' volte: quante scritture vere
    const el = els["adv-line-" + step.view] = fakeEl();
    let writes = 0;
    const desc = Object.getOwnPropertyDescriptor(el, "innerHTML");
    Object.defineProperty(el, "innerHTML", { configurable: true, get: desc.get,
      set: (v) => { writes++; desc.set(v); } });
    for (const adv of step.sequence) {
      if (adv !== "keep") ADVICE = adv;
      renderAdviceLine(step.view, step.corners, () => {}, step.opts);
    }
    out.push({ writes, hidden: el.cls.has("hidden") });
  }
  else if (step.call === "line") {
    const el = els["adv-line-" + step.view] = fakeEl();
    if (step.hide) step.opts = { hide: () => adviceLiftWithoutNote({ notes: step.notes }) };
    const gone = [];
    OPENED.length = 0;
    renderAdviceLine(step.view, step.corners, (c) => gone.push(c ? c.name : null),
                     step.opts);
    // si preme ogni bottone: i nomi, «Vai al punto», «Come si fa»
    for (const attr of ["data-adv-i", "data-adv-goto", "data-adv-how"]) {
      for (const b of el.querySelectorAll("[" + attr + "]")) if (b.onclick) b.onclick();
    }
    out.push({ hidden: el.cls.has("hidden"), html: el.innerHTML,
               gone, opened: OPENED.slice() });
  }
}
console.log(JSON.stringify(out));
"""

_ADVICE = {"defect": "brake_early", "name": "Frenata troppo presto",
           "corners": [{"name": "Variante Alta", "apex_pos": 0.42},
                       {"name": "Tosa", "apex_pos": 0.80}]}


def _run(tmp_path, job):
    script = tmp_path / "rimandi.js"
    script.write_text(_HARNESS, encoding="utf-8")
    cat = {key: en for key, (en, _it) in TEXTS.items()}
    cat["pag.howto"] = "How to do it →"
    cat["adv.and"] = _entry("adv.and")[0]
    env = dict(os.environ, CAT=json.dumps(cat))
    run = subprocess.run([_NODE, str(script), str(WEB / "app.js")],
                         input=json.dumps(job), capture_output=True, text=True,
                         encoding="utf-8", env=env, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


needs_node = pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")


@needs_node
def test_a_corner_is_the_advice_s_only_by_its_apex(tmp_path):
    one = {"defect": "brake_early", "name": "x",
           "corners": [{"name": "A", "apex_pos": 0.42}]}
    zero = {"defect": "brake_early", "name": "x",
            "corners": [{"name": "A", "apex_pos": 0}]}
    got = _run(tmp_path, [
        {"advice": None, "call": "apex", "arg": {"entry": 0.40, "exit": 0.45}},
        {"advice": one, "call": "apex", "arg": {"entry": 0.40, "exit": 0.45}},
        {"call": "apex", "arg": {"entry": 0.43, "exit": 0.50}},
        {"call": "apex", "arg": {"entry": 0.42, "exit": 0.50}},
        {"call": "apex", "arg": {"entry": 0.30, "exit": 0.42}},
        {"advice": zero, "call": "apex", "arg": {"entry": 0, "exit": 0.1}},
    ])
    assert got == [None, 0.42, None, 0.42, 0.42, None]


@needs_node
def test_which_views_show_the_line_for_which_defect(tmp_path):
    job = [{"advice": {"defect": d, "name": "x", "corners": []},
            "call": "relevant", "arg": v}
           for d in ("coasting", "min_speed") for v in ("line", "dynamics", "progress")]
    assert _run(tmp_path, job) == [False, True, True,    # coasting
                                   True, False, True]    # min_speed
    seven = ["brake_early", "brake_late", "over_brake", "throttle_late",
             "min_speed", "lift", "coasting"]
    got = _run(tmp_path, [{"advice": {"defect": d, "name": "x", "corners": []},
                           "call": "relevant", "arg": "progress"} for d in seven])
    assert got == [True] * 7
    assert _run(tmp_path, [{"advice": None, "call": "relevant", "arg": "compare"}]) == [False]


@needs_node
def test_the_line_names_the_found_corners_and_is_gone_without_advice(tmp_path):
    corners = [{"name": "Curva 1", "entry": 0.40, "exit": 0.45},
               {"name": "Curva 2", "entry": 0.60, "exit": 0.65},
               {"name": "", "entry": 0.78, "exit": 0.83}]
    got = _run(tmp_path, [
        {"advice": None, "call": "line", "view": "compare", "corners": corners},
        {"advice": _ADVICE, "call": "line", "view": "compare", "corners": corners},
        {"call": "line", "view": "dynamics", "corners": corners},
        {"call": "line", "view": "compare", "corners": [corners[1]]},
    ])
    off, on, wrong_view, none_found = got
    assert off["hidden"] and off["html"] == ""
    assert not on["hidden"]
    # nome della scheda dove c'e', quello del consiglio dove la scheda non ne ha
    assert "Curva 1" in on["html"] and "Tosa" in on["html"]
    assert "Curva 2" not in on["html"]
    assert on["html"].index("Curva 1") < on["html"].index("On the brake chart")
    assert " · " in on["html"] and 'class="adv-mark"' in on["html"]
    # il clic su un nome porta quella curva; «Come si fa» porta all'apice della prima
    assert on["gone"] == ["Curva 1", ""]
    assert on["opened"] == [["brake_early", 0.42]]
    assert wrong_view["hidden"] and wrong_view["html"] == ""
    assert none_found["hidden"] and none_found["html"] == ""


@needs_node
def test_lift_and_progress_lap_have_no_names_and_goto_null(tmp_path):
    lift = {"defect": "lift", "name": "x", "corners": []}
    got = _run(tmp_path, [
        {"advice": lift, "call": "line", "view": "compare", "corners": []},
        {"call": "line", "view": "progress", "corners": []},
    ])
    for g in got:
        assert not g["hidden"]
        assert "Show me" in g["html"]
        assert g["gone"] == [None]             # goto(null): il riquadro della scheda
        assert g["opened"] == [["lift", None]]
    assert "The straight-line notes" in got[0]["html"]
    assert "the advice you're following" in got[1]["html"]    # adv.progress.lap


@needs_node
def test_opts_replace_the_sentence_and_its_values(tmp_path):
    corners = [{"name": "Curva 1", "entry": 0.42, "exit": 0.42}]
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "line", "view": "sectors", "corners": corners,
         "opts": {"key": "adv.sectors.one", "vals": {"n": 2}}},
        {"call": "line", "view": "sectors", "corners": corners,
         "opts": {"key": "adv.sectors.many", "vals": {"list": "1 and 3"}}},
    ])
    assert "It's in sector 2." in got[0]["html"]
    assert "sectors 1 and 3." in got[1]["html"]
    assert "{n}" not in got[0]["html"] and "{list}" not in got[1]["html"]


@needs_node
def test_the_scroll_picks_the_figure_that_holds_the_apex(tmp_path):
    figs = [{"dataset": {"entry": "0.1", "exit": "0.2"}},
            {"dataset": {"entry": "0.4", "exit": "0.45"}},
            {"dataset": {"entry": "0.6", "exit": "0.7"}}]
    got = _run(tmp_path, [
        {"call": "figidx", "figs": figs, "apex": 0.42},
        {"call": "figidx", "figs": figs, "apex": 0.45},
        {"call": "figidx", "figs": figs, "apex": 0.40},
        {"call": "figidx", "figs": figs, "apex": 0.50},
        {"call": "figidx", "figs": figs, "apex": None},
    ])
    assert got == [1, 1, 1, -1, -1]


@needs_node
def test_progress_keeps_the_line_with_or_without_matched_corners(tmp_path):
    corners = [{"name": "Curva 1", "entry": 0.40, "exit": 0.45},
               {"name": "Curva 2", "entry": 0.60, "exit": 0.65}]
    lap = {"defect": "coasting", "name": "x", "corners": []}
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "line", "view": "progress", "corners": corners},
        {"call": "line", "view": "progress", "corners": [corners[1]]},   # nessuna ritrovata
        {"call": "line", "view": "progress", "corners": []},
        {"advice": lap, "call": "line", "view": "progress", "corners": corners},
    ])
    hit, nomatch, empty, nocorners = got
    assert not hit["hidden"] and "Curva 1" in hit["html"]
    assert "Further down, the cards for these corners" in hit["html"]
    for g in (nomatch, empty, nocorners):
        assert not g["hidden"], g
        assert "Curva" not in g["html"]
        assert "the advice you're following, session by session" in g["html"]
        assert g["gone"] == [None]


# --- Task 3: il Confronto e la scheda frenate --------------------------------

@pytest.mark.parametrize("head", [
    "function drawCornerSpeeds(", "function drawWaterfall(",
    "function drawDebrief(", "function renderBrakeSheet("])
def test_the_compare_cards_carry_the_mark_on_the_advice_corners(head):
    body = _body_of(head)
    assert "adviceApexIn(" in body, head
    assert "advMarkHTML(" in body, head


def test_the_chart_bands_and_the_map_mark_the_advice_corners_on_the_canvas():
    for head in ("function cornerBands(", "function drawMap("):
        body = _body_of(head)
        assert "adviceApexIn(" in body, head
        assert "drawAdvMark(" in body, head


def test_the_map_finds_the_apex_sample_with_the_shared_nearest():
    assert "nearest(" in _body_of("function drawMap(")


def test_the_compare_redraw_writes_its_line_from_the_tab_s_own_render_path():
    body = _body_of("function redraw(")
    assert 'renderAdviceLine("compare"' in body


def test_the_brake_sheet_rows_are_matched_on_their_own_span_not_on_the_index():
    body = _body_of("function renderBrakeSheet(")
    assert "adviceApexIn(r)" in body          # r ha entry/exit del suo riferimento
    assert "brakeRowOpen(adv)" in body         # la riga si ritrova per il goto
    assert "data-adv" in _body_of("function brakeRowOpen(")


def test_goto_for_lift_scrolls_to_the_first_lift_note():
    body = _body_of("function gotoAdviceCompare(")
    assert 'data-kind="lift"' in body
    assert "setRange(cornerWindow(" in body
    notes = _body_of("function noteBlocks(")
    assert "data-kind" in notes


@needs_node
def test_lift_advice_shows_the_line_only_if_the_debrief_has_a_lift_note(tmp_path):
    lift = {"defect": "lift", "name": "x", "corners": []}
    got = _run(tmp_path, [
        {"advice": lift, "call": "line", "view": "compare", "corners": [],
         "hide": True, "notes": []},
        {"call": "line", "view": "compare", "corners": [], "hide": True,
         "notes": [{"kind": "top_speed"}]},
        {"call": "line", "view": "compare", "corners": [], "hide": True,
         "notes": [{"kind": "top_speed"}, {"kind": "lift"}]},
    ])
    assert [g["hidden"] for g in got] == [True, True, False]
    assert got[0]["html"] == ""


@needs_node
def test_an_unchanged_line_is_not_rewritten_on_every_hover(tmp_path):
    corners = [{"name": "Curva 1", "entry": 0.40, "exit": 0.45, "index": 0}]
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "relines", "view": "compare",
         "corners": corners, "sequence": ["keep"] * 4},
    ])
    assert got[0]["writes"] == 1
    # scritta, spenta (una scrittura), ancora spenta (nessuna), riaccesa
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "relines", "view": "compare",
         "corners": corners, "sequence": ["keep", None, {"defect": "coasting",
          "name": "x", "corners": []}, _ADVICE]},
    ])
    assert got[0]["writes"] == 3 and got[0]["hidden"] is False


@needs_node
def test_only_the_brake_row_whose_span_holds_the_apex_gets_the_mark(tmp_path):
    # indici del riferimento della scheda DIVERSI da quelli dell'analisi: la
    # riga 0 della scheda non e' la curva 0 dell'analisi.
    rows = [{"index": 0, "entry": 0.10, "exit": 0.20},
            {"index": 5, "entry": 0.40, "exit": 0.45},
            {"index": 6, "entry": 0.70, "exit": 0.75},
            {"index": 7, "entry": None, "exit": None}]
    got = _run(tmp_path, [
        {"advice": _ADVICE, "adv_row": None, "call": "brakerows", "rows": rows},
        {"adv_row": 0.42, "call": "brakerows", "rows": rows},
        {"advice": None, "adv_row": None, "call": "brakerows", "rows": rows},
    ])
    assert got[0] == ["<tr>", '<tr data-adv="0.42">', "<tr>", "<tr>"]
    # l'accensione sopravvive a una riscrittura della scheda
    assert got[1] == ["<tr>", '<tr data-adv="0.42" class="adv-hit">', "<tr>", "<tr>"]
    assert got[2] == ["<tr>"] * 4


@needs_node
def test_the_analysis_card_is_found_by_index_and_marked_by_its_own_span(tmp_path):
    a = {"corners": [{"index": 0, "entry": 0.40, "exit": 0.45},
                     {"index": 1, "entry": 0.60, "exit": 0.65}]}
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "analysismark", "a": a, "indices": [0, 1, 9]},
    ])
    assert got == [[True, False, False]]


# --- Task 4: Traiettoria e Settori -------------------------------------------

_SECS = [{"start": 0.0, "end": 0.30}, {"start": 0.30, "end": 0.65},
         {"start": 0.65, "end": 1.0}]


def _adv(*apexes, defect="brake_early"):
    return {"defect": defect, "name": "x",
            "corners": [{"name": f"C{i}", "apex_pos": a} for i, a in enumerate(apexes)]}


@needs_node
def test_the_sectors_line_picks_one_same_or_many_and_the_list(tmp_path):
    got = _run(tmp_path, [
        {"advice": _adv(0.42), "call": "secmodel", "sectors": _SECS},
        {"advice": _adv(0.40, 0.50), "call": "secmodel", "sectors": _SECS},
        {"advice": _adv(0.10, 0.80), "call": "secmodel", "sectors": _SECS},
        {"advice": _adv(0.10, 0.42, 0.80), "call": "secmodel", "sectors": _SECS},
    ])
    assert (got[0]["key"], got[0]["vals"]) == ("adv.sectors.one", {"n": 2})
    assert (got[1]["key"], got[1]["vals"]) == ("adv.sectors.same", {"n": 2})
    assert (got[2]["key"], got[2]["vals"]) == ("adv.sectors.many", {"list": "1 and 3"})
    assert (got[3]["key"], got[3]["vals"]) == ("adv.sectors.many", {"list": "1, 2 and 3"})
    # i nomi sono quelli del consiglio, con l'apice come unico tratto
    assert got[3]["corners"] == [
        {"name": "C0", "entry": 0.10, "exit": 0.10, "sector": 0},
        {"name": "C1", "entry": 0.42, "exit": 0.42, "sector": 1},
        {"name": "C2", "entry": 0.80, "exit": 0.80, "sector": 2}]


@needs_node
def test_the_sectors_line_is_off_when_no_advice_corner_falls_in_a_sector(tmp_path):
    got = _run(tmp_path, [
        {"advice": None, "call": "secmodel", "sectors": _SECS},
        {"advice": _adv(0), "call": "secmodel", "sectors": _SECS},          # non trovato
        {"advice": _adv(), "call": "secmodel", "sectors": _SECS},           # senza curve
        {"advice": _adv(0.42), "call": "secmodel", "sectors": []},          # senza settori
        {"advice": _adv(0.42), "call": "secmodel", "sectors": [{"start": 0.5, "end": 0.9}]},
    ])
    assert got == [None] * 5


@needs_node
def test_an_apex_on_a_sector_boundary_counts_for_one_sector_only(tmp_path):
    got = _run(tmp_path, [
        {"advice": _adv(0.30), "call": "secmodel", "sectors": _SECS},
        {"advice": _adv(1.0), "call": "secmodel", "sectors": _SECS},
    ])
    assert (got[0]["key"], got[0]["vals"]) == ("adv.sectors.one", {"n": 2})
    assert (got[1]["key"], got[1]["vals"]) == ("adv.sectors.one", {"n": 3})


@needs_node
def test_only_the_sectors_that_hold_an_apex_get_the_mark(tmp_path):
    got = _run(tmp_path, [
        {"advice": _adv(0.42), "call": "secmarks", "sectors": _SECS},
        {"advice": None, "call": "secmarks", "sectors": _SECS},
    ])
    assert got == [[False, True, False], [False, False, False]]


@needs_node
def test_only_the_trajectory_corner_whose_span_holds_the_apex_gets_the_mark(tmp_path):
    # indici della Traiettoria diversi da quelli dell'analisi: si guarda il tratto
    corners = [{"index": 3, "name": "A", "entry": 0.10, "exit": 0.20},
               {"index": 4, "name": "B", "entry": 0.40, "exit": 0.45},
               {"index": 5, "name": "C", "entry": 0.70, "exit": 0.75}]
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "linemarks", "corners": corners},
        {"advice": None, "call": "linemarks", "corners": corners},
    ])
    assert got[0] == {"chips": [False, True, False], "names": [False, True, False]}
    assert got[1] == {"chips": [False] * 3, "names": [False] * 3}


@needs_node
def test_goto_on_the_trajectory_opens_the_corner_by_its_position_in_its_own_list(tmp_path):
    corners = [{"index": 3, "name": "A", "entry": 0.10, "exit": 0.20},
               {"index": 4, "name": "B", "entry": 0.40, "exit": 0.45}]
    got = _run(tmp_path, [{"call": "gotoline", "corners": corners, "pick": 1}])
    assert got[0]["i"] == 1
    assert got[0]["calls"][0][0] == "range" and got[0]["calls"][0][1]["corner"] == 4
    assert got[0]["calls"][-1] == ["redraw"]


def test_the_trajectory_writes_its_line_from_its_own_render_path():
    assert 'renderAdviceLine("line"' in _body_of("function renderLine(")
    assert "lineChipHTML(" in _body_of("function renderLine(")
    assert "lineNameHTML(" in _body_of("function renderLineTable(")


def test_the_sectors_write_their_line_from_their_own_render_path():
    draw = _body_of("function drawSectors(")
    assert 'renderAdviceLine("sectors"' in draw
    assert "adviceSectorsModel(" in draw
    # la riga porta le curve e la frase scelte dal modello, non una lista vuota
    assert "am.corners" in draw and "am.key" in draw and "am.vals" in draw
    assert "sectorMarkHTML(" in draw
    assert "sectorMarkHTML(" in _body_of("function drawSectorTable(")
    # anche quando i settori non arrivano la riga si spegne
    assert 'renderAdviceLine("sectors"' in _body_of("async function loadSectors(")


@needs_node
def test_the_buttons_use_the_latest_corners_and_goto_even_when_nothing_is_rewritten(tmp_path):
    corners = [{"name": "Curva 1", "entry": 0.40, "exit": 0.45, "index": 4}]
    got = _run(tmp_path, [{"advice": _ADVICE, "call": "stale", "view": "line",
                           "corners": corners}])
    assert got == [[["new", corners[0]]]]


@needs_node
def test_goto_finds_the_corner_in_a_reloaded_payload_by_value(tmp_path):
    corners = [{"index": 3, "name": "A", "entry": 0.10, "exit": 0.20},
               {"index": 4, "name": "B", "entry": 0.40, "exit": 0.45}]
    copy = json.loads(json.dumps(corners))
    got = _run(tmp_path, [{"call": "gotoline", "corners": corners, "pick": 1,
                           "reload": copy}])
    assert got[0]["i"] == 1


@needs_node
def test_the_sectors_marks_are_written_on_the_bars_and_the_table_header(tmp_path):
    sec = lambda i, a, b: {"index": i, "start": a, "end": b, "review_ms": 1000,
                           "baseline_ms": 1000, "delta_ms": 0, "is_best": False}
    s = {"real": True, "sectors": [sec(0, 0, .3), sec(1, .3, .65), sec(2, .65, 1)],
         "n": 3, "review": {"path": "a"}, "laps": [],
         "per_lap": [{"path": "a", "lap_time": "1", "ms": [1, 1, 1]},
                     {"path": "b", "lap_time": "2", "ms": [1, 1, 1]}]}
    got = _run(tmp_path, [{"advice": _adv(0.42), "call": "sectable", "s": s},
                          {"advice": None, "call": "sectable", "s": s}])
    assert got[0] == {"bars": 1, "table": 1, "line": 1}
    assert got[1] == {"bars": 0, "table": 0, "line": 0}


def test_the_trajectory_line_is_switched_off_when_the_load_fails():
    body = _body_of("async function loadLine(")
    assert 'renderAdviceLine("line", [], null' in body


@needs_node
def test_the_line_numbers_the_sectors_like_the_bars_do(tmp_path):
    secs = [dict(sec, index=i + 4) for i, sec in enumerate(_SECS)]
    got = _run(tmp_path, [{"advice": _adv(0.42), "call": "secmodel", "sectors": secs}])
    assert got[0]["vals"] == {"n": 6}


# --- Task 5: Dinamica e Andamento ---------------------------------------------

def test_the_dynamics_writes_its_line_from_its_own_render_path():
    body = _body_of("function drawDynamics(")
    # con dati: la riga porta le curve del giro e il suo goto; senza dati si spegne
    assert 'renderAdviceLine("dynamics", DATA.corners || [], gotoAdviceDynamics' in body
    assert 'renderAdviceLine("dynamics", [], null' in body
    assert "dynamicsAdviceHidden(" in body


@pytest.mark.parametrize("fn", ["drawSlip", "drawYaw", "drawShift"])
def test_the_dynamics_charts_draw_their_bands_through_the_shared_helper(fn):
    # il segno sulle fasce vive in cornerBands: un canvas che disegna le fasce
    # per conto suo non lo avrebbe
    assert "cornerBands(ctx, w, h, a.corners)" in _body_of(f"function {fn}(")


@needs_node
def test_the_band_helper_marks_only_the_advice_corner_on_the_canvas(tmp_path):
    corners = [{"index": 0, "name": "A", "entry": 0.10, "exit": 0.20},
               {"index": 1, "name": "B", "entry": 0.40, "exit": 0.45},
               {"index": 2, "name": "C", "entry": 0.70, "exit": 0.75}]
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "bands", "corners": corners},
        {"advice": None, "call": "bands", "corners": corners},
    ])
    # un solo cerchio, sull'apice 0.42 (x = 420 su 1000 px), in basso
    assert got[0] == [[420, 144]]
    assert got[1] == []


@needs_node
def test_the_line_on_the_dynamics_is_off_for_a_corner_the_advice_does_not_name(tmp_path):
    named = [{"index": 1, "name": "B", "entry": 0.40, "exit": 0.45}]
    other = [{"index": 2, "name": "C", "entry": 0.70, "exit": 0.75}]
    ob = {"defect": "over_brake", "name": "x",
          "corners": [{"name": "Variante Alta", "apex_pos": 0.42}]}
    got = _run(tmp_path, [
        {"advice": ob, "call": "line", "view": "dynamics", "corners": named},
        {"call": "line", "view": "dynamics", "corners": other},
    ])
    assert not got[0]["hidden"] and "B" in got[0]["html"]
    assert got[0]["gone"] == ["B"]
    assert got[1]["hidden"] and got[1]["html"] == ""


@needs_node
def test_the_coasting_line_has_no_names_and_goto_null_scrolls_to_the_box(tmp_path):
    coast = {"defect": "coasting", "name": "x", "corners": []}
    got = _run(tmp_path, [
        {"advice": coast, "call": "line", "view": "dynamics",
         "corners": [{"index": 1, "name": "B", "entry": 0.40, "exit": 0.45}]},
        {"call": "gotodyn", "corner": None},
    ])
    assert not got[0]["hidden"] and "B" not in got[0]["html"]
    assert got[0]["gone"] == [None]
    assert got[1] == {"calls": [], "scrolls": ["dyn-coasting"]}


@needs_node
def test_goto_on_the_dynamics_sets_the_window_on_the_corner_and_scrolls_to_the_slip(tmp_path):
    corner = {"index": 4, "name": "B", "entry": 0.40, "exit": 0.45}
    got = _run(tmp_path, [{"call": "gotodyn", "corner": corner}])
    assert got[0]["calls"][0][0] == "range" and got[0]["calls"][0][1]["corner"] == 4
    assert got[0]["calls"][-1] == ["redraw"]
    assert got[0]["scrolls"] == ["c-slip"]


@needs_node
def test_the_dynamics_line_is_off_when_the_chart_it_points_to_has_no_data(tmp_path):
    full = {"throttle": [0, 1], "brake": [0.5, 0], "slip_front": [0, 0.1], "slip_rear": [0, 0]}
    got = _run(tmp_path, [
        {"advice": {"defect": "coasting", "name": "x", "corners": []},
         "call": "dynhidden", "channels": full},
        {"call": "dynhidden", "channels": {"throttle": [], "brake": []}},
        {"advice": {"defect": "over_brake", "name": "x", "corners": []},
         "call": "dynhidden", "channels": full},
        {"call": "dynhidden", "channels": {"slip_front": [0, 0], "slip_rear": [0, 0]}},
        {"advice": {"defect": "throttle_late", "name": "x", "corners": []},
         "call": "dynhidden", "channels": {"slip_front": [0, 0], "slip_rear": [0, 0.2]}},
    ])
    assert got == [False, True, False, True, False]


def test_the_defect_history_rows_are_marked_by_the_defect_key():
    body = _body_of("function renderDefectHistory(")
    assert "advMarkHTML(" in body and "ADVICE.defect" in body


@needs_node
def test_only_the_defect_history_row_of_the_advice_gets_the_mark(tmp_path):
    h = {"reference": None, "sessions": [{}, {}],
         "defects": [{"key": "brake_early", "name": "A", "values": [1, 2], "unit": "s"},
                     {"key": "coasting", "name": "B", "values": [1, 2], "unit": "s"},
                     {"key": "lift", "name": "C", "values": [1, 2], "unit": "s"}]}
    got = _run(tmp_path, [
        {"advice": {"defect": "coasting", "name": "x", "corners": []},
         "call": "dhrows", "h": h},
        {"advice": None, "call": "dhrows", "h": h},
    ])
    assert got[0] == [["brake_early", False], ["coasting", True], ["lift", False]]
    assert got[1] == [["brake_early", False], ["coasting", False], ["lift", False]]


_PTS = [{"median_s": 0.1, "laps": 3, "started": ""}, {"median_s": 0.2, "laps": 3, "started": ""}]
_PROG_ROWS = [
    {"corner_index": 3, "name": "A", "entry": 0.10, "exit": 0.20, "spread_kmh": 1,
     "std_kmh": 1, "n": 3, "points": _PTS},
    {"corner_index": 4, "name": "B", "entry": 0.40, "exit": 0.45, "spread_kmh": 1,
     "std_kmh": 1, "n": 3, "points": _PTS},
    {"corner_index": 5, "name": "C", "spread_kmh": 1, "std_kmh": 1, "n": 3,   # senza tratto
     "points": _PTS},
]


@needs_node
def test_the_progress_corner_cards_are_marked_by_their_own_span(tmp_path):
    got = _run(tmp_path, [
        {"advice": _ADVICE, "call": "progcards", "rows": _PROG_ROWS},
        {"advice": None, "call": "progcards", "rows": _PROG_ROWS},
    ])
    expect = [[3, False], [4, True], [5, False]]
    assert got[0] == {"sessions": expect, "cons": expect}
    off = [[3, False], [4, False], [5, False]]
    assert got[1] == {"sessions": off, "cons": off}


@needs_node
def test_the_progress_cards_are_listed_once_per_corner_for_the_line(tmp_path):
    p = {"corner_sessions": [_PROG_ROWS[1], _PROG_ROWS[0]],
         "corner_consistency": [_PROG_ROWS[1], _PROG_ROWS[2]]}
    got = _run(tmp_path, [{"advice": _ADVICE, "call": "progcorners", "p": p},
                          {"call": "progcorners", "p": {}}])
    assert [c["index"] for c in got[0]] == [4, 3, 5]
    assert got[0][0] == {"index": 4, "name": "B", "entry": 0.40, "exit": 0.45}
    assert "entry" not in got[0][2]
    assert got[1] == []


@needs_node
def test_progress_goto_scrolls_to_the_defect_row_or_to_the_corner_card(tmp_path):
    coast = {"defect": "coasting", "name": "x", "corners": []}
    sel_c = '#corner-consistency [data-corner="4"]'
    sel_s = '#corner-sessions [data-corner="4"]'
    got = _run(tmp_path, [
        {"advice": coast, "call": "gotoprog", "corner": None,
         "exist": ['#dh-body [data-howto="coasting"]']},
        {"advice": _ADVICE, "call": "gotoprog", "corner": {"index": 4},
         "exist": [sel_s, sel_c]},
        {"call": "gotoprog", "corner": {"index": 4}, "exist": [sel_c]},   # solo coerenza
        {"call": "gotoprog", "corner": {"index": 4}, "exist": []},        # niente: non cade
    ])
    assert got[0]["scrolls"] == ['#dh-body [data-howto="coasting"]']
    assert got[1]["scrolls"] == [sel_s]
    assert got[2]["scrolls"] == [sel_c]
    assert got[3]["scrolls"] == []


def test_the_progress_loader_writes_its_line_and_switches_it_off_on_failure():
    body = _body_of("async function loadProgress(")
    assert 'renderAdviceLine("progress", progressAdviceCorners(p), gotoAdviceProgress' in body
    assert 'renderAdviceLine("progress", [], null' in body
    # le schede che il segno decora leggono lo stesso tratto
    assert "adviceApexIn(" in _body_of("function renderCornerSessions(")
    assert "adviceApexIn(" in _body_of("function renderCornerConsistency(")

