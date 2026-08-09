"""Il tema attivo arriva allo scheduler dal FocusCoach, come chiave inglese.

`Focus.theme` e' la stringa tradotta ("frenata"): usarla per il confronto
funzionerebbe in italiano e romperebbe il filtro in inglese. Questo test esiste per
inchiodare quel punto.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import Focus, FocusKind, FocusReport
from accoach.engine import _focus_theme_key


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
