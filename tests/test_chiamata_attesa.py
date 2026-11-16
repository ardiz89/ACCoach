"""La chiamata ai box quando l'Ingegnere aspetta la risposta sull'assetto.

Rilettura R2-3 (09/11): le gomme smentiscono la modifica, l'Ingegnere tiene
la prova ferma con `confirm_base` finche' il pilota non dice ai box quale
assetto ha caricato. Ma a voce si dicono solo le decisioni con una modifica,
e quell'attesa non ne porta: chi guida senza tastiera poteva fare uno stint
intero senza sapere che l'Ingegnere aspettava lui. Ora lo chiama, due volte
al massimo e solo in pista, passando dallo scheduler come le altre chiamate.
"""

from accoach.coaching.cue import CueCategory
from accoach.coaching.pitcall import _HOLD, HoldCall
from accoach.coaching.spoken import spoken_phrases
from accoach.engine import CoachEngine
from accoach.engineer import Decision, DecisionKind
from accoach.i18n import cue_text

import synth

_ON_TRACK = synth.snap(pos=0.5, speed_kmh=180.0)
_IN_LANE = synth.snap(pos=0.98, speed_kmh=60.0, in_pit_lane=True)
_IN_BOX = synth.snap(pos=0.98, speed_kmh=0.0, in_pit_lane=True)


def _said(cues):
    return [c for c in cues if c.message == _HOLD]


# --- la frase ----------------------------------------------------------------

def test_the_phrase_is_in_the_catalogue_and_short():
    assert _HOLD == "Rientra ai box, scegli l'assetto."
    assert _HOLD in spoken_phrases()
    assert len(_HOLD.split()) <= 8


def test_the_phrase_has_its_english():
    assert cue_text(_HOLD, "en") != _HOLD


# --- HoldCall da solo --------------------------------------------------------

def test_spoken_when_the_hold_starts():
    h = HoldCall()
    out = h.update(_ON_TRACK, True)
    assert len(_said(out)) == 1
    assert out[0].category is CueCategory.PIT_IN
    assert h.update(_ON_TRACK, True) == []          # non a ogni frame


def test_once_more_at_the_next_line_then_never_again():
    h = HoldCall()
    h.update(_ON_TRACK, True)
    h.new_lap()
    assert len(_said(h.update(_ON_TRACK, True))) == 1
    for _ in range(3):
        h.new_lap()
        assert h.update(_ON_TRACK, True) == []      # niente terza volta


def test_nothing_once_the_answer_releases_the_hold():
    h = HoldCall()
    h.update(_ON_TRACK, True)
    assert h.update(_ON_TRACK, False) == []         # la risposta
    h.new_lap()
    assert h.update(_ON_TRACK, False) == []


def test_a_new_hold_is_called_again():
    h = HoldCall()
    h.update(_ON_TRACK, True)
    h.new_lap()
    h.update(_ON_TRACK, True)
    h.update(_ON_TRACK, False)
    assert len(_said(h.update(_ON_TRACK, True))) == 1


def test_not_in_the_pit_lane_nor_stopped_in_the_box():
    h = HoldCall()
    assert h.update(_IN_BOX, True) == []
    assert h.update(_IN_LANE, True) == []
    assert h.update(_ON_TRACK, True) == []          # la prima e' passata ai box
    h.new_lap()
    assert len(_said(h.update(_ON_TRACK, True))) == 1


def test_the_reminder_is_not_said_in_the_pit_and_not_saved_for_later():
    h = HoldCall()
    h.update(_ON_TRACK, True)
    h.new_lap()
    assert h.update(_IN_LANE, True) == []
    h.new_lap()
    assert h.update(_ON_TRACK, True) == []          # due volte al massimo


# --- nel motore, dallo scheduler ---------------------------------------------

class _Reader:
    def __init__(self):
        self.frame = _ON_TRACK

    def read(self):
        return self.frame

    def close(self):
        pass


def _held():
    return Decision(DecisionKind.STAND_DOWN, "Le gomme non tornano.",
                    confirm_base=True)


def _engine(tmp_path, **kw):
    reader = _Reader()
    eng = CoachEngine(reader=reader, voice=None, laps_dir=tmp_path, **kw)
    eng.tick(0.0)                     # auto e pista nuove: l'Ingegnere nasce qui
    return eng, reader


def _spoken(eng, reader, frames, t0):
    out = []
    for i, f in enumerate(frames):
        reader.frame = f
        st = eng.tick(t0 + i * 0.5)
        # Lo schermo la mostra nella lingua attiva: si confronta tradotta.
        if st.spoken is not None and st.spoken.message == cue_text(_HOLD):
            out.append(st.spoken)
    return out


def _lap_line(t):
    """Un traguardo passato in pista: armato a meta' giro, poi il salto."""
    return [synth.snap(pos=0.5, speed_kmh=180.0),
            synth.snap(pos=0.95, speed_kmh=180.0),
            synth.snap(pos=0.02, speed_kmh=180.0)] + [
        synth.snap(pos=0.05 + 0.01 * k, speed_kmh=180.0) for k in range(12)]


def test_engine_calls_in_through_the_scheduler(tmp_path):
    eng, reader = _engine(tmp_path)
    try:
        eng._engineer_decision = _held()
        said = _spoken(eng, reader, [_ON_TRACK] * 10, 1.0)
        assert len(said) == 1 and said[0].category is CueCategory.PIT_IN
        # Il traguardo dopo: una volta ancora.
        said = _spoken(eng, reader, _lap_line(0), 20.0)
        assert len(said) == 1
        # Il traguardo dopo ancora: niente.
        said = _spoken(eng, reader, _lap_line(0) + _lap_line(0), 40.0)
        assert said == []
    finally:
        eng.close()


def test_engine_is_silent_after_the_answer(tmp_path):
    eng, reader = _engine(tmp_path)
    try:
        eng._engineer_decision = _held()
        assert len(_spoken(eng, reader, [_ON_TRACK] * 10, 1.0)) == 1
        eng._engineer_decision = Decision(DecisionKind.COLLECT, "Riparto.")
        assert _spoken(eng, reader, _lap_line(0) + _lap_line(0), 20.0) == []
    finally:
        eng.close()


def test_engine_is_silent_in_the_box(tmp_path):
    eng, reader = _engine(tmp_path)
    try:
        eng._engineer_decision = _held()
        assert _spoken(eng, reader, [_IN_BOX] * 20, 1.0) == []
    finally:
        eng.close()


def test_engine_respects_the_engineer_voice_switch(tmp_path):
    eng, reader = _engine(tmp_path, engineer_voice=False)
    try:
        eng._engineer_decision = _held()
        assert _spoken(eng, reader, [_ON_TRACK] * 10 + _lap_line(0), 1.0) == []
    finally:
        eng.close()
