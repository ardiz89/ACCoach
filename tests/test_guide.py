"""The guide as a page: it must render the real documents, not a happy fixture.

A hand-written Markdown renderer is a liability, and the way it usually fails is
quietly — a construct nobody thought of ends up as literal asterisks in the
middle of a sentence, and the page still looks like a page. So the tests here
are mostly run against the two documents we actually ship, and the main
assertion is a negative one: no Markdown survives into the text the reader sees.
"""
import re
from pathlib import Path

import pytest

from accoach.guide import (
    guide_source,
    render_markdown,
    render_page,
    slugify,
    write_offline_copy,
)

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = {
    "it": (_ROOT / "GUIDA.md").read_text(encoding="utf-8"),
    "en": (_ROOT / "docs" / "FAQ.md").read_text(encoding="utf-8"),
}


def _visible_text(html: str) -> str:
    """What a reader ends up looking at, tags stripped."""
    return re.sub(r"<[^>]+>", "", html)


# --- the documents we ship -------------------------------------------------

@pytest.mark.parametrize("lang", ("it", "en"))
def test_no_markup_leaks_into_the_rendered_text(lang):
    """The failure mode this renderer exists to avoid.

    Each of these was a real bug during development: a fenced code block inside
    a bullet had its fences read as prose, swallowing the command it contained.
    """
    text = _visible_text(render_markdown(_DOCS[lang])[0])
    for leak in ("**", "`", "|--", "](", "```"):
        assert leak not in text, f"{leak!r} left in the rendered {lang} guide"


@pytest.mark.parametrize("lang", ("it", "en"))
def test_every_heading_survives(lang):
    """A dropped section is invisible in the output but missing from the guide."""
    # #### appears once in GUIDA.md ("Curva per sessione", inside section 5) —
    # {1,3} predates that heading and silently missed it.
    source_headings = re.findall(r"^#{1,4}\s+(.+)$", _DOCS[lang], re.M)
    body, parsed = render_markdown(_DOCS[lang])
    assert len(parsed) == len(source_headings)
    for level, slug, _ in parsed:
        assert f'id="{slug}"' in body


def test_the_italian_guide_keeps_its_structure():
    """Counts, so that a block type silently ceasing to parse shows up here."""
    body, headings = render_markdown(_DOCS["it"])
    assert len([h for h in headings if h[0] == 2]) == 9      # the nine sections
    assert body.count("<table>") == 6   # pedali + delta + colori curva + 2 di comandi + config
    assert body.count("<pre>") >= 3                          # the shell examples
    assert body.count("<blockquote>") == 4   # +1: il trail sulle stradali


def test_a_command_inside_a_bullet_stays_a_code_block():
    """Section 5 puts `python -m accoach web` inside a list item; it used to be
    joined into the sentence, fences and all."""
    body, _ = render_markdown(_DOCS["it"])
    assert "<li>" in body
    assert "<pre><code>python -m accoach web</code></pre>" in body


# --- the pieces ------------------------------------------------------------

def test_tables_become_tables():
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    body, _ = render_markdown(md)
    assert "<th>A</th>" in body and "<td>2</td>" in body


def test_nested_lists_nest():
    body, _ = render_markdown("- one\n  - inner\n- two\n")
    assert body.count("<ul>") == 2
    assert "<li>inner</li>" in body


def test_a_wrapped_sentence_is_not_split_into_paragraphs():
    body, _ = render_markdown("- first half\n  second half\n")
    assert "<li>first half second half</li>" in body


def test_code_spans_are_not_re_formatted():
    """`**` inside backticks is a literal, and identifiers must survive intact."""
    body, _ = render_markdown("Use `a ** b` with `lost_at`.")
    assert "<code>a ** b</code>" in body
    assert "<code>lost_at</code>" in body


def test_underscores_outside_code_are_left_alone():
    """No `_emphasis_`: this project writes `slip_ratio` and `lost_at` in prose,
    and a general renderer italicises the middle of them."""
    body, _ = render_markdown("Il campo slip_ratio_qui resta intero.")
    assert "<em>" not in body
    assert "slip_ratio_qui" in body


def test_html_in_the_source_is_escaped():
    body, _ = render_markdown("A <script>alert(1)</script> B")
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_anchors_match_github_so_in_document_links_work():
    """`docs/FAQ.md` opens with a row of links written against GitHub's rules."""
    assert slugify("SmartScreen & Security") == "smartscreen--security"
    assert slugify("How lap recording works (and starting from the pits)") == (
        "how-lap-recording-works-and-starting-from-the-pits")


def test_the_faq_quick_links_resolve():
    """The links at the top of the English document, checked against its own
    headings rather than against the slugifier's opinion of them."""
    body, headings = render_markdown(_DOCS["en"])
    ids = {slug for _, slug, _ in headings}
    targets = set(re.findall(r"\]\(#([^)]+)\)", _DOCS["en"]))
    assert targets and targets <= ids, targets - ids


# --- the page --------------------------------------------------------------

def test_the_page_carries_a_table_of_contents():
    page = render_page(_DOCS["it"], "it")
    assert "Indice" in page
    assert page.count('<a href="#') >= 9


def test_the_page_title_is_the_documents_own():
    assert "<title>Guida a HONE" in render_page(_DOCS["it"], "it")


def test_the_served_page_links_back_into_the_app():
    page = render_page(_DOCS["it"], "it")
    assert 'class="back" href="/"' in page


def test_the_standalone_page_has_no_links_that_would_go_nowhere():
    """Opened from `file://` by the hub, `href="/"` is the filesystem root."""
    page = render_page(_DOCS["it"], "it", standalone=True)
    assert 'href="/"' not in page
    assert "/static/hone_icon.png" not in page
    assert "Guida a HONE" in page


def test_write_offline_copy_lands_next_to_the_users_data(tmp_path, monkeypatch):
    import accoach.paths as paths

    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path)
    out = write_offline_copy("it")
    assert out.parent == tmp_path
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


# --- where the documents live ----------------------------------------------

def test_the_source_document_follows_the_language():
    assert guide_source("it").name == "GUIDA.md"
    assert guide_source("en").name == "FAQ.md"


def test_both_documents_are_actually_present_in_this_checkout():
    """`guide_source` falls back rather than failing, so a missing file would
    otherwise show up only as the wrong language on someone else's machine."""
    for lang in ("it", "en"):
        assert guide_source(lang).is_file()


@pytest.mark.parametrize("build", ("HONE.spec", "ACCoach.spec", "build_exe.bat"))
def test_both_documents_are_shipped_in_the_exe(build):
    """The fallback hid this for months: only ``GUIDA.md`` was bundled, so in the
    frozen build an English user's Guide button opened the Italian document —
    the very bug the language-aware lookup was written to fix. A missing data
    file can't fail loudly here, so it has to fail here instead.
    """
    text = (_ROOT / build).read_text(encoding="utf-8")
    assert "GUIDA.md" in text
    assert "docs/FAQ.md" in text
