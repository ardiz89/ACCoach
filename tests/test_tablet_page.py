"""La vista tablet (`/tablet`): una pagina leggera che gira sull'iPad 3 del pilota.

Lo stato della schermata si decide a ogni frame dal vivo (spec, «I tre stati»):
qui si prova la regola in node, sullo stesso `tablet.js` che la pagina carica,
e che la pagina si serve con la lingua dell'app e con i soli suoi file.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accoach import config
from accoach.api import create_api

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")


@pytest.mark.parametrize("lang", ["it", "en"])
def test_tablet_is_served_with_the_language(tmp_path, lang):
    config.set_language(lang)
    r = TestClient(create_api(tmp_path)).get("/tablet")
    assert r.status_code == 200
    assert re.search(rf'<html lang="{lang}"[ >]', r.text), r.text[:120]
    assert f'window.HONE_LANG = "{lang}"' in r.text


def test_tablet_loads_only_its_files():
    html = (_WEB / "tablet.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script[^>]*\ssrc="([^"]+)"', html)
    sheets = [m for tag in re.findall(r"<link\b[^>]*>", html)
              if 'rel="stylesheet"' in tag
              for m in re.findall(r'href="([^"]+)"', tag)]
    assert sorted(scripts + sheets) == ["/static/i18n.js", "/static/tablet.css",
                                        "/static/tablet.js"]


# Uno stub minimo di `document`: i18n.js al caricamento traduce i testi fissi e
# monta il selettore della lingua, e senza nodi non trova niente da fare.
_HARNESS = """
var window = {HONE_LANG: "it"};
var document = {readyState: "complete",
  querySelectorAll: function () { return []; },
  querySelector: function () { return null; },
  getElementById: function () { return null; },
  documentElement: {}};
var fs = require("fs");
eval(fs.readFileSync(process.argv[1], "utf8"));
eval(fs.readFileSync(process.argv[2], "utf8"));
var req = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(req.calls.map(function (args) {
  return window.HoneTablet[req.fn].apply(null, args);
})));
"""

_CHANGE = [{"param": "tyrePressure", "slot": 0, "delta_clicks": 1}]
_PROPOSE = {"kind": "propose", "tag": "BOX", "change": _CHANGE}


def _call(fn, calls):
    """`HoneTablet[fn](*args)` in node, per ogni `args` di `calls`."""
    r = subprocess.run([_NODE, "-e", _HARNESS, str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       input=json.dumps({"fn": fn, "calls": calls}), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _modes(frames):
    return _call("mode", [[f] for f in frames])


def _live(eng, at_box=False):
    return {"connected": True, "at_box": at_box, "engineer": eng}


needs_node = pytest.mark.skipif(_NODE is None, reason="serve node")


@needs_node
def test_mode_off_without_the_engine():
    assert _modes([{"connected": False}, None]) == ["off", "off"]


@needs_node
def test_off_says_whether_the_engine_or_the_game_is_missing():
    # Senza frame il motore non c'e'; con `connected: false` c'e', e tace il
    # gioco (menu, prima della sessione, replay): due frasi diverse.
    closed, waiting = _call("offText", [[None], [{"connected": False}]])
    assert closed == "Il coach non è acceso. La pagina si ricollega da sola."
    assert waiting == "Il coach è acceso e aspetta i dati del gioco."


def _lever(old_phys, new_phys, old_click, new_click):
    return {"label": "x", "slot": "", "old_phys": old_phys, "new_phys": new_phys,
            "old_click": old_click, "new_click": new_click}


@needs_node
def test_a_lever_in_clicks_is_said_once():
    # ACC «11 click», AC «11» (il numero e' il click), ACC con passo senza
    # base «11 click (~0.1psi/click)»: tre forme, una riga sola, in click.
    assert _call("leverText", [
        [_lever("11 click", "9 click", 11, 9)],
        [_lever("11", "9", 11, 9)],
        [_lever("11 click (~0.1psi/click)", "9 click (~0.1psi/click)", 11, 9)],
    ]) == ["11 → 9 click"] * 3


@needs_node
def test_a_lever_with_a_unit_shows_the_value_and_the_clicks():
    # Come il riepilogo della pagina completa: valore fisico, poi i click col
    # segno. I due valori coi decimali del piu' preciso dei due.
    assert _call("leverText", [
        [_lever("26.8 psi", "27 psi", 66, 68)],
        [_lever("64 °", "62.5 °", 4, 1)],
        [_lever("12 mm", "14 mm", 3, 5)],
    ]) == ["26,8 psi → 27,0 psi (+2 click)",
           "64,0 ° → 62,5 ° (−3 click)",
           "12 mm → 14 mm (+2 click)"]


@needs_node
def test_mode_track_while_driving_without_a_box_change():
    assert _modes([_live(None), _live({"kind": "propose", "tag": "AV", "change": _CHANGE})]) \
        == ["track", "track"]


@needs_node
def test_mode_call_for_a_proposal_or_a_restore_still_to_do():
    restore = {"kind": "reverted", "tag": "BOX", "change": _CHANGE}
    assert _modes([_live(_PROPOSE), _live(restore)]) == ["call", "call"]


@needs_node
def test_mode_call_ends_when_the_change_is_written():
    # Scritta (`applied`) la modifica, l'avviso di rientro non ha piu' ragione.
    done = dict(_PROPOSE, applied=True)
    empty = dict(_PROPOSE, change=[])
    assert _modes([_live(done), _live(empty)]) == ["track", "track"]


@needs_node
def test_mode_box_when_stopped_in_the_pits():
    assert _modes([_live(_PROPOSE, at_box=True), _live(None, at_box=True)]) == ["box", "box"]


@needs_node
def test_the_call_says_restore_for_a_rejected_change():
    restore = {"kind": "reverted", "tag": "BOX", "change": _CHANGE}
    assert _call("callKey", [[_PROPOSE], [restore]]) == ["tablet.call", "tablet.callRestore"]


@needs_node
def test_the_done_button_stays_hidden_after_a_tap_for_that_proposal():
    av = {"kind": "propose", "tag": "AV", "change": _CHANGE}
    other = dict(av, change=[{"param": "tc", "slot": 0, "delta_clicks": -1}])
    key = _call("avKey", [[av]])[0]
    assert key and _call("avKey", [[other]])[0] != key
    # (proposta, chiave del tocco) -> il bottone e' nascosto?
    assert _call("avDoneHidden", [
        [av, None],                 # mai toccato: si vede
        [av, key],                  # toccato: resta nascosto finche' il motore non chiude
        [other, key],               # un'altra proposta: si rivede
        [dict(av, watched=True), None],
        [dict(av, applied=True), None],
    ]) == [False, True, False, True, True]


def test_reconnects():
    src = (_WEB / "tablet.js").read_text(encoding="utf-8")
    assert "onclose" in src
    assert re.search(r"setTimeout\(\s*\w+\s*,\s*3000\s*\)", src)
