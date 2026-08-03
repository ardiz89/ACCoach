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
*why* time was lost: per-wheel ``slip_ratio`` (lock-ups, wheelspin), ``abs``/``tc``
intervention, ``yaw_rate`` (rotation vs steering), tyre core temps and pressures.
Anything cheap to capture now and expensive to add later (it would mean a
re-drive) is worth storing — but a channel that duplicates another one, and that
nothing reads, is not: see v10 in the version log below.

Serialization is **self-describing and forward/backward compatible**: each file
stores its ``fields`` list, and :meth:`Lap.from_dict` maps columns back to
attributes *by name*. So a v1 lap (10 channels) still loads against this v2 model
(missing channels default to zero), and a future v3 reader will still load v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..telemetry.snapshot import SessionType, TelemetrySnapshot

# --- how far to trust a stored `clean` flag --------------------------------
#
# On ACC, `clean` used to be decided by `numberOfTyresOut` — a field ACC
# declares and never fills (measured 2026-07-21 at Monza: four wheels off, flag
# still zero). So an old ACC lap saying "clean" is not a verdict, it is the
# absence of one, and treating it as evidence put a lap that cut the Variante
# della Roggia in charge of every Monza debrief on this machine.
#
# The line is a MOMENT, not a schema version. `isValidLap` landed in 9227401 at
# 2026-07-21 15:07 UTC; the schema only caught up the next day with v8 (`lost_at`,
# 19c27f4). Judging by schema alone would throw away the laps recorded in those
# 22 hours — the real archive holds five, and one of them says `clean=False`,
# which the inert path cannot produce and which therefore proves the flag was
# alive. So: v8 or later, OR recorded after the fix, counts as judged.
_ACC_TRACK_LIMITS_SCHEMA = 8
_ACC_TRACK_LIMITS_UTC = datetime(2026, 7, 21, 15, 7, 43, tzinfo=timezone.utc)

# What ACC writes in `tyre_compound`. Canonical on that title and only that one:
# AC mods put their own strings there ("Soft (S)", "Semislicks (SM)"). Used to
# answer "which game recorded this lap", because the lap file doesn't say. On AC
# the old rule worked — validated live at Spa — so AC laps keep their verdict.
_ACC_COMPOUNDS = ("dry_compound", "wet_compound")


def clean_verdict(clean: object, schema: int = 0, compound: str = "",
                  recorded_utc: str = "") -> int:
    """How much a stored ``clean`` flag is worth: -1 unknown / 0 dirty / 1 clean.

    The single place that rule lives, because it has to give the same answer to
    the catalog and to the catalog-less fallback scan. It didn't, once: the
    catalog demoted the lap and :func:`_find_reference_by_scan` re-elected it,
    so a locked or corrupt catalog silently restored the cut lap as the
    benchmark.

    Demotion is to **unknown**, never to dirty. We don't know those laps cut —
    we know nothing looked. Unknown still qualifies as a reference when it's all
    there is (a doubtful benchmark beats none); it just stops outranking a lap
    that was actually judged.

    A ``clean=False`` from that era is left alone: the inert path can't produce
    one, so it came from somewhere real, and discarding a positive finding
    because the instrument was unreliable in the *other* direction would throw
    away the one thing it did tell us.
    """
    if clean is None:
        return -1
    if not clean:
        return 0
    if compound not in _ACC_COMPOUNDS:
        return 1                        # AC, or a lap with no compound recorded
    if schema >= _ACC_TRACK_LIMITS_SCHEMA:
        return 1
    try:
        when = datetime.fromisoformat(recorded_utc)
    except (TypeError, ValueError):
        return -1                       # no date to appeal to: not judged
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return 1 if when >= _ACC_TRACK_LIMITS_UTC else -1

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
# v9: the in-car setup a lap was driven on (tc/abs/engine map levels, brake bias)
#     — so the race engineer's ACCEPT/REVERT verdict can check which setup the
#     laps it compared were actually on. ACC only; -1 on AC.
# v10: the raw `slip_fl..slip_rr` channel is no longer WRITTEN. v6 replaced it
#     with the physical `sr_*` slip ratio for exactly the reason it was there
#     (lock-ups and wheelspin) and nothing has read the raw one since: four of
#     the 31 columns of every frame of every lap, for no reader. Files that have
#     it still load — columns are matched by name, so the extra ones are simply
#     ignored. The live channel is untouched: `monitor` still shows it raw, which
#     is a raw dashboard's job.
# v11: `fuel` — litres in the tank, per frame. The live fuel engineer has always
#      measured the burn from this channel and spoken about it over the radio,
#      and then thrown the measurement away: the report knew nothing about fuel,
#      so "how much does a lap cost me" had no answer once you got up from the
#      wheel. One float per frame, ~2% on the file. It is a *measurement* and not
#      a strategy: what the burn means for a race is the driver's call.
SCHEMA_VERSION = 11

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
    "abs_active",    # 0..1 ABS intervention
    "tc_active",     # 0..1 TC intervention
    "yaw_rate",      # rad/s about the vertical axis (rotation)
    "tyre_fl", "tyre_fr", "tyre_rl", "tyre_rr",   # tyre core temp, deg C
    "car_x", "car_z",   # world ground-plane position, for the track map (v3)
    "current_sector",   # 0-based sim sector, for real sector splits (v4); -1 unknown
    "sr_fl", "sr_fr", "sr_rl", "sr_rr",           # physical slip ratio per wheel (v6)
    "press_fl", "press_fr", "press_rl", "press_rr",  # tyre pressure psi per wheel (v6)
    "fuel",             # litres in the tank (v11)
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


# A lap that opens at the line has a lap timer of about nothing. The line is
# detected within a frame or two, so a genuine opening sample reads tens of
# milliseconds; this is generous by an order of magnitude.
_OPEN_CLOCK_MAX_MS = 1000


def strip_trailing_wrap(samples: list["LapSample"]) -> list["LapSample"]:
    """Drop trailing samples that already belong to the next lap.

    The mirror of :func:`strip_leading_wrap`: the same one-frame disagreement at
    the line can leave the *last* sample past it, at pos≈0.000 with a lap timer
    of a few milliseconds. Measured in the archive on one lap of 59, closing at
    pos 0.0005.

    Two things it costs. Anything that walks the samples in order — the delta
    trace the report draws, for one — plots that frame at the start of the lap
    carrying end-of-lap numbers. And it makes the lap's measured duration come
    out **negative**, which silently disables the lap-time check in
    :func:`trusted_lap_ms` on precisely the laps that are ragged at the line.
    """
    n = len(samples)
    while n > 1 and samples[n - 1].pos < samples[n - 2].pos:
        n -= 1
    return samples[:n] if n != len(samples) else samples


def strip_stale_open(samples: list["LapSample"]) -> list["LapSample"]:
    """Drop a leading sample whose lap timer still belongs to the lap before.

    The sibling of :func:`strip_leading_wrap`, for the other clock. At the line
    the sim resets ``normalizedCarPosition`` and ``iCurrentTime`` on *different*
    frames, so the recorder's position guard can let through a frame that has
    already wrapped in position (pos≈0.000) while still carrying the previous
    lap's elapsed time. Measured in the archive: four laps open with t between
    69.6 s and 189.2 s at pos 0.000.

    What it costs, if left: :class:`Reference` indexes that sample at pos≈0 with
    t≈70 s, so the reference "took 70 seconds to reach the start line" and every
    live delta against it is out by that much. It is also why one lap's measured
    duration came out **negative**.

    Identified the same way its sibling identifies a wrap: a *leading* sample
    whose clock is large and which is immediately followed by a smaller one. An
    in-lap that legitimately begins mid-lap has a large clock too, but it rises.
    """
    i = 0
    n = len(samples)
    while (i < n - 1 and samples[i].t_ms > _OPEN_CLOCK_MAX_MS
           and samples[i].t_ms > samples[i + 1].t_ms):
        i += 1
    return samples[i:] if i else samples


# How far the sim's declared lap time may sit from the duration the samples
# themselves measured before we stop believing it. The measured span always runs
# a little short — the last sample lands just before the line — and across the
# 59 laps of the real archive that shortfall is at most **1.36 s** (median
# 0.069). The failures this catches are 104 s, 108 s and 118 s. Two orders of
# magnitude of daylight, so the threshold is not a delicate choice; the fraction
# is there so a three-minute circuit gets the same generosity as a one-minute one.
_TIME_TOL_MS = 5_000
_TIME_TOL_FRAC = 0.10


def trusted_lap_ms(declared: int, samples: list["LapSample"]) -> int:
    """The lap's time: the sim's, unless the lap's own clock contradicts it.

    ``last_lap_ms`` is read on the crossing frame, and on some crossings the sim
    has not published the new value yet — so the lap is stamped with the time of
    the lap **before**. Measured in the archive: a Monza lap whose samples span
    224.4 s is filed as a 1:55.902, which is the previous lap's time, and it sits
    in the catalogue as an identical twin of the real 1:55.902. Two laps, one
    time, and one of them a fiction.

    That fiction is not cosmetic. Its :class:`Reference` would answer position
    queries from a 224-second curve while declaring a 115.9-second lap, so both
    the live delta and the predicted lap time would be nonsense — which is the
    shape of "the numbers on screen don't match the game".

    When the two disagree we take the samples' own span. It comes from the same
    clock, read repeatedly through the lap, and the alternative is a number we
    have just proved belongs to a different lap. It understates by the sliver of
    track between the last sample and the line (see ``_TIME_TOL_MS``) — a tenth
    of a second against a hundred seconds of error.
    """
    span = 0 if len(samples) < 2 else int(samples[-1].t_ms - samples[0].t_ms)
    if declared <= 0 or span <= 0:
        return declared
    if abs(declared - span) <= max(_TIME_TOL_MS, declared * _TIME_TOL_FRAC):
        return declared
    return span


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
    abs_active: float = 0.0
    tc_active: float = 0.0
    yaw_rate: float = 0.0
    tyre_core_temp: tuple[float, float, float, float] = _Z4
    car_x: float = 0.0
    car_z: float = 0.0
    current_sector: int = -1
    slip_ratio: tuple[float, float, float, float] = _Z4
    tyre_pressure: tuple[float, float, float, float] = _Z4
    fuel: float = 0.0                 # litres in the tank (v11)

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
            abs_active=s.abs_active,
            tc_active=s.tc_active,
            yaw_rate=s.yaw_rate,
            tyre_core_temp=s.tyre_core_temp,
            car_x=s.car_x,
            car_z=s.car_z,
            current_sector=s.current_sector,
            slip_ratio=s.slip_ratio,
            tyre_pressure=s.tyre_pressure,
            fuel=s.fuel,
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
            round(self.fuel, 2),
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
            abs_active=f("abs_active"),
            tc_active=f("tc_active"),
            yaw_rate=f("yaw_rate"),
            tyre_core_temp=(f("tyre_fl"), f("tyre_fr"), f("tyre_rl"), f("tyre_rr")),
            car_x=f("car_x"),
            car_z=f("car_z"),
            current_sector=int(m["current_sector"]) if m.get("current_sector") is not None else -1,
            slip_ratio=(f("sr_fl"), f("sr_fr"), f("sr_rl"), f("sr_rr")),
            tyre_pressure=(f("press_fl"), f("press_fr"), f("press_rl"), f("press_rr")),
            fuel=f("fuel"),
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
    # --- v9: the in-car setup this lap was driven on (ACC; -1/-1.0 = unknown/AC).
    # The race engineer judged an accepted change on the median time of a window
    # of laps WITHOUT being able to check which setup those laps were actually on:
    # the ACCEPT/REVERT verdict rested on an unrecorded assumption. These close
    # that loop. Aids can be changed mid-lap, so this is the value at the line —
    # the setup the lap FINISHED on, which is the one the next lap inherits.
    tc_level: int = -1
    abs_level: int = -1
    engine_map: int = -1
    brake_bias: float = -1.0

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
            "tc_level": self.tc_level,
            "abs_level": self.abs_level,
            "engine_map": self.engine_map,
            "brake_bias": (None if self.brake_bias < 0 else round(self.brake_bias, 4)),
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
        # Sanitized in one place, then used twice below: the lap time is judged
        # against the very samples we're about to hand out, so the two can't
        # disagree downstream.
        samples = strip_trailing_wrap(strip_stale_open(strip_leading_wrap(
            [LapSample.from_named(fields, r) for r in d.get("samples", [])])))
        return Lap(
            car_model=str(d.get("car_model", "")),
            track=str(d.get("track", "")),
            session=session,
            # Also sanitized on load, and for the same reason as the samples: the
            # files already on disk carry the defect, and a rule that only runs in
            # the recorder fixes it for nobody who has an archive.
            lap_time_ms=trusted_lap_ms(int(d.get("lap_time_ms", 0)), samples),
            valid=bool(d.get("valid", False)),
            recorded_utc=str(d.get("recorded_utc", "")),
            schema_version=int(d.get("schema", 1)),
            # Sanitize on load: drop any leading pre-line wrap frame (pos~1.0
            # recorded one frame before the sim reset it to 0). Older laps on disk
            # carry it and it poisons every position-indexed consumer downstream
            # (the debrief credited a full lap's time to the last corner, the map's
            # first segment jumped across the line). New laps are already clean —
            # the recorder now drops it at the source.
            samples=samples,
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
            # Absent on pre-v9 files → unknown. brake_bias stored as null when
            # unknown, so distinguish missing from a real 0.0 bias (which no car
            # has, but the load path shouldn't assume that).
            tc_level=int(d.get("tc_level", -1)),
            abs_level=int(d.get("abs_level", -1)),
            engine_map=int(d.get("engine_map", -1)),
            brake_bias=(-1.0 if d.get("brake_bias") is None
                        else float(d["brake_bias"])),
        )
