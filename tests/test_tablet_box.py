"""La schermata dei box della vista tablet e il bottone che scrive la modifica.

Il nome del file nuovo e le leve che si mandano li decide `tablet.js` (provato in
node, sullo stesso file che la pagina carica); la scrittura passa dagli
endpoint `/api/setup/*` della pagina completa. L'ultimo test fa a mano la
sequenza della pagina contro l'API vera: e' la prova che il file di partenza
(Task 2) e il bottone (Task 5) parlano lo stesso contratto.
"""
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from accoach.api import create_api
from test_setup_api import CAR, SAMPLE, TRACK
from test_tablet_page import _call, needs_node

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
