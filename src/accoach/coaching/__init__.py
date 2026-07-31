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
    category_words,
    format_debrief,
    lap_time_consistency,
)
from .events import EventDetector
from .flow import FlowStep, build_flow
from .plan import Goal, GoalProgress, TrainingPlan, measure, propose
from .focus import Focus, FocusCoach, FocusKind, FocusReport, format_focus
from .fuel import FuelEngineer
from .gears import GearDetector
from .pressure import PressureAdvisor
from .scheduler import CueScheduler
from .trends import (
    BenchmarkLevel,
    LossTrend,
    benchmark_levels,
    classify_losses,
)
from .training import (
    CornerFacts,
    GlossaryEntry,
    Programme,
    build_gap,
    build_programme,
    dominant_phase,
    glossary_for,
    trail_brake_for,
)
from .tyretemp import TyreTempAdvisor
from .voice import Voice

__all__ = [
    "CoachAnalyzer",
    "Cue",
    "CueCategory",
    "CornerLoss",
    "LapDebrief",
    "build_lap_debrief",
    "category_words",
    "format_debrief",
    "lap_time_consistency",
    "FlowStep",
    "build_flow",
    "Goal",
    "GoalProgress",
    "TrainingPlan",
    "propose",
    "measure",
    "Focus",
    "FocusCoach",
    "FocusKind",
    "FocusReport",
    "format_focus",
    "EventDetector",
    "BalanceDetector",
    "BrakingDetector",
    "GearDetector",
    "FuelEngineer",
    "SetupAdvisor",
    "PressureAdvisor",
    "TyreTempAdvisor",
    "CueScheduler",
    "BenchmarkLevel",
    "LossTrend",
    "benchmark_levels",
    "classify_losses",
    "CornerFacts",
    "GlossaryEntry",
    "Programme",
    "build_gap",
    "build_programme",
    "dominant_phase",
    "glossary_for",
    "trail_brake_for",
    "Voice",
]
