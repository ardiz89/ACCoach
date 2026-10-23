"""Il controllo Safari 9, importabile.

Il tablet del pilota e' un iPad 3 con iOS 9.3.6: Safari 9 capisce ES5 e le
template string, e poco altro. Qui si cerca, in uno script o in un foglio di
stile, tutto cio' che su quel Safari non parte: una pagina che non parte sul
tablet e' una pagina che il pilota non vede in macchina.

Il controllo guarda il *codice*: prima toglie commenti, stringhe e letterali
regex (la parola «const» dentro un testo non e' un `const`), poi cerca le
forme vietate come token interi. Dentro una template string i `${...}` sono
codice e si controllano.
"""
import re

# I file che /tablet carica; quelli che esistono si controllano tutti.
TABLET_FILES = ("i18n.js", "lankey.js", "tablet.js", "tablet.css")

_JS_FORBIDDEN = (
    (r"\blet\b", "let"),
    (r"\bconst\b", "const"),
    (r"\bclass\b", "class"),
    (r"\basync\b", "async"),
    (r"\bawait\b", "await"),
    (r"=>", "freccia =>"),
    (r"\.\.\.", "spread/rest ..."),
    (r"\?\.(?!\d)", "optional chaining ?."),
    (r"\?\?", "nullish ??"),
    (r"\bfetch\s*\(", "fetch()"),
    (r"\.padStart\s*\(", ".padStart()"),
    (r"\.padEnd\s*\(", ".padEnd()"),
    (r"\bIntl\.", "Intl"),
    (r"\bObject\.entries\s*\(", "Object.entries()"),
    (r"\bObject\.values\s*\(", "Object.values()"),
    (r"\bURLSearchParams\b", "URLSearchParams"),
    (r"\bquerySelectorAll\s*\([^()]*\)\s*\.forEach\b", ".forEach su querySelectorAll"),
    (r"\bgetElementsBy\w+\s*\([^()]*\)\s*\.forEach\b", ".forEach su getElementsBy*"),
)

# Regole in piu' per un file solo. In tablet.js nessun `.forEach`: il controllo
# generico lo vede solo attaccato a `querySelectorAll(...)`, e una NodeList
# messa prima in una variabile gli sfugge. Nella vista si scrivono cicli `for`.
_PER_FILE = {
    "tablet.js": ((r"\.forEach\s*\(", ".forEach (in tablet.js solo cicli for)"),),
}

_CSS_FORBIDDEN = (
    (r"display\s*:\s*(inline-)?grid", "display: grid"),
    (r"\bclamp\s*\(", "clamp()"),
    (r"var\s*\(\s*--", "var(--...)"),
    (r"(?<![\w-])gap\s*:", "gap:"),
    (r"(?<![\w-])min\s*\(", "min()"),
    (r"(?<![\w-])max\s*\(", "max()"),
)

# Dopo questi caratteri una «/» apre un letterale regex, non una divisione.
_REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^") | {""}


def _strip_js(src):
    """Il sorgente senza commenti, stringhe e regex; le righe restano le stesse."""
    out = []
    i, n = 0, len(src)
    # pila: "code" oppure, per ogni template aperta, la profondita' di graffe
    stack = []          # un elemento per ogni `${` aperto: graffe interne
    last = ""           # ultimo carattere di codice non bianco

    def blank(text):
        return "".join(c if c == "\n" else " " for c in text)

    def template(i):
        """Consuma il testo di una template da i fino a `${` o alla chiusura."""
        start = i
        while i < n:
            c = src[i]
            if c == "\\":
                i += 2
            elif c == "`":
                out.append(blank(src[start:i + 1]))
                return i + 1, False
            elif c == "$" and src[i + 1:i + 2] == "{":
                out.append(blank(src[start:i]) + "  ")
                stack.append(0)
                return i + 2, True
            else:
                i += 1
        out.append(blank(src[start:i]))
        return i, False

    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(blank(src[i:j]))
            i = j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(blank(src[i:j]))
            i = j
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            out.append(blank(src[i:j + 1]))
            i, last = j + 1, "x"
        elif c == "`":
            out.append(" ")
            i, _ = template(i + 1)
            last = "x"
        elif c == "/" and last in _REGEX_AFTER:
            j, in_class = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            out.append(blank(src[i:j + 1]))
            i, last = j + 1, "x"
        else:
            if stack:
                if c == "{":
                    stack[-1] += 1
                elif c == "}":
                    if stack[-1] == 0:
                        stack.pop()
                        out.append(" ")
                        i, _ = template(i + 1)
                        last = "x"
                        continue
                    stack[-1] -= 1
            out.append(c)
            if not c.isspace():
                last = c if not (c.isalnum() or c in "_$") else "x"
            i += 1
    return "".join(out)


def _strip_css(src):
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), src,
                  flags=re.S)


def safari9_problems(src, kind, name=None):
    """Le righe di `src` che Safari 9 non digerisce: ["<riga>: <cosa>", ...].

    `name` e' il nome del file, se ha regole sue (`_PER_FILE`)."""
    if kind == "js":
        clean, rules = _strip_js(src), _JS_FORBIDDEN + _PER_FILE.get(name, ())
    elif kind == "css":
        clean, rules = _strip_css(src), _CSS_FORBIDDEN
    else:
        raise ValueError("kind deve essere 'js' o 'css'")
    found = []
    for pattern, what in rules:
        for m in re.finditer(pattern, clean):
            found.append((clean.count("\n", 0, m.start()) + 1, what))
    return ["%d: %s" % (line, what) for line, what in sorted(found)]
