"""HONE brand constants — the single source of truth for the product name,
voice and palette used across the (code-side) surfaces.

The Python package stays ``accoach`` (the repo codename) and the user data still
lives under ``~/Documents/ACCoach`` so existing laps aren't orphaned; only the
*product* the user sees is branded HONE.

Palette and fonts come from the brand plan (HONE_Brand_Marketing_Plan.docx). The
hex values are duplicated in the web CSS — keep them in sync if either changes.
"""

from __future__ import annotations

NAME = "HONE"
TAGLINE = "Know why you're slow."
SECONDARY = "Hone every lap."
DOMAIN = "honesim.com"

# Palette (hex). Ink/Slate/Line = surfaces; Cyan = brand; Delta green/red = the
# faster/slower delta; Amber = focus/advisory; text + muted for type.
INK = "#0B0E12"
SLATE = "#151A21"
LINE = "#232B35"
CYAN = "#22D3CE"
GREEN = "#34E08A"
RED = "#FF4D5E"
AMBER = "#FFB020"
TEXT = "#E8EDF2"
MUTED = "#8A95A3"
