"""Where the car actually went — the driven line, measured against a reference.

The report already knows *when* you lost time (delta, sectors, debrief) and
*what the car did* (G, slip, balance). What it could not say is **where on the
tarmac you were**: the track map draws two lines and leaves the reading to the
eye, and the line-deviation trace gives signed metres with no idea of what a
plus sign means at that corner.

This module turns the two paths into numbers a driver can act on, corner by
corner:

* the **side** you are on, expressed as *inside* (+) / *outside* (−) of the
  reference line rather than as a world-axis sign — a metre to the right means
  the inside of a right-hander and the outside of a left one, and no driver
  should have to do that translation in their head;
* **where your apex is** along the track compared with the reference's, in
  metres (the early-apex/late-apex read);
* the **radius you actually drove** through the corner, and the reference's:
  a tighter arc at the same speed is grip spent on rotation;
* the **extra distance** you covered, per corner and over the lap.

Everything is derived from ``car_x``/``car_z`` (recorded since v3, axes
validated live 2026-06-28) plus the corners the analyzer already detects, so no
new capture and no per-track database is involved. Laps without coordinates come
back empty rather than fabricated.

Deliberately descriptive, not prescriptive: the tags this module attaches to a
corner state a geometric fact ("apex 8 m earlier", "1.4 m wide on exit"). The
*why* and the *what to do* belong to the debrief, which owns the causal model —
two modules giving advice about the same corner is how they end up disagreeing.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from .recording.lap import strip_leading_wrap
# Shared on purpose with the corner classifier: the report and the detector must
# measure the same geometry, or a corner called "hairpin" over there can show a
# 90 m radius over here. Sign convention (negative = left, positive = right) was
# validated against five named corners of a real Imola lap.
from .track import _menger_curvature as signed_curvature

# --- what counts as a difference -------------------------------------------
# Below ~0.8 m two lines are the same line: it is inside one driver's own
# lap-to-lap spread, and it is also about half a car's width — the smallest
# displacement anybody can aim for on track. Reporting less would fill the view
# with noise that reads as findings.
_MIN_OFFSET_M = 0.8
# The apex is a speed minimum, and a speed minimum is flat by definition: on a
# long corner the bottom of the V moves a few metres between two laps with no
# change in the line. 5 m is short enough to catch a genuinely different apex
# and long enough to sit outside that flatness.
_MIN_APEX_SHIFT_M = 5.0
# …and on a long corner 5 m is nowhere near enough. Measured over the archive:
# Fagnes reported a 60 m "apex shift" between two laps whose minimum speed was
# identical to the km/h, because the bottom of the V is flat for ~100 m there;
# Casio Triangle 54 m, Tamburello 60 m, same story. So the floor is not a
# distance at all — it is *the flat part itself*. The stretch where speed stays
# within this fraction of the corner's minimum is the apex "plateau", and two
# plateaus that overlap are two laps apexing in the same place, whatever the two
# minima happen to measure. 2% is a little over 1 km/h at 60 km/h: below the
# frame-to-frame wobble of the speed channel, above nothing that matters.
_APEX_FLAT = 0.02
# Below this fraction of the reference's minimum speed the car was not cornering:
# it spun, went off, or stopped. Measured across every recorded lap: the two laps
# with an off read 0.34 and 0.36, and every other corner of every other lap is at
# 0.80 or above — a gap wide enough that the exact number doesn't matter much.
# In that state "your apex moved 174 m" is a true sentence about a lap that no
# longer had an apex.
_OFF_VMIN_RATIO = 0.60
# Extra distance worth a mention. A 2 m detour is ~0.05 s at 150 km/h — the same
# order as the debrief's own reporting floor.
_MIN_EXTRA_M = 2.0
# A radius difference only means something as a proportion: 5 m on a hairpin is
# a different corner, 5 m on a 400 m kink is measurement noise.
_MIN_RADIUS_RATIO = 0.10

# Curvature stencil, in metres of path rather than in samples. Sample spacing is
# a function of speed (≈1.2 m at 250 km/h, ≈0.4 m at 80 km/h at 60 Hz), so a
# fixed number of samples measures a 7 m chord on the straight and a 2 m chord at
# the apex — exactly backwards, since the apex is where the arc matters.
_CURV_SPAN_M = 6.0
# Radius reported per corner is the tightest the driver *sustained*, taken as a
# high percentile of |curvature| instead of its maximum: one kerb strike spikes
# the curvature of three samples and would otherwise be reported as the corner.
_RADIUS_Q = 0.90
# Above this the arc is a straight in disguise; reporting "R = 3 km" as a corner
# radius is a true number that tells nobody anything.
_MAX_RADIUS_M = 1000.0


@dataclass(slots=True)
class LinePoint:
    """One sample of a driven line, reduced to what the geometry needs."""

    pos: float
    x: float
    z: float
    speed_kmh: float
    brake: float
    throttle: float = 0.0


@dataclass(slots=True)
class CornerLine:
    """How your line through one corner differs from the reference's.

    Offsets are signed **inside (+) / outside (−)** relative to the way the
    corner turns — but only where "inside" means something. ``sided`` says
    whether it did; when it is False the numbers are the raw right(+)/left(−)
    side of the reference line, and the view says so.

    Two cases have no inside. A corner the detector couldn't classify (a lap
    with no coordinates), and — found on 2026-07-31 — **a chicane**: the inside
    of a Variante del Rettifilo is on the right for the first half and on the
    left for the second, so any single sign is right about one half and wrong
    about the other. Whichever half you pick, a number on the page is confidently
    inverted. Saying "3.3 m to the right of the line" is true throughout.
    """

    index: int
    name: str
    direction: str
    kind: str
    entry: float
    apex: float
    exit: float
    # Line, in metres. Positive = inside of the corner, negative = outside.
    entry_m: float = 0.0
    apex_m: float = 0.0
    exit_m: float = 0.0
    widest_m: float = 0.0        # biggest excursion to the outside (>= 0)
    widest_pos: float = 0.0
    tightest_m: float = 0.0      # biggest excursion to the inside (>= 0)
    # Apex placement along the track: + = you apex later than the reference.
    apex_shift_m: float = 0.0
    apex_pos_you: float = 0.0
    apex_pos_ref: float = 0.0
    # Metres over which both laps' flat minima overlap. Greater than zero means
    # the two apexes are the same place and `apex_shift_m` is measuring where
    # inside a flat bottom each lap's lowest sample happened to land.
    apex_flat_m: float = 0.0
    # The car wasn't cornering here (spun, went off, stopped): the geometry below
    # is still what was recorded, but none of it is a line anybody chose.
    off_here: bool = False
    # Arc actually driven at the tightest point of the corner.
    radius_m: float = 0.0
    radius_ref_m: float = 0.0
    # Distance covered through the corner, yours minus the reference's.
    extra_m: float = 0.0
    vmin: float = 0.0
    vmin_ref: float = 0.0
    vexit: float = 0.0
    vexit_ref: float = 0.0
    #: Do the offsets above mean inside/outside (True) or right/left (False)?
    sided: bool = True
    tags: list[tuple[str, dict]] = field(default_factory=list)


@dataclass(slots=True)
class LineReport:
    """The whole lap's line, plus one entry per corner."""

    path_m: float = 0.0
    ref_path_m: float = 0.0
    extra_m: float = 0.0
    mean_off_m: float = 0.0
    max_off_m: float = 0.0
    max_off_where: str = ""
    corners: list[CornerLine] = field(default_factory=list)


# --- reading a lap ----------------------------------------------------------

def line_points(lap_or_samples) -> list[LinePoint]:
    """A lap's driven line: strictly forward in position, coordinates only.

    Mirrors what ``detect_corners`` does to the same samples (leading wrap
    stripped, non-advancing frames dropped) so positions line up between the two
    and a corner's span always indexes the same stretch of line.
    """
    samples = getattr(lap_or_samples, "samples", lap_or_samples)
    out: list[LinePoint] = []
    last = -1.0
    for s in strip_leading_wrap(samples):
        if s.pos <= last:
            continue
        last = s.pos
        out.append(LinePoint(s.pos, s.car_x, s.car_z, s.speed_kmh,
                             s.brake, s.throttle))
    return out


def has_line(points: list[LinePoint]) -> bool:
    """True when the lap carries real coordinates (v3+), not an all-zero stub."""
    return any(p.x or p.z for p in points)


def path_length(points: list[LinePoint], lo: float = 0.0, hi: float = 1.0) -> float:
    """Metres travelled along the driven line between two track positions."""
    total = 0.0
    prev: LinePoint | None = None
    for p in points:
        if p.pos < lo or p.pos > hi:
            continue
        if prev is not None:
            total += math.hypot(p.x - prev.x, p.z - prev.z)
        prev = p
    return total


# A step longer than this isn't driving. At 300 km/h a 60 Hz frame covers 1.4 m,
# and the worst rate ever measured on our own recorder (9 Hz) still only ~9 m. A
# 50 m jump is a teleport — a pit reset, a session restart, a lap stitched over a
# gap — and adding it to the odometer would print a kilometre nobody drove on the
# axis of every chart.
_MAX_STEP_M = 50.0


def cumulative_distance(points: list[LinePoint]) -> list[float]:
    """Metres covered along the driven line at each point, from the first one.

    This is what makes a distance axis honest. The games hand us position as a
    fraction of the lap; turning that into metres by multiplying by a published
    track length would be an assumption on two counts — the number itself, and
    that position advances linearly with distance. Here it is measured on the
    coordinates we recorded, the same geometry :func:`path_length` reports as
    "you drove N m".

    One value per point, in the order given, so a caller can hand back whatever
    it is already plotting. A lap with no coordinates comes back all zeros —
    which the caller must read as "no distance to show", not as "the start line".
    """
    out = [0.0] * len(points)
    total = 0.0
    for i in range(1, len(points)):
        step = math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z)
        if step <= _MAX_STEP_M:
            total += step
        out[i] = round(total, 1)
    return out


def curvature_profile(points: list[LinePoint],
                      span_m: float = _CURV_SPAN_M) -> list[float]:
    """Signed curvature (1/m) at each point: negative = left, positive = right.

    The stencil is a fixed *distance* along the path, not a fixed number of
    samples, so the arc measured at a 240 km/h kink and at a 60 km/h hairpin is
    the same length of tarmac.
    """
    n = len(points)
    out = [0.0] * n
    if n < 3:
        return out
    # Cumulative distance, so walking out to ±span_m is a binary search.
    dist = [0.0] * n
    for i in range(1, n):
        dist[i] = dist[i - 1] + math.hypot(points[i].x - points[i - 1].x,
                                           points[i].z - points[i - 1].z)
    for i in range(n):
        a = bisect.bisect_left(dist, dist[i] - span_m)
        b = bisect.bisect_left(dist, dist[i] + span_m)
        if a >= i or b >= n or b <= i:
            continue
        out[i] = signed_curvature((points[a].x, points[a].z),
                                  (points[i].x, points[i].z),
                                  (points[b].x, points[b].z))
    return out


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def radius_over(points: list[LinePoint], curv: list[float],
                lo: float, hi: float) -> float:
    """The radius (m) actually sustained between two positions, 0 when straight."""
    ks = [abs(curv[i]) for i, p in enumerate(points) if lo <= p.pos <= hi]
    k = _percentile(ks, _RADIUS_Q)
    if k <= 0.0:
        return 0.0
    r = 1.0 / k
    return 0.0 if r > _MAX_RADIUS_M else round(r, 1)


# --- one line against another ----------------------------------------------
# Search window when pairing a point of one lap with the reference line, in
# normalized position. The two lines are metres apart, so the matching vertex is
# always within a fraction of a percent of track; ±1% (≈58 m at Monza) is a
# generous bound that turns an O(n·m) scan into a local one — which is what makes
# it affordable to run this on full-resolution laps instead of the 600-point
# plotting downsample.
_MATCH_WINDOW = 0.01


def lateral_offsets(review: list[LinePoint], base: list[LinePoint]) -> list[float]:
    """Signed metres of each reviewed point from the reference line.

    Positive = to the **right** of the reference's direction of travel (the same
    cross-product convention as :func:`signed_curvature`, so multiplying by a
    corner's turn sign converts it to inside/outside). Empty when either line has
    no usable geometry. There is one value per reviewed point, in the order given
    — callers plot it against the same lap's position channel.
    """
    n = len(base)
    if n < 3 or len(review) < 2:
        return []
    # The window search below is a bisect, so the reference must be ordered.
    # Callers hand us whatever they are already plotting, and a lap's first
    # sample can still read pos≈1.0 (the pre-line wrap frame) — one unsorted
    # element is enough to make every window wrong.
    base = sorted(base, key=lambda p: p.pos)
    bpos = [p.pos for p in base]
    out: list[float] = []
    for s in review:
        lo = bisect.bisect_left(bpos, s.pos - _MATCH_WINDOW)
        hi = bisect.bisect_right(bpos, s.pos + _MATCH_WINDOW)
        if hi - lo < 2:                     # degenerate window: fall back to all
            lo, hi = 0, n
        bestj, bestd = lo, float("inf")
        for j in range(lo, hi):
            dx = base[j].x - s.x
            dz = base[j].z - s.z
            d = dx * dx + dz * dz
            if d < bestd:
                bestd = d
                bestj = j
        j0 = max(0, bestj - 1)
        j1 = min(n - 1, bestj + 1)
        dxr = base[j1].x - base[j0].x
        dzr = base[j1].z - base[j0].z
        length = math.hypot(dxr, dzr) or 1.0
        ox = s.x - base[bestj].x
        oz = s.z - base[bestj].z
        out.append(round((dxr * oz - dzr * ox) / length, 2))
    return out


def _turn_sign(direction: str) -> float:
    """+1 for a right-hander, -1 for a left-hander, 0 when unknown.

    Multiplying a right(+)/left(−) offset by this turns it into inside(+)/
    outside(−), which is the only form a driver reads without translating.
    """
    return 1.0 if direction == "right" else (-1.0 if direction == "left" else 0.0)


def _at(points: list[LinePoint], values: list[float], pos: float) -> float:
    """The value of a per-point channel at (the sample nearest to) ``pos``."""
    if not values:
        return 0.0
    i = bisect.bisect_left([p.pos for p in points], pos)
    i = min(len(values) - 1, max(0, i))
    return values[i]


def _speed_at(points: list[LinePoint], pos: float) -> float:
    if not points:
        return 0.0
    i = bisect.bisect_left([p.pos for p in points], pos)
    i = min(len(points) - 1, max(0, i))
    return points[i].speed_kmh


def _apex_pos(points: list[LinePoint], lo: float, hi: float) -> float:
    """Position of the speed minimum in a span — the driver's actual apex."""
    best, bestv = lo, float("inf")
    for p in points:
        if lo <= p.pos <= hi and p.speed_kmh < bestv:
            bestv, best = p.speed_kmh, p.pos
    return best


def apex_plateau(points: list[LinePoint], lo: float, hi: float,
                 flat: float = _APEX_FLAT) -> tuple[float, float] | None:
    """The flat bottom of a corner: where speed stays within ``flat`` of its
    minimum, as a (first, last) pair of track positions.

    This is the width of the answer to "where is the apex". On a hairpin it is a
    few metres and the apex is a point; through Fagnes it is a hundred, and two
    laps whose lowest sample lands at opposite ends of it have not apexed in
    different places — they have apexed in the same flat place twice.
    """
    sel = [p for p in points if lo <= p.pos <= hi]
    if not sel:
        return None
    vmin = min(p.speed_kmh for p in sel)
    inside = [p.pos for p in sel if p.speed_kmh <= vmin * (1.0 + flat)]
    return (min(inside), max(inside)) if inside else None


def _round_half_up(value: float, digits: int = 1) -> float:
    """Arrotonda come fa il browser, non come fa Python.

    `round()` in Python arrotonda alla cifra pari: `round(5.25, 1)` dà **5.2**.
    `toFixed(1)` in JavaScript dà **5.3**. Sulla stessa schermata la Traiettoria
    scriveva «5,2 m largo in uscita» nel chip (scritto qui) e «Uscita 5,3 m
    fuori» nella tabella otto righe sotto (formattata nel browser): due valori
    per lo stesso metro, e il pilota che se ne accorge smette di fidarsi anche
    dei numeri giusti.

    Il verso della correzione è quello: il server si allinea al browser, perché
    metà dei numeri di questa pagina sono formattati là e non hanno un
    equivalente qui.
    """
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(value)).quantize(q, rounding=ROUND_HALF_UP))


def _tags(c: CornerLine) -> list[tuple[str, dict]]:
    """Geometric facts about this corner, biggest first, at most three.

    Each is a fact with its number, not an instruction — see the module note on
    why advice stays in the debrief. Ranked by how far past its own floor the
    measurement is, so a 4 m detour outranks a 1 m one and both outrank an apex
    that moved by six metres on a corner where 5 m is the floor.
    """
    out: list[tuple[float, str, dict]] = []

    def add(score: float, key: str, **kw) -> None:
        out.append((score, key, kw))

    # Nothing here is a choice: say that first, and say it with the number that
    # establishes it rather than with a word the driver has to take on trust.
    if c.off_here:
        add(1e9, "off_here", v=round(c.vmin), vr=round(c.vmin_ref))
    # An apex that "moved" inside a flat bottom hasn't moved. Reporting it is how
    # a driver ends up chasing a difference between two identical laps.
    if c.apex_flat_m > 0.0 or c.off_here:
        pass
    elif abs(c.apex_shift_m) >= _MIN_APEX_SHIFT_M:
        add(abs(c.apex_shift_m) / _MIN_APEX_SHIFT_M,
            "apex_late" if c.apex_shift_m > 0 else "apex_early",
            m=abs(round(c.apex_shift_m)))
    for where, value in (("entry", c.entry_m), ("apex", c.apex_m), ("exit", c.exit_m)):
        if abs(value) < _MIN_OFFSET_M:
            continue
        if c.sided:
            word = "tight_" if value > 0 else "wide_"
        else:
            # Nessun interno da nominare: il segno grezzo è il lato della linea.
            word = "right_" if value > 0 else "left_"
        add(abs(value) / _MIN_OFFSET_M, word + where,
            m=abs(_round_half_up(value, 1)))
    if abs(c.extra_m) >= _MIN_EXTRA_M:
        add(abs(c.extra_m) / _MIN_EXTRA_M,
            "longer_line" if c.extra_m > 0 else "shorter_line",
            m=abs(round(c.extra_m)))
    if c.radius_m and c.radius_ref_m:
        ratio = (c.radius_m - c.radius_ref_m) / c.radius_ref_m
        if abs(ratio) >= _MIN_RADIUS_RATIO:
            add(abs(ratio) / _MIN_RADIUS_RATIO,
                "wider_arc" if ratio > 0 else "tighter_arc",
                r=round(c.radius_m), rr=round(c.radius_ref_m))
    out.sort(key=lambda x: x[0], reverse=True)
    return [(key, kw) for _, key, kw in out[:3]]


def build_line_report(review_lap, base_lap, corners,
                      names: dict[int, str] | None = None) -> LineReport:
    """Compare two laps' driven lines, corner by corner.

    ``corners`` are the ones detected on the *baseline* lap (the same list the
    rest of the report is built from), so a corner keeps its number across every
    view; ``names`` is the curated naming the rest of the page uses, passed in
    rather than looked up here so one corner can't be called two things on two
    tabs. Returns an empty report when either lap has no coordinates.
    """
    names = names or {}
    you = line_points(review_lap)
    ref = line_points(base_lap)
    # Where the recorder decided this lap stopped counting, when it knows (v8+).
    # Used only to corroborate a corner the geometry already flags as an off, so
    # an older lap loses the corroboration and nothing else.
    lost_at = getattr(review_lap, "lost_at", None)
    if not (has_line(you) and has_line(ref)):
        return LineReport()

    offsets = lateral_offsets(you, ref)
    if not offsets:
        return LineReport()
    kyou = curvature_profile(you)
    kref = curvature_profile(ref)

    rows: list[CornerLine] = []
    for c in corners:
        lo, hi = c.entry_pos, c.exit_pos
        inside = [(i, p) for i, p in enumerate(you) if lo <= p.pos <= hi]
        if len(inside) < 3:
            continue
        # A chicane has no single inside — see CornerLine — and neither has a
        # corner the detector couldn't classify. Both keep the raw right/left
        # sign rather than inventing an inside, and the view labels the column
        # accordingly instead of lying about which side of the road you were on.
        sided = c.kind != "chicane" and bool(_turn_sign(c.direction))
        s = _turn_sign(c.direction) if sided else 1.0
        signed = [offsets[i] * s for i, _ in inside]

        apex_you = _apex_pos(you, lo, hi)
        # The reference's apex is recomputed here rather than read from
        # ``c.apex_pos``: the detector smooths speed before taking its minimum,
        # so comparing a smoothed apex with a raw one puts a few metres of
        # difference into every corner on the page. Both sides raw, or neither.
        apex_ref = _apex_pos(ref, lo, hi)
        # Measured along the reference line: converting a difference in
        # normalized position into metres with the lap length would be wrong on
        # any track where position isn't linear in distance.
        a, b = sorted((apex_you, apex_ref))
        # `+ 0.0` so an unmoved apex prints as 0.0 and not as -0.0, which reads
        # like a rounding artefact the driver is meant to interpret.
        shift = path_length(ref, a, b) * (1.0 if apex_you > apex_ref else -1.0) + 0.0
        # …and how much of that is the corner simply being flat at the bottom.
        py = apex_plateau(you, lo, hi)
        pr = apex_plateau(ref, lo, hi)
        flat = 0.0
        if py and pr:
            f0, f1 = max(py[0], pr[0]), min(py[1], pr[1])
            if f0 <= f1:
                # Measured along the reference, like the shift it qualifies, so
                # the two numbers are in the same units of tarmac.
                flat = path_length(ref, f0, f1)

        widest = min(signed)          # most negative = furthest to the outside
        tightest = max(signed)
        wpos = inside[signed.index(widest)][1].pos

        ref_inside = [p.speed_kmh for p in ref if lo <= p.pos <= hi]
        vmin = min(p.speed_kmh for _, p in inside)
        vmin_ref = min(ref_inside) if ref_inside else 0.0
        # Off, spin or stop. Two independent signals, either of which is enough:
        # the recorder's own verdict on where the lap stopped counting (v8+, so
        # None on older laps), and a minimum speed that collapsed against the
        # reference's. Neither is inferred from the other.
        off_here = bool(
            (lost_at is not None and lo <= lost_at <= hi)
            or (vmin_ref > 0.0 and vmin < vmin_ref * _OFF_VMIN_RATIO))
        row = CornerLine(
            index=c.index,
            name=names.get(c.index) or c.name or f"Corner {c.index + 1}",
            direction=c.direction, kind=c.kind, sided=sided,
            entry=round(lo, 4), apex=round(c.apex_pos, 4), exit=round(hi, 4),
            entry_m=round(_at(you, offsets, lo) * s, 2),
            apex_m=round(_at(you, offsets, c.apex_pos) * s, 2),
            exit_m=round(_at(you, offsets, hi) * s, 2),
            widest_m=round(-widest, 2) if widest < 0 else 0.0,
            widest_pos=round(wpos, 4),
            tightest_m=round(tightest, 2) if tightest > 0 else 0.0,
            apex_shift_m=round(shift, 1),
            apex_pos_you=round(apex_you, 4),
            apex_pos_ref=round(apex_ref, 4),
            apex_flat_m=round(flat, 1),
            off_here=off_here,
            radius_m=radius_over(you, kyou, lo, hi),
            radius_ref_m=radius_over(ref, kref, lo, hi),
            extra_m=round(path_length(you, lo, hi) - path_length(ref, lo, hi), 1),
            vmin=round(vmin),
            vmin_ref=round(vmin_ref) if ref_inside else 0.0,
            vexit=round(_speed_at(you, hi)),
            vexit_ref=round(_speed_at(ref, hi)),
        )
        row.tags = _tags(row)
        rows.append(row)

    total = path_length(you)
    ref_total = path_length(ref)
    absolute = [abs(v) for v in offsets]
    worst = max(range(len(offsets)), key=lambda i: absolute[i]) if offsets else 0
    wpos = you[worst].pos if offsets else 0.0
    where = next((r.name for r in rows if r.entry <= wpos <= r.exit), "")

    return LineReport(
        path_m=round(total),
        ref_path_m=round(ref_total),
        extra_m=round(total - ref_total, 1),
        mean_off_m=round(sum(absolute) / len(absolute), 2),
        max_off_m=round(absolute[worst], 2),
        max_off_where=where,
        corners=rows,
    )


# --- the zoomed corner ------------------------------------------------------

def corner_path(points: list[LinePoint], lo: float, hi: float,
                margin: float = 0.15, max_points: int = 160) -> dict:
    """One corner's stretch of line, for drawing it zoomed in.

    ``margin`` extends the window by that fraction of the corner's own length at
    each end, so a corner is never drawn flush to the edge of its box — the
    approach and the exit are part of reading a line.
    """
    span = max(1e-6, hi - lo) * margin
    a, b = lo - span, hi + span
    sel = [p for p in points if a <= p.pos <= b]
    if len(sel) > max_points:
        step = len(sel) / max_points
        sel = [sel[int(i * step)] for i in range(max_points)]
    return {
        "pos": [round(p.pos, 5) for p in sel],
        "x": [round(p.x, 2) for p in sel],
        "z": [round(p.z, 2) for p in sel],
        "speed": [round(p.speed_kmh, 1) for p in sel],
        # The two pedals, so the drawing can mark where the braking started and
        # where the power came back on. Without them the zoomed corner says
        # where you went and not what you were doing — and "you are wider at
        # entry" only becomes a diagnosis next to "and you braked 15 m later".
        "brake": [round(p.brake, 2) for p in sel],
        "throttle": [round(p.throttle, 2) for p in sel],
    }


# --- wording ----------------------------------------------------------------
# Written here rather than in the frontend catalogue because the numbers are
# computed here: a template and its value drifting apart ("8 m earlier" rendered
# for a 3 m shift) is the failure mode that keeps text next to its data.
_TAGS: dict[str, dict[str, str]] = {
    # States the measurement, not a verdict: the driver knows what happened here
    # better than we do, and "no line to read" is the honest limit of this view.
    "off_here": {"en": "Down to {v} km/h against {vr}: no line to read here",
                 "it": "Sceso a {v} km/h contro {vr}: qui non c'è traiettoria da leggere"},
    "apex_early": {"en": "Apex {m} m earlier", "it": "Apex {m} m prima"},
    "apex_late": {"en": "Apex {m} m later", "it": "Apex {m} m dopo"},
    "wide_entry": {"en": "{m} m wide on entry", "it": "{m} m largo in entrata"},
    "tight_entry": {"en": "{m} m tight on entry", "it": "{m} m stretto in entrata"},
    "wide_apex": {"en": "{m} m off the apex", "it": "{m} m lontano dall'apex"},
    "tight_apex": {"en": "{m} m inside at the apex", "it": "{m} m più dentro all'apex"},
    "wide_exit": {"en": "{m} m wide on exit", "it": "{m} m largo in uscita"},
    "tight_exit": {"en": "{m} m tight on exit", "it": "{m} m stretto in uscita"},
    # Dove non c'è un interno solo (una variante), «largo» e «stretto» non
    # vogliono dire niente: resta il lato della linea, che è vero comunque.
    "left_entry": {"en": "{m} m left of the line on entry",
                   "it": "{m} m a sinistra della linea in entrata"},
    "right_entry": {"en": "{m} m right of the line on entry",
                    "it": "{m} m a destra della linea in entrata"},
    "left_apex": {"en": "{m} m left of the line at the apex",
                  "it": "{m} m a sinistra della linea all'apex"},
    "right_apex": {"en": "{m} m right of the line at the apex",
                   "it": "{m} m a destra della linea all'apex"},
    "left_exit": {"en": "{m} m left of the line on exit",
                  "it": "{m} m a sinistra della linea in uscita"},
    "right_exit": {"en": "{m} m right of the line on exit",
                   "it": "{m} m a destra della linea in uscita"},
    "longer_line": {"en": "{m} m longer through here", "it": "{m} m di strada in più"},
    "shorter_line": {"en": "{m} m shorter through here", "it": "{m} m di strada in meno"},
    "tighter_arc": {"en": "Tighter arc: {r} m vs {rr} m",
                    "it": "Arco più stretto: {r} m contro {rr} m"},
    "wider_arc": {"en": "Wider arc: {r} m vs {rr} m",
                  "it": "Arco più largo: {r} m contro {rr} m"},
}


def tag_text(key: str, values: dict, lang: str | None = None) -> str:
    """Render one geometric tag in the requested language."""
    from .i18n import current_language

    lg = lang if lang in ("en", "it") else current_language()
    entry = _TAGS.get(key)
    if entry is None:
        return key
    return entry.get(lg, entry["en"]).format(**values)
