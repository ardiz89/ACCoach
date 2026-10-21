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
const OPENED = [];
function openHowto(d, a) { OPENED.push([d, a]); }
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
