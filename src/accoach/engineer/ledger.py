"""The engineer's track record: every change it proposed, and what happened.

The race engineer is the one part of this app that can *prove* its advice works.
It proposes exactly one change, waits for the driver to apply it, measures the
next few clean laps and keeps or reverts. That loop already produces a verdict
every time — and until now we threw the verdict away the moment the message
scrolled past.

This module writes it down. Append-only JSONL under the app's data directory,
one line per completed test, and a summary that answers the only question a
setup tool should be asked: **how many of its changes actually worked?**

Three things are recorded, and the reason each is worth a line:

* **the outcome of a test** — kept or reverted, with the numbers on both sides.
  Over a season this is a hit rate per car, per symptom and per lever, measured
  on the driver's own laps rather than asserted in a marketing page;
* **which remedy in the list worked** (its rank). The profiles claim their
  remedy tables are ordered "most effective first". That is a falsifiable claim
  and nobody has ever checked it: if rank 0 keeps getting reverted while rank 2
  keeps being kept, the table is wrong for that car and the data says so;
* **the symptoms nobody was aiming at.** The verdict only looks at the symptom
  being treated. A softer front bar that fixes slow-entry understeer may cost
  something on exit, and today that goes unseen. These are **measured, never
  predicted** — this file will not assert a side effect it hasn't observed.

What is deliberately *not* here: any claim that a change will produce a given
number of tenths. We have no model that could support it, and the honest
version of that promise is this ledger, after it has some laps in it.

Failure is never fatal: a ledger that can't be written must not cost the driver
a setup change. Every write is best-effort and silent.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import base_dir

#: One file, appended forever. JSONL because it is written a line at a time from
#: a live session and may be read while it is being written — a JSON array would
#: have to be rewritten whole, and a crash mid-write would take the history with
#: it.
def ledger_path() -> Path:
    return base_dir() / "engineer_log.jsonl"


@dataclass(slots=True)
class Record:
    """One completed test of one setup change."""

    when_utc: str
    car: str
    track: str
    car_class: str
    phase: str
    symptom: str                 # "" for a structural change (e.g. pressures)
    param: str
    slot: int | None
    delta_clicks: int
    remedy_rank: int             # position in the profile's ordered remedy list
    kept: bool
    laps: int
    score_before: float
    score_after: float
    time_before_ms: float
    time_after_ms: float
    #: {symptom: score change} for symptoms the change was *not* aiming at.
    side_effects: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def append(record: Record, path: Path | None = None) -> bool:
    """Write one record. Returns whether it landed; never raises.

    Best-effort on purpose: the ledger is evidence we collect for ourselves, and
    a full disk or a locked file must not break the loop the driver is actually
    using.
    """
    p = path or ledger_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def read(path: Path | None = None, *, car: str = "", track: str = "") -> list[dict]:
    """Every record, oldest first, optionally filtered to a car and/or track.

    A malformed line is skipped rather than fatal: this file is appended to from
    a live session, and a half-written last line after a crash must not make the
    whole history unreadable.
    """
    p = path or ledger_path()
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        if car and rec.get("car") != car:
            continue
        if track and rec.get("track") != track:
            continue
        out.append(rec)
    return out


@dataclass(slots=True)
class Summary:
    """What the record adds up to. Counts, never estimates."""

    tests: int = 0
    kept: int = 0
    #: {param: (kept, tests)} — which levers actually earn their place.
    by_param: dict = field(default_factory=dict)
    #: {symptom: (kept, tests)}
    by_symptom: dict = field(default_factory=dict)
    #: {rank: (kept, tests)} — does "most effective first" hold up?
    by_rank: dict = field(default_factory=dict)
    #: Median lap-time change across the changes that were kept, in ms. Negative
    #: is faster. None when nothing has been kept yet.
    median_gain_ms: float | None = None

    @property
    def hit_rate(self) -> float | None:
        return (self.kept / self.tests) if self.tests else None


def summarise(records: list[dict]) -> Summary:
    """Fold the ledger into counts.

    Deliberately arithmetic only. The temptation with a file like this is to
    start inferring — "this lever works for you" off three samples — and three
    samples is where a hit rate is noise wearing a percentage sign. The caller
    decides what is enough; this returns what happened.
    """
    s = Summary(tests=len(records))
    gains: list[float] = []
    for rec in records:
        kept = bool(rec.get("kept"))
        s.kept += 1 if kept else 0
        for bucket, key in ((s.by_param, rec.get("param") or "?"),
                            (s.by_symptom, rec.get("symptom") or "—"),
                            (s.by_rank, rec.get("remedy_rank", 0))):
            k, n = bucket.get(key, (0, 0))
            bucket[key] = (k + (1 if kept else 0), n + 1)
        if kept:
            before = float(rec.get("time_before_ms") or 0.0)
            after = float(rec.get("time_after_ms") or 0.0)
            if before and after:
                gains.append(after - before)
    if gains:
        s.median_gain_ms = round(statistics.median(gains), 1)
    return s


def side_effect_counts(records: list[dict]) -> Counter:
    """How often each unintended symptom moved, across every test.

    The only route we have to honest side-effect advice: say nothing until the
    same lever has been seen to move the same symptom enough times to mean it.
    """
    counts: Counter = Counter()
    for rec in records:
        for sym in (rec.get("side_effects") or {}):
            counts[(rec.get("param") or "?", sym)] += 1
    return counts
