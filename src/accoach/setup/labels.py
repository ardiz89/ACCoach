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
    "Approximate cold value. Base 20.3 psi at click 0, then 0.1 psi per click.":
        "Valore a freddo, approssimato. Base 20,3 psi al click 0, poi 0,1 psi per click.",
    "Real degrees, from staticCamber": "Gradi reali, da staticCamber",
    "About 0.2 % per click, the front base depends on the car":
        "Circa 0,2 % per click, la base anteriore dipende dall'auto",
    "Steps of about 1 mm": "Passi di circa 1 mm",
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


def param_label(key: str, lang: str | None = None) -> str:
    """Il nome di una leva come lo mostra l'editor («Barra ant.»), dalla sua
    chiave tecnica («aRBFront»). ACC prima, poi Assetto Corsa; una chiave che
    nessuno dei due conosce torna com'e'."""
    from .ac_format import AC_PARAMS
    from .acc_format import SETUP_PARAMS
    for spec in (*SETUP_PARAMS, *AC_PARAMS):
        if spec.key == key:
            return tr(spec.label, lang)
    return key


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
        return (f"Ho scritto «{name}». Ai box apri la schermata Setup, caricalo "
                f"e riparti.")
    return (f"I've written “{name}”. In the pits, open the Setup screen, load it "
            f"and head out.")


def err_slot_required(key: str, slots, lang: str | None = None) -> str:
    opts = ", ".join(slots)
    if _is_it(lang):
        return f"Per «{key}» serve la ruota o l'asse ({opts})."
    return f"“{key}” needs a wheel or an axle ({opts})."


def err_slot_out_of_range(index: int, key: str, lang: str | None = None) -> str:
    if _is_it(lang):
        return f"«{key}» non ha la posizione {index}."
    return f"“{key}” has no position {index}."


def err_slot_invalid(slot, key: str, lang: str | None = None) -> str:
    if _is_it(lang):
        return f"«{slot}» non è una posizione valida per «{key}»."
    return f"“{slot}” is not a valid position for “{key}”."


def err_bad_name(name: str, lang: str | None = None) -> str:
    """Un nome che `store.valid_name` rifiuta. La pagina mostra il testo così com'è."""
    if _is_it(lang):
        return (f"«{name}» non si può usare come nome di un assetto. "
                "Togli \ / : * ? \" < > | e il punto finale, "
                "ed evita nomi riservati di Windows come CON o NUL.")
    return (f"“{name}” can't be used as a setup name. "
            "Remove \ / : * ? \" < > | and any trailing dot, "
            "and avoid Windows reserved names such as CON or NUL.")


def err_needs_value(param: str, lang: str | None = None) -> str:
    if _is_it(lang):
        return f"Per «{param}» indica delta_clicks oppure value."
    return f"For “{param}”, give either delta_clicks or value."
