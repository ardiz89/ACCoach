"""Italian for the setup editor's display strings.

The param specs in :mod:`ac_format` / :mod:`acc_format` are authored in **English**
— canonical, the same convention as ``engineer/profiles/_common.py`` — and this
maps them to Italian. Only *display* strings live here: ``spec.key``
("tyrePressure", "aRBFront") is the technical identifier the API and the setup
files are keyed on, and never translates.

Why a string map and not message keys: these labels are short, fixed, and already
flow through the API as text (``group``/``label``/``note``), so a lookup keeps the
payload shape untouched. A missing entry passes through unchanged — an English
label is a mildly wrong look, not a broken page.

Terminology follows what the games and the sim-racing world actually say (Bump /
Rebound, ARB, Toe, Brake bias), not a literal translation of the Italian.
"""

from __future__ import annotations

from ..i18n import current_language

_IT: dict[str, str] = {
    # --- groups ---
    "Tyres": "Gomme",
    "Alignment": "Allineamento",
    "Aero": "Aero",
    "Mechanical": "Meccanica",
    "Dampers": "Ammortizzatori",
    "Ride height": "Altezze",
    "Drivetrain": "Trasmissione",
    "Brakes": "Freni",
    "Electronics": "Elettronica",
    "Strategy": "Strategia",
    # --- tyres ---
    "Pressure": "Pressione",
    "Compound": "Mescola",
    # --- alignment ---
    "Camber": "Camber",
    "Toe": "Convergenza",
    "Caster LF": "Caster Sx",
    "Caster RF": "Caster Dx",
    # --- aero ---
    "Front wing": "Ala anteriore",
    "Rear wing": "Ala posteriore",
    "Splitter": "Splitter",
    "Brake ducts": "Condotti freni",
    # --- mechanical ---
    "Front ARB": "Barra ant.",
    "Rear ARB": "Barra post.",
    "Springs": "Molle",
    "Bump stop (up)": "Bump stop (su)",
    "Bump stop (down)": "Bump stop (giù)",
    "Bump stop window": "Finestra bump stop",
    "Brake torque": "Coppia frenante",
    # --- dampers ---
    "Bump": "Compressione",
    "Rebound": "Estensione",
    "Slow bump": "Compressione lenta",
    "Fast bump": "Compressione veloce",
    "Slow rebound": "Estensione lenta",
    "Fast rebound": "Estensione veloce",
    # --- ride height ---
    "Ride height (rod length)": "Altezza (rod length)",
    # --- drivetrain ---
    "Diff power": "Diff. power",
    "Diff coast": "Diff. coast",
    "Diff preload": "Precarico diff.",
    "Final drive": "Rapporto finale",
    # --- brakes ---
    "Brake bias": "Bilanciamento freni",
    "Brake power": "Potenza freni",
    # --- electronics ---
    "Traction control": "Controllo trazione",
    "TC1": "TC1",
    "TC2": "TC2",
    "ABS": "ABS",
    "Engine map": "Mappa motore",
    "Fuel map": "Mappa benzina",
    # --- strategy ---
    "Fuel": "Benzina",
    # --- notes (the caveats shown under a param) ---
    "≈ cold; base 20.3 psi, 0.1 psi/click":
        "≈ a freddo; base 20.3 psi, 0.1 psi/click",
    "real degrees in staticCamber": "gradi reali in staticCamber",
    "~0.2%/click; front base depends on the car":
        "~0.2%/click; base anteriore dipende dall'auto",
    "1 mm step (approximate)": "passo 1 mm (approssimato)",
}


def tr(text: str, lang: str | None = None) -> str:
    """Translate a setup display string (EN→IT).

    ``lang`` lets a web request carry its own language — the page's selector, not
    the desktop's ``config.language``. Falls back to the app language for the
    in-process callers (CLI, coach) that have no request context.
    """
    if not text:
        return text
    if (lang or current_language()) == "it":
        return _IT.get(text, text)
    return text


def _is_it(lang: str | None) -> bool:
    return (lang or current_language()) == "it"


# Slot labels (FL/FR/RL/RR, F/R) are deliberately NOT in the catalogue above:
# they stay the same in every language. The engineer page's live tyre panel has
# always shown FL/FR/RL/RR untranslated, so translating them in the setup editor
# next to it would put two notations for the same four wheels on one screen —
# and FL/FR/RL/RR is what the games and the sim-racing world say anyway.
#
# The Italian spellings the editor used to ship are kept as input aliases: the CLI
# takes a slot by hand (`--slot Post-Dx`), and silently rejecting the spelling
# that worked yesterday would be a nasty little regression.
_LEGACY_SLOTS: dict[str, str] = {
    "Ant-Sx": "FL", "Ant-Dx": "FR", "Post-Sx": "RL", "Post-Dx": "RR",
    "Ant": "F", "Post": "R",
}


def canonical_slot(text: str) -> str:
    """Map a slot label — canonical or a legacy Italian one — to the canonical."""
    return _LEGACY_SLOTS.get(text, text)


# --- messages that carry values --------------------------------------------
# The map above only covers fixed strings. These interpolate a param key or a
# setup name, so each gets a small function rather than a catalogue entry.

def reload_hint(name: str, lang: str | None = None) -> str:
    """What to do with a setup we just wrote. Shown on every successful apply.

    Load-in-the-pits is a hard constraint, not a nicety — HONE never edits the
    car you're driving — so this line has to land in the reader's language.
    """
    if _is_it(lang):
        return f"Rientra ai box → schermata Setup → carica '{name}' → riparti."
    return f"Back to the pits → Setup screen → load '{name}' → head out."


def err_slot_required(key: str, slots, lang: str | None = None) -> str:
    opts = ", ".join(slots)
    if _is_it(lang):
        return f"slot richiesto per '{key}' ({opts})"
    return f"slot required for '{key}' ({opts})"


def err_slot_out_of_range(index: int, key: str, lang: str | None = None) -> str:
    if _is_it(lang):
        return f"slot {index} fuori range per '{key}'"
    return f"slot {index} is out of range for '{key}'"


def err_slot_invalid(slot, key: str, lang: str | None = None) -> str:
    if _is_it(lang):
        return f"slot '{slot}' non valido per '{key}'"
    return f"slot '{slot}' is not valid for '{key}'"


def err_needs_value(param: str, lang: str | None = None) -> str:
    if _is_it(lang):
        return f"'{param}': specifica delta_clicks o value"
    return f"'{param}': specify delta_clicks or value"
