"""With a focus active, the voice speaks the trigger word, the screen keeps the sentence.

Coaches speak on track in one to three words and explain once the car is
stopped. Here `voice.say` gets the trigger word, while the history and the
engine state keep the whole message — the overlay and the debrief lose nothing.
"""
from accoach.coaching.cue import Cue, CueCategory
from accoach.engine import _spoken_forms


def _cue(category, message):
    return Cue(category=category, message=message, priority=100.0,
               segment=3, pos=0.5)


def test_without_a_focus_voice_and_screen_say_the_same_thing():
    cue = _cue(CueCategory.LESS_BRAKE, "Freni troppo in curva 4")
    voice, screen = _spoken_forms(cue, focus_theme=None, lang="it")
    assert voice == "Freni troppo in curva 4"
    assert screen == "Freni troppo in curva 4"


def test_with_a_focus_the_voice_gets_the_trigger_word():
    cue = _cue(CueCategory.LESS_BRAKE, "Freni troppo in curva 4")
    voice, screen = _spoken_forms(cue, focus_theme="braking", lang="it")
    assert voice == "meno freno"
    assert screen == "Freni troppo in curva 4"


def test_a_cue_without_a_trigger_keeps_its_sentence():
    cue = _cue(CueCategory.LOCKED, "Bloccaggio!")
    voice, screen = _spoken_forms(cue, focus_theme="braking", lang="it")
    assert voice == "Bloccaggio!"
    assert screen == "Bloccaggio!"


def test_the_trigger_follows_the_language():
    cue = _cue(CueCategory.MORE_THROTTLE, "Poco gas in uscita")
    voice, _ = _spoken_forms(cue, focus_theme="traction", lang="en")
    assert voice == "throttle"
