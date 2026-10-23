"""La voce dice la regola, lo schermo tiene il numero.

Il pilota il 22/10: «basta generalizzare, quando vado ai box da setup visivo vedo
cosa c'è da fare». Gli avvisi di gomme e di aiuti portano due testi: `message`
(col valore, per lo schermo e il report) e `voice` (la frase generale, senza
cifre, l'unica che avra' un WAV). Le asserzioni stanno sulla direzione, perche'
«troppo gonfie» detto a gomme sgonfie e' l'errore che conta.
"""
import re
from dataclasses import replace

import pytest

import tono
from accoach.coaching.advisor import SetupAdvisor
from accoach.coaching.cue import Cue, CueCategory
from accoach.coaching.pressure import PressureAdvisor
from accoach.coaching.tyretemp import TyreTempAdvisor
from accoach.engine import _spoken_forms
from accoach.i18n import cue_text

import test_advisor as adv_t
import test_pressure as press_t
import test_tyretemp as temp_t


def _pressure(press):
    out, _ = press_t._drive_lap(PressureAdvisor(), press)
    assert len(out) == 1
    return out[0]


def _temp(temp):
    out, _ = temp_t._drive_lap(TyreTempAdvisor(), temp)
    assert len(out) == 1
    return out[0]


def _aid(kind, level):
    base = replace(adv_t._BASE, tc_level=level, abs_level=level)
    adv = SetupAdvisor()
    event = adv_t._lock if kind == "abs" else adv_t._spin
    now = 0.0
    for seg in range(20):
        cues = {3: [event(3)], 8: [event(8)], 14: [event(14)]}.get(seg, [])
        adv.update(replace(base, lap_position=seg / 20 + 0.001), cues, now)
        now += 0.1
    out = adv.update(replace(base, lap_position=0.01), [], now)
    assert len(out) == 1
    return out[0]


def _no_digits(text):
    assert not re.search(r"\d", text), text


PRESSURE_CASES = [
    # (psi per ruota, asse, parola di direzione, azione)
    ((28.2, 28.0, 26.4, 26.5), "anteriori", "gonfie", "togli"),
    ((26.5, 26.4, 28.2, 28.0), "posteriori", "gonfie", "togli"),
    ((24.0, 24.2, 26.5, 26.4), "anteriori", "sgonfie", "aggiungi"),
    ((26.5, 26.4, 24.0, 24.2), "posteriori", "sgonfie", "aggiungi"),
]


@pytest.mark.parametrize("press,axle,word,action", PRESSURE_CASES)
def test_pressure_voice_is_general_and_screen_keeps_the_number(press, axle, word, action):
    cue = _pressure(press)
    assert "psi" in cue.message and re.search(r"\d", cue.message)
    assert cue.voice is not None
    _no_digits(cue.voice)
    v = cue.voice.lower()
    assert axle in v and f"troppo {word}" in v and action in v and "freddo" in v
    if word == "gonfie":
        assert "sgonfie" not in v and "aggiungi" not in v
    else:
        assert "troppo sgonfie" in v and "togli" not in v


@pytest.mark.parametrize("temp,word,action", [
    (98.0, "calde", "fluido"),
    (62.0, "fredde", "spingi"),
])
def test_temperature_voice_has_no_degrees(temp, word, action):
    cue = _temp(temp)
    assert "°C" in cue.message
    _no_digits(cue.voice)
    assert f"troppo {word}" in cue.voice.lower() and action in cue.voice.lower()
    assert "°" not in cue.voice


@pytest.mark.parametrize("kind,level,aid", [
    ("abs", 3, "ABS"), ("abs", -1, "ABS"), ("tc", 4, "TC"), ("tc", -1, "TC"),
])
def test_aid_voice_drops_the_from_to(kind, level, aid):
    cue = _aid(kind, level)
    assert "alza" in cue.voice.lower() and aid in cue.voice
    _no_digits(cue.voice)
    assert "dal" not in cue.voice
    if level >= 0:
        assert f" dal {level} al {level + 1}." in cue.message
    else:
        assert "dal" not in cue.message


def test_the_known_and_unknown_level_say_the_same_thing():
    assert _aid("abs", 3).voice == _aid("abs", -1).voice
    assert _aid("tc", 4).voice == _aid("tc", -1).voice


def test_brake_bias_sentence_is_untouched():
    cue = _aid("abs", 9)
    assert cue.category is CueCategory.BRAKE_BIAS
    assert cue.voice is None
    assert cue.message == ("ABS già alto, blocchi davanti in più curve. "
                           "Sposta il bilanciamento freni indietro.")


def test_voice_defaults_to_none():
    assert Cue(CueCategory.LOCKED, "x", 1.0, 0, 0.0).voice is None


# --- _spoken_forms -----------------------------------------------------------

def test_spoken_forms_without_focus_gives_voice_then_screen():
    cue = _pressure(PRESSURE_CASES[0][0])
    assert _spoken_forms(cue, None, "it") == (cue.voice, cue.message)


def test_spoken_forms_without_voice_is_the_message_twice():
    cue = Cue(CueCategory.LOCKED, "Bloccaggio!", 1.0, 0, 0.0)
    assert _spoken_forms(cue, None, "it") == ("Bloccaggio!", "Bloccaggio!")


def test_spoken_forms_with_focus_and_trigger_word_keeps_the_word():
    cue = Cue(CueCategory.MORE_THROTTLE, "Poco gas", 1.0, 0, 0.0, voice="Gas.")
    assert _spoken_forms(cue, "traction", "it") == ("gas", "Poco gas")


def test_spoken_forms_with_focus_and_no_trigger_uses_the_general_voice():
    cue = _aid("abs", 3)
    assert _spoken_forms(cue, "braking", "it") == (cue.voice, cue.message)


def test_in_english_the_voice_is_the_translated_message():
    # Il motore traduce `message` prima di `_spoken_forms`: la voce inglese e'
    # quel testo, non la frase italiana generale.
    cue = _pressure(PRESSURE_CASES[0][0])
    cue.message = cue_text(cue.message, "en")
    voice, screen = _spoken_forms(cue, None, "en")
    assert voice == screen == cue.message
    assert "psi" in voice and "Gomme" not in voice


# --- il tono -----------------------------------------------------------------

def test_every_new_spoken_sentence_passes_the_tone_check():
    cues = [_pressure(c[0]) for c in PRESSURE_CASES]
    cues += [_temp(98.0), _temp(62.0)]
    cues += [_aid(k, lv) for k in ("abs", "tc") for lv in (3, -1)]
    for cue in cues:
        for sentence in re.split(r"(?<=[.!?])\s+", cue.voice):
            assert tono.violations(sentence, "it", max_words=8) == [], sentence
