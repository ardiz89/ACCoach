"""Clean, game-agnostic telemetry snapshot.

The rest of the application consumes :class:`TelemetrySnapshot` instead of the
raw ctypes structs, so analysis / overlay / TTS code never has to know about
memory layout. A snapshot is one coherent read of all three pages at an instant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ACStatus(IntEnum):
    OFF = 0
    REPLAY = 1
    LIVE = 2
    PAUSE = 3


class SessionType(IntEnum):
    UNKNOWN = -1
    PRACTICE = 0
    QUALIFY = 1
    RACE = 2
    HOTLAP = 3
    TIME_ATTACK = 4
    DRIFT = 5
    DRAG = 6
    HOTSTINT = 7
    HOTLAP_SUPERPOLE = 8


# gear index in the shared memory: 0 = reverse, 1 = neutral, 2 = 1st gear ...
def gear_label(raw_gear: int) -> str:
    if raw_gear == 0:
        return "R"
    if raw_gear == 1:
        return "N"
    return str(raw_gear - 1)


@dataclass(slots=True)
class TelemetrySnapshot:
    """One coherent instant of telemetry, normalized and game-agnostic."""

    # --- meta ---
    connected: bool
    status: ACStatus
    session: SessionType
    car_model: str
    track: str

    # --- driver inputs ---
    throttle: float          # 0..1
    brake: float             # 0..1
    clutch: float            # 0..1 (ACC only; 0 on AC)
    steer_angle: float       # radians, +left
    gear: str                # "R" / "N" / "1".."8"

    # --- engine / speed ---
    rpm: int
    max_rpm: int
    speed_kmh: float

    # --- dynamics ---
    accel_g: tuple[float, float, float]   # lateral, vertical, longitudinal
    yaw_rate: float                       # rad/s about the vertical axis (rotation)
    wheel_slip: tuple[float, float, float, float]
    # Physical slip ratio per wheel = (wheel surface speed - car speed) / car speed.
    # Car-agnostic: ~0 gripping, negative under lock (wheel slower), positive in
    # wheelspin. 0 below crawl speed where it isn't meaningful.
    slip_ratio: tuple[float, float, float, float]

    # --- tyres ---
    tyre_core_temp: tuple[float, float, float, float]   # deg C
    tyre_pressure: tuple[float, float, float, float]    # psi
    brake_temp: tuple[float, float, float, float]       # deg C (ACC only)

    # --- assists active ---
    abs_active: float        # 0..1 intervention
    tc_active: float         # 0..1 intervention

    # --- adjustable in-car aids (current selected levels; -1 = unknown/AC) ---
    tc_level: int            # traction-control level the driver has dialled in
    abs_level: int           # ABS level the driver has dialled in
    engine_map: int          # engine map (HUD shows +1), -1 if unknown
    brake_bias: float        # front brake bias as a raw fraction, -1.0 if unknown

    # --- timing / position ---
    current_lap_ms: int
    last_lap_ms: int
    best_lap_ms: int
    completed_laps: int
    lap_position: float      # 0..1 normalized position around the track
    fuel: float              # litres
    in_pit: bool

    # --- world position (for the track map / racing-line analysis) ---
    car_x: float             # world X (metres); 0 when unknown
    car_z: float             # world Z (metres); the second ground-plane axis

    # --- real track sectors (the sim's official splits) ---
    # current_sector is the 0-based sector the car is in; sector boundaries are
    # recovered later from where it increments around the lap. -1 / 0 when the
    # game doesn't publish sectors (e.g. some AC content) so we fall back to thirds.
    current_sector: int = -1
    sector_count: int = 0

    # --- track-limits / conditions (for clean-lap detection & reference matching) ---
    # All from the AC+ACC common prefix, so they work on both games.
    tyres_out: int = 0           # wheels currently off-track (numberOfTyresOut)
    air_temp: float = 0.0        # deg C
    road_temp: float = 0.0       # deg C
    surface_grip: float = 0.0    # 0..1 track grip
    tyre_compound: str = ""      # e.g. "dry_compound" / "wet_compound"
    penalty: int = 0             # current penalty enum (0 = none); ACC only
    # True anywhere in the pit lane, not just stopped in the box (`in_pit`). A lap
    # that touches the pit lane is not a timed lap — see LapRecorder.
    in_pit_lane: bool = False
    # Which title we're reading. Not trivia: several fields are *declared* by both
    # games and *filled* by only one (brake_temp is simulated on ACC and frozen at
    # a static value on AC), so a consumer has to know before showing a number.
    is_acc: bool = False
    # Does the sim still count the current lap? True/False on ACC, which says so
    # directly; None on AC, which doesn't have the notion and where track limits
    # are inferred from `tyres_out` instead. None means "unknown", never "valid".
    lap_valid: bool | None = None

    @staticmethod
    def disconnected() -> "TelemetrySnapshot":
        """A neutral snapshot used when the game isn't running."""
        z4 = (0.0, 0.0, 0.0, 0.0)
        return TelemetrySnapshot(
            connected=False,
            status=ACStatus.OFF,
            session=SessionType.UNKNOWN,
            car_model="",
            track="",
            throttle=0.0,
            brake=0.0,
            clutch=0.0,
            steer_angle=0.0,
            gear="N",
            rpm=0,
            max_rpm=0,
            speed_kmh=0.0,
            accel_g=(0.0, 0.0, 0.0),
            yaw_rate=0.0,
            wheel_slip=z4,
            slip_ratio=z4,
            tyre_core_temp=z4,
            tyre_pressure=z4,
            brake_temp=z4,
            abs_active=0.0,
            tc_active=0.0,
            tc_level=-1,
            abs_level=-1,
            engine_map=-1,
            brake_bias=-1.0,
            current_lap_ms=0,
            last_lap_ms=0,
            best_lap_ms=0,
            completed_laps=0,
            lap_position=0.0,
            fuel=0.0,
            in_pit=False,
            car_x=0.0,
            car_z=0.0,
            current_sector=-1,
            sector_count=0,
        )


def format_lap_time(ms: int) -> str:
    """Format milliseconds as M:SS.mmm. The games use a huge sentinel value
    (e.g. 2147483647) when no time is set."""
    if ms <= 0 or ms >= 1_000_000_000:
        return "--:--.---"
    minutes, rem = divmod(ms, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"
