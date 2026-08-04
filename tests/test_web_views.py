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


def test_the_corner_is_turned_by_its_real_shape_not_by_the_stretched_one():
    """×1 e ×3 devono essere la stessa curva, vista uguale.

    L'inquadratura sceglie **l'angolo** che fa stare la curva più grande nel
    riquadro. Se quell'angolo lo decide anche la linea gonfiata, passando a ×3
    la curva viene pure **ruotata** — e siccome a ×3 il fondo sparisce di
    proposito, non resta nessun appiglio per riconoscerla. Due disegni della
    stessa curva che non si somigliano, in un pulsante che serve a confrontarli.

    Quindi: l'angolo dal materiale **vero** (`pool = real`, che non contiene mai
    punti gonfiati), lo zoom da quello **disegnato**, perché a ×3 la tua linea
    non deve uscire dal bordo.
    """
    body = _APPJS[_APPJS.index("  const real = []"):]
    body = body[:body.index("const turn = (")]
    assert "const pool = real;" in body, "l'angolo si sceglie sulla curva vera"
    # `real` prende la tua linea NON gonfiata; `draw` quella gonfiata.
    assert "real.push([you.x[i], you.z[i]])" in body
    assert "draw.push([yx[i], yz[i]])" in body
    # e il riquadro si riallarga su `draw` dopo aver fissato l'angolo
    assert "for (const p of draw)" in body


# --- race pace is wired ----------------------------------------------------

@pytest.mark.parametrize("el", ("st-when", "st-sub", "st-select", "st-numbers",
                                "st-laps", "st-notes", "c-stint"))
def test_the_stint_view_has_the_elements_its_code_reaches_for(el):
    assert f'id="{el}"' in _HTML
    assert f'"{el}"' in _APPJS


def test_the_stint_tab_exists_and_owns_its_panel():
    assert 'data-view="stint"' in _HTML
    assert _view_of_ids()["st-numbers"] == "stint"


def test_the_stint_tab_refetches_rather_than_repainting():
    """The notes strip is written by the backend in the requested language, so a
    cached payload would leave that paragraph in the language you left."""
    block = _APPJS.split("function redrawCurrentView()")[1].split("\n}")[0]
    assert 'VIEW === "stint"' in block
    assert "loadStint(CURRENT" in block


def test_changing_car_and_track_forgets_the_stint_it_was_showing():
    """Stints belong to a car, a track and a tank. Keeping the payload across a
    combo change shows one car's fuel load under another car's name."""
    block = _APPJS.split("sel.onchange = ")[1].split("\n  };")[0]
    assert "STINT = null;" in block
    assert "STINT_I = 0;" in block


def test_the_tyre_charts_live_on_exactly_one_tab():
    """They were on Trends under a heading that said "across the stint", drawn
    over every lap ever recorded for the combo. One panel, one span."""
    assert _view_of_ids()["tyres"] == "stint"
    block = _APPJS.split("async function loadProgress(")[1].split("\n}")[0]
    assert "drawTyres" not in block, "Trends is still drawing the tyres"


def test_trends_says_where_the_tyre_charts_went():
    """A panel that vanishes without a pointer reads as a feature that broke."""
    assert 'id="go-stint"' in _HTML
    assert _view_of_ids()["go-stint"] == "progress"
    assert 'showView("stint")' in _APPJS


def test_a_drift_the_numbers_called_flat_is_not_drawn_as_a_line():
    """The regression line is the picture of the finding. Drawing it under a
    slope that failed its own significance test would put on the canvas exactly
    what the readout refused to put in words."""
    block = _APPJS.split("function drawStintPace(")[1].split("\n}")[0]
    assert "cur.trend.significant" in block


def test_the_pace_chart_is_scaled_to_the_laps_that_were_a_pace():
    """One 3:25 spin in the middle squashes eight laps of racing into a flat
    line at the top of the canvas."""
    block = _APPJS.split("function drawStintPace(")[1].split("\n}")[0]
    assert "l.counted" in block


def test_every_tab_on_the_row_has_a_keyboard_shortcut():
    """The digits were [1-9] and the row grew to ten when Race pace arrived, so
    the last tab silently lost its shortcut. Nothing breaks, nothing logs, and
    the only way to notice is to press 0 and watch nothing happen."""
    tabs = len(re.findall(r'class="tab[ "]', _HTML))
    assert 0 < tabs <= 10, f"{tabs} tabs, more than the digit row can reach"
    block = _APPJS.split("function wireKeys()")[1].split("\n}")[0]
    assert "/^[0-9]$/" in block


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
        decl = re.search(r"display\s*:\s*([\w-]+)", body)
        if decl is None:
            continue
        # `display: none` è l'opposto del pericolo: non può lasciare un pannello
        # a schermo, può solo toglierlo. Serve per lo stato «ancora nessun giro»,
        # dove `#view-flow` riempiva la finestra di una card vuota e spingeva il
        # messaggio sotto la piega. Il divieto vale per chi lo rende visibile.
        if decl.group(1) == "none":
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


# --- naming a corner from the screen (2026-08-04) --------------------------

_I18NJS = (WEB / "i18n.js").read_text(encoding="utf-8")
_CSS = (WEB / "style.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("key", ["line.name.edit", "line.name.hint",
                                 "line.name.save", "line.name.drop",
                                 "line.name.err"])
def test_the_rename_control_speaks_both_languages(key):
    """Every string the driver sees while naming a corner. A missing key does
    not raise here — it renders as the key itself, on screen, in production."""
    m = re.search(r'"' + re.escape(key) + r'":\s*\{([^}]*)\}', _I18NJS)
    assert m, f"{key} is missing from i18n.js"
    assert "en:" in m.group(1) and "it:" in m.group(1)


def test_the_typed_name_is_bounded_by_the_same_number_on_both_sides():
    """The input's maxlength and the server's limit have to agree, or the
    driver types a name the page accepts and the endpoint refuses."""
    from accoach.cornernames import MAX_NAME
    assert f'maxlength="{MAX_NAME}"' in _APPJS


def test_the_name_field_cannot_push_its_own_buttons_off_the_card():
    """It sits in a heading beside Save and Remove, inside a 300 px-wide
    column on the narrow layout. A field with no bound is how that heading
    stops fitting."""
    assert re.search(r"#corner-name\s*\{[^}]*max-width", _CSS, re.S)


def test_saving_a_name_refetches_instead_of_patching_the_label():
    """The name is used by the debrief, the losses, the braking sheet and the
    coach's voice. A screen where only the title changed is the app
    disagreeing with itself."""
    fn = _APPJS[_APPJS.index("async function saveCornerName"):]
    fn = fn[:fn.index("\n}\n")]
    assert "loadLine()" in fn and "loadCombo(" in fn and "SHEET = null" in fn


def test_the_rename_box_only_prefills_a_name_the_driver_typed():
    """The screen caught this and the tests did not: pre-filled with "Corner 1"
    — the detector's count, not a name — one Save with nothing changed stores
    that number as a name, outranking every curated table."""
    fn = _APPJS[_APPJS.index("function renderCornerTitle"):]
    fn = fn[:fn.index("\n}\n")]
    assert "c.typed ? escAttr(c.name)" in fn
    # And "Remove" is only offered where there is something to remove.
    assert re.search(r"c\.typed[^;]*corner-drop", fn, re.S)


def test_the_way_in_is_visible_without_hovering_for_it():
    """Also from the screen. The pencil was hidden until the title was hovered,
    which looked tidy and meant nobody would ever find the only route onto the
    circuits we could not curate."""
    m = re.search(r"\.chart\.corner-map h3 \.rename\s*\{([^}]*)\}", _CSS, re.S)
    assert m, "the rename control lost its own rule"
    opacity = re.search(r"opacity:\s*([\d.]+)", m.group(1))
    assert opacity and float(opacity.group(1)) > 0.3, \
        "a control at opacity 0 is a feature nobody finds"


def test_the_map_labels_corners_by_the_name_everything_else_uses():
    """It drew "T" + the detector's index, and both halves were wrong. The name
    was ignored, so the map read "T1" where hovering the same apex read "Curva
    Niki Lauda" — one screen contradicting itself. And the number was the
    detector's count on *this* lap, which is the sliding number `cornermap`
    exists to stop."""
    fn = _APPJS[_APPJS.index("function drawMapTo"):]
    fn = fn[:fn.index("\n}\n")]
    loop = fn[fn.index("for (const c of a.corners"):]
    loop = loop[:loop.index("\n  }")]
    assert "c.name" in loop, "the map is labelling corners by index again"


# --- the two pedals on the zoomed corner (2026-08-04) ----------------------

def test_the_corner_drawing_uses_the_thresholds_the_rest_of_the_app_measures_with():
    """It drew the brake marker at 0.3, a number from nowhere, while the braking
    sheet on the same page measures onset at `_BRAKE_ON`. Two answers to one
    question, on one screen. Pinned to the Python constants so they cannot drift
    apart again."""
    from accoach.coaching.analyzer import _BRAKE_ON
    from accoach.coaching.diagnosis import _THROTTLE_ON
    fn = _APPJS[_APPJS.index("function drawCornerZoom"):]
    fn = fn[:fn.index("\n}\n")]
    m = re.search(r"const BRAKE_ON = ([\d.]+), THROTTLE_ON = ([\d.]+);", fn)
    assert m, "the corner drawing lost its named thresholds"
    assert float(m.group(1)) == _BRAKE_ON
    assert float(m.group(2)) == _THROTTLE_ON


def test_the_corner_crop_carries_both_pedals():
    """The throttle marker needs the channel, and the crop is the only place it
    can come from."""
    from accoach.trajectory import corner_path
    import inspect
    src = inspect.getsource(corner_path)
    assert '"brake"' in src and '"throttle"' in src


@pytest.mark.parametrize("key", ["line.leg.brake", "line.leg.throttle"])
def test_every_marker_on_the_corner_drawing_is_named_in_the_legend(key):
    """The braking markers were drawn for weeks and were in no legend at all.
    A marker nobody can name is a decoration."""
    assert f'data-i18n="{key}"' in _HTML
    m = re.search(r'"' + re.escape(key) + r'":\s*\{([^}]*)\}', _I18NJS)
    assert m and "en:" in m.group(1) and "it:" in m.group(1)


def test_the_gap_magnifier_no_longer_offers_a_setting_that_overstates():
    """×5 drew a 2.5 m excursion — the 75th percentile of the archive — as 73 px,
    a quarter of the canvas, and still could not show the laps that are too
    close together to see (0.6 px). ×3 is the one that earns its place."""
    assert "[1, 3].map((z) =>" in _APPJS
    assert "[1, 3, 5]" not in _APPJS


def test_no_rule_at_all_can_outrank_the_hidden_class(): 
    """The wider version of the test above, and it is wider because the trap
    sprang again one rung lower.

    `.map-legend .swatch { display: inline-flex }` is two classes against
    `.hidden`'s one, so every legend entry meant to appear only sometimes
    appeared always — the asphalt swatch on laps with no road under them, and
    the "where the lap was lost" cross on laps nobody lost. An ID was never the
    point: **anything** that sets `display` on an element that also carries
    `hidden` wins, so the rule is now checked on every selector that could
    match a hideable element.
    """
    hideable = set(re.findall(r'class="([^"]*\bhidden\b[^"]*)"', _HTML))
    classes = {c for group in hideable for c in group.split() if c != "hidden"}
    ids = set(re.findall(r'id="([\w-]+)"[^>]*class="[^"]*\bhidden\b', _HTML))
    ids |= set(re.findall(r'class="[^"]*\bhidden\b[^"]*"[^>]*id="([\w-]+)"', _HTML))

    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", _screen_css()):
        sel, body = m.group(1).strip(), m.group(2)
        decl = re.search(r"display\s*:\s*([\w-]+)", body)
        if decl is None or decl.group(1) == "none" or ":not(.hidden)" in sel:
            continue
        # A rule scoped to a page STATE on <body> is the deliberate exception:
        # `body.no-data .empty { display: block }` exists to bring the "no laps
        # yet" messages forward, and everything around them is switched off by
        # the same block. The hazard is a component rule that quietly outranks
        # `hidden` wherever that component appears.
        if sel.startswith("body."):
            continue
        last = sel.split(",")[-1].strip()
        target = last.split()[-1] if last.split() else last
        names = set(re.findall(r"[.#]([\w-]+)", target))
        clash = (names & classes) or (names & ids)
        assert not clash, (
            f"{sel!r} sets display on something that is hidden by class "
            f"({sorted(clash)}) — qualify it with :not(.hidden)")
