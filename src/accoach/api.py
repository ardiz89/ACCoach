"""Analysis web app — REST API over saved laps + the static frontend.

The cold-review counterpart to the live overlay: a local web page (served here)
to look back at recorded laps — overlaid telemetry traces vs the reference, the
delta across the lap, and the corner-by-corner debrief.

    python -m accoach web        # serves http://127.0.0.1:8778

It reads only the lap store (the game needn't be running) and lives entirely in
new files, so it doesn't touch the live-coaching code.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .braking_points import build_sheet
from .coaching import (
    CornerFacts,
    CueCategory,
    Goal,
    Programme,
    TrainingPlan,
    benchmark_levels,
    build_flow,
    build_gap,
    build_lap_debrief,
    build_programme,
    category_words,
    classify_losses,
    lap_time_consistency,
    measure as measure_plan,
    propose as propose_plan,
    trail_brake_for,
)
from .coaching.training import MIN_LAPS as _TRAIN_MIN_LAPS, assess as _assess_training
from .comparison import Reference
from .i18n import current_language
from .recording import laps_root, load_lap
from .recording.catalog import LapCatalog, _GRIP_BAND, _TEMP_BAND_C
from .recording.lap import SAMPLE_FIELDS
from .recording.storage import _catalog_path, _slug, list_lap_files
from .sectors import ideal_lap, sector_spans, sector_times
from .sessions import group_sessions
from .telemetry.snapshot import format_lap_time
from .track import detect_corners
from .trackedges import crop as crop_edges, edges_and_fit, edges_for
from .trackdata import name_corners
from .trackmesh import road_shapes
from .trajectory import (
    LinePoint,
    build_line_report,
    corner_path,
    cumulative_distance,
    curvature_profile,
    lateral_offsets,
    line_points,
    tag_text,
)

PORT = 8778
_MAX_POINTS = 600   # downsample traces for the browser

# Below this, a corner didn't really move between two sessions. Same reasoning
# as the guided flow's floor: it is inside the spread of one driver's own laps,
# and reporting it as progress would be flattering rather than true.
_SESSION_MOVE_MS = 60.0

# How many recent laps the braking sheet pools. Enough for a median to mean
# something, few enough that it describes how you drive *now* — a braking point
# from three sessions ago is somebody else's.
_SHEET_LAPS = 10


def _web_dir() -> Path:
    # When frozen by PyInstaller the static files live under _MEIPASS/accoach/web.
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) / "accoach" / "web") if base else (Path(__file__).parent / "web")


_WEB_DIR = _web_dir()


def _pick_indices(n: int) -> list[int]:
    """Which of a lap's frames the browser gets: evenly thinned to _MAX_POINTS.

    Split out from :func:`_downsample` because the distance channel has to be
    measured at full rate and *then* thinned — reproducing this arithmetic in a
    second place is how two channels end up one frame out of register.
    """
    if n <= _MAX_POINTS:
        return list(range(n))
    step = n / _MAX_POINTS
    return [int(i * step) for i in range(_MAX_POINTS)]


def _downsample(lap):
    """Evenly thin a lap's samples to at most _MAX_POINTS for plotting."""
    s = lap.samples
    return [s[i] for i in _pick_indices(len(s))]


def _axle_slip(pair) -> float:
    """The worst slip ratio across one axle's two wheels — the wheel with the
    largest magnitude, sign kept. Negative = locking (braking), positive =
    spinning (power). So a front-axle lock and a rear-axle wheelspin both survive
    the aggregation to a single per-axle trace the Dynamics view can plot."""
    a, b = pair
    return a if abs(a) >= abs(b) else b


# Handling-balance thresholds are owned by the live coach (coaching/balance.py);
# import them so the report's per-point balance ribbon stays in sync with what
# the coach calls understeer/oversteer instead of drifting from a second copy.
from .coaching.balance import (  # noqa: E402
    _MIN_SPEED_KMH as _BAL_MIN_SPEED,
    _STEER_CATCH as _BAL_CATCH,
    _STEER_HARD as _BAL_STEER_HARD,
    _UNDERSTEER_RATIO as _BAL_UNDER,
    _YAW_LOOSE as _BAL_LOOSE,
    _YAW_SIGN as _BAL_YAW_SIGN,
)


def _balance_at(s) -> float:
    """A signed handling-balance value for one frame, in roughly [-1, 1]:
    negative = understeer (the nose pushes — lots of lock, little rotation),
    positive = oversteer (the rear steps out — rotation against opposite lock),
    0 = neutral or not cornering. Mirrors coaching/balance.py's tests so the map
    ribbon reads the same faults the live coach calls."""
    if s.speed_kmh < _BAL_MIN_SPEED:
        return 0.0
    yaw = s.yaw_rate * _BAL_YAW_SIGN
    # Oversteer takes precedence (like the live coach): opposite lock — steer and
    # yaw disagree in sign — while genuinely rotating. Small steer is fine here:
    # catching a slide often means little or reducing lock, so this uses the
    # lower _STEER_CATCH gate, not _STEER_HARD.
    if (abs(s.steer_angle) >= _BAL_CATCH and s.steer_angle * yaw < 0.0
            and abs(yaw) >= _BAL_LOOSE):
        return round(min(1.0, abs(yaw) / (2 * _BAL_LOOSE)), 3)
    # Understeer: rotating far less than the wheel asks (yaw/steer below normal),
    # judged only once the driver is genuinely cornering (steer past _STEER_HARD).
    steer = abs(s.steer_angle)
    if steer < _BAL_STEER_HARD:
        return 0.0
    ratio = abs(yaw) / steer
    if ratio < _BAL_UNDER:
        return round(-min(1.0, (_BAL_UNDER - ratio) / _BAL_UNDER), 3)
    return 0.0


def _points(samples) -> list[LinePoint]:
    """Plotting samples as bare line points, in the order they'll be drawn.

    Deliberately no filtering: the caller aligns the result with the same lap's
    ``pos`` channel index by index, so dropping a sample here would shift a whole
    trace by one against the chart it's overlaid on.
    """
    return [LinePoint(s.pos, s.car_x, s.car_z, s.speed_kmh, s.brake) for s in samples]


def _lateral_offsets(review_s, base_s) -> list[float] | None:
    """Signed lateral distance (m) of each review point from the reference line.

    Thin wrapper over :func:`trajectory.lateral_offsets` — the line geometry lives
    in one module now, so the Dynamics trace and the Trajectory view can't drift
    into disagreeing about which side of the road the driver was on.
    """
    return lateral_offsets(_points(review_s), _points(base_s)) or None


# How far the coordinate trail may disagree with the clock before we stop
# believing it. Measured on the 39 real laps in the archive: the 30 with sound
# coordinates agree with speed×time to within **0.1%**, and the ones that don't
# are not close calls — the six Nürburgring laps recorded before the AC1
# coordinate fix (2026-06-28) report a 5 km lap as 167 m (−96.7%), and the June
# ACC laps carry no coordinates at all (−100%). 5% leaves fifty times the
# observed spread and still rejects both.
_DIST_TOL = 0.05


def _distance_channel(lap) -> list[float]:
    """Metres covered at each frame — or all zeros when the coordinates lie.

    This is the channel every chart's x-axis is labelled from, so it gets a
    second, independent source before it is believed: distance from the
    coordinate trail, against distance from speed integrated over time. Laps
    whose two answers disagree come back as zeros, which the frontend reads as
    "no distance to show" and falls back to per cent.

    The guard is not hypothetical. Six laps in the archive have coordinates that
    collapse a 5 km lap into 167 m; without this they would have been drawn with
    an axis running to 150 m, labelled with total confidence. A silently wrong
    scale is worse than an abstract one — and in this project a number nobody
    corroborated has cost weeks before.
    """
    dist = cumulative_distance(_points(lap.samples))
    if not dist or dist[-1] <= 0.0:
        return [0.0] * len(lap.samples)
    s = lap.samples
    clock = 0.0
    for i in range(1, len(s)):
        dt = (s[i].t_ms - s[i - 1].t_ms) / 1000.0
        # A gap of a second or more isn't a frame interval; it's a stitch in the
        # recording, and the mean speed across it means nothing.
        if 0.0 < dt < 1.0:
            clock += (s[i].speed_kmh + s[i - 1].speed_kmh) / 7.2 * dt
    if clock <= 0.0 or abs(dist[-1] - clock) / clock > _DIST_TOL:
        return [0.0] * len(s)
    return dist


def _channels(lap) -> dict:
    idx = _pick_indices(len(lap.samples))
    s = [lap.samples[i] for i in idx]
    # Metres covered at each plotted frame — what turns every chart's x-axis from
    # "50% of the lap" into a place on the track. Measured over the *full*-rate
    # coordinates and only then thinned: accumulating over 600 plotting points
    # would cut each corner into ten chords and report a lap shorter than the one
    # the Trajectory tab measures for the same drive (the two agree to 5 m in
    # 6.9 km on the real laps — same number, so the page can't contradict itself).
    dist = _distance_channel(lap)
    return {
        "pos": [round(x.pos, 4) for x in s],
        "dist_m": [dist[i] for i in idx],
        "speed": [round(x.speed_kmh, 1) for x in s],
        "throttle": [round(x.throttle, 3) for x in s],
        "brake": [round(x.brake, 3) for x in s],
        "steer": [round(x.steer_angle, 3) for x in s],
        "gear": [x.gear for x in s],
        # World ground-plane path (v3+). Old laps have all-zero coords; the
        # frontend checks ``has_map`` before drawing the track map.
        "x": [round(x.car_x, 2) for x in s],
        "z": [round(x.car_z, 2) for x in s],
        # --- Dynamics view (Tier 1) — channels recorded since v6/v7 but never
        # plotted before. All from the same downsampled frames, so they line up
        # point-for-point with pos/speed and share the crosshair.
        "g_lat": [round(x.g_lat, 3) for x in s],     # lateral G (cornering)
        "g_long": [round(x.g_long, 3) for x in s],   # longitudinal G (+accel/-brake)
        # Physical slip ratio aggregated per axle (front / rear), sign kept.
        "slip_front": [round(_axle_slip(x.slip_ratio[:2]), 3) for x in s],
        "slip_rear": [round(_axle_slip(x.slip_ratio[2:]), 3) for x in s],
        # Signed handling balance (- understeer / + oversteer) for the map ribbon.
        "balance": [_balance_at(x) for x in s],
        # Rotation vs input (yaw trace) and engine revs (shift-point view).
        "yaw": [round(x.yaw_rate, 4) for x in s],
        "rpm": [int(x.rpm) for x in s],
    }


def _tyre_channels(lap) -> dict | None:
    """Per-point tyre core temp & pressure along the lap (4 wheels each), for the
    intra-lap tyre view — how heat and pressure build corner by corner, which the
    stint-level means in /api/progress can't show. None when the lap never
    recorded per-wheel tyres (older laps), so the frontend hides the charts."""
    s = _downsample(lap)
    temp = {w: [round(getattr(x, "tyre_core_temp")[i], 1) for x in s]
            for i, w in enumerate(("fl", "fr", "rl", "rr"))}
    press = {w: [round(getattr(x, "tyre_pressure")[i], 2) for x in s]
             for i, w in enumerate(("fl", "fr", "rl", "rr"))}
    hot = any(v > 0 for v in temp["fl"]) or any(v > 0 for v in press["fl"])
    return {"temp": temp, "press": press} if hot else None


def _fuel_of(row) -> float | None:
    """A catalog row's measured burn, or None when the lap never recorded fuel."""
    try:
        v = row["fuel_used"]
    except (KeyError, IndexError, TypeError):
        return None
    return round(float(v), 2) if v not in (None, "") else None


def _fuel_mean(rows) -> float | None:
    """Litres per lap over the laps that measured it.

    Averaged over the laps that *have* the number rather than over all of them:
    an out-lap from the pits refuels, gets no burn, and would otherwise drag the
    session's consumption towards zero.
    """
    vals = [v for v in (_fuel_of(r) for r in rows) if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _has_map(lap) -> bool:
    """True if the lap carries real world coordinates (recorded under v3+)."""
    return any(s.car_x != 0.0 or s.car_z != 0.0 for s in lap.samples)


def _delta_trace(lap, reference: Reference) -> dict:
    s = _downsample(lap)
    pos, dms, sd = [], [], []
    for x in s:
        rp = reference.point_at(x.pos)
        pos.append(round(x.pos, 4))
        dms.append(round((x.t_ms - rp.t_ms) / 1000.0, 3))
        # Local speed gap vs the reference AT THE SAME track position (+ = you're
        # faster here, - = slower). Unlike the cumulative time delta this doesn't
        # accumulate, so it's the signal the track-map heatmap colours by: where
        # you carry more/less speed than the reference, corner by corner.
        sd.append(round(x.speed_kmh - rp.speed_kmh, 1))
    return {"pos": pos, "delta_s": dms, "speed_delta": sd}


def _pick_known(requested: str | None, fallback: str | None, known: set[str]) -> str | None:
    """Resolve a user-supplied lap path against the catalog's known paths.

    Closes path traversal on the (potentially LAN-exposed) analysis endpoints:
    a ``lap``/``baseline`` query param is honoured only if it matches a path the
    catalog actually indexed for this car+track. Anything else falls through to
    the fallback or ``None`` (→ 404) instead of reading an arbitrary file off
    disk.
    """
    if requested is None:
        return fallback
    return requested if requested in known else None


def _setup_of(lap) -> dict | None:
    """The in-car setup a lap was driven on, or None if it wasn't recorded.

    None on AC (no aid levels) and on pre-v9 laps. Comparing two laps that turn
    out to be on different brake bias or TC is half the reason a delta looks the
    way it does; without this the driver was comparing them blind.
    """
    if lap.tc_level < 0 and lap.abs_level < 0 and lap.brake_bias < 0:
        return None
    out: dict = {}
    if lap.tc_level >= 0:
        out["tc"] = lap.tc_level
    if lap.abs_level >= 0:
        out["abs"] = lap.abs_level
    if lap.engine_map >= 0:
        out["engine_map"] = lap.engine_map
    if lap.brake_bias >= 0:
        # Front bias as the percentage the game shows, not the raw fraction.
        out["brake_bias"] = round(lap.brake_bias * 100, 1)
    return out or None


def _corner_at(pos: float | None, corners, names: dict) -> str | None:
    """Which corner a track position falls in, by name; None if it's on a straight.

    Deliberately no nearest-corner fallback: "you lost it at Lesmo" when the
    driver actually ran wide 300 m earlier on the straight is a confident wrong
    answer, and those are worse than no answer here — the whole point of the
    field is to send them to look at one specific place.
    """
    if pos is None:
        return None
    for c in corners:
        if c.entry_pos <= pos <= c.exit_pos:
            return names.get(c.index, f"Corner {c.index + 1}")
    return None


def _off_track(row: dict) -> bool:
    """Did the driver put 3+ wheels off on this lap?

    Deliberately two-valued while the stored flag has three states (clean / dirty
    / unknown): only *dirty* is a fact worth a mark. "Unknown" covers every lap
    recorded before the flag existed — the majority of most archives — and a UI
    that renders it reads as broken rather than informative. So absence of data
    is absence of UI, and the day the legacy laps age out nothing changes shape.

    The catalog stores -1 unknown / 0 dirty / 1 clean (see `_clean_to_int`).
    """
    return row.get("clean") == 0


def _fastest_clean(valid: list[dict]) -> dict | None:
    """The quickest lap that could be a reference at all, conditions aside."""
    usable = [r for r in valid if not _off_track(r)]
    return min(usable, key=lambda r: r["lap_time_ms"]) if usable else None


def _conditions_of(row: dict | None) -> dict:
    """The conditions a lap was driven in, with "never recorded" as absence.

    A zero temperature, a zero grip and an empty compound all mean the same
    thing — the field wasn't there when this lap was saved — and every rule
    downstream treats unknown as "can't be called similar".
    """
    row = row or {}
    return {
        "road_temp": row.get("road_temp") or None,
        "grip": row.get("grip") or None,
        "compound": row.get("tyre_compound") or None,
    }


def _elected_path(cat, car: str, track: str, valid: list[dict],
                  road_temp: float | None = None,
                  grip: float | None = None,
                  compound: str | None = None) -> str | None:
    """The lap the coach treats as the reference, for the page to agree with it.

    Not simply the fastest: a lap driven off track is time you can't repeat, so
    the catalog's reference query excludes it (``clean <> 0``, confirmed-clean
    preferred). Comparing against the plain fastest meant the analysis page could
    silently baseline everything on a lap the live coach had already rejected —
    and then star it in the dropdown while comparing against something else.

    ``road_temp`` is the *reviewed lap's* track temperature, not today's: the
    report has no "today", and the honest benchmark for a lap driven at 12 degrees
    is your best lap at about 12, not the personal best you set at 32 on a
    rubbered-in evening. Without it this page kept electing the outright fastest
    while the live coach - which does pass the temperature - was electing
    something else, so the star in the dropdown could name a lap the coach had
    never used. A preference, not a filter (see ``best_reference_path``).

    ``grip`` and ``compound`` come from the same lap and are held to the same
    rule. The tyre matters most (a different compound is a different car) and is
    the last thing relaxed; grip is inert on ACC, which reports 0 there by
    design. See ``best_reference_path``.

    Falls back to the fastest when every lap on record is dirty, so the page keeps
    working instead of going blank.
    """
    elected = cat.best_reference_path(car, track, road_temp, grip, compound)
    if elected is not None:
        return elected
    return min(valid, key=lambda r: r["lap_time_ms"])["path"] if valid else None


def _conditions_note(elected: dict | None, fastest: dict | None,
                     review: dict | None) -> dict | None:
    """Why the baseline isn't your fastest lap, when the reason is the conditions.

    A driver who opens the page and finds a slower lap as the benchmark has to be
    told why, or the app just looks broken. Emitted only when the reason really
    is conditions: the elected lap matches the reviewed lap on something the
    faster one doesn't. When the faster lap matches on everything it was passed
    over for cleanliness, and saying "conditions" would be a confident wrong
    answer.

    Which condition is *named* is decided in the order the election holds onto
    them — tyre, then track temperature, then grip — so the sentence reports the
    strongest reason rather than the first one that happens to differ.
    """
    if elected is None or fastest is None or not review:
        return None
    if elected["path"] == fastest["path"]:
        return None
    out = {"faster_lap_time": format_lap_time(fastest["lap_time_ms"])}

    mine, e, f = review, _conditions_of(elected), _conditions_of(fastest)

    # Tyre: compared, never interpreted (see best_reference_path).
    if mine["compound"] and e["compound"] == mine["compound"] \
            and f["compound"] != mine["compound"]:
        return {**out, "reason": "compound", "compound": e["compound"],
                "faster_compound": f["compound"]}

    def _near(a, b, band):
        return a is not None and b is not None and abs(a - b) <= band

    if _near(e["road_temp"], mine["road_temp"], _TEMP_BAND_C) \
            and not _near(f["road_temp"], mine["road_temp"], _TEMP_BAND_C):
        return {**out, "reason": "temp",
                "faster_road_temp": round(f["road_temp"], 1) if f["road_temp"] else None,
                "road_temp": round(e["road_temp"], 1),
                "review_road_temp": round(mine["road_temp"], 1)}

    if _near(e["grip"], mine["grip"], _GRIP_BAND) \
            and not _near(f["grip"], mine["grip"], _GRIP_BAND):
        return {**out, "reason": "grip",
                "grip": round(e["grip"], 2),
                "faster_grip": round(f["grip"], 2) if f["grip"] else None}

    # Nothing about the weather explains it, so it's the other axis of the
    # election: the faster lap was never judged for track limits and this one
    # was. Added the day pre-v8 ACC laps stopped being trusted (see
    # catalog._clean_to_int) — without it the driver opens the page, finds their
    # personal best demoted with no explanation, and the app looks broken in
    # exactly the way this function exists to prevent. Note the wording the UI
    # gives it: "never checked", not "cut the corner". We don't know that it
    # cut; we know nothing looked.
    if elected.get("clean") == 1 and fastest.get("clean") == -1:
        return {**out, "reason": "unjudged"}
    return None


def _tyre_means(samples, attr: str, ndigits: int) -> list[float] | None:
    """Per-wheel average of a 4-tuple channel (FL, FR, RL, RR) over a lap.

    Returns ``None`` when the lap has no samples or the channel was never
    recorded (all-zero — older lap versions predate per-wheel temps/pressures),
    so the tyre trend can hide laps with no data instead of plotting a flat zero.
    """
    n = len(samples)
    if not n:
        return None
    acc = [0.0, 0.0, 0.0, 0.0]
    for s in samples:
        v = getattr(s, attr)
        acc[0] += v[0]; acc[1] += v[1]; acc[2] += v[2]; acc[3] += v[3]
    means = [a / n for a in acc]
    if max(means) <= 0:
        return None
    return [round(m, ndigits) for m in means]


#: How many recent laps get replayed against your best one. Both the Trends tab
#: and the training programme read this same window: two panels describing "your
#: recent laps" over different numbers of laps would disagree about what recurs.
_RECENT_LAPS = 15


@dataclass(slots=True)
class _History:
    """Your recent laps, replayed against your best one — once, for two readers.

    The Trends tab and the training programme both need the same thing: every
    recent lap turned into a debrief, then classified into what recurs. It used
    to live inside ``/api/progress`` alone; the moment a second endpoint needed
    it, copying the loop would have created a second definition of "recently"
    and a second definition of "systematic", which is exactly the kind of split
    this project keeps paying for.
    """

    fastest: str = ""
    best_ms: int = 0
    corners: list = field(default_factory=list)
    names: dict = field(default_factory=dict)
    debriefs: list = field(default_factory=list)
    dated: list = field(default_factory=list)   # (recorded_utc, LapDebrief)
    trends: list = field(default_factory=list)  # LossTrend, worst total first
    recurring: list = field(default_factory=list)
    lap_objs: dict = field(default_factory=dict)


def _history(valid: list[dict], chrono: list[dict], track: str,
             lg: str) -> _History:
    """Load the laps once and build everything cross-lap from them.

    Every failure mode here is a lap file we couldn't read, and none of them is
    worth a 500: the answer degrades to "no trends" rather than taking the page
    down with it, which is what the Trends tab already did.
    """
    fastest_row = min(valid, key=lambda r: r["lap_time_ms"])
    h = _History(fastest=fastest_row["path"], best_ms=fastest_row["lap_time_ms"])

    # Every valid lap, loaded once — shared by the debriefs, the tyre trend and
    # the ideal lap. Three readers used to mean three file reads.
    for r in valid:
        try:
            h.lap_objs[r["path"]] = load_lap(r["path"])
        except (OSError, ValueError):
            pass

    try:
        ref_lap = h.lap_objs.get(h.fastest) or load_lap(h.fastest)
        reference = Reference(ref_lap)
        h.corners = detect_corners(ref_lap.samples)
        h.names = {c.index: n
                   for c, n in zip(h.corners, name_corners(track, h.corners, lg))}
        tally: dict[str, dict] = {}
        for r in chrono[-_RECENT_LAPS:]:
            if r["path"] == h.fastest:
                continue
            lp = h.lap_objs.get(r["path"])
            if lp is None:
                continue
            deb = build_lap_debrief(lp, reference, h.corners, lg)
            h.debriefs.append(deb)
            h.dated.append((r["recorded_utc"] or "", deb))
            for loss in deb.losses:
                t = tally.setdefault(loss.category.value,
                                     {"message": loss.message, "count": 0,
                                      "corners": set()})
                t["count"] += 1
                t["corners"].add(h.names.get(loss.index, f"Corner {loss.index + 1}"))
        h.recurring = sorted(
            ({"category": k, "message": v["message"], "count": v["count"],
              "corners": sorted(v["corners"])} for k, v in tally.items()),
            key=lambda x: x["count"], reverse=True)
        h.trends = classify_losses(h.debriefs)
    except (OSError, ValueError):
        h.debriefs, h.dated, h.trends, h.recurring = [], [], [], []
    return h


def _corner_vmins(corner, chrono: list[dict], lap_objs: dict) -> list[float]:
    """Your minimum speed at one corner, lap by lap across the recent window.

    One definition, two readers: the Trends tab turns this into "how repeatable
    is this corner", and the training programme quotes the same spread inside a
    drill. Written as the raw list rather than a summary so each caller keeps
    its own statistic without either inventing a second window.
    """
    out: list[float] = []
    for r in chrono[-_RECENT_LAPS:]:
        lp = lap_objs.get(r["path"])
        if lp is None:
            continue
        inside = [s.speed_kmh for s in lp.samples
                  if corner.entry_pos <= s.pos <= corner.exit_pos]
        if inside:
            out.append(min(inside))
    return out


def _sheet_pool(valid: list[dict], ref_row: dict | None) -> list[dict]:
    """Which of your laps a braking sheet is measured on.

    Extracted so the Map tab's sheet and the braking drill quote the same
    number: a drill that told you "you brake at 214 km/h here" while the sheet
    two tabs over said 209 would be two answers to one question. The rule is the
    live coach's own — the same road-temperature band it uses to elect a
    reference, because two laps 20° apart are two circuits.
    """
    ref_temp = (ref_row or {}).get("road_temp") or 0.0
    pool = valid
    if ref_temp:
        same = [r for r in valid
                if r["road_temp"] and abs(r["road_temp"] - ref_temp) <= _TEMP_BAND_C]
        pool = same or valid
    return sorted(pool, key=lambda r: r["recorded_utc"] or "")[-_SHEET_LAPS:]


class _RevalidatingStatic(StaticFiles):
    """Static files that the browser must always check before reusing.

    Found on 2026-07-31 while verifying a fix: the page was running JavaScript
    from cache while the server had the new file, and no reload shifted it.
    Without a ``Cache-Control`` header a browser is free to guess how long a
    file stays fresh, and its guess is a fraction of the file's age — which for
    a bundled release means *days*. So an update lands, the app looks updated,
    and the driver is still running last month's page.

    ``no-cache`` does not mean "don't cache": it means "cache it, but ask me
    first". Everything is served from localhost, so a revalidation costs
    nothing and an unnoticed stale file costs a bug report nobody can reproduce.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        return super().is_not_modified(response_headers, request_headers)

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


def create_api(
    laps_dir: Path | str | None = None,
    setups_root: Path | str | None = None,
    demo: bool = False,
) -> FastAPI:
    laps_dir = Path(laps_dir)
    app = FastAPI(title="HONE analysis")

    # Race-engineer setup read/write routes (/api/setup/*). Kept in their own
    # module so this file stays about lap analysis.
    from .setup.store import DEFAULT_ROOTS
    from .setup.web_api import register_setup_routes
    register_setup_routes(app, setups_root or DEFAULT_ROOTS)

    def _catalog() -> LapCatalog:
        cat = LapCatalog(_catalog_path(laps_dir))
        cat.sync(list_lap_files(laps_dir))
        return cat

    @app.get("/api/combos")
    def combos() -> list[dict]:
        """Every car+track that has laps, with its best time."""
        with _catalog() as cat:
            rows = cat._conn.execute(
                """SELECT car_model, track, car_key, track_key,
                          COUNT(*) AS laps,
                          MIN(CASE WHEN valid=1 AND lap_time_ms>0
                                   THEN lap_time_ms END) AS best_ms
                   FROM lap GROUP BY car_key, track_key
                   ORDER BY MAX(recorded_utc) DESC"""
            ).fetchall()
        out = []
        for r in rows:
            best = r["best_ms"] or 0
            out.append({
                "car": r["car_model"], "track": r["track"],
                "car_key": r["car_key"], "track_key": r["track_key"],
                "laps": r["laps"], "best_ms": best,
                "best": format_lap_time(best) if best else "--:--.---",
            })
        return out

    @app.get("/api/laps")
    def laps(car: str = Query(...), track: str = Query(...)) -> list[dict]:
        with _catalog() as cat:
            rows = cat.laps_for(car, track)
        return [{
            "path": r["path"],
            "lap_time_ms": r["lap_time_ms"],
            "lap_time": format_lap_time(r["lap_time_ms"]),
            "valid": bool(r["valid"]),
            "off_track": _off_track(r),
            "source": r.get("source", "own"),
            "recorded_utc": r["recorded_utc"],
            "samples": r["sample_count"],
            # Track temperature, recorded since v5 and never shown until now.
            # Braking points move 10-20 m between a cold track and a hot one, so
            # comparing two laps without knowing this is comparing two different
            # circuits. 0/None = the lap predates the field: no badge (see
            # `_off_track` for the same "absence of data is absence of UI" rule).
            "road_temp": (round(r["road_temp"], 1)
                          if r["road_temp"] else None),
        } for r in rows]

    @app.get("/api/analysis")
    def analysis(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),       # the lap to review (default: most recent)
        baseline: str | None = Query(None),  # the lap to compare against (default: fastest)
        lang: str | None = Query(None),      # render the debrief in this language
    ) -> dict:
        lg = lang or current_language()
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
            known = {r["path"] for r in all_laps}
            # The reviewed lap is resolved first because the reference is elected
            # *for it*: its track temperature is the only "current conditions"
            # this page has.
            review_path = _pick_known(
                lap, next((r["path"] for r in all_laps if r["valid"]), None), known)
            review_row = next((r for r in all_laps if r["path"] == review_path), None)
            mine = _conditions_of(review_row)
            review_temp = mine["road_temp"]
            elected = _elected_path(cat, car, track, valid, review_temp,
                                    mine["grip"], mine["compound"])
            fastest_row = _fastest_clean(valid)

        baseline_path = _pick_known(baseline, elected, known)
        if baseline_path is None or review_path is None:
            raise HTTPException(404, "no valid lap for this car+track")
        elected_row = next((r for r in all_laps if r["path"] == elected), None)
        # Only when the page is actually showing the elected lap: with a baseline
        # the user picked by hand, a note about the election explains a choice
        # nobody made.
        conditions = (_conditions_note(elected_row, fastest_row, mine)
                      if baseline_path == elected else None)

        try:
            baseline_lap = load_lap(baseline_path)
            review = load_lap(review_path)
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

        reference = Reference(baseline_lap)
        if not reference.usable:
            raise HTTPException(422, "comparison lap has too few samples")

        try:
            corners = detect_corners(baseline_lap.samples)
            names = {c.index: n for c, n in zip(corners, name_corners(track, corners, lg))}
            debrief = build_lap_debrief(review, reference, corners, lg)
            consistency = lap_time_consistency([r["lap_time_ms"] for r in valid])
        except Exception:  # noqa: BLE001 - a degenerate lap shouldn't 500 the UI
            raise HTTPException(422, "lap could not be analysed")

        # Minimum speed per corner (you vs the reference, lined up by position) —
        # the metric a driver reads first to see where they're scrubbing speed.
        corner_speeds = []
        for c in corners:
            inside = [s for s in review.samples if c.entry_pos <= s.pos <= c.exit_pos]
            if not inside:
                continue
            vmin_live = min(s.speed_kmh for s in inside)
            vmin_ref = min(reference.point_at(s.pos).speed_kmh for s in inside)
            corner_speeds.append({
                "index": c.index,
                "name": names.get(c.index, f"Corner {c.index + 1}"),
                "apex": round(c.apex_pos, 4),
                "vmin_live": round(vmin_live, 0),
                "vmin_ref": round(vmin_ref, 0),
                "delta": round(vmin_live - vmin_ref, 0),
            })

        return {
            "car": car, "track": track,
            "has_map": _has_map(review) and _has_map(baseline_lap),
            # The elected reference, regardless of what the user is comparing
            # against right now — that's what the dropdown's ★ marks.
            "best_path": elected,
            "reference": {
                "path": baseline_path,
                "lap_time_ms": reference.lap_time_ms,
                "lap_time": format_lap_time(reference.lap_time_ms),
                "channels": _channels(baseline_lap),
                "setup": _setup_of(baseline_lap),
                # Why this lap and not the faster one, when the answer is the
                # weather. None when it isn't (see _conditions_note).
                "by_conditions": conditions,
            },
            "review": {
                "path": review_path,
                "road_temp": round(review_temp, 1) if review_temp else None,
                "setup": _setup_of(review),
                "lap_time_ms": review.lap_time_ms,
                "lap_time": format_lap_time(review.lap_time_ms),
                "channels": _channels(review),
                "delta": _delta_trace(review, reference),
                # Line-deviation (Tier 2): signed metres off the reference line,
                # aligned with the review channels' pos. Only when both have a map.
                "line_offset": (_lateral_offsets(_downsample(review), _downsample(baseline_lap))
                                if _has_map(review) and _has_map(baseline_lap) else None),
                # Per-point tyre temps/pressures along this lap (or None if absent).
                "tyres": _tyre_channels(review),
                # Where the lap stopped counting, and which corner that is.
                # `off_track` said a lap was thrown away without ever saying
                # where, which is the only part the driver can act on. None on
                # laps recorded before v8 — never recorded is not "nowhere".
                "lost_at": review.lost_at,
                "lost_at_corner": _corner_at(review.lost_at, corners, names),
            },
            "corners": [{
                "index": c.index, "entry": c.entry_pos,
                "apex": c.apex_pos, "exit": c.exit_pos,
                "name": names.get(c.index, f"Corner {c.index + 1}"),
            } for c in corners],
            "corner_speeds": corner_speeds,
            # One theme above the corners when the driver is far off the pace —
            # corner-by-corner is the wrong lens there. "" when the gap is small.
            "headline": debrief.headline,
            "losses": [{
                # The corner this is about, by number. The Trajectory view writes
                # this same sentence onto its drawing, and matching it up by name
                # would break the day two corners share one (and on every track
                # with no curated names at all).
                "index": x.index,
                "label": names.get(x.index, f"Corner {x.index + 1}"),
                "lost_s": round(x.lost_ms / 1000, 3),
                "category": x.category.value, "message": x.message,
                "detail": x.detail, "fix": x.fix,
                # When this corner's loss was made in the corner before it
                # (coaching/chain.py). Empty most of the time, on purpose.
                "inherited": x.inherited, "inherited_from": x.inherited_from,
                # Where inside the corner the time went. A split of `lost_s`,
                # so the parts add back up to it (coaching/phases.py).
                "phases": [{"phase": p.phase, "lost_s": round(p.lost_ms / 1000.0, 3)}
                           for p in x.phases],
                "phase_note": x.phase_note,
                "vmin_live": round(x.min_speed_live, 0),
                "vmin_ref": round(x.min_speed_ref, 0),
                "apex": x.apex_pos,
            } for x in debrief.losses],
            # Lap-wide findings that aren't a corner: a lift where the reference
            # is flat, a top-speed deficit. Human coaches open a debrief with
            # these, and the per-corner list structurally can't hold them.
            "notes": [{
                "kind": n.kind, "message": n.message, "detail": n.detail,
                "lost_s": round(n.lost_ms / 1000, 3),
                "pos": round(n.pos, 4), "where": n.where,
            } for n in debrief.notes],
            # The same findings, edited into a short sequence: what to look at
            # first, with the chart that shows it and the stretch to zoom to.
            # Built server-side next to the diagnosis so the rules about what to
            # drop are testable, instead of living in the view layer.
            "flow": [{
                "kind": s.kind, "title": s.title, "body": s.body,
                "detail": s.detail, "fix": s.fix,
                "lost_s": round(s.lost_ms / 1000, 3), "where": s.where,
                "chart": s.chart,
                "from": round(s.from_pos, 4), "to": round(s.to_pos, 4),
            } for s in build_flow(debrief, lg)],
            "consistency": consistency,
            "laps": [{
                "path": r["path"], "lap_time": format_lap_time(r["lap_time_ms"]),
                "lap_time_ms": r["lap_time_ms"],
                "valid": bool(r["valid"]), "off_track": _off_track(r),
                "source": r.get("source", "own"),
                "recorded_utc": r["recorded_utc"],
                # The dropdown has been written to show this since the day track
                # temperature was recorded — and this payload never carried it,
                # so the degrees next to a lap time have never once appeared.
                # /api/laps sends it; the page reads its list from here.
                "road_temp": (round(r["road_temp"], 1) if r["road_temp"] else None),
            } for r in all_laps],
        }

    def _two_laps(car: str, track: str, lap: str | None, baseline: str | None):
        """Resolve the (review, baseline) pair the whole page is built around.

        Same election rule as /api/analysis — including refusing a path the
        catalog doesn't know, which is what keeps these endpoints from reading
        arbitrary files when the app is exposed on the LAN.
        """
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
            elected = _elected_path(cat, car, track, valid)
        known = {r["path"] for r in all_laps}
        base_path = _pick_known(baseline, elected, known)
        rev_path = _pick_known(
            lap, next((r["path"] for r in all_laps if r["valid"]), None), known)
        if base_path is None or rev_path is None:
            raise HTTPException(404, "no valid lap for this car+track")
        try:
            return load_lap(rev_path), load_lap(base_path), rev_path, base_path
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

    @app.get("/api/trajectory")
    def trajectory(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),
        baseline: str | None = Query(None),
        lang: str | None = Query(None),
        fmt: str = Query("json"),            # "csv" downloads the corner table
    ):
        # No return annotation on purpose: this route answers with a JSON body
        # or a CSV attachment, and FastAPI would try to make a response model out
        # of the union.
        """The line you drove, corner by corner, against the reference's.

        Its own endpoint rather than more fields on /api/analysis: the zoomed
        corner crops are the only part of the report that needs the lap at full
        resolution, and paying for them on every tab that only wants a delta
        trace would be the wrong trade.
        """
        lg = lang or current_language()
        review, base, rev_path, base_path = _two_laps(car, track, lap, baseline)
        try:
            corners = detect_corners(base.samples)
            names = {c.index: n
                     for c, n in zip(corners, name_corners(track, corners, lg))}
            report = build_line_report(review, base, corners, names)
        except Exception:  # noqa: BLE001 - a degenerate lap shouldn't 500 the UI
            raise HTTPException(422, "lap could not be analysed")

        you_pts, ref_pts = line_points(review), line_points(base)
        rows = [{
            "index": c.index, "name": c.name,
            "direction": c.direction, "kind": c.kind, "sided": c.sided,
            "entry": c.entry, "apex": c.apex, "exit": c.exit,
            "apex_you": c.apex_pos_you, "apex_ref": c.apex_pos_ref,
            "entry_m": c.entry_m, "apex_m": c.apex_m, "exit_m": c.exit_m,
            "widest_m": c.widest_m, "widest_pos": c.widest_pos,
            "tightest_m": c.tightest_m,
            "apex_shift_m": c.apex_shift_m,
            # …and the two things that say whether that number means anything:
            # how much of the corner's bottom is flat, and whether the car was
            # cornering here at all.
            "apex_flat_m": c.apex_flat_m,
            "off_here": c.off_here,
            "radius_m": c.radius_m, "radius_ref_m": c.radius_ref_m,
            "extra_m": c.extra_m,
            "vmin": c.vmin, "vmin_ref": c.vmin_ref,
            "vexit": c.vexit, "vexit_ref": c.vexit_ref,
            "tags": [tag_text(k, v, lg) for k, v in c.tags],
        } for c in report.corners]

        if fmt == "csv":
            return _trajectory_csv(car, track, review, rows)

        # The edges of the asphalt, from the game's own track data — but only if
        # the track installed here is the track this lap was driven on. See
        # trackedges: a mismatch is a ribbon drawn 187 m from the car, and no
        # ribbon at all is the better answer.
        track_edges, track_fit = edges_and_fit(track, you_pts)

        # Zoomed crops, one per corner: this is the only place the full-rate
        # samples are worth serving, and only over a few hundred metres each.
        for row, c in zip(rows, report.corners):
            you_crop = corner_path(you_pts, c.entry, c.exit)
            row["line"] = {
                "you": you_crop,
                "ref": corner_path(ref_pts, c.entry, c.exit),
            }
            crop_xz = list(zip(you_crop["x"], you_crop["z"]))
            # La strada vera, dal modello di collisione del gioco: e' il
            # poligono dell'asfalto, non il corridoio attorno alla linea
            # dell'IA, e porta con se' i cordoli. Dove c'e', vince.
            shapes = (road_shapes(track, crop_xz, track_fit)
                      if track_fit is not None else None)
            if shapes:
                row["line"]["road"] = shapes
            elif track_edges is not None:
                row["line"]["edges"] = crop_edges(track_edges, crop_xz)

        def _curve(points) -> dict:
            k = curvature_profile(points)
            step = max(1, len(points) // _MAX_POINTS)
            return {"pos": [round(points[i].pos, 4) for i in range(0, len(points), step)],
                    "k": [round(k[i], 5) for i in range(0, len(points), step)]}

        return {
            "car": car, "track": track,
            "has_map": bool(report.corners) or report.path_m > 0,
            "review": {"path": rev_path, "lap_time": format_lap_time(review.lap_time_ms),
                       "lap_time_ms": review.lap_time_ms},
            "reference": {"path": base_path, "lap_time": format_lap_time(base.lap_time_ms),
                          "lap_time_ms": base.lap_time_ms},
            "lap": {
                "path_m": report.path_m, "ref_path_m": report.ref_path_m,
                "extra_m": report.extra_m, "mean_off_m": report.mean_off_m,
                "max_off_m": report.max_off_m, "max_off_where": report.max_off_where,
            },
            "corners": rows,
            "curvature": {"you": _curve(you_pts), "ref": _curve(ref_pts)},
            # Present only when the edges are real: the view says "asphalt" — not
            # "track limits" — and needs the width to say it with a number.
            "edges": ({"width_m": track_edges.width_m()} if track_edges else None),
        }

    def _trajectory_csv(car: str, track: str, review, rows: list[dict]) -> Response:
        """The corner table as a spreadsheet — the dataset behind the view.

        Offered because the numbers here are the ones people take away to a
        forum post or a spreadsheet of their own; a screenshot of a table is a
        worse answer to that than a file.
        """
        import csv
        import io

        cols = ["index", "name", "direction", "kind", "entry", "apex", "exit",
                "apex_shift_m", "apex_flat_m", "off_here",
                "entry_m", "apex_m", "exit_m", "widest_m",
                "tightest_m", "radius_m", "radius_ref_m", "extra_m",
                "vmin", "vmin_ref", "vexit", "vexit_ref"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])
        stem = (f"{_slug(car)}__{_slug(track)}__line__"
                f"{format_lap_time(review.lap_time_ms).replace(':', 'm').replace('.', 's')}")
        return Response(
            buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})

    @app.get("/api/braking")
    def braking(
        car: str = Query(...),
        track: str = Query(...),
        lang: str | None = Query(None),
        fmt: str = Query("json"),            # "csv" downloads the sheet
    ):
        # No return annotation: JSON body or CSV attachment (see /api/trajectory).
        """Your braking points for this car and track — the cheat sheet, yours.

        Pooled across your recent laps rather than read off the single reference:
        a braking point you hit once is not a reference, and the spread across
        several laps is the number that says whether you have one at all.

        Which laps get pooled is decided here rather than in
        ``braking_points.py``, because "which laps belong together" is a question
        about track temperature and about how recent they are — and both live in
        the catalog.
        """
        lg = lang or current_language()
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            valid = [r for r in all_laps
                     if r["valid"] and r["lap_time_ms"] > 0 and not _off_track(r)]
            elected = _elected_path(cat, car, track, valid)
        if not valid or elected is None:
            raise HTTPException(404, "no valid lap for this car+track")

        # Which laps belong together is `_sheet_pool`'s rule, shared with the
        # braking drill in /api/training so the two never quote different points.
        pool = _sheet_pool(valid, next((r for r in valid if r["path"] == elected),
                                       None))

        objs = []
        for r in pool:
            try:
                objs.append(load_lap(r["path"]))
            except (OSError, ValueError):
                pass
        if not objs:
            raise HTTPException(404, "lap file unreadable")
        try:
            ref_lap = next((o for o in objs if o.lap_time_ms), objs[0])
            corners = detect_corners(load_lap(elected).samples)
            names = {c.index: n
                     for c, n in zip(corners, name_corners(track, corners, lg))}
            sheet = build_sheet(objs, corners, names, track, lg,
                                road_temps=[r["road_temp"] for r in pool])
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")
        except Exception:  # noqa: BLE001 - a degenerate lap shouldn't 500 the UI
            raise HTTPException(422, "lap could not be analysed")

        rows = [{
            "index": r.index, "name": r.name, "pos": r.onset_pos,
            "speed_kmh": r.speed_kmh, "spread_kmh": r.speed_spread_kmh,
            "spread_m": r.speed_spread_m,
            "gear": r.gear, "distance_m": r.distance_m,
            "vmin_kmh": r.vmin_kmh, "gear_min": r.gear_min,
            "peak_brake": r.peak_brake, "laps": r.laps,
            "landmark": r.landmark,
        } for r in sheet.rows]

        if fmt == "csv":
            return _braking_csv(car, track, rows)

        return {
            "car": car, "track": track,
            "laps": sheet.laps,
            "road_temp_from": sheet.road_temp_from,
            "road_temp_to": sheet.road_temp_to,
            "reference": {"path": elected,
                          "lap_time": format_lap_time(ref_lap.lap_time_ms)},
            "rows": rows,
        }

    def _braking_csv(car: str, track: str, rows: list[dict]) -> Response:
        """The sheet as a file — this is the artefact people print and tape to
        the desk, which is the whole reason the static one got 332 votes."""
        import csv
        import io

        cols = ["index", "name", "speed_kmh", "gear", "spread_kmh", "spread_m",
                "distance_m",
                "vmin_kmh", "gear_min", "peak_brake", "laps", "landmark", "pos"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])
        stem = f"{_slug(car)}__{_slug(track)}__frenate"
        return Response(
            buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})

    def _corner_moves(newer_path: str, older_path: str, track: str,
                      lg: str, limit: int = 3) -> dict:
        """Which corners moved between two laps, both ways, named and explained.

        Two debriefs rather than a new comparison: run it one way and you get
        the corners where the newer lap is slower, run it the other way and the
        same machinery names the corners where it is faster. Nothing here
        computes a time difference itself — that would be a second, subtly
        different implementation of the windowing rule the debrief already owns
        (a corner is credited with the straight that follows it).
        """
        try:
            newer, older = load_lap(newer_path), load_lap(older_path)
            ref_old, ref_new = Reference(older), Reference(newer)
            if not (ref_old.usable and ref_new.usable):
                return {"improved": [], "regressed": []}
            corners_old = detect_corners(older.samples)
            corners_new = detect_corners(newer.samples)
            worse = build_lap_debrief(newer, ref_old, corners_old, lg).losses
            better = build_lap_debrief(older, ref_new, corners_new, lg).losses
        except Exception:  # noqa: BLE001 - a session view must not 500 on one bad lap
            return {"improved": [], "regressed": []}

        def _rows(losses, advice: bool):
            # The message is only carried for the corners that went backwards.
            # Reversing the comparison names what the *older* lap did wrong, so
            # on an improvement it would print an instruction ("more throttle on
            # exit") under the heading "you got faster here" — advice aimed at a
            # lap you already stopped driving. The corner and the time are the
            # honest half of that finding.
            return [{"label": x.label, "gain_s": round(x.lost_ms / 1000, 3),
                     **({"message": x.message} if advice else {})}
                    for x in losses[:limit] if x.lost_ms >= _SESSION_MOVE_MS]

        return {"improved": _rows(better, advice=False),
                "regressed": _rows(worse, advice=True)}

    @app.get("/api/sessions")
    def sessions(
        car: str = Query(...),
        track: str = Query(...),
        index: int = Query(0),               # 0 = the most recent run
        lang: str | None = Query(None),
    ) -> dict:
        """The laps of one sitting, and what changed since the sitting before.

        The rest of the app is lap-centric — pick two laps, compare them — which
        is the right shape for studying a lap and the wrong one for the question
        you have when you get up from the wheel.
        """
        lg = lang or current_language()
        with _catalog() as cat:
            rows = cat.laps_for(car, track)
        runs = group_sessions(rows)
        if not runs:
            return {"sessions": [], "current": None}

        index = max(0, min(index, len(runs) - 1))
        cur = runs[index]
        best = cur.best
        temps = cur.road_temps
        valid_ms = [l["lap_time_ms"] for l in cur.valid_laps]

        prev = runs[index + 1] if index + 1 < len(runs) else None
        prev_best = prev.best if prev else None
        moves = {"improved": [], "regressed": []}
        if best and prev_best:
            moves = _corner_moves(best["path"], prev_best["path"], track, lg)

        def _summary(s):
            b = s.best
            return {
                "started_utc": s.started.isoformat() if s.started else None,
                "laps": len(s.laps), "valid": len(s.valid_laps),
                "best_ms": b["lap_time_ms"] if b else None,
                "best": format_lap_time(b["lap_time_ms"]) if b else None,
            }

        return {
            "sessions": [_summary(s) for s in runs],
            "index": index,
            "current": {
                **_summary(cur),
                "ended_utc": cur.ended.isoformat() if cur.ended else None,
                "duration_s": round(cur.duration_s),
                "best_path": best["path"] if best else None,
                "road_temp_from": min(temps) if temps else None,
                "road_temp_to": max(temps) if temps else None,
                "consistency": lap_time_consistency(valid_ms),
                # Every lap of the run, in the order driven — cut and invalid
                # ones included. They can't set the numbers, but leaving them out
                # would show a session you didn't have.
                # Litres per lap, measured from the tank level (schema v11).
                # None on laps recorded before the channel existed and on laps
                # that refuelled — the frontend hides the column rather than
                # printing a zero nobody burned.
                "fuel_per_lap": _fuel_mean(cur.laps),
                "laps_detail": [{
                    "path": l["path"],
                    "lap_time": format_lap_time(l["lap_time_ms"]),
                    "lap_time_ms": l["lap_time_ms"],
                    "valid": bool(l["valid"]),
                    "off_track": _off_track(l),
                    "is_best": bool(best and l["path"] == best["path"]),
                    "fuel_used": _fuel_of(l),
                } for l in cur.laps],
                "previous": {
                    "started_utc": prev.started.isoformat() if prev and prev.started else None,
                    "best_ms": prev_best["lap_time_ms"] if prev_best else None,
                    "delta_ms": (best["lap_time_ms"] - prev_best["lap_time_ms"])
                                if best and prev_best else None,
                    **moves,
                } if prev else None,
            },
        }

    @app.get("/api/sectors")
    def sectors(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),       # the lap to review (default: most recent)
        baseline: str | None = Query(None),  # the lap to compare against (default: fastest)
    ) -> dict:
        """Per-sector breakdown of review vs baseline, plus the ideal lap."""
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
            if not valid:
                raise HTTPException(404, "no valid lap for this car+track")
            known = {r["path"] for r in all_laps}
            # Same election as /api/analysis, for the same reason and with the
            # same input: two tabs of one page must not disagree about which lap
            # is the benchmark.
            review_path = _pick_known(
                lap, next((r["path"] for r in all_laps if r["valid"]), None), known)
            review_row = next((r for r in all_laps if r["path"] == review_path), None)
            mine = _conditions_of(review_row)
            elected = _elected_path(cat, car, track, valid, mine["road_temp"],
                                    mine["grip"], mine["compound"])
        baseline_path = _pick_known(baseline, elected, known)
        if baseline_path is None or review_path is None:
            raise HTTPException(404, "no valid lap for this car+track")
        try:
            review = load_lap(review_path)
            base = load_lap(baseline_path)
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

        # Canonical spans come from the baseline: real sim sectors if it has
        # them, else equal thirds. Every lap is timed against these same spans so
        # review / baseline / ideal all line up.
        spans, real = sector_spans(base)
        n = len(spans)
        rev_st = sector_times(review, spans)
        base_st = sector_times(base, spans)
        if not rev_st or not base_st:
            raise HTTPException(422, "lap too sparse for sector splits")

        # Ideal lap stitched from the best sector of every valid lap.
        ideal = None
        objs: list = []
        try:
            objs = [load_lap(r["path"]) for r in valid]
            ideal = ideal_lap(objs, [r["path"] for r in valid], spans)
        except (OSError, ValueError):
            objs, ideal = [], None

        # Every lap's sectors against the same spans. The ideal lap already says
        # a 2:03.412 is in there somewhere; this is where you see *which* laps it
        # is made of, and whether a sector you're proud of was one good lap or a
        # habit. Free-ish: these laps are already in memory for the ideal, so it
        # costs a walk over samples and not a read from disk.
        per_lap = []
        for obj, row in zip(objs, valid):
            st = sector_times(obj, spans)
            if len(st) != n:
                continue
            per_lap.append({
                "path": row["path"],
                "lap_time": format_lap_time(row["lap_time_ms"]),
                "recorded_utc": row.get("recorded_utc"),
                "off_track": _off_track(row),
                "ms": st,
            })

        sectors_out = [{
            "index": i,
            "start": round(spans[i][0], 3),
            "end": round(spans[i][1], 3),
            "review_ms": rev_st[i],
            "baseline_ms": base_st[i],
            "delta_ms": rev_st[i] - base_st[i],
            "is_best": bool(ideal and ideal.best_from[i] == review_path),
        } for i in range(n)]

        out = {
            "car": car, "track": track, "n": n, "real": real,
            "review": {"path": review_path, "lap_time_ms": review.lap_time_ms,
                       "lap_time": format_lap_time(review.lap_time_ms)},
            "baseline": {"path": baseline_path, "lap_time_ms": base.lap_time_ms,
                         "lap_time": format_lap_time(base.lap_time_ms)},
            "sectors": sectors_out,
            "per_lap": per_lap,
            "laps": [{"path": r["path"], "lap_time": format_lap_time(r["lap_time_ms"]),
                      "valid": bool(r["valid"]), "off_track": _off_track(r)}
                     for r in all_laps],
        }
        if ideal:
            your_best = min(valid, key=lambda r: r["lap_time_ms"])["lap_time_ms"]
            out["ideal"] = {
                "best_ms": ideal.best_ms,
                "best_from": ideal.best_from,
                "ideal_ms": ideal.ideal_ms,
                "ideal": format_lap_time(ideal.ideal_ms),
                "gain_ms": your_best - ideal.ideal_ms,
            }
        return out

    @app.get("/api/progress")
    def progress(car: str = Query(...), track: str = Query(...),
                 lang: str | None = Query(None)) -> dict:
        """Lap-time trend, consistency, benchmark levels and recurring mistakes."""
        lg = lang or current_language()
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            pro_path = cat.fastest_pro_path(car, track)
        valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
        if not valid:
            # Same shape as the full answer, empty: a caller that has to check
            # whether a key exists before reading it is a caller that will
            # eventually forget.
            return {"car": car, "track": track, "laps": [], "pb_trend": [],
                    "consistency": lap_time_consistency([]), "levels": [],
                    "trends": [], "recurring": [], "tyres": [],
                    "corner_consistency": []}

        # Chronological (oldest first) for the trend.
        chrono = sorted(valid, key=lambda r: r["recorded_utc"] or "")
        laps = [{"recorded_utc": r["recorded_utc"],
                 "lap_time_ms": r["lap_time_ms"],
                 "lap_time": format_lap_time(r["lap_time_ms"])} for r in chrono]

        per_day: dict[str, int] = {}
        for r in chrono:
            day = (r["recorded_utc"] or "")[:10] or "?"
            per_day[day] = min(per_day.get(day, r["lap_time_ms"]), r["lap_time_ms"])
        pb_trend = [{"day": d, "best_ms": ms, "best": format_lap_time(ms)}
                    for d, ms in sorted(per_day.items())]

        # Recurring mistakes, per-corner trends and every lap loaded once — all
        # of it shared with /api/training (see `_history`). Systematic (a
        # weakness to train) vs sporadic (a one-off) is decided in there and
        # kept as objects, because the training plan below picks its goals from
        # these and re-deriving them from the serialised dicts would be a second
        # definition of "systematic".
        h = _history(valid, chrono, track, lg)
        fastest, best_ms = h.fastest, h.best_ms
        corners, cnames = h.corners, h.names
        recurring, loss_trends = h.recurring, h.trends
        dated, lap_objs = h.dated, h.lap_objs
        trends: list[dict] = []
        if loss_trends:
            trends = [{
                "corner_index": t.corner_index,
                "name": cnames.get(t.corner_index, t.name),
                "category": t.category.value,
                "kind": t.kind,
                "systematic": t.systematic,
                "occurrences": t.occurrences,
                "laps": t.laps,
                "median_s": round(t.median_ms / 1000.0, 3),
                "total_s": round(t.total_ms / 1000.0, 3),
            } for t in loss_trends]

        # Tyre temps & pressures per lap, chronological — to spot heat build-up
        # and pressure drift across a stint (the degradation signal a driver
        # feels but can't see). Laps predating per-wheel capture are skipped.
        tyres: list[dict] = []
        for r in chrono:
            lp = lap_objs.get(r["path"])
            if lp is None:
                continue
            temp = _tyre_means(lp.samples, "tyre_core_temp", 1)
            press = _tyre_means(lp.samples, "tyre_pressure", 2)
            if temp is None and press is None:
                continue
            tyres.append({
                "recorded_utc": r["recorded_utc"],
                "lap_time": format_lap_time(r["lap_time_ms"]),
                "temp": temp, "press": press,
            })

        # Consistency per corner: how much the min speed at each corner varies
        # across the recent laps. A wide spread means the driver isn't repeating
        # that corner — a "where you're inconsistent" signal the global σ hides.
        corner_consistency: list[dict] = []
        for c in corners:
            vmins = _corner_vmins(c, chrono, lap_objs)
            if len(vmins) >= 3:
                mean = sum(vmins) / len(vmins)
                # Sample variance (÷ n-1), matching `lap_time_consistency`. These
                # laps are a sample of how you drive, not the population, and the
                # page showed two numbers both labelled σ computed two different
                # ways — the lap-time one Bessel-corrected, this one not. On the
                # handful of laps we actually deal with that is ~11% at n=5, so
                # the two σ on the same screen disagreed for no reason a reader
                # could see.
                var = sum((v - mean) ** 2 for v in vmins) / (len(vmins) - 1)
                corner_consistency.append({
                    "corner_index": c.index,
                    "name": cnames.get(c.index, f"Corner {c.index + 1}"),
                    "n": len(vmins),
                    "mean_kmh": round(mean, 1),
                    "spread_kmh": round(max(vmins) - min(vmins), 1),
                    "std_kmh": round(var ** 0.5, 2),
                })
        corner_consistency.sort(key=lambda x: x["spread_kmh"], reverse=True)

        # Benchmark ladder: rolling best → ideal (consistency) → PRO (skill ceiling).
        ideal_ms = pro_ms = None
        try:
            paths = [r["path"] for r in valid if r["path"] in lap_objs]
            objs = [lap_objs[p] for p in paths]
            spans, _ = sector_spans(lap_objs.get(fastest) or load_lap(fastest))
            il = ideal_lap(objs, paths, spans)
            ideal_ms = il.ideal_ms if il else None
        except (OSError, ValueError):
            ideal_ms = None
        if pro_path:
            try:
                pro_ms = load_lap(pro_path).lap_time_ms
            except (OSError, ValueError):
                pro_ms = None
        levels = [{
            "key": lv.key, "label": lv.label,
            "lap_time_ms": lv.lap_time_ms, "lap_time": format_lap_time(lv.lap_time_ms),
            "gain_ms": lv.gain_ms, "gain_s": round(lv.gain_ms / 1000.0, 3),
        } for lv in benchmark_levels(best_ms, ideal_ms=ideal_ms, pro_ms=pro_ms, lang=lg)]

        return {
            "car": car, "track": track,
            "laps": laps, "pb_trend": pb_trend,
            "consistency": lap_time_consistency([r["lap_time_ms"] for r in valid]),
            "levels": levels,
            "trends": trends,
            "recurring": recurring,
            "tyres": tyres,
            "corner_consistency": corner_consistency,
        }

    def _plan_for(car: str, track: str, dated: list, trends: list,
                  names: dict, lang: str) -> tuple[TrainingPlan, list, bool, list]:
        """The plan for this car+track: stored if you accepted one, proposed if not.

        A plan that hasn't been accepted comes back as a *proposal* (``saved``
        false). That distinction is the whole point of the feature: a target you
        never agreed to isn't one you can be measured against, and a plan
        recomputed on every page load can't be worked on.

        Returns the plan, its per-goal progress, whether it was stored, and the
        debriefs it is being measured on — the training programme needs the
        objects, not the JSON, and rebuilding them from the payload would be a
        second definition of every rule in ``plan.py``.
        """
        try:
            with _catalog() as cat:
                stored = cat.load_plan(car, track)
                mastered, _parked = cat.load_focus_state(car, track)
        except Exception:  # noqa: BLE001 - the plan is a convenience, never a 500
            stored, mastered = None, set()

        if stored:
            plan = TrainingPlan.from_dict(stored)
            since = [d for when, d in dated if when > plan.created_utc]
            saved = True
            # A stored plan carries the words of the language it was accepted
            # in, and it outlives that choice by weeks. The numbers stay exactly
            # as agreed; the corner's name and the category's own sentences are
            # re-derived for the language being asked for, because they are
            # labels, not terms of the agreement. (Found on screen: an Italian
            # page whose goals both read "Time lost here".)
            for g in plan.goals:
                g.name = names.get(g.corner_index, g.name)
                try:
                    what, fix = category_words(CueCategory(g.category), lang)
                except ValueError:      # a category we no longer have
                    continue
                g.what, g.fix = what, fix
        else:
            plan = propose_plan([t for t in trends], [d for _, d in dated],
                                mastered=mastered, car=car, track=track)
            # Names are resolved by the API layer everywhere else on this page;
            # do it here too so a curated corner isn't called "Corner 4" in the
            # one panel that is meant to be read for weeks.
            for g in plan.goals:
                g.name = names.get(g.corner_index, g.name)
            since = []
            saved = False
        return plan, measure_plan(plan, since), saved, since

    def _plan_payload(plan: TrainingPlan, progress: list, saved: bool,
                      laps_since: int) -> dict:
        """The plan as the page draws it."""
        by_index = {p.corner_index: p for p in progress}
        return {
            "saved": saved,
            "created_utc": plan.created_utc or None,
            "laps_since": laps_since,
            "goals": [{
                "corner_index": g.corner_index, "name": g.name,
                "category": g.category, "what": g.what, "fix": g.fix,
                "baseline_s": round(g.baseline_ms / 1000.0, 3),
                "target_s": round(g.target_ms / 1000.0, 3),
                "laps_seen": g.laps_seen,
                "progress": _progress_payload(by_index.get(g.corner_index)),
            } for g in plan.goals],
        }

    def _progress_payload(p) -> dict | None:
        if p is None or not p.laps:
            return None
        return {"laps": p.laps, "hits": p.hits, "needed": p.needed,
                "median_s": round(p.median_ms / 1000.0, 3),
                "best_s": round(p.best_ms / 1000.0, 3), "done": p.done}

    @app.get("/api/training")
    def training(car: str = Query(...), track: str = Query(...),
                 lang: str | None = Query(None)) -> dict:
        """The Training tab: how to get to your theoretical ideal, in drills.

        Everything the answer is built from already exists — the plan's goals,
        the debriefs' phase split, the ideal lap, the braking sheet. What lives
        here is the wiring: load each of those *once*, from the same laps, so
        the programme quotes numbers that match the tab they came from. A drill
        that says you brake at 214 km/h while the Map tab says 209 is worse than
        a drill with no number in it.

        The gate is checked before any lap is read: under the bar the whole
        answer is one sentence, and replaying fifteen laps to write it would be
        work nobody sees.
        """
        lg = lang or current_language()
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
            pro_path = cat.fastest_pro_path(car, track)
            valid = [r for r in all_laps if r["valid"] and r["lap_time_ms"] > 0]
            # The braking sheet has always been measured on clean laps only; a
            # drill quoting a braking point set on a lap that went off would be
            # quoting a mistake.
            clean = [r for r in valid if not _off_track(r)]
            elected = _elected_path(cat, car, track, clean) if clean else None

        if len(valid) < _TRAIN_MIN_LAPS:
            out = Programme(readiness=_assess_training(len(valid), 0, lg)).to_dict()
            out.update({"car": car, "track": track, "plan": None})
            return out

        chrono = sorted(valid, key=lambda r: r["recorded_utc"] or "")
        h = _history(valid, chrono, track, lg)
        plan, progress, saved, since = _plan_for(car, track, h.dated, h.trends,
                                                 h.names, lg)
        goal_idx = {g.corner_index for g in plan.goals}

        # What you bleed on a typical lap at the corners the plan names. The
        # median, not the mean: one lap where you spun in that corner is not
        # what you are being asked to train.
        per_lap = [sum(x.lost_ms for x in d.losses if x.index in goal_idx)
                   for d in h.debriefs]
        pro_ms = 0
        if pro_path:
            try:
                pro_ms = load_lap(pro_path).lap_time_ms
            except (OSError, ValueError):
                pro_ms = 0

        gap = None
        try:
            best_lap = h.lap_objs.get(h.fastest)
            paths = [r["path"] for r in valid if r["path"] in h.lap_objs]
            objs = [h.lap_objs[p] for p in paths]
            if best_lap is not None and objs:
                spans, _ = sector_spans(best_lap)
                il = ideal_lap(objs, paths, spans)
                if il:
                    gap = build_gap(
                        h.best_ms, il.ideal_ms, sector_times(best_lap, spans),
                        il.best_ms,
                        per_lap_ms=statistics.median(per_lap) if per_lap else 0.0,
                        pro_ms=pro_ms, lang=lg)
        except (OSError, ValueError):
            gap = None

        facts = _training_facts(goal_idx, h, chrono, clean, elected, track, lg)
        # Corners the chain analysis blamed for a *later* corner's loss: the
        # programme puts them first, because fixing the corner that hands over
        # the deficit fixes two and the other order fixes neither.
        inherited = {x.inherited_from for d in h.debriefs for x in d.losses
                     if x.inherited_from >= 0}

        prog = build_programme(plan, progress, h.debriefs, gap, facts,
                               valid_laps=len(valid), lang=lg,
                               inherited_sources=inherited,
                               trail_brake=trail_brake_for(car))
        out = prog.to_dict()
        out.update({"car": car, "track": track,
                    "plan": _plan_payload(plan, progress, saved, len(since))})
        return out

    def _training_facts(indices: set[int], h: _History, chrono: list[dict],
                        clean: list[dict], elected: str | None,
                        track: str, lg: str) -> dict[int, CornerFacts]:
        """The measured numbers a drill drops into its sentences.

        Only for the corners the plan actually names — building a braking sheet
        is not free, and nothing else on this page needs one. Anything that
        can't be measured is simply left at its default: the drill then prints
        one line fewer, which is the intended behaviour, not a degraded one.
        """
        if not indices:
            return {}
        out = {i: CornerFacts() for i in indices}

        for i in indices:
            live = [x.min_speed_live for d in h.debriefs for x in d.losses
                    if x.index == i and x.min_speed_live > 0]
            ref = [x.min_speed_ref for d in h.debriefs for x in d.losses
                   if x.index == i and x.min_speed_ref > 0]
            if live:
                out[i].min_speed_kmh = round(statistics.median(live), 1)
            if ref:
                out[i].min_speed_ref_kmh = round(statistics.median(ref), 1)
            corner = next((c for c in h.corners if c.index == i), None)
            if corner is not None:
                vmins = _corner_vmins(corner, chrono, h.lap_objs)
                if len(vmins) >= 3:
                    out[i].spread_kmh = round(max(vmins) - min(vmins), 1)

        # The braking sheet, on exactly the laps the Map tab pools (`_sheet_pool`).
        try:
            ref_row = next((r for r in clean if r["path"] == elected), None)
            pool = _sheet_pool(clean, ref_row)
            objs = [h.lap_objs[r["path"]] for r in pool if r["path"] in h.lap_objs]
            if objs and h.corners:
                sheet = build_sheet(objs, h.corners, h.names, track, lg,
                                    road_temps=[r["road_temp"] for r in pool])
                for row in sheet.rows:
                    if row.index not in out:
                        continue
                    out[row.index].brake_speed_kmh = row.speed_kmh
                    out[row.index].brake_gear = row.gear
                    out[row.index].brake_distance_m = row.distance_m
                    out[row.index].brake_spread_m = row.speed_spread_m
                    out[row.index].brake_spread_kmh = row.speed_spread_kmh
                    out[row.index].landmark = row.landmark or ""
        except Exception:  # noqa: BLE001 - a drill line, never a 500
            pass
        return out

    @app.post("/api/plan")
    def accept_plan(payload: dict = Body(...)) -> dict:
        """Accept the plan currently being proposed for a car+track.

        Takes the goals from the client rather than recomputing them: the driver
        is agreeing to the plan *they were shown*, and a plan that quietly
        differed from the one on screen because a lap landed in between would be
        a plan nobody agreed to.
        """
        from datetime import datetime, timezone

        car = str(payload.get("car") or "")
        track = str(payload.get("track") or "")
        goals = payload.get("goals") or []
        if not car or not track or not goals:
            raise HTTPException(422, "a plan needs a car, a track and a goal")
        # Accepts a goal exactly as it was served — seconds and all, extra keys
        # ignored — so the client can echo back the object it displayed instead
        # of rebuilding it in another unit. Rebuilt through the dataclass so a
        # malformed goal is rejected here rather than stored and blown up on the
        # next read.
        try:
            plan = TrainingPlan(car=car, track=track,
                                goals=[_goal_from_payload(g) for g in goals])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, "malformed goal")
        stamp = datetime.now(timezone.utc).isoformat()
        with _catalog() as cat:
            cat.save_plan(car, track, stamp, plan.to_dict()["goals"])
        return {"ok": True, "created_utc": stamp}

    def _goal_from_payload(g: dict) -> Goal:
        """One goal as the client sends it back: seconds accepted, ms preferred."""
        def _ms(key: str) -> float:
            if g.get(key + "_ms") is not None:
                return float(g[key + "_ms"])
            return float(g.get(key + "_s") or 0.0) * 1000.0

        return Goal(
            corner_index=int(g["corner_index"]),
            name=str(g.get("name", "")),
            category=str(g.get("category", "")),
            what=str(g.get("what", "")),
            fix=str(g.get("fix", "")),
            baseline_ms=_ms("baseline"),
            target_ms=_ms("target"),
            laps_seen=int(g.get("laps_seen", 0)),
        )

    @app.delete("/api/plan")
    def drop_plan(car: str = Query(...), track: str = Query(...)) -> dict:
        """Give up on the current plan; the next read proposes a fresh one."""
        with _catalog() as cat:
            cat.clear_plan(car, track)
        return {"ok": True}

    @app.get("/api/export")
    def export(
        car: str = Query(...),
        track: str = Query(...),
        lap: str | None = Query(None),
        fmt: str = Query("csv"),
    ) -> Response:
        """Download a lap's full-resolution telemetry as CSV or JSON."""
        with _catalog() as cat:
            all_laps = cat.laps_for(car, track)
        known = {r["path"] for r in all_laps}
        path = _pick_known(lap, next((r["path"] for r in all_laps if r["valid"]), None), known)
        if path is None:
            raise HTTPException(404, "no lap to export")
        try:
            lp = load_lap(path)
        except (OSError, ValueError):
            raise HTTPException(404, "lap file unreadable")

        stem = (f"{_slug(car)}__{_slug(track)}__"
                f"{format_lap_time(lp.lap_time_ms).replace(':', 'm').replace('.', 's')}")

        if fmt == "json":
            import json
            return Response(
                json.dumps(lp.to_dict()), media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})

        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(SAMPLE_FIELDS)
        for s in lp.samples:
            w.writerow(s.as_row())
        return Response(
            buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})

    def _serve(page: str) -> Response:
        """Serve a web page; in demo mode inject a DEMO banner so synthetic laps
        can never be mistaken for real ones (the launcher will happily open a
        demo server already bound to the analysis port)."""
        path = _WEB_DIR / page
        if not demo:
            return FileResponse(str(path))
        html = path.read_text(encoding="utf-8")
        banner = ('<div class="demo-banner" data-i18n="demo.banner">'
                  'DEMO — synthetic laps, not your real data</div>')
        html = html.replace("<body>", '<body class="demo-mode">\n' + banner, 1)
        return Response(content=html, media_type="text/html")

    @app.get("/")
    def index() -> Response:
        return _serve("index.html")

    @app.get("/engineer")
    def engineer() -> Response:
        """The race-engineer setup page (live diagnosis + setup editor)."""
        return _serve("engineer.html")

    @app.get("/guida")
    @app.get("/guide")
    def guide_page(lang: str | None = None) -> Response:
        """The user guide, rendered from the Markdown we ship.

        Two paths because the guide has two names depending on which language
        you're in, and a link that works only in Italian is the bug this page
        replaces — the "Guide" button used to open the Italian file in Notepad
        whatever you had chosen.
        """
        from .guide import render_guide

        try:
            return Response(content=render_guide(lang), media_type="text/html")
        except FileNotFoundError:
            # A build that lost the .md should say so, not serve a blank page.
            return Response(
                content="<h1>Guida non disponibile</h1><p>Il documento non è "
                        "incluso in questa installazione.</p>",
                media_type="text/html", status_code=404)

    @app.get("/test")
    def test_page() -> Response:
        """The on-track test checklist — tablet-first, reads the live feed and
        auto-captures the cues HONE fires for each test."""
        return _serve("test.html")

    @app.get("/api/test/latest_lap")
    def test_latest_lap() -> dict:
        """The most recently recorded lap, so the tablet can auto-attach it to a
        test result (a real telemetry reference for later calibration)."""
        with _catalog() as cat:
            row = cat._conn.execute(
                "SELECT path, car_model, track, lap_time_ms, valid, recorded_utc "
                "FROM lap ORDER BY recorded_utc DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return {"lap": None}
        return {"lap": {
            "path": Path(row["path"]).name,
            "car": row["car_model"],
            "track": row["track"],
            "lap_time_ms": row["lap_time_ms"],
            "lap_time": format_lap_time(row["lap_time_ms"]),
            "valid": bool(row["valid"]),
            "recorded_utc": row["recorded_utc"],
        }}

    @app.post("/api/test/save")
    def test_save(payload: dict = Body(...)) -> dict:
        """Persist a test run as JSON under ``<data>/test_runs/`` on this PC.

        Named by the run's stable ``run_id`` so the tablet's periodic autosave
        overwrites one file per session instead of littering the folder.
        """
        import json as _json
        from datetime import datetime, timezone

        runs = laps_dir.parent / "test_runs"
        runs.mkdir(parents=True, exist_ok=True)
        cat = _slug(str(payload.get("category") or "run"))
        rid = _slug(str(payload.get("run_id") or ""))[:24]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"testrun__{cat}__{rid or stamp}.json"
        path = runs / name
        path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return {"ok": True, "file": name, "path": str(path)}

    if _WEB_DIR.is_dir():
        app.mount("/static", _RevalidatingStatic(directory=str(_WEB_DIR)),
                  name="static")

    return app


def _seed_demo() -> str:
    """Seed a temp lap store with several laps (improving over days) for a demo."""
    import tempfile

    from .recording.lap import Lap, LapSample
    from .recording.storage import save_lap
    from .telemetry.snapshot import SessionType

    import math

    corners = [(0.22, 0.40, 0.31, 120.0), (0.62, 0.80, 0.71, 95.0)]
    zones = {0: (0.16, 0.40), 1: (0.58, 0.80)}

    def track_xz(pos):
        """A closed synthetic circuit; periodic in pos so it joins at 0≡1.

        Sized so the shape agrees with the speeds below: this outline is 6.3 km
        long, which is what 100 s at these speeds covers. It used to be 1.8 km,
        and a demo lap driven round it at 255 km/h was a circuit whose own scale
        bar contradicted its own speedometer — visible now that the charts label
        their axis with the distance measured off these coordinates.
        """
        a = 2 * math.pi * pos
        x = 1080.0 * math.sin(a) + 252.0 * math.sin(2 * a)
        z = 756.0 * math.cos(a) - 180.0 * math.sin(3 * a)
        return x, z

    def profile(pos):
        spd, brake, thr, steer = 255.0, 0.0, 1.0, 0.0
        for lo, hi, apex, vmin in corners:
            if (lo - 0.05) <= pos <= hi:
                half = (hi - lo) / 2
                d = min(1.0, abs(pos - apex) / half)
                spd = vmin + (255.0 - vmin) * d
                brake = 0.85 if (lo - 0.04) <= pos < apex else 0.0
                thr = 1.0 if pos >= apex else 0.0
                steer = 0.28 * ((pos - lo) / (apex - lo) if pos < apex
                               else (hi - pos) / (hi - apex))
                steer = max(0.0, steer)
        return spd, brake, thr, steer

    def build(slow_corner, amt, stint=0):
        # Tyre heat & pressure build up over the stint (rears run hotter on this
        # RWD demo car, with a slight left/right bias), so the "tyres over time"
        # trend shows a real shape instead of flat lines.
        warm = 1.9 * stint
        temp = (82.0 + warm, 83.5 + warm, 88.0 + warm * 1.15, 89.6 + warm * 1.15)
        press = (26.4 + 0.05 * stint, 26.5 + 0.05 * stint,
                 26.9 + 0.06 * stint, 27.0 + 0.06 * stint)
        s, off = [], 0
        for i in range(401):
            pos = i / 400
            spd, brake, thr, steer = profile(pos)
            cx, cz = track_xz(pos)
            wide = False
            if slow_corner is not None:
                lo, hi = zones[slow_corner]
                if lo <= pos <= hi:
                    off += max(1, amt // 5)
                    spd = max(spd - amt, 80.0)
                    wide = True
                    # Ran wide here: nudge the line radially outward so the
                    # track map shows a visibly different racing line.
                    r = math.hypot(cx, cz) or 1.0
                    push = amt * 0.18
                    cx += cx / r * push
                    cz += cz / r * push
            sector = 0 if pos < 0.30 else (1 if pos < 0.65 else 2)  # unequal sectors
            # Synthetic dynamics so the Dynamics tab isn't blank in --demo: G from
            # the pedals/steering, slip ratio as a light front lock under braking
            # and a touch of rear spin on corner exit (low speed + throttle).
            g_long = thr * 0.85 - brake * 1.55
            g_lat = (steer / 0.28) * 2.30
            lock = -0.05 * brake
            spin = 0.06 * thr if spd < 165.0 else 0.0
            slip = (lock, lock, spin, spin)
            # Yaw for the balance ribbon: a normal yaw/steer ratio in clean
            # corners, dropping in the corner where the car ran wide (a push).
            yaw = -steer * (0.5 if wide else 2.0)
            # Gear/RPM from speed so the shift-point view has a shape: revs climb
            # within a gear then drop on the upshift (a sawtooth), gear steps up.
            if spd < 110.0:
                gear, glo, ghi = "2", 60.0, 110.0
            elif spd < 170.0:
                gear, glo, ghi = "3", 110.0, 170.0
            else:
                gear, glo, ghi = "4", 170.0, 260.0
            rpm = int(4200 + max(0.0, min(1.0, (spd - glo) / (ghi - glo))) * 4200)
            s.append(LapSample(int(pos * 100000) + off, pos, spd, thr, brake,
                               steer, gear, rpm, round(g_lat, 3), round(g_long, 3),
                               car_x=cx, car_z=cz, current_sector=sector,
                               yaw_rate=round(yaw, 4),
                               tyre_core_temp=temp, tyre_pressure=press,
                               slip_ratio=slip))
        return Lap("HONE Demo", "Demo Circuit", SessionType.PRACTICE,
                   100000 + off, True, samples=s)

    d = tempfile.mkdtemp(prefix="accoach_webdemo_")
    ref = build(None, 0)          # the fast reference lap (coolest tyres)
    # Dated before the stint laps so the "tyres over time" trend reads as a
    # coherent warm-up across the session instead of a stray cool lap at the end.
    ref.recorded_utc = "2026-06-19T18:00:00+00:00"
    save_lap(ref, d)
    # A few laps getting better over successive days (less time lost each time).
    specs = [(0, 30, "2026-06-20"), (0, 24, "2026-06-21"), (1, 20, "2026-06-22"),
             (0, 16, "2026-06-23"), (1, 12, "2026-06-24"), (0, 8, "2026-06-25")]
    for k, (sc, amt, day) in enumerate(specs, start=1):
        lap = build(sc, amt, stint=k)
        lap.recorded_utc = f"{day}T18:00:00+00:00"
        save_lap(lap, d)
    return d


def _port_in_use(host: str, port: int) -> bool:
    """True if something is already listening on host:port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def main(argv: list[str] | None = None) -> None:
    import threading
    import webbrowser

    import uvicorn

    from .config import load_config
    from .logging_setup import setup_logging
    setup_logging()
    cfg = load_config()
    argv = sys.argv[1:] if argv is None else argv

    port = cfg.web.port
    # Bind host vs local host: in LAN mode uvicorn listens on 0.0.0.0 so other
    # devices can reach it, but the PC's own URL / port-check / browser still use
    # 127.0.0.1. `--lan` forces it on for this run without touching the config.
    bind = "0.0.0.0" if (cfg.lan or "--lan" in argv) else "127.0.0.1"
    local = "127.0.0.1"

    # The engineer page and the analysis page are served by the same app; the
    # launcher passes --engineer to land directly on the setup editor.
    path = "/engineer" if "--engineer" in argv else "/"
    url = f"http://{local}:{port}{path}"

    # If a server is already up (e.g. the user opened Analysis earlier), don't try
    # to bind a second one — just open the browser at the requested page.
    if _port_in_use(local, port):
        print(f"HONE already running: opening {url}")
        webbrowser.open(url)
        return

    laps_dir = _seed_demo() if "--demo" in argv else cfg.laps_path()
    if "--demo" in argv:
        print("HONE analysis in DEMO mode (synthetic laps)")

    print(f"HONE analysis on {url}  (Ctrl+C to stop)")
    if bind != local:
        print("LAN access ON — other devices on your network can reach this app.")
    # Open the browser once the server has had a moment to come up.
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_api(laps_dir, demo="--demo" in argv),
                host=bind, port=port, log_level="warning")


if __name__ == "__main__":
    main()
