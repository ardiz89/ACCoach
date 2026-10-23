"""La pagina Ingegnere non scrive l'assetto mentre stai guidando.

Scrivere manda `/engineer/applied`, e da li' l'ingegnere conta i giri di
verifica. In pista l'assetto nuovo non e' sulla macchina (si carica dal
garage): i giri sarebbero contati con quello vecchio e il verdetto sbagliato.
La vista tablet lo sapeva dal 23/10, la pagina completa no.

La regola: si blocca solo se l'ultimo frame dice «stai guidando e non sei fermo
ai box». Senza frame, gioco spento/menu o ai box si scrive come sempre, perche'
la pagina serve anche per preparare un assetto senza guidare.

I test eseguono il vero `engineer.js` in node, con un `fetch` finto che conta.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(_NODE is None, reason="serve node")

_HARNESS = r"""
const fs = require("fs");
const [i18nPath, engPath, lang] = process.argv.slice(2);
global.window = {}; window.HONE_LANG = lang;
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
var WS_PORT = 8777, AUTO_PREFIX = "HONE";
// La porta verso il motore vera: senza lankey.js lascia l'URL com'e'.
eval(asVar(line(/^const liveUrl = /)));
var location = { hostname: "pc" };
const els = {};
var $ = (id) => els[id] || (els[id] = { dataset: {}, hidden: false, disabled: false, textContent: "", innerHTML: "", value: "HONE_9" });
var state = { setupPath: "p", pending: { x: 1 }, lastLive: null };
const calls = [];
var fetch = (url, o) => { calls.push(url); return Promise.resolve({}); };
var api = async (url) => { calls.push(url); return { name: "HONE_1", reload_hint: "h" }; };
var changesPayload = () => [{ param: "a", slot: null, delta_clicks: 1 }];
var nextAutoName = () => "HONE_1";
var onComboChange = async () => {};
var showToast = () => {};
var setTimeout = () => {}, connectWS = () => {};
var showModalError = (m) => { els["modal-error"] = { textContent: m }; };
for (const f of ["liveRefused", "inPista", "writeLocked", "paintWriteLock", "afterWrite", "applyNow",
                 "confirmWrite", "confirmRestored", "confirmAvDone", "onWsClose", "probeKey"]) {
  eval(grab(f));
}
(async () => {
  const out = [];
  for (const sc of JSON.parse(fs.readFileSync(0, "utf8"))) {
    calls.length = 0;
    state.lastLive = sc.frame; state.pending = { x: 1 };
    for (const id of ["btn-apply", "btn-write", "modal-ok", "es-restored", "write-lock"]) {
      els[id] = { hidden: false, disabled: false, textContent: "" };
    }
    if (sc.close) onWsClose();
    paintWriteLock();
    const painted = {
      apply: els["btn-apply"].disabled, write: els["btn-write"].disabled,
      ok: els["modal-ok"].disabled, restored: els["es-restored"].disabled,
      line: els["write-lock"].hidden ? "" : els["write-lock"].textContent,
    };
    await applyNow(); const a = calls.slice(); calls.length = 0;
    await confirmWrite(); const w = calls.slice(); calls.length = 0;
    confirmRestored(); const r = calls.slice(); calls.length = 0;
    confirmAvDone(); const d = calls.slice();
    out.push({ painted, applyNow: a, confirmWrite: w, restored: r, avDone: d });
  }
  console.log(JSON.stringify(out));
})();
"""

IN_PISTA = {"connected": True, "status": "LIVE", "at_box": False}
AI_BOX = {"connected": True, "status": "LIVE", "at_box": True}
PAUSA = {"connected": True, "status": "PAUSE", "at_box": False}
MENU = {"connected": True, "status": "OFF", "at_box": False}
REPLAY = {"connected": True, "status": "REPLAY", "at_box": False}
SPENTO = {"connected": False}


def _run(tmp_path, lang, *frames, close=False):
    script = tmp_path / "h.js"
    script.write_text(_HARNESS, encoding="utf-8")
    run = subprocess.run(
        [_NODE, str(script), str(_WEB / "i18n.js"), str(_WEB / "engineer.js"), lang],
        input=json.dumps([{"frame": f, "close": close} for f in frames]), capture_output=True,
        text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _writes(r):
    return [u for u in r["applyNow"] + r["confirmWrite"] if "/api/setup/apply" in u]


def _applied(urls):
    return [u for u in urls if u.endswith("/engineer/applied")]


def test_on_track_nothing_is_written_nor_announced(tmp_path):
    (r,) = _run(tmp_path, "it", IN_PISTA)
    assert r["applyNow"] == [] and r["confirmWrite"] == []
    assert r["restored"] == []


def test_on_track_the_buttons_are_off_with_a_line_that_says_why(tmp_path):
    (r,) = _run(tmp_path, "it", IN_PISTA)
    p = r["painted"]
    assert p["apply"] and p["write"] and p["ok"] and p["restored"]
    assert p["line"] == "Il file lo scrivi quando sei fermo ai box."
    (en,) = _run(tmp_path, "en", IN_PISTA)
    assert en["painted"]["line"] == "You write the file when you're stopped in the pits."


def test_a_pause_on_track_still_counts_as_driving(tmp_path):
    """In pausa ACC sei fermo in pista, non ai box: l'assetto non si carica."""
    (r,) = _run(tmp_path, "it", PAUSA)
    assert r["applyNow"] == [] and r["restored"] == []
    assert r["painted"]["apply"]


def test_at_the_box_it_writes_and_tells_the_engine(tmp_path):
    (r,) = _run(tmp_path, "it", AI_BOX)
    assert not any(r["painted"][k] for k in ("apply", "write", "ok", "restored"))
    assert r["painted"]["line"] == ""
    assert len(_writes(r)) == 2
    assert len(_applied(r["applyNow"])) == 1 and len(_applied(r["confirmWrite"])) == 1
    assert len(_applied(r["restored"])) == 1


@pytest.mark.parametrize("frame", [None, SPENTO, MENU, REPLAY])
def test_without_a_driving_frame_it_writes_as_before(tmp_path, frame):
    """La pagina serve anche per preparare un assetto col gioco spento o nei menu."""
    (r,) = _run(tmp_path, "it", frame)
    assert not any(r["painted"][k] for k in ("apply", "write", "ok", "restored"))
    assert len(_writes(r)) == 2
    assert len(_applied(r["restored"])) == 1


def test_the_dial_button_still_tells_the_engine_on_track(tmp_path):
    """`av-done` e' la modifica fatta guidando: avvisare subito e' giusto."""
    (r,) = _run(tmp_path, "it", IN_PISTA)
    assert len(_applied(r["avDone"])) == 1


def test_when_the_engine_goes_away_the_buttons_unlock(tmp_path):
    """Ultimo frame «in pista», poi il WebSocket cade (motore fermo, gioco
    chiuso): senza frame si scrive come sempre, non si resta bloccati."""
    (r,) = _run(tmp_path, "it", IN_PISTA, close=True)
    assert not any(r["painted"][k] for k in ("apply", "write", "ok", "restored"))
    assert r["painted"]["line"] == ""
    assert len(_writes(r)) == 2


# Il guardiano chiude il WebSocket senza dire perche': alla chiusura la pagina
# chiede /health alla 8777, e un 401 (la chiave che manca) si dice sul
# distintivo invece di «offline». Motore spento resta «offline».
_PROBE = r"""
const fs = require("fs");
const [i18nPath, engPath, status] = process.argv.slice(2);
global.window = {}; window.HONE_LANG = "it";
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(i18nPath, "utf8"));
const src = fs.readFileSync(engPath, "utf8");
const line = (re) => src.split("\n").find((l) => re.test(l));
eval(line(/^const t = /).replace(/^const /, "var "));
eval(line(/^const liveUrl = /).replace(/^const /, "var "));
var WS_PORT = 8777, location = { hostname: "pc" };
const els = {};
var $ = (id) => els[id] || (els[id] = { dataset: {}, textContent: "" });
var state = { lastLive: null };
const asked = [];
var fetch = (url) => { asked.push(url); return status === "off"
  ? Promise.reject(new Error("off")) : Promise.resolve({ status: Number(status) }); };
var paintWriteLock = () => {}, setTimeout = () => {}, connectWS = () => {};
for (const name of ["onWsClose", "probeKey"]) {
  const i = src.indexOf("function " + name + "(");
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) { eval(src.slice(i, k + 1)); break; } }
  }
}
onWsClose();
setImmediate(() => console.log(JSON.stringify({ asked, text: $("live-text").textContent })));
"""


@pytest.mark.parametrize("status, text", [
    ("401", "Apri HONE dal codice QR dell'hub."),
    ("off", "telemetria offline"),
])
def test_a_websocket_refused_for_the_key_says_so_on_the_badge(tmp_path, status, text):
    script = tmp_path / "p.js"
    script.write_text(_PROBE, encoding="utf-8")
    run = subprocess.run([_NODE, str(script), str(_WEB / "i18n.js"),
                          str(_WEB / "engineer.js"), status],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["asked"] == ["http://pc:8777/health"]
    assert out["text"] == text
