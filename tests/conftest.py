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


# --- i test non scrivono nella cartella dati del pilota ----------------------
# Scoperto il 19/09 **mentre il pilota girava a Suzuka**: le righe
# «=== ACCoach starting ===» e i «trailing garbage» che comparivano nel suo log
# dal vivo erano le mie esecuzioni della suite. `setup_logging()` apre un
# RotatingFileHandler su `logs_dir()`, che e' `~/Documents/ACCoach/logs`: la
# stessa cartella che l'app vera sta scrivendo, e la stessa che `logs --zip`
# impacchetta per una segnalazione.
#
# Due danni, e il secondo e' peggiore del primo: la suite sporca l'unica traccia
# che abbiamo di una sessione in pista, e la sporca con righe che sembrano
# l'app. Ho passato dieci minuti a chiedermi perche' il coach si riavviasse.
#
# La trappola da conoscere: `logging_setup` fa `from .paths import logs_dir`
# **all'import**, quindi rimpiazzare `paths.logs_dir` non lo sposta -- il nome e'
# gia' legato. Per questo si rimpiazza in **ogni** modulo che se l'e' portato a
# casa, cercandoli invece di elencarli: un elenco scritto a mano si dimentica il
# modulo aggiunto domani, ed e' la famiglia di difetto che questo progetto paga
# piu' spesso.
@pytest.fixture(autouse=True)
def _logs_nella_sandbox(tmp_path_factory, monkeypatch):
    import sys as _sys

    from accoach import paths as _paths

    finta = tmp_path_factory.mktemp("logs")
    monkeypatch.setattr(_paths, "logs_dir", lambda: finta)
    for nome, modulo in list(_sys.modules.items()):
        if not nome.startswith("accoach") or modulo is _paths:
            continue
        if getattr(modulo, "logs_dir", None) is not None:
            monkeypatch.setattr(modulo, "logs_dir", lambda: finta, raising=False)
    yield
