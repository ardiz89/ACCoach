"""A corner map learned from your own laps, so a corner keeps its number.

**The defect this fixes.** Corners are detected per lap, from the lap's own
steering and speed (see :mod:`accoach.track`), and the number a corner is given
is its index in *that* detection. Measured on the archive, that number is not
stable: on sixteen Monza laps by the same car the detector returns **five, six,
seven, eight or nine corners** depending on the lap, and on a lap where it found
eight, the corner at position 0.371 answered to "Corner 4" while on the next lap
it was "Corner 5" — and every corner after it shifted with it. Imola on the 720S
alternates between nine and ten; the Nürburgring between seven, eight and nine.

So today a driver comparing two of their own laps can read about "Corner 7" in
both and be reading about two different corners. The curated tables in
:mod:`accoach.trackdata` hide this for the corners they name, which is exactly
half the problem: they cover eleven circuits, and the corners they leave
numbered shift underneath the names that don't.

**The fix is not a better detector.** The detector is right to find what the lap
contains — a lap where you coasted through a kink genuinely has one corner
fewer. What is missing is a per-circuit *reference* to number against, and that
reference does not need a source, a track guide or an author: it is in the laps
already. Drive a circuit a handful of times and the corners that are really
there show up every time.

**Which is what makes it decidable.** Measured on the archive, the two
populations do not overlap: on Monza the corners that exist appear in 13 to 16
laps out of 16, and the spurious ones in 2 or 3. Nürburgring: 7/7 against 2/7.
There is no judgement call in that gap.

This is the same shape as the pit entry the coach learns (see the ``pit_entry``
table in the catalog): a per-track fact no game publishes, measured from what
the driver did, kept as several samples so one odd lap can be outvoted.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

#: Two apexes this close are the same corner seen on two laps. Measured, not
#: chosen: across the archive the same corner wanders by up to 0.032 of a lap
#: between laps — 180 m at Monza, where Curva Grande and the Parabolica are long
#: enough that the speed minimum moves with the line you took. Imola on a GT3 is
#: an order tighter (2-15 m). 0.04 clears the worst case and stays under
#: ``trackdata._NAME_TOL`` (0.05), so a corner can never be clustered with one
#: the naming would consider a different corner.
CLUSTER_TOL = 0.04

#: A corner has to turn up in at least this share of laps. The archive leaves no
#: room to argue about the value: real corners appear in 13-16 laps out of 16 and
#: spurious ones in 2 or 3, so anything between a fifth and four fifths picks the
#: same set. A half is chosen because it is the one that reads as a rule rather
#: than as a tuned constant.
MIN_SHARE = 0.5

#: Below this many laps, nothing is learned. Two laps cannot tell a corner from a
#: coincidence: every apex would be in "half the laps" by having appeared once.
MIN_LAPS = 4


@dataclass(slots=True)
class LearnedCorner:
    """One corner of a circuit, as the driver's own laps agree it exists."""

    pos: float                 # median apex position across the laps that had it
    direction: str             # majority direction, "" when the laps never said
    seen: int                  # laps this corner was found in
    spread: float              # how far it moved between laps, in lap fractions


@dataclass(slots=True)
class CornerMap:
    """A circuit's corners, in lap order, learned from ``laps`` laps."""

    corners: list[LearnedCorner] = field(default_factory=list)
    laps: int = 0

    def __len__(self) -> int:
        return len(self.corners)

    def number_of(self, apex_pos: float, *, tol: float = CLUSTER_TOL) -> int | None:
        """Which corner of the circuit this detected apex is, 1-based.

        ``None`` when it matches nothing the map knows — a kink detected on one
        odd lap has no number, and inventing one for it is how the numbering
        started shifting in the first place.
        """
        if not self.corners:
            return None
        i = min(range(len(self.corners)),
                key=lambda k: abs(self.corners[k].pos - apex_pos))
        return i + 1 if abs(self.corners[i].pos - apex_pos) <= tol else None


def learn(laps: list[list[tuple[float, str]]], *,
          tol: float = CLUSTER_TOL, min_share: float = MIN_SHARE,
          min_laps: int = MIN_LAPS) -> CornerMap:
    """Build a circuit's corner map from several laps' detected corners.

    Each lap is a list of ``(apex position, direction)`` — direction may be ``""``
    on laps recorded before coordinates, which cannot classify a corner.

    Pure: no I/O, no catalog, no detector. The caller runs the detector.
    """
    if len(laps) < min_laps:
        return CornerMap([], len(laps))

    # Grow clusters from every apex seen, nearest-first, so a corner detected a
    # little off on one lap joins the corner it is, not the one next to it.
    flat = sorted((p, d, i) for i, lap in enumerate(laps) for p, d in lap)
    clusters: list[list[tuple[float, str, int]]] = []
    for point in flat:
        if clusters and point[0] - clusters[-1][0][0] <= tol:
            clusters[-1].append(point)
        else:
            clusters.append([point])

    # A corner seen twice on the same lap counts once: the detector splitting a
    # complex must not let it outvote a corner every lap agrees on.
    need = max(2, round(min_share * len(laps)))
    out: list[LearnedCorner] = []
    for cluster in clusters:
        laps_seen = {i for _p, _d, i in cluster}
        if len(laps_seen) < need:
            continue
        positions = [p for p, _d, _i in cluster]
        dirs = [d for _p, d, _i in cluster if d]
        out.append(LearnedCorner(
            pos=round(statistics.median(positions), 4),
            direction=(statistics.mode(dirs) if dirs else ""),
            seen=len(laps_seen),
            spread=round(max(positions) - min(positions), 4),
        ))
    return CornerMap(out, len(laps))


def serialize(cmap: CornerMap) -> str:
    """``pos:dir:seen`` per corner, semicolon separated — the catalog stores text.

    Deliberately not JSON: the catalog's other learned tables (``focus_state``,
    ``pit_entry``) keep comma-separated scalars, and a row a person can read in a
    SQLite browser is worth more here than a schema.
    """
    return ";".join(f"{c.pos:.4f}:{c.direction}:{c.seen}" for c in cmap.corners)


def deserialize(raw: str, laps: int = 0) -> CornerMap:
    out: list[LearnedCorner] = []
    for part in (raw or "").split(";"):
        bits = part.split(":")
        if len(bits) != 3:
            continue
        try:
            out.append(LearnedCorner(float(bits[0]), bits[1], int(bits[2]), 0.0))
        except ValueError:
            continue
    return CornerMap(out, laps)


def learn_from(lap_objs) -> CornerMap:
    """Learn a map from already-loaded laps, running the detector on each.

    Takes lap objects rather than paths because every page that would want a map
    has already paid to load them (see ``api._history``): building it is then a
    walk over samples already in memory, and no screen pays for the feature it
    doesn't use.
    """
    from .track import detect_corners

    laps: list[list[tuple[float, str]]] = []
    for lap in lap_objs:
        try:
            corners = detect_corners(lap.samples)
        except Exception:      # noqa: BLE001 — a degenerate lap teaches nothing
            continue
        if corners:
            laps.append([(c.apex_pos, c.direction) for c in corners])
    return learn(laps)


def refresh(cat, car: str, track: str, lap_objs) -> CornerMap:
    """Load this combo's map, rebuilding it when the archive has moved on.

    Rebuilt on a **different** lap count rather than a larger one: laps get
    deleted as well as added, and a map left over from an archive that no longer
    exists is the kind of stale that nobody goes looking for.
    """
    stored = cat.load_corner_map(car, track)
    fresh = learn_from(lap_objs)
    if fresh.laps and fresh.laps != stored.laps:
        cat.save_corner_map(car, track, fresh)
        return fresh
    return stored if stored.corners else fresh
