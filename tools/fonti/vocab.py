"""Vocabolario chiuso: alias delle curve e normalizzazione dei valori (italiano e inglese).

Tutto è deterministico. Un valore ambiguo non si sceglie: `normalize` dà `None`.
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

# Nomi canonici e ordine vengono da trackdata. Gli alias sono prudenti: i numeri di
# curva solo nelle forme «tN» / «turn N» / «curva N», mai il numero nudo, e mai un
# alias che valga per due curve. Numerazione usata dalle guide: T1-2 Tamburello,
# T3-4 Villeneuve, T5 Tosa, T6-7 Piratella, T8-9 Acque Minerali, T10-11 Variante Alta.
# I numeri oltre l'11 (Rivazza) non sono uniformi tra le guide: restano fuori.
_EXTRA = {
    "Tamburello": ["tamburelo", "tamburrello", "tamburello chicane", "tamburello corner",
                   "tamburello 1", "tamburello 2", "t1", "t2", "turn 1", "turn 2",
                   "curva 1", "curva 2"],
    "Villeneuve": ["villeneuve chicane", "villenueve", "villeneuf", "villa neuve",
                   "t3", "t4", "turn 3", "turn 4", "curva 3", "curva 4"],
    "Tosa": ["tosa hairpin", "tornante tosa", "t5", "turn 5", "curva 5"],
    "Piratella": ["pirattela", "piratela", "piratella corner", "t6", "t7",
                  "turn 6", "turn 7", "curva 6", "curva 7"],
    "Acque Minerali": ["acqua minerale", "acque minerale", "aqua minerale",
                       "acqua minerali", "acque minerali corner", "t8", "t9",
                       "turn 8", "turn 9", "curva 8", "curva 9"],
    "Variante Alta": ["variante alta chicane", "alta chicane", "high chicane",
                      "t10", "t11", "turn 10", "turn 11", "curva 10", "curva 11"],
    "Rivazza": ["rivaza", "revazza", "rivazzas", "rivazza 1", "rivazza 2",
                "rivazza uno", "rivazza due"],
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


def _uniq(found: set[str]) -> str | None:
    return next(iter(found)) if len(found) == 1 else None


def _brake(q: str) -> str | None:
    found: set[str] = set()
    nums = "|".join(str(b) for b in BOARDS)
    for m in re.finditer(
        rf"(?<![\d.,])({nums})(?![\d])\s*(?:m|metre|metres|meter|meters|mt)?\s*"
        rf"(?:board|boards|marker|markers|sign|signs|cartello|cartelli)\b", q):
        found.add(f"board:{m.group(1)}")
    for m in re.finditer(
        rf"\bcartell\w*\s+(?:dei|dai|da|del|di)?\s*({nums})(?![\d])", q):
        found.add(f"board:{m.group(1)}")
    for slug, phrases in OBJECTS.items():
        if any(alias_regex(p).search(q) for p in phrases):
            found.add(f"object:{slug}")
    return _uniq(found)


_ORD = {
    "1": ["first", "1st", "prima"], "2": ["second", "2nd", "seconda"],
    "3": ["third", "3rd", "terza"], "4": ["fourth", "4th", "quarta"],
    "5": ["fifth", "5th", "quinta"], "6": ["sixth", "6th", "sesta"],
}
_NOT_UNIT = r"(?!\s*(?:sec|m\b|metr|meter|tenth|decim|%|km|mph|psi|bar\b))"


def _gear(q: str) -> str | None:
    found: set[str] = set()
    for digit, words in _ORD.items():
        for w in words:
            pre = rf"(?:in|into|to|use|take|a|alla|nella)\s+(?:the\s+)?{w}\b"
            post = rf"\b{w}\s+(?:gear|marcia)\b"
            ctx = rf"\b(?:gear|marcia)\s+{w}\b"
            if w[0].isdigit():  # «3rd» da solo è già una marcia
                if re.search(rf"(?<![\d]){w}\b", q):
                    found.add(digit)
            elif re.search(f"{pre}|{post}|{ctx}", q):
                found.add(digit)
    for m in re.finditer(rf"\b(?:in|into|to|gear|marcia)\s+([1-6])(?!\d){_NOT_UNIT}", q):
        found.add(m.group(1))
    for m in re.finditer(r"(?<![\d])([1-6])\s+(?:gear|marcia)\b", q):
        found.add(m.group(1))
    return _uniq(found)


def _near(a: str, b: str, q: str, gap: int = 2) -> bool:
    between = rf"(?:\W+\w+){{0,{gap}}}\W+"
    return bool(re.search(rf"\b(?:{a}){between}(?:{b})\b|\b(?:{b}){between}(?:{a})\b", q))


def _apex(q: str) -> str | None:
    anchor = r"apex|apexing|apice|clip|clipping"
    kinds = {
        "early": r"early|anticipat\w*|presto",
        "middle": r"mid|middle|centre|center|central\w*",
        "late": r"late|tardi\w*|ritardat\w*",
    }
    return _uniq({k for k, w in kinds.items() if _near(w, anchor, q)})


def _kerb(q: str) -> str | None:
    k = r"kerb|kerbs|curb|curbs|cordolo|cordoli"
    found: set[str] = set()
    if re.search(rf"\b(?:no|without|avoid|never|don't use|do not use)\s+(?:the\s+)?(?:{k})\b"
                 rf"|\bsenza\s+(?:il\s+)?(?:{k})\b"
                 rf"|\bnon\s+(?:usare|toccare|prendere)\s+(?:il\s+)?(?:{k})\b", q):
        found.add("none")
    if _near(r"entry|turn-in|turn in|ingresso|entrata|inserimento", k, q):
        found.add("entry")
    if _near(r"apex|apice", k, q):
        found.add("apex")
    if _near(r"exit|uscita", k, q):
        found.add("exit")
    return _uniq(found)


_NORMALIZERS = {"brake": _brake, "gear": _gear, "apex": _apex, "kerb": _kerb}
TYPES = ("brake", "gear", "apex", "kerb", "line", "mistake")


def normalize(type_: str, quote: str) -> str | None:
    """Valore canonico che la citazione sostiene, o `None` se non c'è o è ambiguo."""
    fn = _NORMALIZERS.get(type_)
    return fn(_norm(quote)) if fn else None
