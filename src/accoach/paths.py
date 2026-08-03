"""Shared, user-writable locations for ACCoach data, logs and config.

Everything lives under ``~/Documents/ACCoach`` so the paths are identical from
source and from the frozen exe (a path relative to ``__file__`` is meaningless
once PyInstaller-frozen, and may be read-only). Single source of truth — other
modules should import from here instead of recomputing ``Path.home() / ...``.
"""

from __future__ import annotations

from pathlib import Path


def base_dir() -> Path:
    return Path.home() / "Documents" / "ACCoach"


def laps_dir() -> Path:
    """Dove stanno i giri: quella configurata, o la predefinita.

    `data.laps_dir` esisteva da tempo e **la onorava solo l'app web**: il motore
    live, il registratore, il debrief, la Home dell'hub e l'import PRO usavano
    tutti la cartella predefinita. Se lo impostavi, guidavi una sessione e aprivi
    Analisi trovavi la pagina **vuota** — mentre la Home continuava a mostrare
    quella stessa sessione, perché leggeva altrove. L'app si contraddiceva da
    sola, e il sintomo somigliava a una perdita di dati.

    La lettura sta qui e non nei chiamanti perché era proprio la dispersione il
    difetto. `load_config()` è in cache, quindi costa un accesso a dizionario.
    """
    from .config import load_config  # locale: config importa questo modulo

    try:
        configured = load_config().data.laps_dir
    except Exception:   # noqa: BLE001 - una config illeggibile non sposta i giri
        configured = ""
    return Path(configured).expanduser() if configured else base_dir() / "laps"


def logs_dir() -> Path:
    return base_dir() / "logs"


def config_path() -> Path:
    return base_dir() / "config.toml"
