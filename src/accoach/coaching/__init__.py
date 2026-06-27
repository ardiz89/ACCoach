"""Coaching: turn the live delta into spoken suggestions."""

from __future__ import annotations

from .advisor import SetupAdvisor
from .analyzer import CoachAnalyzer
from .balance import BalanceDetector
from .braking import BrakingDetector
from .cue import Cue, CueCategory
from .debrief import (
    CornerLoss,
    LapDebrief,
    build_lap_debrief,
    format_debrief,
    lap_time_consistency,
)
from .events import EventDetector
from .fuel import FuelEngineer
from .gears import GearDetector
from .pressure import PressureAdvisor
from .scheduler import CueScheduler
from .tyretemp import TyreTempAdvisor
from .voice import Voice

__all__ = [
    "CoachAnalyzer",
    "Cue",
    "CueCategory",
    "CornerLoss",
    "LapDebrief",
    "build_lap_debrief",
    "format_debrief",
    "lap_time_consistency",
    "EventDetector",
    "BalanceDetector",
    "BrakingDetector",
    "GearDetector",
    "FuelEngineer",
    "SetupAdvisor",
    "PressureAdvisor",
    "TyreTempAdvisor",
    "CueScheduler",
    "Voice",
]
