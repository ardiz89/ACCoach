"""CueScheduler ordering: tier dominates raw priority."""
from accoach.coaching.cue import Cue, CueCategory, CueTier, tier_of
from accoach.coaching.scheduler import CueScheduler


def _cue(category, priority, segment=0):
    return Cue(category=category, message=category.value, priority=priority,
               segment=segment, pos=0.0)


def test_tier_assignment():
    assert tier_of(CueCategory.LOCKED) == CueTier.ACUTE
    assert tier_of(CueCategory.UNDERSTEER) == CueTier.ACUTE
    assert tier_of(CueCategory.FUEL) == CueTier.ACUTE
    assert tier_of(CueCategory.MORE_THROTTLE) == CueTier.TECHNIQUE
    assert tier_of(CueCategory.LIMITER) == CueTier.TECHNIQUE
    assert tier_of(CueCategory.TYRE_PRESSURE) == CueTier.ADVISORY


def test_acute_beats_big_corner_loss():
    sch = CueScheduler()
    # A corner losing 0.8s (raw-ms priority 800) must NOT outrank a lock-up.
    sch.submit(_cue(CueCategory.TIME_LOSS, 800.0, segment=3))
    sch.submit(_cue(CueCategory.LOCKED, 300.0, segment=5))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.LOCKED


def test_priority_breaks_ties_within_tier():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.TIME_LOSS, 200.0, segment=1))
    sch.submit(_cue(CueCategory.CARRY_SPEED, 500.0, segment=2))   # bigger loss
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.CARRY_SPEED


def test_advisory_yields_to_technique():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.TYRE_PRESSURE, 240.0, segment=0))   # advisory
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 130.0, segment=4))   # technique
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.MORE_THROTTLE


def test_min_interval_still_gates():
    sch = CueScheduler(min_interval_s=4.0)
    sch.submit(_cue(CueCategory.LOCKED, 300.0))
    assert sch.poll(now=100.0) is not None
    sch.submit(_cue(CueCategory.OVERSTEER, 300.0))
    assert sch.poll(now=101.0) is None        # within the min interval
    sch.submit(_cue(CueCategory.OVERSTEER, 300.0, segment=9))
    assert sch.poll(now=105.0) is not None     # interval elapsed


# --- Fix B: acute carry-over (2026-06-26 live: 27 spins detected, 0 spoken) ---

def test_unspoken_acute_is_carried_to_next_cycle():
    sch = CueScheduler()
    # A lock and a spin pile up in the same cycle; only one can be spoken now.
    sch.submit(_cue(CueCategory.LOCKED, 300.0, segment=5), now=100.0)
    sch.submit(_cue(CueCategory.WHEELSPIN, 300.0, segment=7), now=100.0)
    first = sch.poll(now=100.0)
    assert first is not None and first.tier == CueTier.ACUTE
    # The other acute cue is NOT lost — it speaks once the gap elapses.
    second = sch.poll(now=104.0)
    assert second is not None and second.tier == CueTier.ACUTE
    assert second.category is not first.category


def test_non_acute_loser_is_dropped_not_carried():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.LOCKED, 300.0, segment=5), now=100.0)
    sch.submit(_cue(CueCategory.CARRY_SPEED, 900.0, segment=2), now=100.0)  # technique
    assert sch.poll(now=100.0).category is CueCategory.LOCKED
    # The technique cue was dropped as stale-this-cycle, not queued for later.
    assert sch.poll(now=104.0) is None


# --- Fix C: staleness (2026-06-26 live: "stai veleggiando" spoken at full gas) ---

def test_stale_technique_cue_is_not_spoken():
    sch = CueScheduler(min_interval_s=4.0, technique_stale_s=2.5)
    sch.submit(_cue(CueCategory.COASTING, 270.0, segment=3), now=100.0)
    # Next speak opportunity is a full gap later; by then the coast is long over.
    assert sch.poll(now=104.0) is None


def test_fresh_technique_cue_is_spoken():
    sch = CueScheduler(min_interval_s=4.0, technique_stale_s=2.5)
    # First open the gap, then a fresh technique cue within the stale window.
    sch.submit(_cue(CueCategory.LOCKED, 300.0), now=100.0)
    sch.poll(now=100.0)
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 200.0, segment=4), now=105.0)
    assert sch.poll(now=105.5).category is CueCategory.MORE_THROTTLE


# --- Acute latency: acute cues interrupt sooner than the full technique gap ---

def test_acute_can_interrupt_before_full_gap():
    sch = CueScheduler(min_interval_s=4.0, acute_interval_s=1.5)
    sch.submit(_cue(CueCategory.LOCKED, 300.0, segment=0), now=100.0)
    assert sch.poll(now=100.0) is not None              # first cue spoken
    # A new acute event 1.6 s later may speak — no need to wait the full 4 s.
    sch.submit(_cue(CueCategory.WHEELSPIN, 300.0, segment=5), now=101.6)
    spoken = sch.poll(now=101.6)
    assert spoken is not None and spoken.category is CueCategory.WHEELSPIN


def test_technique_still_waits_full_gap():
    sch = CueScheduler(min_interval_s=4.0, acute_interval_s=1.5)
    sch.submit(_cue(CueCategory.LOCKED, 300.0, segment=0), now=100.0)
    sch.poll(now=100.0)
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 200.0, segment=4), now=101.6)
    assert sch.poll(now=102.0) is None                  # acute-only window
    assert sch.poll(now=104.0).category is CueCategory.MORE_THROTTLE


def test_carried_acute_survives_to_next_slot_but_not_forever():
    sch = CueScheduler(min_interval_s=4.0)
    sch.submit(_cue(CueCategory.LOCKED, 300.0, segment=5), now=100.0)
    sch.submit(_cue(CueCategory.WHEELSPIN, 300.0, segment=7), now=100.0)
    sch.poll(now=100.0)                       # speaks one, carries the other
    # Way past the acute stale window -> the carried cue is finally dropped.
    assert sch.poll(now=120.0) is None
