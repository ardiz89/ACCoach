"""Il registro dell'ingegnere arriva sullo schermo.

`/api/setup/record` esisteva, era testato, restituiva prove/tenute/riuscita/
guadagno mediano/effetti collaterali — e **non lo chiamava nessuno**. Zero
occorrenze in `engineer.js`. Il loop misurato è l'unica cosa che ci distingue da
un generatore di setup, e il pilota non lo vedeva.

È anche l'unico numero della pagina che può darci torto, il che è il punto.
"""
import re
from pathlib import Path

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_JS = (_WEB / "engineer.js").read_text(encoding="utf-8")
_HTML = (_WEB / "engineer.html").read_text(encoding="utf-8")
_I18N = (_WEB / "i18n.js").read_text(encoding="utf-8")


def test_the_page_actually_asks_for_the_record():
    """Il difetto, in una riga: l'endpoint c'era e nessuno lo chiamava."""
    assert "/api/setup/record" in _JS


def test_it_is_asked_for_the_car_and_track_on_screen():
    """Un registro globale mescolerebbe una GT3 a Monza con una Formula a Spa:
    l'endpoint filtra, e il client deve dirgli su cosa."""
    # Guardato su tutta la funzione, non sulla singola stringa: l'URL è spezzato
    # su due literal per stare negli 88 caratteri, e una regex che si ferma al
    # primo backtick vede solo metà chiamata.
    body = _JS[_JS.index("async function loadRecord"):]
    body = body[:body.index("\n}")]
    assert "car=" in body and "track=" in body


def test_the_panel_exists_and_starts_hidden():
    assert 'id="eng-record"' in _HTML
    assert re.search(r'id="eng-record"[^>]*hidden', _HTML)


def test_a_percentage_is_withheld_until_there_are_enough_tests():
    """«Un tasso di riuscita su tre campioni è rumore travestito da percentuale»
    — lo dice il modulo che lo calcola, e la pagina deve rispettarlo."""
    assert "REC_MIN_TESTS" in _JS
    n = int(re.search(r"REC_MIN_TESTS\s*=\s*(\d+)", _JS).group(1))
    assert n >= 5, "sotto i cinque campioni una percentuale non significa niente"
    assert re.search(r"r\.tests\s*>=\s*REC_MIN_TESTS", _JS), \
        "la soglia deve governare la percentuale, non solo esistere"


def test_the_counts_are_shown_even_when_the_percentage_is_not():
    """Nascondere tutto sotto soglia sarebbe la stessa opacità di prima. I
    conteggi si mostrano sempre: sono un fatto, non una stima."""
    assert '"rec.counts"' in _I18N and "{kept}" in _I18N and "{tests}" in _I18N
    assert '"rec.thin"' in _I18N, "e si dice perché la percentuale non c'è"


def test_an_empty_record_says_what_will_fill_it():
    """Sarà vuoto a lungo, ed è lo stato normale all'inizio: un pannello vuoto
    senza spiegazione è la stessa app rotta di sempre."""
    assert '"rec.none"' in _I18N


def test_the_failures_are_shown_too():
    """Il registro serve se può darci torto: le leve che non si guadagnano il
    posto e gli effetti collaterali mai predetti stanno lì apposta."""
    for key in ('"rec.byparam"', '"rec.byrank"', '"rec.side"'):
        assert key in _I18N
    assert "by_rank" in _JS and "side_effects" in _JS


def test_every_record_string_is_in_both_languages():
    for key in re.findall(r'"(rec\.[a-z_]+)"', _I18N):
        block = _I18N[_I18N.index(f'"{key}"'):][:600]
        assert "en:" in block and "it:" in block, key


# --- il registro come lo legge il pilota -----------------------------------
# Si esegue la `loadRecord` vera, col catalogo vero (i18n.js) e un DOM finto.

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

_NODE = shutil.which("node")

_HARNESS = r"""
const fs = require("fs");
const [i18nPath, engPath, lang] = process.argv.slice(2);
global.window = {};
global.localStorage = { getItem: () => lang, setItem() {} };
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(i18nPath, "utf8"));
const src = fs.readFileSync(engPath, "utf8");
function grab(name) {
  const i = src.indexOf("function " + name + "(");
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
const line = (re) => src.split("\n").find((l) => re.test(l));
// `const` dentro un eval resta nell'eval: si dichiara `var`, che ne esce.
const asVar = (code) => code.replace(/^const /, "var ");
eval(asVar(line(/^const t = /))); eval(grab("fmtN"));
eval(asVar(src.slice(src.indexOf("const tf = "), src.indexOf("};", src.indexOf("const tf = ")) + 2)));
eval(asVar(line(/^const REC_MIN_TESTS/)));
const els = {};
const $ = (id) => els[id] || (els[id] = { hidden: false, textContent: "", innerHTML: "" });
const state = { car: "c", track: "t" };
let RECORD = null;
const api = async () => RECORD;
eval("async " + grab("loadRecord"));
(async () => {
  const out = [];
  for (const r of JSON.parse(fs.readFileSync(0, "utf8"))) {
    RECORD = r;
    await loadRecord();
    out.push({ head: $("rec-head").innerHTML, tables: $("rec-tables").innerHTML,
               laps: [tf("eng.oc.laps", { n: 1 }), tf("eng.oc.laps", { n: 3 })] });
  }
  console.log(JSON.stringify(out));
})();
"""


def _record(tmp_path, lang, *records):
    script = tmp_path / "rec.js"
    script.write_text(_HARNESS, encoding="utf-8")
    run = subprocess.run([_NODE, str(script), str(_WEB / "i18n.js"), str(_WEB / "engineer.js"),
                          lang], input=json.dumps(records), capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _rec(gain_ms):
    return {"tests": 2, "kept": 1, "hit_rate": 0.5, "median_gain_ms": gain_ms,
            "by_param": {"aRBFront": {"kept": 1, "tests": 2}},
            "labels": {"aRBFront": "Barra ant."},
            "by_rank": {}, "side_effects": [
                {"param": "aRBFront", "label": "Barra ant.", "symptom": "oversteer exit low",
                 "words": "sovrasterzo in uscita dalle curve lente", "seen": 2}]}


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")
def test_the_median_lap_time_change_keeps_its_sign(tmp_path):
    """`median_gain_ms` è la variazione del tempo: negativa vuol dire più veloce.
    Chiamarla «guadagno» rovesciava il senso proprio quando la modifica aiutava."""
    faster, slower = _record(tmp_path, "it", _rec(-120.0), _rec(80.0))
    assert "variazione mediana del giro −0,120 s" in faster["head"]
    assert "variazione mediana del giro +0,080 s" in slower["head"]
    assert "guadagno" not in faster["head"] + slower["head"]
    (en,) = _record(tmp_path, "en", _rec(-120.0))
    assert "median lap-time change −0.120 s" in en["head"]


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")
def test_the_record_names_levers_and_symptoms_as_the_page_does(tmp_path):
    (r,) = _record(tmp_path, "it", _rec(-120.0))
    assert "Barra ant." in r["tables"] and "aRBFront" not in r["tables"]
    assert "sovrasterzo in uscita dalle curve lente" in r["tables"]
    assert "oversteer exit low" not in r["tables"]


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")
def test_the_page_tf_picks_singular_and_plural(tmp_path):
    """«su 1 giri» era il caso normale di una prova corta."""
    (it,) = _record(tmp_path, "it", _rec(-120.0))
    assert it["laps"] == ["su 1 giro", "su 3 giri"]
    (en,) = _record(tmp_path, "en", _rec(-120.0))
    assert en["laps"] == ["over 1 lap", "over 3 laps"]
