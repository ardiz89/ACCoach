"""Turn engine state into plain JSON-able dicts for frontends.

Kept out of the core dataclasses on purpose: telemetry/coaching types stay clean
and UI-agnostic, and every presentation concern (rounding, formatted lap-time
strings, which fields a HUD needs) lives here. The overlay and the analysis app
both consume :func:`state_to_dict`.
"""

from __future__ import annotations

from .coaching import Cue
from .comparison import DeltaState, format_delta
from .engine import EngineState
from .telemetry import TelemetrySnapshot, format_lap_time


def snapshot_to_dict(s: TelemetrySnapshot) -> dict:
    return {
        "connected": s.connected,
        "status": s.status.name,
        "session": s.session.name,
        "car": s.car_model,
        "track": s.track,
        "speed_kmh": round(s.speed_kmh, 1),
        "gear": s.gear,
        "rpm": s.rpm,
        "max_rpm": s.max_rpm,
        "throttle": round(s.throttle, 3),
        "brake": round(s.brake, 3),
        "in_pit": s.in_pit,
        "lap_position": round(s.lap_position, 4),
        "aids": {
            "tc": s.tc_level,            # current selected level, -1 if unknown
            "abs": s.abs_level,
            "engine_map": s.engine_map,
        },
        # Per-wheel [FL, FR, RL, RR]. The pilot's #1 live readout: tyre temps and
        # pressures decide whether a "push" is setup or just a cold/over-pressure tyre.
        "tyres": {
            "temp": [round(t, 1) for t in s.tyre_core_temp],
            "pressure": [round(p, 1) for p in s.tyre_pressure],
        },
        "lap": {
            "current_ms": s.current_lap_ms,
            "last_ms": s.last_lap_ms,
            "best_ms": s.best_lap_ms,
            "completed": s.completed_laps,
            "current": format_lap_time(s.current_lap_ms),
            "last": format_lap_time(s.last_lap_ms),
            "best": format_lap_time(s.best_lap_ms),
        },
    }


def delta_to_dict(d: DeltaState | None) -> dict | None:
    if d is None:
        return None
    return {
        "ms": round(d.delta_ms, 1),
        "s": round(d.delta_ms / 1000.0, 3),
        "text": format_delta(d.delta_ms),
        "ahead": d.ahead,
        "local_ms": round(d.local_delta_ms, 1),     # gaining(-)/losing(+) right now
        "local_s": round(d.local_delta_ms / 1000.0, 3),
        "local_losing": d.local_losing,
        "brake_in_m": d.brake_in_m,                  # metres to ref's next braking point
        "predicted_ms": int(d.predicted_lap_ms),
        "predicted": format_lap_time(int(d.predicted_lap_ms)),
        "reference_ms": d.reference_lap_ms,
        "reference": format_lap_time(d.reference_lap_ms),
    }


def cue_to_dict(c: Cue | None) -> dict | None:
    if c is None:
        return None
    return {
        "category": c.category.value,
        "message": c.message,
        "priority": round(c.priority, 1),
        "segment": c.segment,
    }


def state_to_dict(st: EngineState) -> dict:
    """The full per-tick payload sent to frontends."""
    return {
        **snapshot_to_dict(st.snapshot),
        "delta": delta_to_dict(st.delta),
        "cue": cue_to_dict(st.spoken),
        "saved_laps": st.saved_laps,
        "reference_ms": st.reference_ms,
        "history": st.history,
        "engineer": st.engineer,
        "focus": st.focus,
    }
