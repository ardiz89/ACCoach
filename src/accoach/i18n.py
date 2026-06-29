"""Lightweight internationalisation — language state + spoken-cue translation.

The app is bilingual (English / Italian). English is the canonical interface
language; the neural coach **voice** is Italian (pre-rendered WAVs keyed by the
Italian cue phrases). The live coaching cues are authored in Italian in the
detectors (so the Italian WAVs match verbatim); for an English session this
module translates each cue phrase to English at the boundary — the spoken text
(via SAPI5) and the on-screen cue both become English, while the Italian neural
pipeline is left untouched.

This is the foundation for a full UI language switch; later phases move the rest
of the on-screen text (debrief, engineer, focus, …) into a keyed catalogue.
"""

from __future__ import annotations

import re

LANGUAGES = ("en", "it")
DEFAULT_LANGUAGE = "en"

_NAMES = {"en": "English", "it": "Italiano"}


def language_name(lang: str) -> str:
    return _NAMES.get(lang, lang)


def current_language() -> str:
    """The active app language, from config (falls back to the default)."""
    try:
        from .config import load_config
        lang = load_config().language
    except Exception:  # pragma: no cover - config must never break coaching
        return DEFAULT_LANGUAGE
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


# --- spoken/displayed coaching cues: Italian (canonical) -> English ----------
# Keys MUST match the exact strings the detectors emit (they also key the Italian
# neural WAVs). Keep them verbatim.
_CUE_EN: dict[str, str] = {
    # events.py
    "Bloccaggio, alleggerisci il freno": "Lock-up — ease off the brake",
    "Pattini in uscita, meno gas": "Wheelspin on exit — less throttle",
    # balance.py
    "Sovrasterzo, sii più dolce col gas in uscita":
        "Oversteer — smoother on the throttle out",
    "L'anteriore scivola, entra più piano": "Front washing out — slower on entry",
    # braking.py
    "Stai veleggiando: riduci il tempo morto fra freno e gas":
        "Coasting — close the gap between brake and throttle",
    "Rilasci il freno troppo presto: portane un filo fino all'inserimento":
        "Releasing the brake too early — trail a little to turn-in",
    # gears.py
    "Sei sul limitatore, cambia prima": "On the limiter — shift earlier",
    "Marcia troppo lunga, scala per avere più spinta":
        "Gear too tall — drop one for more drive",
    # analyzer.py (corner cues)
    "Bel tratto, continua così": "Good through there, keep it up",
    "Puoi frenare più tardi": "You can brake later",
    "Più gas qui": "More throttle here",
    "Stai frenando troppo, alleggerisci": "Braking too much — ease off",
    "Porta più velocità in curva": "Carry more speed through the corner",
    # fuel.py
    "Ultimo giro di benzina, rientra ai box!": "Last lap of fuel — box now!",
}

# Numeric cue templates (f-strings in the detectors) → English, by regex.
_CUE_EN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Stai perdendo (\d+) decimi qui$"), r"Losing \1 tenths here"),
    (re.compile(r"^Benzina per circa (\d+) giri\.$"), r"Fuel for about \1 laps."),
]


def cue_text(italian: str, lang: str | None = None) -> str:
    """Render a coaching cue in ``lang`` (default: the active language).

    Italian is the source; for English we translate. Unknown phrases pass through
    unchanged (a safe fallback rather than a crash)."""
    lang = lang or current_language()
    if lang != "en":
        return italian
    if italian in _CUE_EN:
        return _CUE_EN[italian]
    for pat, repl in _CUE_EN_PATTERNS:
        m = pat.match(italian)
        if m:
            return pat.sub(repl, italian)
    return italian
