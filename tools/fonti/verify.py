"""Verificatore: un fatto entra solo se la citazione è nel testo e sostiene il valore.

È il cancello di sicurezza. Accettare per sbaglio è il guasto grave, rifiutare per
sbaglio no: nel dubbio si rifiuta. Qui si controlla l'aggancio al testo; il senso
(ironia, negazioni lontane) lo controllano dopo gli autori indipendenti e il factcheck.
"""

from __future__ import annotations

import bisect
import re

from tools.fonti import vocab

CONTEXT_CHARS = 300  # quanti caratteri grezzi prima della citazione si guardano per la curva
OFFSET_SLACK = 5     # di quanto l'offset dichiarato può mancare l'inizio vero della citazione
NEAR_WORDS = 5       # parole prima e dopo la citazione in cui una negazione conta
MIN_WORDS = 4
_TERMINATORS = ".!?…"


def norm_text(s: str) -> str:
    return vocab.fold(s)


def _quote_regex(quote: str) -> re.Pattern:
    pre = r"(?<!\w)" if re.match(r"\w", quote) else ""
    post = r"(?!\w)" if re.search(r"\w$", quote) else ""
    return re.compile(pre + re.escape(quote) + post)


def _boundaries(body: str, segments) -> list[int] | None:
    """Indici grezzi dove una frase finisce; None se i segmenti non tornano col testo.

    La frase finisce a «.», «!», «?» o a un a capo (il punto fra due cifre no). Nei
    sottotitoli senza punteggiatura la frase è il segmento.
    """
    ends = [i for i, c in enumerate(body)
            if c in "\n\r!?…" or (c == "." and not (0 < i < len(body) - 1
                                                    and body[i - 1].isdigit() and body[i + 1].isdigit()))]
    if not segments or any(c in body for c in _TERMINATORS):
        return ends
    cursor = 0
    for seg in segments:
        text = seg.get("text") if isinstance(seg, dict) else None
        if not isinstance(text, str):
            return None
        at = body.find(text, cursor)
        if at < 0:
            return None
        cursor = at + len(text)
        ends.append(cursor)
    return sorted(set(ends))


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


def check_fact(track: str, fact: dict, body: str, segments: list | None = None) -> str | None:
    type_ = fact.get("type")
    if type_ not in vocab.TYPES:
        return "tipo_ignoto"
    body = str(body)
    quote = norm_text(str(fact.get("quote", "")))
    nbody, idx = vocab.norm_map(body)
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

    # La citazione sta in una frase sola; i controlli di senso guardano la frase intera.
    ends = _boundaries(body, segments)
    if ends is None:
        return "citazione_oltre_frase"
    core = len(quote.rstrip(_TERMINATORS + " "))
    first, last = idx[j], idx[j + max(core, 1) - 1]
    k = bisect.bisect_left(ends, first)
    if k < len(ends) and ends[k] <= last:
        return "citazione_oltre_frase"
    s_raw = ends[k - 1] + 1 if k > 0 else 0
    e_raw = ends[k] if k < len(ends) else len(body)
    ns, ne = bisect.bisect_left(idx, s_raw), bisect.bisect_left(idx, e_raw)
    sentence = nbody[ns:ne]

    value = str(fact.get("value", ""))
    if type_ != "gear":  # le marce si dicono anche a parole
        cited = set(re.findall(r"(?<![0-9])[0-9]+(?![0-9])", quote))
        if any(n not in cited for n in re.findall(r"[0-9]+", value)):
            return "numero_non_citato"

    before = " ".join(nbody[:j].split()[-NEAR_WORDS:])
    after = " ".join(nbody[q_end:].split()[:NEAR_WORDS])
    around = f"{before} {quote} {after}"
    if vocab.NEGATION.search(around) or vocab.NEGATION.search(sentence):
        return "negazione"
    if type_ in ("apex", "kerb") and (vocab.NEGATIVE_SENSE.search(around)
                                     or vocab.NEGATIVE_SENSE.search(sentence)):
        return "negazione"

    # Il segno del valore: da lì all'indietro, la prima curva nominata è quella del fatto.
    got = vocab.locate(type_, quote) if type_ not in ("line", "mistake") else None
    mark = j + got[1] if got else q_end
    window = bisect.bisect_left(idx, idx[j] - CONTEXT_CHARS)  # idx cresce: primo carattere nella finestra
    if _last_corner(track, nbody, window, mark) != fact.get("corner"):
        return "curva_non_trovata"

    if type_ in ("line", "mistake"):
        return None if norm_text(value) == quote else "valore_diverso"
    if got is None:
        return "valore_non_normalizzabile"
    reason = vocab.sentence_reason(type_, sentence, mark - ns)
    if reason:
        return reason
    return None if got[0] == value else "valore_diverso"
