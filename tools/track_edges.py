"""Read the track edges out of an Assetto Corsa AI spline, and check them.

Spike tool, deliberately outside the shipped package (like ``gaze_spike.py``):
nothing in HONE imports it, and running it needs an AC installation. What it is
for is answering one question with evidence instead of opinion — *can we draw the
edges of the road under the driven line?* — and leaving behind the numbers that
answer it.

    python tools/track_edges.py monza
    python tools/track_edges.py spa --lap "<path to a .lap.json.gz>"

The format (AC ``ai/fast_lane.ai``, version 7), as decoded here and confirmed
against three tracks:

    0   int   version (7)
    4   int   count           number of points
    8   int   lapTime         0 in every file checked
    12  int   sampleCount     0 in every file checked
    16  count × 20 bytes      (float x, y, z, float length, int id)
    ..  int   count           repeated — this is the detail block's own header
    ..  count × 72 bytes      18 floats per point (see _DETAIL below)
    ..  (undecoded remainder — 0.8 to 2.5 MB, not needed for the edges)

The detail fields this tool actually relies on are ``sideLeft``/``sideRight``
(metres from the racing line to each edge) and the forward vector; the names of
the others are the community's and are printed as-is, unverified.

Two limits found by measuring, both of which any product use has to respect:

* **the spline's frame is the frame of the track you have installed, not of the
  track you drove.** At Monza the two are 187 m apart here: the recorded laps
  came from a different Monza than the one in ``content/tracks/monza``. Imola,
  Spa and Suzuka line up to within 1.5 m. So the alignment is a per-track check
  to run, never an assumption — hence ``--check`` below.
* **the edges are the asphalt, not the limits of the track.** A clean Imola lap
  sits up to 2.4 m past them where it uses the kerbs, while the lap that spun is
  14.6 m past them at the corner the coach flagged. Anything drawn from this must
  say "asphalt", or it will call a legal kerb an excursion.
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

_HEAD = 16
_POINT = 20          # x, y, z, length, id
_DETAIL = 72         # 18 floats
_FIELDS = ("speed", "gas", "brake", "obsolete", "radius", "sideLeft", "sideRight",
           "camber", "direction", "nx", "ny", "nz", "length",
           "fx", "fy", "fz", "tag", "grade")
_SIDE_L, _SIDE_R, _FX, _FZ = 5, 6, 13, 15


def ac_tracks_dir() -> Path | None:
    """Where Assetto Corsa keeps its tracks, on a default Steam install."""
    for root in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        p = Path(root) / "steamapps" / "common" / "assettocorsa" / "content" / "tracks"
        if p.is_dir():
            return p
    return None


def find_spline(track: str) -> Path | None:
    """``<track>/ai/fast_lane.ai``, or the first layout that has one."""
    root = ac_tracks_dir()
    if root is None:
        return None
    direct = root / track / "ai" / "fast_lane.ai"
    if direct.exists():
        return direct
    return next((p for p in sorted((root / track).glob("*/ai/fast_lane.ai"))), None)


def read_spline(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple]]:
    """(points, details) — details aligned index-for-index with points."""
    b = path.read_bytes()
    version, count = struct.unpack_from("<2i", b, 0)
    if version != 7:
        raise SystemExit(f"unexpected spline version {version} (only 7 is decoded)")
    detail_at = _HEAD + count * _POINT
    repeat = struct.unpack_from("<i", b, detail_at)[0]
    if repeat != count:
        raise SystemExit(f"detail block says {repeat} points, header says {count}")
    detail_at += 4
    pts = [struct.unpack_from("<3f", b, _HEAD + i * _POINT) for i in range(count)]
    det = [struct.unpack_from("<18f", b, detail_at + i * _DETAIL) for i in range(count)]
    return pts, det


def edges(pts, det, i: int):
    """The two edge points either side of spline point ``i``, in world x/z.

    Left and right are taken across the *horizontal* forward vector: the third
    dimension is height, and a track's width is measured on the ground.
    """
    x, _, z = pts[i]
    d = det[i]
    fx, fz = d[_FX], d[_FZ]
    n = math.hypot(fx, fz) or 1.0
    px, pz = -fz / n, fx / n
    return ((x + px * d[_SIDE_L], z + pz * d[_SIDE_L]),
            (x - px * d[_SIDE_R], z - pz * d[_SIDE_R]))


def lateral(pts, det, x: float, z: float):
    """(offset, sideLeft, sideRight) of a world point against the nearest spline
    point. Positive offset = towards the left edge."""
    j = min(range(len(pts)), key=lambda k: (pts[k][0] - x) ** 2 + (pts[k][2] - z) ** 2)
    px_, pz_ = pts[j][0], pts[j][2]
    d = det[j]
    n = math.hypot(d[_FX], d[_FZ]) or 1.0
    ux, uz = -d[_FZ] / n, d[_FX] / n
    return (x - px_) * ux + (z - pz_) * uz, d[_SIDE_L], d[_SIDE_R]


def _box(xs, zs):
    return min(xs), max(xs), min(zs), max(zs)


def check_lap(pts, det, lap_path: Path) -> None:
    """Does a recorded lap sit inside these edges? The only test that matters."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from accoach.recording.storage import load_lap        # noqa: PLC0415
    from accoach.trajectory import line_points            # noqa: PLC0415

    lap = load_lap(lap_path)
    line = line_points(lap)
    if not any(p.x or p.z for p in line):
        print("  this lap has no coordinates — nothing to check against")
        return

    # Frames first: same shape in a different place is the failure that looks
    # like a decoding bug and isn't.
    sb = _box([p[0] for p in pts], [p[2] for p in pts])
    lb = _box([p.x for p in line], [p.z for p in line])
    dx = ((sb[0] - lb[0]) + (sb[1] - lb[1])) / 2
    dz = ((sb[2] - lb[2]) + (sb[3] - lb[3])) / 2
    print(f"  frame offset  dx {dx:+7.1f} m  dz {dz:+7.1f} m", end="")
    if abs(dx) > 5 or abs(dz) > 5:
        print("  <-- NOT the same track model: stop here")
        return
    print("  (same track model)")

    over = []
    for s in line:
        lat, sl, sr = lateral(pts, det, s.x, s.z)
        d = (lat - sl) if lat > sl else ((-sr - lat) if lat < -sr else 0.0)
        if d > 0:
            over.append((d, s.pos, s.speed_kmh))
    over.sort(reverse=True)
    print(f"  {len(line) - len(over)}/{len(line)} samples inside the asphalt")
    for d, pos, v in over[:3]:
        print(f"    worst: {d:5.2f} m past the edge at pos {pos:.3f} ({v:.0f} km/h)")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("track", help="track folder name, e.g. monza")
    ap.add_argument("--lap", help="a recorded .lap.json.gz to check the edges against")
    ap.add_argument("--csv", help="write the edge polygon here (x,z per side)")
    a = ap.parse_args(argv)

    path = find_spline(a.track)
    if path is None:
        raise SystemExit(f"no fast_lane.ai for {a.track} (is Assetto Corsa installed?)")
    pts, det = read_spline(path)
    widths = sorted(d[_SIDE_L] + d[_SIDE_R] for d in det)
    print(f"{path}")
    print(f"  {len(pts)} points, {widths[0]:.1f} / {widths[len(widths)//2]:.1f} / "
          f"{widths[-1]:.1f} m wide (min / median / max)")
    print("  point 0: " + "  ".join(f"{n}={v:.3f}" for n, v in zip(_FIELDS, det[0])))

    if a.lap:
        check_lap(pts, det, Path(a.lap))
    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write("i,left_x,left_z,line_x,line_z,right_x,right_z\n")
            for i in range(len(pts)):
                (lx, lz), (rx, rz) = edges(pts, det, i)
                fh.write(f"{i},{lx:.2f},{lz:.2f},{pts[i][0]:.2f},{pts[i][2]:.2f},"
                         f"{rx:.2f},{rz:.2f}\n")
        print(f"  edges written to {a.csv}")


if __name__ == "__main__":
    main()
