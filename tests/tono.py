"""Il controllo del tono: le regole del pilota sui testi dell'app, come codice.

Non è un test (`test_tono.py` lo è): è lo strumento che i task di riscrittura
usano per sapere cosa resta da fare. Fa tre cose.

* `violations(testo, lingua)` applica le regole a un testo e dice quali rompe.
* `SURFACES` raccoglie *tutti* i testi di ogni superficie dell'app, in italiano
  e in inglese, con una chiave che dice dove stanno (file e riga).
* `PENDING` elenca le superfici non ancora riscritte. `test_tono.py` pretende
  zero violazioni solo da quelle che ne sono fuori: ogni task che riscrive una
  superficie la toglie da qui, e da quel momento non può più peggiorare.

Le regole sono quelle della spec dei testi (2026-10-21), «Le regole, come si
controllano». Il modello è `tests/test_howto_tono.py`, che le applicava solo al
«Come si fa» e alla Pagella.
"""
from __future__ import annotations

import ast
import functools
import html
import html.parser
import re
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "accoach"
WEB = SRC / "web"

RULES = ("emoji", "colon", "dash", "bang", "long", "decimal", "unit", "slogan")

# Misure mie per «frasi brevi» (spec, «Scelte mie» 4): 25 parole in generale,
# otto per la voce, che si deve capire al primo ascolto a 200 km/h.
MAX_WORDS = 25
MAX_WORDS_BY_SURFACE = {"coach": 8}

# Due frasi uguali sono un difetto solo se sono frasi: «Giro» o «Salva» in due
# schermate sono etichette, non la stessa frase detta due volte.
MIN_DUP_WORDS = 4

# La lista vive qui e si allunga quando il pilota ne trova un'altra.
SLOGANS = (
    "bella costanza", "ottimo lavoro", "continua così", "sei pronto", "scopri",
    "al volo", "a colpo d'occhio",
    "nice consistency", "great job", "keep it up", "you're all set", "discover",
    "at a glance",
)

# --- le regole --------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_SENTINEL = "\u00a7"        # un segnaposto, dopo che il suo contenuto è sparito
_TAG = re.compile(r"<[^>]*>")

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF"     # pittogrammi, emoticon, trasporti, simboli
    "\u2600-\u27BF"              # simboli vari e dingbat (✓ ⚡ ☀)
    "\u2B00-\u2BFF"              # frecce e simboli vari (⭐)
    "\u2300-\u23FF\u2139"          # tecnici (⏸ ⏱ ⌚) e ℹ; le frecce 2190-21FF restano ammesse
    "\u25A0-\u25FF"              # forme geometriche (▶ ● ▲)
    "\uFE0F\u200D]")

# Orari, tempi sul giro e rapporti: i soli due punti che non sono un'etichetta.
# In più gli indirizzi e i percorsi, che li hanno per costruzione.
_COLON_OK = re.compile(
    r"\d{1,2}:\d{2}(?:[.:]\d+)*"      # 22:58   1:47.427   0:59.1
    r"|\d+:\d+"                       # 3:1
    r"|https?://\S*"                  # indirizzi
    r"|\b[A-Za-z]:[\\/]")             # C:\...

_LAP_TIME = re.compile(r"\d{1,2}:\d{2}(?:\.\d+)?")
_VERSION = re.compile(r"\d+(?:\.\d+){2,}|\b[Vv]\d+\.\d+|\bPython \d+\.\d+")

# «°» seguito da una parola è un ordinale italiano («2° giro»), non un'unità.
_UNITS = (r"(?:%|km/h|mph|kPa|rpm|kW|Nm|ms|mm|cm|km|kg|min|psi|Hz|bar|°C"
          r"|°(?!\s+[^\W\d_])|s|m|L|h)")
_NUM_UNIT = re.compile(rf"(?:\d(?:[.,]\d+)?|(?<![^\W\d_]){_SENTINEL}){_UNITS}(?![\w/])")

_DASH_SPACED = re.compile(r"\s[-–—]\s|[–—]")
_VALUE_BEFORE = re.compile(rf"[\d%°§]\s*(?:{_UNITS})?\s*$")
_VALUE_AFTER = re.compile(rf"\s*[\d§][\d.,]*\s*({_UNITS}(?![\w/]))?")
# «1.000» (migliaia) e «34.512» (un tempo di settore, scritto come un tempo sul giro).
_THOUSANDS = re.compile(r"\b[1-9]\d{0,2}(?:\.\d{3})+\b")


def placeholders(text: str) -> set[str]:
    """I segnaposti `{nome}` di un testo, per nome (senza le specifiche di formato)."""
    return {re.split(r"[:!|]", m[1:-1], maxsplit=1)[0].strip()
            for m in _PLACEHOLDER.findall(text or "")}


def _plain(text: str) -> str:
    """Il testo come lo legge chi guarda lo schermo: niente marcatori HTML, e i
    segnaposti ridotti a un segno solo (il loro contenuto non è testo)."""
    text = html.unescape(_TAG.sub("", text or ""))
    return _PLACEHOLDER.sub(_SENTINEL, text.replace("’", "'"))


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def words(sentence: str) -> int:
    return len(re.findall(r"\w[\w'’°%/.,:-]*", sentence))


def _dash_is_between_values(text: str) -> bool:
    """Un intervallo: da una parte e dall'altra un valore nudo, con la sua unità
    se ce l'ha («22 °C — 30 °C»). «Curva 3 — 4 decimi persi» è enfasi."""
    for m in _DASH_SPACED.finditer(text):
        before, after = text[:m.start()], text[m.end():]
        v = _VALUE_AFTER.match(after)
        if _VALUE_BEFORE.search(before) and v:
            if v.group(1) or not re.match(r"\s*[^\W\d_]", after[v.end():]):
                continue
        return False
    return True


def violations(text: str, lang: str, max_words: int = MAX_WORDS) -> list[str]:
    """Una voce per regola violata, nell'ordine di `RULES`."""
    out: list[str] = []
    plain = _plain(text)
    if not plain.strip():
        return out
    if _EMOJI.search(plain):
        out.append("emoji")
    if ":" in _COLON_OK.sub("", plain):
        out.append("colon")
    # Un solo trattino (o «–», «—») fra due cifre è un intervallo, non un
    # modo di dare enfasi; un testo che è solo il segno è una cella vuota.
    if plain.strip() not in {"-", "–", "—"} and _DASH_SPACED.search(plain) \
            and not _dash_is_between_values(plain):
        out.append("dash")
    if "!" in plain:
        out.append("bang")
    if any(words(s) > max_words for s in _sentences(plain)):
        out.append("long")
    numbers = _THOUSANDS.sub(" ", _VERSION.sub(" ", _LAP_TIME.sub(" ", plain)))
    if lang == "it" and re.search(r"\d\.\d", numbers):
        out.append("decimal")
    elif lang == "en" and re.search(r"(?<![\d,])\d+,\d{1,2}(?!\d)", numbers):
        out.append("decimal")
    if _NUM_UNIT.search(plain):
        out.append("unit")
    low = plain.lower()
    if any(re.search(rf"(?<!\w){re.escape(s)}(?!\w)", low) for s in SLOGANS):
        out.append("slogan")
    return out


# --- i testi di ogni superficie --------------------------------------------

Entries = dict[str, dict[str, str]]


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:          # un file fuori dal repo (i test ne fabbricano)
        return path.name


def _text_of(node: ast.AST) -> list[tuple[str, str]]:
    """Le foglie di testo di un valore: [(sottochiave, testo)]. Un valore che non
    è testo (una chiamata, un nome) non produce nulla."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [("", node.value)]
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                name = v.value.id if isinstance(v.value, ast.Name) else "x"
                parts.append("{" + name + "}")
        return [("", "".join(parts))]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text_of(node.left), _text_of(node.right)
        if len(left) == 1 == len(right) and not left[0][0] and not right[0][0]:
            return [("", left[0][1] + right[0][1])]
        return []
    if isinstance(node, ast.Dict):
        out = []
        for k, v in zip(node.keys, node.values):
            name = k.value if isinstance(k, ast.Constant) else ast.unparse(k) if k else "**"
            for sub, text in _text_of(v):
                out.append((f"[{name}]{sub}", text))
        return out
    if isinstance(node, (ast.Tuple, ast.List)):
        out = []
        for i, v in enumerate(node.elts):
            out.extend((f"[{i}]{sub}", text) for sub, text in _text_of(v))
        return out
    return []


def lang_pairs(path: Path, tree: ast.AST | None = None) -> Entries:
    """I dizionari `{"it": …, "en": …}` di un modulo Python, anche quando i due
    valori sono a loro volta tabelle (`{"it": {k: testo}, "en": {k: testo}}`):
    una voce per coppia, con la chiave «file:riga» (e la sottochiave)."""
    if tree is None:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    name = rel(path)
    out: Entries = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        named = {k.value: v for k, v in zip(node.keys, node.values)
                 if isinstance(k, ast.Constant) and k.value in ("it", "en")}
        if set(named) != {"it", "en"}:
            continue
        side = {lg: dict(_text_of(v)) for lg, v in named.items()}
        for sub in sorted(set(side["it"]) | set(side["en"])):
            entry = {lg: side[lg][sub] for lg in ("it", "en") if sub in side[lg]}
            if entry:
                out[f"{name}:{node.lineno}{sub}"] = entry
    out.update(_branch_pairs(tree, name))
    return out


_LANG_NAMES = {"lang", "lg", "language"}


def _is_lang_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _LANG_NAMES
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Name) and node.func.id == "current_language"
    if isinstance(node, ast.BoolOp):
        return any(_is_lang_expr(v) for v in node.values)
    return False


def _it_branch(test: ast.AST) -> str | None:
    """Dei due rami di `if lang == "it"`: quale è l'italiano? 'body', 'orelse' o None."""
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and _is_lang_expr(test.left) and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value in ("it", "en")
            and isinstance(test.ops[0], (ast.Eq, ast.NotEq))):
        return None
    positive = isinstance(test.ops[0], ast.Eq)
    return ("body" if positive else "orelse") if test.comparators[0].value == "it" \
        else ("orelse" if positive else "body")


def _branch_texts(stmts: list[ast.stmt]) -> list[str]:
    """I testi scritti da un ramo, nell'ordine del sorgente: valori di `return`,
    assegnazioni e `+=`. Gli `if lang` annidati li conta il loro giro."""
    found: list[tuple[int, int, str]] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.If) and _it_branch(node.test):
            return
        value = getattr(node, "value", None) if isinstance(
            node, (ast.Return, ast.Assign, ast.AugAssign, ast.Expr)) else None
        if value is not None:
            leaves = _text_of(value)
            if len(leaves) == 1 and not leaves[0][0]:
                found.append((node.lineno, node.col_offset, leaves[0][1]))
        for child in ast.iter_child_nodes(node):
            visit(child)

    for st in stmts:
        visit(st)
    return [t for _, _, t in sorted(found)]


def _branch_pairs(tree: ast.AST, name: str) -> Entries:
    """I testi scritti con `if lang == "it": … else: …` (o la stessa cosa in un
    `x if lang == "it" else y`): i testi dei due rami in coppia per posizione. Se
    i rami non ne scrivono lo stesso numero, i senza-compagno restano a una
    lingua sola, così le regole si applicano comunque."""
    out: Entries = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            which = _it_branch(node.test)
            if not which:
                continue
            body, orelse = _branch_texts(node.body), _branch_texts(node.orelse)
        elif isinstance(node, ast.IfExp):
            which = _it_branch(node.test)
            if not which:
                continue
            body = [t for _, t in _text_of(node.body)]
            orelse = [t for _, t in _text_of(node.orelse)]
        else:
            continue
        it, en = (body, orelse) if which == "body" else (orelse, body)
        for i in range(max(len(it), len(en))):
            entry = {}
            if i < len(it):
                entry["it"] = it[i]
            if i < len(en):
                entry["en"] = en[i]
            out[f"{name}:{node.lineno}@{i}"] = entry
    return out


def _tables(path: Path, names: tuple[str, ...], pair: Callable[[str, str], dict]) -> Entries:
    """Le tabelle `NOME: dict[str, str]` di un modulo (la lingua è la chiave)."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out: Entries = {}
    for node in ast.walk(tree):
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id in names and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                    out[f"{rel(path)}:{target.id}[{k.value[:40]}]"] = pair(k.value, v.value)
    return out


def _merge(*parts: Entries) -> Entries:
    out: Entries = {}
    for p in parts:
        out.update(p)
    return out


def _modules(*names: str) -> Entries:
    return _merge(*(lang_pairs(SRC / n) for n in names))


# -- il catalogo del report e della pagina Ingegnere (i18n.js) --

def _entry_end(src: str, start: int) -> int:
    """La graffa che chiude una voce: i valori sono backtick e possono contenerne."""
    i = start
    while i < len(src):
        c = src[i]
        if c == "`":
            i = src.index("`", i + 1) + 1
            continue
        if c == "}":
            return i
        i += 1
    raise ValueError("voce del catalogo senza fine")


_CAT_ENTRY = re.compile(r'"([\w.\-]+)"\s*:\s*\{\s*(?=en:|it:)')
_CAT_VALUE = re.compile(r"\b(en|it)\s*:\s*`([^`]*)`")


@functools.lru_cache(maxsize=1)
def i18n_catalogue() -> Entries:
    """`CAT` di `web/i18n.js`: {chiave: {it, en}}, voci su più righe comprese."""
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    out: Entries = {}
    for m in _CAT_ENTRY.finditer(src):
        body = src[m.end():_entry_end(src, m.end())]
        out[m.group(1)] = {lg: text for lg, text in _CAT_VALUE.findall(body)}
    return out


_JS_STRING = re.compile(r'"([^"\n]*)"|\'([^\'\n]*)\'|`([^`]*)`')
_ENGINEER_FILES = ("engineer.html", "engineer.js")
_REPORT_FILES = ("index.html", "app.js", "tour.js", "test.html", "test.js")


def _literals(name: str) -> set[str]:
    src = (WEB / name).read_text(encoding="utf-8")
    # Una chiave chiesta dentro un modello (`${t("eng.click")}`) sta dentro il
    # letterale col backtick: si cerca anche come argomento di `t(…)` e `tf(…)`.
    return {a or b or c for a, b, c in _JS_STRING.findall(src)} \
        | set(re.findall(r"\btf?\(\s*[\"']([\w.\-]+)[\"']", src))


def _asked(names: tuple[str, ...], keys: set[str]) -> set[str]:
    """Le chiavi che questi file chiedono: per nome intero, o come prefisso
    («pag.err.» + k) quando la chiave è costruita a runtime."""
    lits: set[str] = set()
    for n in names:
        lits |= _literals(n)
        if n.endswith(".html"):
            lits |= set(re.findall(r'data-i18n[\w-]*="([^"]+)"',
                                   (WEB / n).read_text(encoding="utf-8")))
    prefixes = {s for s in lits if s.endswith(".") and len(s) > 3}
    return {k for k in keys if k in lits or any(k.startswith(p) for p in prefixes)}


@functools.lru_cache(maxsize=1)
def _engineer_keys() -> frozenset[str]:
    """Le chiavi del catalogo che solo la pagina Ingegnere usa. Il giro guidato
    dell'Ingegnere (`tour.e*`) si costruisce con `t("tour.e1.t")` e simili."""
    cat = i18n_catalogue()
    used_eng = _asked(_ENGINEER_FILES, set(cat))
    used_report = _asked(_REPORT_FILES, set(cat))
    return frozenset(used_eng - used_report)


# Il report si riscrive in due tempi: prima la Pagella, il piano, la sessione,
# la navigazione e l'accoglienza (`report_a`), poi le schede di analisi
# (`report_b`). Il prefisso della chiave decide da che parte sta.
REPORT_A_PREFIXES = frozenset((
    "pag howto adv ses flow recap plan train rec prog dh trends recur cornerses "
    "cons tour tab tabgroup nav title demo lang combo empty load err modal kbd "
    "badge btn lbl ctl lvl focus live debrief").split())


def _report(part: str | None = None) -> Entries:
    eng = _engineer_keys()
    out = {}
    for k, v in i18n_catalogue().items():
        if k in eng:
            continue
        in_a = k.split(".", 1)[0] in REPORT_A_PREFIXES
        if part is None or (part == "a") == in_a:
            out[f"web/i18n.js:{k}"] = v
    return out


def _engineer() -> Entries:
    eng = _engineer_keys()
    pages = {f"web/i18n.js:{k}": v for k, v in i18n_catalogue().items() if k in eng}
    files = sorted((SRC / "engineer").rglob("*.py"))
    py = _merge(*(lang_pairs(p) for p in files))
    # Le frasi dei rimedi sono scritte in inglese e tradotte da una tabella.
    common = SRC / "engineer" / "profiles" / "_common.py"
    tr = _tables(common, ("_IT",), lambda en, it: {"en": en, "it": it})
    labels = _tables(SRC / "setup" / "labels.py", ("_IT",), lambda en, it: {"en": en, "it": it})
    return _merge(pages, py, tr, labels)


_BACKEND = ("coaching/debrief.py", "trajectory.py", "coaching/training.py",
            "coaching/howto.py", "pagella.py", "api.py",
            # Anche questi scrivono testi del report e la brief non li nomina:
            # la spec elenca «trends», e chain/flow/phases hanno dizionari it/en.
            "coaching/trends.py", "coaching/chain.py", "coaching/flow.py",
            "coaching/phases.py")


def _report_backend() -> Entries:
    return _modules(*_BACKEND)


# I testi fissi della pagina di prova (`test.js`, `test.html`) e del riquadro
# di prova (`testpanel.py`): sono in italiano soltanto, e la spec li mette dentro
# (il contenuto del protocollo, `test_plan.json`, resta fuori).
_JS_TXT_BLOCK = re.compile(r"const TXT = \{(.*?)\n  \};", re.S)
_JS_TXT_ENTRY = re.compile(r'(\w+):\s*((?:"[^"\n]*"\s*\+?\s*)+),')


def page_js_texts() -> Entries:
    """`TXT` di `test.js`: {chiave: {"it": testo}}, concatenazioni comprese."""
    src = (WEB / "test.js").read_text(encoding="utf-8")
    block = _JS_TXT_BLOCK.search(src)
    if not block:
        return {}
    return {f"web/test.js:TXT.{k}": {"it": "".join(re.findall(r'"([^"\n]*)"', v))}
            for k, v in _JS_TXT_ENTRY.findall(block.group(1))}


class _HtmlText(html.parser.HTMLParser):
    """Il testo che si vede di una pagina: nodi di testo, `placeholder`, `title`."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[int, str]] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        for name, value in attrs:
            if name in ("placeholder", "title") and value and value.strip():
                self.found.append((self.getpos()[0], value.strip()))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip() and re.search(r"[^\W\d_]", data):
            self.found.append((self.getpos()[0], " ".join(data.split())))


def html_texts(path: Path) -> Entries:
    parser = _HtmlText()
    parser.feed(path.read_text(encoding="utf-8"))
    out: Entries = {}
    for i, (line, text) in enumerate(parser.found):
        out[f"web/{path.name}:{line}#{i}"] = {"it": text}
    return out


def _testpanel_texts() -> Entries:
    return _tables(SRC / "testpanel.py", ("_TXT",), lambda k, v: {"it": v})


def _hub() -> Entries:
    from accoach import i18n
    ui = {f"i18n.py:_UI[{k}]": dict(v) for k, v in i18n._UI.items()}
    return _merge(ui, page_js_texts(), html_texts(WEB / "test.html"),
                  _testpanel_texts())


_COACH_FILES = ("coaching/cue.py", "coaching/focus.py", "coaching/pitcall.py",
                "coaching/voice.py")


def static_cue_texts(path: Path) -> set[str]:
    """Le frasi fisse di un modulo del coach: testi passati a una chiamata che
    prende anche una `CueCategory` (il criterio di `tools/render_cues.py`), con
    le f-string in forma «{nome}» e le stringhe spezzate con `+` ricomposte."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out: set[str] = set()
    assigned: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.JoinedStr, ast.Constant, ast.BinOp)):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigned.setdefault(t.id, []).append(node.value)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        args = list(node.args) + [kw.value for kw in node.keywords]
        if not any(isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)
                   and a.value.id == "CueCategory" for a in args):
            continue
        for a in args:
            # Un messaggio costruito prima (`msg = f"…"`) e passato per nome.
            leaves = [x for v in assigned.get(a.id, []) for x in _text_of(v)]                 if isinstance(a, ast.Name) else _text_of(a)
            for sub, text in leaves:
                if not sub and len(text) > 5:
                    out.add(text)
    return out


def cue_english(italian: str) -> str:
    """L'inglese di una frase del coach, come lo darebbe `i18n.cue_text`. Per una
    f-string («Benzina per circa {n} giri») i modelli regex vogliono cifre vere:
    si provano con un numero finto per segnaposto, e si rimettono i segnaposti."""
    from accoach import i18n
    names = list(dict.fromkeys(re.findall(r"\{([^{}]*)\}", italian)))
    if not names:
        return i18n.cue_text(italian, "en")
    # Il singolare ha la sua frase («Qui perdi {n} decimo»): con un numero finto
    # plurale l'inglese verrebbe al plurale, uguale a quello della frase accanto.
    singular = len(names) == 1 and re.search(r"\}\s+(?:giro|decimo)\b", italian)
    fake = {n: ("1" if singular else str(9001 + i)) for i, n in enumerate(names)}
    rendered = _PLACEHOLDER.sub(lambda m: fake[m.group(0)[1:-1]], italian)
    english = i18n.cue_text(rendered, "en")
    if english == rendered:
        return italian                      # nessuno l'ha tradotta
    for n, num in fake.items():
        english = re.sub(rf"(?<!\d){num}(?!\d)", "{" + n + "}", english)
    return english


_COACH_ALL = sorted((SRC / "coaching").glob("*.py")) + [SRC / "engine.py"]


def _coach() -> Entries:
    from accoach import i18n
    out = _modules(*_COACH_FILES, "engine.py")
    out.update({f"i18n.py:_CUE_EN[{it[:40]}]": {"it": it, "en": en}
                for it, en in i18n._CUE_EN.items()})
    # Le frasi fisse che la tabella non conosce: l'inglese è quel che il coach
    # direbbe oggi (la frase italiana, se nessuno l'ha tradotta).
    known = {e["it"] for e in out.values() if "it" in e}
    for path in _COACH_ALL:
        for it in sorted(static_cue_texts(path) - known):
            out[f"{rel(path)}:cue[{it[:40]}]"] = {"it": it, "en": cue_english(it)}
            known.add(it)
    return out


# -- la guida --

_FENCE = re.compile(r"^\s*(```|~~~)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_CODE = re.compile(r"`[^`]*`")
_MD_MARK = re.compile(r"[*_]{1,3}(?=\S)|(?<=\S)[*_]{1,3}")


def markdown_sentences(src: str) -> list[tuple[int, str]]:
    """I paragrafi di un file Markdown come li legge chi guarda la pagina:
    [(riga, testo)]. Niente blocchi di codice, niente codice in linea, niente
    separatori di tabella; una cella di tabella e una voce di elenco sono un
    paragrafo ciascuna."""
    out: list[tuple[int, str]] = []
    para: list[str] = []
    start = 0
    fenced = False

    def flush() -> None:
        if para:
            out.append((start, " ".join(para)))
            para.clear()

    for n, raw in enumerate(src.splitlines(), 1):
        if _FENCE.match(raw):
            flush()
            fenced = not fenced
            continue
        line = raw.strip()
        if fenced or line.startswith("<!--") or re.fullmatch(r"[-*_=\s|:]*", line):
            flush()
            continue
        if line.startswith("|"):
            flush()
            for cell in line.strip("|").split("|"):
                out.append((n, cell.strip()))
            continue
        item = re.match(r"(?:[-*+]|\d+[.)])\s+(.*)", line)
        heading = re.match(r"#+\s*(.*)", line)
        if item or heading:
            flush()
            out.append((n, (item or heading).group(1)))
            continue
        if not para:
            start = n
        para.append(line)
    flush()
    cleaned = []
    for n, text in out:
        text = _MD_MARK.sub("", _MD_CODE.sub("", _MD_LINK.sub(r"\1", text)))
        text = re.sub(r"\s+", " ", text).strip()
        if text and re.search(r"[^\W\d_]", text):
            cleaned.append((n, text))
    return cleaned


def _guide(lang: str) -> Entries:
    """Una lingua della guida: il suo file Markdown e i testi fissi della pagina
    (`guide.py`) in quella lingua. Le due lingue sono due superfici perché si
    riscrivono in due task: la chiave di `guide.py` porta la lingua, così non
    sta in due superfici."""
    name = {"it": "GUIDA.md", "en": "docs/FAQ.md"}[lang]
    out: Entries = {}
    for n, text in markdown_sentences((ROOT / name).read_text(encoding="utf-8")):
        out[f"{name}:{n}"] = {lang: text}
    out.update({f"guide.py:{k}[{lang}]": {lang: v[lang]}
                for k, v in _modules("guide.py").items() if lang in v})
    return out


SURFACES: dict[str, Callable[[], Entries]] = {
    "report_a": functools.lru_cache(maxsize=1)(lambda: _report("a")),
    "report_b": functools.lru_cache(maxsize=1)(lambda: _report("b")),
    "engineer": functools.lru_cache(maxsize=1)(_engineer),
    "report_backend": functools.lru_cache(maxsize=1)(_report_backend),
    "hub": functools.lru_cache(maxsize=1)(_hub),
    "coach": functools.lru_cache(maxsize=1)(_coach),
    "guide_it": functools.lru_cache(maxsize=1)(lambda: _guide("it")),
    "guide_en": functools.lru_cache(maxsize=1)(lambda: _guide("en")),
}

# Le superfici non ancora riscritte. Ogni task che ne riscrive una la toglie.
PENDING: set[str] = set(SURFACES) - {"report_a", "report_b", "report_backend",
                                       "engineer", "hub", "coach",
                                       "guide_it", "guide_en"}


# --- il conto ---------------------------------------------------------------

def surface_violations(name: str, entries: Entries) -> list[tuple[str, str, str]]:
    """[(chiave, lingua, regola)] per ogni testo di una superficie."""
    limit = MAX_WORDS_BY_SURFACE.get(name, MAX_WORDS)
    return [(key, lang, rule)
            for key, entry in entries.items()
            for lang, text in entry.items()
            for rule in violations(text, lang, limit)]


def placeholder_mismatches(entries: Entries) -> list[str]:
    """Le chiavi con entrambe le lingue ma segnaposti diversi."""
    return [k for k, e in entries.items()
            if "@" not in k      # i rami `if lang` sono f-string: i nomi sono espressioni
            and "it" in e and "en" in e and placeholders(e["it"]) != placeholders(e["en"])]


def _norm(sentence: str) -> str:
    return re.sub(r"\W+", " ", sentence.lower()).strip()


def duplicates(surfaces: dict[str, Entries]) -> dict[tuple[str, str], list[str]]:
    """Le frasi (di almeno `MIN_DUP_WORDS` parole) che stanno in due chiavi
    diverse, per lingua: {(lingua, frase): [«superficie|chiave», …]}."""
    seen: dict[tuple[str, str], list[str]] = {}
    for name, entries in surfaces.items():
        for key, entry in entries.items():
            for lang, text in entry.items():
                where = f"{name}|{key}"
                for s in {_norm(x) for x in _sentences(_plain(text))}:
                    if len(s.split()) >= MIN_DUP_WORDS:
                        seen.setdefault((lang, s), [])
                        if where not in seen[(lang, s)]:
                            seen[(lang, s)].append(where)
    # La guida può ripetere i titoli e le etichette dell'interfaccia che cita:
    # un doppione guida-interfaccia non conta (quelli dentro la guida, sì).
    out = {}
    for key, where in seen.items():
        ui = [w for w in where if not w.startswith("guide_")]
        guide = [w for w in where if w.startswith("guide_")]
        kept = (ui if len(ui) > 1 else []) + (guide if len(guide) > 1 else [])
        if kept:
            out[key] = kept
    return out


def census() -> dict[str, dict[str, int]]:
    """Le violazioni per superficie e per regola: la misura del lavoro."""
    out: dict[str, dict[str, int]] = {}
    for name, fn in SURFACES.items():
        count = {r: 0 for r in RULES}
        for _, _, rule in surface_violations(name, fn()):
            count[rule] += 1
        out[name] = count
    return out


if __name__ == "__main__":      # python tests/tono.py
    for name, fn in SURFACES.items():
        entries = fn()
        texts = sum(len(e) for e in entries.values())
        c = census()[name]
        print(f"{name:15} {len(entries):5} voci {texts:5} testi  "
              + "  ".join(f"{r}={n}" for r, n in c.items()))
    print("duplicati:", len(duplicates({n: f() for n, f in SURFACES.items()})))
