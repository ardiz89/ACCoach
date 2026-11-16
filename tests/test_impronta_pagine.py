"""Le pagine e l'impronta dell'assetto (Task 6).

La pagina Ingegnere e il tablet mandano al motore il percorso del file scritto
o scelto, mostrano quale assetto il motore riconosce in macchina (`loaded`) e
avvisano se il file su cui si lavora non e' quello. Si prova in node, sui file
che le pagine caricano.
"""
import json
import subprocess
from pathlib import Path

import pytest

import tono
from test_tablet_box import _BOX_HARNESS
from test_tablet_page import _NODE, needs_node

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_ROOT = Path(__file__).resolve().parent.parent

_KEYS = ("match", "probable", "unsaved", "unknown", "tag", "differs")


# ---- le chiavi ------------------------------------------------------------

def test_the_new_keys_are_in_both_languages_and_in_tone():
    entries = tono.SURFACES["engineer"]()
    keys = [f"web/i18n.js:eng.loaded.{k}" for k in _KEYS] + ["web/i18n.js:eng.carry"]
    assert set(keys) <= set(entries), set(keys) - set(entries)
    for k in keys:
        assert set(entries[k]) == {"it", "en"}, k
        for lang, text in entries[k].items():
            assert tono.violations(text, lang) == [], (k, lang, text)


# ---- il tablet ------------------------------------------------------------

_TABLET_HEAD = _BOX_HARNESS.split("var out = {};")[0]


def _tablet(script: str, lang: str = "it") -> dict:
    code = _TABLET_HEAD.replace('HONE_LANG: "it"', f'HONE_LANG: "{lang}"') \
        + "var out = {};\n" + script + "\nprocess.stdout.write(JSON.stringify(out));"
    r = subprocess.run([_NODE, "-e", code, str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


_SETUPS = ('{car: "mclaren", track: "Imola", confirm: %s,'
           ' setups: [{name: "base", path: "S/base.json", mtime: 1},'
           ' {name: "HONE_1", path: "S/HONE_1.json", mtime: 2}], base: %s, last_written: null}')


@needs_node
def test_tablet_sends_the_written_file():
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, %s);
window.HoneTablet.render(frame);
reply(find("/api/setup/preview")[0], 200, {ok: true, errors: [], diff: [
  {group: "Gomme", label: "Pressione", slot: "FL", old_click: 57, new_click: 59,
   delta: 2, old_phys: "26 psi", new_phys: "26.2 psi"}]});
window.HoneTablet.render(frame);
$("t-write").onclick();
$("t-confirm-ok").onclick();
reply(find("/api/setup/apply")[0], 200, {ok: true, name: "HONE_2",
  path: "S/HONE_2.json", reload_hint: "x"});
out.applied = find("/engineer/applied").map(function (x) { return x.body; });
""" % (_SETUPS % ("false", '"S/HONE_1.json"')))
    assert out["applied"] == ['{"path":"S/HONE_2.json"}']


@needs_node
def test_tablet_answer_sends_the_path_to_the_engine():
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, %s);
window.HoneTablet.render(frame);
$("t-base").value = "S/base.json";
$("t-base").onchange();
out.base = find("/engineer/base").map(function (x) { return x.body; });
out.api = find("/api/setup/base").filter(function (x) { return x.method === "POST"; })
  .map(function (x) { return x.body; });
""" % (_SETUPS % ("true", "null")))
    assert out["base"] == ['{"path":"S/base.json"}']
    assert out["api"] == ['{"path":"S/base.json"}']


@needs_node
def test_tablet_av_done_keeps_the_empty_body():
    out = _tablet(r"""
var f = JSON.parse(JSON.stringify(frame)); f.at_box = false;
f.engineer = {kind: "propose", tag: "AV", change: {param: "brakeBias"}};
window.HoneTablet.render(f);
$("t-av-done").onclick();
out.applied = find("/engineer/applied").map(function (x) { return x.body; });
""")
    assert out["applied"] == ["{}"]


def _frame_with(loaded: str) -> str:
    return ("var f = JSON.parse(JSON.stringify(frame)); f.engineer.loaded = %s;"
            " window.HoneTablet.render(f);" % loaded)


@needs_node
@pytest.mark.parametrize("lang,loaded,text", [
    ("it", '{state: "match", name: "HONE_8", probable: false}', "In macchina c'è HONE_8."),
    ("it", '{state: "match", name: "HONE_8", probable: true}',
     "In macchina c'è probabilmente HONE_8."),
    ("it", '{state: "unsaved", name: null, names: []}', "Assetto non salvato"),
    ("it", '{state: "unknown", name: null, names: []}', "Non riconosciuto"),
    ("it", '{state: "ambiguous", name: null, names: ["a", "b"]}', "Non riconosciuto"),
    ("en", '{state: "match", name: "HONE_8", probable: false}', "The car has HONE_8."),
    ("en", '{state: "unsaved", name: null, names: []}', "Setup not saved"),
])
def test_tablet_loaded_line(lang, loaded, text):
    out = _tablet(_frame_with(loaded) + r"""
out.text = $("t-loaded").textContent; out.hidden = $("t-loaded").hidden;
""", lang)
    assert out["hidden"] is False and out["text"] == text


@needs_node
def test_tablet_loaded_line_hidden_without_it_and_never_html():
    out = _tablet(_frame_with("null") + r"""
out.hidden = $("t-loaded").hidden;
""")
    assert out["hidden"] is True
    out = _tablet(_frame_with('{state: "match", name: "<img src=x>", probable: false}') + r"""
out.html = $("t-loaded").innerHTML; out.text = $("t-loaded").textContent;
""")
    assert out["html"] == "" and "<img" in out["text"]


@needs_node
def test_tablet_dropdown_labels_the_file_in_the_car_and_stays_empty():
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, %s);
var f = JSON.parse(JSON.stringify(frame));
f.engineer.loaded = {state: "match", name: "HONE_1", probable: false};
window.HoneTablet.render(f);
out.opts = $("t-base").children.map(function (o) { return o.textContent; });
out.sel = $("t-base").children.map(function (o) { return !!o.selected; });
out.sent = find("/engineer/base").length;
""" % (_SETUPS % ("true", "null")))
    assert out["opts"][-3:] == ["", "base", "HONE_1 · in macchina"]
    assert out["sel"][-3] is True and out["sent"] == 0


@needs_node
def test_tablet_warns_when_the_file_is_not_the_one_in_the_car():
    script = r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, %s);
var f = JSON.parse(JSON.stringify(frame));
f.engineer.loaded = {state: "match", name: "%s", probable: false};
window.HoneTablet.render(f);
out.text = $("t-warn").textContent; out.hidden = $("t-warn").hidden;
"""
    out = _tablet(script % (_SETUPS % ("false", '"S/HONE_1.json"'), "base"))
    assert out["hidden"] is False
    assert out["text"] == "In macchina c'è base, stai modificando HONE_1."
    out = _tablet(script % (_SETUPS % ("false", '"S/HONE_1.json"'), "HONE_1"))
    assert out["hidden"] is True


@needs_node
def test_tablet_carry_line():
    out = _tablet(r"""
var f = JSON.parse(JSON.stringify(frame));
f.engineer.carry = [{param: "brakeBias", delta_clicks: 1}];
window.HoneTablet.render(f);
out.text = $("t-carry").textContent; out.hidden = $("t-carry").hidden;
window.HoneTablet.render(frame);
out.hiddenAfter = $("t-carry").hidden;
""")
    assert out["hidden"] is False
    assert out["text"] == "Nel file metto anche le modifiche già tenute fatte dal volante."
    assert out["hiddenAfter"] is True


# ---- la pagina Ingegnere --------------------------------------------------

_ENGINEER = r"""
const fs = require("fs");
const [i18nPath, engPath, lang] = process.argv.slice(1);
global.window = {HONE_LANG: lang};
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(i18nPath, "utf8"));
const src = fs.readFileSync(engPath, "utf8");
function grab(name) {
  let i = src.indexOf("async function " + name + "(");
  if (i < 0) i = src.indexOf("function " + name + "(");
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
var sent = [];
var state = {setups: []}, WS_PORT = 1, location = {hostname: "pc"};
var liveUrl = (u) => u, liveRefused = () => {}, showToast = () => {};
var onComboChange = async () => {}, writeLocked = () => false;
var fetch = (u, o) => { sent.push({url: u, body: o.body}); return Promise.resolve({}); };
var api = (u, o) => { sent.push({url: u, body: o && o.body}); return Promise.resolve({}); };
for (const f of ["loadedText", "loadedWarn", "setupLabel", "afterWrite", "sendAnswer"]) {
  eval(grab(f));
}
const body = JSON.parse(fs.readFileSync(0, "utf8"));
(async () => {
  const out = {};
  out.text = body.loaded.map((l) => loadedText(l));
  out.warn = body.warn.map((a) => loadedWarn(a[0], a[1]));
  out.label = body.label.map((a) => setupLabel(a[0], a[1]));
  await afterWrite({name: "HONE_2", path: "S/HONE_2.json", reload_hint: "x"});
  state.answer = "S/base.json"; sendAnswer();
  out.sent = sent;
  process.stdout.write(JSON.stringify(out));
})();
"""


def _eng(lang="it"):
    body = {
        "loaded": [None, {"state": "match", "name": "HONE_8", "probable": False},
                   {"state": "match", "name": "HONE_8", "probable": True},
                   {"state": "unsaved"}, {"state": "unknown"}, {"state": "ambiguous"}],
        "warn": [[{"state": "match", "name": "a"}, "b"],
                 [{"state": "match", "name": "a"}, "a"],
                 [{"state": "unsaved"}, "b"], [None, "b"],
                 [{"state": "match", "name": "a"}, None]],
        "label": [["a", {"state": "match", "name": "a"}],
                  ["b", {"state": "match", "name": "a"}],
                  ["a", None], ["a", {"state": "unsaved"}]],
    }
    r = subprocess.run([_NODE, "-e", _ENGINEER, str(_WEB / "i18n.js"),
                        str(_WEB / "engineer.js"), lang],
                       input=json.dumps(body), capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_engineer_page_texts_and_bodies():
    out = _eng("it")
    assert out["text"] == [None, "In macchina c'è HONE_8.",
                           "In macchina c'è probabilmente HONE_8.",
                           "Assetto non salvato", "Non riconosciuto", "Non riconosciuto"]
    assert out["warn"] == ["In macchina c'è a, stai modificando b.", None, None, None, None]
    assert out["label"] == ["a · in macchina", "b", "a", "a"]
    bodies = {s["url"].rsplit("/", 1)[-1]: s["body"] for s in out["sent"]}
    assert json.loads(bodies["applied"]) == {"path": "S/HONE_2.json"}
    assert json.loads(bodies["base"]) == {"path": "S/base.json"}


@needs_node
def test_engineer_page_texts_in_english():
    out = _eng("en")
    assert out["text"][1] == "The car has HONE_8."
    assert out["label"][0] == "a · in the car"


def test_the_other_applied_calls_of_the_page_stay_empty():
    src = (_WEB / "engineer.js").read_text(encoding="utf-8")
    assert src.count("}/engineer/applied`") == 3
    assert src.count('body: "{}"') == 2


def test_the_pages_have_the_places_for_the_new_lines():
    eng = (_WEB / "engineer.html").read_text(encoding="utf-8")
    for i in ("es-loaded", "es-carry", "setup-warn"):
        assert f'id="{i}"' in eng, i
    tab = (_WEB / "tablet.html").read_text(encoding="utf-8")
    for i in ("t-loaded", "t-carry", "t-warn"):
        assert f'id="{i}"' in tab, i


def test_guide_and_faq_explain_the_three_answers():
    # GUIDA.md e' la guida italiana, docs/FAQ.md quella inglese.
    for name, heading, needles in (
            ("GUIDA.md", "### L'Ingegnere riconosce l'assetto ai box",
             ("In macchina c'è", "Assetto non salvato", "Non riconosciuto", "· in macchina",
              "pressioni", "non propone modifiche ai box", "niente da confrontare")),
            ("docs/FAQ.md", "### The engineer recognises the setup in the pits",
             ("The car has", "Setup not saved", "Not recognised", "· in the car"))):
        text = (_ROOT / name).read_text(encoding="utf-8")
        assert heading in text, name
        section = text.split(heading, 1)[1].split("\n### ", 1)[0]
        for needle in needles:
            assert needle in section, (name, needle)
