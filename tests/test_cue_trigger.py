"""Le parole-innesco: quello che il coach dice in pista quando c'e' un focus.

Tre coach professionisti indipendenti usano lo stesso strumento e lo stesso nome
(«trigger words»), per un motivo dichiarato: la banda passante del pilota che guida
e' finita. Una-tre parole, sempre le stesse.

Il test sulle due lingue non e' pedanteria: l'audit del 2026-08-08 ha trovato due
messaggi che escono in italiano quando l'interfaccia e' in inglese.
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
