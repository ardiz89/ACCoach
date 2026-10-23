"""Le linguette Telemetria e Assetto della vista tablet (spec «Le linguette»).

La regola che sceglie la linguetta (`pickTab`) si prova pura in node, sullo
stesso `tablet.js` che la pagina carica; il resto con il DOM finto di
`test_tablet_box.py`, sulla funzione che il dito chiama davvero (l'`onclick`
montato da `boot`).
"""
import json
import re
import subprocess
from pathlib import Path

from test_tablet_box import _BOX_HARNESS
from test_tablet_page import _NODE, _call, needs_node

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"

_TRACK = {"connected": True, "at_box": False}
_BOX = {"connected": True, "at_box": True}


@needs_node
def test_the_first_frame_picks_by_where_the_car_is():
    assert _call("pickTab", [[None, _TRACK, None], [None, _BOX, None]]) == ["track", "setup"]


@needs_node
def test_a_tap_holds_until_the_box_state_changes():
    # Review Focus 1: il tocco su Assetto in pista non viene tolto dal frame
    # dopo, che dice ancora «non ai box».
    tapped = _call("pickTab", [[{"tab": "track", "atBox": False}, _TRACK, "setup"]])[0]
    assert tapped == "setup"
    held = _call("pickTab", [[{"tab": "setup", "atBox": False}, _TRACK, None]] * 3)
    assert held == ["setup"] * 3
    # E vale anche al contrario: ai box, Telemetria resta Telemetria.
    assert _call("pickTab", [[{"tab": "track", "atBox": True}, _BOX, None]]) == ["track"]


@needs_node
def test_leaving_the_box_goes_back_to_telemetry_and_stopping_opens_setup():
    # Review Focus 2: non si resta su Assetto quando si riparte.
    assert _call("pickTab", [
        [{"tab": "setup", "atBox": True}, _TRACK, None],
        [{"tab": "track", "atBox": False}, _BOX, None],
    ]) == ["track", "setup"]


@needs_node
def test_a_tap_wins_over_the_box_change_of_the_same_frame():
    assert _call("pickTab", [[{"tab": "setup", "atBox": True}, _TRACK, "setup"]]) == ["setup"]


def test_the_tabs_are_in_the_page_with_their_keys():
    html = (_WEB / "tablet.html").read_text(encoding="utf-8")
    for tid, key in (("t-tab-track", "tablet.tab.track"), ("t-tab-setup", "tablet.tab.setup")):
        m = re.search(r'<button[^>]*id="%s"[^>]*>' % tid, html)
        assert m, tid
        assert 'data-i18n="%s"' % key in m.group(0)


def test_the_tabs_are_tall_enough_for_a_finger():
    # Ogni regola su .t-tab, anche quella della vista compatta: e' li' che
    # l'altezza scende.
    css = (_WEB / "tablet.css").read_text(encoding="utf-8")
    blocks = re.findall(r"\.t-tab\s*\{([^}]*)\}", css)
    heights = [int(h) for b in blocks for h in re.findall(r"min-height:\s*(\d+)px", b)]
    assert len(heights) >= 2, heights
    assert min(heights) >= 44, heights


def test_the_tabs_are_a_tablist():
    html = (_WEB / "tablet.html").read_text(encoding="utf-8")
    assert re.search(r'<div[^>]*class="t-tabs"[^>]*role="tablist"', html)
    for tid in ("t-tab-track", "t-tab-setup"):
        m = re.search(r'<button[^>]*id="%s"[^>]*>' % tid, html)
        assert m and 'role="tab"' in m.group(0), tid


# Il DOM finto dei box, fino al primo frame escluso: da qui ogni test fa la sua
# sequenza.
_PRELUDE = _BOX_HARNESS.split("var frame = {")[0]


def _run(body):
    r = subprocess.run([_NODE, "-e", _PRELUDE + body, str(_WEB / "i18n.js"),
                        str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


_ON_TRACK = r"""
var track = {connected: true, at_box: false, car: "mclaren", track: "Imola", engineer: null};
var propose = {connected: true, at_box: false, car: "mclaren", track: "Imola",
  engineer: {kind: "propose", tag: "BOX", confidence: "medium",
             change: [{param: "tyrePressure", slot: null, delta_clicks: 2}]}};
function snap() {
  return {tab: $("tablet").getAttribute("data-tab"), mode: $("tablet").getAttribute("data-mode"),
          change: !$("t-change").hidden, actions: !$("t-actions").hidden,
          levers: $("t-levers").children.length, mark: $("t-tab-setup").getAttribute("data-mark"),
          write: !$("t-write").disabled, atbox: !$("t-atbox").hidden,
          trackSel: $("t-tab-track").getAttribute("aria-selected"),
          setupSel: $("t-tab-setup").getAttribute("aria-selected")};
}
"""


@needs_node
def test_tapping_setup_on_track_shows_the_box_screen_and_a_later_proposal():
    # Review Focus 5: la schermata Assetto funziona in pista, e una proposta
    # che arriva dopo il tocco appare al frame successivo.
    out = _run(_ON_TRACK + r"""
var o = {};
window.HoneTablet.render(track);
o.start = snap();
o.baseBefore = find("/api/setup/base").length;
$("t-tab-setup").onclick();
o.tapped = snap();
o.baseAfter = find("/api/setup/base").length;
reply(find("/api/setup/base")[0], 200, {car: "mclaren", track: "Imola",
  setups: [{name: "base", path: "S/base.json", mtime: 1}], base: "S/base.json", last_written: null});
window.HoneTablet.render(track);
o.same = snap();
window.HoneTablet.render(propose);
o.previews = find("/api/setup/preview").length;
reply(find("/api/setup/preview")[0], 200, {ok: true, errors: [], diff: [
  {group: "Gomme", label: "Pressione", slot: "FL", old_click: 57, new_click: 59,
   delta: 2, old_phys: "26 psi", new_phys: "26.2 psi"}]});
window.HoneTablet.render(propose);
o.proposal = snap();
// In pista si legge e basta: il bottone non apre la conferma.
$("t-write").onclick();
o.confirmOnTrack = !$("t-confirm").hidden;
// Fermo ai box scrive, dopo la conferma.
var box = JSON.parse(JSON.stringify(propose)); box.at_box = true;
window.HoneTablet.render(box);
o.atBox = snap();
$("t-write").onclick();
o.confirm = !$("t-confirm").hidden;
o.applyBeforeOk = find("/api/setup/apply").length;
$("t-confirm-ok").onclick();
o.apply = find("/api/setup/apply").length;
process.stdout.write(JSON.stringify(o));
""")
    assert out["start"]["tab"] == "track" and out["start"]["trackSel"] == "true"
    assert out["baseBefore"] == 0          # in pista, su Telemetria, non si chiede nulla
    assert out["tapped"]["tab"] == "setup" and out["tapped"]["mode"] == "track"
    assert out["tapped"]["setupSel"] == "true" and out["tapped"]["trackSel"] == "false"
    assert out["baseAfter"] == 1           # entrando in Assetto si chiede la base
    assert out["same"]["tab"] == "setup"   # il frame dopo non toglie la linguetta
    assert out["previews"] == 1
    p = out["proposal"]
    assert p["tab"] == "setup" and p["mode"] == "call"
    assert p["change"] and p["actions"] and p["levers"] == 1
    assert p["mark"] == "1"
    # Ruling 5: in pista la modifica si legge, il file no.
    assert p["write"] is False and p["atbox"] is True
    assert out["confirmOnTrack"] is False
    b = out["atBox"]
    assert b["write"] is True and b["atbox"] is False
    assert out["confirm"] and out["applyBeforeOk"] == 0 and out["apply"] == 1


@needs_node
def test_the_call_opens_setup_and_the_mark_goes_with_the_change():
    out = _run(_ON_TRACK + r"""
var o = {};
window.HoneTablet.render(track);
o.noMark = $("t-tab-setup").getAttribute("data-mark");
window.HoneTablet.render(propose);
o.call = snap();
$("t-call").onclick();
o.afterCall = snap();
$("t-tab-track").onclick();
o.back = snap();
// Ai box la vista passa da sola ad Assetto; ripartendo torna a Telemetria.
var box = JSON.parse(JSON.stringify(propose)); box.at_box = true;
window.HoneTablet.render(box);
o.box = snap();
window.HoneTablet.render(track);
o.leave = snap();
window.HoneTablet.render(null);
o.off = $("tablet").getAttribute("data-mode");
process.stdout.write(JSON.stringify(o));
""")
    assert out["noMark"] != "1"
    assert out["call"]["tab"] == "track" and out["call"]["mode"] == "call"
    assert out["call"]["mark"] == "1"
    assert out["afterCall"]["tab"] == "setup"
    assert out["back"]["tab"] == "track"
    assert out["box"]["tab"] == "setup" and out["box"]["mode"] == "box"
    assert out["leave"]["tab"] == "track" and out["leave"]["mark"] != "1"
    assert out["off"] == "off"


# Il riquadro del file scritto: resta finche' serve (il nome da caricare ai
# box), sparisce quando non e' piu' la notizia. Il file si scrive fermo ai box
# (Ruling 5): in pista la linguetta Assetto si legge e basta.
_WRITTEN = _ON_TRACK + r"""
function lastReq(path) { var r = find(path); return r[r.length - 1]; }
function tap(id) { $(id).onclick(); }
var o = {};
var box = JSON.parse(JSON.stringify(propose)); box.at_box = true;
function writeAtBox() {
  window.HoneTablet.render(track);
  window.HoneTablet.render(box);
  reply(lastReq("/api/setup/base"), 200, {car: "mclaren", track: "Imola",
    setups: [{name: "base", path: "S/base.json", mtime: 1}], base: "S/base.json", last_written: null});
  window.HoneTablet.render(box);
  reply(lastReq("/api/setup/preview"), 200, {ok: true, errors: [], diff: [
    {group: "Gomme", label: "Pressione", slot: "FL", old_click: 57, new_click: 59,
     delta: 2, old_phys: "26 psi", new_phys: "26.2 psi"}]});
  window.HoneTablet.render(box);
  tap("t-write");
  tap("t-confirm-ok");
}
// Il riquadro come lo vede il pilota: sulla linguetta Assetto.
function doneShown() {
  if ($("tablet").getAttribute("data-tab") !== "setup") tap("t-tab-setup");
  return !$("t-done").hidden;
}
function errShown() {
  if ($("tablet").getAttribute("data-tab") !== "setup") tap("t-tab-setup");
  return !$("t-err").hidden;
}
"""


def _written(body):
    return _run(_WRITTEN + body + "\nprocess.stdout.write(JSON.stringify(o));")


def _ok_write():
    return r"""
writeAtBox();
reply(lastReq("/api/setup/apply"), 200, {name: "HONE_1", reload_hint: "Ho scritto HONE_1."});
window.HoneTablet.render(box);
o.written = doneShown();
"""


@needs_node
def test_a_file_written_at_the_box_stays_while_you_are_there_and_goes_when_you_leave():
    out = _written(_ok_write() + r"""
window.HoneTablet.render(box);
o.atBox = doneShown();
window.HoneTablet.render(track);
o.left = doneShown();
""")
    assert out == {"written": True, "atBox": True, "left": False}


@needs_node
def test_a_new_proposal_drops_the_written_file():
    out = _written(_ok_write() + r"""
var other = JSON.parse(JSON.stringify(box));
other.engineer.change[0].delta_clicks = 3;
window.HoneTablet.render(other);
o.other = doneShown();
""")
    assert out == {"written": True, "other": False}


@needs_node
def test_box_then_off_then_track_drops_the_written_file():
    out = _written(_ok_write() + r"""
window.HoneTablet.render({connected: false});
window.HoneTablet.render(track);
o.after = doneShown();
""")
    assert out == {"written": True, "after": False}


@needs_node
def test_another_car_or_track_drops_the_written_file():
    out = _written(_ok_write() + r"""
var monza = JSON.parse(JSON.stringify(box)); monza.track = "Monza";
window.HoneTablet.render(monza);
o.monza = doneShown();
""")
    assert out == {"written": True, "monza": False}


@needs_node
def test_a_write_error_goes_when_you_leave_the_box():
    out = _written(r"""
writeAtBox();
reply(lastReq("/api/setup/apply"), 500, {detail: "boom"});
window.HoneTablet.render(box);
o.err = errShown();
window.HoneTablet.render(track);
o.back = errShown();
""")
    assert out == {"err": True, "back": False}


@needs_node
def test_a_tap_does_not_add_a_pedal_sample():
    # Il tocco ridisegna col frame che c'era: non e' un campione nuovo.
    out = _run(_ON_TRACK + r"""
var cv = $("t-trace"); cv.offsetWidth = 0;
var pushes = 0, orig = $("tr-thr");
var val = "";
Object.defineProperty(orig, "textContent", {get: function () { return val; },
  set: function (v) { pushes++; val = v; }});
var pedals = JSON.parse(JSON.stringify(track));
pedals.throttle = 0.5; pedals.brake = 0; pedals.steer = 0;
window.HoneTablet.render(pedals);
var a = pushes;
$("t-tab-setup").onclick();
$("t-tab-track").onclick();
var b = pushes;
// Neanche un altro file di partenza o il cambio di lingua: ridisegnano
// l'ultimo frame, non ne portano uno nuovo.
$("t-base").value = "S/altro.json";
$("t-base").onchange();
window.HoneI18nRerender();
process.stdout.write(JSON.stringify({first: a, afterTaps: b, afterRedraws: pushes}));
""")
    assert out["afterTaps"] == out["first"]
    assert out["afterRedraws"] == out["first"]


# Ruling 5: scrivere in pista avvisava il motore (`/engineer/applied`), che
# apriva la prova con la macchina ancora sull'assetto vecchio. In pista la
# linguetta Assetto si legge; il file e «l'ho gia' rimesso» solo da fermo ai
# box.
_READY = r"""
var revert = JSON.parse(JSON.stringify(propose));
revert.engineer.kind = "reverted"; revert.engineer.message = "Va tolta.";
var revertBox = JSON.parse(JSON.stringify(revert)); revertBox.at_box = true;
function prep(f) {
  window.HoneTablet.render(f);
  if ($("tablet").getAttribute("data-tab") !== "setup") tap("t-tab-setup");
  var b = lastReq("/api/setup/base");
  if (b && b.readyState !== 4) reply(b, 200, {car: "mclaren", track: "Imola",
    setups: [{name: "base", path: "S/base.json", mtime: 1}], base: "S/base.json", last_written: null});
  window.HoneTablet.render(f);
  var pv = lastReq("/api/setup/preview");
  if (pv && pv.readyState !== 4) reply(pv, 200, {ok: true, errors: [], diff: [
    {group: "Gomme", label: "Pressione", slot: "FL", old_click: 57, new_click: 59,
     delta: 2, old_phys: "26 psi", new_phys: "26.2 psi"}]});
  window.HoneTablet.render(f);
}
"""


@needs_node
def test_on_track_a_confirm_opened_at_the_box_cannot_write():
    out = _written(_READY + r"""
prep(box);
tap("t-write");
o.confirmAtBox = !$("t-confirm").hidden;
// Riparte con la conferma aperta, e il dito la tocca lo stesso.
window.HoneTablet.render(propose);
tap("t-confirm-ok");
tap("t-tab-setup");
tap("t-confirm-ok");
tap("t-write");
o.confirmOnTrack = !$("t-confirm").hidden;
tap("t-confirm-ok");
o.apply = find("/api/setup/apply").length;
o.applied = find("/engineer/applied").length;
""")
    assert out == {"confirmAtBox": True, "confirmOnTrack": False, "apply": 0, "applied": 0}


@needs_node
def test_on_track_the_restore_cannot_be_marked_put_back():
    out = _written(_READY + r"""
prep(revert);
o.trackShown = !$("t-restored").hidden;
o.trackEnabled = !$("t-restored").disabled;
o.writeEnabled = !$("t-write").disabled;
o.atbox = !$("t-atbox").hidden;
tap("t-restored");
o.appliedOnTrack = find("/engineer/applied").length;
window.HoneTablet.render(revertBox);
o.boxEnabled = !$("t-restored").disabled;
o.boxAtbox = !$("t-atbox").hidden;
tap("t-restored");
o.appliedAtBox = find("/engineer/applied").length;
""")
    assert out == {"trackShown": True, "trackEnabled": False, "writeEnabled": False,
                   "atbox": True, "appliedOnTrack": 0,
                   "boxEnabled": True, "boxAtbox": False, "appliedAtBox": 1}


def test_the_at_box_line_is_in_the_page_with_its_key():
    html = (_WEB / "tablet.html").read_text(encoding="utf-8")
    m = re.search(r'<[^>]*id="t-atbox"[^>]*>', html)
    assert m and 'data-i18n="tablet.writeAtBox"' in m.group(0)
