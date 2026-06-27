"""CoachAnalyzer: corner cause attribution + feed-forward cue lifecycle."""
from accoach.coaching.analyzer import CoachAnalyzer, CornerStats, classify_corner
from accoach.coaching.cue import CueCategory
from accoach.comparison import LapComparator, Reference
from accoach.track import detect_corners

import synth


# --- classify_corner: the pure cause-attribution core ----------------------

def _stats(lost, **kw):
    base = dict(throttle_live=1.0, throttle_ref=1.0, brake_live=0.0, brake_ref=0.0,
                min_speed_live=100.0, min_speed_ref=100.0, braking_early=False)
    base.update(kw)
    return CornerStats(lost_ms=lost, **base)


def test_classify_good_when_clearly_faster():
    cue = classify_corner(_stats(-300.0), 0, 0.3)
    assert cue is not None and cue.category == CueCategory.GOOD


def test_classify_none_when_loss_below_threshold():
    assert classify_corner(_stats(50.0), 0, 0.3) is None


def test_classify_braking_early_takes_precedence():
    cue = classify_corner(_stats(200.0, braking_early=True), 0, 0.3)
    assert cue.category == CueCategory.BRAKE_LATER


def test_classify_more_throttle():
    cue = classify_corner(_stats(200.0, throttle_live=0.6, throttle_ref=0.9), 0, 0.3)
    assert cue.category == CueCategory.MORE_THROTTLE


def test_classify_less_brake():
    cue = classify_corner(_stats(200.0, brake_live=0.5, brake_ref=0.2), 0, 0.3)
    assert cue.category == CueCategory.LESS_BRAKE


def test_classify_carry_speed():
    cue = classify_corner(_stats(200.0, min_speed_live=90.0, min_speed_ref=110.0), 0, 0.3)
    assert cue.category == CueCategory.CARRY_SPEED


def test_classify_generic_time_loss_fallback():
    cue = classify_corner(_stats(200.0), 0, 0.3)
    assert cue.category == CueCategory.TIME_LOSS
    assert cue.priority == 200.0


# --- zone layout -----------------------------------------------------------

def test_zone_at_returns_minus_one_on_straight():
    an = CoachAnalyzer()
    an.set_corners(detect_corners(synth.build_lap().samples))
    assert an._zone_at(0.5) == -1            # straight between the two corners
    assert an._zone_at(0.31) >= 0            # inside corner 0


def test_set_corners_falls_back_to_fixed_segments():
    an = CoachAnalyzer(num_segments=8)
    an.set_corners([])
    assert len(an._zones) == 8


# --- feed-forward lifecycle ------------------------------------------------

def _snap_from_sample(smp, extra_ms=0):
    return synth.snap(
        pos=smp.pos, current_lap_ms=smp.t_ms + extra_ms, speed_kmh=smp.speed_kmh,
        throttle=smp.throttle, brake=smp.brake, steer_angle=smp.steer_angle,
        gear=smp.gear,
    )


def _drive(analyzer, comparator, lap, extra_ms_in_corner0=0):
    """Replay one lap of frames; return cues emitted during it."""
    cues = []
    for smp in lap.samples:
        extra = extra_ms_in_corner0 if 0.16 <= smp.pos <= 0.40 else 0
        s = _snap_from_sample(smp, extra)
        cues += analyzer.update(s, comparator.compare(s))
    return cues


def test_feed_forward_announces_corner_advice_on_next_lap():
    ref = Reference(synth.build_lap())
    an = CoachAnalyzer()
    an.set_corners(detect_corners(ref.lap.samples))
    cmp = LapComparator(ref)

    review = synth.build_lap(slow_corner=0, amt=30)
    # Lap 1: the analyzer watches and stores corner-0 advice (no announce yet).
    _drive(an, cmp, review)
    # Lap 2: approaching corner 0, the stored advice is spoken.
    lap2 = _drive(an, cmp, review)
    announced = [c for c in lap2 if c.segment == 0
                 and c.category in (CueCategory.CARRY_SPEED, CueCategory.MORE_THROTTLE,
                                    CueCategory.BRAKE_LATER, CueCategory.LESS_BRAKE,
                                    CueCategory.TIME_LOSS)]
    assert announced, "expected corner-0 advice to be announced on lap 2"


def test_no_cues_when_delta_is_none():
    an = CoachAnalyzer()
    assert an.update(synth.snap(pos=0.3), None) == []
