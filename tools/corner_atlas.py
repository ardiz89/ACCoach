"""Corner positions and directions for a circuit, read off its centreline.

**Why this exists.** ``trackdata._CORNERS`` maps a name to the normalized track
position of its apex, and until now every one of those numbers was anchored to a
*recorded reference lap*. That is why four circuits had names and twenty-two did
not: what was missing was never the names, it was a lap on each track.

It turns out a lap isn't needed. The bundled centrelines
(``accoach/tracks/*.csv``, TUMFTM — GPS traces from OpenStreetMap) **start at the
start/finish line**, so a point's fraction of the total arc length *is* a
normalized track position. Measured on the three circuits that had both a curated
table and a bundled centreline, comparing the curvature peaks here against the
lap-anchored positions already in ``_CORNERS``:

    Monza    best circular shift +0.000   mean error 0.0021  (12 m)
    Spa                          -0.006               0.0047  (33 m)
    Suzuka                       +0.001               0.0025  (14 m)

Twelve to thirty-three metres on circuits five to seven kilometres long, against
a naming tolerance (``_NAME_TOL`` = 0.05) worth about 290 m at Monza. The
positions this prints are a sixth of the tolerance away from ones that took a
reference lap to produce.

**What it does not do: name anything.** It prints where the corners are, which
way they turn and how tight they are. Attaching a name is a human reading a
source, and the point of the printout is to make that reading checkable — the
order and the direction of a real circuit's corners are facts you can hold
against it, and a name that lands on a corner turning the wrong way is caught
before it ships (see ``trackdata._DIRECTIONS``, which exists because two names
reached the corner next door on 2026-07-30).

**The trap this tool cannot see, and the reason some circuits are not curated.**
A centreline describes *a* layout, and circuits have several. Barcelona caught
it: the bundled trace has no chicane in the last third (five right-handers and
no left), so it is the 2021-on 14-turn layout — while the ACC track guides for
the same circuit describe 16 turns with a left-right chicane at T14-T15. Curating
positions off the wrong one would put the last third of the lap in the wrong
place, confidently. So a circuit whose source and centreline disagree about how
many corners it has does not get a table, and ``spa1998`` is kept out of the
alias map for the same reason.

The corner *count* is the cheapest way to notice. ``--count`` sweeps the radius
threshold and reports how many apexes survive: where a plateau lands exactly on
a circuit's published turn count, the trace is describing that layout. COTA
settles on **20** for every threshold from 300 m up, which is its published
number.

Not part of the app: a developer tool for building the table, kept out of the
bundle like the other tools here.

    python tools/corner_atlas.py Silverstone
    python tools/corner_atlas.py --all
    python tools/corner_atlas.py --check      # re-measure against the tables we have
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

TRACKS = _ROOT / "src" / "accoach" / "tracks"

#: A corner is a stretch tighter than this. 220 m is the radius above which a
#: bend stops being something a driver takes as a corner and becomes a curved
#: straight — Monza's Curva Grande is ~180 m and is named, the Kemmel kink is
#: ~600 m and is not. It over-collects on purpose: an unnamed apex costs nothing
#: (it falls back to a number at runtime), a missing one has to be noticed.
MAX_RADIUS_M = 220.0

#: Two apexes closer together than this along the lap are one corner seen twice.
#: 2% of a 5.8 km lap is 116 m, which is shorter than the gap between Monza's
#: two Lesmos (0.053 apart) and longer than the wobble inside one corner.
MIN_SEP = 0.02

#: Curvature is measured over a stencil this long, in metres. Short enough to
#: resolve a chicane, long enough that the GPS jitter in the source traces does
#: not read as a corner.
STENCIL_M = 12.0


def centreline(path: Path) -> tuple[list[float], list[float]]:
    xs, zs = [], []
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split(",")
        xs.append(float(parts[0]))
        zs.append(float(parts[1]))
    return xs, zs


def _menger(p0, p1, p2) -> float:
    """Signed curvature, same formula and same sign meaning as ``track.py``."""
    (x0, z0), (x1, z1), (x2, z2) = p0, p1, p2
    cross = (x1 - x0) * (z2 - z0) - (z1 - z0) * (x2 - x0)
    denom = (math.hypot(x1 - x0, z1 - z0) * math.hypot(x2 - x1, z2 - z1)
             * math.hypot(x2 - x0, z2 - z0))
    return 2.0 * cross / denom if denom > 0.0 else 0.0


def analyse(xs: list[float], zs: list[float], *, flip: bool = False):
    """(apexes, total_m) — apexes as (fraction, radius_m, direction), in lap order."""
    n = len(xs)
    dist = [0.0]
    for i in range(1, n):
        dist.append(dist[-1] + math.hypot(xs[i] - xs[i - 1], zs[i] - zs[i - 1]))
    total = dist[-1]
    frac = [d / total for d in dist]

    step = max(2, round(STENCIL_M / (total / n)))
    kappa = [0.0] * n
    for i in range(n):
        kappa[i] = _menger((xs[(i - step) % n], zs[(i - step) % n]),
                           (xs[i], zs[i]),
                           (xs[(i + step) % n], zs[(i + step) % n]))

    # Smoothed magnitude for picking peaks; the sign is read at the peak itself,
    # where it is least ambiguous.
    win = max(1, step // 2)
    mag = [sum(abs(kappa[(i + j) % n]) for j in range(-win, win + 1)) / (2 * win + 1)
           for i in range(n)]

    floor = 1.0 / MAX_RADIUS_M
    picked: list[tuple[float, float, str]] = []
    taken: list[float] = []
    for i in sorted(range(n), key=lambda j: -mag[j]):
        if mag[i] < floor:
            break
        if any(min(abs(frac[i] - t), 1.0 - abs(frac[i] - t)) < MIN_SEP for t in taken):
            continue
        taken.append(frac[i])
        k = kappa[i]
        direction = ("right" if k > 0 else "left")
        if flip:
            direction = "left" if direction == "right" else "right"
        picked.append((frac[i], 1.0 / mag[i], direction))
    picked.sort()
    return picked, total


def _handedness() -> bool:
    """Do the bundled traces turn the way the sim says, or mirrored?

    Not assumed: the centrelines are OpenStreetMap eastings and northings, the
    sim's coordinates are left-handed, and a mirrored frame turns every left into
    a right. Decided by measurement, against the only directions in the codebase
    that were read off real laps (``_DIRECTIONS``, Spa and Suzuka).
    """
    from accoach.trackdata import _CORNERS, _DIRECTIONS

    agree = disagree = 0
    for track, csv in (("spa", "Spa.csv"), ("suzuka", "Suzuka.csv")):
        want = _DIRECTIONS.get(track, {})
        if not want:
            continue
        found, _ = analyse(*centreline(TRACKS / csv))
        for name, pos in _CORNERS[track]:
            if name not in want:
                continue
            near = min(found, key=lambda a: min(abs(a[0] - pos), 1.0 - abs(a[0] - pos)))
            if min(abs(near[0] - pos), 1.0 - abs(near[0] - pos)) > MIN_SEP:
                continue
            if near[2] == want[name]:
                agree += 1
            else:
                disagree += 1
    if agree + disagree == 0:
        raise SystemExit("no measured direction to calibrate against")
    print(f"# handedness check: {agree} agree, {disagree} disagree "
          f"-> {'MIRRORED, flipping' if disagree > agree else 'same as the sim'}")
    return disagree > agree


def report(csv_name: str, flip: bool) -> None:
    path = TRACKS / csv_name
    found, total = analyse(*centreline(path), flip=flip)
    print(f"\n## {path.stem}  —  {total:.0f} m, {len(found)} corners")
    print(f"{'#':>3}  {'pos':>6}  {'metres':>7}  {'radius':>7}  direction")
    for i, (f, r, d) in enumerate(found, 1):
        print(f"{i:>3}  {f:6.3f}  {f * total:7.0f}  {r:6.0f} m  {d}")


#: Circuits that needed the detector read at something other than the default,
#: and why. Recorded rather than hard-coded into the table, so ``--check`` can
#: re-derive each table with the settings it was actually built at.
#:
#: COTA: at the default 110 m minimum separation its esses merge into each other
#: and the read comes out with T3 and T4 the wrong way round — the only two
#: directions of fourteen that fought the source. At 77 m they resolve and all
#: fourteen agree, with T6 showing up as the two apexes of one long corner,
#: which is exactly what the source calls "a long, sweeping right-hander". The
#: conflict was this tool's resolution, not a disagreement about the circuit.
PARAMS: dict[str, tuple[float, float]] = {          # key -> (max radius, min sep)
    "austin": (240.0, 0.014),
}

#: Circuits looked at properly and **not** curated, with what stopped each one.
#:
#: This exists because the work of getting to "no" costs the same as the work of
#: getting to "yes", and without a record it gets paid again every time. Both
#: entries below took an hour to reach and neither leaves a trace in the table.
#:
#: **Seven of these were held for a reason that turned out to be wrong**, and
#: Sepang is the one that proved it: it settled on 18 apexes against a published
#: 15, and the rule said "different counts, no table". But official numbering
#: merges complexes — Sepang's own guide calls Turns 7 and 8 "a long double-apex
#: right hander" — so eighteen rilievi for fifteen turns is one road counted two
#: ways. The count is a hint. The **sequence of directions** is the proof, and
#: for Sepang it came out 15 out of 15. The entries below that still say only
#: "settles on N, the circuit has M" are therefore worth re-attacking with a
#: sourced direction list before believing them.
#:
#: It is also a list that **rots**, which is the other reason it is checked
#: rather than just written down. Catalunya sat here from 2026-08-03 with a
#: sound-looking reason — the trace has 14 turns and the ACC guides describe 16
#: — and the reason turned out to be about the numbering, not the names, so it
#: is curated now. ``--check`` fails loudly if a circuit is in both places.
HELD: dict[str, str] = {
    "montreal":
        "14 turns published, 16 features in the trace, and the two guides that "
        "describe it contradict each other exactly at T5-T7 (one has L,R,L "
        "where the other has R,L,R). The ends are certain — T1 left, T2 Senna "
        "right, T10 the hairpin, T11 the left kink, T12 the right kink before "
        "the Casino straight, T13/T14 the final right-left — but a numbered "
        "circuit is all-or-nothing, and the middle will not resolve.",
    "sakhir":
        "The closest miss here. 15 apexes for 15 published turns and 14 of the "
        "15 directions agree with a guide that states all of them; the one "
        "mismatch is explained (T5 is a gentle kink the detector reads only "
        "above 220 m, and T11 is read as two apexes). What stops it is the end "
        "of the lap: two independent sources call T15 'effectively the exit of "
        "Turn 14', and the geometry puts 790 m of straight between the last "
        "two rights. One of them is not where the numbering says it is.",
    "budapest":
        "The trace is the right layout — 4372 m against a published 4381 — so "
        "the 17 apexes against 14 turns is just the merging, as at Sepang. What "
        "stops it is that the two guides **contradict each other**: one reads "
        "Turns 2-5 as left-right-left-right and 10-13 as right-...; the other "
        "has T3 a 180-degree left, T4 a right and 10-13 as left-right-left-"
        "right. And the geometry cannot arbitrate — both score **14/14**, "
        "because with five directions unstated the solver has room to satisfy "
        "either. Under-determined is not close: it is a coin toss in a "
        "measurement's clothing.",
    "sochi":
        "Right layout too (5836 m against 5848). A source gives the global "
        "constraint — 12 rights and 6 lefts — and names five lefts, so the "
        "sixth was the only unknown; the geometry ties three candidates and the "
        "source rules one out. Then the tie-break killed it: a second source "
        "makes **both** survivors left-handers, which would be seven lefts, and "
        "the two sources put the famous 180-degree left at different numbers "
        "(T3 against T4). One of them also describes a 'Turn 19' on an "
        "eighteen-turn circuit.",
    "yasmarina":
        "Settled by the tape measure, not by the corner count: the trace is "
        "**5542 m** and *both* published layouts are 5281 — the 2021 rebuild "
        "kept the length. 261 m is 5%, where Sepang's trace came within 0.14% "
        "and Monza, Spa and Suzuka within 1%. So this is neither layout, and "
        "no direction list can rescue a road that isn't the road.",
    "moscowraceway":
        "The published count exists now, and it made things worse rather than "
        "better. The tape measure picks the layout cleanly: the trace is "
        "4058 m, the 'Full Circuit' is 4.070 km (0.29%), and the next candidate "
        "of the circuit's **eighteen** variations is four times further away "
        "(4.009 km, 1.2%) — outside the band every curated trace has landed in. "
        "That layout is published at **21 corners**; the detector gives 19 from "
        "200 m all the way to 600 m (18 at 150 m) and 20 at 800 m, so two turns "
        "are merged somewhere, which after Sepang is not by itself a reason to "
        "stop. And the count itself deserves less trust than it looks: the row "
        "carrying it has no citation, its 4.070 km is stated elsewhere on the "
        "same page as the **designed** length rather than a raced one, and the "
        "same table contradicts its own infobox on another variant (Sprint #4 "
        "at 2.661 km against 2.545 km). What "
        "stops it is that no source describes *this* road turn by turn: the "
        "guides that walk the lap are all written for the raced Grand Prix #1 "
        "layout — 3.955 km, 15 turns, 103 m and four variations away — and one "
        "of them states a single direction ('the quick Turn 1 left-hander') "
        "for a corner the two layouts need not even share. A direction list "
        "for the wrong configuration is the Barcelona trap with extra steps.",
    "ims": "Published count not reachable at any threshold.",
    "norisring": "Published count not reachable at any threshold.",
    "oschersleben": "Published count not reachable at any threshold.",
}


#: circuit key in ``_CORNERS`` -> the centreline that describes it.
CSV_FOR = {
    "austin": "Austin.csv", "brandshatch": "BrandsHatch.csv",
    "budapest": "Budapest.csv", "catalunya": "Catalunya.csv",
    "hockenheim": "Hockenheim.csv", "ims": "IMS.csv",
    "melbourne": "Melbourne.csv", "mexicocity": "MexicoCity.csv",
    "montreal": "Montreal.csv", "monza": "Monza.csv",
    "moscowraceway": "MoscowRaceway.csv", "mountpanorama": "MountPanorama.csv",
    "norisring": "Norisring.csv", "nurburgring": "Nuerburgring.csv",
    "oschersleben": "Oschersleben.csv", "sakhir": "Sakhir.csv",
    "saopaulo": "SaoPaulo.csv", "sepang": "Sepang.csv",
    "shanghai": "Shanghai.csv", "silverstone": "Silverstone.csv",
    "sochi": "Sochi.csv", "spa": "Spa.csv", "redbullring": "Spielberg.csv",
    "suzuka": "Suzuka.csv", "yasmarina": "YasMarina.csv",
    "zandvoort": "Zandvoort.csv",
}


def check() -> None:
    """Every curated table, re-measured against the geometry it should describe.

    Two ways a row can be wrong, and both are caught here rather than on a
    driver's screen: the position can land on no corner at all, and the name can
    land on a corner turning the other way. The second is the one that actually
    happened (2026-07-30, twice), and it is the one a human proof-reading a list
    of names will never catch.

    **One standing complaint, and it is the checker's limit, not the table's.**
    Spa's Raidillon reads as a left here. Eau Rouge is a left-right-left inside
    about 200 m, which is shorter than ``MIN_SEP``, so the right in the middle
    is swallowed by the two lefts either side and the peak that survives is one
    of them. The table's "right" was measured on a real lap and stands. Read it
    as: this tool resolves corners, not the elements inside a complex.
    """
    from accoach.trackdata import _CORNERS, _DIRECTIONS, render

    flip = _handedness()
    bad = 0
    for track in sorted(_CORNERS):
        table = _CORNERS[track]
        csv = CSV_FOR.get(track)
        if not table:
            continue
        if csv is None:
            print(f"\n## {track}: {len(table)} curated, NO CENTRELINE — unverified")
            continue
        global MAX_RADIUS_M, MIN_SEP
        keep = (MAX_RADIUS_M, MIN_SEP)
        MAX_RADIUS_M, MIN_SEP = PARAMS.get(track, keep)
        found, total = analyse(*centreline(TRACKS / csv), flip=flip)
        MAX_RADIUS_M, MIN_SEP = keep
        want = _DIRECTIONS.get(track, {})
        # A table anchored to real laps and a trace read off OpenStreetMap do not
        # share an origin, and the difference is a CONSTANT: the trace's zero is
        # not exactly the sim's start/finish line. Measured at 12-33 m on Monza,
        # Spa and Suzuka — but **116 m** at the Red Bull Ring, where every one of
        # the eight corners the laps see is off by 0.019 to 0.043.
        #
        # A constant shift is a change of frame, not an error, so it comes off
        # before distances are judged. Otherwise this checker calls a perfectly
        # placed lap-anchored table wrong and — worse — compares each name
        # against the direction of the corner NEXT DOOR. What it cannot hide is
        # a *varying* offset, which is what a genuinely misplaced row looks like.
        shift = _frame_shift(table, found)
        note = f", frame {shift * total:+.0f} m" if abs(shift) * total >= 20 else ""
        print(f"\n## {track}: {len(table)} curated, {len(found)} geometric, "
              f"{total:.0f} m{note}")
        worst = 0.0
        for label, pos0 in table:
            pos = pos0 + shift
            near = min(found, key=lambda a: min(abs(a[0] - pos), 1.0 - abs(a[0] - pos)))
            d = min(abs(near[0] - pos), 1.0 - abs(near[0] - pos))
            worst = max(worst, d)
            flags = []
            if d > MIN_SEP:
                flags.append(f"FAR ({d * total:.0f} m)")
            if label in want and want[label] != near[2]:
                flags.append(f"DIRECTION: table says {want[label]}, geometry {near[2]}")
            bad += bool(flags)
            print(f"   {render(label, 'en'):26s} {pos0:.3f} -> {near[0]:.3f}  "
                  f"{near[2]:5s} r={near[1]:4.0f} m  {'  '.join(flags)}")
        print(f"   worst {worst * total:.0f} m (tolerance {_NAME_TOL_M(total):.0f} m)")

    stale = sorted(set(HELD) & set(_CORNERS))
    if stale:
        print(f"\nHELD but curated — the note is out of date: {', '.join(stale)}")
    print(f"\n{'OK' if not bad and not stale else str(bad) + ' ROWS TO LOOK AT'}")


def _frame_shift(table, found) -> float:
    """The constant offset between a curated table and the trace.

    The median of each row's signed distance to its nearest apex. Median and not
    mean for the usual reason: one row that genuinely sits on the wrong corner
    must not be allowed to drag the frame across to meet it.
    """
    offs = []
    for _label, pos in table:
        near = min(found, key=lambda a: min(abs(a[0] - pos), 1.0 - abs(a[0] - pos)))
        d = near[0] - pos
        if d > 0.5:
            d -= 1.0
        elif d < -0.5:
            d += 1.0
        offs.append(d)
    if not offs:
        return 0.0
    offs.sort()
    return offs[len(offs) // 2]


def _NAME_TOL_M(total: float) -> float:
    from accoach.trackdata import _NAME_TOL
    return _NAME_TOL * total


def fit(csv_name: str, wanted: list[tuple[str, str]], flip: bool) -> None:
    """Lay an ordered list of (name, direction) onto the geometry.

    The source supplies what it is good for — the corners of a circuit, in order,
    and which way each turns — and the geometry supplies what no source states:
    where each one is, as a fraction of the lap. The join between them is the
    part a human does badly, because the detector over-collects (every kink is
    an apex) and choosing which apexes the names belong to is a combinatorial
    problem that *looks* like a reading exercise.

    So it is solved rather than eyeballed: over every order-preserving
    assignment, keep the one that agrees with the source's directions most
    often. Order-preserving is not a convenience, it is the constraint that
    makes the answer meaningful — corners cannot overtake each other.

    Prints the alignment and, more importantly, the disagreements. A name whose
    direction fights the geometry does not go in a table.
    """
    found, total = analyse(*centreline(TRACKS / csv_name), flip=flip)
    n, m = len(wanted), len(found)
    if n > m:
        print(f"{csv_name}: {n} names for {m} apexes — the geometry is too coarse")
        return

    # Direction agreement decides; **prominence** breaks the ties, and without it
    # the answer is wrong in a way that still scores perfectly. Measured on
    # Interlagos, whose back half is a run of left-handers: with agreement as the
    # only score the solver was free to slide Curva do Sol 700 m down the track
    # onto a different left and still read 14/14. A circuit names its *notable*
    # corners, so among alignments that agree equally, the one sitting on the
    # tighter apexes is the one meant. Weighted far below a direction so it can
    # never outvote one.
    NEG = float("-inf")
    best = [[NEG] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        best[0][j] = 0
    for i in range(1, n + 1):
        for j in range(i, m + 1):
            skip = best[i][j - 1]
            take = best[i - 1][j - 1]
            if take != NEG:
                agree = (not wanted[i - 1][1]
                         or wanted[i - 1][1] == found[j - 1][2])
                take += (1.0 if agree else 0.0) + 0.1 * min(1.0, 40.0 / found[j - 1][1])
            if take >= skip:
                best[i][j], back[i][j] = take, 1
            else:
                best[i][j], back[i][j] = skip, 0

    pairs, i, j = [], n, m
    while i > 0:
        if back[i][j] == 1:
            pairs.append((wanted[i - 1], found[j - 1]))
            i -= 1
        j -= 1
    pairs.reverse()

    print(f"\n## {Path(csv_name).stem} — {n} names onto {m} apexes, "
          f"{best[n][m]}/{n} directions agree")
    for (name, want), (pos, radius, direction) in pairs:
        flag = "" if (not want or want == direction) else f"  <-- source says {want}"
        print(f'   ("{name}", {pos:.3f}),'.ljust(42) +
              f"# {direction}, r={radius:.0f} m, {pos * total:.0f} m{flag}")


def rotation(csv_name: str) -> float:
    """Net turning of one lap, in degrees: **positive anticlockwise**.

    Read in the trace's own frame, which is eastings and northings — a plan view
    of the real world — so this is the direction the circuit really runs. The
    mirror the rest of this file applies is between that frame and the *sim's*
    left-handed coordinates, and does not belong here. (Applying it anyway was
    the first thing tried, and it turned every circuit the wrong way round.)
    """
    xs, zs = centreline(TRACKS / csv_name)
    n = len(xs)
    total = 0.0
    for i in range(n):
        a, b, c = (i - 1) % n, i, (i + 1) % n
        v1 = (xs[b] - xs[a], zs[b] - zs[a])
        v2 = (xs[c] - xs[b], zs[c] - zs[b])
        total += math.atan2(v1[0] * v2[1] - v1[1] * v2[0],
                            v1[0] * v2[0] + v1[1] * v2[1])
    return math.degrees(total)


def sanity() -> None:
    """The cheapest check that the traces and the mirror are both right.

    Which way a circuit runs is a fact anybody can look up, and it is decided by
    a number this tool computes from the raw trace without knowing the circuit's
    name. Every one of the twenty-six agrees: Austin, Interlagos, Bathurst, Yas
    Marina, Indianapolis's road course and the Norisring come out anticlockwise
    and the rest clockwise, which is how they run.

    Suzuka is the one that makes the check worth keeping. It is a **figure of
    eight** — the only one here — so its lap crosses itself and its net turning
    cancels to zero instead of coming out at ±360. Nothing in this file knows
    that; it falls out of the geometry.
    """
    for name in sorted(p.name for p in TRACKS.glob("*.csv")):
        deg = rotation(name)
        if abs(deg) < 90.0:
            way = "figure of eight (net turning cancels)"
        else:
            way = "clockwise" if deg < 0 else "anticlockwise"
        print(f"   {Path(name).stem:16s} {deg:+7.1f} deg   {way}")


def count(csv_name: str, flip: bool) -> None:
    """How many corners this trace has, as the "what counts as a corner"
    threshold is relaxed. A plateau that sits on a circuit's published turn
    count is evidence the trace describes that layout — and a plateau that sits
    somewhere else is a warning not to curate it."""
    global MAX_RADIUS_M
    keep = MAX_RADIUS_M
    xs, zs = centreline(TRACKS / csv_name)
    print(f"\n## {Path(csv_name).stem}")
    try:
        for r in (150, 200, 220, 250, 300, 400, 500, 600, 800):
            MAX_RADIUS_M = r
            found, _ = analyse(xs, zs, flip=flip)
            seq = "".join(d[0].upper() for _, _, d in found)
            print(f"   radius <= {r:4d} m -> {len(found):3d} corners  {seq}")
    finally:
        MAX_RADIUS_M = keep


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    if args[0] == "--check":
        check()
        return
    if args[0] == "--sanity":
        sanity()
        return
    if args[0] == "--count":
        flip = _handedness()
        rest = args[1:] or [p.name for p in sorted(TRACKS.glob("*.csv"))]
        for a in rest:
            count(a if a.endswith(".csv") else a + ".csv", flip)
        return
    flip = _handedness()
    names = ([p.name for p in sorted(TRACKS.glob("*.csv"))] if args[0] == "--all"
             else [a if a.endswith(".csv") else a + ".csv" for a in args])
    for n in names:
        report(n, flip)


if __name__ == "__main__":
    main()
