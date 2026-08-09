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
from accoach.coaching.scheduler import CueScheduler


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
