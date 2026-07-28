"""Adding a view must not quietly break the ones already there.

The analysis page grew a new landing tab and two things went wrong at once, both
silently: a panel can be added without being wired to a tab, and the guided tour
— which skips any step whose target isn't on screen — shrank from eight steps to
three while still reporting itself as complete. Neither failure raises anything.
Both are visible from the source, so they're checked here.
"""
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"
_HTML = (WEB / "index.html").read_text(encoding="utf-8")
_APPJS = (WEB / "app.js").read_text(encoding="utf-8")
_TOURJS = (WEB / "tour.js").read_text(encoding="utf-8")

_TABS = re.findall(r'data-view="([\w-]+)"', _HTML)
_PANELS = re.findall(r'id="view-([\w-]+)"', _HTML)


def _view_of_ids() -> dict[str, str]:
    """{element id: the view panel it sits inside} — by document order.

    Crude on purpose: the page is one flat file where each `<div id="view-x">`
    opens a section that runs until the next one. Good enough to answer "is this
    element on a tab the user has to switch to first?", which is the question.
    """
    out: dict[str, str] = {}
    current = ""
    for m in re.finditer(r'id="([\w-]+)"', _HTML):
        name = m.group(1)
        if name.startswith("view-"):
            current = name[len("view-"):]
            continue
        out[name] = current
    return out


def _default_view() -> str:
    m = re.search(r'class="tab active"[^>]*data-view="([\w-]+)"', _HTML)
    assert m, "no tab is marked active in index.html"
    return m.group(1)


# --- tabs and panels agree -------------------------------------------------

def test_every_tab_has_a_panel():
    for view in _TABS:
        assert f"view-{view}" in _PANELS or view in _PANELS, view


def test_every_panel_has_a_tab():
    """A panel nothing can reach is dead weight that still renders."""
    for panel in _PANELS:
        assert panel in _TABS, panel


def test_exactly_one_tab_starts_active():
    assert len(re.findall(r'class="tab active"', _HTML)) == 1


def test_the_panel_of_the_active_tab_is_the_one_left_visible():
    """The others carry `hidden`; the active one must not."""
    default = _default_view()
    for panel in _PANELS:
        block = re.search(rf'<div id="view-{panel}"([^>]*)>', _HTML).group(1)
        hidden = "hidden" in block
        assert hidden == (panel != default), panel


def test_the_javascript_starts_on_the_tab_the_html_marks_active():
    m = re.search(r'let VIEW = "([\w-]+)"', _APPJS)
    assert m and m.group(1) == _default_view()


def test_view_switching_is_derived_from_the_dom():
    """It used to be three hand-written lists; forgetting one stacks two panels."""
    assert "querySelectorAll(\"[id^='view-']\")" in _APPJS


# --- the guided tour survives a new landing tab ----------------------------

def test_the_tour_skips_steps_it_cannot_point_at():
    """The behaviour that makes the next test necessary, pinned so it stays true."""
    assert "if (steps[i].before || (el && visible(el))) out.push(i);" in _TOURJS


def _tour_steps() -> list[tuple[str, bool]]:
    body = _APPJS.split("function tourSteps()")[1].split("\n}")[0]
    return [(m.group(1), "before:" in m.group(0))
            for m in re.finditer(r'\{\s*sel:\s*"([^"]+)"[^}]*\}', body)]


def test_the_tour_has_steps():
    assert len(_tour_steps()) >= 5


def test_every_tour_step_points_at_something_that_exists():
    ids = set(re.findall(r'id="([\w-]+)"', _HTML))
    classes = set(re.findall(r'class="([^"]+)"', _HTML))
    flat = {c for group in classes for c in group.split()}
    for sel, _ in _tour_steps():
        target = sel.lstrip("#.")
        assert target in ids or target in flat, sel


def test_tour_steps_on_a_hidden_tab_bring_it_forward_first():
    """Without this, a step whose tab isn't open is dropped and nobody is told."""
    where = _view_of_ids()
    default = _default_view()
    for sel, has_before in _tour_steps():
        if not sel.startswith("#"):
            continue                      # class selectors are page chrome
        view = where.get(sel[1:], "")
        if view and view != default:
            assert has_before, f"{sel} lives in the {view!r} tab but never opens it"


# --- the guided flow is wired ---------------------------------------------

@pytest.mark.parametrize("el", ("flow-card", "flow-count", "flow-dots",
                                "flow-prev", "flow-next", "flow-whole", "c-flow"))
def test_the_flow_view_has_the_elements_its_code_reaches_for(el):
    assert f'id="{el}"' in _HTML
    assert f'"{el}"' in _APPJS


def test_the_flow_is_rendered_when_a_lap_loads_and_when_the_tab_opens():
    assert "renderFlow(a);" in _APPJS
    assert 'VIEW === "flow"' in _APPJS


def test_a_language_switch_refetches_rather_than_repainting():
    """Every word of the flow, the debrief and the corner names is written by
    the backend in the requested language; repainting the cached payload leaves
    all of it in the language you just left."""
    block = _APPJS.split("window.HoneI18nRerender")[1]
    assert "reloadSelection()" in block
    assert "drawDebrief(DATA)" not in block
