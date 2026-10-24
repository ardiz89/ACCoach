"""config.toml salvato da Blocco Note si legge lo stesso.

Il 24/10 un `config.toml` con il BOM UTF-8 in testa (Blocco Note e PowerShell 5
lo mettono) veniva scartato intero e in silenzio: lingua inglese e porte
predefinite, e i server di prova finivano sulle porte del pilota. Il BOM non e'
un errore del pilota, quindi si legge; un file davvero rotto invece si dice.
"""
from accoach import config

TOML = 'language = "it"\n\n[server]\nport = 8797\n\n[web]\nport = 8798\n'


def _load(tmp_path, monkeypatch, data: bytes):
    path = tmp_path / "config.toml"
    path.write_bytes(data)
    monkeypatch.setattr(config, "config_path", lambda: path)
    return config.load_config(reload=True)


def test_a_utf8_bom_is_not_an_error(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, b"\xef\xbb\xbf" + TOML.encode("utf-8"))
    assert (cfg.language, cfg.server.port, cfg.web.port) == ("it", 8797, 8798)
    assert config.config_problem() is None


def test_notepad_unicode_utf16_is_read_too(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, TOML.encode("utf-16"))
    assert (cfg.language, cfg.server.port) == ("it", 8797)


def test_the_page_language_reader_accepts_the_bom_as_well(tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, b"\xef\xbb\xbf" + TOML.encode("utf-8"))
    assert config.read_language() == "it"


def test_setting_the_language_keeps_working_on_a_bom_file(tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, b"\xef\xbb\xbf" + TOML.encode("utf-8"))
    config.write_language("en")
    assert config.read_language() == "en"


def test_a_really_broken_file_is_reported_not_hidden(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, b'language = \n')
    assert cfg.language == config.Config().language
    assert config.config_problem()
    config.config_path().write_text(TOML, encoding="utf-8")
    config.load_config(reload=True)
    assert config.config_problem() is None
