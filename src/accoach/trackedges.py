"""Where the asphalt ends — read out of Assetto Corsa's own AI spline.

The telemetry says where the car was; it has never said where the road was. AC
ships that second fact for every installed track, in ``ai/fast_lane.ai``: the
racing line the AI drives, and for each of its points the distance to the left
and right edge of the asphalt. The decoding, and the evidence that it is right,
are in `SPIKE-BORDI.md` — including the four bytes (a repeated point count) whose
absence made an earlier attempt read "gas = 36.79".

**The geometry is not tied to the game the lap came from.** It used to be: the
first version demanded that the spline's coordinates and the lap's coordinates be
the same numbers, which meant the drawing appeared on Assetto Corsa and nowhere
else — the one place in this app where what you saw depended on which sim you had
launched. It shouldn't, and it no longer does. A circuit is a circuit: the shape
you drove is *fitted* onto the shape in the file (rotation, translation and a
scale that has to come out at 1), and if the two are the same place the fit says
so in metres. So an ACC lap gets its asphalt from the same track's AC files, and
Monza — 187 m out in raw coordinates, and refused for it — comes back in at 4 m.

What is left to say no to:

* **it may not be the same circuit.** The fit is only believed when the residual
  is small AND the scale is ~1: both, because either alone can be fooled. Spa
  1998 fits modern Spa at scale 1.000 and is still a different track (58 m); a
  lap whose coordinates are broken fits *everything* to 8 m by shrinking the
  circuit seventy times over;
* **there may be no file at all** — a driver with only ACC (whose own track data
  is packed) and no AC installed, a mod track without an AI line, a Steam library
  somewhere unusual.

Both cases return ``None``. Nothing here guesses: an edge we cannot read is an
edge we do not draw.

One more thing the caller has to carry through to the user: these are the edges
of the **asphalt**, not the limits of the track. A clean lap uses the kerbs and
sits a couple of metres past them.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

# Header: version, point count, lapTime, sampleCount. Then `count` points of
# (x, y, z, length, id), then the count AGAIN, then `count` detail records.
_HEAD = 16
_POINT = 20
_DETAIL = 72
_SIDE_L, _SIDE_R, _FX, _FZ = 5, 6, 13, 15
_VERSION = 7

# --- deciding whether two shapes are the same circuit ------------------------
# Measured on the 39 real laps against the four installed splines — 24 pairings,
# every one classified correctly by these two numbers together:
#
#   giro           spline      p95      scala
#   Imola          imola      17.3      0.999   <- il peggiore dei veri
#   monza          monza       4.2      1.001   <- 187 m di scarto grezzo
#   spa            spa         4.0      1.000
#   suzuka         suzuka      2.4      1.000
#   spa_1998       spa        58.3      1.000   <- altro tracciato, scala giusta
#   ks_nurburgring qualunque  12-18     0.015   <- coordinate rotte, forma finta
#   pista sbagliata           162-839   0.68-1.23
#
# The gap between the worst true match (17.3 m) and the best false one (58.3 m)
# is 3.4x, so the threshold sits in open space rather than on a boundary.
#
# The 95th percentile rather than the mean: a layout change is *local* — Spa 1998
# is modern Spa everywhere except one corner, and an average dilutes exactly the
# evidence that matters.
_FIT_P95_M = 25.0
# And the scale, because the residual alone is not enough. A lap whose
# coordinates collapsed to nearly nothing (the Nürburgring laps recorded before
# the AC1 fix) matches *every* circuit beautifully once you are allowed to shrink
# it to the size of a car park.
_FIT_SCALE = (0.97, 1.03)
# Points compared. 200 is one every 25-35 m: enough that a missing chicane
# cannot hide between two of them, cheap enough to try every rotation.
_FIT_N = 200
# The two shapes start wherever their own files start. Correct pairs all came out
# at offset 0 — the spline does begin at the start line — but that is an
# observation about four Kunos tracks, not a rule to build on.
_FIT_STEP = 4

# Beyond this the "edge" isn't an edge: a handful of points in some files carry a
# side of hundreds of metres (a pit exit, or a spline that wanders off the
# asphalt). Drawing them would put a spike through the middle of the picture.
_MAX_SIDE_M = 30.0


@dataclass(slots=True)
class TrackEdges:
    """One track's asphalt, as two lines either side of the AI's racing line."""

    track: str
    x: list[float]
    z: list[float]
    left: list[float]        # metres to the left edge at each point
    right: list[float]       # metres to the right edge
    # Indices where the edge does NOT continue from the point before, because
    # the points in between were unreadable. Measured on the archive: Suzuka
    # drops 228 points in one run, and joining across it drew 343 m of straight
    # "asphalt" through the middle of the circuit. A hole has to stay a hole.
    breaks: set[int] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.x)

    def width_m(self) -> float:
        """Median width, for a sanity check by whoever is reading this."""
        w = sorted(l + r for l, r in zip(self.left, self.right))
        return round(w[len(w) // 2], 1) if w else 0.0

    def _forward(self, i: int) -> tuple[float, float]:
        """Unit heading at point ``i``, taken from a step that really exists.

        Normally the step to the next point. At the last point before a hole
        that step spans the hole, so the heading comes from behind instead —
        otherwise the two edge points there are thrown out sideways, and the
        ribbon ends with a flick that looks like a corner.
        """
        n = len(self.x)
        j = (i + 1) % n
        if j in self.breaks or n < 2:
            j, i = i, (i - 1) % n
        dx, dz = self.x[j] - self.x[i], self.z[j] - self.z[i]
        d = math.hypot(dx, dz) or 1.0
        return dx / d, dz / d

    def edge_points(self) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """The two edges as world (x, z) polylines, in spline order."""
        left: list[tuple[float, float]] = []
        right: list[tuple[float, float]] = []
        for i in range(len(self.x)):
            fx, fz = self._forward(i)
            # Perpendicular on the ground: the third axis is height, and a
            # track's width is measured flat.
            px, pz = -fz, fx
            left.append((self.x[i] + px * self.left[i], self.z[i] + pz * self.left[i]))
            right.append((self.x[i] - px * self.right[i], self.z[i] - pz * self.right[i]))
        return left, right

    def _crosses_hole(self, a: int, b: int) -> bool:
        """Does the walk from ``a`` forward to ``b`` pass through a hole?

        Asked about the interval and not about ``b`` alone, because the drawing
        thins the walk: consecutive points in the picture can be ten apart on
        the spline, and a hole between them is still a hole.
        """
        n = len(self.x)
        span = (b - a) % n or n
        return any((k - a) % n <= span for k in self.breaks)

    def runs(self, idx: list[int]) -> list[list[int]]:
        """Split a walk of indices wherever the asphalt stops being known.

        Everything drawn goes through here, so a hole in the data comes out as a
        hole in the picture rather than as a shortcut across it.
        """
        out: list[list[int]] = []
        cur: list[int] = []
        for i in idx:
            if cur and self._crosses_hole(cur[-1], i):
                out.append(cur)
                cur = []
            cur.append(i)
        if cur:
            out.append(cur)
        return [r for r in out if len(r) > 1]


# --- finding the game -------------------------------------------------------

def _steam_libraries() -> list[Path]:
    """Every Steam library folder this machine knows about.

    Games are routinely installed on a second drive; looking only in Program
    Files finds the launcher's own library and nobody else's.
    """
    roots = [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    out: list[Path] = []
    for r in roots:
        if r.is_dir():
            out.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # The file is Valve's own key/value format; the only thing needed from it
        # is every "path" value, so a regex beats a parser as a dependency.
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = Path(m.group(1).replace("\\\\", "\\"))
            if p.is_dir():
                out.append(p)
    return out


def tracks_dir() -> Path | None:
    """Assetto Corsa's ``content/tracks``, or None if AC isn't installed here."""
    for lib in _steam_libraries():
        p = lib / "steamapps" / "common" / "assettocorsa" / "content" / "tracks"
        if p.is_dir():
            return p
    return None


def spline_path(track: str) -> Path | None:
    """The AI line for ``track``: its own, or the first layout that has one."""
    root = tracks_dir()
    if root is None or not track:
        return None
    # Lap files carry the folder name the sim reported, but not always its case.
    folder = root / track
    if not folder.is_dir():
        folder = next((p for p in root.iterdir()
                       if p.is_dir() and p.name.lower() == track.lower()), None)
        if folder is None:
            return None
    direct = folder / "ai" / "fast_lane.ai"
    if direct.exists():
        return direct
    return next(iter(sorted(folder.glob("*/ai/fast_lane.ai"))), None)


# --- reading it -------------------------------------------------------------

def read_edges(path: Path) -> TrackEdges | None:
    """Parse one ``fast_lane.ai``. None when it isn't the format we decoded."""
    try:
        b = path.read_bytes()
    except OSError:
        return None
    if len(b) < _HEAD + _POINT:
        return None
    version, count = struct.unpack_from("<2i", b, 0)
    if version != _VERSION or count <= 0:
        return None
    detail_at = _HEAD + count * _POINT
    if len(b) < detail_at + 4 + count * _DETAIL:
        return None
    # The count is repeated as the detail block's own header. If the two ever
    # disagree we are not reading what we think we are — and reading on would
    # produce numbers that look like data.
    if struct.unpack_from("<i", b, detail_at)[0] != count:
        return None
    detail_at += 4

    xs, zs, left, right = [], [], [], []
    breaks: set[int] = set()
    skipped = False
    for i in range(count):
        x, _y, z = struct.unpack_from("<3f", b, _HEAD + i * _POINT)
        d = struct.unpack_from("<18f", b, detail_at + i * _DETAIL)
        sl, sr = d[_SIDE_L], d[_SIDE_R]
        if not (0.0 < sl < _MAX_SIDE_M and 0.0 < sr < _MAX_SIDE_M):
            # Dropping the point is right — a side of hundreds of metres is not
            # an edge. Dropping it *silently* is not: the two survivors either
            # side of the hole then join up, and the ribbon takes a shortcut
            # across whatever is in between (343 m of it, at Suzuka).
            skipped = True
            continue
        if skipped and xs:
            breaks.add(len(xs))
        skipped = False
        xs.append(x); zs.append(z); left.append(sl); right.append(sr)
    if len(xs) < 16:
        return None
    # A hole that ends at the last point wraps round to the first one.
    if skipped and xs:
        breaks.add(0)
    return TrackEdges(track=path.parent.parent.name, x=xs, z=zs,
                      left=left, right=right, breaks=breaks)


# --- putting the track under the lap ----------------------------------------

def _resample(xs: list[float], zs: list[float], n: int) -> list[tuple[float, float]]:
    """``n`` points spread evenly *by distance* around a closed shape.

    By distance and not by index, because the two shapes are sampled by whatever
    each file felt like: the spline puts a point every metre and a half, the
    recorder puts one every 60th of a second, so a straight is dense in one and
    sparse in the other. Comparing them index by index would compare a corner
    against a straight and call the circuit a different circuit.
    """
    d = [0.0]
    for i in range(1, len(xs)):
        d.append(d[-1] + math.hypot(xs[i] - xs[i - 1], zs[i] - zs[i - 1]))
    total = d[-1]
    if total <= 0:
        return []
    out: list[tuple[float, float]] = []
    j = 0
    for k in range(n):
        target = total * k / n
        while j < len(d) - 2 and d[j + 1] < target:
            j += 1
        f = (target - d[j]) / max(1e-9, d[j + 1] - d[j])
        out.append((xs[j] + f * (xs[j + 1] - xs[j]), zs[j] + f * (zs[j + 1] - zs[j])))
    return out


@dataclass(frozen=True, slots=True)
class Fit:
    """How to move a track's own coordinates onto a lap's."""

    scale: float
    cos: float
    sin: float
    dx: float
    dz: float
    p95_m: float
    mirror: bool

    def apply(self, x: float, z: float) -> tuple[float, float]:
        if self.mirror:
            x = -x
        return (self.scale * (x * self.cos - z * self.sin) + self.dx,
                self.scale * (x * self.sin + z * self.cos) + self.dz)


def _kabsch(a: list[tuple[float, float]], b: list[tuple[float, float]]):
    """The rotation and scale that best carry ``a`` onto ``b``, both centred.

    Closed form, not a search: for a rotation plus a uniform scale the best
    answer is an arctangent of two sums. Iterating towards it would be slower and
    would also be able to stop somewhere that isn't the answer.
    """
    sxx = sum(p[0] * q[0] + p[1] * q[1] for p, q in zip(a, b))
    sxy = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(a, b))
    norm = sum(p[0] ** 2 + p[1] ** 2 for p in a)
    if norm <= 0:
        return None
    theta = math.atan2(sxy, sxx)
    scale = math.hypot(sxx, sxy) / norm
    c, s = math.cos(theta), math.sin(theta)
    err = sorted(math.hypot(scale * (p[0] * c - p[1] * s) - q[0],
                            scale * (p[0] * s + p[1] * c) - q[1])
                 for p, q in zip(a, b))
    return scale, c, s, err[int(0.95 * len(err))]


def fit(edges: TrackEdges, points) -> Fit | None:
    """Is this the circuit the lap was driven on, and where does it sit?

    Answers both at once, in metres. The older version of this asked only
    "are the coordinates already the same numbers?", which is a question about
    file formats rather than about places — and it is why the drawing used to
    appear on one sim and not the other.
    """
    xs = [p.x for p in points]
    zs = [p.z for p in points]
    if len(xs) < 2 or not (any(xs) or any(zs)):
        return None
    lap = _resample(xs, zs, _FIT_N)
    road = _resample(edges.x, edges.z, _FIT_N)
    if len(lap) < _FIT_N or len(road) < _FIT_N:
        return None
    lb = (sum(p[0] for p in lap) / _FIT_N, sum(p[1] for p in lap) / _FIT_N)
    b = [(p[0] - lb[0], p[1] - lb[1]) for p in lap]

    best: Fit | None = None
    for mirror in (False, True):
        src = [(-x, z) for x, z in road] if mirror else road
        ra = (sum(p[0] for p in src) / _FIT_N, sum(p[1] for p in src) / _FIT_N)
        cent = [(p[0] - ra[0], p[1] - ra[1]) for p in src]
        # Where each shape starts is an accident of its file, so every rotation
        # of one against the other is tried and the best one wins.
        for shift in range(0, _FIT_N, _FIT_STEP):
            got = _kabsch(cent[shift:] + cent[:shift], b)
            if got is None:
                continue
            scale, c, s, p95 = got
            if best is not None and p95 >= best.p95_m:
                continue
            # The translation is derived, not searched: once the rotation is
            # known, the two centres have to end up on top of each other.
            # ``ra`` is already the mirrored centroid — mirroring it again here
            # would move the track by twice its own offset.
            ax, az = ra
            best = Fit(scale=scale, cos=c, sin=s, mirror=mirror, p95_m=p95,
                       dx=lb[0] - scale * (ax * c - az * s),
                       dz=lb[1] - scale * (ax * s + az * c))
    if best is None or best.p95_m > _FIT_P95_M:
        return None
    if not (_FIT_SCALE[0] <= best.scale <= _FIT_SCALE[1]):
        return None
    return best


def placed(edges: TrackEdges, at: Fit) -> TrackEdges:
    """The same asphalt, moved into the lap's coordinates."""
    xz = [at.apply(x, z) for x, z in zip(edges.x, edges.z)]
    return TrackEdges(
        track=edges.track,
        x=[p[0] for p in xz], z=[p[1] for p in xz],
        # The widths ride along with the scale, or a circuit fitted at 0.99 would
        # keep full-size edges around a shrunken centre line.
        left=[v * at.scale for v in edges.left],
        right=[v * at.scale for v in edges.right],
        breaks=set(edges.breaks),
    )


def _nearest(edges: TrackEdges, x: float, z: float) -> int:
    best, bd = 0, float("inf")
    for i in range(len(edges.x)):
        d = (edges.x[i] - x) ** 2 + (edges.z[i] - z) ** 2
        if d < bd:
            bd, best = d, i
    return best


def crop(edges: TrackEdges, xz: list[tuple[float, float]],
         pad: int = 6, max_points: int = 160) -> dict | None:
    """The two edges alongside one stretch of driven line, as world polylines.

    The spline is indexed by its own points, not by lap position, so the stretch
    is found by matching the ends of the driven crop to the nearest spline points
    and walking forward between them — forward including *through* the start
    line, since a corner is allowed to straddle it.

    ``pad`` extends the result a few points each way so the ribbon doesn't stop
    dead at the edge of the picture.
    """
    if not xz or len(edges) < 2:
        return None
    n = len(edges)
    i0 = _nearest(edges, *xz[0])
    i1 = _nearest(edges, *xz[-1])
    steps = (i1 - i0) % n
    # A stretch that appears to run most of the way round the track is not a
    # corner: it's the two ends matching in the wrong order (a hairpin whose
    # entry and exit are metres apart in space, half a lap apart on the line).
    if steps == 0 or steps > n // 2:
        return None
    idx = [(i0 - pad + k) % n for k in range(steps + 2 * pad + 1)]
    # An edge is a smooth line: a point every metre and a half draws the same
    # ribbon as a point every ten, and fifteen corners' worth of the former is a
    # payload the browser pays for on every lap it opens.
    if len(idx) > max_points:
        step = len(idx) / max_points
        idx = [idx[int(k * step)] for k in range(max_points)]
    return _shape(edges, idx)


def _shape(edges: TrackEdges, idx: list[int], places: int = 2) -> dict | None:
    """Index walk -> the polylines to draw, one entry per unbroken stretch."""
    left, right = edges.edge_points()
    runs = [
        {"left": [[round(left[i][0], places), round(left[i][1], places)] for i in r],
         "right": [[round(right[i][0], places), round(right[i][1], places)] for i in r]}
        for r in edges.runs(idx)
    ]
    if not runs:
        return None
    return {"runs": runs, "width_m": edges.width_m()}


_cache: dict[str, TrackEdges | None] = {}


def edges_for(track: str, points=None) -> TrackEdges | None:
    """The asphalt for ``track``, laid under ``points`` when they are given.

    Cached per track: the files are 1-3 MB and the report re-asks on every
    corner. A miss is cached too — a track without an AI line will not grow one
    while the app is open.

    With ``points`` the answer comes back **in the lap's own coordinates**,
    whichever sim wrote them, or None when the fit says this isn't that circuit.
    """
    key = (track or "").lower()
    if key not in _cache:
        path = spline_path(track)
        _cache[key] = read_edges(path) if path else None
    got = _cache[key]
    if got is None or points is None:
        return got
    at = fit(got, points)
    return placed(got, at) if at else None
