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
    # advisor.py (brake-bias, static)
    "Blocchi l'anteriore in più curve e l'ABS è già alto: "
    "prova a spostare il bilanciamento freni verso il posteriore.":
        "Locking the fronts in several corners and ABS is already high: "
        "try moving brake bias rearward.",
    # analyzer.py (corner cues)
    "Bel tratto, continua così": "Good through there, keep it up",
    "Puoi frenare più tardi": "You can brake later",
    "Più gas qui": "More throttle here",
    "Stai frenando troppo, alleggerisci": "Braking too much — ease off",
    "Porta più velocità in curva": "Carry more speed through the corner",
    # fuel.py
    "Ultimo giro di benzina, rientra ai box!": "Last lap of fuel — box now!",
}

def _axle_en(it: str) -> str:
    return "Front" if it == "anteriori" else "Rear"


# Templated cues (f-strings in the detectors) → English. ``repl`` is either a
# regex replacement string or a callable(match) -> str for cases that remap words.
_CUE_EN_PATTERNS: list[tuple[re.Pattern, object]] = [
    # analyzer.py / fuel.py
    (re.compile(r"^Stai perdendo (\d+) decimi qui$"), r"Losing \1 tenths here"),
    (re.compile(r"^Benzina per circa (\d+) giri\.$"), r"Fuel for about \1 laps."),
    # advisor.py — ABS / TC, with or without the "(dal N al N+1)" detail
    (re.compile(r"^Blocchi l'anteriore in più curve: prova ad alzare l'ABS"
                r"(?: \(dal (\d+) al (\d+)\))?\.$"),
     lambda m: ("Locking the fronts in several corners: try raising the ABS"
                + (f" (from {m.group(1)} to {m.group(2)})." if m.group(1) else "."))),
    (re.compile(r"^Pattini in uscita in più punti del giro: prova ad alzare il TC"
                r"(?: \(dal (\d+) al (\d+)\))?\.$"),
     lambda m: ("Spinning up on exit in several places: try raising the TC"
                + (f" (from {m.group(1)} to {m.group(2)})." if m.group(1) else "."))),
    # pressure.py
    (re.compile(r"^Gomme (anteriori|posteriori) a ([\d.]+) psi, troppo alte: "
                r"cala circa ([\d.]+) psi a freddo\.$"),
     lambda m: f"{_axle_en(m.group(1))} tyres at {m.group(2)} psi, too high: "
               f"drop about {m.group(3)} psi cold."),
    (re.compile(r"^Gomme (anteriori|posteriori) a ([\d.]+) psi, troppo basse: "
                r"alza circa ([\d.]+) psi a freddo\.$"),
     lambda m: f"{_axle_en(m.group(1))} tyres at {m.group(2)} psi, too low: "
               f"add about {m.group(3)} psi cold."),
    # tyretemp.py
    (re.compile(r"^Gomme troppo calde \((\d+)°C\): stai forzando, "
                r"cerca di essere più fluido\.$"),
     lambda m: f"Tyres too hot ({m.group(1)}°C): you're overdriving — be smoother."),
    (re.compile(r"^Gomme fredde \((\d+)°C\): puoi spingere di più "
                r"per portarle in temperatura\.$"),
     lambda m: f"Tyres cold ({m.group(1)}°C): push harder to bring them up to temperature."),
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
            return repl(m) if callable(repl) else pat.sub(repl, italian)
    return italian
