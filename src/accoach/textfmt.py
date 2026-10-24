"""Il formato dei numeri nei testi, uguale per ogni superficie.

In italiano la virgola decimale («0,18 s»), in inglese il punto («0.18 s»); il
numero e l'unità separati da uno spazio; un valore che arrotonda a zero è «0»,
mai «-0,00» (un meno davanti a uno zero si legge come una misura, e non c'è).
Il gemello JS è `HoneI18n.fmtNum` in `web/i18n.js`: stesso comportamento, e
`tests/test_textfmt.py` lo prova eseguendo il JS vero.
"""
from __future__ import annotations


def fmt_num(v: float, decimals: int, lang: str, unit: str | None = None) -> str:
    """``fmt_num(0.18, 2, "it", "s")`` -> «0,18 s»; senza unità, solo il numero."""
    if abs(v) < 0.5 * 10 ** -decimals:
        v = 0.0
    text = f"{v:.{decimals}f}".replace("-", "−")
    if lang == "it":
        text = text.replace(".", ",")
    return f"{text} {unit}" if unit else text


# Le sigle che restano maiuscole in un nome di auto o di pista. Il resto prende
# la maiuscola iniziale; un pezzo con una cifra dentro («gt3», «m4», «r8») e'
# una sigla anche lui.
_UPPER = {"amg", "amr", "bmw", "gt", "gtr", "gte", "gts", "lms", "rsr", "tcr",
          "evo", "dtm", "gp", "ii", "iii", "rs", "cs", "gtd", "usa", "uk"}
_SPECIAL = {"mclaren": "McLaren"}


def display_name(raw: str) -> str:
    """Il nome di un'auto o di una pista come lo legge una persona.

    Il gioco scrive ``ferrari_296_gt3`` e ``brands_hatch``; il pannello «In
    pista», la Home e le pagine li mostravano cosi' (24/10). Un nome che ha gia'
    maiuscole o spazi e nessun trattino basso resta com'e' («HONE Demo»). Il
    prefisso ``ks_`` dei contenuti Kunos di AC non dice niente e si toglie.
    Gemello JS: ``HoneI18n.displayName`` in ``web/i18n.js``.
    """
    if not raw or ("_" not in raw and raw != raw.lower()):
        return raw
    parts = [p for p in raw.split("_") if p]
    if len(parts) > 1 and parts[0].lower() == "ks":
        parts = parts[1:]
    out = []
    for p in parts:
        low = p.lower()
        if low in _SPECIAL:
            out.append(_SPECIAL[low])
        elif low in _UPPER or any(c.isdigit() for c in low):
            out.append(low.upper())
        else:
            out.append(low[:1].upper() + low[1:])
    return " ".join(out)
