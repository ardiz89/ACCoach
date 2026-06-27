"""Per-sector lap breakdown, derived from position-indexed samples.

We prefer the sim's **real sector boundaries**: every sample carries the 0-based
``current_sector`` the game reported, so the boundary positions are simply where
that index increments around the lap. When a lap has no usable sector data (older
recordings, or AC content that doesn't publish sectors) we fall back to **equal
thirds** by track position — either way the split is positional, so any lap can be
timed against a chosen set of spans.

Because elapsed time (``t_ms``) is stored against position, splitting after the
fact is exact, works on laps already on disk, and lets us time *every* lap against
one canonical set of spans for a fair comparison and the **ideal lap** (each lap's
best sector stitched together).
"""

from __future__ import annotations

from dataclasses import dataclass

from .comparison import Reference
from .recording.lap import Lap

DEFAULT_SECTORS = 3

# A track has at most a handful of sectors; ignore anything larger as garbage.
_MAX_SECTORS = 30

# Span = a (start, end) track-position range. A lap's sectors are a list of these
# covering [0, 1]. They come either from the real boundaries or from equal thirds.
Span = tuple[float, float]


def sector_bounds(n: int = DEFAULT_SECTORS) -> list[Span]:
    """``n`` equal-position spans covering the lap."""
    return [(i / n, (i + 1) / n) for i in range(n)]


def real_boundaries(lap: Lap) -> list[float]:
    """Internal split positions from the sim's ``current_sector``, or ``[]``.

    A boundary is the position where the index **steps forward** (e.g. 0→1, 1→2)
    as the lap progresses. We deliberately key off the forward transition rather
    than the earliest position a sector index appears: a lap usually ends a few
    samples *past* the start/finish line still reporting the final sector (a
    trailing sample at pos≈0.000 with sector 2), so "earliest position" would put
    the last sector's boundary near 0 and lose the real split. Needs at least two
    distinct sectors to be meaningful.
    """
    bounds: dict[int, float] = {}
    distinct: set[int] = set()
    prev: int | None = None
    for s in lap.samples:
        v = s.current_sector
        if v < 0 or v >= _MAX_SECTORS:
            continue
        distinct.add(v)
        # Forward step (ignore the 2→0 wrap and any backward jitter): the new
        # sector begins here. Keep the first such position per index.
        if prev is not None and v > prev and v not in bounds and 0.0 < s.pos < 1.0:
            bounds[v] = s.pos
        prev = v
    if len(distinct) < 2:
        return []
    bs = sorted(round(p, 4) for v, p in bounds.items() if v > 0)
    # Drop any non-increasing duplicates that decimation noise could introduce.
    out: list[float] = []
    for p in bs:
        if not out or p > out[-1]:
            out.append(p)
    return out


def sector_spans(lap: Lap, n_default: int = DEFAULT_SECTORS) -> tuple[list[Span], bool]:
    """The spans to split ``lap`` by. Returns (spans, real?) — real boundaries
    when the sim published them, else equal thirds."""
    bs = real_boundaries(lap)
    if bs:
        edges = [0.0, *bs, 1.0]
        return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)], True
    return sector_bounds(n_default), False


def sector_times(lap: Lap, spans: list[Span]) -> list[int]:
    """Elapsed ms spent in each span.

    Returns ``[]`` when the lap is too sparse or has no time. Cumulative boundary
    times are rounded then diffed so the sectors sum to the lap time exactly: the
    clock starts at 0 and the final span closes on the recorded lap time.
    """
    ref = Reference(lap)
    if not ref.usable or lap.lap_time_ms <= 0:
        return []
    cum = [0]
    for start, end in spans[:-1]:
        cum.append(int(round(ref.time_at(end))))
    cum.append(int(lap.lap_time_ms))
    return [max(0, cum[i + 1] - cum[i]) for i in range(len(spans))]


@dataclass(slots=True)
class IdealLap:
    """The fastest sectors across a set of laps, stitched into one ideal time."""

    best_ms: list[int]        # best time per sector
    best_from: list[str]      # the lap path each best sector came from
    ideal_ms: int             # sum of the best sectors


def ideal_lap(laps: list[Lap], paths: list[str],
              spans: list[Span]) -> IdealLap | None:
    """Best-per-sector across ``laps`` (paired with ``paths``), all timed against
    the same ``spans``. None if no lap yields a full set of sectors."""
    n = len(spans)
    best: list[int | None] = [None] * n
    src: list[str | None] = [None] * n
    for lap, path in zip(laps, paths):
        st = sector_times(lap, spans)
        if len(st) != n:
            continue
        for i, t in enumerate(st):
            if t > 0 and (best[i] is None or t < best[i]):
                best[i] = t
                src[i] = path
    if any(b is None for b in best):
        return None
    best_ms = [int(b) for b in best]                      # type: ignore[arg-type]
    return IdealLap(best_ms=best_ms,
                    best_from=[s or "" for s in src],
                    ideal_ms=sum(best_ms))
