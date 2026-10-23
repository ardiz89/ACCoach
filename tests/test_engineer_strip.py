"""La striscia della strada dell'ingegnere (spec «La strada dell'ingegnere»).

Le tappe e la frase del passo si calcolano da `engineer.progress` (Task 1) con
una funzione pura: `HoneTablet.stripText` in tablet.js (ES5, Safari 9) e
`stripText` in engineer.js, la pagina completa. Le due pagine devono raccontare
la stessa cosa, quindi gli stessi casi passano su tutte e due, e i risultati si
confrontano uno per uno.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

import tono
from test_tablet_box import _BOX_HARNESS
from test_tablet_page import _NODE, needs_node

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"

# Le fasi del profilo GT3, come le manda il motore (etichette tradotte).
_PHASES = [
    {"key": "pressures", "label": "Pressioni", "tag": "BOX"},
    {"key": "mechanical", "label": "Grip meccanico", "tag": "BOX"},
    {"key": "aero", "label": "Aero / rake", "tag": "BOX"},
    {"key": "brake_bias", "label": "Bilanciamento freni", "tag": "AV"},
    {"key": "electronics", "label": "Elettronica", "tag": "AV"},
]


def _p(index, stage, have=None, need=None):
    return {"phases": _PHASES, "index": index, "stage": stage, "have": have, "need": need}


# I casi: il nome, gli argomenti di `stripText` (`progress`, il `tag` della
# modifica in attesa). Il «dove» della modifica viene dalla modifica, non
# dalla fase: le fasi 3 e 4 (dal volante) propongono anche leve da box, e una
# fase da box propone il bilanciamento freni dal volante.
_CASES = [
    ("baseline", [_p(0, "baseline", 2, 3), None]),
    ("test", [_p(1, "test", 1, 3), "BOX"]),
    ("change_box", [_p(1, "change"), "BOX"]),
    ("change_av", [_p(3, "change"), "AV"]),
    ("change_box_in_av_phase", [_p(3, "change"), "BOX"]),
    ("change_av_in_box_phase", [_p(1, "change"), "AV"]),
    ("change_untagged", [_p(1, "change"), None]),
    ("restore", [_p(2, "restore"), "BOX"]),
    ("diagnose", [_p(1, "diagnose"), None]),
    ("done", [_p(5, "done"), None]),
    ("change_after_done", [_p(5, "change"), "BOX"]),
    ("baseline_no_count", [_p(0, "baseline"), None]),
    ("test_no_count", [_p(1, "test"), None]),
    ("null", [None, None]),
]

# tablet.js come lo carica la pagina, con la lingua scelta.
_TABLET = """
var window = {HONE_LANG: process.argv[3]};
var document = {readyState: "complete",
  querySelectorAll: function () { return []; },
  querySelector: function () { return null; },
  getElementById: function () { return null; },
  documentElement: {}};
var fs = require("fs");
eval(fs.readFileSync(process.argv[1], "utf8"));
eval(fs.readFileSync(process.argv[2], "utf8"));
var cases = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map(function (a) {
  return window.HoneTablet.stripText(a[0], a[1]);
})));
"""

# La funzione di engineer.js, presa dal file come fa test_engineer_record_panel.
_ENGINEER = r"""
const fs = require("fs");
const [i18nPath, engPath, lang] = process.argv.slice(1);
global.window = {};
window.HONE_LANG = lang;
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(i18nPath, "utf8"));
const src = fs.readFileSync(engPath, "utf8");
function grab(name) {
  const i = src.indexOf("function " + name + "(");
  if (i < 0) throw new Error("manca " + name);
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
const line = (re) => src.split("\n").find((l) => re.test(l));
const asVar = (code) => code.replace(/^const /, "var ");
eval(asVar(line(/^const t = /)));
eval(asVar(src.slice(src.indexOf("const tf = "), src.indexOf("};", src.indexOf("const tf = ")) + 2)));
eval(grab("stripText"));
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map((a) => stripText(a[0], a[1]))));
"""


def _run(harness, script, lang, cases):
    r = subprocess.run([_NODE, "-e", harness, str(_WEB / "i18n.js"), str(_WEB / script), lang],
                       input=json.dumps(cases), capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _both(lang):
    """{nome del caso: (tablet, engineer)} per ogni caso."""
    cases = [c[1] for c in _CASES]
    tab = _run(_TABLET, "tablet.js", lang, cases)
    eng = _run(_ENGINEER, "engineer.js", lang, cases)
    return {name: (a, b) for (name, _), a, b in zip(_CASES, tab, eng)}


def _states(r):
    return [s["state"] for s in r["steps"]]


@needs_node
@pytest.mark.parametrize("lang", ["it", "en"])
def test_both_pages_tell_the_same_road(lang):
    for name, (tab, eng) in _both(lang).items():
        assert tab == eng, name


@needs_node
@pytest.mark.parametrize("page", [0, 1], ids=["tablet", "engineer"])
def test_the_road_in_italian(page):
    r = {k: v[page] for k, v in _both("it").items()}

    b = r["baseline"]
    assert _states(b) == ["now", "next", "next", "next", "next"]
    assert [s["label"] for s in b["steps"]] == [p["label"] for p in _PHASES]
    assert b["line"] == "Giri buoni per la base, 2 di 3."
    assert "75 °C" in b["why"] and "valido" in b["why"]

    t = r["test"]
    assert _states(t) == ["done", "now", "next", "next", "next"]
    assert t["line"] == "Provo la modifica, giri buoni 1 di 3. Poi decido se tenerla."
    assert t["why"] == b["why"]

    assert r["change_box"]["line"] == "Hai una modifica da fare ai box."
    assert r["change_av"]["line"] == "Hai una modifica da fare dal volante."
    assert _states(r["change_av"]) == ["done", "done", "done", "now", "next"]
    # Il «dove» lo dice la modifica, non la fase.
    assert r["change_box_in_av_phase"]["line"] == "Hai una modifica da fare ai box."
    assert r["change_av_in_box_phase"]["line"] == "Hai una modifica da fare dal volante."
    assert r["change_untagged"]["line"] == "Hai una modifica da fare."
    # Diverso dall'avviso di rientro, che nello stesso momento sta sopra.
    assert r["restore"]["line"] == (
        "La modifica non ha aiutato. Quando è di nuovo com'era rifaccio la base.")
    assert r["diagnose"]["line"] == "Ho i giri che servono e decido a fine giro."
    # Il perché del giro buono serve solo dove si contano giri.
    for name in ("change_box", "change_av", "change_box_in_av_phase", "restore",
                 "diagnose", "done"):
        assert r[name]["why"] == "", name

    # Review Focus 3: finito, niente contatore e niente tappa accesa oltre la fine.
    d = r["done"]
    assert _states(d) == ["done"] * 5
    assert d["line"] == "Assetto finito, tutte le fasi sono fatte."
    assert not re.search(r"\d", d["line"])
    # Una modifica proposta a fasi finite (il ricontrollo delle pressioni).
    a = r["change_after_done"]
    assert _states(a) == ["done"] * 5
    assert a["line"] == "Hai una modifica da fare ai box."

    # Il contatore viene dal motore: senza numeri la frase non ne scrive uno.
    for name in ("baseline_no_count", "test_no_count"):
        assert r[name]["line"] == "" and r[name]["why"] == "", name

    # Review Focus 4: senza `progress` niente striscia, e niente si rompe.
    assert r["null"] is None


@needs_node
def test_the_road_in_english():
    r = {k: v[0] for k, v in _both("en").items()}
    assert r["baseline"]["line"] == "Good laps for the baseline, 2 of 3."
    assert r["test"]["line"] == "Testing the change, good laps 1 of 3. Then I decide whether to keep it."
    assert r["change_av"]["line"] == "You have a change to make from the wheel."
    assert r["change_box_in_av_phase"]["line"] == "You have a change to make in the pits."
    assert r["restore"]["line"] == (
        "The change didn't help. Once it's back as it was, I redo the baseline.")
    assert r["done"]["line"] == "Setup finished, every phase is done."


@needs_node
def test_a_broken_progress_hides_the_strip_instead_of_breaking():
    bad = [[b, "BOX"] for b in
           ({}, {"phases": []}, {"phases": "x", "index": 0, "stage": "baseline"}, "x", 3)]
    assert _run(_TABLET, "tablet.js", "it", bad) == [None] * len(bad)
    assert _run(_ENGINEER, "engineer.js", "it", bad) == [None] * len(bad)


def test_the_new_keys_are_on_the_engineer_surface_and_in_tone():
    keys = {f"web/i18n.js:eng.road.{k}" for k in
            ("base", "why", "change", "changeBox", "changeAv", "test", "restore",
             "diagnose", "done")}
    entries = tono.SURFACES["engineer"]()
    assert keys <= set(entries), keys - set(entries)
    for k in keys:
        assert set(entries[k]) == {"it", "en"}, k
        for lang, text in entries[k].items():
            assert tono.violations(text, lang) == [], (k, lang, text)


def test_the_strip_sits_above_the_phase_line_on_both_pages():
    tab = (_WEB / "tablet.html").read_text(encoding="utf-8")
    assert 0 < tab.index('id="t-road"') < tab.index('id="t-phase"')
    # Fuori dalle due schermate: si vede in tutte e due le linguette.
    assert tab.index('id="t-road"') > tab.index('id="t-track"')
    eng = (_WEB / "engineer.html").read_text(encoding="utf-8")
    assert 0 < eng.index('id="es-road"') < eng.index('id="es-phase"')


# Il DOM finto dei box: la striscia si scrive solo quando cambia.
_DOM = _BOX_HARNESS.split("var out = {};")[0] + r"""
var out = {};
var road = function (eng) {
  var f = JSON.parse(JSON.stringify(frame)); f.at_box = false; f.engineer = eng; return f;
};
var prog = {phases: [{key: "pressures", label: "Pressioni", tag: "BOX"},
                     {key: "brake_bias", label: "Bilanciamento freni", tag: "AV"}],
            index: 0, stage: "baseline", have: 1, need: 3};
window.HoneTablet.render(road({phase: {key: "pressures", label: "Pressioni"}}));
out.hiddenWithout = $("t-road").hidden;
for (var i = 0; i < 3; i++) {
  window.HoneTablet.render(road({phase: {key: "pressures", label: "Pressioni"}, progress: prog}));
}
out.hiddenWith = $("t-road").hidden;
// Il DOM finto non svuota i figli con innerHTML: tre frame uguali, un disegno.
out.steps = $("t-road-steps").children.length;
out.line = $("t-road-line").textContent;
var p2 = JSON.parse(JSON.stringify(prog)); p2.have = 2;
window.HoneTablet.render(road({phase: {key: "pressures", label: "Pressioni"}, progress: p2}));
out.line2 = $("t-road-line").textContent;
window.HoneTablet.render(road(null));
out.hiddenNull = $("t-road").hidden;
process.stdout.write(JSON.stringify(out));
"""


@needs_node
def test_the_tablet_writes_the_strip_only_when_it_changes():
    r = subprocess.run([_NODE, "-e", _DOM, str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hiddenWithout"] is True
    assert out["hiddenWith"] is False
    assert out["steps"] == 2
    assert out["line"] == "Giri buoni per la base, 1 di 3."
    assert out["line2"] == "Giri buoni per la base, 2 di 3."
    assert out["hiddenNull"] is True


# renderRoad di engineer.js, sul suo DOM finto: tre frame uguali, un disegno.
_ENG_DOM = _ENGINEER.split("const cases = ")[0] + r"""
let writes = 0;
const els = {};
const El = () => ({ hidden: false, textContent: "", className: "", children: [],
  set innerHTML(v) { writes++; this.children = []; },
  appendChild(c) { this.children.push(c); return c; } });
var $ = (id) => els[id] || (els[id] = El());
global.document.createElement = () => El();
eval("var roadKey = null;");
eval(grab("renderRoad"));
const prog = { phases: [{ key: "pressures", label: "Pressioni", tag: "BOX" }],
               index: 0, stage: "baseline", have: 1, need: 3 };
const out = {};
renderRoad({});
out.hiddenWithout = $("es-road").hidden;
for (let i = 0; i < 3; i++) renderRoad({ progress: prog });
out.writes = writes;
out.hiddenWith = $("es-road").hidden;
out.line = $("es-road-line").textContent;
renderRoad({ progress: Object.assign({}, prog, { have: 2 }) });
out.writes2 = writes;
out.line2 = $("es-road-line").textContent;
renderRoad({ progress: Object.assign({}, prog, { stage: "change" }), tag: "AV" });
out.line3 = $("es-road-line").textContent;
renderRoad(null);
out.hiddenNull = $("es-road").hidden;
console.log(JSON.stringify(out));
"""


@needs_node
def test_the_engineer_page_writes_the_strip_only_when_it_changes():
    r = subprocess.run([_NODE, "-e", _ENG_DOM, str(_WEB / "i18n.js"), str(_WEB / "engineer.js"),
                        "it"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hiddenWithout"] is True and out["hiddenWith"] is False
    assert out["writes"] == 1
    assert out["line"] == "Giri buoni per la base, 1 di 3."
    assert out["writes2"] == 2 and out["line2"] == "Giri buoni per la base, 2 di 3."
    assert out["line3"] == "Hai una modifica da fare dal volante."
    assert out["hiddenNull"] is True
