"""Trigger words: what the coach says on track while a focus is active.

Three independent professional coaches use the same tool and the same name
("trigger words"), for a stated reason: the bandwidth of a driver who is driving
is finite. One to three words, always the same ones.

The two-language test isn't pedantry: the 2026-08-08 audit found two messages that
come out in Italian when the interface is set to English.
"""
from accoach.coaching.cue import (
    TRIGGER, CueCategory, CueTier, tier_of, trigger_text,
)


def test_trigger_is_one_to_three_words():
    for cat, entry in TRIGGER.items():
        for lang, phrase in entry.items():
            n = len(phrase.split())
            assert 1 <= n <= 3, f"{cat.name}/{lang}: {n} parole in {phrase!r}"


def test_every_technique_category_has_a_trigger_in_both_languages():
    missing = [
        c.name for c in CueCategory
        if tier_of(c) == CueTier.TECHNIQUE
        and c is not CueCategory.GOOD
        and not (TRIGGER.get(c, {}).get("it") and TRIGGER.get(c, {}).get("en"))
    ]
    assert not missing, f"categorie di tecnica senza innesco in due lingue: {missing}"


def test_trigger_text_returns_none_outside_technique():
    assert trigger_text(CueCategory.LOCKED, "it") is None
    assert trigger_text(CueCategory.TYRE_PRESSURE, "it") is None
    assert trigger_text(CueCategory.GOOD, "it") is None


def test_trigger_text_falls_back_to_english():
    assert trigger_text(CueCategory.MORE_THROTTLE, "it") == "gas"
    assert trigger_text(CueCategory.MORE_THROTTLE, "en") == "throttle"
    assert trigger_text(CueCategory.MORE_THROTTLE, "de") == "throttle"
