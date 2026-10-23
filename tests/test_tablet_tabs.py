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
    css = (_WEB / "tablet.css").read_text(encoding="utf-8")
    m = re.search(r"\.t-tab\s*\{([^}]*)\}", css)
    assert m, "manca la regola .t-tab"
    h = re.search(r"min-height:\s*(\d+)px", m.group(1))
    assert h and int(h.group(1)) >= 44


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
// Il bottone scrive anche fuori dai box, sempre dopo la conferma.
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
