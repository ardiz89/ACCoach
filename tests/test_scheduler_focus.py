"""The attention budget: with a focus active, the coach speaks about one theme only.

At most two or three themes per session is the rule independent professional
coaches agree on, for a stated reason: the bandwidth of a driver in motion is
finite. Here the cap is one, because the FocusCoach elects a single focus at a
time.

Acute cues stay outside the filter (they're events, not themes to train) and so do
advisories (they're spoken at the finish line, where there's room for a full
sentence).
"""
from accoach.coaching.cue import Cue, CueCategory
from accoach.coaching.debrief import build_lap_debrief
from accoach.coaching.scheduler import CueScheduler
from accoach.comparison import Reference
from accoach.track import detect_corners

import synth


def _cue(category, priority, segment=0):
    return Cue(category=category, message=category.value, priority=priority,
               segment=segment, pos=0.0)


def test_no_focus_behaves_exactly_as_today():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 300.0, segment=4))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.MORE_THROTTLE


def test_cue_in_the_focus_theme_speaks():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.LESS_BRAKE, 300.0, segment=4))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.LESS_BRAKE


def test_cue_outside_the_focus_theme_stays_silent():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 900.0, segment=4))   # costs more
    assert sch.poll(now=100.0) is None


def test_the_focus_theme_holds_everywhere_on_the_lap():
    """Coaches work the pattern, not a single corner."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.LESS_BRAKE, 100.0, segment=11))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.segment == 11


def test_acute_and_advisory_ignore_the_focus():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.WHEELSPIN, 250.0, segment=2))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.WHEELSPIN

    sch2 = CueScheduler()
    sch2.set_focus("braking")
    sch2.submit(_cue(CueCategory.TYRE_PRESSURE, 240.0, segment=0))
    chosen2 = sch2.poll(now=100.0)
    assert chosen2 is not None and chosen2.category is CueCategory.TYRE_PRESSURE


def test_praise_ignores_the_focus():
    """Opening with something true the driver does well is half the job."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.GOOD, 50.0, segment=6))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.GOOD


def test_clearing_the_focus_restores_everything():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.set_focus(None)
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 300.0, segment=4))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.MORE_THROTTLE


def test_an_off_theme_cue_does_not_consume_the_speaking_slot():
    """Filtered out at selection time, not at submit: if something else can speak, it speaks."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 900.0, segment=4))
    sch.submit(_cue(CueCategory.LESS_BRAKE, 100.0, segment=5))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.LESS_BRAKE


# --- nothing is lost, only postponed ---------------------------------------

def test_a_silenced_cue_is_still_in_the_debrief():
    """What the filter swallows on track must still be there afterwards.

    True by construction today — the debrief is computed from the lap and never
    learns what was spoken — but the construction is the whole guarantee, and
    nothing else pins it: let the focus theme reach `build_lap_debrief`, or
    build the debrief from what the scheduler actually said, and the driver
    silently loses the corners the voice skipped. The promise made to them is
    "nothing is lost, it moves to the debrief", so it gets a test of its own.
    """
    ref_lap = synth.build_lap(n=300, clean=True)
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    slow = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)

    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 900.0, segment=corners[0].index))
    assert sch.poll(now=100.0) is None, "an off-theme cue must not be spoken"

    debrief = build_lap_debrief(slow, reference, corners)
    lost_there = [loss for loss in debrief.losses
                  if loss.index == 0 and loss.lost_ms > 0]
    assert lost_there, "the debrief dropped the corner the voice stayed quiet on"
