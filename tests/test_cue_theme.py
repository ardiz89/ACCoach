"""A category's theme: an English key for comparisons, a label for the driver.

The completeness test exists because this project has already been bitten by this
family of bug: a category with a title, a chart and a drill, and no producer. A
technique category with no theme would never be spoken while a focus is active,
and the defect would be invisible.
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
    # Unknown language: falls back to English, doesn't blow up.
    assert theme_label(CueCategory.BRAKE_LATER, "de") == "braking"


def test_every_technique_category_has_an_explicit_theme():
    """Fails when a technique category is added without giving it a theme."""
    missing = [
        c.name for c in CueCategory
        if tier_of(c) == CueTier.TECHNIQUE
        and c is not CueCategory.GOOD          # praise has no theme: see Task 3
        and c not in THEME
    ]
    assert not missing, f"categorie di tecnica senza tema in THEME: {missing}"


def test_every_theme_entry_has_both_languages():
    for cat, entry in THEME.items():
        assert entry.get("it"), f"{cat.name}: manca l'italiano"
        assert entry.get("en"), f"{cat.name}: manca l'inglese"


def test_no_safety_category_sits_in_the_technique_tier():
    """The premise the plan's deviation from the spec rests on.

    The spec listed the categories that always speak; the plan replaced that
    list with a rule — only TECHNIQUE cues are filtered — on the grounds that
    the two say the same thing. True today, and nothing enforces it: `tier_of`
    sends any unlisted category to TECHNIQUE ("the safe middle"), and that
    default has just picked up a second meaning, "silenceable by the focus". A
    safety category added tomorrow to `_SAFETY_CATEGORIES` but not to `_TIER`
    would pass the quiet gate and then be swallowed by the focus gate.
    """
    from accoach.engine import _SAFETY_CATEGORIES

    silenceable = {c for c in _SAFETY_CATEGORIES if tier_of(c) == CueTier.TECHNIQUE}
    assert not silenceable, (
        "categorie di sicurezza che il filtro del focus può zittire: "
        f"{sorted(c.name for c in silenceable)}"
    )
