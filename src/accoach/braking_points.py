"""Your braking points, corner by corner — the cheat sheet, but yours.

The most upvoted thing this community produced about braking references is a
*static* sheet of Monza's braking points (332 votes on r/simracing, read
2026-07-22). Its own author flags the two holes: the points move 10-20 m between
one car and another, and again between a cold track and a hot one. The sharpest
comment adds a third — in a race they move lap to lap.

A sheet built from your own laps has none of those holes, because it never
generalises: it is *this* car, on *this* track, in the conditions you actually
drove, and it says how many laps it looked at.

What it reports per corner, and why each is something you can act on from the
cockpit:

* **the speed you brake at** — the one braking reference every car gives you for
  free, on the dash, in every corner of every track. Metres from a marker board
  require a marker board; km/h don't;
* **the gear** you're in when you hit the pedal;
* **how long the braking zone is**, in metres — what actually changes when you
  brake later;
* **the minimum speed** you carry through, and the gear you take it in;
* **how repeatable you are**: the spread of your braking speed across the laps
  in the sheet. A static sheet cannot know this and it is the number that says
  whether you have a braking point at all, or a different one every lap;
* **the visual landmark**, where the track has a verified one (`trackdata`).

Nothing here is predicted or adjusted: if you want the sheet for a hot track,
drive on a hot track. Every row is a measurement, and the header says which laps
it came from.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .coaching.analyzer import _BRAKE_ON
from .trackdata import landmark_at
from .trajectory import line_points, path_length

# A corner is only a braking corner if the driver actually brakes for it. Below
# this the "braking zone" is a brush of the pedal on a flat-out kink, and a sheet
# that lists it teaches a braking point that doesn't exist.
_MIN_BRAKE_PEAK = 0.25
# A corner needs a braking point in this fraction of the sheet's laps before it
# gets a row: braking once in five laps for a corner is a mistake, not a
# reference.
_MIN_PRESENCE = 0.5


@dataclass(slots=True)
class BrakePoint:
    """One corner's braking reference, measured on one lap."""

    index: int
    onset_pos: float
    speed_kmh: float
    gear: str
    distance_m: float       # from the pedal to the slowest point (0 = no coords)
    vmin_kmh: float
    gear_min: str
    peak_brake: float


@dataclass(slots=True)
class SheetRow:
    """One corner's braking reference across the laps of the sheet."""

    index: int
    name: str
    onset_pos: float
    speed_kmh: float          # median across the laps
    speed_spread_kmh: float   # max - min: how repeatable the point is
    speed_spread_m: float     # the same spread as metres of braking point
    gear: str
    distance_m: float
    vmin_kmh: float
    gear_min: str
    peak_brake: float
    laps: int                 # how many laps this row was measured on
    landmark: str | None = None


@dataclass(slots=True)
class BrakingSheet:
    laps: int = 0
    road_temp_from: float | None = None
    road_temp_to: float | None = None
    rows: list[SheetRow] = field(default_factory=list)


def _mode(values: list[str]) -> str:
    """The most common gear, not the mean of one — gears are labels ("R", "N").

    Ties go to the lower gear: on the boundary between two, the lower one is the
    one that still works.
    """
    if not values:
        return ""
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    tied = [v for v, n in counts.items() if n == best]

    def _key(g: str) -> tuple[int, str]:
        return (int(g), g) if g.isdigit() else (99, g)

    return min(tied, key=_key)


def _spread_metres(spread_kmh: float, speed_kmh: float, vmin_kmh: float,
                   distance_m: float) -> float:
    """The braking-speed spread expressed as metres of braking point.

    km/h is the reference you use in the car; metres is the one the sheets
    people share are written in ("brake at the 100 m board"), and the one that
    makes the number mean something — 12 km/h sounds small until it is 15 m.

    Assumes the braking is even from the pedal to the slowest point, which is
    close enough over one braking zone and is why the view prints it with a "≈".
    Zero when the lap has no coordinates (no distance to scale) — an unmeasurable
    number is left out rather than approximated twice over.
    """
    drop = speed_kmh - vmin_kmh
    if not distance_m or drop <= 0:
        return 0.0
    return round(distance_m * spread_kmh / drop)


def brake_points_of_lap(lap, corners) -> list[BrakePoint]:
    """Where this lap braked for each corner it braked for at all.

    A corner with no real braking (a flat-out kink) is simply absent, rather than
    present with a zero — the caller counts rows, and a corner that appears with
    nothing in it would be counted as measured.
    """
    pts = line_points(lap)
    out: list[BrakePoint] = []
    for c in corners:
        inside = [s for s in lap.samples if c.entry_pos <= s.pos <= c.exit_pos]
        if len(inside) < 3:
            continue
        peak = max(s.brake for s in inside)
        if peak < _MIN_BRAKE_PEAK:
            continue
        onset = next((s for s in inside if s.brake >= _BRAKE_ON), None)
        if onset is None:
            continue
        slowest = min(inside, key=lambda s: s.speed_kmh)
        # Along the path, not as the crow flies: a braking zone that curves (the
        # run down to a hairpin) would otherwise read shorter than it is.
        distance = (round(path_length(pts, onset.pos, slowest.pos))
                    if pts and onset.pos < slowest.pos else 0.0)
        out.append(BrakePoint(
            index=c.index,
            onset_pos=round(onset.pos, 4),
            speed_kmh=round(onset.speed_kmh),
            gear=onset.gear,
            distance_m=distance,
            vmin_kmh=round(slowest.speed_kmh),
            gear_min=slowest.gear,
            peak_brake=round(peak, 2),
        ))
    return out


def build_sheet(laps, corners, names: dict[int, str] | None = None,
                track: str = "", lang: str | None = None,
                road_temps: list[float] | None = None,
                marks=None) -> BrakingSheet:
    """The braking sheet for a set of laps of the same car and track.

    ``laps`` should already be the laps you want pooled — the caller decides
    that, because "which laps belong together" is a question about track
    temperature and about how recent they are, and the answer lives with the
    catalog that stores both. Medians, not means: one aborted braking would drag
    a mean by 20 km/h, and the sheet would then teach that number.
    """
    names = names or {}
    # The braking references the driver typed (:mod:`accoach.cornernames`).
    # Passed in rather than read here for the same reason `names` is: this
    # function is given everything it needs and touches no files.
    per_corner: dict[int, list[BrakePoint]] = {}
    for lap in laps:
        for bp in brake_points_of_lap(lap, corners):
            per_corner.setdefault(bp.index, []).append(bp)

    n = len(laps)
    rows: list[SheetRow] = []
    for c in corners:
        found = per_corner.get(c.index, [])
        if not found or len(found) < max(1, _MIN_PRESENCE * n):
            continue
        speeds = [p.speed_kmh for p in found]
        spread = round(max(speeds) - min(speeds))
        distances = [p.distance_m for p in found if p.distance_m > 0]
        onset = statistics.median([p.onset_pos for p in found])
        rows.append(SheetRow(
            index=c.index,
            name=names.get(c.index) or f"Corner {c.index + 1}",
            onset_pos=round(onset, 4),
            speed_kmh=round(statistics.median(speeds)),
            speed_spread_kmh=spread,
            speed_spread_m=_spread_metres(
                spread, statistics.median(speeds),
                statistics.median([p.vmin_kmh for p in found]),
                statistics.median(distances) if distances else 0.0),
            gear=_mode([p.gear for p in found]),
            distance_m=round(statistics.median(distances)) if distances else 0.0,
            vmin_kmh=round(statistics.median([p.vmin_kmh for p in found])),
            gear_min=_mode([p.gear_min for p in found]),
            peak_brake=round(statistics.median([p.peak_brake for p in found]), 2),
            laps=len(found),
            # The landmark is looked up at the median onset, so the phrase
            # describes where *you* brake and not where the curated apex is.
            landmark=landmark_at(track, onset, lang, marks) if track else None,
        ))

    temps = [t for t in (road_temps or []) if t]
    return BrakingSheet(
        laps=n,
        road_temp_from=min(temps) if temps else None,
        road_temp_to=max(temps) if temps else None,
        rows=rows,
    )
