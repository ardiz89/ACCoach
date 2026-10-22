"""La schermata dei box della vista tablet e il bottone che scrive la modifica.

Il nome del file nuovo e le leve che si mandano li decide `tablet.js` (provato in
node, sullo stesso file che la pagina carica); la scrittura passa dagli
endpoint `/api/setup/*` della pagina completa. L'ultimo test fa a mano la
sequenza della pagina contro l'API vera: e' la prova che il file di partenza
(Task 2) e il bottone (Task 5) parlano lo stesso contratto.
"""
import json
import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from accoach.api import create_api
from test_setup_api import CAR, SAMPLE, TRACK
from test_tablet_page import _NODE, _call, needs_node

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"


@needs_node
def test_next_name():
    assert _call("nextName", [[[]], [["base", "HONE_1", "hone_3"]], [["HONE_x"]]]) \
        == ["HONE_1", "HONE_4", "HONE_1"]


@needs_node
def test_changes_for():
    eng = {"change": [{"param": "tyrePressure", "slot": None, "delta_clicks": 2}]}
    assert _call("changesFor", [[eng]]) == [
        [{"param": "tyrePressure", "slot": 0, "delta_clicks": 2}]]


def test_write_path_in_source():
    src = (_WEB / "tablet.js").read_text(encoding="utf-8")
    for needle in ("/api/setup/apply", "confirm: true", "/engineer/applied",
                   "already exists"):
        assert needle in src, needle
    # Il doppio tocco: il bottone di conferma si spegne PRIMA della richiesta,
    # non nella sua risposta.
    m = re.search(r"\$\(\"t-confirm-ok\"\)\.disabled\s*=\s*true", src)
    assert m, "il bottone di conferma non si spegne"
    assert m.start() < src.index('"/api/setup/apply"')


@needs_node
def test_box_write_end_to_end(tmp_path):
    setups_root = tmp_path / "Setups"
    d = setups_root / CAR / TRACK
    d.mkdir(parents=True)
    (d / "base.json").write_text(json.dumps(SAMPLE, indent="\t"), encoding="utf-8")
    c = TestClient(create_api(tmp_path / "laps", setups_root=setups_root))

    # Il gioco scrive auto e pista come vuole: la pagina le manda come arrivano.
    base = c.get("/api/setup/base", params={"car": CAR.upper(), "track": TRACK.lower()}).json()
    assert base["base"] and base["last_written"] is None

    eng = {"kind": "propose", "tag": "BOX",
           "change": [{"param": "tyrePressure", "slot": None, "delta_clicks": 2}]}
    changes = _call("changesFor", [[eng]])[0]
    prev = c.post("/api/setup/preview", params={"lang": "it"},
                  json={"path": base["base"], "changes": changes}).json()
    assert prev["ok"], prev
    assert prev["diff"][0]["new_click"] == prev["diff"][0]["old_click"] + 2

    name = _call("nextName", [[[s["name"] for s in base["setups"]]]])[0]
    r = c.post("/api/setup/apply", params={"lang": "it"},
               json={"path": base["base"], "as_name": name, "confirm": True,
                     "changes": changes})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "HONE_1" and r.json()["reload_hint"]

    written = json.loads((d / "HONE_1.json").read_text(encoding="utf-8"))
    assert written["basicSetup"]["tyres"]["tyrePressure"][0] == 59

    after = c.get("/api/setup/base", params={"car": CAR, "track": TRACK}).json()
    assert after["last_written"] == "HONE_1"
    assert Path(after["base"]).name == "HONE_1.json"
    # Il prossimo nome e' il successivo: la pagina non riscrive sopra HONE_1.
    assert _call("nextName", [[[s["name"] for s in after["setups"]]]])[0] == "HONE_2"


# La pagina vera in node: i18n.js + tablet.js con un DOM finto che basta al
# flusso dei box, e un XMLHttpRequest che non risponde finche' il test non lo
# dice. Cosi' il doppio tocco si prova sulla funzione che il bottone chiama
# (l'`onclick` montato da `boot`), mentre la richiesta e' ancora in volo.
_BOX_HARNESS = r"""
var fs = require("fs");
var els = {}, ready = false;
function El(tag) {
  this.tagName = tag; this.children = []; this.attrs = {};
  this.textContent = ""; this.innerHTML = ""; this.hidden = false;
  this.disabled = false; this.value = ""; this.className = ""; this.offsetWidth = 0;
}
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return this.attrs.hasOwnProperty(k) ? this.attrs[k] : null; };
El.prototype.removeAttribute = function (k) { delete this.attrs[k]; };
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
var window = {HONE_LANG: "it", addEventListener: function () {}};
var location = {hostname: "pc"};
var document = {readyState: "complete",
  querySelectorAll: function () { return []; },
  querySelector: function () { return null; },
  getElementById: function (id) {
    if (!ready) return null;
    return els[id] || (els[id] = new El("div"));
  },
  createElement: function (tag) { return new El(tag); },
  createTextNode: function (s) { return {textContent: s}; },
  documentElement: {}};
function WebSocket() { return {}; }
var sent = [];
function XMLHttpRequest() { this.readyState = 0; this.status = 0; this.responseText = ""; }
XMLHttpRequest.prototype.open = function (m, u) { this.method = m; this.url = u; };
XMLHttpRequest.prototype.setRequestHeader = function () {};
XMLHttpRequest.prototype.send = function (b) { this.body = b; sent.push(this); };
function reply(x, status, obj) {
  x.readyState = 4; x.status = status; x.responseText = JSON.stringify(obj);
  x.onreadystatechange();
}
function find(path) {
  var out = [];
  for (var i = 0; i < sent.length; i++) if (sent[i].url.indexOf(path) !== -1) out.push(sent[i]);
  return out;
}
eval(fs.readFileSync(process.argv[1], "utf8"));
ready = true;
eval(fs.readFileSync(process.argv[2], "utf8"));
var $ = document.getElementById;

var frame = {connected: true, at_box: true, car: "mclaren", track: "Imola",
  engineer: {kind: "propose", tag: "BOX", confidence: "medium",
             change: [{param: "tyrePressure", slot: null, delta_clicks: 2}]}};
var out = {};
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, {car: "mclaren", track: "Imola",
  setups: [{name: "base", path: "S/base.json", mtime: 1},
           {name: "HONE_1", path: "S/HONE_1.json", mtime: 2}],
  base: "S/HONE_1.json", last_written: null});
window.HoneTablet.render(frame);
reply(find("/api/setup/preview")[0], 200, {ok: true, errors: [], diff: [
  {group: "Gomme", label: "Pressione", slot: "FL", old_click: 57, new_click: 59,
   delta: 2, old_phys: "26 psi", new_phys: "26.2 psi"},
  {group: "Allineamento", label: "Campanatura", slot: "FL", old_click: 0, new_click: 5,
   delta: 5, old_phys: "-4 deg", new_phys: "-3.5 deg"}]});
window.HoneTablet.render(frame);
out.levers = $("t-levers").children.map(function (li) {
  return li.children.map(function (c) { return c.textContent; }).join("");
});

$("t-write").onclick();
out.confirmHidden = $("t-confirm").hidden;
// Il doppio tocco, con la prima richiesta ancora senza risposta.
$("t-confirm-ok").onclick();
window.HoneTablet.render(frame);
$("t-confirm-ok").onclick();
out.disabledInFlight = $("t-confirm-ok").disabled;
out.afterDoubleTap = find("/api/setup/apply").length;
// Il disco ha gia' quei nomi: ogni risposta e' un 409 «already exists».
var names = [];
for (var n = 0; n < 6; n++) {
  var reqs = find("/api/setup/apply");
  if (reqs.length <= n) break;
  var body = JSON.parse(reqs[n].body);
  names.push(body.as_name);
  reply(reqs[n], 409, {detail: body.as_name + ".json already exists (use overwrite=True or a new name)"});
}
out.names = names;
out.applyTotal = find("/api/setup/apply").length;
out.applied = find("/engineer/applied").length;
out.err = $("t-err").textContent;
out.okEnabledAgain = !$("t-confirm-ok").disabled;
// Il lavoro di prima: sulla base che la schermata nomina, con la conferma.
out.firstBody = JSON.parse(find("/api/setup/apply")[0].body);
out.lang = find("/api/setup/apply")[0].url;
process.stdout.write(JSON.stringify(out));
"""


@needs_node
def test_double_tap_writes_once_and_409_tries_the_next_name_four_times():
    r = subprocess.run([_NODE, "-e", _BOX_HARNESS, str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    # Il valore fisico con la regola dei numeri della pagina (fmtNum).
    # I due valori coi decimali del piu' preciso; i click col segno.
    assert out["levers"] == ["Pressione FL 26,0 psi → 26,2 psi (+2 click)",
                             "Campanatura FL −4,0 deg → −3,5 deg (+5 click)"]
    assert out["confirmHidden"] is False
    assert out["disabledInFlight"] is True
    assert out["afterDoubleTap"] == 1
    assert out["names"] == ["HONE_2", "HONE_3", "HONE_4", "HONE_5"]
    assert out["applyTotal"] == 4
    assert out["applied"] == 0           # niente scritto, il motore non si avvisa
    assert "HONE_5" in out["err"]
    assert out["okEnabledAgain"] is True
    assert out["firstBody"] == {"path": "S/HONE_1.json", "as_name": "HONE_2", "confirm": True,
                                "changes": [{"param": "tyrePressure", "slot": 0,
                                             "delta_clicks": 2}]}
    assert "lang=it" in out["lang"]


@needs_node
def test_a_base_list_error_says_what_failed():
    harness = _BOX_HARNESS.split("window.HoneTablet.render(frame);\nreply(")[0] + r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 500, {detail: "boom"});
window.HoneTablet.render(frame);
process.stdout.write(JSON.stringify({err: $("t-err").textContent, hidden: $("t-err").hidden}));
"""
    r = subprocess.run([_NODE, "-e", harness, str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out == {"err": "Non riesco a caricare i setup. boom", "hidden": False}
