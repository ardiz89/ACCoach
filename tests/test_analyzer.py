"""CoachAnalyzer: corner cause attribution + feed-forward cue lifecycle."""
from accoach.coaching.analyzer import (
    CoachAnalyzer, CornerStats, classify_corner, corner_level, _GAIN_MS, _LOSS_MS,
)
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


# --- la carta della curva: il dato che oggi viene buttato -------------------

def _replay(review=None):
    """Guida un giro contro se stesso (o contro `review`); torna (analyzer, cues)."""
    ref = Reference(synth.build_lap())
    an = CoachAnalyzer()
    an.set_corners(detect_corners(ref.lap.samples))
    cmp = LapComparator(ref)
    cues = _drive(an, cmp, review if review is not None else synth.build_lap())
    return an, cues


def test_no_card_before_the_first_corner_closes():
    an = CoachAnalyzer()
    an.set_corners(detect_corners(synth.build_lap().samples))
    assert an.last_corner is None


def test_a_corner_taken_well_still_leaves_a_card():
    """Il caso che oggi si perde: classify_corner torna None e il dato sparisce."""
    an, cues = _replay()
    assert cues == [], "un giro contro se stesso non deve produrre cue"
    assert an.last_corner is not None
    assert an.last_corner.index == 1            # l'ultima curva chiusa del giro
    assert abs(an.last_corner.lost_ms) < _LOSS_MS  # dentro la norma, e comunque misurata


def test_the_card_follows_the_corner_you_just_left():
    an, _ = _replay(synth.build_lap(slow_corner=0, amt=30))
    assert an.last_corner is not None
    assert an.last_corner.index == 1


def test_set_corners_clears_the_card():
    """Un layout di zone nuovo invalida gli indici: la carta vecchia mente.

    Il layout dev'essere davvero un altro: ripassare le curve della stessa pista
    non è un layout nuovo. Qui si passa al ripiego a segmenti fissi, che è la
    differenza più netta possibile.
    """
    an, _ = _replay()
    assert an.last_corner is not None
    an.set_corners([])
    assert an.last_corner is None


def test_the_same_layout_recomputed_keeps_the_card():
    """Il motore richiama `set_corners` a ogni giro salvato, con le stesse zone.

    Se azzerasse comunque, il riquadro sparirebbe dal traguardo alla prima
    curva su ogni giro — il rettilineo dove il pilota ha davvero il tempo di
    leggerlo.
    """
    an, _ = _replay()
    an.set_corners(detect_corners(synth.build_lap().samples))
    assert an.last_corner is not None


def test_reset_keeps_the_card():
    """`reset()` butta lo stato del giro in corso; la carta non lo è.

    Era il contrario, e si contraddiceva col commento della carta stessa
    («sopravvive al traguardo di proposito»): `_rebuild_reference` chiama
    `reset()` dopo ogni giro salvato, quindi il riquadro spariva a ogni giro.
    """
    an, _ = _replay()
    an.reset()
    assert an.last_corner is not None


def test_drop_last_corner_clears_the_card():
    an, _ = _replay()
    an.drop_last_corner()
    assert an.last_corner is None


# --- il semaforo: stesse soglie della voce, o si contraddicono --------------

def test_a_clear_gain_is_the_bright_end():
    assert corner_level(-_GAIN_MS) == "gain"
    assert corner_level(-_GAIN_MS - 1) == "gain"


def test_inside_the_band_is_green():
    assert corner_level(0.0) == "ok"
    assert corner_level(-_GAIN_MS + 1) == "ok"
    assert corner_level(_LOSS_MS - 1) == "ok"


def test_the_colour_turns_exactly_where_the_coach_speaks():
    """La soglia del giallo È la soglia della voce: se il coach parla, non è verde."""
    assert corner_level(_LOSS_MS) == "warn"
    assert corner_level(_GAIN_MS) == "warn"


def test_past_the_praise_threshold_the_other_way_is_red():
    assert corner_level(_GAIN_MS + 1) == "bad"


def test_the_level_never_contradicts_the_voice():
    """Ogni perdita che merita un cue è almeno gialla; ogni lode è 'gain'."""
    for lost in (_LOSS_MS, _LOSS_MS + 50, _GAIN_MS, _GAIN_MS + 500):
        st = CornerStats(lost_ms=lost, throttle_live=1.0, throttle_ref=1.0,
                         brake_live=0.0, brake_ref=0.0, min_speed_live=100.0,
                         min_speed_ref=100.0, braking_early=False)
        assert classify_corner(st, 0, 0.3) is not None
        assert corner_level(lost) in ("warn", "bad")
    assert corner_level(-_GAIN_MS) == "gain"
