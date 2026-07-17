"""One dark theme for the desktop shell, built from the HONE brand palette.

``brand.py`` is the single source of truth for the colours; this module turns
them into a Qt stylesheet (and finds the window icon) so the launcher/hub stops
hardcoding hex values inline. Widgets opt into variants with dynamic properties
(e.g. ``btn.setProperty("accent", True)``) or object names (``#sidebar``).

**Fonts must be loaded before the stylesheet means anything.** Naming a family in
QSS only picks it if the system has it installed, and HONE is deliberately offline
— no CDN to fall back on. So the three brand faces ship with the app (see
``web/fonts``, OFL, redistributable) and :func:`load_fonts` registers them with Qt.
Call it once after the ``QApplication`` exists, in every process that draws UI —
the hub, the overlay and the terminal apps each have their own.

The three faces carry different jobs, per the brand plan:

* **Space Grotesk** — display only: the wordmark, section titles, headlines.
* **Inter** — the UI body face: buttons, labels, inputs.
* **JetBrains Mono** — numbers meant to be *read in a column* (lap times, deltas).
  Its digits are all one width, so a time doesn't jitter as it updates. This is
  the only reliable way to get that in Qt: QSS silently ignores
  ``font-variant-numeric: tabular-nums`` (measured — Qt supports a subset of CSS),
  and while Space Grotesk and Inter both *have* a ``tnum`` feature, reaching it
  needs per-widget ``QFont.setFeature`` rather than a stylesheet rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import brand

# The brand faces. Each falls back to a system face if its file ever goes missing
# from the bundle, so a packaging slip degrades the look instead of the layout.
DISPLAY = "Space Grotesk"       # wordmark, titles, headlines
UI = "Inter"                    # body text, buttons, inputs
MONO = "JetBrains Mono"         # lap times, deltas, anything read in a column

_DISPLAY_STACK = f'"{DISPLAY}", "Segoe UI", sans-serif'
_UI_STACK = f'"{UI}", "Segoe UI", sans-serif'
_MONO_STACK = f'"{MONO}", "Cascadia Mono", Consolas, monospace'

_FONT_FILES = (
    "SpaceGrotesk-Regular.ttf", "SpaceGrotesk-Bold.ttf",
    "Inter-Regular.ttf", "Inter-Bold.ttf",
    "JetBrainsMono-Regular.ttf", "JetBrainsMono-Bold.ttf",
)

_fonts_loaded = False


def _web_dir() -> Path:
    """The bundled ``accoach/web`` asset directory, from source or a frozen build.

    It's already in the PyInstaller ``datas`` (whole-directory), so assets placed
    under it — the icon, the fonts — need no new packaging entry.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        frozen = Path(base) / "accoach" / "web"
        if frozen.is_dir():
            return frozen
    return Path(__file__).resolve().parent / "web"


def _icon_path() -> Path | None:
    """Locate hone_icon.png from source or a frozen build."""
    p = _web_dir() / "hone_icon.png"
    return p if p.is_file() else None


def load_fonts() -> list[str]:
    """Register the bundled brand faces with Qt; return the families now available.

    Idempotent and non-fatal: a missing file is skipped, and the stylesheet's
    fallbacks cover it. Needs a live ``QApplication``.
    """
    global _fonts_loaded
    from PySide6.QtGui import QFontDatabase

    if _fonts_loaded:
        return sorted({DISPLAY, UI, MONO} & set(QFontDatabase.families()))

    fonts = _web_dir() / "fonts"
    for name in _FONT_FILES:
        p = fonts / name
        if p.is_file():
            QFontDatabase.addApplicationFont(str(p))
    _fonts_loaded = True
    return sorted({DISPLAY, UI, MONO} & set(QFontDatabase.families()))


def window_icon():
    """A ``QIcon`` for the app window (empty icon if the asset is missing)."""
    from PySide6.QtGui import QIcon

    p = _icon_path()
    return QIcon(str(p)) if p else QIcon()


def qss() -> str:
    """The application stylesheet, composed from the brand palette."""
    b = brand
    return f"""
    * {{
        font-family: {_UI_STACK};
    }}
    QWidget {{
        background: {b.INK};
        color: {b.TEXT};
        font-size: 14px;
    }}
    QToolTip {{
        background: {b.SLATE};
        color: {b.TEXT};
        border: 1px solid {b.LINE};
    }}

    /* --- sidebar navigation --- */
    QListWidget#sidebar {{
        background: {b.SLATE};
        border: none;
        border-right: 1px solid {b.LINE};
        outline: 0;
        padding: 8px 6px;
    }}
    QListWidget#sidebar::item {{
        padding: 10px 12px;
        margin: 2px 0;
        border-radius: 8px;
        color: {b.MUTED};
    }}
    QListWidget#sidebar::item:selected {{
        background: {b.LINE};
        color: {b.TEXT};
    }}
    QListWidget#sidebar::item:hover:!selected {{
        color: {b.TEXT};
    }}

    /* --- type roles ---
       Display face for the things you read as a headline, mono for the things you
       read as a number. "stat" holds lap times and gaps that refresh in place, so
       it takes the mono face: proportional digits would shift the text sideways
       on every update (in Space Grotesk a '0' is half again as wide as a '1'). */
    QLabel[role="brand"]    {{ font-family: {_DISPLAY_STACK};
                               font-size: 22px; font-weight: bold; color: {b.TEXT}; }}
    QLabel[role="title"]    {{ font-family: {_DISPLAY_STACK};
                               font-size: 20px; font-weight: bold; color: {b.TEXT}; }}
    QLabel[role="headline"] {{ font-family: {_DISPLAY_STACK};
                               font-size: 17px; color: {b.TEXT}; }}
    QLabel[role="stat"]     {{ font-family: {_MONO_STACK};
                               font-size: 22px; font-weight: bold; color: {b.TEXT}; }}
    QLabel[role="muted"]    {{ color: {b.MUTED}; font-size: 12px; }}
    QLabel[role="good"]     {{ color: {b.GREEN}; }}
    QLabel[role="bad"]      {{ color: {b.RED}; }}
    QLabel[role="link"]     {{ color: {b.CYAN}; font-size: 11px; }}

    /* --- cards --- */
    QFrame[role="card"] {{
        background: {b.SLATE};
        border: 1px solid {b.LINE};
        border-radius: 12px;
    }}
    QFrame[role="hline"] {{ border: none; border-top: 1px solid {b.LINE}; }}

    /* --- buttons --- */
    QPushButton {{
        background: {b.SLATE};
        color: {b.TEXT};
        border: 1px solid {b.LINE};
        border-radius: 8px;
        padding: 9px 14px;
        text-align: left;
    }}
    QPushButton:hover {{ border-color: {b.CYAN}; }}
    QPushButton:disabled {{ color: {b.MUTED}; border-color: {b.LINE}; }}
    QPushButton[accent="true"] {{
        background: {b.CYAN};
        color: {b.INK};
        border: none;
        font-weight: bold;
    }}
    QPushButton[accent="true"]:hover {{ background: {b.GREEN}; }}
    QPushButton[accent="true"]:disabled {{ background: {b.LINE}; color: {b.MUTED}; }}
    QPushButton[danger="true"] {{ border-color: {b.RED}; color: {b.RED}; }}

    /* --- inputs --- */
    QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {b.SLATE};
        border: 1px solid {b.LINE};
        border-radius: 6px;
        padding: 5px 8px;
        min-height: 20px;
    }}
    QComboBox QAbstractItemView {{
        background: {b.SLATE};
        border: 1px solid {b.LINE};
        selection-background-color: {b.LINE};
    }}
    QCheckBox {{ spacing: 8px; }}
    """
