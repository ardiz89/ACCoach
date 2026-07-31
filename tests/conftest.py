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


# --- riprodurre la CI su una macchina che ha i giochi installati -------------
# Un test che passa solo perche' CHI LO SCRIVE ha Assetto Corsa e' un test che
# non prova niente, e ne e' gia' passato uno: rattoppava `spline_path`, e sulla
# macchina di sviluppo tutte e 67 le piste installate finivano per puntare al
# file finto. Verde qui, rosso in CI.
#
#   HONE_NO_AC=1 python -m pytest
#
# finge una macchina senza il gioco, cioe' esattamente la CI.
import os

import pytest


@pytest.fixture(autouse=True)
def _pretend_no_game_installed(monkeypatch):
    if not os.environ.get("HONE_NO_AC"):
        yield
        return
    from accoach import trackedges as _te
    monkeypatch.setattr(_te, "tracks_dir", lambda: None)
    _te._cache.clear()
    yield
    _te._cache.clear()
