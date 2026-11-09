"""L'Ingegnere chiede su quale assetto lavora.

Il test dell'08/11 (ACC, 720S, Imola): a inizio sessione `/api/setup/base` non
aveva un `last_written` e proponeva il file piu' recente per data, `HONE_2`
(65/60 sugli anteriori). Il pilota guidava quasi certamente `720sEVO_Imola_0`
(57/52). `HONE_3` ha alzato gli anteriori di 13 click invece di 5: a caldo
25,8 → 28,0 psi, contro +0,5 previsti.

Due rimedi. Il primo file si sceglie, non si propone: la tendina parte vuota
e il tasto per scrivere resta spento. E la risposta delle gomme si controlla:
quando si chiude la prova di una pressione, uno spostamento a caldo lontano da
quello previsto vuol dire che la base non era quella, e la pagina richiede.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from accoach.engine import CoachEngine
from accoach.engineer import Decision, DecisionKind, LapStats, RaceEngineer
from accoach.engineer.core import FRONT, AtomicChange, ProposedChange
from accoach.engineer.profiles import GT3_PROFILE
from accoach import config
from accoach.telemetry.snapshot import TelemetrySnapshot
from test_tablet_box import _BOX_HARNESS

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="serve node")


# --- il motore: la risposta delle gomme -------------------------------------

def _lap(front, time_ms=100000):
    return LapStats(lap_time_ms=time_ms, stable=True,
                    pressures_hot={"front": front, "rear": 26.9})


def _test_pressure(clicks, before, after, time_after=100000):
    """Una prova di pressione sugli anteriori: base a `before`, poi `after`."""
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng.window = [_lap(before) for _ in range(3)]
    eng._pending = ProposedChange(
        changes=tuple(AtomicChange("tyrePressure", s, clicks) for s in FRONT),
        rationale="Pressione anteriore.", phase_label="Pressioni", tag="BOX")
    eng.mark_applied()
    d = None
    for _ in range(3):
        d = eng.observe(_lap(after, time_after))
    return eng, d


@pytest.fixture(autouse=True)
def _italiano(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


def test_0811_predicted_plus_half_measured_plus_2_2_asks_for_the_base():
    """HONE_3: +5 click (0,1 psi l'uno) previsti +0,5, misurati +2,2."""
    _, d = _test_pressure(5, 25.8, 28.0)
    assert d.kind is DecisionKind.ACCEPTED
    assert d.confirm_base is True
    assert "+2,2 psi" in d.message and "+0,5 psi" in d.message
    assert "anteriori" in d.message
    assert "Quale assetto hai caricato" not in d.message   # la domanda la fa la pagina
    assert "ai box" in d.message.lower()


@pytest.mark.parametrize("measured_after", [25.3, 25.2])
def test_0811_predicted_minus_0_8_measured_minus_half_or_0_6_is_fine(measured_after):
    """Previsto −0,8, misurato −0,5 o −0,6: le gomme hanno risposto."""
    _, d = _test_pressure(-8, 25.8, measured_after)
    assert d.kind is DecisionKind.ACCEPTED
    assert d.confirm_base is False
    assert "psi" not in d.message


def test_the_tolerance_is_never_below_0_8_psi():
    """Un click (+0,1) e la gomma si muove di +0,8: dentro, non scatta.
    Di +0,95 invece sì: 0,85 di scarto supera 0,8."""
    assert _test_pressure(1, 25.0, 25.8)[1].confirm_base is False
    assert _test_pressure(1, 25.0, 25.95)[1].confirm_base is True


def test_without_hot_pressures_nothing_is_said():
    eng = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng.window = [LapStats(lap_time_ms=100000) for _ in range(3)]
    eng._pending = ProposedChange(
        changes=tuple(AtomicChange("tyrePressure", s, 5) for s in FRONT),
        rationale="Pressione anteriore.", phase_label="Pressioni", tag="BOX")
    eng.mark_applied()
    for _ in range(3):
        d = eng.observe(LapStats(lap_time_ms=100000))
    assert d.confirm_base is False


def test_a_held_restore_keeps_asking_lap_after_lap():
    """Un giro piu' lento boccia la prova: il ripristino tenuto porta la
    domanda anche ai giri dopo, perche' e' lo stesso verdetto."""
    eng, d = _test_pressure(5, 25.8, 28.0, time_after=103000)
    assert d.kind is DecisionKind.REVERTED and d.confirm_base is True
    again = eng.observe(_lap(28.0))
    assert again is d


def test_english_message():
    config.set_language("en")
    _, d = _test_pressure(5, 25.8, 28.0)
    assert "+2.2 psi" in d.message and "+0.5 psi" in d.message
    assert "front" in d.message


class _Dead:
    def read(self):
        return TelemetrySnapshot.disconnected()

    def close(self):
        pass


def test_the_live_frame_carries_confirm_base(tmp_path):
    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path, engineer_voice=False)
    try:
        eng._engineer = RaceEngineer(GT3_PROFILE, min_stable=3)
        eng._engineer_decision = Decision(DecisionKind.ACCEPTED, "x", confirm_base=True)
        assert eng._engineer_block()["confirm_base"] is True
        eng._engineer_decision = Decision(DecisionKind.ACCEPTED, "x")
        assert eng._engineer_block()["confirm_base"] is False
    finally:
        eng.close()


# --- il tablet ---------------------------------------------------------------

# Come nel DOM vero, `innerHTML = ""` toglie i figli: la tendina si rifa' da
# capo, e la voce vuota deve stare in cima a quella nuova.
_HEAD = _BOX_HARNESS.split("window.HoneTablet.render(frame);\nreply(")[0].replace(
    "El.prototype.setAttribute",
    'Object.defineProperty(El.prototype, "innerHTML", {configurable: true,\n'
    '  set: function (v) { this.children = []; this._html = v; },\n'
    '  get: function () { return this._html || ""; }});\n'
    "El.prototype.setAttribute", 1)
_SETUPS = r"""
var SETUPS = [{name: "HONE_2", path: "S/HONE_2.json", mtime: 3},
              {name: "720sEVO_Imola_0", path: "S/i0.json", mtime: 1}];
function pv(x) {
  reply(x, 200, {ok: true, errors: [], diff: [
    {group: "Gomme", label: "Pressione", slot: "FL", old_click: 57, new_click: 62,
     delta: 5, old_phys: "26 psi", new_phys: "26.5 psi"}]});
}
function opts() {
  return $("t-base").children.map(function (o) { return [o.value, !!o.selected]; });
}
"""


def _tablet(body):
    r = subprocess.run([_NODE, "-e", _HEAD + _SETUPS + body + "\nprocess.stdout.write(JSON.stringify(out));",
                        str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_tablet_the_first_file_is_chosen_not_proposed():
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, {car: "mclaren", track: "Imola", setups: SETUPS,
  base: null, last_written: null, confirm: true});
window.HoneTablet.render(frame);
out.ask = !$("t-ask").hidden;
out.askText = $("t-ask").textContent;
out.opts = opts();
out.writeOff = $("t-write").disabled;
out.previews = find("/api/setup/preview").length;
$("t-write").onclick();
out.confirmOpen = !$("t-confirm").hidden;
$("t-base").value = "S/i0.json";
$("t-base").onchange();
window.HoneTablet.render(frame);
out.previewPath = JSON.parse(find("/api/setup/preview")[0].body).path;
pv(find("/api/setup/preview")[0]);
window.HoneTablet.render(frame);
out.askAfter = !$("t-ask").hidden;
out.writeOn = !$("t-write").disabled;
""")
    assert out["ask"] is True
    assert out["askText"] == "Quale assetto hai caricato in ACC?"
    # La tendina parte vuota: la prima voce non e' un file ed e' quella scelta.
    assert out["opts"][0] == ["", True]
    assert [v for v, _ in out["opts"][1:]] == ["S/HONE_2.json", "S/i0.json"]
    assert out["writeOff"] is True
    assert out["previews"] == 0
    assert out["confirmOpen"] is False
    assert out["previewPath"] == "S/i0.json"
    assert out["askAfter"] is False
    assert out["writeOn"] is True


@needs_node
def test_tablet_with_last_written_nothing_changes():
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, {car: "mclaren", track: "Imola", setups: SETUPS,
  base: "S/HONE_2.json", last_written: "HONE_2", confirm: false});
window.HoneTablet.render(frame);
out.ask = !$("t-ask").hidden;
out.opts = opts();
out.previewPath = JSON.parse(find("/api/setup/preview")[0].body).path;
""")
    assert out["ask"] is False
    assert out["opts"] == [["S/HONE_2.json", True], ["S/i0.json", False]]
    assert out["previewPath"] == "S/HONE_2.json"


@needs_node
def test_tablet_confirm_base_asks_again_once():
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, {car: "mclaren", track: "Imola", setups: SETUPS,
  base: "S/HONE_2.json", last_written: "HONE_2", confirm: false});
window.HoneTablet.render(frame);
pv(find("/api/setup/preview")[0]);
window.HoneTablet.render(frame);
out.before = !$("t-ask").hidden;
// La prova si chiude: le gomme non hanno risposto come previsto.
var verdict = {connected: true, at_box: true, car: "mclaren", track: "Imola",
  engineer: {kind: "reverted", tag: "BOX", confirm_base: true,
             message: "Le gomme anteriori si sono mosse di +2,2 psi.",
             change: [{param: "tyrePressure", slot: null, delta_clicks: -5}]}};
window.HoneTablet.render(verdict);
out.ask = !$("t-ask").hidden;
out.opts = opts();
out.writeOff = $("t-write").disabled;
var n = find("/api/setup/preview").length;
$("t-base").value = "S/i0.json";
$("t-base").onchange();
window.HoneTablet.render(verdict);
out.previewPath = JSON.parse(find("/api/setup/preview")[n].body).path;
// Lo stesso verdetto torna a ogni frame: non si richiede.
window.HoneTablet.render(verdict);
out.askAgain = !$("t-ask").hidden;
""")
    assert out["before"] is False
    assert out["ask"] is True
    assert out["opts"][0] == ["", True]
    assert out["writeOff"] is True
    assert out["previewPath"] == "S/i0.json"
    assert out["askAgain"] is False


@needs_node
def test_tablet_confirm_base_seen_on_track_waits_for_the_box():
    """Il verdetto arriva a fine giro, in pista e su Telemetria: la domanda
    c'e' lo stesso quando ti fermi, anche se il frame dopo non la porta piu'."""
    out = _tablet(r"""
window.HoneTablet.render(frame);
reply(find("/api/setup/base")[0], 200, {car: "mclaren", track: "Imola", setups: SETUPS,
  base: "S/HONE_2.json", last_written: "HONE_2", confirm: false});
window.HoneTablet.render(frame);
window.HoneTablet.render({connected: true, at_box: false, car: "mclaren", track: "Imola",
  engineer: {kind: "accepted", confirm_base: true, message: "Le gomme...", change: null}});
window.HoneTablet.render({connected: true, at_box: false, car: "mclaren", track: "Imola",
  engineer: {kind: "collect", message: "Servono 3 giri.", change: null}});
window.HoneTablet.render(frame);
var b = find("/api/setup/base");
if (b[b.length - 1].readyState !== 4) reply(b[b.length - 1], 200, {car: "mclaren", track: "Imola",
  setups: SETUPS, base: "S/HONE_2.json", last_written: "HONE_2", confirm: false});
window.HoneTablet.render(frame);
out.ask = !$("t-ask").hidden;
out.opts = opts();
""")
    assert out["ask"] is True
    assert out["opts"][0] == ["", True]


# --- la pagina Ingegnere -----------------------------------------------------

_ENG = r"""
const fs = require("fs");
const [i18nPath, engPath, lang] = process.argv.slice(1);
global.window = {}; window.HONE_LANG = lang;
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {},
                    createElement: () => { const o = { dataset: {}, textContent: "", selected: false };
                      Object.defineProperty(o, "value", {
                        get() { return this._v !== undefined ? this._v : this.textContent; },
                        set(v) { this._v = v; } });
                      return o; } };
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
eval(asVar(line(/^const noSetupHTML = /)));
const els = {};
function select() {
  return { options: [], dataset: {},
    appendChild(o) { this.options.push(o); return o; },
    set innerHTML(v) { this.options = []; }, get innerHTML() { return ""; },
    get selectedOptions() {
      const s = this.options.find((o) => o.selected) || this.options[0];
      return s ? [s] : []; },
    set value(v) { this.options.forEach((o) => { o.selected = o.value === v; }); },
    get value() { const s = this.selectedOptions[0]; return s ? s.value : ""; } };
}
els.setup = select();
els.combo = { selectedOptions: [{ dataset: { car: "mclaren", track: "Imola" } }] };
var $ = (id) => els[id] || (els[id] = { dataset: {}, hidden: false, disabled: false,
                                         textContent: "", innerHTML: "" });
var state = { car: null, track: null, setupPath: null, params: [], base: {}, pending: {},
              lastLive: null };
var LIST = [], BASE = null, CURRENT = null;
const asked = [];
var api = async (url) => {
  asked.push(url);
  if (url.indexOf("/api/setup/list") === 0) return LIST;
  if (url.indexOf("/api/setup/base") === 0) return BASE;
  if (url.indexOf("/api/setup/current") === 0) return CURRENT;
  throw new Error(url);
};
var loadClass = async () => {}, loadRecord = () => {}, renderSetup = () => {},
    renderTray = () => {}, showToast = () => {}, dn = (s) => s;
for (const f of ["onComboChange", "fillSetups", "esc", "askBaseText", "askBaseHTML", "onSetupChange", "askAgain",
                 "inPista", "writeLocked", "paintWriteLock"]) {
  eval(grab(f));
}
function snap() {
  paintWriteLock();
  // Una voce si riconosce dal file che porta (`dataset.path`); la domanda non
  // ne porta nessuno.
  return { opts: els.setup.options.map((o) => [o.dataset.path || "", !!o.selected]),
           path: state.setupPath, body: $("setup-body").innerHTML,
           apply: $("btn-apply").disabled, write: $("btn-write").disabled,
           ok: $("modal-ok").disabled, restored: $("es-restored").disabled };
}
(async () => {
  const sc = JSON.parse(fs.readFileSync(0, "utf8"));
  LIST = sc.list; BASE = sc.base;
  CURRENT = { name: "x", car: "mclaren", has_backup: false, params: [], groups: [] };
  const out = {};
  await onComboChange(sc.prefer);
  out.start = snap();
  out.askedBase = asked.filter((u) => u.indexOf("/api/setup/base") === 0).length;
  if (sc.pick) {
    els.setup.value = sc.pick;
    await onSetupChange();
    out.picked = snap();
  }
  if (sc.again) {
    await askAgain();
    out.again = snap();
  }
  console.log(JSON.stringify(out));
})();
"""

_LIST = [{"name": "720sEVO_Imola_0", "path": "S/i0.json", "mtime": 1},
         {"name": "HONE_2", "path": "S/HONE_2.json", "mtime": 3}]


def _engineer(**sc):
    sc.setdefault("prefer", None)
    r = subprocess.run([_NODE, "-e", _ENG, str(_WEB / "i18n.js"), str(_WEB / "engineer.js"), "it"],
                       input=json.dumps(dict({"list": _LIST}, **sc)), capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_engineer_page_asks_for_the_first_file():
    out = _engineer(base={"base": None, "last_written": None, "confirm": True,
                          "setups": []}, pick="720sEVO_Imola_0")
    s = out["start"]
    # La domanda in cima, scelta; poi i file dal piu' recente.
    assert s["opts"][0][1] is True and s["opts"][0][0] == ""
    assert [v for v, _ in s["opts"][1:]] == ["S/HONE_2.json", "S/i0.json"]
    assert s["path"] is None
    assert "Quale assetto hai caricato in ACC?" in s["body"]
    assert s["apply"] and s["write"] and s["ok"]
    assert s["restored"] is False          # «L'ho già rimesso» non scrive niente
    p = out["picked"]
    assert p["path"] == "S/i0.json"
    assert not (p["apply"] or p["write"] or p["ok"])


@needs_node
def test_engineer_page_with_last_written_selects_it():
    out = _engineer(base={"base": "S/HONE_2.json", "last_written": "HONE_2",
                          "confirm": False, "setups": []})
    s = out["start"]
    assert s["path"] == "S/HONE_2.json"
    assert all(v for v, _ in s["opts"])
    assert not s["apply"]


@needs_node
def test_engineer_page_after_a_write_does_not_ask():
    """`afterWrite` passa il nome scritto: e' quello, senza domanda."""
    out = _engineer(prefer="HONE_2", base={"confirm": True})
    assert out["askedBase"] == 0
    assert out["start"]["path"] == "S/HONE_2.json"


@needs_node
def test_engineer_page_confirm_base_asks_again():
    out = _engineer(base={"base": "S/HONE_2.json", "last_written": "HONE_2",
                          "confirm": False, "setups": []}, again=True)
    a = out["again"]
    assert a["opts"][0] == ["", True]
    assert a["path"] is None
    assert a["apply"] and a["write"]


def test_engineer_page_reads_confirm_base_from_the_frame():
    src = (_WEB / "engineer.js").read_text(encoding="utf-8")
    body = src[src.index("function renderEngineer("):]
    body = body[:body.index("\n}")]
    assert "confirm_base" in body and "askAgain" in body


def test_strings_in_both_languages():
    cat = (_WEB / "i18n.js").read_text(encoding="utf-8")
    for key in ('"tablet.askBase"', '"eng.askBaseBody"'):
        block = cat[cat.index(key):][:400]
        assert "en:" in block and "it:" in block, key
    assert "Quale assetto hai caricato in ACC?" in cat
    assert 'id="t-ask"' in (_WEB / "tablet.html").read_text(encoding="utf-8")
