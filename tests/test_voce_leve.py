"""L'ingegnere a voce: il prefisso e poi la leva, senza il numero dei click.

Ogni frase che la voce dice in italiano diventa un WAV registrato una volta
(ElevenLabs); una leva senza la sua frase cadrebbe sulla voce di Windows. Questi
test pretendono che ogni rimedio che un profilo puo' proporre abbia la sua frase,
che sia vera (la direzione del passo) e che stia nel tono del 21/10.
"""
import re

import pytest

from accoach.engineer import Balance, LapStats, Phase, Speed, Symptom
from accoach.engineer.core import AtomicChange, ProposedChange, WorkPhase
from accoach.engineer.profiles import FORMULA_PROFILE, GT3_PROFILE, ROAD_PROFILE
from accoach.engineer.steps import AccSteps
from accoach.engineer.voice_levers import all_voice_levers, voice_lever

import tono

_PROFILES = {"GT3": GT3_PROFILE, "Formula": FORMULA_PROFILE, "Road": ROAD_PROFILE}


class _FakePhase(WorkPhase):
    def owns(self, symptom):
        return True

    def gate(self, window):
        return False


def _all_remedies():
    """Ogni builder di ogni profilo, costruito come fa il motore."""
    phase = _FakePhase("x", "Mechanical grip", "BOX")
    out = []
    for name, prof in _PROFILES.items():
        for sym, builders in prof.remedy_table.items():
            for i, build in enumerate(builders):
                out.append((f"{name}:{sym}:{i}", build(sym, phase)))
    return out


def _pressure(front, rear):
    from accoach.engineer.profiles._common import PressurePhase
    ph = PressurePhase(27.5, 0.7, steps=AccSteps())
    return ph.pressure_remedy(LapStats(lap_time_ms=100000, symptom_scores={},
                                       symptom_corners={},
                                       pressures_hot={"front": front, "rear": rear}))


def _check(phrase):
    assert phrase, "nessuna frase a voce"
    assert not re.search(r"\d", phrase), f"un numero a voce: {phrase!r}"
    assert tono.words(phrase) <= 8, f"troppo lunga per la voce: {phrase!r}"


@pytest.mark.parametrize("where,change", _all_remedies(), ids=lambda x: x if isinstance(x, str) else "")
def test_every_profile_remedy_has_a_voice_lever(where, change):
    _check(voice_lever(change))


# --- la direzione: scritti a mano, dalla tabella --------------------------

def _ch(param, slots, step):
    return ProposedChange(tuple(AtomicChange(param, s, step) for s in slots),
                          "x", "y", "BOX")


@pytest.mark.parametrize("param,slots,step,word", [
    ("aRBFront", (None,), -1, "Ammorbidisci"),
    ("aRBRear", (None,), -1, "Ammorbidisci"),
    ("rearWing", (None,), -1, "Riduci"),
    ("rearWing", (None,), +1, "Aumenta"),
    ("brakeBias", (None,), -1, "indietro"),
    ("brakeBias", (None,), +1, "avanti"),
    ("rideHeight", (2, 3), +2, "Alza"),
    ("rideHeight", (2, 3), -2, "Abbassa"),
    ("preload", (None,), -1, "Riduci"),
    ("preload", (None,), +1, "Aumenta"),
    ("toe", (0, 1), -1, "toe-out"),
    ("toe", (2, 3), +1, "toe-in"),
    ("camber", (0, 1), -1, "negativo"),
    ("tyrePressure", (0, 1), -2, "Abbassa"),
])
def test_the_lever_goes_the_way_the_step_goes(param, slots, step, word):
    assert word in voice_lever(_ch(param, slots, step))


def test_the_step_size_does_not_change_the_phrase():
    """Uno o due click, a voce e' la stessa leva: il numero lo tiene lo schermo."""
    assert voice_lever(_ch("rideHeight", (2, 3), +1)) == voice_lever(_ch("rideHeight", (2, 3), +2))


def test_a_lever_nobody_wrote_is_none():
    """Una leva nella direzione che nessun profilo propone non ha una frase: meglio
    None (e il ripiego col log) che una frase vera per la direzione opposta."""
    assert voice_lever(_ch("aRBFront", (None,), +1)) is None
    assert voice_lever(ProposedChange((), "x", "y", "BOX")) is None


@pytest.mark.parametrize("front,rear,axis,word", [
    (24.7, 27.5, "anteriori", "Alza"),
    (30.0, 27.5, "anteriori", "Abbassa"),
    (27.5, 24.7, "posteriori", "Alza"),
    (27.5, 30.0, "posteriori", "Abbassa"),
])
def test_the_four_pressure_levers(front, rear, axis, word):
    phrase = voice_lever(_pressure(front, rear))
    _check(phrase)
    assert axis in phrase and phrase.startswith(word)


def test_the_table_keeps_the_tone():
    phrases = all_voice_levers()
    assert len(phrases) == len(set(phrases)), "la stessa frase due volte"
    bad = {p: tono.violations(p, "it", tono.MAX_WORDS_BY_SURFACE["coach"])
           for p in phrases}
    assert {p: v for p, v in bad.items() if v} == {}
    for p in phrases:
        _check(p)


def test_every_phrase_in_the_table_is_reachable():
    """Una frase che nessun rimedio produce e' un WAV pagato per niente."""
    used = {voice_lever(c) for _, c in _all_remedies()}
    used |= {voice_lever(_pressure(f, r)) for f, r in
             ((24.7, 27.5), (30.0, 27.5), (27.5, 24.7), (27.5, 30.0))}
    assert set(all_voice_levers()) == used


# --- l'annuncio -----------------------------------------------------------

class _FakeVoice:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def close(self):
        pass


def _engine(tmp_path, monkeypatch, lang="it"):
    import accoach.engine as engine_mod
    from accoach.engine import CoachEngine
    from accoach.telemetry.snapshot import TelemetrySnapshot

    class _Reader:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    monkeypatch.setattr(engine_mod, "current_language", lambda: lang)
    voice = _FakeVoice()
    return CoachEngine(reader=_Reader(), voice=voice, laps_dir=tmp_path), voice


def _it_change():
    return ProposedChange(
        changes=(AtomicChange("aRBFront", None, -1),),
        rationale=("Hai sottosterzo in ingresso, quindi ammorbidisci la barra "
                   "antirollio anteriore di 1 click."),
        phase_label="Grip meccanico", tag="BOX",
        lever="Ammorbidisci la barra antirollio anteriore di 1 click")


def test_italian_announcement_is_two_phrases_prefix_then_lever(tmp_path, monkeypatch):
    from accoach.engineer import Decision, DecisionKind
    eng, voice = _engine(tmp_path, monkeypatch)
    change = _it_change()
    eng._announce_engineer(Decision(DecisionKind.PROPOSE, "msg", change, "high"))
    eng._announce_engineer(Decision(DecisionKind.REVERTED, "msg", change.reversed(), ""))
    eng.close()
    assert voice.said == [
        "Ingegnere, rientra ai box.",
        "Ammorbidisci la barra antirollio anteriore.",
        "Ingegnere, rientra ai box.",
        "Riporta l'assetto com'era.",
    ]


def test_a_missing_lever_drops_the_clicks_and_logs(tmp_path, monkeypatch):
    import accoach.engine as engine_mod
    from accoach.engineer import Decision, DecisionKind
    warned = []
    # Il logger dell'app puo' non propagare (logging_setup): si guarda il suo
    # metodo, non il root.
    monkeypatch.setattr(engine_mod._log, "warning",
                        lambda msg, *a: warned.append(msg % a))
    eng, voice = _engine(tmp_path, monkeypatch)
    change = ProposedChange(
        changes=(AtomicChange("aRBFront", None, +1),),
        rationale="x", phase_label="y", tag="BOX",
        lever="Irrigidisci la barra antirollio anteriore di 1 click")
    eng._announce_engineer(Decision(DecisionKind.PROPOSE, "msg", change, "high"))
    eng.close()
    assert voice.said == ["Ingegnere, rientra ai box.",
                          "Irrigidisci la barra antirollio anteriore."]
    assert any("aRBFront" in w for w in warned)
