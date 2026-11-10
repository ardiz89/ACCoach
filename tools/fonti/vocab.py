"""Vocabolario chiuso: alias delle curve e normalizzazione dei valori (italiano e inglese).

Tutto è deterministico. Nel dubbio `locate` dà `None`: un valore ambiguo, negato
o detto in modo diverso dalle forme ammesse non si sceglie. Le cifre sono solo quelle
ASCII: una cifra a larghezza piena o araba non è un numero citato.
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

# Nomi canonici e ordine vengono da trackdata. Gli alias sono i nomi, le loro
# storpiature nei sottotitoli e i numeri di curva di TURNS. Mai un alias che valga per
# due curve.
_EXTRA = {
    "Tamburello": ["tamburelo", "tamburrello", "tamborello", "tambrella"],
    "Villeneuve": ["villenueve", "villeneuf", "villa neuve"],
    "Tosa": [],
    "Piratella": ["pirattela", "piratela", "paratella", "puritella"],
    "Acque Minerali": ["acqua minerale", "acque minerale", "aqua minerale", "acqua minerali",
                       "aqua minerali", "aqua mineral", "minerali", "minerale"],
    "Variante Alta": ["alta chicane"],
    "Rivazza": ["rivaza", "revazza", "rivazzas", "rivatsa"],
    # Spa: nel catalogo Eau Rouge e Raidillon sono una curva sola.
    "La Source": [],
    "Raidillon": ["eau rouge", "eau rouge raidillon", "radillon", "radillion"],
    "Les Combes": [],
    "Rivage": [],
    "Pouhon": ["puyon", "puan", "poo on"],
    "Fagnes": ["les fagnes", "lyfagna"],
    "Stavelot": ["stavalo"],
    "Bus Stop": ["bus stop chicane"],
    # Monza.
    "Variante del Rettifilo": ["rettifilo", "prima variante", "first chicane", "turn 1 chicane"],
    "Curva Grande": ["curva grande"],
    "Variante della Roggia": ["roggia", "seconda variante", "second chicane"],
    "Lesmo 1": ["first lesmo", "lesmo one", "prima di lesmo"],
    "Lesmo 2": ["second lesmo", "lesmo two", "seconda di lesmo"],
    "Variante Ascari": ["ascari", "ascari chicane"],
    "Parabolica": ["curva parabolica", "alboreto", "curva alboreto"],
    # Silverstone: solo grafie del nome. Club, Vale, Village e The Loop sono anche
    # parole comuni: lì contano i due autori e il controllo.
    "Farm Curve": ["farm"],
    "Maggotts": ["maggots"],
    "Becketts": ["beckets", "beckett", "beckett's", "becket's"],
    "Luffield": ["luffield corner", "luffa"],
    # Storpiature dei sottotitoli trovate il 10/11.
    "Abbey": ["abby"],
    "Copse": ["cops", "cops corner"],
    "Stowe": ["stow", "stove", "stow corner"],
    "Brooklands": ["brooklyn's", "brooklyns"],
    "Vale": ["veil"],
    # Mount Panorama: «chase», «hell» e «skyline» da soli sono parole comuni.
    "Hell Corner": ["hell's corner", "hells corner"],
    "Griffins Bend": ["griffin's bend", "griffins", "griffin's"],
    "The Cutting": ["cutting"],
    "Quarry Corner": ["quarry"],
    "Reid Park": ["reed park", "reeve park"],
    "Sulman Park": ["salmon park"],
    "McPhillamy Park": ["mcphillamy", "mcfillamy park", "mcfarlane park"],
    "The Dipper": ["dipper"],
    "Forrest's Elbow": ["forest elbow", "forrest elbow", "forest's elbow", "forrests elbow",
                        "force elbow", "the elbow"],  # a Bathurst il gomito è uno solo
    "The Chase": ["chase corner"],
    "Murray's Corner": ["murray's", "murrays corner", "murray"],
    # Zandvoort: «hairpin» no, perché a Zandvoort i tornanti sono due (Tarzan e Hugenholtz).
    "Tarzanbocht": ["tarzan", "tarzan corner", "tarzan bocht"],
    "Gerlachbocht": ["gerlach"],
    "Hugenholtzbocht": ["hugenholtz", "hogan halls"],
    "Slotemakerbocht": ["slotemaker"],
    "Mastersbocht": ["masters corner", "masters bocht"],
    "Hans Ernst": ["hans ernst bocht", "hans ernstbocht"],
    "Arie Luyendijkbocht": ["arie luyendijk", "luyendijk", "ariel indict curve"],
    # Brands Hatch. «Dingle Dell» non è nel catalogo; «clear» da solo è una parola comune.
    "Paddock Hill Bend": ["paddock hill", "paddock", "paddical", "paddock bend hill",
                          "paddock kill bend"],
    "Druids": ["druid", "druids hairpin"],
    "Graham Hill Bend": ["graham hill", "gram he'll bend"],
    "Surtees": [],
    "Hawthorn Bend": ["hawthorn", "hawthorns", "hawthorne", "hawthornes"],
    "Westfield Bend": ["westfield", "wesfields", "west field"],
    "Sheene Curve": ["sheene", "sheen", "sheens", "xin curve"],
    "Stirling's": ["stirlings", "stirling", "stirling's bend", "sterling's", "sterlings"],
    "Clearways": ["clearway"],
    "Clark Curve": ["clark", "clarks", "clark's"],
    # Suzuka. «Hairpin» e «Esses» sono parole comuni, ma a Suzuka c'è una curva sola così.
    "Esses": ["s curves", "s-curves", "the esses", "s curve"],
    "Dunlop": ["dunlop curve", "dunlop corner"],
    "Degner 1": ["first degner", "degner one", "degner curve 1", "digna one", "dner one",
                 "degna 1", "first degna"],
    "Degner 2": ["second degner", "degner two", "degner curve 2", "decker 2", "deckner two",
                 "second degna", "degna 2"],
    "Hairpin": ["suzuka hairpin", "hair pin"],
    "Spoon": ["spoon curve", "spoon corner"],
    "130R": ["130 r", "one thirty r", "130 are", "130 or"],
    "Casio Triangle": ["casio", "casio chicane", "final chicane", "last chicane",
                       "chicane"],  # l'unica chicane
}

# I numeri di curva di Imola come li usano le guide su ACC raccolte il 10/11 (Yorkie065,
# Tobias Pfeffer, SimRacingSetups, Luke Morris): la 2 è la prima frenata, la 7 il
# tornante a sinistra, dopo la 9 l'Acque Minerali. Deciso dal pilota il 10/11. Solo le
# curve dove quelle guide concordano: le pieghe 1, 8, 10, 13, 16 e 19 restano fuori,
# perché le fonti esterne le numerano in modi diversi.
TURNS: dict[str, dict[str, tuple[int, ...]]] = {
    "imola": {
        "Tamburello": (2, 3, 4),
        "Villeneuve": (5, 6),
        "Tosa": (7,),
        "Piratella": (9,),
        "Acque Minerali": (11, 12),
        "Variante Alta": (14, 15),
        "Rivazza": (17, 18),
    },
    # Silverstone su ACC parte dalla vecchia zona box: la curva 1 è Copse, non Abbey come
    # in F1 (Scuderia Fantozzi lo dice in chiaro, e così ScallionForward2838 e
    # FatherJack_Hackett). Sul resto le fonti del 10/11 numerano in modi diversi
    # (Yorkie065: Loop 14; ScallionForward2838: Luffield 14), quindi resta solo Copse.
    "silverstone": {
        "Copse": (1,),
    },
    # Mount Panorama: la 1 è la prima staccata dopo il traguardo per Yorkie065, Track
    # Titan, Yas Heat, Luke Morris e Salt_Slip_9038; la 2 è Griffins Bend per Yorkie065 e SideMax Motorworks; Skyline 11
    # (Track Titan), The Dipper 14 e Forrest's Elbow 18 (Yorkie065) li dice una guida
    # sola, in chiaro, e nessuna fonte del 10/11 li contraddice. The Chase e Murray's no:
    # lì le guide contano le pieghe in modi diversi.
    "mountpanorama": {
        "Hell Corner": (1,),
        "Griffins Bend": (2,),
        "Skyline": (11,),
        "The Dipper": (14,),
        "Forrest's Elbow": (18,),
    },
    # Brands Hatch: Surtees 4 (Yorkie065, djperijey), Sheene 7 (djperijey, Vida8943);
    # Hawthorn 5, Stirling's 8 e Clark 9 da djperijey, Westfield 6 da una fonte Reddit,
    # in chiaro, senza contraddizioni.
    "brandshatch": {
        "Surtees": (4,),
        "Hawthorn Bend": (5,),
        "Westfield Bend": (6,),
        "Sheene Curve": (7,),
        "Stirling's": (8,),
        "Clark Curve": (9,),
    },
}
# I nomi della pista: una fonte è di quella pista solo se il titolo ne dice uno. Una
# ricerca «ACC Imola» riporta anche guide di Spa, e un «turn 7» di Spa non è la Tosa.
TRACK_NAMES: dict[str, tuple[str, ...]] = {
    "imola": ("imola", "enzo e dino ferrari", "santerno"),
    "spa": ("spa", "francorchamps", "spa-francorchamps"),
    "monza": ("monza",),
    "silverstone": ("silverstone",),
    "suzuka": ("suzuka",),
    "mountpanorama": ("bathurst", "mount panorama", "mt panorama"),    "zandvoort": ("zandvoort",),    "brandshatch": ("brands hatch", "brands"),    "catalunya": ("barcelona", "barcellona", "catalunya", "catalonia", "montmelo"),
}
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
          8: "eight", 9: "nine", 11: "eleven", 12: "twelve", 14: "fourteen", 15: "fifteen",
          17: "seventeen", 18: "eighteen"}


def turn_aliases(track: str) -> dict[str, list[str]]:
    """Per ogni curva gli alias numerici: «turn 7», «turn seven», «t7», «curva 7»."""
    out = {}
    for name, nums in TURNS.get(track, {}).items():
        out[name] = sorted({a for n in nums for a in (f"turn {n}", f"turn {_WORDS[n]}", f"t{n}",
                                                      f"curva {n}")})
    return out


CORNERS: dict[str, dict[str, list[str]]] = {
    track: {
        name: sorted({name.lower(), *_EXTRA.get(name, []), *turn_aliases(track).get(name, [])})
        for name, _pos in _CORNERS[track]
    }
    # Solo le piste con le curve per nome: quelle numerate (COTA, Red Bull Ring…)
    # hanno nel catalogo un numero, e il report lo traduce in «Curva N».
    for track in _CORNERS if all(isinstance(n, str) for n, _pos in _CORNERS[track])
}
# Gli alias che chiamano la curva col numero: la pagina di controllo li segna.
NUMBER_ALIASES: dict[str, set[str]] = {
    track: {a for aliases in turn_aliases(track).values() for a in aliases} for track in TURNS
}


def mask_numbers(track: str, text: str) -> str:
    """Il testo con gli alias numerici delle curve coperti da «_», stessa lunghezza.

    «turn 17, brake at the 100» ha un numero solo, quello del cartello: il 17 è il nome
    della curva. Le posizioni non cambiano, quindi gli offset restano buoni.
    """
    for a in sorted(NUMBER_ALIASES.get(track, ()), key=len, reverse=True):
        text = alias_regex(a).sub(lambda m: "_" * len(m.group()), text)
    return text


def alias_regex(alias: str) -> re.Pattern:
    # «tosa-like» non è la Tosa: dopo il nome niente lettera, nemmeno dietro un trattino.
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])(?!-[^\W\d_])")


# --- normalizzazione del testo ----------------------------------------------

_WS = re.compile(r"\s")
# Ogni variante di apostrofo diventa «'», le virgolette tipografiche «"».
_FOLD = {c: "'" for c in "’‘‛´`ʼ′＇"} | {"“": '"', "”": '"'}


def norm_map(s: str) -> tuple[str, list[int]]:
    """Testo normalizzato e, per ogni suo carattere, l'indice nel testo grezzo.

    Minuscolo, apostrofi e virgolette dritti, ogni sequenza di spazi ridotta a uno,
    niente spazi in testa e in coda.
    """
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
            out.append(_FOLD.get(ch, ch))
            idx.append(i)
    return "".join(out), idx


def fold(s: str) -> str:
    return norm_map(s)[0]


# --- parole che rovesciano o indeboliscono ------------------------------------

_CONTRACTIONS = ("can", "won", "shouldn", "didn", "doesn", "isn", "aren", "wouldn",
                 "couldn", "don", "haven", "hasn", "mustn", "wasn", "weren")
NEGATION = re.compile(
    r"\b(?:" + "|".join(f"{c}'?t" for c in _CONTRACTIONS) + r""
    r"|not|do not|cannot|can not|never|avoid\w*|stay off|stay away|keep off|keep away"
    r"|stay clear|watch out|careful\w*|mistakes?|wrong|too slow|bad|instead|no|nor|neither"
    r"|without"
    r"|non|mai|senza|evit\w*|nessun\w*|niente|neanche|nemmeno|neppure|mica|né|lascia stare"
    r"|lontan\w*|guai|sbagli\w*|errore|errori|scordat\w*|dimentic\w*|attenzione|occhio)\b")
NEGATIVE_SENSE = re.compile(
    r"\b(?:kill\w*|will cost|costs? you|dangerous|pericolos\w*|crash\w*|spin\w*)\b")
# Condizionali e incertezze: il valore non è un consiglio fermo.
HEDGE = re.compile(r"\b(?:maybe|perhaps|might|could|if|unless|or|either|forse|magari|se|oppure|o)\b")
# Parole che spostano la frenata rispetto al punto detto.
RELATIVE = re.compile(
    r"\b(?:later|earlier|sooner|after|past|beyond|before|ahead|behind|dopo|oltre|prima"
    r"|più tardi|piu tardi|in anticipo|in ritardo|than|too|troppo|early|late|presto|tardi)\b")
RELATIVE_WORDS = 3  # distanza massima, in parole, dal numero o dal verbo della frenata
_BRAKE_VERB = re.compile(r"\b(?:brak\w*|fren\w*|stacc\w*)\b")


def _word_index(s: str, pos: int) -> int:
    """Indice della parola che contiene `pos` (o della prima dopo)."""
    return len(re.findall(r"[\w']+", s[:pos])) - (1 if re.search(r"[\w']$", s[:pos]) else 0)


def relative_near(s: str, anchors: list[int]) -> bool:
    """Una parola relativa sta entro RELATIVE_WORDS parole da un'ancora o da un verbo di frenata."""
    words = [_word_index(s, p) for p in anchors]
    words += [_word_index(s, m.start()) for m in _BRAKE_VERB.finditer(s)]
    return any(abs(_word_index(s, m.start()) - w) <= RELATIVE_WORDS
               for m in RELATIVE.finditer(s) for w in words)


# --- frenata ----------------------------------------------------------------

_NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
NOT_BOARD_UNIT = re.compile(
    r"\s*(?:kph|kmh|km|mph|ms\b|s\b|sec|second|secondi|lap|giri\b|giro\b|%|psi|bar\b"
    r"|rpm|kg|click|tenth|decim|deg|°|gradi|st\b|nd\b|rd\b|th\b|x\b|percent|per cent)")
_BRAKE_EN = r"\b(?:brake|brakes|braking)\s+(?:hard\s+)?(?:at|by|when you reach|as you reach)\s+(?:the\s+)?"
_BRAKE_IT = (r"\b(?:frena|frenare|frenata|frenate|stacca|staccare|staccata)\s+"
             r"(?:al|alla|allo|ai|agli|sul|sulla|sullo|all'|sull')\s*")


def board_numbers(s: str) -> list[re.Match]:
    """Ogni numero di due o più cifre: in una frase di frenata deve essercene uno solo."""
    return [m for m in _NUMBER.finditer(s) if len(re.sub(r"[^0-9]", "", m.group())) >= 2]


_BOARD_WORD = re.compile(
    r"\s*(?:m|metre|metres|meter|meters|mt)?\s*(?:board|boards|marker|markers|sign|signs)\b")


def _brake(q: str) -> tuple[str, int, int] | None:
    if NEGATION.search(q) or HEDGE.search(q):
        return None
    multi = board_numbers(q)
    mentioned = {slug for slug, phrases in OBJECTS.items()
                 if any(alias_regex(p).search(q) for p in phrases)}
    if multi:
        if len(multi) > 1 or mentioned:
            return None
        m = multi[0]
        if not m.group().isdigit() or int(m.group()) not in BOARDS:
            return None
        if NOT_BOARD_UNIT.match(q, m.end()) or relative_near(q, [m.start()]):
            return None
        word = _BOARD_WORD.match(q, m.end())
        return f"board:{int(m.group())}", m.start(), word.end() if word else m.end()
    if len(mentioned) != 1:
        return None
    slug = next(iter(mentioned))
    alts = "|".join(re.escape(p) for p in OBJECTS[slug])
    m = re.search(rf"(?:{_BRAKE_EN}|{_BRAKE_IT})(?P<obj>{alts})(?![a-z0-9])", q)
    if not m or relative_near(q, [m.start("obj")]):
        return None
    return f"object:{slug}", m.start("obj"), m.end("obj")


# --- marce ------------------------------------------------------------------

_ORD = {
    "1": ["first", "1st", "prima", "primo"], "2": ["second", "2nd", "seconda", "secondo"],
    "3": ["third", "3rd", "terza", "terzo"], "4": ["fourth", "4th", "quarta", "quarto"],
    "5": ["fifth", "5th", "quinta", "quinto"], "6": ["sixth", "6th", "sesta", "sesto"],
}
_ORD_WORD = {w: d for d, ws in _ORD.items() for w in ws}
_ORD_IT_IN = {"prima", "seconda", "terza", "quarta", "quinta", "sesta"}  # «in seconda»
# Tutto quello che somiglia a una marcia: ordinali in parole o «Nth», e cifre sole.
_GEAR_LIKE = re.compile(
    r"\b(?:" + "|".join(_ORD_WORD) + r"|[0-9]+(?:st|nd|rd|th))\b"
    r"|(?<![\w.,])[0-9](?!\w|[.,][0-9])")
# «first» avverbio: a inizio frase o inciso, seguito da un soggetto o da un verbo.
_FIRST_ADVERB = re.compile(
    r"(?:^|[,;:.!?]\s*|\b(?:and|then)\s+)first\s+"
    r"(?:you|we|i|i'm|you're|we're|they|let's|lets|brake|braking|turn|lift|go|get|take|look"
    r"|make|focus|try|keep|use)\b")
_GEAR = r"(?:gear|gears|marcia|marce)"
# Gli attacchi di una marcia: «down to», «shift (down) to», «shifting down to»,
# «switch (down) to», «drop (down) to» (10/11: le guide di Monza e Silverstone).
_LEAD_VERB = r"(?:shift(?:ing|s)?|switch(?:ing|es)?|drop(?:ping|s)?)"
_DIGIT_LEAD = r"(?:down to|" + _LEAD_VERB + r"(?:\s+(?:down|up))?(?:\s+(?:to|into))?)"
_ORD_LEAD = r"(?:down to|" + _LEAD_VERB + r"(?:\s+(?:down|up))?(?:\s+(?:to|into))?|into)"
UNIT_AFTER_DIGIT = re.compile(
    r"\s*(?:laps?\b|giri\b|giro\b|kph|km/h|kmh|km\b|mph|corners?\b|curva\b|curve\b"
    r"|seconds?\b|secs?\b|s\b|secondi\b|metres?\b|meters?\b|metri\b|m\b|mt\b|tenths?\b"
    r"|decimi\b|%|psi\b|bar\b|clicks?\b|rpm\b|or\b|o\b|and\b|e\b|to\b)")
_NOUN_AFTER_ORD = (
    r"(?!\s+(?:place|position|posizione|corners?|curva|curve|laps?|giro|sector|settore"
    r"|time|volta|half|part|apex|brak\w*|chicane|run|step|steps)\b"
    # «and»/«or» bloccano solo se dopo viene un'altra marcia («second and third»):
    # «shift down to third and aim…» è una marcia sola (10/11).
    r"|\s+(?:or|o|and|e)\s+(?:the\s+)?(?:" + "|".join(_ORD_WORD) + r"|[0-9]\b))")


def _gear_tokens(q: str) -> list[re.Match]:
    adverbs = {m.start() + m.group().index("first") for m in _FIRST_ADVERB.finditer(q)}
    return [m for m in _GEAR_LIKE.finditer(q) if m.start() not in adverbs]


def _gear_value(q: str, m: re.Match) -> str | None:
    """La marcia del segno m, se sta accanto a un attacco («down to», «shift») o a «gear»."""
    tok, at = m.group(), m.start()

    def here(pattern: str) -> bool:
        return any(x.start("t") == at for x in re.finditer(pattern, q))

    t = rf"(?P<t>{re.escape(tok)})"
    if tok.isdigit():
        if tok not in "123456":
            return None
        if UNIT_AFTER_DIGIT.match(q, m.end()) and not re.match(rf"\s*{_GEAR}\b", q[m.end():]):
            return None
        ok = (here(rf"\b{_DIGIT_LEAD}\s+{t}(?!\w)")
              or here(rf"\b{_GEAR}\s+{t}(?!\w)")
              or here(rf"(?<![\w.,]){t}\s*{_GEAR}\b"))
        return tok if ok else None
    digit = _ORD_WORD.get(tok) or (tok[0] if len(tok) == 3 and tok[0] in "123456" else None)
    if digit is None:
        return None
    ok = (here(rf"\b{t}\s+{_GEAR}\b")
          or here(rf"\b{_GEAR}\s+{t}\b{_NOUN_AFTER_ORD}")
          or here(rf"\b{_ORD_LEAD}\s+{t}\b{_NOUN_AFTER_ORD}")
          or (tok in _ORD_IT_IN and here(rf"\bin\s+{t}\b{_NOUN_AFTER_ORD}")))
    return digit if ok else None


def gear_positions(s: str) -> list[int]:
    """Dove, nel testo già normalizzato, c'è un segno che vale come marcia."""
    return [m.start() for m in _gear_tokens(s) if _gear_value(s, m)]


def _gear(q: str) -> tuple[str, int, int] | None:
    if NEGATION.search(q) or HEDGE.search(q):
        return None
    tokens = _gear_tokens(q)
    if len(tokens) != 1:
        return None
    m = tokens[0]
    value = _gear_value(q, m)
    if value is None:
        return None
    word = re.compile(rf"\s+{_GEAR}\b").match(q, m.end())
    return value, m.start(), word.end() if word else m.end()


# --- apice e cordolo ----------------------------------------------------------

def _adjacent(a: str, b: str, q: str) -> tuple[int, int] | None:
    """Dove a e b stanno vicini: in mezzo al più una parola, solo spazi o trattini."""
    gap = r"[ -]+(?:[\w']+[ -]+)?"
    m = re.search(rf"\b(?:{a}){gap}(?:{b})\b|\b(?:{b}){gap}(?:{a})\b", q)
    return m.span() if m else None


def _present(kinds: dict[str, str], q: str) -> set[str]:
    return {k for k, w in kinds.items() if re.search(rf"\b(?:{w})\b", q)}


_APEX_KINDS = {
    "early": r"early|earlier|anticipat\w*|presto",
    "middle": r"mid|middle|centre|center|central\w*|centrale",
    "late": r"late|later|tardi\w*|tardo|ritardat\w*",
}


def _apex(q: str) -> tuple[str, int, int] | None:
    if NEGATION.search(q) or NEGATIVE_SENSE.search(q):
        return None
    kinds = _present(_APEX_KINDS, q)
    if len(kinds) != 1:
        return None
    k = next(iter(kinds))
    at = _adjacent(_APEX_KINDS[k], r"apex|apexes|apexing|apice|apici", q)
    return None if at is None else (k, *at)


_KERB = r"kerb|kerbs|curb|curbs|cordolo|cordoli"
_KERB_POS = {
    "entry": r"entry|turn-in|turn in|ingresso|entrata|inserimento",
    "apex": r"apex|apice",
    "exit": r"exit|uscita",
}


def _kerb(q: str) -> tuple[str, int, int] | None:
    if NEGATIVE_SENSE.search(q):
        return None
    pos = _present(_KERB_POS, q)
    if NEGATION.search(q):
        none = re.search(
            rf"^(?:you\s+)?(?:don't use|do not use|dont use|never use|avoid|no|without)\s+"
            rf"(?:the\s+|any\s+)?(?:{_KERB})$"
            rf"|^(?:non usare|non toccare|non prendere|evita|senza)\s+(?:il\s+|i\s+)?(?:{_KERB})$", q)
        return ("none", 0, len(q)) if none and not pos else None
    if len(pos) != 1:
        return None
    p = next(iter(pos))
    at = _adjacent(_KERB_POS[p], _KERB, q)
    return None if at is None else (p, *at)


_NORMALIZERS = {"brake": _brake, "gear": _gear, "apex": _apex, "kerb": _kerb}
TYPES = ("brake", "gear", "apex", "kerb", "line", "mistake")


def locate(type_: str, quote: str) -> tuple[str, int, int] | None:
    """Valore, inizio e fine del suo segno nella citazione già normalizzata con `fold`."""
    fn = _NORMALIZERS.get(type_)
    return fn(quote) if fn else None


def sentence_reason(type_: str, sentence: str, at: int) -> str | None:
    """Controlli sulla frase intera che contiene la citazione; `at` è il segno del valore."""
    if NEGATION.search(sentence):
        return "negazione"
    if type_ in ("apex", "kerb") and NEGATIVE_SENSE.search(sentence):
        return "negazione"
    if type_ in ("brake", "gear") and HEDGE.search(sentence):
        return "valore_non_normalizzabile"
    if type_ == "brake":
        nums = board_numbers(sentence)
        if len(nums) > 1:
            return "valore_non_normalizzabile"
        if nums and NOT_BOARD_UNIT.match(sentence, nums[0].end()):
            return "valore_non_normalizzabile"
        if relative_near(sentence, [at]):
            return "valore_non_normalizzabile"
    if type_ == "gear":
        m = re.match(r"[0-9]+", sentence[at:])
        if m and m.group().isdigit() and len(m.group()) == 1:
            rest = sentence[at + 1:]
            if UNIT_AFTER_DIGIT.match(rest) and not re.match(rf"\s*{_GEAR}\b", rest):
                return "valore_non_normalizzabile"
    return None


# --- chi parla ------------------------------------------------------------------

# Un ruolo si prova solo detto in prima persona: una di queste forme nella citazione già
# normalizzata con `fold`, senza negazione. Una parola sola («race», «coach») non basta:
# «the racing line», «the Coach Dave setup» non dicono niente di chi parla.
# Pilota vuol dire un campionato o un team: «I race in public lobbies», «corro con la
# Ferrari», «sono un pilota della domenica» non sono un pilota.
ROLE_CONTEXT = (r"(?:championship|campionato|league|lega|series|serie|gt\W+world|gtwc|lfm|sro"
                r"|esports|endurance|team|scuderia)")
# La parola del campionato o del team entro le 6 parole che seguono.
_NEAR_CONTEXT = rf"(?:\W+[\w']+){{0,5}}?\W+{ROLE_CONTEXT}\b"
# Un coach dice chi o cosa allena: «I teach you to brake», «I coach myself» non bastano.
COACH_OBJECTS = (r"(?:drivers|driving|sim racing|racing|people to drive|students|clients"
                 r"|racecraft|guida|piloti)")
# L'oggetto entro le 4 parole che seguono il verbo.
_NEAR_OBJECT = rf"(?:\W+[\w']+){{0,3}}?\W+{COACH_OBJECTS}\b"
ROLE_PATTERNS = {
    "coach": [re.compile(p) for p in (
        r"\bi(?:'m| am) (?:an? )?(?:(?:driver|driving|sim racing) )?(?:coach|instructor)\b",
        r"\bi (?:coach|teach)\b" + _NEAR_OBJECT,
        r"\b(?:sono|faccio) (?:il |un |l')?(?:coach|istruttore)\b",
        r"\binsegno (?:a guidare|guida|ai piloti)\b",
    )],
    "pilota": [re.compile(p) for p in (
        r"\bi race (?:in|for)\b" + _NEAR_CONTEXT,
        r"\bi drive for\b" + _NEAR_CONTEXT,
        r"\bi(?:'m| am) a driver for\b" + _NEAR_CONTEXT,
        r"\bcorro (?:nel|per|in)\b" + _NEAR_CONTEXT,
        rf"^(?=.*\b{ROLE_CONTEXT}\b).*\bsono (?:un )?pilota\b",
    )],
}
# Frasi che non provano mai un ruolo: si tolgono dalla citazione prima di cercare le forme.
ROLE_EXCLUDED = ("racing line", "race line", "coach dave", "my coach", "il mio coach",
                 "mio istruttore", "della domenica")
# Parole riferite: chi parla dice il ruolo di un altro, o lo cita. Vale nella citazione
# e nelle 6 parole che la precedono nel testo.
REPORTED = re.compile(r"[\"«»„]|\b(?:says|said|dice|disse|ha detto|secondo lui|according to)\b")


def proves_role(role: str, quote: str, before: str = "") -> bool:
    """La citazione dice in prima persona che chi parla ha quel ruolo.

    `before` è il testo che precede la citazione: se nelle sue ultime 6 parole qualcuno
    «dice» o apre le virgolette, il ruolo è riferito e non vale.
    """
    q = fold(quote)
    if NEGATION.search(q) or REPORTED.search(q):
        return False
    if REPORTED.search(" ".join(fold(before).split()[-6:])):
        return False
    for phrase in ROLE_EXCLUDED:
        q = alias_regex(phrase).sub(" ", q)
    return any(p.search(q) for p in ROLE_PATTERNS.get(role, []))


# Un tempo sul giro come si scrive: «1:41.2», «1:41,234».
LAP_TIME = re.compile(r"[0-9]{1,2}:[0-9]{2}[.,][0-9]{1,3}")
# Un nome detto nel testo vale solo dopo una presentazione.
NAME_LEADS = ("i'm", "i am", "my name is", "sono", "mi chiamo")

# Parole del vocabolario dei fatti: un nome o un'auto fatti di queste non sono un nome
# né un'auto, ma un pezzo di consiglio copiato nel campo sbagliato.
VOCAB_TERMS: tuple[str, ...] = tuple(sorted(
    {a for corners in CORNERS.values() for aliases in corners.values() for a in aliases}
    | {p for phrases in OBJECTS.values() for p in phrases}
    | {w for words in _ORD.values() for w in words}
    | {"gear", "gears", "marcia", "marce", "board", "boards", "marker", "markers",
       "apex", "apexes", "apice", "apici", "early", "middle", "mid", "late", "later",
       "kerb", "kerbs", "curb", "curbs", "cordolo", "cordoli", "entry", "exit",
       "ingresso", "uscita", "brake", "braking", "frenata", "staccata"}))
