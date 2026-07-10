"""One dark theme for the desktop shell, built from the HONE brand palette.

``brand.py`` is the single source of truth for the colours; this module turns
them into a Qt stylesheet (and finds the window icon) so the launcher/hub stops
hardcoding hex values inline. Widgets opt into variants with dynamic properties
(e.g. ``btn.setProperty("accent", True)``) or object names (``#sidebar``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import brand

# The brand display face (same as the overlay); Segoe UI is the Windows fallback.
_FONT = "Space Grotesk"


def _icon_path() -> Path | None:
    """Locate hone_icon.png from source or a frozen build.

    It's bundled under ``accoach/web`` (already in the PyInstaller ``datas``), so
    no new packaging entry is needed — we reuse the web asset.
    """
    base = getattr(sys, "_MEIPASS", None)
    candidates: list[Path] = []
    if base:
        candidates.append(Path(base) / "accoach" / "web" / "hone_icon.png")
    candidates.append(Path(__file__).resolve().parent / "web" / "hone_icon.png")
    for c in candidates:
        if c.is_file():
            return c
    return None


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
        font-family: "{_FONT}", "Segoe UI", sans-serif;
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

    /* --- type roles --- */
    QLabel[role="brand"]    {{ font-size: 22px; font-weight: bold; color: {b.TEXT}; }}
    QLabel[role="title"]    {{ font-size: 20px; font-weight: bold; color: {b.TEXT}; }}
    QLabel[role="headline"] {{ font-size: 17px; color: {b.TEXT}; }}
    QLabel[role="stat"]     {{ font-size: 22px; font-weight: bold; color: {b.TEXT};
                               font-variant-numeric: tabular-nums; }}
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
