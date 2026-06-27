"""Decide which cue to actually speak, and when.

The analyzer can produce a cue at every segment boundary — far more than a driver
wants to hear. :class:`CueScheduler` is the filter between "what could be said"
and "what is said":

* a minimum gap between spoken cues, so the coach never talks over itself;
* pick the **highest-priority** pending cue (the biggest time loss) when several
  are queued, and drop the rest as stale;
* suppress a cue that repeats the *same advice in the same place* too soon, so
  you're not told "more throttle here" every single lap.

Two refinements from the 2026-06-26 live validation:

* **Staleness (per tier).** A cue queued behind the min-gap can be voiced seconds
  after it stopped being true ("stai veleggiando" spoken at full throttle).
  Technique/advisory cues are dropped once older than ``technique_stale_s`` —
  shorter than the speak gap, so they're never voiced stale. Acute cues get a
  longer window so a carried-over one (below) can still be spoken next cycle.
* **Acute carry-over.** Acute events (lock-up, wheelspin) fire once per episode,
  so an un-spoken acute cue dropped as "stale this cycle" is lost forever. We now
  carry un-spoken ACUTE cues to the next cycle instead, so a spin that loses its
  slot to a lock is still announced ~one gap later rather than swallowed.

Time is injected (``now`` in monotonic seconds) so the logic is pure and
testable without real clocks or audio. ``submit``/``submit_all`` take an optional
``now`` used as the cue's queue time; when omitted (older callers/tests) the cue
never goes stale.
"""

from __future__ import annotations

from .cue import Cue, CueTier

_DEFAULT_MIN_INTERVAL_S = 4.0
_DEFAULT_ACUTE_INTERVAL_S = 1.5      # acute cues may speak this soon after the last cue
_DEFAULT_REPEAT_SUPPRESS_S = 20.0
_DEFAULT_TECHNIQUE_STALE_S = 2.5     # technique/advisory cue older than this is dropped
_ACUTE_STALE_MARGIN_S = 1.5          # acute window = min_interval + this (survives 1 carry)


class CueScheduler:
    def __init__(
        self,
        min_interval_s: float = _DEFAULT_MIN_INTERVAL_S,
        repeat_suppress_s: float = _DEFAULT_REPEAT_SUPPRESS_S,
        technique_stale_s: float = _DEFAULT_TECHNIQUE_STALE_S,
        acute_interval_s: float = _DEFAULT_ACUTE_INTERVAL_S,
    ) -> None:
        self.min_interval_s = min_interval_s
        self.acute_interval_s = acute_interval_s
        self.repeat_suppress_s = repeat_suppress_s
        self.technique_stale_s = technique_stale_s
        # Each entry is (cue, queued_at | None).
        self._pending: list[tuple[Cue, float | None]] = []
        self._last_spoken_at: float = -1e9
        self._recent: dict[tuple, float] = {}  # dedup_key -> last spoken time

    def submit(self, cue: Cue, now: float | None = None) -> None:
        self._pending.append((cue, now))

    def submit_all(self, cues: list[Cue], now: float | None = None) -> None:
        self._pending.extend((c, now) for c in cues)

    def _stale_limit(self, cue: Cue) -> float:
        if cue.tier == CueTier.ACUTE:
            return self.min_interval_s + _ACUTE_STALE_MARGIN_S
        return self.technique_stale_s

    def _is_stale(self, cue: Cue, queued_at: float | None, now: float) -> bool:
        return queued_at is not None and (now - queued_at) > self._stale_limit(cue)

    def poll(self, now: float) -> Cue | None:
        """Return the cue to speak right now, or ``None``."""
        # Drop stale cues every tick, independent of the speak gap, so the queue
        # never holds something that's no longer true.
        self._pending = [
            (c, t0) for (c, t0) in self._pending if not self._is_stale(c, t0, now)
        ]

        elapsed = now - self._last_spoken_at
        if elapsed < self.acute_interval_s:
            return None
        # Between the acute and the full gap, only acute cues may interrupt — a
        # lock-up/wheelspin is spoken close to the event instead of waiting the
        # full technique gap; technique cues still wait the full interval.
        acute_only = elapsed < self.min_interval_s
        if not self._pending:
            return None

        # Most urgent first: tier dominates, priority breaks ties within a tier
        # (so a big corner time-loss can't jump ahead of an acute safety call).
        self._pending.sort(key=lambda ct: ct[0].rank(), reverse=True)
        chosen: Cue | None = None
        for cue, _t0 in self._pending:
            if acute_only and cue.tier != CueTier.ACUTE:
                continue
            last = self._recent.get(cue.dedup_key())
            if last is not None and now - last < self.repeat_suppress_s:
                continue
            chosen = cue
            break

        if chosen is None:
            # Nothing eligible spoke; keep the queue (staleness will prune it) so a
            # fresh technique cue isn't discarded during an acute-only window.
            return None

        # We're speaking: carry over un-spoken ACUTE cues to the next cycle; drop
        # everything else as stale-this-cycle. A single-shot acute event thus
        # isn't lost when it loses its slot — it speaks ~one gap later.
        self._pending = [
            (c, t0) for (c, t0) in self._pending
            if c is not chosen and c.tier == CueTier.ACUTE
        ]
        self._last_spoken_at = now
        self._recent[chosen.dedup_key()] = now
        return chosen

    def reset(self) -> None:
        self._pending.clear()
