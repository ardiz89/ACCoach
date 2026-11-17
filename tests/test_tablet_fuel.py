"""La benzina sulla vista tablet (sezione C): terza cifra grande, «≈ N giri» sotto."""
import json
import re
import subprocess

from test_tablet_box import _BOX_HARNESS
from test_tablet_page import _NODE, _WEB, needs_node

_PRE = _BOX_HARNESS.split("var frame =")[0]


def _render(fuel):
    js = _PRE + r"""
var frame = {connected: true, at_box: false, speed_kmh: 120, gear: 3, fuel: %s};
window.HoneTablet.render(frame);
process.stdout.write(JSON.stringify({pct: $("t-fuel").textContent,
                                     laps: $("t-fuel-laps").textContent}));
""" % json.dumps(fuel)
    r = subprocess.run([_NODE, "-e", js, str(_WEB / "i18n.js"), str(_WEB / "tablet.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_shows_percentage_and_laps():
    out = _render({"litres": 24.5, "pct": 41, "laps": 6})
    assert out == {"pct": "41", "laps": "≈ 6 giri"}


@needs_node
def test_one_lap_is_singular():
    assert _render({"litres": 3, "pct": 5, "laps": 1})["laps"] == "≈ 1 giro"


@needs_node
def test_dash_when_unknown():
    assert _render({"litres": 3, "pct": None, "laps": None}) == {"pct": "–", "laps": "–"}
    assert _render(None) == {"pct": "–", "laps": "–"}


def test_page_has_the_fuel_block_and_keys():
    html = (_WEB / "tablet.html").read_text(encoding="utf-8")
    assert 'id="t-fuel"' in html and 'id="t-fuel-laps"' in html
    js = (_WEB / "i18n.js").read_text(encoding="utf-8")
    for k in ("tablet.fuel", "tablet.fuelLaps", "tablet.fuelLap"):
        assert '"%s"' % k in js


def test_the_last_big_number_has_no_right_margin():
    """Revisione finale: a 1024 punti velocita', marcia e «100» stavano a pochi
    px dal bordo. I 24 px dopo l'ultima cifra non separano niente."""
    css = (_WEB / "tablet.css").read_text(encoding="utf-8")
    assert re.search(r"\.t-big:last-child\s*\{\s*margin-right:\s*0;", css)
