"""Le pagine web seguono la lingua dell'app, non quella del browser.

Prima la lingua stava in `localStorage.hone_lang` con «en» di ripiego: un
tablet nuovo apriva la pagina Ingegnere in inglese mentre l'hub era in italiano.
Ora la lingua è quella del config (`language`), che il server scrive nell'HTML
al momento di servirlo, e il selettore della pagina cambia la lingua dell'app.
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


def _client(tmp_path):
    return TestClient(create_api(tmp_path))


@pytest.mark.parametrize("page", ["/", "/engineer"])
@pytest.mark.parametrize("lang", ["it", "en"])
def test_the_served_page_carries_the_configured_language(tmp_path, page, lang):
    config.set_language(lang)
    html = _client(tmp_path).get(page).text
    assert f'<html lang="{lang}">' in html
    inj = f'window.HONE_LANG = "{lang}"'
    assert inj in html
    # prima di i18n.js, che la legge all'avvio
    assert html.index(inj) < html.index("/static/i18n.js")


def test_a_change_made_by_the_hub_shows_on_the_next_load(tmp_path):
    """Il server non congela la lingua: la rilegge dal file ogni volta, perché
    l'hub è un altro processo e scrive solo il config."""
    c = _client(tmp_path)
    config.set_language("en")
    assert 'window.HONE_LANG = "en"' in c.get("/engineer").text
    # scrittura «da fuori»: l'altro processo cambia il file, non la nostra cache
    path = config.config_path()
    path.write_text(path.read_text(encoding="utf-8").replace(
        'language = "en"', 'language = "it"'), encoding="utf-8")
    assert 'window.HONE_LANG = "it"' in c.get("/engineer").text


def test_the_language_is_injected_in_demo_too(tmp_path):
    config.set_language("it")
    html = TestClient(create_api(tmp_path, demo=True)).get("/").text
    assert 'window.HONE_LANG = "it"' in html and "demo-banner" in html


def test_post_language_updates_the_config(tmp_path):
    config.set_language("en")
    r = _client(tmp_path).post("/api/language", json={"lang": "it"})
    assert r.status_code == 200 and r.json() == {"lang": "it"}
    assert config.load_config(reload=True).language == "it"


@pytest.mark.parametrize("bad", ["fr", "", "IT", None, 5, ["it"]])
def test_post_language_rejects_anything_else(tmp_path, bad):
    config.set_language("en")
    r = _client(tmp_path).post("/api/language", json={"lang": bad})
    assert r.status_code == 422
    assert config.load_config(reload=True).language == "en"


def test_post_language_touches_nothing_else(tmp_path):
    config.set_language("en")
    before = config.load_config(reload=True)
    r = _client(tmp_path).post("/api/language", json={"lang": "it", "voice": {"enabled": False},
                                                      "data": {"laps_dir": "x"}})
    assert r.status_code == 200
    after = config.load_config(reload=True)
    assert after.language == "it"
    assert after.voice == before.voice and after.data == before.data


# --- i18n.js: esegue il vero file in node -----------------------------------
_HARNESS = r"""
const fs = require("fs");
const [path, injected, stored] = process.argv.slice(2);
const posts = [];
global.window = {};
if (injected !== "-") window.HONE_LANG = injected;
global.localStorage = { getItem: () => (stored === "-" ? null : stored), setItem() {} };
global.fetch = (url, opt) => { posts.push([url, opt && opt.body]); return Promise.resolve({ ok: true }); };
global.document = { readyState: "complete", querySelectorAll: () => [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(path, "utf8"));
const out = { lang: window.HoneI18n.lang, label: window.HoneI18n.t("lang.label") };
window.HoneI18n.set("it");
out.after = window.HoneI18n.lang;
out.posts = posts;
console.log(JSON.stringify(out));
"""


def _run(tmp_path, injected, stored):
    script = tmp_path / "h.js"
    script.write_text(_HARNESS, encoding="utf-8")
    run = subprocess.run([_NODE, str(script), str(_WEB / "i18n.js"), injected, stored],
                         capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire il JS")
def test_the_injected_language_beats_a_stored_one(tmp_path):
    out = _run(tmp_path, "it", "en")
    assert out["lang"] == "it" and out["label"] == "Lingua"


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire il JS")
def test_the_stored_language_is_ignored_when_nothing_is_injected(tmp_path):
    assert _run(tmp_path, "-", "it")["lang"] == "en"


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire il JS")
def test_the_selector_changes_the_app_language(tmp_path):
    out = _run(tmp_path, "en", "-")
    assert out["after"] == "it"
    assert [[u, json.loads(b)] for u, b in out["posts"]] == [["/api/language", {"lang": "it"}]]


def test_i18n_js_no_longer_reads_the_browser_store():
    src = (_WEB / "i18n.js").read_text(encoding="utf-8")
    assert "localStorage" not in re.sub(r"//.*", "", src)
