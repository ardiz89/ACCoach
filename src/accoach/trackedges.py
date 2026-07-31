"""Where the asphalt ends — read out of Assetto Corsa's own AI spline.

The telemetry says where the car was; it has never said where the road was. AC
ships that second fact for every installed track, in ``ai/fast_lane.ai``: the
racing line the AI drives, and for each of its points the distance to the left
and right edge of the asphalt. The decoding, and the evidence that it is right,
are in `SPIKE-BORDI.md` — including the four bytes (a repeated point count) whose
absence made an earlier attempt read "gas = 36.79".

This module is the product-side half, and it is written around the two ways the
answer can be *no*:

* **the track you have installed may not be the track you drove.** The spline's
  coordinates are the installed model's; a lap recorded on a different version of
  the same circuit sits somewhere else entirely — 187 m away, at Monza, on this
  developer's own machine. So every answer is checked against the lap it will be
  drawn under, and a mismatch returns nothing rather than a plausible ribbon in
  the wrong place;
* **there may be no file at all** — ACC (whose track data is packed), a mod track
  without an AI line, a Steam library somewhere unusual, or a driver who has
  never installed AC.

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

# How far the spline's bounding box may sit from the lap's before we call them
# two different track models. Measured across the archive: Imola, Spa and Suzuka
# line up within 1.5 m, Monza is 187 m out. Anything in between doesn't exist,
# so the exact number matters little — 5 m is comfortably outside the noise of
# "the same track driven at different widths" and nowhere near a real mismatch.
_ALIGN_TOL_M = 5.0

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


def aligned(edges: TrackEdges, points) -> bool:
    """Is this spline describing the same track model the lap was driven on?

    Compares where the two sit, not how big they are: a different version of the
    same circuit has the same shape in a different place, which is exactly the
    failure that looks like a decoding bug and isn't.
    """
    xs = [p.x for p in points]
    zs = [p.z for p in points]
    if len(xs) < 2 or not any(xs) and not any(zs):
        return False
    dx = ((min(edges.x) - min(xs)) + (max(edges.x) - max(xs))) / 2
    dz = ((min(edges.z) - min(zs)) + (max(edges.z) - max(zs))) / 2
    return abs(dx) <= _ALIGN_TOL_M and abs(dz) <= _ALIGN_TOL_M


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
    """The asphalt for ``track``, checked against ``points`` when given.

    Cached per track: the files are 1-3 MB and the report re-asks on every
    corner. A miss is cached too — a track without an AI line will not grow one
    while the app is open.
    """
    key = (track or "").lower()
    if key not in _cache:
        path = spline_path(track)
        _cache[key] = read_edges(path) if path else None
    got = _cache[key]
    if got is None or points is None:
        return got
    return got if aligned(got, points) else None
