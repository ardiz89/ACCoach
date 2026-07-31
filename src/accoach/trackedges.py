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

**Nor is it tied to the name.** The sims don't agree on those either: Mount
Panorama is ``mount_panorama`` in ACC and ``rt_bathurst`` in the mod that puts it
in AC. Since the fit can recognise a circuit from its shape, the name is not
needed — the lap's own length narrows 65 installed tracks to a handful, and the
fit picks among them. Measured over the whole archive: 24 laps placed on the
right circuit, none on a wrong one, and the 15 refusals are exactly the laps
whose coordinates are broken or absent.

What is left to say no to:

* **it may not be the same circuit.** Believed only when the residual is small
  AND the scale is ~1 AND it beat every other candidate: all three, because each
  alone can be fooled. Spa 1998 fits modern Spa at scale 1.000 and is a different
  track; a lap whose coordinates are broken fits *everything* by shrinking the
  circuit seventy times over; and a circuit's own historic version cannot be
  ruled out by any absolute number at all — only by the real one scoring better;
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
import sys
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
# Misurato il 2026-07-31 su ogni giro valido in archivio contro ogni spline
# installata compatibile per lunghezza: **24 accoppiamenti veri e 95 falsi**.
#
# La conclusione non è quella che speravo. **Nessuna statistica assoluta separa
# un circuito dalla propria versione storica:**
#
#   peggiore dei veri      26.7 m   (monza, McLaren 720S 1:53.7)
#   migliore dei falsi     22.3 m   (suzuka contro suzuka_1998)
#
# Provati e scartati anche il massimo (veri fino a 49 m, falsi da 30 in su), il
# rapporto max/p95 (veri 1.01-2.29, falsi 1.03-1.48) e perfino il controllo
# fisico — quanta parte del giro finirebbe fuori dall'asfalto — che pure sembrava
# il più promettente (veri fino al 18%, falsi dal 13%). Si sovrappongono tutti.
#
# Ciò che separa, e separa in tutti e 24 i casi, è il **confronto fra i
# candidati**: la pista giusta batte sempre e nettamente la propria variante
# storica — Suzuka 3 m contro 22, Imola 17 contro 32, Spa 4 contro 51. Per questo
# `_by_shape` assegna un punteggio a tutti e tiene il migliore, invece di
# fermarsi al primo che passa. È l'unica parte del meccanismo che non si può
# togliere.
#
# Il 95° percentile e non la media: il cambio di tracciato è *locale* — Spa 1998
# è Spa moderna dappertutto tranne una curva — e una media diluisce proprio la
# prova che conta.
#
# Questa soglia resta quindi solo come **tetto**: dice «nessuna di queste è la
# tua pista», non sceglie fra due. 35 m lascia aria sopra il peggiore dei veri e
# resta lontanissima dalle piste sbagliate (162 m in su). Rischio residuo, e va
# detto invece che nascosto: chi guidasse la Suzuka moderna avendo installata
# **solo** quella del 1998 si vedrebbe disegnata quella del 1998.
_FIT_P95_M = 35.0
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


def all_splines() -> list[tuple[str, Path]]:
    """Every installed track that has an AI line, by folder name."""
    root = tracks_dir()
    if root is None:
        return []
    out = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        got = spline_path(p.name)
        if got is not None:
            out.append((p.name, got))
    return out


# --- circuits that ship with HONE -------------------------------------------
# The game's own files only cover the tracks you have installed, in the sim you
# have installed. These 26 cover everyone — see tracks/NOTICE.md for where they
# come from and under what licence. They are also *better* where they overlap:
# their widths are measured off satellite imagery, so they describe the track,
# while the game's describe every square metre of tarmac (Spa's La Source reads
# 24.5 m in AC's own data, because the paved run-off is paved).

def bundled_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) / "accoach" / "tracks") if base else (Path(__file__).resolve().parent / "tracks")


def bundled_tracks() -> list[tuple[str, Path]]:
    """The circuits shipped with HONE, by name."""
    d = bundled_dir()
    if not d.is_dir():
        return []
    return [(p.stem, p) for p in sorted(d.glob("*.csv"))]


def read_csv_edges(path: Path, track: str | None = None) -> TrackEdges | None:
    """Parse one bundled circuit: ``x_m, y_m, w_tr_right_m, w_tr_left_m``.

    Same shape as everything else in this module, so a bundled circuit and one
    read out of the game go through exactly the same fitting, cropping and
    drawing. Nothing downstream knows which is which — which is the point.
    """
    xs: list[float] = []
    zs: list[float] = []
    left: list[float] = []
    right: list[float] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bits = line.split(",")
        if len(bits) < 4:
            continue
        try:
            x, z, wr, wl = (float(b) for b in bits[:4])
        except ValueError:
            continue
        # Same guard as the game's files: a side of hundreds of metres is not an
        # edge. These files have never needed it, which is itself worth knowing.
        if not (0.0 < wl < _MAX_SIDE_M and 0.0 < wr < _MAX_SIDE_M):
            continue
        xs.append(x); zs.append(z); left.append(wl); right.append(wr)
    if len(xs) < 16:
        return None
    return TrackEdges(track=track or path.stem, x=xs, z=zs, left=left, right=right)


def spline_length(path: Path) -> float:
    """How long the AI line is, in metres — reading only the point block.

    The rest of the file is 1-3 MB of detail records, and this number is used to
    throw away most of the library before anything expensive happens.
    """
    try:
        with path.open("rb") as f:
            head = f.read(_HEAD)
            if len(head) < _HEAD:
                return 0.0
            version, count = struct.unpack_from("<2i", head, 0)
            if version != _VERSION or count <= 1:
                return 0.0
            blob = f.read(count * _POINT)
    except OSError:
        return 0.0
    if len(blob) < count * _POINT:
        return 0.0
    pts = [struct.unpack_from("<3f", blob, i * _POINT) for i in range(count)]
    total = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][2] - pts[i - 1][2])
                for i in range(1, count))
    # Closing chord: the last point sits next to the first, not on it.
    return total + math.hypot(pts[0][0] - pts[-1][0], pts[0][2] - pts[-1][2])


def _length_of(path: Path) -> float:
    """How long a circuit is, for the cheap first pass — either kind of file."""
    if path.suffix.lower() != ".csv":
        return spline_length(path)
    key = "len:" + str(path)
    if key not in _len_cache:
        e = read_csv_edges(path)
        if e is None:
            _len_cache[key] = 0.0
        else:
            total = sum(math.hypot(e.x[i] - e.x[i - 1], e.z[i] - e.z[i - 1])
                        for i in range(1, len(e)))
            _len_cache[key] = total + math.hypot(e.x[0] - e.x[-1], e.z[0] - e.z[-1])
    return _len_cache[key]


_len_cache: dict[str, float] = {}


# How far a candidate's length may sit from the driven lap's before it isn't
# worth fitting. Measured across the 65 installed tracks: at +-2% the shortlist
# for any given circuit is 1 to 5 tracks, not 65 — and the ones that survive are
# different enough in shape that the fit separates them by hundreds of metres.
# Kept at 3% because the driven line is not the AI line: it cuts and it runs wide,
# and Bathurst's own spline already measures 0.9% under the published length.
_LENGTH_TOL = 0.03


# --- reading it -------------------------------------------------------------

def read_edges(path: Path, track: str | None = None) -> TrackEdges | None:
    """Parse one ``fast_lane.ai``. None when it isn't the format we decoded.

    ``track`` names the circuit. Without it the name is taken from the folder
    two levels up, which is the *layout* on tracks that have several — the
    Nürburgring would come back calling itself "layout_gp_a".
    """
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
    return TrackEdges(track=track or path.parent.parent.name, x=xs, z=zs,
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


# Keyed by the file, not by the name: the same spline is reachable under more
# than one name (the sim's, the folder's), and `_by_shape` already holds the path
# it wants — asking for it back by name is how a lookup ends up resolving to
# somewhere else entirely.
_cache: dict[str, TrackEdges | None] = {}


def _at_path(path: Path, track: str) -> TrackEdges | None:
    """One circuit, from whichever kind of file it lives in."""
    key = str(path)
    if key not in _cache:
        reader = read_csv_edges if path.suffix.lower() == ".csv" else read_edges
        _cache[key] = reader(path, track)
    return _cache[key]


def _by_name(track: str) -> TrackEdges | None:
    path = spline_path(track)
    return _at_path(path, track) if path else None


def _lap_length(points) -> float:
    return sum(math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z)
               for i in range(1, len(points)))


def _by_shape(points) -> TrackEdges | None:
    """Find the circuit by what it *looks like*, not by what it's called.

    The names belong to the sims, and the sims disagree: Mount Panorama is
    ``mount_panorama`` in ACC and ``rt_bathurst`` in the mod that puts it in AC.
    Matching on the string is why the drawing appeared in one game and not the
    other — the very thing this module has stopped doing.

    It doesn't need the name. The fit already knows whether two shapes are the
    same place, so the shape *is* the lookup. Length narrows the 65 installed
    tracks to a handful first (measured: 1 to 5), because fitting all of them
    would cost seconds instead of tenths.

    **Every candidate is scored and the best one wins**, rather than the first
    that passes. That is not tidiness, it is the only thing that separates a
    circuit from its own historic version — see ``_FIT_P95_M``.
    """
    want = _lap_length(points)
    if want <= 0:
        return None
    best: TrackEdges | None = None
    best_p95 = float("inf")
    # Both sources, scored against each other. Not "bundled first, game as a
    # fallback": on a track that is in both, whichever describes *your* lap
    # better should win, and only the fit knows which that is.
    for name, path in bundled_tracks() + all_splines():
        length = _length_of(path)
        if not length or abs(length - want) / want > _LENGTH_TOL:
            continue
        got = _at_path(path, name)
        if got is None:
            continue
        at = fit(got, points)
        if at is not None and at.p95_m < best_p95:
            best, best_p95 = placed(got, at), at.p95_m
    return best


def edges_for(track: str, points=None) -> TrackEdges | None:
    """The asphalt for ``track``, laid under ``points`` when they are given.

    Cached per track: the files are 1-3 MB and the report re-asks on every
    corner. A miss is cached too — a track without an AI line will not grow one
    while the app is open.

    With ``points`` the answer comes back **in the lap's own coordinates**,
    whichever sim wrote them — and the name is not consulted at all, because the
    shape is a better answer than the string (and the string is the sim's, not
    the circuit's). Without ``points`` there is nothing to fit against, so the
    name is all there is.
    """
    if points is None:
        return _by_name(track)
    return _by_shape(points)
