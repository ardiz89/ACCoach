"""Cue: urgency tiers and scheduling keys."""
from accoach.coaching.cue import Cue, CueCategory, CueTier, tier_of


def _cue(cat, priority=100.0, segment=3, pos=0.3):
    return Cue(cat, "msg", priority, segment, pos)


def test_acute_categories_outrank_technique():
    assert tier_of(CueCategory.LOCKED) == CueTier.ACUTE
    assert tier_of(CueCategory.OVERSTEER) == CueTier.ACUTE
    assert tier_of(CueCategory.BRAKE_LATER) == CueTier.TECHNIQUE


def test_advisory_categories():
    assert tier_of(CueCategory.TC_UP) == CueTier.ADVISORY
    assert tier_of(CueCategory.TYRE_PRESSURE) == CueTier.ADVISORY


def test_unknown_category_defaults_to_technique():
    assert tier_of(CueCategory.CARRY_SPEED) == CueTier.TECHNIQUE


def test_rank_orders_tier_before_priority():
    # A huge-priority technique cue must rank below a low-priority acute one.
    technique = _cue(CueCategory.CARRY_SPEED, priority=900.0)
    acute = _cue(CueCategory.LOCKED, priority=50.0)
    assert acute.rank() > technique.rank()       # higher tier wins
    assert acute.tier == CueTier.ACUTE


def test_priority_breaks_ties_within_a_tier():
    a = _cue(CueCategory.CARRY_SPEED, priority=300.0)
    b = _cue(CueCategory.MORE_THROTTLE, priority=100.0)
    assert a.rank() > b.rank()


def test_dedup_key_is_category_and_segment():
    a = _cue(CueCategory.BRAKE_LATER, segment=5)
    b = _cue(CueCategory.BRAKE_LATER, segment=5, priority=999.0)
    c = _cue(CueCategory.BRAKE_LATER, segment=6)
    assert a.dedup_key() == b.dedup_key()
    assert a.dedup_key() != c.dedup_key()
