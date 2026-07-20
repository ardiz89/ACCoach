"""The setup editor speaks the language the page asked for.

The bug these cover: the param labels were authored in Italian with no translation
at all, while HONE ships with English as its default language — so the engineer's
main screen greeted an English user half in Italian. The second half of the bug was
subtler: the strings that *were* translatable resolved against ``config.language``
(the desktop's setting), not the language of the web request, so a browser set to
English still got Italian next to English chrome.

Nothing tested the language of these endpoints, which is exactly why it survived.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from accoach.setup import labels
from accoach.setup.acc_format import SETUP_PARAMS, slot_labels
from accoach.setup.ac_format import AC_PARAMS


def _display_strings():
    out = set()
    for spec in list(AC_PARAMS) + list(SETUP_PARAMS):
        out.add(spec.group)
        out.add(spec.label)
        if getattr(spec, "note", ""):
            out.add(spec.note)
    return out


def test_every_display_string_has_an_italian_translation():
    # A missing entry doesn't crash — it falls through as English. That silence is
    # the whole failure mode, so the catalogue has to be checked, not trusted.
    missing = sorted(s for s in _display_strings() if s not in labels._IT)
    assert not missing, f"no Italian for: {missing}"


def test_catalogue_has_no_dead_entries():
    # The reverse drift: a label gets reworded and its entry silently stops
    # matching, which reads exactly like a missing translation.
    used = _display_strings() | set(slot_labels(4)) | set(slot_labels(2))
    dead = sorted(k for k in labels._IT if k not in used)
    assert not dead, f"catalogue entries nothing uses: {dead}"


def test_specs_are_authored_in_english():
    # English is canonical here, matching engineer/profiles/_common.py.
    italian = {"Gomme", "Pressione", "Convergenza", "Ala posteriore", "Barra ant.",
               "Meccanica", "Elettronica", "Ammortizzatori", "Benzina"}
    assert not (_display_strings() & italian)


@pytest.mark.parametrize("text, it", [
    ("Tyres", "Gomme"),
    ("Pressure", "Pressione"),
    ("Toe", "Convergenza"),
    ("Slow rebound", "Estensione lenta"),
])
def test_tr_translates_on_request_language(text, it):
    assert labels.tr(text, "en") == text
    assert labels.tr(text, "it") == it


@pytest.mark.parametrize("slot", ["FL", "FR", "RL", "RR", "F", "R"])
def test_wheel_slots_are_the_same_in_every_language(slot):
    # FL/FR/RL/RR stay put: the live tyre panel shows them untranslated, so the
    # editor next to it must match, and it's the sim-racing convention anyway.
    assert labels.tr(slot, "it") == slot
    assert labels.tr(slot, "en") == slot


def test_unknown_string_passes_through_rather_than_blanking():
    assert labels.tr("Nurburgring downforce widget", "it") == "Nurburgring downforce widget"
    assert labels.tr("", "it") == ""


def test_request_language_beats_the_desktop_config(monkeypatch):
    """The heart of the mixed-language bug.

    With the desktop set to Italian, a browser asking for English must get English.
    Before, tr() read config.language and ignored the request entirely.
    """
    monkeypatch.setattr(labels, "current_language", lambda: "it")
    assert labels.tr("Pressure", "en") == "Pressure"      # request wins
    assert labels.tr("Pressure", None) == "Pressione"     # no request → config


def test_reload_hint_is_localised_and_names_the_setup():
    en = labels.reload_hint("quali_q1", "en")
    it = labels.reload_hint("quali_q1", "it")
    assert "quali_q1" in en and "quali_q1" in it
    assert "pits" in en.lower()
    assert "box" in it.lower()
    assert en != it


def test_errors_are_localised_and_keep_the_param_key():
    for lang in ("en", "it"):
        assert "tyrePressure" in labels.err_slot_required("tyrePressure", ("FL",), lang)
        assert "tyrePressure" in labels.err_slot_invalid("XX", "tyrePressure", lang)
        assert "tyrePressure" in labels.err_slot_out_of_range(9, "tyrePressure", lang)
        assert "rearWing" in labels.err_needs_value("rearWing", lang)
    assert labels.err_slot_required("k", ("FL",), "en") != \
        labels.err_slot_required("k", ("FL",), "it")


def test_old_italian_slot_spelling_still_resolves():
    # The canonical slot labels went Italian → English. The CLI takes them by hand,
    # so the spelling that used to work must not start erroring out.
    assert labels.canonical_slot("Post-Dx") == "RR"
    assert labels.canonical_slot("Ant-Sx") == "FL"
    assert labels.canonical_slot("RR") == "RR"          # canonical passes through
    assert labels.canonical_slot("nonsense") == "nonsense"
