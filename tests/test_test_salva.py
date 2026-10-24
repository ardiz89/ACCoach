"""La pagina di prova dice cosa fare quando il PC non accetta altre prove.

`/api/test/save` risponde 409 al duecentounesimo file (`MAX_TEST_RUNS`). Prima la
pagina scriveva la frase generica «Il PC ha risposto con un errore», che non dice
ne' che cosa e' successo ne' che i risultati sono ancora sul tablet. Il JS si
esegue in node con un DOM finto: e' l'unico modo di vedere la frase scelta.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from accoach import api

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_NODE = shutil.which("node")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const status = Number(process.argv[3]);
const els = {};
function mk() {
  const store = { classList: { toggle() {}, add() {}, remove() {} }, style: {},
                  dataset: {}, children: [], textContent: "", value: "" };
  return new Proxy(store, {
    get(t, k) { return k in t ? t[k] : function () { return mk(); }; },
    set(t, k, v) { t[k] = v; return true; },
  });
}
global.document = {
  getElementById(id) { return els[id] || (els[id] = mk()); },
  querySelectorAll() { return []; }, createElement() { return mk(); },
};
global.window = {};
global.location = { hostname: "pc" };
global.localStorage = { getItem() { return null; }, setItem() {} };
global.WebSocket = function () { throw new Error("no"); };
const vero = global.setTimeout;
// Solo il rinvio dell'autosave (800 ms) gira subito; il resto non serve.
global.setTimeout = (f, ms) => { if (ms === 800) f(); return 0; };
global.clearTimeout = () => {};
global.fetch = async (u) => {
  if (u.indexOf("test_plan") >= 0) return { json: async () => ({ categories: [{ id: "c", title: "C", tests: [{ id: "t1", n: 1, what: "1) a", expected: "b" }] }], glossary: [] }) };
  return { status, ok: status < 300,
           json: async () => (status === 409 ? { detail: "too many saved test runs" }
                                              : status === 200 ? { ok: true } : {}) };
};
eval(src);
vero(() => {
  els.car.oninput({ target: { value: "x" } });
  vero(() => { console.log(JSON.stringify(els.savestate.textContent)); }, 20);
}, 20);
"""


def _testo_dopo(tmp_path, status: int) -> str:
    h = tmp_path / "h.js"
    h.write_text(_HARNESS, encoding="utf-8")
    out = subprocess.run([_NODE, str(h), str(_WEB / "test.js"), str(status)],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire il JS")
def test_al_409_la_pagina_dice_il_fatto_e_cosa_fare(tmp_path):
    testo = _testo_dopo(tmp_path, 409)
    assert str(api.MAX_TEST_RUNS) in testo
    assert "test_runs" in testo
    assert "tablet" in testo
    assert testo != _testo_dopo(tmp_path, 500)


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire il JS")
def test_un_altro_errore_resta_la_frase_generica(tmp_path):
    assert _testo_dopo(tmp_path, 500) == "Il PC ha risposto con un errore."
    assert _testo_dopo(tmp_path, 200) == "Salvato"
