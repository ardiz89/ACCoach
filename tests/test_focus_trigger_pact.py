"""The briefing states what you'll hear on track.

Trigger words only work because they were agreed beforehand. A coach who started
shouting "gas" without ever having said so would just be shouting.

The pact names the **theme** and gives the word as an example, because the theme
is what the filter actually enforces: with "braking" active the driver also hears
"trail it", "later", "earlier". Promising a single word and then saying four would
be a promise broken on the second lap.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import _brief_pact


def test_the_pact_names_the_theme_and_gives_the_word_as_an_example():
    assert _brief_pact(CueCategory.LESS_BRAKE, "it") == (
        " In pista sentirai solo parole di frenata, come «meno freno».")
    assert _brief_pact(CueCategory.LESS_BRAKE, "en") == (
        " On track you'll only hear braking words, like “less brake”.")


def test_the_theme_is_the_translated_label_not_the_english_key():
    """This one is shown to the driver, so here the label is the right thing."""
    assert "trazione" in _brief_pact(CueCategory.MORE_THROTTLE, "it")
    assert "traction" in _brief_pact(CueCategory.MORE_THROTTLE, "en")


def test_no_trigger_no_pact():
    """Categories with no trigger word promise nothing — and add no stray space."""
    assert _brief_pact(CueCategory.LOCKED, "it") == ""
    assert _brief_pact(CueCategory.GOOD, "it") == ""


def test_the_trail_brake_word_does_not_mean_release():
    """Il cue scatta quando rilasci il freno TROPPO PRESTO: la cura è portarne un
    filo all'inserimento. «rilascia» diceva il contrario di quel che serve."""
    from accoach.coaching.cue import TRIGGER
    assert TRIGGER[CueCategory.TRAIL_BRAKE] == {"it": "accompagna", "en": "trail it"}
    for word in TRIGGER[CueCategory.TRAIL_BRAKE].values():
        assert "rilascia" not in word and "release" not in word
