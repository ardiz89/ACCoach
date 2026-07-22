"""Data model for a recorded lap.

A :class:`Lap` is the unit the coaching layer compares against: a sequence of
:class:`LapSample` frames captured around the track, plus enough metadata to
know *which* lap it is (car, track, time) and whether it's trustworthy.

Samples are keyed by ``pos`` — the normalized 0..1 position around the track —
rather than by wall-clock time. That's deliberate: to compare two laps we line
them up by *where on the track* the car is, not by how long each lap took, so a
faster and a slower lap through the same corner are directly comparable.

Channels
--------
Beyond the basic inputs we record the signals coaching actually needs to explain
*why* time was lost: per-wheel ``slip`` (lock-ups, wheelspin, under/oversteer),
``abs``/``tc`` intervention, ``yaw_rate`` (rotation vs steering), and tyre core
temps. Anything cheap to capture now and expensive to add later (it would mean a
re-drive) is worth storing.

Serialization is **self-describing and forward/backward compatible**: each file
stores its ``fields`` list, and :meth:`Lap.from_dict` maps columns back to
attributes *by name*. So a v1 lap (10 channels) still loads against this v2 model
(missing channels default to zero), and a future v3 reader will still load v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..telemetry.snapshot import SessionType, TelemetrySnapshot

# Bump when the *writer* adds/changes channels. Readers tolerate older versions
# because columns are matched by name via the stored ``fields`` list.
# v5: lap-level clean flag + track conditions (air/road temp, grip, compound).
# v6: per-wheel physical slip_ratio + tyre_pressure (reliable lock/spin & hot
#     pressures offline — the raw wheel_slip channel is car-dependent).
# v7: lap-level `source` ("own" / "pro") so an imported PRO reference is a
#     first-class benchmark level, distinct from the driver's own laps.
# v8: `lost_at` — WHERE the lap stopped counting. `clean=False` said a lap was
#     thrown away without ever saying at which corner, which is the only part the
#     driver can do anything about.
SCHEMA_VERSION = 8

# Fixed serialization order for a LapSample, written into every file. Per-wheel
# channels are flattened with [fl, fr, rl, rr] suffixes.
SAMPLE_FIELDS = (
    "t_ms",          # ms since the lap started (from the sim's current-lap timer)
    "pos",           # normalized track position 0..1
    "speed_kmh",
    "throttle",      # 0..1
    "brake",         # 0..1
    "steer_angle",   # radians, +left
    "gear",          # "R" / "N" / "1".. as shown to the driver
    "rpm",
    "g_lat",         # lateral G
    "g_long",        # longitudinal G (+accel / -brake)
    "slip_fl", "slip_fr", "slip_rl", "slip_rr",   # per-wheel slip
    "abs_active",    # 0..1 ABS intervention
    "tc_active",     # 0..1 TC intervention
    "yaw_rate",      # rad/s about the vertical axis (rotation)
    "tyre_fl", "tyre_fr", "tyre_rl", "tyre_rr",   # tyre core temp, deg C
    "car_x", "car_z",   # world ground-plane position, for the track map (v3)
    "current_sector",   # 0-based sim sector, for real sector splits (v4); -1 unknown
    "sr_fl", "sr_fr", "sr_rl", "sr_rr",           # physical slip ratio per wheel (v6)
    "press_fl", "press_fr", "press_rl", "press_rr",  # tyre pressure psi per wheel (v6)
)

# Defaults for channels absent from an older file, keyed by field name.
_Z4 = (0.0, 0.0, 0.0, 0.0)


def strip_leading_wrap(samples: list["LapSample"]) -> list["LapSample"]:
    """Drop leading pre-line wrap frames from a lap.

    At the start/finish crossing the sim bumps its lap counter one frame before
    it wraps ``normalizedCarPosition`` from ~1.0 back to 0.0, so the first sample
    of a lap can still read ~1.0. That single high ``pos`` is poison to any
    strictly-forward position filter (``Reference``, ``detect_corners``,
    ``sector_times``): it seeds the filter near 1.0 and every real sample after it
    — all lower — is then rejected, collapsing the lap to one point (``usable``
    False, zero corners). We identify such a frame precisely: a *leading* sample
    that is both high and immediately followed by a lower ``pos`` (the wrap
    discontinuity). A lap that legitimately starts mid-track (a partial in-lap)
    rises monotonically instead, so it's left untouched.
    """
    i = 0
    n = len(samples)
    while i < n - 1 and samples[i].pos > 0.5 and samples[i].pos > samples[i + 1].pos:
        i += 1
    return samples[i:] if i else samples


@dataclass(slots=True)
class LapSample:
    """One frame of a lap, the set coaching/comparison needs."""

    t_ms: int
    pos: float
    speed_kmh: float
    throttle: float
    brake: float
    steer_angle: float
    gear: str
    rpm: int
    g_lat: float
    g_long: float
    wheel_slip: tuple[float, float, float, float] = _Z4
    abs_active: float = 0.0
    tc_active: float = 0.0
    yaw_rate: float = 0.0
    tyre_core_temp: tuple[float, float, float, float] = _Z4
    car_x: float = 0.0
    car_z: float = 0.0
    current_sector: int = -1
    slip_ratio: tuple[float, float, float, float] = _Z4
    tyre_pressure: tuple[float, float, float, float] = _Z4

    @staticmethod
    def from_snapshot(s: TelemetrySnapshot) -> "LapSample":
        return LapSample(
            t_ms=int(s.current_lap_ms),
            pos=s.lap_position,
            speed_kmh=s.speed_kmh,
            throttle=s.throttle,
            brake=s.brake,
            steer_angle=s.steer_angle,
            gear=s.gear,
            rpm=s.rpm,
            g_lat=s.accel_g[0],
            g_long=s.accel_g[2],
            wheel_slip=s.wheel_slip,
            abs_active=s.abs_active,
            tc_active=s.tc_active,
            yaw_rate=s.yaw_rate,
            tyre_core_temp=s.tyre_core_temp,
            car_x=s.car_x,
            car_z=s.car_z,
            current_sector=s.current_sector,
            slip_ratio=s.slip_ratio,
            tyre_pressure=s.tyre_pressure,
        )

    def as_row(self) -> list:
        return [
            self.t_ms,
            round(self.pos, 5),
            round(self.speed_kmh, 2),
            round(self.throttle, 4),
            round(self.brake, 4),
            round(self.steer_angle, 4),
            self.gear,
            self.rpm,
            round(self.g_lat, 3),
            round(self.g_long, 3),
            round(self.wheel_slip[0], 3), round(self.wheel_slip[1], 3),
            round(self.wheel_slip[2], 3), round(self.wheel_slip[3], 3),
            round(self.abs_active, 3),
            round(self.tc_active, 3),
            round(self.yaw_rate, 4),
            round(self.tyre_core_temp[0], 1), round(self.tyre_core_temp[1], 1),
            round(self.tyre_core_temp[2], 1), round(self.tyre_core_temp[3], 1),
            round(self.car_x, 2), round(self.car_z, 2),
            self.current_sector,
            round(self.slip_ratio[0], 3), round(self.slip_ratio[1], 3),
            round(self.slip_ratio[2], 3), round(self.slip_ratio[3], 3),
            round(self.tyre_pressure[0], 2), round(self.tyre_pressure[1], 2),
            round(self.tyre_pressure[2], 2), round(self.tyre_pressure[3], 2),
        ]

    @staticmethod
    def from_named(fields: list[str], row: list) -> "LapSample":
        """Reconstruct from a row using its file's field names (version-tolerant)."""
        m = dict(zip(fields, row))

        def f(name: str, default: float = 0.0) -> float:
            v = m.get(name, default)
            return float(v) if v is not None else default

        return LapSample(
            t_ms=int(m.get("t_ms", 0) or 0),
            pos=f("pos"),
            speed_kmh=f("speed_kmh"),
            throttle=f("throttle"),
            brake=f("brake"),
            steer_angle=f("steer_angle"),
            gear=str(m.get("gear", "N")),
            rpm=int(m.get("rpm", 0) or 0),
            g_lat=f("g_lat"),
            g_long=f("g_long"),
            wheel_slip=(f("slip_fl"), f("slip_fr"), f("slip_rl"), f("slip_rr")),
            abs_active=f("abs_active"),
            tc_active=f("tc_active"),
            yaw_rate=f("yaw_rate"),
            tyre_core_temp=(f("tyre_fl"), f("tyre_fr"), f("tyre_rl"), f("tyre_rr")),
            car_x=f("car_x"),
            car_z=f("car_z"),
            current_sector=int(m["current_sector"]) if m.get("current_sector") is not None else -1,
            slip_ratio=(f("sr_fl"), f("sr_fr"), f("sr_rl"), f("sr_rr")),
            tyre_pressure=(f("press_fl"), f("press_fr"), f("press_rl"), f("press_rr")),
        )


@dataclass(slots=True)
class Lap:
    """A full recorded lap: metadata plus position-ordered samples."""

    car_model: str
    track: str
    session: SessionType
    lap_time_ms: int
    valid: bool                     # "complete" — started at a start/finish crossing
    recorded_utc: str = ""          # ISO-8601, set by the recorder/storage layer
    schema_version: int = SCHEMA_VERSION
    samples: list[LapSample] = field(default_factory=list)
    # --- v5: trustworthiness + conditions (separate from `valid`/complete) ---
    # clean is None when unknown (legacy files, or a sim that doesn't expose the
    # track-limits signal). A reference lap must be valid AND not clean==False.
    clean: bool | None = None
    # --- v8: where it went wrong, 0..1 track position; None if it didn't (or if
    # the lap predates the field). The first point at which the lap stopped
    # counting, not the worst one — after that the lap was already gone.
    lost_at: float | None = None
    air_temp: float = 0.0           # deg C
    road_temp: float = 0.0          # deg C
    grip: float = 0.0               # 0..1 surface grip
    tyre_compound: str = ""
    # --- v7: provenance — "own" (driver's lap) or "pro" (imported benchmark) ---
    source: str = "own"

    @property
    def duration_s(self) -> float:
        return self.lap_time_ms / 1000.0

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "car_model": self.car_model,
            "track": self.track,
            "session": int(self.session),
            "lap_time_ms": self.lap_time_ms,
            "valid": self.valid,
            "clean": self.clean,        # True / False / null (unknown)
            "lost_at": (None if self.lost_at is None else round(self.lost_at, 4)),
            "air_temp": round(self.air_temp, 1),
            "road_temp": round(self.road_temp, 1),
            "grip": round(self.grip, 4),
            "tyre_compound": self.tyre_compound,
            "source": self.source,
            "recorded_utc": self.recorded_utc,
            "fields": list(SAMPLE_FIELDS),
            "samples": [s.as_row() for s in self.samples],
        }

    @staticmethod
    def from_dict(d: dict) -> "Lap":
        try:
            session = SessionType(int(d.get("session", -1)))
        except ValueError:
            session = SessionType.UNKNOWN
        # Older files predate the self-describing ``fields`` list; fall back to
        # the v1 channel order so they still load.
        fields = d.get("fields") or list(SAMPLE_FIELDS[:10])
        # clean: absent OR null -> None (unknown); never coerce a missing flag to
        # False, so a legacy lap stays "unknown" (still eligible) rather than dirty.
        raw_clean = d.get("clean")
        clean = None if raw_clean is None else bool(raw_clean)
        return Lap(
            car_model=str(d.get("car_model", "")),
            track=str(d.get("track", "")),
            session=session,
            lap_time_ms=int(d.get("lap_time_ms", 0)),
            valid=bool(d.get("valid", False)),
            recorded_utc=str(d.get("recorded_utc", "")),
            schema_version=int(d.get("schema", 1)),
            # Sanitize on load: drop any leading pre-line wrap frame (pos~1.0
            # recorded one frame before the sim reset it to 0). Older laps on disk
            # carry it and it poisons every position-indexed consumer downstream
            # (the debrief credited a full lap's time to the last corner, the map's
            # first segment jumped across the line). New laps are already clean —
            # the recorder now drops it at the source.
            samples=strip_leading_wrap(
                [LapSample.from_named(fields, r) for r in d.get("samples", [])]),
            clean=clean,
            # Absent on pre-v8 files. "We never recorded where" — which is not the
            # same as "nowhere", so it stays None rather than becoming a position.
            lost_at=(None if d.get("lost_at") is None else float(d["lost_at"])),
            air_temp=float(d.get("air_temp", 0.0) or 0.0),
            road_temp=float(d.get("road_temp", 0.0) or 0.0),
            grip=float(d.get("grip", 0.0) or 0.0),
            tyre_compound=str(d.get("tyre_compound", "")),
            # Absent on pre-v7 files → "own" (the safe default; only an explicit
            # import marks a lap "pro").
            source=str(d.get("source") or "own"),
        )
