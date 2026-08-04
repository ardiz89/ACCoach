"""Corner names the driver typed, for the circuits nobody curated.

Fourteen of the twenty-six bundled circuits have a name table and twelve do not,
each for a reason written down in ``tools/corner_atlas.HELD`` — and ten more
circuits in ACC have no bundled geometry at all, so no amount of desk work will
ever name them. The driver, on the other hand, is *on* those circuits and knows
perfectly well what the corner is called. This is where that goes.

**Not in the catalog, and the distinction is the whole design.** The catalog is
a cache: it is rebuilt from the lap files whenever it is missing or stale, and
:mod:`accoach.cornermap`'s learned corners live there precisely because losing
them costs a re-read. A name the driver typed cannot be recomputed from
anything. It is the only copy, so it goes in its own file, in plain JSON, next
to ``config.toml`` where a person can read it, back it up and edit it.

A name is stored against a **position**, not against a corner number, for the
same reason the curated tables are: the detector's numbering moves between laps
and between cars, and a name pinned to "corner 4" would drift off its corner the
first time a lap detected one corner fewer. It is also stored per **circuit**
and not per car — a corner's name is a fact about the road.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .cornermap import CLUSTER_TOL
from .trackdata import _key

#: How far a detected apex may sit from the stored position and still be the
#: corner that was named. Deliberately *not* ``trackdata._NAME_TOL`` (0.05,
#: about 290 m at Monza): that tolerance answers "which of the circuit's known
#: corners is this", where the alternatives are hundreds of metres apart. Here
#: the question is "is this the same apex I named", and the measured answer is
#: already in ``cornermap``: the same apex wanders up to 0.032 of a lap between
#: laps by the same car, so 0.04 covers the wander with nothing to spare for
#: reaching the corner next door.
TOL = CLUSTER_TOL

#: Longest name accepted. Not a guess at good taste: the name is drawn in the
#: corner title, in the chips, in the debrief sentences and in the coach's
#: speech, and the longest curated name we ship is "Variante del Rettifilo" at
#: 23 characters. Forty leaves room for a longer real name — the Nürburgring's
#: "Michael-Schumacher-S" is 20 — while a paragraph pasted in by accident is
#: refused where it can still be explained, rather than silently wrecking a
#: layout that was measured at 1600 px.
MAX_NAME = 40


def path() -> Path:
    from .paths import base_dir
    return base_dir() / "corner-names.json"


@dataclass(frozen=True)
class CustomNames:
    """One circuit's driver-typed names, ordered by position."""

    names: tuple[tuple[float, str], ...] = ()

    #: Carried on the object rather than imported by the caller, so
    #: ``trackdata`` can honour these names without importing this module —
    #: which it cannot do anyway, since this one imports it.
    tol: float = TOL

    def __len__(self) -> int:
        return len(self.names)

    def of(self, apex_pos: float) -> str | None:
        """The name for this apex, or None. Nearest wins, inside :data:`TOL`."""
        best, best_d = None, TOL
        for pos, name in self.names:
            d = abs(pos - apex_pos)
            if d <= best_d:
                best, best_d = name, d
        return best


_EMPTY = CustomNames()


def _read(p: Path) -> dict:
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load(p: Path | None = None) -> dict[str, CustomNames]:
    """Every circuit's names, keyed by circuit — not by the sim's spelling.

    An unreadable or half-written file costs the names and not the page: the
    report's job is to show a lap, and it must still do it when this file is
    corrupt. Same call already made for the learned corner map.
    """
    out: dict[str, CustomNames] = {}
    for track, rows in _read(p or path()).items():
        pairs = []
        if isinstance(rows, list):
            for row in rows:
                try:
                    pos, name = float(row["pos"]), str(row["name"]).strip()
                except (TypeError, ValueError, KeyError):
                    continue
                if name and 0.0 <= pos <= 1.0:
                    pairs.append((pos, name))
        if pairs:
            out[_key(str(track))] = CustomNames(tuple(sorted(pairs)))
    return out


def for_track(track: str, p: Path | None = None) -> CustomNames:
    return load(p).get(_key(track), _EMPTY)


def put(track: str, apex_pos: float, name: str, p: Path | None = None) -> None:
    """Name this corner, or — with an empty name — take the name back off it.

    Renaming the corner the driver already named replaces it rather than piling
    a second name onto the same apex: two names within :data:`TOL` of each other
    are two answers to one question, and the file would keep both while the
    screen could only ever show one.
    """
    p = p or path()
    name = (name or "").strip()
    key = _key(track)
    data = _read(p)

    rows = [r for r in data.get(key, []) if isinstance(r, dict)]
    kept = []
    for r in rows:
        try:
            if abs(float(r["pos"]) - apex_pos) > TOL:
                kept.append(r)
        except (TypeError, ValueError, KeyError):
            continue
    if name:
        kept.append({"pos": round(float(apex_pos), 4), "name": name})
    kept.sort(key=lambda r: r["pos"])

    if kept:
        data[key] = kept
    else:
        data.pop(key, None)
    _write(p, data)


def _write(p: Path, data: dict) -> None:
    """Write it whole or not at all.

    The file is the only copy of something a person typed, and the failure mode
    of a plain overwrite is a half-written file — which :func:`load` would then
    read as "no names", quietly, on the next page load.
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
