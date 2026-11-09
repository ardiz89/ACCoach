"""Verificatore: un fatto entra solo se la citazione è nel testo e sostiene il valore."""

from __future__ import annotations

import re

from tools.fonti import vocab

CONTEXT_CHARS = 300


def norm_text(s: str) -> str:
    s = s.lower()
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _has_corner(track: str, corner: str, text: str) -> bool:
    aliases = vocab.CORNERS.get(track, {}).get(corner)
    return bool(aliases) and any(vocab.alias_regex(a).search(text) for a in aliases)


def check_fact(track: str, fact: dict, body: str) -> str | None:
    type_ = fact.get("type")
    if type_ not in vocab.TYPES:
        return "tipo_ignoto"
    quote = norm_text(str(fact.get("quote", "")))
    if not quote or quote not in norm_text(body):
        return "citazione_assente"
    value = str(fact.get("value", ""))
    if type_ != "gear":  # le marce si dicono anche a parole
        cited = set(re.findall(r"(?<!\d)\d+(?!\d)", quote))
        if any(n not in cited for n in re.findall(r"\d+", value)):
            return "numero_non_citato"
    offset = max(0, int(fact.get("offset", 0) or 0))
    before = norm_text(body[max(0, offset - CONTEXT_CHARS):offset])
    corner = fact.get("corner", "")
    if not (_has_corner(track, corner, quote) or _has_corner(track, corner, before)):
        return "curva_non_trovata"
    if type_ in ("line", "mistake"):
        return None
    got = vocab.normalize(type_, quote)
    if got is None:
        return "valore_non_normalizzabile"
    return None if got == value else "valore_diverso"
