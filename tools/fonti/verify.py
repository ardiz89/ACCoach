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
_LINE_BREAKS = "\n\r\v\f\x85  "


def norm_text(s: str) -> str:
    return vocab.fold(s)


def _quote_regex(quote: str) -> re.Pattern:
    pre = r"(?<!\w)" if re.match(r"\w", quote) else ""
    post = r"(?!\w)" if re.search(r"\w$", quote) else ""
    return re.compile(pre + re.escape(quote) + post)


def _boundaries(body: str, segments) -> list[int] | None:
    """Indici grezzi dove una frase finisce; None se i segmenti non tornano col testo.

    La frase finisce a «.», «!», «?», «…» o a un a capo di qualunque tipo (il punto fra
    due cifre no). Con i sottotitoli anche la fine di ogni segmento chiude la frase, che
    il testo abbia punteggiatura o no.
    """
    ends = [i for i, c in enumerate(body)
            if c in _LINE_BREAKS + "!?…" or (c == "." and not (0 < i < len(body) - 1
                                                             and body[i - 1].isdigit() and body[i + 1].isdigit()))]
    if not segments:
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


_FOLLOW = re.compile(r" (?:into|at|for|in|through|alla|alle|al|per) (?:the )?")


def _corners_in(track: str, text: str, start: int, end: int) -> set[str]:
    return {name for name, aliases in vocab.CORNERS.get(track, {}).items()
            if any(vocab.alias_regex(a).search(text, start, end) for a in aliases)}


def _corner_after(track: str, text: str, start: int, end: int) -> str | None:
    """La curva detta subito dopo il valore: «... into tosa», «... alla tosa».

    Fra il valore e la curva c'è solo la preposizione (e «the»): nessuna virgola, nessun
    «then». Se due curve combaciano nello stesso punto è ambiguo.
    """
    m = _FOLLOW.match(text, start, end)
    if not m:
        return None
    names = {name for name, aliases in vocab.CORNERS.get(track, {}).items()
             for a in aliases
             if vocab.alias_regex(a).match(text, m.end(), end)}
    return next(iter(names)) if len(names) == 1 else None


def _other_gear(track: str, text: str, window: int, ns: int, ne: int,
                mark: int, corner: str | None) -> bool:
    """Un'altra marcia nella frase che non è chiaramente di un'altra curva.

    Due marce si separano solo se fra loro è nominata una curva e la curva di ciascuna
    (l'ultima nominata prima) esiste ed è diversa: «tosa second gear, piratella in third».
    """
    for p in vocab.gear_positions(text[ns:ne]):
        other = ns + p
        if other == mark:
            continue
        a, b = sorted((mark, other))
        ca = corner if a == mark else _last_corner(track, text, window, a)
        cb = corner if b == mark else _last_corner(track, text, window, b)
        if not (_corners_in(track, text, a, b) and ca and cb and ca != cb):
            return True
    return False


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

    # Un errore si descrive proprio con le negazioni: per `mistake` non contano.
    before = " ".join(nbody[:j].split()[-NEAR_WORDS:])
    after = " ".join(nbody[q_end:].split()[:NEAR_WORDS])
    around = f"{before} {quote} {after}"
    if type_ != "mistake":
        if vocab.NEGATION.search(around) or vocab.NEGATION.search(sentence):
            return "negazione"
        if type_ in ("apex", "kerb") and (vocab.NEGATIVE_SENSE.search(around)
                                         or vocab.NEGATIVE_SENSE.search(sentence)):
            return "negazione"

    # Il segno del valore: da lì all'indietro, la prima curva nominata è quella del fatto.
    # Oppure, nella stessa frase, la curva subito dopo il valore con una preposizione.
    got = vocab.locate(type_, quote) if type_ not in ("line", "mistake") else None
    mark = j + got[1] if got else q_end
    window = bisect.bisect_left(idx, idx[j] - CONTEXT_CHARS)  # idx cresce: primo carattere nella finestra
    corner = _last_corner(track, nbody, window, mark)
    if got:
        follow = _corner_after(track, nbody, j + got[2], ne)
        if follow is not None:
            # Un'altra curva prima del valore, nella stessa frase, la rende ambigua.
            corner = follow if _corners_in(track, nbody, ns, mark) <= {follow} else None
    if corner != fact.get("corner"):
        return "curva_non_trovata"
    # Un consiglio descrittivo non ha un segno: se la frase fino alla fine della citazione
    # nomina due curve, non si sa a quale va.
    if type_ in ("line", "mistake") and len(_corners_in(track, nbody, min(ns, j), q_end)) > 1:
        return "curva_non_trovata"
    if type_ == "gear" and got and _other_gear(track, nbody, min(window, ns), ns, ne, mark, corner):
        return "valore_non_normalizzabile"

    if type_ in ("line", "mistake"):
        return None if norm_text(value) == quote else "valore_diverso"
    if got is None:
        return "valore_non_normalizzabile"
    reason = vocab.sentence_reason(type_, sentence, mark - ns)
    if reason:
        return reason
    return None if got[0] == value else "valore_diverso"



def locate_quote(quote: str, body: str, offset: int | None = None) -> tuple[str | None, int | None]:
    """Dove sta la citazione nel testo grezzo: `(motivo, inizio)`.

    Normalizzata e a confini di parola come in `check_fact`, almeno 4 parole. Con
    `offset`, conta solo l'occorrenza entro OFFSET_SLACK caratteri, la più vicina.
    """
    q = norm_text(str(quote or ""))
    body = str(body)
    nbody, idx = vocab.norm_map(body)
    starts = [m.start() for m in _quote_regex(q).finditer(nbody)] if q else []
    if not starts:
        return "citazione_assente", None
    if len(q.split()) < MIN_WORDS:
        return "citazione_corta", None
    if offset is None:
        return None, idx[starts[0]]
    if not isinstance(offset, int) or isinstance(offset, bool):
        return "offset_errato", None
    near = [j for j in starts if abs(idx[j] - offset) <= OFFSET_SLACK]
    if not near:
        return "offset_errato", None
    return None, idx[min(near, key=lambda k: abs(idx[k] - offset))]


def check_quote(quote: str, body: str, offset: int | None = None) -> str | None:
    """Solo l'aggancio al testo: presenza, 4 parole e, se dato, l'offset."""
    return locate_quote(quote, body, offset)[0]


def contains(quote: str, phrase: str) -> bool:
    """La frase (un nome, un tempo, un'auto) sta nella citazione, a confini di parola."""
    p = norm_text(str(phrase or ""))
    return bool(p) and _quote_regex(p).search(norm_text(str(quote or ""))) is not None
