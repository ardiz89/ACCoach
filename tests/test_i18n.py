"""i18n: language setting + spoken-cue translation (Italian source -> English)."""
import pytest

from accoach import config, i18n


@pytest.fixture(autouse=True)
def _reset_config_cache():
    config._cache = None
    yield
    config._cache = None


def test_cue_text_translates_static_to_english():
    assert i18n.cue_text("Bloccaggio, alleggerisci il freno", "en") == \
        "Lock-up — ease off the brake"
    # Italian is the source: asking for Italian returns it unchanged.
    assert i18n.cue_text("Bloccaggio, alleggerisci il freno", "it") == \
        "Bloccaggio, alleggerisci il freno"


def test_cue_text_translates_numeric_templates():
    assert i18n.cue_text("Stai perdendo 3 decimi qui", "en") == "Losing 3 tenths here"
    assert i18n.cue_text("Benzina per circa 2 giri.", "en") == "Fuel for about 2 laps."


def test_cue_text_unknown_passes_through():
    assert i18n.cue_text("frase sconosciuta", "en") == "frase sconosciuta"


def test_current_language_defaults_to_en(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    assert i18n.current_language() == "en"


def test_set_language_persists_and_switches(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: cfgfile)
    config.load_config(reload=True)
    config.set_language("it")
    assert i18n.current_language() == "it"                 # cache updated
    assert 'language = "it"' in cfgfile.read_text(encoding="utf-8")  # persisted
    # …and a fresh load from disk keeps it.
    config.load_config(reload=True)
    assert config.load_config().language == "it"
