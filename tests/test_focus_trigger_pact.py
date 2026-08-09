"""The briefing states the word you'll hear on track.

Trigger words only work because they were agreed beforehand. A coach who started
shouting "gas" without ever having said so would just be shouting.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import _brief_pact


def test_the_pact_names_the_trigger_word():
    assert _brief_pact(CueCategory.LESS_BRAKE, "it") == " In pista ti dirò solo: «meno freno»."
    assert _brief_pact(CueCategory.LESS_BRAKE, "en") == " On track I'll only say: “less brake”."


def test_no_trigger_no_pact():
    """Categories with no trigger word promise nothing."""
    assert _brief_pact(CueCategory.LOCKED, "it") == ""
    assert _brief_pact(CueCategory.GOOD, "it") == ""
