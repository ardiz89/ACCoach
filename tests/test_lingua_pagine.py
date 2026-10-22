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
window.HoneI18n.set("it").then(() => {
  out.after = window.HoneI18n.lang;
  out.posts = posts;
  console.log(JSON.stringify(out));
});
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


# --- il config non si perde (giro di correzioni 1) ---------------------------
_RICH = ('language = "it"   # lingua\nlan = true\n[data]\nlaps_dir = "D:/miei_giri"\n'
         '[voice]\nmale = true\n')


def test_a_post_on_an_unreadable_config_refuses_and_writes_nothing(tmp_path):
    """L'hub può essere colto a metà scrittura, o il file ha un refuso: il POST
    non deve rimpiazzarlo coi default (lan, laps_dir, male azzerati)."""
    path = config.config_path()
    broken = 'language = "it"\nlan = tr'
    path.write_text(broken, encoding="utf-8")
    before = path.read_bytes()
    r = _client(tmp_path).post("/api/language", json={"lang": "en"})
    assert r.status_code == 503
    assert path.read_bytes() == before


def test_a_post_changes_only_the_language_line(tmp_path):
    path = config.config_path()
    path.write_text(_RICH, encoding="utf-8")
    config.load_config(reload=True)
    assert _client(tmp_path).post("/api/language", json={"lang": "en"}).status_code == 200
    assert path.read_text(encoding="utf-8") == _RICH.replace('"it"', '"en"')


def test_a_post_adds_the_line_when_the_file_has_none(tmp_path):
    path = config.config_path()
    path.write_text('lan = true\n[voice]\nmale = true\n', encoding="utf-8")
    assert _client(tmp_path).post("/api/language", json={"lang": "it"}).status_code == 200
    cfg = config.load_config(reload=True)
    assert cfg.language == "it" and cfg.lan is True and cfg.voice.male is True


def test_a_hub_save_does_not_undo_the_pages_choice(tmp_path):
    """L'hub carica il config all'avvio (lingua «it») e salva quando cambia
    un'altra cosa: non deve riscrivere la lingua che la pagina ha cambiato.
    La pagina qui è un altro processo: cambia il FILE, non la nostra cache."""
    path = config.config_path()
    path.write_text(_RICH, encoding="utf-8")
    hub_cfg = config.load_config(reload=True)           # come l'hub all'avvio
    path.write_text(_RICH.replace('"it"', '"en"'), encoding="utf-8")
    assert hub_cfg.language == "it"                     # la sua copia è vecchia
    hub_cfg.voice.rate = 120                            # l'hub cambia altro e salva
    assert config.save_config(hub_cfg) is True
    fresh = config.load_config(reload=True)
    assert fresh.language == "en" and fresh.voice.rate == 120
    assert fresh.lan is True and fresh.data.laps_dir == "D:/miei_giri"


def test_a_hub_save_still_saves_what_it_changed_over_an_outside_edit(tmp_path):
    path = config.config_path()
    path.write_text(_RICH, encoding="utf-8")
    cfg = config.load_config(reload=True)
    path.write_text(_RICH.replace("male = true", "male = false"), encoding="utf-8")
    cfg.lan = False
    config.save_config(cfg)
    fresh = config.load_config(reload=True)
    assert fresh.lan is False and fresh.voice.male is False


def test_save_config_does_not_overwrite_an_unreadable_file():
    path = config.config_path()
    path.write_text('lan = tr', encoding="utf-8")
    cfg = config.Config()
    cfg.voice.rate = 99
    config.save_config(cfg)
    assert path.read_text(encoding="utf-8") == 'lan = tr'


def test_save_config_writes_atomically(monkeypatch):
    import os
    seen = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append((str(a), str(b))), real(a, b))[1])
    config.save_config(config.load_config(reload=True))
    assert seen and seen[0][1] == str(config.config_path()) and seen[0][0] != seen[0][1]


def test_serving_a_page_does_not_replace_the_shared_config(tmp_path):
    path = config.config_path()
    path.write_text(_RICH, encoding="utf-8")
    cached = config.load_config(reload=True)
    path.write_text('language = "it"\nlan = tr', encoding="utf-8")   # a metà scrittura
    html = _client(tmp_path).get("/engineer").text
    assert config.load_config() is cached and cached.lan is True
    assert 'window.HONE_LANG = "it"' in html     # ripiego: la lingua che avevamo


def test_pages_are_served_no_cache(tmp_path):
    assert _client(tmp_path).get("/engineer").headers["cache-control"] == "no-cache"


def test_a_page_without_i18n_keeps_its_own_language(tmp_path):
    config.set_language("en")
    html = _client(tmp_path).get("/test").text
    assert '<html lang="it">' in html and "HONE_LANG" not in html


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire il JS")
def test_a_refused_change_puts_the_selector_back(tmp_path):
    prog = r"""
const fs = require("fs");
global.window = { HONE_LANG: "en" };
const sel = { value: "it", className: "lang-select" };
global.fetch = () => Promise.resolve({ ok: false });
let reloaded = false;
global.location = { reload() { reloaded = true; } };
global.document = { readyState: "complete", querySelectorAll: (q) => q === "select.lang-select" ? [sel] : [],
                    querySelector: () => null, documentElement: {} };
eval(fs.readFileSync(process.argv[2], "utf8"));
window.HoneI18nRerender = () => { reloaded = true; };
window.HoneI18n.set("it");
setTimeout(() => console.log(JSON.stringify({ lang: window.HoneI18n.lang, sel: sel.value, reloaded })), 20);
"""
    script = tmp_path / "s.js"
    script.write_text(prog, encoding="utf-8")
    run = subprocess.run([_NODE, str(script), str(_WEB / "i18n.js")],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out == {"lang": "en", "sel": "en", "reloaded": False}



# --- giro 2 -------------------------------------------------------------------
def test_a_single_quoted_language_line_is_edited_not_duplicated(tmp_path):
    path = config.config_path()
    path.write_text("language = 'it'\nlan = true\n", encoding="utf-8")
    assert _client(tmp_path).post("/api/language", json={"lang": "en"}).status_code == 200
    assert path.read_text(encoding="utf-8") == 'language = "en"\nlan = true\n'


def test_a_language_key_in_a_section_is_not_the_apps(tmp_path):
    path = config.config_path()
    text = '[voice]\nlanguage = "it"\nmale = true\n'
    path.write_text(text, encoding="utf-8")
    r = _client(tmp_path).post("/api/language", json={"lang": "en"})
    assert r.status_code == 200
    assert path.read_text(encoding="utf-8") == 'language = "en"\n' + text
    assert config.load_config(reload=True).language == "en"


def test_if_the_result_does_not_carry_the_language_nothing_is_written(tmp_path, monkeypatch):
    """Rete di sicurezza: dopo la sostituzione si rilegge il file e si controlla."""
    path = config.config_path()
    path.write_text('language = "it"\n', encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(config.re, "subn", lambda *a, **k: (a[2], 1))   # «riuscita» ma vuota
    r = _client(tmp_path).post("/api/language", json={"lang": "en"})
    assert r.status_code == 503 and path.read_bytes() == before


def test_save_config_says_whether_it_saved():
    path = config.config_path()
    cfg = config.load_config(reload=True)
    cfg.voice.rate = 99
    assert config.save_config(cfg) is True
    path.write_text('lan = tr', encoding="utf-8")
    assert config.save_config(cfg) is False


def test_save_config_returns_false_on_an_os_error(monkeypatch):
    cfg = config.load_config(reload=True)
    cfg.voice.rate = 98

    def boom(*a):
        raise OSError("disk")
    monkeypatch.setattr(config, "_atomic_write", boom)
    assert config.save_config(cfg) is False


def test_the_atomic_write_retries_when_windows_refuses_the_replace(monkeypatch):
    import os
    real, calls = os.replace, []

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("file in uso")
        real(a, b)
    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(config.time, "sleep", lambda s: None)
    assert config.save_config(config.load_config(reload=True)) is True
    assert len(calls) == 3


def _hub(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from accoach import hub_home, launcher
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(hub_home, "load_home_data",
                        lambda *a, **k: hub_home.HomeData(status="empty"))
    return launcher.MainWindow()


def _panel(win, cls):
    return next(p for p in win._panels if type(p).__name__ == cls)


def test_the_settings_note_says_when_the_save_failed(monkeypatch):
    from accoach.i18n import t
    win = _hub(monkeypatch)
    try:
        panel = _panel(win, "SettingsPanel")
        config.config_path().write_text('lan = tr', encoding="utf-8")
        panel._do_save()
        assert panel._saved_note.text() == t("set.save_failed")
        assert t("set.save_failed") != "set.save_failed"
        assert config.config_path().read_text(encoding="utf-8") == 'lan = tr'
    finally:
        win.close()


def test_the_lan_checkbox_goes_back_when_the_save_failed(monkeypatch):
    win = _hub(monkeypatch)
    try:
        panel = _panel(win, "DevicesPanel")
        config.config_path().write_text('lan = tr', encoding="utf-8")
        panel._lan.setChecked(True)
        assert panel._lan.isChecked() is False
    finally:
        win.close()


def test_the_hub_follows_a_language_changed_by_a_page(monkeypatch):
    win = _hub(monkeypatch)
    try:
        panel = _panel(win, "SettingsPanel")
        path = config.config_path()
        config.set_language("it")
        win._lang.setCurrentIndex(win._lang.findData("it"))
        path.write_text(path.read_text(encoding="utf-8").replace(
            'language = "it"', 'language = "en"'), encoding="utf-8")   # una pagina, altro processo
        panel._do_save()
        assert win._lang.currentData() == "en"
        assert panel._saved_note.text() == "Saved."
    finally:
        win.close()
