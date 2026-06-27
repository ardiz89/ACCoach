# Hand-off — coaching fixes from the first live validation (2026-06-26)

> STATUS 2026-06-26: **all three fixes below are now IMPLEMENTED in this session,
> with tests (full suite 164 green).** Fix A in `engine.py`, Fix B+C in
> `coaching/scheduler.py`. Still to do: **live re-validation on a clean lap** via
> `run_audit.py`. This note is kept as the rationale/record.

Source: surgical cue-audit of a live session (BMW M4 GT3 @ Imola, AC1, ref 1:43.775)
captured with `run_audit.py`. Raw data: `~/Documents/ACCoach/audit/live_session.jsonl`
(+ `session1_backup.jsonl`). Full findings in memory `live-validation-2026-06-26`.

The coach's **acute lock detection is production-grade**. Three real defects were
found, ranked by impact. Each item below has: the evidence, the mechanism in the
code, the proposed fix, and the tests to add/extend.

---

## Fix A — Abnormal-state gate (HIGHEST IMPACT)

**Evidence.** On a throw-away lap (delta ballooning +6→+13 s, then the car parked
at pos 0.783 with delta climbing to +180 s) the coach fired **6 `coasting` + 5
`trail_brake`** cues, a `GOOD` "bel tratto, continua così" at **delta +12.5 s /
65 km/h**, and a tyre-pressure cue. None of it is useful when you're not on a lap.

**Mechanism.** Nothing gates non-acute coaching on whether the lap is a valid
flying lap. The analyzer/braking/advisor detectors keep emitting and the scheduler
keeps speaking one every 4 s regardless of context.

**Proposed fix (in `src/accoach/engine.py` — owned by this thread, so `coaching/`
stays untouched).** In `CoachEngine.tick`, compute a `flying` flag and only submit
**non-acute** cues when flying; always submit acute ones. Keep calling every
detector's `update()` so their internal state still advances.

```python
GATE_DELTA_MS = 3000.0   # |delta| beyond this = not a representative lap
def _flying(delta):
    return delta is not None and abs(delta.delta_ms) <= GATE_DELTA_MS
```

Acute = LOCKED, WHEELSPIN, UNDERSTEER, OVERSTEER, FUEL (i.e. `tier_of(c) == ACUTE`).
Filter via `cue.tier == CueTier.ACUTE`. Suggested shape:

```python
flying = _flying(delta)
def submit(cues):
    self.scheduler.submit_all(
        [c for c in cues if flying or c.tier == CueTier.ACUTE])
```

Open question to tune live: add a speed/off-track condition too? Delta magnitude
alone already covers the parked/disaster case; revisit if needed.

**Tests (new `tests/test_engine_gate.py`, uses the existing stub-reader pattern):**
- driving frames with a small healthy delta → technique cues reach the scheduler;
- frames forced to a huge delta (slow/parked) → technique cues suppressed, but a
  lock/spin frame in the same window is still submitted/spoken.

---

## Fix B — Wheelspin starvation (acute cue dropped forever)

**Evidence.** 27 real wheelspins detected (rear slip_ratio 0.19–0.20 at full
throttle) → **0 `wheelspin` cues spoken** the whole session.

**Mechanism.** `CueScheduler.poll()` (`src/accoach/coaching/scheduler.py:43`):
within the 4 s gap it returns early; when it does fire it sorts `_pending`, picks
ONE, then `self._pending.clear()` drops the rest as "stale". But `EventDetector`
fires each episode **once** (`events.py` `_step`), so a spin that loses its slot to
a co-pending lock (both ACUTE prio 300; stable sort keeps lock first because
`events.update` appends lock before spin) is discarded and never re-emitted.

**Proposed fix (`scheduler.py`).** Don't discard un-spoken **ACUTE** cues — carry
them to the next cycle so they're spoken ~4 s later (if still fresh, see Fix C).
Non-acute cues stay "speak-now-or-stale". Sketch:

```python
# after choosing `chosen`, instead of a blanket clear:
self._pending = [c for c in self._pending
                 if c is not chosen and c.tier == CueTier.ACUTE]
```

Guard against unbounded growth (cap, or rely on Fix C staleness). Re-test that a
lock and a spin co-pending now both get spoken across two cycles.

**Tests (extend `tests/test_scheduler.py`):**
- submit a LOCKED and a WHEELSPIN in the same cycle → first poll speaks the higher,
  a poll 4 s later speaks the other (currently it's lost);
- a non-acute loser is still dropped (not carried).

---

## Fix C — Stale "coasting" spoken at full throttle

**Evidence.** `coasting` ("stai veleggiando") spoken at **throttle 0.99** (pos
0.273 and 0.485). Coasting is *detected* correctly (`braking.py` `_is_coasting`:
both pedals < 0.05, held 0.6 s) but *spoken* up to ~4 s later when the situation
has changed.

**Mechanism.** Speak-time ≠ detect-time. The scheduler has no notion of a cue's
age, so a queued cue can be voiced long after it stopped being true.

**Proposed fix.** Give `Cue` a generation timestamp (or pass `created_at` when the
scheduler receives it) and have `poll()` skip cues older than e.g. `min_interval_s`
(or whose `pos` is now far from the car). Smallest change: stamp in `submit`/
`submit_all`:

```python
def submit_all(self, cues, now=None):
    for c in cues: self._pending.append((c, now))
# in poll(): skip (c, t0) where now - t0 > STALE_S
```

`STALE_S ≈ 3–4 s` (a corner's worth). Mostly relevant to TECHNIQUE cues; acute
ones carried by Fix B should also respect it so a lock isn't announced a corner late.

**Tests (extend `tests/test_scheduler.py`):**
- a cue submitted, then `poll()` called after `> STALE_S` with the gap satisfied →
  not spoken;
- a fresh cue in the same poll → spoken.

---

## Suggested order
A (engine-only, biggest UX win, lowest risk) → C (kills the contradictory voicing)
→ B (recovers the missing acute spin). Re-run `python run_audit.py` after each and
diff against this baseline. Full suite must stay green (`python -m pytest -q`).
