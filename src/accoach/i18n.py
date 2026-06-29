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


# --- UI chrome catalogue (keyed; both languages equal) -----------------------
# Fixed interface strings for the Python surfaces (overlay, terminal, launcher),
# so they follow the selected language like the voice and cues do.
_UI: dict[str, dict[str, str]] = {
    # overlay
    "overlay.waiting": {"en": "waiting for the game…", "it": "in attesa del gioco…"},
    "overlay.rec": {"en": "REC ● learning the reference lap…",
                    "it": "REC ● sto imparando il giro di riferimento…"},
    "overlay.brake": {"en": "BRAKE", "it": "FRENA"},
    "overlay.focus": {"en": "FOCUS", "it": "FOCUS"},
    # terminal coach
    "coach.title": {"en": "voice coach", "it": "coach vocale"},
    "coach.no_ref": {"en": "no reference yet — drive a clean lap",
                     "it": "nessun riferimento — fai un giro pulito"},
    "coach.listening": {"en": "listening… drive and I'll coach you",
                        "it": "in ascolto… guida e ti seguo"},
    "coach.waiting": {"en": "waiting for game…", "it": "in attesa del gioco…"},
    "coach.warming": {"en": "warming up… drive a few clean laps",
                      "it": "scaldando… fai qualche giro pulito"},
    "coach.delta_title": {"en": "Delta vs reference", "it": "Delta vs riferimento"},
    "coach.delta_none": {"en": "no reference yet — drive a clean lap",
                         "it": "nessun riferimento — fai un giro pulito"},
    "coach.focus_title": {"en": "Focus · lesson", "it": "Focus · lezione"},
    "coach.coach_panel": {"en": "Coach", "it": "Coach"},
    "lbl.delta": {"en": "Delta", "it": "Delta"},
    "lbl.predicted": {"en": "Predicted", "it": "Previsto"},
    "lbl.reference": {"en": "Reference", "it": "Riferimento"},
    "lbl.state": {"en": "State", "it": "Stato"},
    "lbl.car_track": {"en": "Car @ Track", "it": "Auto @ Pista"},
    "lbl.current": {"en": "Current", "it": "Attuale"},
    "lbl.last": {"en": "Last", "it": "Ultimo"},
    "lbl.best": {"en": "Best", "it": "Migliore"},
    "lbl.laps_saved": {"en": "Laps saved", "it": "Giri salvati"},
    "state.waiting_game": {"en": "waiting for game…", "it": "in attesa del gioco…"},
    "voice.on": {"en": "voice", "it": "voce"},
    "voice.off": {"en": "text", "it": "testo"},
    # launcher
    "ui.language": {"en": "Language", "it": "Lingua"},
    "ui.tip_borderless": {
        "en": "Tip: set the game to Borderless so the overlay draws over it.",
        "it": "Suggerimento: imposta il gioco in Borderless così l'overlay ci si disegna sopra."},
    "btn.coach_live": {"en": "▶  Coach Live  (overlay + voice)",
                       "it": "▶  Coach Live  (overlay + voce)"},
    "btn.coach_live_demo": {"en": "▶  Coach Live — DEMO (no game)",
                            "it": "▶  Coach Live — DEMO (senza gioco)"},
    "btn.stop_live": {"en": "⏹  Stop Coach Live", "it": "⏹  Ferma Coach Live"},
    "btn.analysis": {"en": "📊  Analysis & Report (browser)",
                     "it": "📊  Analisi & Report (browser)"},
    "btn.engineer": {"en": "🔧  Race engineer (browser)",
                     "it": "🔧  Ingegnere di pista (browser)"},
    "btn.debrief": {"en": "📈  Last-lap debrief", "it": "📈  Debrief ultimo giro"},
    "btn.monitor": {"en": "📈  Telemetry monitor", "it": "📈  Monitor telemetria"},
    "btn.coach_term": {"en": "🎙  Voice coach (terminal)",
                       "it": "🎙  Coach vocale (terminale)"},
    "btn.verify_g": {"en": "🔧  Verify G axes", "it": "🔧  Verifica assi G"},
    "btn.get_started": {"en": "✨  Get started", "it": "✨  Come iniziare"},
    "btn.settings": {"en": "⚙  Settings", "it": "⚙  Impostazioni"},
    "btn.mobile": {"en": "📱  Phone / tablet", "it": "📱  Telefono / tablet"},
    "btn.guide": {"en": "❓  Guide — how to use", "it": "❓  Guida — come si usa"},
    # phone / tablet (LAN) dialog
    "mob.title": {"en": "Open on phone / tablet", "it": "Apri su telefono / tablet"},
    "mob.lan": {"en": "Allow access from other devices on my network",
                "it": "Consenti l'accesso dagli altri dispositivi in rete"},
    "mob.report": {"en": "Report", "it": "Report"},
    "mob.engineer": {"en": "Engineer", "it": "Ingegnere"},
    "mob.scan": {"en": "Scan with your phone's camera, or type the address.",
                 "it": "Inquadra col telefono, oppure digita l'indirizzo."},
    "mob.off": {"en": "Turn on the option above to open these pages from your phone.",
                "it": "Attiva l'opzione qui sopra per aprire le pagine dal telefono."},
    "mob.no_ip": {"en": "No network address found — connect this PC to Wi-Fi or LAN.",
                  "it": "Nessun indirizzo di rete — collega il PC a Wi-Fi o LAN."},
    "mob.same_net": {"en": "Your phone must be on the same Wi-Fi / network as this PC.",
                     "it": "Il telefono dev'essere sulla stessa Wi-Fi / rete del PC."},
    "mob.firewall": {"en": "If Windows asks, allow access on Private networks.",
                     "it": "Se Windows lo chiede, consenti l'accesso su reti private."},
    "mob.restart": {"en": "After changing this, (re)start Coach Live or Analysis.",
                    "it": "Dopo la modifica, (ri)avvia Coach Live o Analisi."},
    "mob.no_qr": {"en": "(QR unavailable — install 'segno')",
                  "it": "(QR non disponibile — installa 'segno')"},
    # settings dialog
    "ui.settings": {"en": "Settings", "it": "Impostazioni"},
    "set.voice": {"en": "Coach voice", "it": "Voce del coach"},
    "set.rate": {"en": "Reading speed (wpm)", "it": "Velocità lettura (ppm)"},
    "set.scale": {"en": "Overlay scale", "it": "Scala overlay"},
    "set.scale_hint": {"en": "Applies on the next Coach Live start.",
                       "it": "Attivo al prossimo avvio di Coach Live."},
    "btn.save": {"en": "Save", "it": "Salva"},
    "btn.cancel": {"en": "Cancel", "it": "Annulla"},
    "btn.close": {"en": "Close", "it": "Chiudi"},
}


def t(key: str, lang: str | None = None, **fmt) -> str:
    """Translate a UI key into the active (or given) language; format with ``fmt``.

    Falls back to English, then to the key itself, so a missing entry is visible
    rather than crashing."""
    lang = lang or current_language()
    entry = _UI.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    return text.format(**fmt) if fmt else text


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
