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
    text = f"{v:.{decimals}f}"
    if lang == "it":
        text = text.replace(".", ",")
    return f"{text} {unit}" if unit else text
