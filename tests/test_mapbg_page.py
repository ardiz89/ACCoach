"""La mappa del report con sotto la pista vista dall'alto: la parte della pagina.

Le funzioni pure di app.js si eseguono in node, come fa
`test_engineer_record_panel.py`: si prende il sorgente vero, si estraggono le
funzioni per nome e le si chiama senza DOM. Il conto che conta e' uno. Un punto
del modello del gioco deve finire sullo schermo esattamente dove la mappa
disegna lo stesso punto portato nelle coordinate del giro da `Fit.apply`.
"""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from accoach.trackedges import Fit

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_JS = (_WEB / "app.js").read_text(encoding="utf-8")
_I18N = (_WEB / "i18n.js").read_text(encoding="utf-8")
_NODE = shutil.which("node")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name) {
  const i = src.indexOf("function " + name + "(");
  if (i < 0) throw new Error("manca " + name);
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
const line = (re) => src.split("\n").find((l) => re.test(l));
const asVar = (code) => code.replace(/^const /, "var ");
eval(asVar(line(/^const MAPBG_LEVELS = /)));
eval(asVar(line(/^const MAP_MAX_PX_PER_M = /)));
for (const f of ["affCompose", "affApply", "mapBgAffine", "mapBgLevel",
                 "lineWidthOnPhoto", "mapLineWidth", "mapView", "mapXY",
                 "mapZoomAt", "mapWheelFactor"]) eval(grab(f));
const job = JSON.parse(fs.readFileSync(0, "utf8"));
const out = {};
out.level = job.level.map((a) => mapBgLevel(a[0], a[1]));
out.photo = job.photo.map((a) => lineWidthOnPhoto(a[0], a[1]));
out.today = job.today.map((a) => mapLineWidth(a[0], a[1], false));
out.points = [];
for (const c of job.points) {
  const v = mapView(c.box, c.w, c.h, c.view);
  const xy = mapXY(v, c.w, c.h);
  const T = mapBgAffine(c.fit, v.A);
  const p = affApply(T, c.model[0], c.model[1]);
  out.points.push({ got: p, want: [xy.X(c.lap[0]), xy.Y(c.lap[1])] });
}
out.zoom = job.zoom.map((c) => {
  const v0 = mapView(c.box, c.w, c.h, c.view);
  const xy0 = mapXY(v0, c.w, c.h);
  const nv = mapZoomAt(c.view, c.box, c.w, c.h, c.px, c.py, c.f);
  const v1 = mapView(c.box, c.w, c.h, nv);
  const xy1 = mapXY(v1, c.w, c.h);
  // il punto del giro che stava sotto il cursore
  const x = v0.cx - (c.px - c.w / 2) / v0.s, z = v0.cz + (c.h / 2 - c.py) / v0.s;
  return { k: v1.k, s: v1.s, s0: v1.s0, before: [xy0.X(x), xy0.Y(z)], after: [xy1.X(x), xy1.Y(z)] };
});
out.wheel = job.wheel.map((a) => mapWheelFactor(a[0], a[1]));
console.log(JSON.stringify(out));
"""


def _run(tmp_path, job):
    script = tmp_path / "mapbg.js"
    script.write_text(_HARNESS, encoding="utf-8")
    run = subprocess.run([_NODE, str(script), str(_WEB / "app.js")], input=json.dumps(job),
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def _job(**kw):
    job = {"level": [], "photo": [], "today": [], "points": [], "zoom": [], "wheel": []}
    job.update(kw)
    return job


_BOX = {"minX": -800.0, "maxX": 650.0, "minZ": -420.0, "maxZ": 380.0}


def _fit(deg, scale, mirror):
    a = math.radians(deg)
    return Fit(scale=scale, cos=math.cos(a), sin=math.sin(a), dx=37.5, dz=-112.25,
               p95_m=0.3, mirror=mirror)


needs_node = pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")


@needs_node
@pytest.mark.parametrize("mirror", (False, True))
@pytest.mark.parametrize("view", ({"k": 1, "cx": 0, "cz": 0},
                                  {"k": 6.5, "cx": 120.0, "cz": -40.0}))
def test_the_affine_puts_a_model_point_where_the_lap_point_is(tmp_path, mirror, view):
    fit = _fit(33.0, 1.0007, mirror)
    points = []
    for mx, mz in ((0.0, 0.0), (412.5, -233.0), (-610.0, 95.75), (88.0, 300.0)):
        lx, lz = fit.apply(mx, mz)
        points.append({"box": _BOX, "w": 1036, "h": 640, "view": view,
                       "fit": {"scale": fit.scale, "cos": fit.cos, "sin": fit.sin,
                               "dx": fit.dx, "dz": fit.dz, "mirror": fit.mirror},
                       "model": [mx, mz], "lap": [lx, lz]})
    out = _run(tmp_path, _job(points=points))
    for p in out["points"]:
        assert abs(p["got"][0] - p["want"][0]) < 0.01, p
        assert abs(p["got"][1] - p["want"][1]) < 0.01, p


@needs_node
def test_the_level_follows_the_zoom(tmp_path):
    out = _run(tmp_path, _job(level=[[0.3, 1], [10, 1], [5, 2], [1, 1], [1, 2]]))
    assert out["level"][:3] == [5, 0, 0]
    # 1 px per metro: il tassello da 0,8 m per pixel e' gia' piu' fine dello
    # schermo, quello da 1,6 no. Su uno schermo doppio serve 0,5 m: 0,8.
    assert out["level"][3:] == [4, 3]


@needs_node
def test_the_line_stays_inside_the_road_at_full_lap_scale(tmp_path):
    out = _run(tmp_path, _job(photo=[[1, 0.87], [1, 3], [0, 0.87], [0, 0.3]]))
    assert out["photo"][0] <= 2.61 + 1e-9
    assert out["photo"][1] == 7
    assert out["photo"][2] == 2
    # mai piu' sottile di 1,5 px: una linea che sparisce non si legge
    assert out["photo"][3] == 1.5


@needs_node
def test_without_a_background_the_line_is_as_today(tmp_path):
    out = _run(tmp_path, _job(today=[[0, 0.87], [1, 0.87], [0.5, 3]]))
    assert out["today"] == [2, 7, 4.5]
    body = _JS[_JS.index("function drawMapTo("):]
    body = body[:body.index("\n}")]
    assert "mapLineWidth(" in body, "la larghezza della linea passa dalla regola"


@needs_node
def test_the_wheel_zooms_around_the_cursor_and_stops_at_ten_px_per_metre(tmp_path):
    whole = {"k": 1, "cx": 0, "cz": 0}
    out = _run(tmp_path, _job(zoom=[
        {"box": _BOX, "w": 1036, "h": 640, "view": whole, "px": 300, "py": 200, "f": 1.25},
        {"box": _BOX, "w": 1036, "h": 640, "view": {"k": 1e6, "cx": 10, "cz": 10},
         "px": 518, "py": 320, "f": 1.25},
        {"box": _BOX, "w": 1036, "h": 640, "view": whole, "px": 300, "py": 200, "f": 0.8},
    ]))
    first, top, out_of_whole = out["zoom"]
    assert abs(first["k"] - 1.25) < 1e-9
    assert abs(first["after"][0] - first["before"][0]) < 0.01
    assert abs(first["after"][1] - first["before"][1]) < 0.01
    assert abs(top["s"] - 10) < 1e-9
    assert out_of_whole["k"] == 1, "sotto il giro intero non si va"


@needs_node
def test_the_wheel_zoom_follows_how_far_the_wheel_turned(tmp_path):
    out = _run(tmp_path, _job(wheel=[[-100, 0], [100, 0], [-3, 1], [-10, 0], [-5000, 0],
                                     [5000, 0], [-1, 2], [0, 0]]))
    want = [1.25, 0.8, 1.25 ** 1.2, 1.25 ** 0.1, 4, 0.25, 4, 1]
    for got, w in zip(out["wheel"], want):
        assert abs(got - w) < 1e-9, (out["wheel"], want)


def test_the_wheel_handler_uses_the_factor():
    i = _JS.index('map.addEventListener("wheel"')
    body = _JS[i:i + 900]
    assert "mapWheelFactor(e.deltaY, e.deltaMode)" in body
    assert "f < 1 && MAP_VIEW.k <= 1" in body, "all'indietro al giro intero scorre la pagina"


def test_the_background_is_dimmed_as_chosen():
    assert "saturate(0.55) brightness(0.62)" in _JS


def _body(name):
    body = _JS[_JS.index(f"function {name}("):]
    return body[:body.index("\n}")]


def test_the_rail_has_no_background():
    assert "mapBgDraw" not in _body("drawRail")


def test_the_background_is_asked_only_for_a_lap_with_a_map():
    body = _body("loadCombo")
    assert "loadMapBg(" in body
    assert re.search(r"if \(a\.has_map\)\s*loadMapBg\(", body)


def test_the_corner_view_uses_the_background_only_at_true_scale():
    body = _body("drawCornerZoom")
    assert "mapBgDraw(" in body
    assert re.search(r"if \(MAPBG && LINE_MAG === 1\) \{[^}]*mapBgDraw\(", body)
    assert re.search(r"if \(!photo\) \{\s*if \(shapes\) drawSurfaces", body), \
        "con lo sfondo il disegno dell'asfalto non va sopra la pista vera"


def test_the_legend_names_the_background_in_both_languages():
    block = _I18N[_I18N.index('"line.leg.photo"'):][:400]
    assert "Lo sfondo è la pista vista dall'alto, presa dai file di Assetto Corsa." in block
    assert "The background is the track seen from above, taken from Assetto Corsa's files." in block
    assert 'line.leg.photo' in _JS
