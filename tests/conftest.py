"""Shared pytest fixtures."""
import pytest

from accoach import config


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path_factory, monkeypatch):
    """Pin the config to defaults (language 'en') for every test.

    Most tests assert English UI / debrief strings, matching CI's fresh config.
    Without this they'd fail on a dev machine whose
    ``~/Documents/ACCoach/config.toml`` is set to Italian (e.g. after switching
    the language in the launcher). Each test gets a fresh default config, fully
    isolated from whatever is on disk. Tests that need a specific config just
    re-point ``config.config_path`` themselves (the override wins for that test).
    """
    cfg_file = tmp_path_factory.mktemp("cfg") / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: cfg_file)
    config.load_config(reload=True)
    yield
