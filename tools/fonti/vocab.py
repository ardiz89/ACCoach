"""Vocabolario chiuso: alias delle curve e normalizzazione dei valori (italiano e inglese).

Tutto è deterministico. Nel dubbio `normalize` dà `None`: un valore ambiguo, negato
o detto in modo diverso dalle forme ammesse non si sceglie.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from accoach.trackdata import _CORNERS  # noqa: E402

BOARDS = (50, 100, 150, 200, 250, 300)

# Lista chiusa: slug -> frasi (già in minuscolo, apostrofi dritti).
OBJECTS = {
    "bridge": ["bridge", "ponte"],
    "tyre_wall": ["tyre wall", "tire wall", "wall of tyres", "wall of tires",
                  "muro di gomme", "muro delle gomme"],
    "kerb_start": ["kerb start", "curb start", "start of the kerb", "start of the curb",
                   "start of kerb", "inizio del cordolo", "inizio cordolo"],
    "marshal_post": ["marshal post", "marshals post", "marshal's post", "marshal station",
                     "postazione dei commissari", "posto dei commissari",
                     "postazione commissari", "posto commissari"],
    "apex_kerb": ["apex kerb", "apex curb", "cordolo dell'apice", "cordolo all'apice",
                  "cordolo d'apice"],
}

# Nomi canonici e ordine vengono da trackdata. Gli alias sono solo i nomi e le loro
# storpiature nei sottotitoli: nessun numero di curva («t5», «turn 5», «curva 5»),
# perché la numerazione non ha una fonte. Mai un alias che valga per due curve.
_EXTRA = {
    "Tamburello": ["tamburelo", "tamburrello"],
    "Villeneuve": ["villenueve", "villeneuf", "villa neuve"],
    "Tosa": [],
    "Piratella": ["pirattela", "piratela"],
    "Acque Minerali": ["acqua minerale", "acque minerale", "aqua minerale", "acqua minerali"],
    "Variante Alta": ["alta chicane"],
    "Rivazza": ["rivaza", "revazza", "rivazzas"],
}

CORNERS: dict[str, dict[str, list[str]]] = {
    "imola": {
        name: sorted({name.lower(), *_EXTRA.get(name, [])})
        for name, _pos in _CORNERS["imola"]
    }
}


def alias_regex(alias: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


# Negazioni e parole che rovesciano il senso. Una sola basta a non decidere.
NEGATION = re.compile(
    r"\b(?:not|don't|dont|do not|never|avoid\w*|stay off|instead|no|non|mai|evita|evitare"
    r"|senza|without|nor|neither)\b|\w+n't\b")
NEGATIVE_SENSE = re.compile(
    r"\b(?:kill\w*|will cost|costs? you|dangerous|pericolos\w*|crash\w*|spin\w*)\b")


def negated(text: str) -> bool:
    return bool(NEGATION.search(_norm(text)))


def negative_sense(text: str) -> bool:
    return bool(NEGATIVE_SENSE.search(_norm(text)))


def _uniq(found: set[str]) -> str | None:
    return next(iter(found)) if len(found) == 1 else None


# --- frenata ----------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_NOT_BOARD_UNIT = re.compile(
    r"\s*(?:kph|kmh|km|mph|ms\b|s\b|sec|second|secondi|lap|giri\b|giro\b|%|psi|bar\b"
    r"|rpm|kg|click|tenth|decim|deg|°|gradi|st\b|nd\b|rd\b|th\b|x\b|percent|per cent)")
_RELATIVE = re.compile(
    r"\b(?:later|earlier|sooner|after|past|beyond|before|ahead|behind|dopo|oltre|prima"
    r"|più tardi|piu tardi|in anticipo|in ritardo|than|too|troppo|early|late|presto|tardi)\b")
# Condizionali e incertezze: il valore non è un consiglio fermo.
HEDGE = re.compile(r"\b(?:maybe|perhaps|might|could|if|unless|or|either|forse|magari|se|oppure|o)\b")
_BRAKE_EN = r"\b(?:brake|brakes|braking)\s+(?:hard\s+)?(?:at|by|when you reach|as you reach)\s+(?:the\s+)?"
_BRAKE_IT = (r"\b(?:frena|frenare|frenata|frenate|stacca|staccare|staccata)\s+"
             r"(?:al|alla|allo|ai|agli|sul|sulla|sullo|all'|sull')\s*")


def _brake(q: str) -> str | None:
    if NEGATION.search(q) or _RELATIVE.search(q) or HEDGE.search(q):
        return None
    # Ogni numero di due o più cifre conta: deve essercene uno solo, ed è il cartello.
    multi = [m for m in _NUMBER.finditer(q) if len(re.sub(r"\D", "", m.group())) >= 2]
    mentioned = {slug for slug, phrases in OBJECTS.items()
                 if any(alias_regex(p).search(q) for p in phrases)}
    if multi:
        if len(multi) > 1 or mentioned:
            return None
        m = multi[0]
        if not m.group().isdigit() or int(m.group()) not in BOARDS:
            return None
        if _NOT_BOARD_UNIT.match(q, m.end()):
            return None
        return f"board:{int(m.group())}"
    if len(mentioned) != 1:
        return None
    slug = next(iter(mentioned))
    alts = "|".join(re.escape(p) for p in OBJECTS[slug])
    if re.search(rf"(?:{_BRAKE_EN}|{_BRAKE_IT})(?:{alts})(?![a-z0-9])", q):
        return f"object:{slug}"
    return None


# --- marce ------------------------------------------------------------------

_ORD = {
    "1": ["first", "1st", "prima", "primo"], "2": ["second", "2nd", "seconda", "secondo"],
    "3": ["third", "3rd", "terza", "terzo"], "4": ["fourth", "4th", "quarta", "quarto"],
    "5": ["fifth", "5th", "quinta", "quinto"], "6": ["sixth", "6th", "sesta", "sesto"],
}
_ORD_WORD = {w: d for d, ws in _ORD.items() for w in ws}
# Tutto quello che somiglia a una marcia: ordinali in parole o «Nth», e cifre sole.
_GEAR_LIKE = re.compile(
    r"\b(?:" + "|".join(_ORD_WORD) + r"|\d+(?:st|nd|rd|th))\b"
    r"|(?<![\w.,])\d(?![\w]|[.,]\d)")
_GEAR = r"(?:gear|gears|marcia|marce)"
_LEAD = r"(?:shift down to|shift down into|shift to|shift into|down to|into|in)"
_UNIT_AFTER_DIGIT = (
    r"(?!\s*(?:laps?\b|giri\b|giro\b|kph|km/h|kmh|km\b|mph|corners?\b|curva\b|curve\b"
    r"|seconds?\b|secs?\b|s\b|secondi\b|metres?\b|meters?\b|metri\b|m\b|mt\b|tenths?\b"
    r"|decimi\b|%|psi\b|bar\b|clicks?\b|rpm\b|or\b|o\b|and\b|e\b|to\b))")
_NOUN_AFTER_ORD = (
    r"(?!\s+(?:place|position|posizione|corners?|curva|curve|laps?|giro|sector|settore"
    r"|time|volta|half|part|apex|brak\w*|or|o|and|e)\b)")


def _gear(q: str) -> str | None:
    if NEGATION.search(q) or HEDGE.search(q):
        return None
    tokens = _GEAR_LIKE.findall(q)
    if len(tokens) != 1:
        return None
    tok = tokens[0]
    t = re.escape(tok)
    if tok.isdigit():
        if tok not in "123456":
            return None
        ok = (re.search(rf"\b{_LEAD}\s+{t}(?!\w){_UNIT_AFTER_DIGIT}", q)
              or re.search(rf"\b{_GEAR}\s+{t}(?!\w){_UNIT_AFTER_DIGIT}", q)
              or re.search(rf"(?<![\w.,]){t}\s*{_GEAR}\b", q))
        return tok if ok else None
    digit = _ORD_WORD.get(tok) or (tok[0] if tok[0] in "123456" and len(tok) == 3 else None)
    if digit is None:
        return None
    ok = (re.search(rf"\b{t}\s+{_GEAR}\b", q)
          or re.search(rf"\b{_GEAR}\s+{t}\b{_NOUN_AFTER_ORD}", q)
          or re.search(rf"\b{_LEAD}\s+(?:the\s+)?{t}\b{_NOUN_AFTER_ORD}", q))
    return digit if ok else None


# --- apice e cordolo ----------------------------------------------------------

def _adjacent(a: str, b: str, q: str) -> bool:
    """a e b vicini: in mezzo al più una parola, solo spazi o trattini (niente virgole)."""
    gap = r"[ -]+(?:[\w']+[ -]+)?"
    return bool(re.search(rf"\b(?:{a}){gap}(?:{b})\b|\b(?:{b}){gap}(?:{a})\b", q))


def _present(kinds: dict[str, str], q: str) -> set[str]:
    return {k for k, w in kinds.items() if re.search(rf"\b(?:{w})\b", q)}


_APEX_KINDS = {
    "early": r"early|earlier|anticipat\w*|presto",
    "middle": r"mid|middle|centre|center|central\w*|centrale",
    "late": r"late|later|tardi\w*|tardo|ritardat\w*",
}


def _apex(q: str) -> str | None:
    if NEGATION.search(q) or NEGATIVE_SENSE.search(q):
        return None
    kinds = _present(_APEX_KINDS, q)
    if len(kinds) != 1:
        return None
    k = next(iter(kinds))
    return k if _adjacent(_APEX_KINDS[k], r"apex|apexes|apexing|apice|apici", q) else None


_KERB = r"kerb|kerbs|curb|curbs|cordolo|cordoli"
_KERB_POS = {
    "entry": r"entry|turn-in|turn in|ingresso|entrata|inserimento",
    "apex": r"apex|apice",
    "exit": r"exit|uscita",
}


def _kerb(q: str) -> str | None:
    if NEGATIVE_SENSE.search(q):
        return None
    pos = _present(_KERB_POS, q)
    if NEGATION.search(q):
        none = re.search(
            rf"^(?:you\s+)?(?:don't use|do not use|dont use|never use|avoid|no|without)\s+"
            rf"(?:the\s+|any\s+)?(?:{_KERB})$"
            rf"|^(?:non usare|non toccare|non prendere|evita|senza)\s+(?:il\s+|i\s+)?(?:{_KERB})$", q)
        return "none" if none and not pos else None
    if len(pos) != 1:
        return None
    p = next(iter(pos))
    return p if _adjacent(_KERB_POS[p], _KERB, q) else None


_NORMALIZERS = {"brake": _brake, "gear": _gear, "apex": _apex, "kerb": _kerb}
TYPES = ("brake", "gear", "apex", "kerb", "line", "mistake")


def normalize(type_: str, quote: str) -> str | None:
    """Valore canonico che la citazione sostiene, o `None` se non c'è, è ambiguo o negato."""
    fn = _NORMALIZERS.get(type_)
    return fn(_norm(quote)) if fn else None
