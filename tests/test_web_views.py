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


# --- the line view is wired -----------------------------------------------

@pytest.mark.parametrize("el", ("line-summary", "line-chips", "line-facts",
                                "line-table", "line-readout", "line-missing",
                                "c-corner", "c-offset", "c-curv"))
def test_the_line_view_has_the_elements_its_code_reaches_for(el):
    assert f'id="{el}"' in _HTML
    assert f'"{el}"' in _APPJS


def test_the_line_view_reloads_when_the_lap_changes():
    """It's a separate request from /api/analysis (the zoomed corners need the
    lap at full resolution), so nothing else invalidates it."""
    block = _APPJS.split("async function loadCombo")[1].split("\n}")[0]
    assert "LINE = null;" in block
    assert 'VIEW === "line"' in block


def test_an_exaggerated_gap_says_so_on_the_canvas():
    """The zoom can blow up the distance between the two lines. An unlabelled
    exaggeration is just a wrong drawing, so the label is part of the feature."""
    assert "LINE_MAG > 1" in _APPJS
    assert "line.mag.note" in _APPJS


def test_printing_hides_every_view_without_naming_them():
    """The print sheet is the braking cheat sheet and nothing else.

    The rule used to list the eight panels it wanted gone, by id. A ninth tab
    then printed itself underneath the sheet, and the only way to notice is to
    print. Derived from the id prefix, a new view is hidden the day it is added.
    """
    block = _CSS[_CSS.index("@media print"):]
    block = block[:block.index("\n}")]
    assert '[id^="view-"]' in block
    assert "#view-map { display: block !important; }" in block


def test_no_two_functions_in_app_js_share_a_name():
    """The last declaration wins, in silence.

    Found the day the Training tab grew a `renderSession` and the Session tab
    already had one: the run plan simply never appeared on the page, nothing was
    logged, and every test still passed. One flat 3000-line script has no module
    scope to catch this, so it is caught here.
    """
    names = re.findall(r"^function (\w+)", _APPJS, re.M)
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"declared twice in app.js: {dupes}"


# --- the training tab is wired --------------------------------------------

def test_the_glossary_shows_its_words_when_closed():
    """A box labelled "Glossary" tells the reader they don't know things, and
    gets skipped by exactly the people it exists for. The row of terms is the
    invitation: you scan it and open it for the one word you don't have."""
    block = _APPJS.split("function renderWords(")[1].split("\n}")[0]
    assert "words-list" in block and "e.term" in block
    assert "<details" in block, "it has to start closed"
    assert 'id="train-words"' in _HTML
    assert _view_of_ids()["train-words"] == "training"


@pytest.mark.parametrize("el", ("train-gate", "train-gap", "train-steps",
                                "train-session", "train-words", "plan"))
def test_the_training_view_has_the_elements_its_code_reaches_for(el):
    assert f'id="{el}"' in _HTML
    assert f'"{el}"' in _APPJS


def test_the_plan_lives_on_exactly_one_tab():
    """It used to sit under Trends. Two panels drawing the same plan is two
    places for it to disagree about what you're working on — and the goals are
    now the steps, each with the drill that closes it."""
    assert _view_of_ids()["plan"] == "training"
    assert "renderPlan(" not in _APPJS, "the old Trends renderer is still there"
    block = _APPJS.split("async function loadProgress(")[1].split("\n}")[0]
    assert "plan" not in block, "Trends is still drawing the plan"


def test_trends_says_where_the_plan_went():
    """A panel that vanishes without a pointer reads as a feature that broke."""
    assert 'id="go-training"' in _HTML
    assert _view_of_ids()["go-training"] == "progress"
    assert 'showView("training")' in _APPJS


def test_the_training_tab_refetches_rather_than_repainting():
    """Every sentence of a drill is written by the backend in the requested
    language, so a cached payload would still be in the language you left."""
    block = _APPJS.split("function redrawCurrentView()")[1].split("\n}")[0]
    assert 'VIEW === "training"' in block
    assert "loadTraining(CURRENT)" in block


# --- the comparison lap is only forwarded when it was actually chosen ------

def test_the_comparison_lap_is_only_forwarded_when_the_driver_picked_it():
    """The picker is *filled* with the elected reference, so sending its value
    back on every reload pinned the page to a reference elected for another
    lap's conditions — and hid the note explaining the choice, because the page
    was then no longer showing the elected lap."""
    assert "let BASELINE_PINNED = false;" in _APPJS
    block = _APPJS.split("function reloadSelection()")[1].split("\n}")[0]
    assert "pinnedBaseline()" in block
    assert '$("baseline").value' not in block


def test_every_view_that_forwards_the_baseline_uses_the_same_rule():
    """Sectors, Line and the trajectory export all send it too; one of them
    keeping the old habit would make the tabs disagree about the benchmark."""
    for fn in ("loadSectors", "loadLine"):
        block = _APPJS.split(f"async function {fn}()")[1].split("\n}\n")[0]
        assert "pinnedBaseline()" in block, fn


def test_the_starred_lap_is_repainted_when_the_election_moves():
    """The star can move without the combo changing: the reference is elected
    for the conditions of the lap under review."""
    block = _APPJS.split("function fillLaps(")[1].split("\n}")[0]
    assert 'dataset.star' in block


def test_a_language_switch_refetches_rather_than_repainting():
    """Every word of the flow, the debrief and the corner names is written by
    the backend in the requested language; repainting the cached payload leaves
    all of it in the language you just left."""
    block = _APPJS.split("window.HoneI18nRerender")[1]
    assert "reloadSelection()" in block
    assert "drawDebrief(DATA)" not in block


def test_dates_follow_the_page_language_not_the_browser_s():
    """`toLocaleDateString(undefined, …)` asks Chrome, not the page: an English
    page on an Italian machine read "since 31 lug · 13:58"."""
    block = _APPJS[_APPJS.index("function fmtWhen("):]
    block = block[:block.index("\n}")]
    assert "toLocaleDateString(LANG()" in block
    assert "undefined" not in block


def test_a_language_switch_also_reaches_the_per_combo_views():
    """`reloadSelection` refetches the *lap*. Trends, Session and Training are
    per car+track and it never touched them, so the page came back with its
    chrome in one language and its content in the other — caught on Training,
    but it was never only there. Their cached payloads have to go too."""
    block = _APPJS.split("window.HoneI18nRerender")[1]
    for call in ("loadProgress(CURRENT)", "loadSession(CURRENT",
                 "loadTraining(CURRENT)"):
        assert call in block, call
    for cache in ("SHEET = null", "TRAINING = null"):
        assert cache in block, cache


# --- the page must not scroll sideways on a phone --------------------------
# Measured in a 390px-wide frame against the real page, per view. Both rules
# below fixed a page that scrolled horizontally; a static check can only pin
# that the rule is still there, which is the half that regresses silently.

_CSS = (WEB / "style.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    """The body of the first CSS rule whose selector line contains `selector`."""
    i = _CSS.index(selector)
    return _CSS[i:_CSS.index("}", i)]


def test_the_header_row_wraps():
    """It keeps growing — logo, name, the tour "?", the language picker, the
    colour-blind toggle, the guide link. Unwrapped it measured 404px inside a
    390px phone and took the whole page sideways with it."""
    assert "flex-wrap: wrap" in _rule(".brand {")


def test_the_consistency_rows_stack_on_a_narrow_screen():
    """Their third column is `auto` + `white-space: nowrap`, so it cannot shrink:
    39px of horizontal scroll on Trends, 17 on Compare. Reading the report on a
    tablet next to the wheel is a documented use of this app."""
    assert "@media (max-width: 700px)" in _CSS
    narrow = _CSS[_CSS.index(".cons-nums {"):]
    block = narrow[:narrow.index("\n.recur")] if "\n.recur" in narrow else narrow
    assert ".cons-row { grid-template-columns: 1fr auto; }" in block
    assert "white-space: normal" in block


@pytest.mark.parametrize("view", ("flow", "session", "line", "training"))
def test_the_new_views_declare_a_narrow_layout(view):
    """All were built two-column-ish; none was checked on a phone until the
    page was measured in a 390px frame."""
    marker = {"flow": ".flow-btn.ghost", "session": ".ses-lap",
              "line": ".line-grid", "training": ".step-head"}[view]
    tail = _CSS[_CSS.index("@media (max-width: 700px)"):]
    assert marker in tail, f"no narrow-screen rule for the {view} view"


# --- the lap position is one wording, in one place --------------------------
# Three readouts print where you are on the lap (Compare, Dynamics, Trajectory).
# They used to build the label by hand, in three places, in per cent; when the
# axis learned to speak metres, a view left behind would keep saying "45%" next
# to charts labelled "2000 m" and nothing would fail.

def test_no_readout_writes_its_own_position_label():
    for m in re.finditer(r'ro\.pos"\)\}([^`]{0,40})', _APPJS):
        assert "posLabel(" in m.group(1), m.group(0)


def test_the_metre_axis_still_has_a_way_back_to_per_cent():
    """A lap with no coordinates — or with coordinates the backend refused to
    believe — must fall back, not draw a scale it doesn't have."""
    block = _APPJS[_APPJS.index("function gridX("):]
    block = block[:block.index("\nfunction ")]
    assert 'Math.round(q * 100) + "%"' in block
    assert "distanceTicks()" in block


# --- the lap bar: one identity strip, on every tab --------------------------
# The landing view explained a lap without ever naming it — the lap time, the
# reference and the gap lived inside Compare's own summary. They moved to a strip
# under the tabs; these pin the two ways that can silently regress.

def test_the_lap_bar_is_outside_every_view():
    """Inside a view panel it would show on one tab and vanish on the other
    seven, which is the bug it was built to fix."""
    assert 'id="lapbar"' in _HTML
    assert _view_of_ids()["lapbar"] == "", "the lap bar sits in a view panel"


def test_the_compare_summary_no_longer_repeats_the_lap_bar():
    """Two places printing the same gap drift apart the day one of them learns
    something the other doesn't."""
    body = _APPJS[_APPJS.index("function drawSummary("):]
    body = body[:body.index("\n}")]
    for key in ('t("lbl.lap")', 't("lbl.comparison")', 't("lbl.gap")'):
        assert key not in body, key


def test_a_remembered_view_is_checked_before_it_is_used():
    """localStorage outlives the page: a view saved by an older build, or one
    removed since, must not be restored onto a panel that isn't there."""
    body = _APPJS[_APPJS.index("function savedView("):]
    body = body[:body.index("\n}")]
    assert 'getElementById("view-" + v)' in body


def test_no_id_rule_can_outrank_the_hidden_class():
    """`.hidden { display: none }` is how one view is shown and seven are not,
    and it is a *class*: any `#view-x` rule that sets `display` wins on
    specificity and leaves that panel on screen under every other tab. It
    happened the day the landing view was centred vertically, so the rule is
    pinned here: qualify such selectors with `:not(.hidden)`.
    """
    for m in re.finditer(r"(#view-[\w-]+)([^{]*)\{([^}]*)\}", _screen_css()):
        sel, rest, body = m.group(1), m.group(2), m.group(3)
        if "display" not in body:
            continue
        assert ":not(.hidden)" in sel + rest, f"{sel}{rest} sets display"


def _screen_css() -> str:
    """The stylesheet without its print block — printing deliberately forces
    every panel visible, which is the opposite rule and not a mistake."""
    i = _CSS.find("@media print")
    if i == -1:
        return _CSS
    depth, j = 0, _CSS.index("{", i)
    for k in range(j, len(_CSS)):
        if _CSS[k] == "{":
            depth += 1
        elif _CSS[k] == "}":
            depth -= 1
            if depth == 0:
                return _CSS[:i] + _CSS[k + 1:]
    return _CSS[:i]


def test_every_surface_the_backend_extracts_is_painted():
    """Il disegno e il decodificatore devono conoscere le stesse superfici.

    Una classe estratta e mai dipinta è lavoro pagato e buttato; una dipinta e
    mai estratta è un colore che nessuno vedrà mai.
    """
    import re
    from accoach import trackmesh as tm

    js = (Path(__file__).resolve().parents[1] / "src" / "accoach" / "web" / "app.js").read_text(encoding="utf-8")
    block = js[js.index("const SURFACE_PAINT"):js.index("];", js.index("const SURFACE_PAINT"))]
    painted = set(re.findall(r'\["(\w+)"', block))
    assert painted == set(tm._CLASSES), (sorted(painted), sorted(tm._CLASSES))
