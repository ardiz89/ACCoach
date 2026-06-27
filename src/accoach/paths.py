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
    return base_dir() / "laps"


def logs_dir() -> Path:
    return base_dir() / "logs"


def config_path() -> Path:
    return base_dir() / "config.toml"
