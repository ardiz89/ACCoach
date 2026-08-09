"""Il tema attivo arriva allo scheduler dal FocusCoach, come chiave inglese.

`Focus.theme` e' la stringa tradotta ("frenata"): usarla per il confronto
funzionerebbe in italiano e romperebbe il filtro in inglese. Questo test esiste per
inchiodare quel punto.

I due test in fondo coprono un buco trovato in revisione: il tema e' per
combinazione auto/pista, e deve essere scordato al cambio (o resterebbe
appiccicato, magari per l'intera sessione successiva) ma non a ogni giro sulla
STESSA combinazione, dove `_rebuild_reference` gira di nuovo per rincorrere il
nuovo miglior tempo appena impostato da `_observe_lap`.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import Focus, FocusKind, FocusReport
from accoach.engine import CoachEngine, _focus_theme_key

import synth


class _StubReader:
    """Replays a fixed list of snapshots, holding the last one once exhausted."""

    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


def _focus(category, theme):
    return Focus(corner_index=3, name="Curva 4", theme=theme, category=category,
                 baseline_ms=300.0, drill="")


def test_active_focus_yields_the_english_key():
    rep = FocusReport(kind=FocusKind.DRILL,
                      message="",
                      focus=_focus(CueCategory.LESS_BRAKE, "frenata"))
    assert _focus_theme_key(rep) == "braking"


def test_the_translated_label_is_not_used():
    """Anche con l'etichetta in italiano, la chiave resta inglese."""
    rep = FocusReport(kind=FocusKind.DRILL,
                      message="",
                      focus=_focus(CueCategory.MORE_THROTTLE, "trazione"))
    assert _focus_theme_key(rep) == "traction"


def test_no_focus_yields_none():
    assert _focus_theme_key(None) is None
    assert _focus_theme_key(FocusReport(kind=FocusKind.ASSESS, message="")) is None
    assert _focus_theme_key(FocusReport(kind=FocusKind.CLEAN, message="")) is None


# --- the theme belongs to a car/track, not to the session ------------------

def test_car_switch_clears_the_leftover_focus_theme(tmp_path):
    """Un tema di focus e' di una combinazione auto/pista sola: al cambio va
    scordato, o il filtro continuerebbe a scartare consigli su un tema che non
    c'entra piu' niente — anche per l'intera sessione successiva, se quella
    combinazione non accumula mai un riferimento da cui nascere un focus."""
    frames = [
        synth.snap(pos=0.1, car_model="ferrari_488_gt3", track="monza"),
        synth.snap(pos=0.1, car_model="porsche_992_gt3", track="spa"),
    ]
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    eng.tick(0.0)                          # connects to car A / track A
    eng.scheduler.set_focus("braking")     # simulate a focus elected there
    eng.tick(0.0)                          # switches to car B / track B
    assert eng.scheduler.focus_theme is None
    eng.close()


def test_same_car_track_rebuild_does_not_clear_the_focus_theme(tmp_path):
    """`_rebuild_reference` also runs mid-session on the SAME car/track, right
    after `_observe_lap`, to chase a lap that just became the new best
    (engine.py's "chase the new best" call). That path must leave the theme
    alone, or it would erase the very theme `_observe_lap` just set."""
    frames = [synth.snap(pos=0.1)]
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    eng.tick(0.0)                          # connects, establishes eng._key
    eng.scheduler.set_focus("braking")
    eng._rebuild_reference(*eng._key)      # same combination: the mid-lap path
    assert eng.scheduler.focus_theme == "braking"
    eng.close()
