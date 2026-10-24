"""Ogni impostazione spiega sé stessa.

Segnalato dall'utente: «un utente potrebbe non sapere cos'è "overlay scale" o
"reading speed"». Il pannello non aveva un solo testo d'aiuto, in nessuna lingua.

Un tooltip da solo non basta — se non c'è niente di visibile su cui passare
sopra, nessuno ci passa sopra. Da qui il "?" accanto a ogni campo.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from accoach.i18n import t                                   # noqa: E402

_SETTINGS = ("set.voice", "set.engineer_voice", "set.male_voice",
             "set.radio", "set.rate", "set.scale", "set.wean", "set.pedals",
             "set.autorecord")


@pytest.mark.parametrize("key", _SETTINGS)
@pytest.mark.parametrize("lang", ("en", "it"))
def test_every_setting_has_help_in_both_languages(key, lang):
    help_text = t(f"{key}.help", lang=lang)
    assert help_text != f"{key}.help", f"manca l'aiuto per {key} in {lang}"
    assert len(help_text) > 40, "una definizione di tre parole non aiuta nessuno"


@pytest.mark.parametrize("key", _SETTINGS)
def test_the_help_does_not_merely_repeat_the_label(key):
    """«Scala overlay: scala l'overlay» è rumore con l'aria di documentazione."""
    label = t(key, lang="it").lower()
    assert t(f"{key}.help", lang="it").lower() != label


def test_the_help_marks_are_wired_to_the_tooltips():
    """Il "?" deve portare il testo giusto, non uno qualunque."""
    from PySide6.QtWidgets import QApplication
    from accoach.launcher import SettingsPanel

    QApplication.instance() or QApplication([])

    class _Hub:
        def action_button(self, *a, **k):
            from PySide6.QtWidgets import QPushButton
            return QPushButton()
        special_button = action_button

        def _show_wizard(self):
            pass

    panel = SettingsPanel(_Hub())
    assert set(panel._helps) == set(_SETTINGS)
    for key, mark in panel._helps.items():
        assert mark.text() == "?"
        assert mark.toolTip() == t(f"{key}.help")


def test_the_voice_is_a_choice_between_two_and_is_saved(tmp_path, monkeypatch):
    """«Voce maschile» spenta non diceva quale voce restava (24/10): ora si
    sceglie fra Maschile e Femminile, e la scelta finisce in `voice.male`."""
    from PySide6.QtWidgets import QApplication, QComboBox
    from accoach import config, launcher

    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    app = QApplication.instance() or QApplication([])  # noqa: F841
    win = launcher.MainWindow()
    try:
        s = win._settings
        assert isinstance(s._male, QComboBox) and s._male.count() == 2
        s._male.setCurrentIndex(1)
        s._do_save()
        assert config.load_config(reload=True).voice.male is False
        assert s._rate.suffix().strip()            # l'unità accanto al numero
    finally:
        win.close()
