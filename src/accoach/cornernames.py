"""What the driver typed about a circuit: corner names, and braking references.

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

**The second kind: braking references.** Roadmap item 2 asks for "brake at the
end of the green" instead of a distance, and it stalled on exactly the half a
desk cannot supply. The *positions* have been measured for a while; the *words*
have not, and on 2026-07-31 two independent sources were found to contradict
each other on almost every corner at Imola — boards against flag-lights — with
no measurement able to arbitrate between a 50 m board and a 100 m one. The
driver is looking at the thing. Same file, same lifetime, same reasoning.
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

#: How far a braking onset may sit from a stored reference and still be the same
#: braking point. This is ``trackdata._LANDMARK_TOL``, not :data:`TOL`: a
#: landmark answers "is the car braking *here*", and the shipped tables already
#: settled that question at 0.02 — about 116 m at Monza, which is the length of
#: a braking zone rather than the width of an apex.
MARK_TOL = 0.02

#: A phrase, not a name: "alla fine del verde sulla sinistra" is 33 characters
#: and the longest one we ship ("alla fine del verde sulla sinistra") is exactly
#: that. Eighty leaves room without letting a paragraph into a table cell.
MAX_MARK = 80


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


@dataclass(frozen=True)
class CustomMarks:
    """One circuit's driver-typed braking references, ordered by position.

    Stored as the driver wrote them and shown in both languages unchanged.
    Translating a person's own words is the one thing this must not do: "alla
    fine del verde" is not a string with an English equivalent, it is what they
    see out of the window.
    """

    marks: tuple[tuple[float, str], ...] = ()
    tol: float = MARK_TOL

    def __len__(self) -> int:
        return len(self.marks)

    def of(self, pos: float) -> str | None:
        best, best_d = None, MARK_TOL
        for at, text in self.marks:
            d = abs(at - pos)
            if d <= best_d:
                best, best_d = text, d
        return best


_NO_MARKS = CustomMarks()


def _rows(entry, kind: str) -> list:
    """The rows of one kind out of a circuit's entry, whichever shape it is.

    The file shipped earlier today with a bare list of corner names per circuit;
    it now holds two kinds and so an object. Reading both is four lines and
    means nobody's file needs converting — including the one on this machine.
    """
    if isinstance(entry, list):
        return entry if kind == "corners" else []
    if isinstance(entry, dict):
        got = entry.get(kind)
        return got if isinstance(got, list) else []
    return []


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
    for track, entry in _read(p or path()).items():
        pairs = _pairs(_rows(entry, "corners"), "name")
        if pairs:
            out[_key(str(track))] = CustomNames(tuple(pairs))
    return out


def load_marks(p: Path | None = None) -> dict[str, CustomMarks]:
    out: dict[str, CustomMarks] = {}
    for track, entry in _read(p or path()).items():
        pairs = _pairs(_rows(entry, "marks"), "text")
        if pairs:
            out[_key(str(track))] = CustomMarks(tuple(pairs))
    return out


def _pairs(rows, field: str) -> list[tuple[float, str]]:
    """(position, text) for the rows that parse, in order — the rest dropped."""
    out = []
    for row in rows if isinstance(rows, list) else ():
        try:
            pos, text = float(row["pos"]), str(row[field]).strip()
        except (TypeError, ValueError, KeyError):
            continue
        if text and 0.0 <= pos <= 1.0:
            out.append((pos, text))
    return sorted(out)


def for_track(track: str, p: Path | None = None) -> CustomNames:
    return load(p).get(_key(track), _EMPTY)


def marks_for(track: str, p: Path | None = None) -> CustomMarks:
    return load_marks(p).get(_key(track), _NO_MARKS)


def put(track: str, apex_pos: float, name: str, p: Path | None = None) -> None:
    """Name this corner, or — with an empty name — take the name back off it.

    Renaming the corner the driver already named replaces it rather than piling
    a second name onto the same apex: two names within :data:`TOL` of each other
    are two answers to one question, and the file would keep both while the
    screen could only ever show one.
    """
    _put(track, apex_pos, name, "corners", "name", TOL, p)


def put_mark(track: str, pos: float, text: str, p: Path | None = None) -> None:
    """What you look at when you brake here, or — empty — take it back off."""
    _put(track, pos, text, "marks", "text", MARK_TOL, p)


def _put(track: str, pos: float, text: str, kind: str, field: str,
         tol: float, p: Path | None) -> None:
    p = p or path()
    text = (text or "").strip()
    key = _key(track)
    data = _read(p)

    entry = data.get(key)
    kinds = {k: [r for r in _rows(entry, k) if isinstance(r, dict)]
             for k in ("corners", "marks")}
    kept = []
    for r in kinds[kind]:
        try:
            if abs(float(r["pos"]) - pos) > tol:
                kept.append(r)
        except (TypeError, ValueError, KeyError):
            continue
    if text:
        kept.append({"pos": round(float(pos), 4), field: text})
    kept.sort(key=lambda r: r["pos"])
    kinds[kind] = kept

    kinds = {k: v for k, v in kinds.items() if v}
    if kinds:
        data[key] = kinds
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
