"""The user guide as a web page, rendered from the Markdown we already ship.

Until now the "Guide" button opened ``GUIDA.md`` in Notepad: a 284-line document
with tables drawn in pipes and headings written as hash marks, wrapped at 80
columns by a program with no notion of a heading. The content was fine; the
presentation was the reason nobody read past section 3.

Two rules shaped this module.

**One source of truth.** The page is rendered from ``GUIDA.md`` (Italian) and
``docs/FAQ.md`` (English) at request time, never from a copy. Editing the
Markdown is still how you edit the guide, and the guide can't drift from what
ships in the exe — both files are already bundled.

**No new dependency.** ``markdown`` and friends are not in ``requirements.txt``
and are not in the frozen exe, so pulling one in would mean a page that works on
a developer's machine and 404s for everyone else. What's here instead is a
renderer for the subset those two documents actually use — headings, paragraphs,
bold/italic/code, links, fenced code, nested lists, blockquotes, tables, rules —
and a test that renders the real files and fails if any Markdown leaks through.
It is deliberately not a general Markdown implementation; see ``_INLINE`` below
for the one construct it refuses on purpose.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Where the documents live
# ---------------------------------------------------------------------------


def guide_source(lang: str | None = None) -> Path:
    """The guide document for ``lang``, wherever this build keeps it.

    Frozen and source layouts differ: PyInstaller unpacks data files under
    ``sys._MEIPASS`` while the exe itself sits elsewhere, and a source checkout
    has them at the repository root. Falls back to the other language rather
    than to nothing — a guide in the wrong language still beats a 404.
    """
    if lang is None:
        from .i18n import current_language
        lang = current_language()

    names = (["GUIDA.md", "docs/FAQ.md"] if lang == "it"
             else ["docs/FAQ.md", "GUIDA.md"])
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            roots.append(Path(base))
        roots.append(Path(sys.executable).parent)
    else:
        roots.append(_SRC.parent.parent)          # repo root, from src/accoach/

    candidates = [root / name for name in names for root in roots]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
# Single-asterisk emphasis only. `_underscore_` emphasis is NOT supported, and
# that is the point: this codebase is full of identifiers like `lost_at` and
# `slip_ratio` that appear in prose outside backticks, and a general renderer
# turns the middle of those into italics.
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.S)

_INLINE = (_LINK, _BOLD, _ITALIC)


def _inline(text: str) -> str:
    """Escape, then apply inline markup — with code spans held out of it."""
    spans: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE_SPAN.sub(_stash, text)
    text = html.escape(text)
    text = _LINK.sub(lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">'
                               f"{m.group(1)}</a>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>",
                  text)


def slugify(text: str) -> str:
    """GitHub-compatible heading anchor, so in-document links keep working.

    ``docs/FAQ.md`` opens with a row of ``[Overlay](#overlay)`` style links
    written against GitHub's rules; they have to resolve here too.
    """
    plain = _CODE_SPAN.sub(r"\1", text)
    plain = _BOLD.sub(r"\1", _LINK.sub(r"\1", plain))
    plain = re.sub(r"[^\w\s-]", "", plain.lower(), flags=re.U)
    # One dash per space, NOT per run of them: dropping "&" from "SmartScreen &
    # Security" leaves two spaces, and GitHub's anchor for it is the double-dash
    # "smartscreen--security" that the FAQ's own quick-links row points at.
    return re.sub(r"\s", "-", plain.strip())


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM = re.compile(r"^(\s*)(?:([-*])|(\d+)\.)\s+(.*)$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,})\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:-]*-[\s|:-]*$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _starts_block(line: str) -> bool:
    """Would this line open a block of its own, rather than continue a sentence?"""
    stripped = line.lstrip()
    return bool(
        _ITEM.match(line) or _HEADING.match(line) or _RULE.match(line)
        or stripped.startswith(("```", ">", "|"))
    )


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _render_table(lines: list[str]) -> str:
    head, *body = [_split_row(ln) for ln in lines if not _TABLE_SEP.match(ln)]
    out = ["<div class=\"table-wrap\"><table><thead><tr>"]
    out += [f"<th>{_inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _render_list(lines: list[str], headings: list[tuple[int, str, str]]) -> str:
    """One list level; deeper indentation recurses through :func:`_blocks`."""
    base = _indent(lines[0])
    first = _ITEM.match(lines[0])
    assert first is not None
    ordered = first.group(3) is not None

    items: list[list[str]] = []
    for line in lines:
        m = _ITEM.match(line)
        if m is not None and _indent(line) <= base:
            items.append([m.group(4)])
        elif items:
            items[-1].append(line)

    out = ["<ol>" if ordered else "<ul>"]
    for item in items:
        # Dedent an item's continuation by their *common* indent, not by the
        # marker's: everything under a bullet is written relative to the text,
        # and shaving the marker's column instead leaves a fenced block inside
        # the item indented by two — which then renders as indented code.
        pad = min((_indent(x) for x in item[1:] if x.strip()), default=0)
        raw = [item[0]] + [x[pad:] if len(x) > pad else x.strip()
                           for x in item[1:]]
        # Continuation lines belong to the item's own sentence — a wrapped
        # sentence must not become a second paragraph. Anything that *starts a
        # block* ends the sentence instead: a nested item, a blank line, or a
        # fenced code block (section 5 of the guide puts a command inside a
        # bullet, and treating its fence as prose swallowed the command).
        lead, rest = [raw[0]], []
        for line in raw[1:]:
            if rest or not line.strip() or _starts_block(line):
                rest.append(line)
            else:
                lead.append(line.strip())
        body = _inline(" ".join(lead))
        if rest:
            body += _blocks(rest, headings)
        out.append(f"<li>{body}</li>")
    out.append("</ol>" if ordered else "</ul>")
    return "".join(out)


def _blocks(lines: list[str], headings: list[tuple[int, str, str]]) -> str:
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.lstrip().startswith("```"):
            i += 1
            code = []
            while i < n and not lines[i].lstrip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
            continue

        if _RULE.match(line) and not _ITEM.match(line):
            out.append("<hr>")
            i += 1
            continue

        m = _HEADING.match(line)
        if m is not None:
            level, text = len(m.group(1)), m.group(2).strip()
            slug = slugify(text)
            headings.append((level, slug, text))
            out.append(f'<h{level} id="{slug}">{_inline(text)}'
                       f'<a class="anchor" href="#{slug}" aria-hidden="true">#</a>'
                       f"</h{level}>")
            i += 1
            continue

        if line.lstrip().startswith(">"):
            quote = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{_blocks(quote, headings)}</blockquote>")
            continue

        if (line.strip().startswith("|") and i + 1 < n
                and _TABLE_SEP.match(lines[i + 1])):
            table = []
            while i < n and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            out.append(_render_table(table))
            continue

        if _ITEM.match(line):
            block, base = [], _indent(line)
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    # A blank line ends the list unless what follows is still in it.
                    nxt = next((x for x in lines[i + 1:] if x.strip()), "")
                    if not (_ITEM.match(nxt) and _indent(nxt) >= base):
                        break
                    block.append(cur)
                elif _indent(cur) < base or (_indent(cur) == base
                                             and not _ITEM.match(cur)):
                    break
                else:
                    block.append(cur)
                i += 1
            out.append(_render_list(block, headings))
            continue

        para = []
        while i < n and lines[i].strip() and not _starts_block(lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
        else:
            i += 1
    return "".join(out)


def render_markdown(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Return ``(body_html, headings)``; headings are ``(level, slug, text)``."""
    headings: list[tuple[int, str, str]] = []
    return _blocks(text.replace("\r\n", "\n").split("\n"), headings), headings


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

_PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{icon}
<style>{css}</style>
</head>
<body>
<header class="guide-top">{header}</header>
<div class="guide-shell">
  <nav class="guide-toc" aria-label="{toc_label}">
    <p class="toc-title">{toc_label}</p>
    <ol>{toc}</ol>
  </nav>
  <main class="guide-body">{body}</main>
</div>
<script>
// Highlight the section you're reading. Progressive: without JS the page is
// still the whole guide, just without the moving marker.
(function () {{
  var links = Array.prototype.slice.call(document.querySelectorAll('.guide-toc a'));
  var targets = links.map(function (a) {{
    return document.getElementById(decodeURIComponent(a.hash.slice(1)));
  }});
  function sync() {{
    var best = 0;
    for (var i = 0; i < targets.length; i++) {{
      if (targets[i] && targets[i].getBoundingClientRect().top <= 120) best = i;
    }}
    links.forEach(function (a, i) {{ a.classList.toggle('current', i === best); }});
  }}
  addEventListener('scroll', sync, {{passive: true}});
  sync();
}})();
</script>
</body>
</html>
"""

_CSS = """
:root {
  --bg:#0B0E12; --panel:#151A21; --line:#232B35; --text:#E8EDF2; --muted:#8A95A3;
  --cyan:#22D3CE; --amber:#FFB020; --green:#34E08A; --red:#FF4D5E;
  --font-ui:"Inter",system-ui,"Segoe UI",sans-serif;
  --font-head:"Space Grotesk","Inter",system-ui,sans-serif;
  --font-mono:"JetBrains Mono",ui-monospace,Consolas,monospace;
}
@font-face{font-family:"Inter";src:url("/static/fonts/Inter-Regular.ttf") format("truetype");font-weight:400;font-display:swap}
@font-face{font-family:"Inter";src:url("/static/fonts/Inter-Bold.ttf") format("truetype");font-weight:700;font-display:swap}
@font-face{font-family:"Space Grotesk";src:url("/static/fonts/SpaceGrotesk-Bold.ttf") format("truetype");font-weight:700;font-display:swap}
@font-face{font-family:"JetBrains Mono";src:url("/static/fonts/JetBrainsMono-Regular.ttf") format("truetype");font-weight:400;font-display:swap}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-ui);
     font-size:16px;line-height:1.65;-webkit-text-size-adjust:100%}
.guide-top{position:sticky;top:0;z-index:5;display:flex;align-items:center;
  justify-content:space-between;gap:16px;padding:12px 24px;background:rgba(11,14,18,.92);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.brand{color:var(--text);text-decoration:none;font-family:var(--font-head);letter-spacing:.04em}
.brand .name{font-weight:700}
.brand .sub{color:var(--muted);font-weight:400}
.back{color:var(--cyan);text-decoration:none;font-size:14px;white-space:nowrap}
.back:hover{text-decoration:underline}
.guide-shell{display:grid;grid-template-columns:260px minmax(0,1fr);gap:40px;
  max-width:1180px;margin:0 auto;padding:32px 24px 96px}
.guide-toc{position:sticky;top:76px;align-self:start;max-height:calc(100vh - 108px);
  overflow-y:auto;font-size:14px}
.toc-title{margin:0 0 10px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.12em;font-size:11px}
.guide-toc ol{list-style:none;margin:0;padding:0;border-left:1px solid var(--line)}
.guide-toc li{margin:0}
.guide-toc a{display:block;padding:6px 12px;color:var(--muted);text-decoration:none;
  border-left:2px solid transparent;margin-left:-1px}
.guide-toc a:hover{color:var(--text)}
.guide-toc a.current{color:var(--cyan);border-left-color:var(--cyan)}
.guide-body{min-width:0;max-width:76ch}
.guide-body h1{font-family:var(--font-head);font-size:34px;line-height:1.2;margin:0 0 8px}
.guide-body h2{font-family:var(--font-head);font-size:24px;margin:56px 0 12px;
  padding-top:16px;border-top:1px solid var(--line);scroll-margin-top:88px}
.guide-body h3{font-family:var(--font-head);font-size:18px;margin:32px 0 8px;
  color:var(--cyan);scroll-margin-top:88px}
.guide-body h1 .anchor,.guide-body h2 .anchor,.guide-body h3 .anchor{
  margin-left:8px;color:var(--line);text-decoration:none;font-size:.7em;opacity:0}
.guide-body h2:hover .anchor,.guide-body h3:hover .anchor{opacity:1}
.guide-body p{margin:0 0 14px}
.guide-body a{color:var(--cyan)}
.guide-body strong{color:#fff}
.guide-body ul,.guide-body ol{margin:0 0 16px;padding-left:22px}
.guide-body li{margin:0 0 8px}
.guide-body li>ul,.guide-body li>ol{margin-top:8px}
.guide-body code{font-family:var(--font-mono);font-size:.88em;background:var(--panel);
  border:1px solid var(--line);border-radius:4px;padding:1px 5px;color:var(--amber)}
.guide-body pre{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;overflow-x:auto;margin:0 0 16px}
.guide-body pre code{background:none;border:0;padding:0;color:var(--text);font-size:14px}
.guide-body blockquote{margin:0 0 16px;padding:12px 16px;background:var(--panel);
  border-left:3px solid var(--cyan);border-radius:0 8px 8px 0;color:#cfd8e3}
.guide-body blockquote p:last-child{margin-bottom:0}
.guide-body hr{border:0;border-top:1px solid var(--line);margin:40px 0 0}
/* Both documents put a rule between every section, and h2 already draws one.
   Two lines with a gap between them read as a mistake, so the heading yields. */
.guide-body hr+h2{border-top:0;padding-top:0;margin-top:28px}
.table-wrap{overflow-x:auto;margin:0 0 18px;border:1px solid var(--line);border-radius:8px}
.guide-body table{border-collapse:collapse;width:100%;font-size:14px}
.guide-body th,.guide-body td{text-align:left;padding:9px 14px;
  border-bottom:1px solid var(--line);vertical-align:top}
.guide-body thead th{background:var(--panel);font-family:var(--font-head);
  color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-size:11px}
.guide-body tbody tr:last-child td{border-bottom:0}
@media (max-width:900px){
  .guide-shell{grid-template-columns:1fr;gap:8px;padding:20px 18px 64px}
  .guide-toc{position:static;max-height:none;border:1px solid var(--line);
    border-radius:8px;padding:14px 12px;margin-bottom:24px}
  .guide-body h1{font-size:27px}
}
"""

_STRINGS = {
    "it": {"subtitle": "· Guida", "back": "← Torna all'analisi", "toc": "Indice"},
    "en": {"subtitle": "· Guide", "back": "← Back to analysis", "toc": "Contents"},
}


def render_page(markdown_text: str, lang: str = "it",
                standalone: bool = False) -> str:
    """The full HTML page for a guide document.

    ``standalone`` is for the copy the hub opens straight off disk, with no
    server running: the links back into the app would go nowhere from a
    ``file://`` page, so they're dropped rather than left broken. The brand
    fonts are served from ``/static`` and simply fall back to the system stack
    there — a different typeface beats a page that only opens sometimes.
    """
    body, headings = render_markdown(markdown_text)
    s = _STRINGS.get(lang, _STRINGS["it"])
    title = next((t for lvl, _, t in headings if lvl == 1), "HONE")

    toc = "".join(
        f'<li><a href="#{slug}">{_inline(text)}</a></li>'
        for lvl, slug, text in headings if lvl == 2
    )
    brand = (f'<span class="name">HONE</span> <span class="sub">{s["subtitle"]}</span>')
    if standalone:
        header, icon = f'<span class="brand">{brand}</span>', ""
    else:
        header = (f'<a class="brand" href="/">{brand}</a>'
                  f'<a class="back" href="/">{s["back"]}</a>')
        icon = '<link rel="icon" href="/static/hone_icon.png">'

    return _PAGE.format(lang=lang, title=html.escape(title), css=_CSS, body=body,
                        toc=toc, toc_label=s["toc"], header=header, icon=icon)


def render_guide(lang: str | None = None, standalone: bool = False) -> str:
    """Read the guide for ``lang`` off disk and render it."""
    if lang is None:
        from .i18n import current_language
        lang = current_language()
    path = guide_source(lang)
    if not path.is_file():
        raise FileNotFoundError(path)
    return render_page(path.read_text(encoding="utf-8"), lang, standalone)


def write_offline_copy(lang: str | None = None) -> Path:
    """Render the guide next to the user's data and return the file to open.

    The hub's Guide button can be pressed with nothing else running, so it can't
    rely on the analysis server being up. One fixed filename per language,
    rewritten every time: the guide follows the installed Markdown instead of
    going stale in a cache.
    """
    from .paths import base_dir

    if lang is None:
        from .i18n import current_language
        lang = current_language()
    dest = base_dir() / f"guida_{lang}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_guide(lang, standalone=True), encoding="utf-8")
    return dest
