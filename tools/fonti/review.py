"""La pagina di controllo per il pilota: una pagina HTML statica, curva per curva.

Niente script e niente risorse esterne: il CSS sta nella pagina. Ogni testo che
viene dalle fonti passa per `html.escape`, e delle fonti si mostrano solo citazioni
di al massimo QUOTE_WORDS parole, mai un testo intero.
"""

from __future__ import annotations

import html
import math
import sqlite3
from pathlib import Path

from tools.fonti import apify, consensus, export, vocab

QUOTE_WORDS = export.QUOTE_WORDS

SECTIONS = (
    ("verificato", "Verificati"),
    ("conteso", "Contesi"),
    ("singolo", "Una fonte sola"),
    ("respinto", "Respinti dal controllo"),
    ("non_confermato", "Non confermati dal controllo"),
    ("descrittivo", "Descrittivi"),
)

CLASS_LABELS = {"gt3": "GT3", "gt3_presunta": "GT3 presunta", "gt4": "GT4",
                "altra": "altra classe", "ignota": "classe ignota"}
TYPE_LABELS = {"brake": "frenata", "gear": "marcia", "apex": "corda", "kerb": "cordolo",
               "line": "linea", "mistake": "errore"}

# Tutte le frasi fisse della pagina, perché il tono si possa controllare.
WHY = {
    "verificato": "Almeno due persone indipendenti dicono la stessa cosa.",
    "conteso": "Le fonti dicono cose diverse, quindi non esce nell'app.",
    "singolo": ("Non bastano persone indipendenti. "
                "Sulla frenata serve anche un coach o un pilota con il suo tempo."),
    "respinto": "Un controllo su altri testi l'ha smentito, quindi non esce nell'app.",
    "non_confermato": ("Nessun altro testo lo dice e nessuno lo smentisce. "
                       "Nell'app esce come una fonte dice."),
    "descrittivo": "Linea ed errori non hanno un valore fisso. Li leggi tu e non escono nell'app.",
}
T = {
    "intro": "Qui vedi cosa dicono le fonti pubbliche, curva per curva.",
    "rule": "Nell'app esce solo un verificato che ha passato il controllo.",
    "spent": "Hai speso {spent} di Apify su un tetto di {cap}.",
    "unspent": "Non hai ancora speso niente di Apify per questa pista.",
    "rejects_title": "Scarti del verificatore",
    "no_rejects": "Il verificatore non ha scartato nessun fatto.",
    "whole": "Le risposte rifiutate intere non restano nel database. Le trovi nell'uscita di ingest.",
    "empty": "Niente qui.",
    "no_facts": "Non c'è ancora nessun fatto per questa pista.",
    "out": "Esce nell'app.",
    "unchecked": "Manca il controllo, quindi non esce ancora.",
    "check_said": "Il controllo dice",
    "quoted": "Cita",
    "open_at": "apri a {t}",
    "open": "apri la fonte",
    "no_link": "link non sicuro, non lo apro",
    "by_number": "curva dal numero",
    "others": "Altre classi o classe ignota",
    "others_why": "Non contano per la GT3. Se dicono un altro valore, la voce è contesa.",
}
TESTI = tuple(WHY.values()) + tuple(T.values()) + tuple(CLASS_LABELS.values())

_CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1b;--mute:#6b6b66;--line:#d9d9d4;--ok:#1f7a3a;--no:#a3261b;--card:#fff}
@media (prefers-color-scheme: dark){:root{--bg:#161615;--fg:#ecece8;--mute:#9a9a94;
--line:#33332f;--ok:#6cc48a;--no:#ec7c70;--card:#1f1f1d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:28px;margin:0 0 8px}h2{font-size:22px;margin:32px 0 8px;border-bottom:1px solid var(--line)}
h3{font-size:17px;margin:20px 0 4px}
.why,.mute{color:var(--mute);margin:0 0 8px}
ul{padding-left:20px;margin:4px 0}
.fact{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;
margin:8px 0;list-style:none}
.n{color:var(--mute);font-variant-numeric:tabular-nums}
.ok{color:var(--ok)}.no{color:var(--no)}
q{font-style:italic}
a{color:inherit}
table{border-collapse:collapse}td{padding:2px 12px 2px 0;font-variant-numeric:tabular-nums}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def money(x: float) -> str:
    return f"{x:.2f}".replace(".", ",") + " $"


def _people(n: int) -> str:
    return f"{n} persona" if n == 1 else f"{n} persone"


def _author(aid: str) -> str:
    platform, _, name = aid.partition(":")
    return f"{name} ({platform})" if platform else name


def safe(url) -> bool:
    """Solo un link http o https diventa cliccabile."""
    return isinstance(url, str) and url.lower().startswith(("http://", "https://"))


def link(url: str, start_s) -> str:
    """L'URL della fonte, per YouTube al secondo giusto (arrotondato per difetto).

    Un `t=` già presente si sostituisce: ne resta uno solo, in fondo.
    """
    url = url or ""
    if start_s is None or not ("youtube.com" in url or "youtu.be" in url):
        return url
    base, _, rest = url.partition("?")
    query, hash_, frag = rest.partition("#")
    parts = [x for x in query.split("&") if x and not x.startswith("t=")]
    parts.append(f"t={int(math.floor(start_s))}s")
    return f"{base}?{'&'.join(parts)}{hash_}{frag}"


def _clock(start_s) -> str:
    s = int(math.floor(start_s))
    return f"{s // 60}:{s % 60:02d}"


_NUMBERS = {a for aliases in vocab.NUMBER_ALIASES.values() for a in aliases}
_NAMES = {a for corners in vocab.CORNERS.values() for aliases in corners.values()
          for a in aliases} - _NUMBERS


def by_number(quote) -> bool:
    """La citazione chiama la curva solo col numero («turn 7»), senza il nome."""
    q = vocab.fold(str(quote or ""))
    has = lambda aliases: any(vocab.alias_regex(a).search(q) for a in aliases)  # noqa: E731
    return has(_NUMBERS) and not has(_NAMES)


def _source(s: dict) -> str:
    text = T["open_at"].format(t=_clock(s["start_s"])) if s["start_s"] is not None else T["open"]
    klass = CLASS_LABELS.get(s.get("car_class") or "ignota", CLASS_LABELS["ignota"])
    if by_number(s["quote"]):
        klass = f'{klass} · {T["by_number"]}'
    if safe(s["url"]):
        where = f'<a href="{_e(link(s["url"], s["start_s"]))}">{_e(text)}</a>'
    else:
        where = f'<span class="mute">{_e(T["no_link"])}</span>'
    return (f'<li><q>{_e(export.cut(s["quote"], QUOTE_WORDS))}</q> '
            f'<span class="n">{_e(klass)}</span> {where}</li>')


def _value(v: dict) -> str:
    authors = ", ".join(_author(a) for a in v["authors"])
    sources = "".join(_source(s) for s in v["sources"])
    return (f'<div><b>{_e(export.cut(v["value"]))}</b> <span class="n">{_people(v["n"])}</span>'
            f'<div class="mute">{_e(authors)}</div><ul>{sources}</ul></div>')


def _fact(e: dict, section: str, checks) -> str:
    head = f'<b>{_e(TYPE_LABELS.get(e["type"], e["type"]))}</b>'
    note = ""
    if section == "verificato":
        ok = export.status(e, checks) == "confermato"
        note = (f'<p class="ok">{T["out"]}</p>' if ok else f'<p class="mute">{T["unchecked"]}</p>')
    elif section == "respinto":
        parts = []
        for c in checks[e["fact_key"]]["respinto"]:
            parts.append(f'<p class="no">{T["check_said"]} <q>{_e(export.cut(c.get("reason")))}</q></p>'
                         f'<p class="mute">{T["quoted"]} <q>{_e(export.cut(c.get("quote")))}</q>'
                         f', {_e(c.get("model"))}</p>')
        note = "".join(parts)
    values = e["values"] if section != "verificato" else e["values"][:1]
    others = ""
    if e.get("others"):
        others = (f'<p class="mute"><b>{T["others"]}</b>. {T["others_why"]}</p>'
                  + "".join(_value(v) for v in e["others"]))
    return f'<li class="fact">{head}{note}{"".join(_value(v) for v in values)}{others}</li>'


def _section_of(e: dict, checks) -> str:
    if e["state"] == "verificato" and export.status(e, checks) in ("respinto", "non_confermato"):
        return export.status(e, checks)
    return e["state"]


def _header(conn: sqlite3.Connection, track: str) -> str:
    row = conn.execute("SELECT baseline_usd, last_usd, cap_usd FROM spend WHERE track=?",
                       (track,)).fetchone()
    if row and row[0] is not None and row[1] is not None:
        cap = row[2] if row[2] is not None else 0.0
        spend = T["spent"].format(spent=money(apify.spent(conn, track)), cap=money(cap))
    else:
        spend = T["unspent"]
    rejects = conn.execute(
        "SELECT j.reason, COUNT(*) FROM rejects j JOIN results r ON r.id = j.result_id"
        " WHERE r.track=? GROUP BY j.reason ORDER BY COUNT(*) DESC, j.reason", (track,)).fetchall()
    if rejects:
        rows = "".join(f"<tr><td>{_e(reason)}</td><td>{n}</td></tr>" for reason, n in rejects)
        table = f"<table>{rows}</table>"
    else:
        table = f'<p class="mute">{T["no_rejects"]}</p>'
    return (f'<p>{T["intro"]} {T["rule"]}</p><p>{_e(spend)}</p>'
            f'<h2>{T["rejects_title"]}</h2>{table}<p class="mute">{T["whole"]}</p>')


def page(conn: sqlite3.Connection, track: str) -> str:
    entries = consensus.build(conn, track)
    checks = export.factchecks(conn, track)
    corners: dict[str, list[dict]] = {}
    for e in entries:  # il consenso è già nell'ordine del catalogo
        corners.setdefault(e["corner"], []).append(e)
    body = [f"<h1>Fonti di {_e(track.capitalize())}</h1>", _header(conn, track)]
    if not corners:
        body.append(f'<p class="mute">{T["no_facts"]}</p>')
    for corner, items in corners.items():
        body.append(f"<section><h2>{_e(corner)}</h2>")
        for key, title in SECTIONS:
            mine = [e for e in items if _section_of(e, checks) == key]
            body.append(f'<h3>{title}</h3><p class="why">{WHY[key]}</p>')
            if mine:
                body.append("<ul>" + "".join(_fact(e, key, checks) for e in mine) + "</ul>")
            else:
                body.append(f'<p class="mute">{T["empty"]}</p>')
        body.append("</section>")
    return ("<!doctype html>\n<html lang=\"it\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Fonti di {_e(track.capitalize())}</title><style>{_CSS}</style></head>"
            f"<body><main>{''.join(body)}</main></body></html>\n")


def render(conn: sqlite3.Connection, track: str, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(conn, track), encoding="utf-8", newline="\n")
    return out
