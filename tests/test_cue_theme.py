"""Il tema di una categoria: chiave inglese per i confronti, etichetta per il pilota.

Il test di completezza esiste perche' questo progetto ha gia' preso questa famiglia
di difetti: una categoria con titolo, grafico ed esercizio e nessun produttore. Una
categoria di tecnica senza tema non verrebbe mai pronunciata con un focus attivo, e
il difetto sarebbe invisibile.
"""
from accoach.coaching.cue import (
    THEME, CueCategory, CueTier, theme_key, theme_label, tier_of,
)


def test_theme_key_is_english_regardless_of_language():
    assert theme_key(CueCategory.BRAKE_LATER) == "braking"
    assert theme_key(CueCategory.MORE_THROTTLE) == "traction"
    assert theme_key(CueCategory.CARRY_SPEED) == "cornering"
    assert theme_key(CueCategory.TIME_LOSS) == "line"


def test_theme_label_is_translated():
    assert theme_label(CueCategory.BRAKE_LATER, "it") == "frenata"
    assert theme_label(CueCategory.BRAKE_LATER, "en") == "braking"
    # Lingua sconosciuta: si ripiega sull'inglese, non si esplode.
    assert theme_label(CueCategory.BRAKE_LATER, "de") == "braking"


def test_every_technique_category_has_an_explicit_theme():
    """Fallisce quando si aggiunge una categoria di tecnica senza darle un tema."""
    missing = [
        c.name for c in CueCategory
        if tier_of(c) == CueTier.TECHNIQUE
        and c is not CueCategory.GOOD          # la lode non ha tema: vedi Task 3
        and c not in THEME
    ]
    assert not missing, f"categorie di tecnica senza tema in THEME: {missing}"


def test_every_theme_entry_has_both_languages():
    for cat, entry in THEME.items():
        assert entry.get("it"), f"{cat.name}: manca l'italiano"
        assert entry.get("en"), f"{cat.name}: manca l'inglese"
