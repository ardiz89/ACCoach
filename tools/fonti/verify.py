"""Verificatore: un fatto entra solo se la citazione è nel testo e sostiene il valore.

È il cancello di sicurezza. Accettare per sbaglio è il guasto grave, rifiutare per
sbaglio no: nel dubbio si rifiuta.
"""

from __future__ import annotations

import bisect
import re

from tools.fonti import vocab

CONTEXT_CHARS = 300  # quanti caratteri grezzi prima della citazione si guardano per la curva
OFFSET_SLACK = 5     # di quanto l'offset dichiarato può mancare l'inizio vero della citazione
NEAR_WORDS = 5       # parole prima (e dopo) la citazione in cui una negazione conta
MIN_WORDS = 4

_WS = re.compile(r"\s")
_TYPO = {"’": "'", "‘": "'", "“": '"', "”": '"'}


def _norm_map(s: str) -> tuple[str, list[int]]:
    """Testo normalizzato e, per ogni suo carattere, l'indice nel testo grezzo."""
    out: list[str] = []
    idx: list[int] = []
    ws_at: int | None = None
    for i, c in enumerate(s):
        if _WS.match(c):
            if ws_at is None:
                ws_at = i
            continue
        if ws_at is not None:
            if out:
                out.append(" ")
                idx.append(ws_at)
            ws_at = None
        for ch in c.lower():
            out.append(_TYPO.get(ch, ch))
            idx.append(i)
    return "".join(out), idx


def norm_text(s: str) -> str:
    return _norm_map(s)[0]


def _quote_regex(quote: str) -> re.Pattern:
    pre = r"(?<!\w)" if re.match(r"\w", quote) else ""
    post = r"(?!\w)" if re.search(r"\w$", quote) else ""
    return re.compile(pre + re.escape(quote) + post)


def _last_corner(track: str, text: str, start: int, end: int) -> str | None:
    """La curva nominata per ultima in text[start:end]; None se nessuna o se è ambiguo."""
    best: tuple[int, int] | None = None
    names: set[str] = set()
    for name, aliases in vocab.CORNERS.get(track, {}).items():
        for a in aliases:
            for m in vocab.alias_regex(a).finditer(text, start, end):
                key = (m.end(), -m.start())
                if best is None or key > best:
                    best, names = key, {name}
                elif key == best:
                    names.add(name)
    return next(iter(names)) if len(names) == 1 else None


def check_fact(track: str, fact: dict, body: str) -> str | None:
    type_ = fact.get("type")
    if type_ not in vocab.TYPES:
        return "tipo_ignoto"
    quote = norm_text(str(fact.get("quote", "")))
    nbody, idx = _norm_map(str(body))
    starts = [m.start() for m in _quote_regex(quote).finditer(nbody)] if quote else []
    if not starts:
        return "citazione_assente"
    if len(quote.split()) < MIN_WORDS:
        return "citazione_corta"

    offset = fact.get("offset")
    if (not isinstance(offset, int) or isinstance(offset, bool)
            or not 0 <= offset <= len(body)):
        return "offset_errato"
    near = [j for j in starts if abs(idx[j] - offset) <= OFFSET_SLACK]
    if not near:
        return "offset_errato"
    j = min(near, key=lambda k: abs(idx[k] - offset))
    q_end = j + len(quote)

    value = str(fact.get("value", ""))
    if type_ != "gear":  # le marce si dicono anche a parole
        cited = set(re.findall(r"(?<!\d)\d+(?!\d)", quote))
        if any(n not in cited for n in re.findall(r"\d+", value)):
            return "numero_non_citato"

    before = " ".join(nbody[:j].split()[-NEAR_WORDS:])
    after = " ".join(nbody[q_end:].split()[:NEAR_WORDS])
    around = f"{before} {quote} {after}"
    if vocab.NEGATION.search(around):
        return "negazione"
    if type_ in ("apex", "kerb") and vocab.NEGATIVE_SENSE.search(around):
        return "negazione"

    window = bisect.bisect_left(idx, idx[j] - CONTEXT_CHARS)  # idx cresce: primo carattere nella finestra
    if _last_corner(track, nbody, window, q_end) != fact.get("corner"):
        return "curva_non_trovata"

    if type_ in ("line", "mistake"):
        return None if norm_text(value) == quote else "valore_diverso"
    got = vocab.normalize(type_, quote)
    if got is None:
        return "valore_non_normalizzabile"
    return None if got == value else "valore_diverso"
