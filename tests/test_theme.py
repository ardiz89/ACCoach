"""Theme: the brand faces ship with the app and reach the widgets that need them.

These guard a failure that is *silent by construction*: naming a family Qt hasn't
got just falls back to a system face, so the app keeps working and merely stops
looking like itself. That's how the three brand faces went unrendered for weeks —
they were named everywhere and installed nowhere. A test is the only thing that
notices.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from accoach import theme


def test_every_declared_font_file_is_present():
    # If a file goes missing from web/fonts the app still runs — it just quietly
    # renders in Segoe UI. Fail loudly here instead.
    fonts = theme._web_dir() / "fonts"
    missing = [n for n in theme._FONT_FILES if not (fonts / n).is_file()]
    assert not missing, f"brand fonts missing from the bundle: {missing}"


def test_licences_ship_next_to_the_fonts():
    # All three faces are OFL; redistribution requires the licence to travel with
    # them, and they're only redistributable because it does.
    fonts = theme._web_dir() / "fonts"
    for name in ("OFL-SpaceGrotesk.txt", "OFL-Inter.txt", "OFL-JetBrainsMono.txt"):
        assert (fonts / name).is_file(), f"missing licence: {name}"


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def test_load_fonts_registers_all_three(qt_app):
    families = theme.load_fonts()
    assert set(families) == {theme.DISPLAY, theme.UI, theme.MONO}


def test_load_fonts_is_idempotent(qt_app):
    first = theme.load_fonts()
    assert theme.load_fonts() == first


@pytest.mark.parametrize("role, expected", [
    ("brand", theme.DISPLAY),
    ("title", theme.DISPLAY),
    ("headline", theme.DISPLAY),
    ("stat", theme.MONO),
])
def test_type_roles_resolve_to_their_brand_face(qt_app, role, expected):
    from PySide6.QtGui import QFontInfo
    from PySide6.QtWidgets import QLabel

    theme.load_fonts()
    qt_app.setStyleSheet(theme.qss())
    lbl = QLabel("1:40.000")
    lbl.setProperty("role", role)
    lbl.ensurePolished()
    assert QFontInfo(lbl.font()).family() == expected


def test_lap_times_use_a_face_whose_digits_are_all_one_width(qt_app):
    """The 'stat' role holds times that refresh in place.

    Not a style preference: Space Grotesk's '0' is ~1.5x the width of its '1', so a
    proportional face makes a centred time jump sideways as it updates. Qt gives no
    stylesheet route to tabular figures (it ignores font-variant-numeric), so the
    mono face IS the mechanism — this asserts the property, not the font name.
    """
    from PySide6.QtGui import QFontMetricsF
    from PySide6.QtWidgets import QLabel

    theme.load_fonts()
    qt_app.setStyleSheet(theme.qss())
    lbl = QLabel("1:40.000")
    lbl.setProperty("role", "stat")
    lbl.ensurePolished()
    fm = QFontMetricsF(lbl.font())
    widths = {round(fm.horizontalAdvance(d * 4), 2) for d in "0123456789"}
    assert len(widths) == 1, f"digits are not tabular: {sorted(widths)}"
