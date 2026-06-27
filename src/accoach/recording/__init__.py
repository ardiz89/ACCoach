"""Lap recording: capture, model, and persist laps for reference comparison."""

from __future__ import annotations

from .lap import Lap, LapSample
from .recorder import LapRecorder
from .storage import (
    DEFAULT_LAPS_DIR,
    describe_lap,
    find_reference_lap,
    list_lap_files,
    load_lap,
    save_lap,
)

__all__ = [
    "Lap",
    "LapSample",
    "LapRecorder",
    "DEFAULT_LAPS_DIR",
    "describe_lap",
    "find_reference_lap",
    "list_lap_files",
    "load_lap",
    "save_lap",
]
