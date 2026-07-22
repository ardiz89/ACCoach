"""Friendly corner names per track.

The coach detects corners geometrically (see :mod:`accoach.track`) and numbers
them T1, T2…  A driver, though, thinks in *names* — "you lost time at Tosa", not
"at corner 3". This module maps detected corners to real names.

Names are assigned by **apex position**, not by index, so the mapping is robust
to the detector finding a slightly different number of corners than the official
count: each detected corner takes the nearest curated name within a tolerance,
and anything unmatched falls back to ``Curva N``.

The curated positions are this sim's ``normalizedCarPosition`` (0..1 from the
start/finish line). They were anchored to a real recorded reference lap; once the
track map exists they can be refined visually. Unknown tracks just get T-numbers.
"""

from __future__ import annotations

import re

# Max distance (in normalized position) between a detected apex and a curated
# apex for the name to apply.
_NAME_TOL = 0.05


def _slug(text: str) -> str:
    text = (text or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


# track-slug -> ordered list of (name, approx apex pos). Anchored to a real
# Imola reference lap (BMW M4 GT3, 1:43.7) whose detected apexes were
# 0.143 / 0.291 / 0.351 / 0.484 / 0.585 / 0.693 / 0.844 — matched here to the
# known Imola corner sequence.
_CORNERS: dict[str, list[tuple[str, float]]] = {
    "imola": [
        ("Tamburello", 0.143),       # 1st chicane after the straight
        ("Villeneuve", 0.291),       # 2nd chicane
        ("Tosa", 0.351),             # left hairpin
        ("Piratella", 0.484),        # left, uphill
        ("Acque Minerali", 0.585),   # right-left, downhill
        ("Variante Alta", 0.693),    # chicane
        ("Rivazza", 0.844),          # double left before the line
    ],
    # Anchored the same way, to a real Monza lap (Ferrari 488 GT3 Evo, 2:03.7)
    # whose detected apexes were 0.169 / 0.247 / 0.378 / 0.447 / 0.500 / 0.686 /
    # 0.888. The minimum speeds identify them beyond doubt: 49 km/h at the first
    # chicane, 205 through Curva Grande, 119 in the Parabolica.
    "monza": [
        ("Variante del Rettifilo", 0.169),   # 1st chicane, slowest point of the lap
        ("Curva Grande", 0.247),             # long right, taken near flat
        ("Variante della Roggia", 0.378),    # 2nd chicane
        ("Lesmo 1", 0.447),
        ("Lesmo 2", 0.500),
        ("Variante Ascari", 0.686),          # triple, detected as one corner
        ("Parabolica", 0.888),               # onto the main straight
    ],
}


def corner_name(track: str, index: int, apex_pos: float, lang: str | None = None) -> str:
    """Name for a detected corner, by nearest curated apex, else ``Corner N`` /
    ``Curva N`` per language (curated names are proper nouns, kept as-is)."""
    table = _CORNERS.get(_slug(track))
    if table:
        name, pos = min(table, key=lambda t: abs(t[1] - apex_pos))
        if abs(pos - apex_pos) <= _NAME_TOL:
            return name
    from .i18n import current_language
    word = "Curva" if (lang or current_language()) == "it" else "Corner"
    return f"{word} {index + 1}"


def name_corners(track: str, corners, lang: str | None = None) -> list[str]:
    """Names for a list of detected corners (objects with ``index``/``apex_pos``)."""
    return [corner_name(track, c.index, c.apex_pos, lang) for c in corners]


def has_names(track: str) -> bool:
    return _slug(track) in _CORNERS
