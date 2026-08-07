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
    """The digits were [1-9] and the row grew to ten when Race pace arrived, then
    to eleven when the recap became the landing tab. Nothing breaks, nothing
    logs, and the only way to notice a tab fell off the end is to press its key
    and watch nothing happen.

    Pinning the ceiling as a bare number (`<= 11`) is exactly the mistake that
    caused this twice already: it and the real tab count are two hand-kept
    numbers that only happen to agree today. The ceiling here is derived from
    `KEY_ROW` itself, so a twelfth tab with no wider row fails this test on
    the actual property (every tab reachable by one key) instead of on a
    number someone forgot to bump.
    """
    tabs = len(re.findall(r'class="tab[ "]', _HTML))
    m = re.search(r'const KEY_ROW = "([^"]+)"', _APPJS)
    assert m, "wireKeys()/wireTabs() lost their shared KEY_ROW constant"
    assert 0 < tabs <= len(m.group(1)), \
        f"{tabs} tabs, more than KEY_ROW ({m.group(1)!r}) can reach"


def test_every_reachable_tab_gets_its_shortcut_shown():
    """`wireTabs()` used to stop labelling tooltips at the ninth tab
    (`i <= 9`), so the tenth tab's shortcut (kbd `0`) worked but nobody could
    find it — and an eleventh would have inherited the same silent gap. It has
    to label every tab `KEY_ROW` can reach, derived the same way, not a second
    hand-kept number."""
    block = _APPJS.split("function wireTabs()")[1].split("\n}")[0]
    assert "i <= 9" not in block
    assert "KEY_ROW.length" in block


def test_printing_hides_every_view_without_naming_them():
    """The print sheet is the braking cheat sheet and nothing else.

    The rule used to list the eight panels it wanted gone, by id. A ninth tab
    then printed itself underneath the sheet, and the only way to notice is to
    print. Derived from the id prefix, a new view is hidden the day it is added.
    """
    block = _CSS[_CSS.index("@media print"):]
    block = block[:block.index("\n}")]
    assert '[id^="view-"]' in block
    # Il foglio vive dentro il Confronto, che porta con sé grafici, riepilogo,
    # cascata e debrief: si spegne per discendenza e si riaccende la SOLA catena
    # che arriva al foglio. Fra due `!important` decide la specificità, quindi
    # ogni selettore che riaccende dev'essere più specifico di quello che ha
    # spento — verificato per mutazione (accorciare `#view-compare > .cmp-shell`
    # a `.cmp-shell` stampa una pagina vuota).
    assert "#view-compare > *, .cmp-shell > *, .cmp-map > *" in block
    assert ("#view-compare, #view-compare > .cmp-shell, .cmp-shell > .cmp-map,\n"
            "  .cmp-map > #brakesheet { display: block !important; }") in block


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


def test_the_tab_row_scrolls_itself_at_every_width():
    """Misurato col browser in un riquadro da 768 px (un tablet accanto al
    volante, uso dichiarato di quest'app): la fila di schede era larga 1016 px e
    portava la PAGINA a scorrere di lato di 248 px con undici schede, 170 con
    dieci — su **ogni** vista, perché la fila sta fuori da tutte, quindi non è
    una vista a sfondare ma la navigazione. Lo scorrimento della fila esisteva
    già, ma solo sotto i 520 px: fra 521 px e ~1000 px non c'era niente. La
    regola vive quindi sul selettore base e non in un @media, e `.tab` non si
    lascia comprimere (`flex: 0 0 auto`) invece di spezzare le etichette."""
    assert "overflow-x: auto" in _rule(".tabs {")
    tab = _rule("\n.tab {")
    assert "flex: 0 0 auto" in tab and "white-space: nowrap" in tab


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
    # E senza i commenti. Questo foglio ne ha di lunghi, e finivano DENTRO il
    # selettore di ogni regola che li segue (`[^{}]+` risale fino alla graffa
    # precedente): un selettore così non si riconosce più, e la regola che
    # segue un commento sfuggiva a ogni controllo. Nell'altro verso, un
    # commento che *cita* una regola («`.empty` è `display: none`») veniva
    # letto come una regola vera. Misurato: senza questo taglio la mutazione
    # «una regola nuova spegne `.missing`» restava VERDE.
    css = re.sub(r"/\*.*?\*/", "", _CSS, flags=re.S)
    # EVERY print block, not just the first: a second one added higher up the
    # file used to be the one that got stripped, leaving the real print rules in
    # the "screen" text and failing two tests for a reason that had nothing to
    # do with either.
    while True:
        i = css.find("@media print")
        if i == -1:
            return css
        depth, j = 0, css.index("{", i)
        cut = None
        for k in range(j, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    cut = k
                    break
        css = css[:i] + (css[cut + 1:] if cut is not None else "")


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


def _i18n_between(first: str, last: str) -> str:
    """La fetta di ``i18n.js`` fra due chiavi, con l'ordine verificato.

    Ritagliare fra due `index()` è comodo per isolare una voce e chiedere che
    NON contenga qualcosa. Ma se un giorno le due chiavi vengono scambiate di
    posto in ``i18n.js`` — un riordino innocuo, che nessuno viene a rileggere
    qui — la fetta esce **vuota**, e ogni ``assert x not in fetta`` passa per
    sempre su qualunque testo. La difesa si spegnerebbe in silenzio proprio
    mentre resta verde. Dimostrato per mutazione: invertendo le due voci e
    rimettendo il difetto originale in piedi, la suite non se ne accorgeva.

    Quindi l'ordine è un'asserzione, non un'assunzione.
    """
    i, j = _I18NJS.index(first), _I18NJS.index(last)
    assert i < j, (
        f"{first} non viene più prima di {last} in i18n.js: la fetta fra le due "
        f"sarebbe vuota e il test passerebbe su qualunque testo"
    )
    return _I18NJS[i:j]


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
    exists to stop.

    The loop grew a neighbour-distance scan on 2026-08-05 (see
    `test_the_map_label_degrades_with_the_canvas_it_is_drawn_to`), so this only
    pins the surviving half of the original bug: the label still has to start
    from the corner's name, not just its index."""
    fn = _APPJS[_APPJS.index("function drawMapTo"):]
    fn = fn[:fn.index("\n}\n")]
    block = fn[fn.index("// Corner labels at each apex"):fn.index("// Start/finish")]
    assert "c.name" in block, "the map is labelling corners by index again"


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


def test_the_whole_lap_map_draws_no_road_under_the_lines():
    """Added on 2026-08-04 and taken back out the same day, so the reason is
    kept where the next person will look.

    At whole-lap zoom the fit is 0.869 px per metre: the Red Bull Ring's 11.9 m
    of asphalt is 10.3 px, and the reviewed line is 2-7 px because its thickness
    carries the speed gap. A line two thirds as wide as the road, centred on a
    racing line that uses the kerb, spills past a road drawn to scale — so the
    picture claimed the car was off the track on corners where it measurably was
    not (0-2% of samples outside the ribbon, worst case 0.4 m).

    The zoomed corner keeps its asphalt: there the corner fills the box and the
    line is a thread across it.
    """
    fn = _APPJS[_APPJS.index("function drawMapTo"):]
    fn = fn[:fn.index("\n}\n")]
    assert "drawRoad(" not in fn, (
        "the whole-lap map is drawing a road again — read the comment above it")


# --- braking references typed from the sheet (roadmap item 2) --------------

@pytest.mark.parametrize("key", ["brk.mark.edit", "brk.mark.hint"])
def test_the_braking_reference_cell_speaks_both_languages(key):
    m = re.search(r'"' + re.escape(key) + r'":\s*\{([^}]*)\}', _I18NJS)
    assert m and "en:" in m.group(1) and "it:" in m.group(1)


def test_the_reference_cell_only_prefills_what_the_driver_typed():
    """Pre-filled with a phrase we ship, one Save with nothing changed adopts
    our wording as theirs — where it then outranks the table it came from."""
    fn = _APPJS[_APPJS.index("function editMark"):]
    fn = fn[:fn.index("\n}\n")]
    assert "typed ? btn.textContent.trim() : \"\"" in fn
    assert re.search(r"typed\s*\?[^;]*drop", fn, re.S)


def test_saving_a_reference_refetches_the_sheet():
    """The same phrase is spoken by the debrief; a screen where only this cell
    changed is the app disagreeing with itself."""
    fn = _APPJS[_APPJS.index("function editMark"):]
    fn = fn[:fn.index("\n}\n")]
    assert "SHEET = null" in fn and "loadBraking()" in fn


def test_the_reference_length_agrees_on_both_sides():
    from accoach.cornernames import MAX_MARK
    fn = _APPJS[_APPJS.index("function editMark"):]
    assert f'maxlength="{MAX_MARK}"' in fn[:fn.index("\n}\n")]


def test_the_pencil_does_not_print():
    """The sheet is meant to be printed and taped up, and a pencil drawn on
    paper is a smudge."""
    i = _CSS.find("@media print")
    block = _CSS[i:_CSS.index("\n}", i)]
    assert ".pencil" in block


# --- il rail -----------------------------------------------------------------

def test_the_rail_lives_outside_every_view_panel():
    """Un rail dentro un pannello sarebbe sei rail: sei canvas, sei hover da
    cablare e sei posti dove ricordarsi di ridisegnare. Fuori da tutti, è uno."""
    where = _view_of_ids()
    assert "rail" in where, "manca #rail in index.html"
    assert where["rail"] == "", "il rail sta dentro un pannello di vista"
    # `_view_of_ids` lavora per ordine nel documento: gli basta che nessun
    # `id="view-…` preceda `id="rail"`. Un rail spostato DENTRO `.views`, sopra
    # `#view-flow` (il primo pannello), passerebbe comunque quell'assert — e il
    # layout sarebbe rotto lo stesso, perché `.stage > .views` azzera `--gut`
    # per i discendenti di `.views`, rail compreso. La verifica vera è
    # strutturale: il rail dev'essere un FRATELLO di `.views`, non un figlio.
    assert _HTML.index('id="rail"') < _HTML.index('class="views"'), \
        "il rail dev'essere un fratello di .views, non un discendente"


def test_every_view_panel_lives_inside_the_stage():
    """Il palco è la griglia a due colonne: un pannello fuori tornerebbe a
    larghezza piena e finirebbe sotto il rail."""
    stage = _HTML.split('<div class="stage">')[1].split('<!-- /stage -->')[0]
    for panel in _PANELS:
        assert f'id="view-{panel}"' in stage, panel


def test_the_rail_is_declared_once_and_only_for_views_that_exist():
    """Un elenco scritto due volte è un elenco che diverge."""
    assert _APPJS.count("const RAIL_VIEWS") == 1
    body = _APPJS.split("const RAIL_VIEWS = [")[1].split("]")[0]
    for name in re.findall(r'"([\w-]+)"', body):
        assert name in _TABS, name


def test_rail_views_is_exactly_the_views_about_one_lap():
    """Il test sopra verifica solo la metà positiva (ogni nome elencato è una
    scheda vera) — passerebbe anche con quattro nomi, o con sei se qualcuno
    aggiungesse "session" per sbaglio. Le schede sopra il giro (Com'è andata,
    Allenamento, Sessione, Passo gara, Andamento) non hanno un giro da
    ritagliare, quindi un rail lì risponderebbe a un clic senza cambiare
    niente — «peggio di un comando assente», dice il commento sopra
    RAIL_VIEWS. Erano sei finché la Mappa era una scheda; ora la mappa è la
    colonna destra del Confronto e il rail la segue lì."""
    body = _APPJS.split("const RAIL_VIEWS = [")[1].split("]")[0]
    names = re.findall(r'"([\w-]+)"', body)
    assert set(names) == {"flow", "compare", "line", "sectors", "dynamics"}, names
    # Insiemistica a parte: le due metà devono partizionare le schede vere, così
    # una scheda nuova non può restare fuori da entrambe senza che si veda.
    assert set(names) | {"recap", "training", "session", "stint", "progress"} == set(_TABS)


def test_switching_tab_says_whether_this_one_has_a_rail():
    """La classe si applica anche al primo paint (vedi il test sotto), quindi
    la logica vive in `applyRailed`, non più inline qui — ma `showView` deve
    comunque richiamarla a ogni cambio di scheda."""
    block = _APPJS.split("function showView(")[1].split("\n}")[0]
    assert "applyRailed(" in block


def test_the_starting_tab_gets_the_rail_class_without_a_click():
    """`showView` mette la classe `railed` solo quando viene chiamata, e
    `init()` la chiama solo se la vista salvata in localStorage è diversa da
    quella già `active` in HTML. Con localStorage vuoto — la prima visita, il
    caso più comune — o con una vista salvata uguale a quella di partenza,
    `showView` non scattava mai: il rail restava nascosto sulla prima
    schermata anche su una scheda che lo prevede, finché non si cliccava un
    tab qualsiasi. Il difetto era invisibile perché nessuno guarda la pagina
    appena caricata senza toccarla — la scheda di partenza va trattata come
    tutte le altre nove."""
    block = _APPJS.split("async function init(")[1].split("\n}")[0]
    assert "applyRailed(" in block, \
        "init() non applica mai la classe railed sulla scheda di partenza"


def test_apply_railed_toggles_the_class_it_is_named_for():
    """L'estrazione ha spostato la verifica su "chi chiama `applyRailed`" e ha
    lasciato scoperto il meccanismo stesso: nulla controllava più che il suo
    corpo faccia davvero il toggle su `RAIL_VIEWS`, invece di essere una
    funzione vuota chiamata da entrambi i posti giusti."""
    block = _APPJS.split("function applyRailed(")[1].split("\n}")[0]
    assert 'classList.toggle("railed", RAIL_VIEWS.indexOf(name) >= 0)' in block


def test_init_applies_the_rail_before_the_first_draw():
    """Il bug critico dopo il primo fix: `applyRailed` scattava in `init()`,
    ma DOPO `await loadCombo(...)`. `loadCombo` disegna `renderFlow`/`redraw`
    in modo sincrono non appena il fetch risponde, e quei disegni leggono
    `cv.clientWidth` — che dipende dalla classe `railed` su <body>. Con quella
    ancora assente il primo disegno usciva a larghezza piena; poi il rail
    compariva senza che nulla lo seguisse a ridisegnare. Succede proprio sulla
    prima schermata: quando la vista salvata coincide con quella di partenza
    (o non c'è), `showView` — che ha l'ordine giusto — non scatta affatto."""
    block = _APPJS.split("async function init(")[1].split("\n}")[0]
    assert block.index("applyRailed(") < block.index("await loadCombo("), \
        "applyRailed deve scattare prima del primo loadCombo, non dopo"


def test_the_rail_is_drawn_outside_the_per_view_switch():
    """`redrawCurrentView` è uno switch per-vista e il rail non appartiene a
    nessuna vista. Dentro un ramo, al cambio scheda resterebbe fermo all'ultimo
    giro e dopo un resize l'hover punterebbe al posto sbagliato.

    Il criterio è l'indentazione: una riga a sé, ai due spazi del corpo della
    funzione, non può stare dentro un `if` — un ramo la indenterebbe di più o se
    la porterebbe sulla propria riga."""
    block = _APPJS.split("function redrawCurrentView()")[1].split("\n}")[0]
    assert re.search(r"^  drawRail\(\);$", block, re.M), \
        "drawRail() dev'essere una riga a sé, fuori dallo switch per-vista"


def test_a_lap_without_coordinates_still_has_a_rail():
    """I giri ACC registrati prima dello schema con le coordinate sono esattamente
    questo caso, e col rail persistente diventerebbero una colonna vuota su tutte
    le schede."""
    assert 'id="rail-nomap"' in _HTML
    block = _APPJS.split("function drawRail(")[1].split("\n}")[0]
    assert '$("rail-nomap")' in block, "il segnaposto non viene passato a drawMapTo"


def test_the_rail_is_drawn_when_a_lap_loads():
    """Un nuovo giro cambia le curve e le perdite che il rail elenca (nome,
    numero, quanto è costata ciascuna): senza questa chiamata la colonna
    resterebbe quella del giro precedente finché non si cambia scheda o non
    si ridimensiona la finestra — nessuno dei due gesti segue automaticamente
    un cambio di giro dal menu a tendina."""
    block = _APPJS.split("async function loadCombo")[1].split("\n}")[0]
    assert "drawRail();" in block


def test_the_rail_list_is_drawn_outside_the_per_view_switch():
    """`drawRail()` (la mappa) è ancorato fuori dallo switch di
    `redrawCurrentView` — vedi il test sopra — ma `drawRailList()` (la
    classifica delle curve sotto la mappa) non lo era: se finisse dentro un
    ramo per-vista, la lista invecchierebbe in silenzio al cambio scheda
    (nuovo giro caricato mentre si è su Allenamento, poi si passa a Confronto)
    e dopo un cambio lingua, esattamente come per `drawRail()`."""
    block = _APPJS.split("function redrawCurrentView()")[1].split("\n}")[0]
    assert re.search(r"^  drawRailList\(\);$", block, re.M), \
        "drawRailList() dev'essere una riga a sé, fuori dallo switch per-vista"


def test_the_rail_lists_the_clean_corners_too():
    """La classifica dice da dove cominciare; il selettore deve poter aprire
    anche una curva dove non hai perso niente — è lì che si va a vedere cosa hai
    fatto giusto."""
    block = _APPJS.split("function railRows(")[1].split("\n}")[0]
    assert "cold" in block and "hot" in block


def test_the_selected_corner_is_remembered_by_number_not_by_name():
    """Due curve possono chiamarsi uguale: su ogni pista senza nomi curati si
    chiamano tutte `Corner N`, e la riga accesa sarebbe la prima delle due."""
    block = _APPJS.split("function cornerWindow(")[1].split("\n}")[0]
    assert "corner: c.index" in block


def test_clicking_a_corner_moves_the_shared_window():
    block = _APPJS.split("function drawRailList()")[1].split("\n\nfunction")[0]
    assert "setRange(cornerWindow(" in block
    assert "setRange(null)" in block, "manca «Tutto il giro»"


# --- il rail su un giro vero: barra e nomi (2026-08-05) ---------------------
# Trovati misurando nel DOM un giro vero (Monza, McLaren 720S GT3, 7 curve):
# nessuno dei due era visibile a un test statico prima che qualcuno guardasse
# lo schermo.

def test_the_rail_bar_spans_the_full_row_width():
    """Misurato su quel giro: una colonna da 34px per una barra che rappresenta
    un rapporto 20:1 (−4.72s contro −0.24s) lasciava quattro righe su cinque
    sotto gli 8px, indistinguibili l'una dall'altra e dai numeri già scritti
    accanto. Deve stare sotto il nome, a piena larghezza di riga — niente
    scala non lineare per farcela stare in una colonna stretta."""
    row = _rule(".rail-row {")
    assert "34px" not in row, "la barra non deve più avere una colonna fissa stretta"
    bar = _rule(".rail-row .bar {")
    assert "grid-column: 1 / -1" in bar


def test_the_rail_list_scrolls_on_its_own():
    """`.rail` è `position: sticky`, non `fixed`: con 16-20 curve la lista
    supera l'altezza dello schermo, e senza un proprio scorrimento le ultime
    righe smetterebbero di essere raggiungibili una volta che la pagina ha
    finito di scorrere."""
    block = _rule(".rail-list {")
    assert "overflow-y: auto" in block


def test_the_map_label_avoids_real_text_collisions_not_apex_distance():
    """Trovato il 2026-08-05 guardando la mappa grande vera (Monza, tela
    1036px): la prima versione decideva sulla distanza fra gli APICI, e su
    quella tela scartava un nome («Variante del Rettifilo») che non avrebbe
    mai toccato nulla — il vicino più vicino stava a un centinaio di pixel.
    Quello che collide sono i RETTANGOLI di testo, non i punti: `drawMapTo`
    deve confrontare le etichette già scritte, non una distanza a soglia."""
    fn = _APPJS[_APPJS.index("function drawMapTo"):]
    fn = fn[:fn.index("\n}\n")]
    block = fn[fn.index("// Corner labels at each apex"):fn.index("// Start/finish")]
    assert "measureText(" in block
    assert "overlaps(" in block
    assert "Math.hypot" not in block, \
        "la distanza fra apici non deve tornare a decidere l'etichetta"
    assert 'ctx.fillText(c.name || ("T" + (c.index + 1)), X(rv.x[i]) + 6, Y(rv.z[i]) - 4)' \
        not in block, "il fillText incondizionato non deve tornare"


def test_corner_bands_still_uses_the_shared_threshold():
    """`degradeLabel` resta la soglia di `cornerBands`, che ha uno spazio
    lineare (una fascia lungo un asse) su cui un singolo numero funziona. La
    mappa non la usa più — lì collidono rettangoli veri, non un numero — ed è
    corretto che restino due meccanismi diversi per due geometrie diverse."""
    assert "function degradeLabel(" in _APPJS
    bands = _APPJS.split("function cornerBands(")[1].split("\n}")[0]
    assert "degradeLabel(ctx" in bands


def test_the_map_label_also_checks_its_share_of_the_canvas():
    """Trovato il 2026-08-05, un giro dopo il fix della collisione: la
    collisione da sola non basta. Sul rail (220px) «Variante della Roggia»
    (109px) non toccava nessun'altra etichetta e passava il test — ma da
    sola copriva metà della larghezza della mappa, cancellando il disegno
    del giro che il rail esiste per mostrare. Serve una condizione di
    proporzione, verificata PRIMA della collisione sul nome intero, ed
    espressa come FRAZIONE della tela — non un numero di pixel fisso: la
    stessa funzione disegna una mappa da 220px e una da quasi 1000, e un
    valore assoluto sarebbe tarato sull'una o sull'altra."""
    fn = _APPJS[_APPJS.index("function drawMapTo"):]
    fn = fn[:fn.index("\n}\n")]
    block = fn[fn.index("// Corner labels at each apex"):fn.index("// Start/finish")]
    m = re.search(r"maxLabelW\s*=\s*w\s*\*\s*([\d.]+)", block)
    assert m, "la soglia dev'essere una frazione di w (la tela), non un pixel fisso"
    frac = float(m.group(1))
    assert 0 < frac <= 0.5, f"{frac} non è 'una frazione ragionevole' della tela"
    gate = "ctx.measureText(full).width < maxLabelW"
    assert gate in block
    assert block.index(gate) < block.index("rectOf(full)"), \
        "la proporzione va verificata prima di provare la collisione sul nome intero"


def test_the_rail_hover_is_routed_per_view_not_wired_to_one():
    """L'hover della minimappa chiamava `redraw`, che è la funzione della sola
    vista Confronto. Su un rail che vive su sei schede sarebbe muto sulle altre
    cinque — o peggio, ridisegnerebbe una vista che non è sullo schermo."""
    assert "function hoverTo(" in _APPJS
    block = _APPJS.split("function hoverTo(")[1].split("\n}\n")[0]
    # «map» non è più nell'elenco: la mappa ha smesso di essere una vista e vive
    # accanto ai grafici del Confronto (il suo mirino si controlla nel test
    # dedicato, che chiede `drawMap(DATA, p)` DENTRO il ramo del Confronto).
    for view in ("dynamics", "line", "compare"):
        assert f'"{view}"' in block, view


def test_the_compare_minimap_is_gone_now_that_the_rail_is_the_map():
    """La stessa figura due volte a venti centimetri: è la ripetizione che il
    panel ha misurato come causa della «mancanza di logica» percepita."""
    assert "c-minimap" not in _HTML
    assert "drawMiniMap" not in _APPJS
    assert "MINI_HIT" not in _APPJS


def test_all_hover_sources_route_through_hoverTo_not_the_view_function():
    """Il rail funzionava solo come sorgente: i gestori dei grafici (Confronto,
    Dinamica, Traiettoria) e della mappa grande chiamavano `redraw`/
    `drawDynamics`/`renderLine`/`drawMap` DIRETTAMENTE — `hoverTo` è l'unica
    funzione che aggiorna anche il rail. Se un gestore futuro richiama di nuovo
    la funzione di vista invece di `hoverTo`, il rail torna a essere a senso
    unico: sorgente di mirino, mai destinazione — esattamente come nacque la
    minimappa cablata alla sola vista Confronto."""
    block = _APPJS.split("function wireHover()")[1].split("\n}\n")[0]
    for direct in ("redraw(", "drawDynamics(", "renderLine(", "drawMap("):
        assert direct not in block, f"{direct} bypassa hoverTo dentro wireHover"
    # Otto sorgenti di hover (grafici Confronto, mappa grande, rail, tracce
    # Dinamica, G-G, curva ingrandita, offset/curvatura, nastro bilanciamento)
    # per due eventi (move, leave) = almeno 16 chiamate a hoverTo.
    assert block.count("hoverTo(") >= 16


def test_drawRail_takes_an_explicit_point_instead_of_only_reading_LAST_HOVER():
    """`drawRail` leggeva `LAST_HOVER` da sé; chiamata da dentro `hoverTo` in un
    punto dove quella variabile non fosse ancora aggiornata, avrebbe disegnato
    il mirino di un istante prima. Un parametro esplicito — con `LAST_HOVER`
    come default per chi ridisegna la vista intera senza un punto fresco in
    mano — toglie la dipendenza dall'ordine delle righe."""
    assert "function drawRail(p = LAST_HOVER)" in _APPJS
    block = _APPJS.split("function drawRail(")[1].split("\n}")[0]
    assert 'drawMapTo($("c-rail"), $("rail-nomap"), DATA, p)' in block
    hover_block = _APPJS.split("function hoverTo(")[1].split("\n}\n")[0]
    assert "drawRail(p);" in hover_block


def test_the_hero_row_has_no_orphaned_minimap_column():
    """La seconda colonna della griglia (360px) era per la minimappa; rimossa
    lei dal markup, un `.hero` ancora a due colonne lascerebbe quello spazio
    riservato e vuoto invece di far respirare il riepilogo a piena larghezza."""
    hero_block = _CSS[_CSS.index(".hero {"):_CSS.index("/* --- Your braking points")]
    assert "grid-template-columns" not in hero_block
    assert "360px" not in hero_block
    assert "minimap" not in hero_block.lower()
    assert "padding-left: var(--gut)" in hero_block


def test_hoverTo_never_nulls_last_hover_on_mouse_leave():
    """`updateReadout` (vista Confronto) confronta `LAST_HOVER` con `null` per
    decidere se congelare il readout (l'ultimo valore, spento) o svuotarlo al
    suggerimento — un confronto valido solo se `hoverTo` non lo azzera già in
    anticipo. Uscire dal rail deve congelare il readout esattamente come uscire
    dai grafici, non cancellarlo all'istante."""
    block = _APPJS.split("function hoverTo(")[1].split("\n}\n")[0]
    assert re.search(r"if\s*\(\s*p\s*!=\s*null\s*\)\s*LAST_HOVER\s*=\s*p;", block), \
        "LAST_HOVER va scritto solo quando p è un punto vero, mai azzerato qui"
    # Ogni occorrenza dell'assegnazione dev'essere dietro quella guardia — non
    # deve restarne una incondizionata, eseguita anche quando p è null.
    assert block.count("LAST_HOVER = p;") == len(
        re.findall(r"if\s*\(\s*p\s*!=\s*null\s*\)\s*LAST_HOVER\s*=\s*p;", block)
    ), "trovata un'assegnazione a LAST_HOVER non protetta dalla guardia p != null"


# --- correzioni della revisione finale (2026-08-05) -------------------------

def test_the_gutter_moved_from_main_to_the_stage():
    """Lo spec della revisione lo chiama il rischio di regressione principale
    della spedizione del rail, e non aveva un test: il gutter di pagina si è
    spostato da `main` (una banda per vista) a `.stage` (l'intero palco a due
    colonne), e `.stage > .views` lo azzera per i propri discendenti così non
    si applica due volte. Se `.stage` smettesse di pagarlo, o `.views`
    smettesse di azzerarlo, il commento sopra la regola dice cosa succede su
    un monitor largo: 480px di vuoto fra il rail e i grafici."""
    stage = _rule(".stage {")
    assert "padding: 0 var(--gut)" in stage
    views = _rule(".stage > .views {")
    assert "--gut: 0px" in views


def test_line_chip_click_also_refreshes_the_rail():
    """Chip e rail scelgono la stessa finestra condivisa (`RANGE`) ma la
    leggono con due chiavi diverse — posizione nell'array di Traiettoria
    contro numero di curva — e prima di questo fix non si parlavano affatto:
    un clic sul chip aggiornava `RANGE` e richiamava `renderLine(null)` da
    solo, senza mai passare da `redrawCurrentView`, quindi il rail — che vive
    fuori da questa vista — restava con la riga della curva precedente ancora
    accesa. Trovato guardando lo schermo in entrambi i versi, non da un test."""
    handler = _APPJS.split("setRange(cornerWindow(L.corners[LINE_I]));")[1].split("};")[0]
    assert "redrawCurrentView();" in handler
    assert "renderLine(null);" not in handler


def test_the_line_view_translates_the_rails_corner_number_into_its_own_index():
    """Il rail sceglie una curva per NUMERO (`RANGE.corner`, il campo `index`
    di `/api/analysis`); la Traiettoria naviga per POSIZIONE nel proprio
    elenco (`LINE_I`, indice dentro `L.corners`, da `/api/trajectory` — un
    elenco che può avere curve diverse). Prima di questo fix un clic su una
    riga del rail cambiava `RANGE` senza mai toccare `LINE_I`: il disegno
    ingrandito, il titolo, la tabella e il chip acceso restavano sulla curva
    di prima. Una ricerca per `index` — non un'assegnazione diretta fra le due
    chiavi — è ciò che li fa concordare."""
    block = _APPJS.split("function renderLine(cx)")[1].split("\n}\n\n")[0]
    assert "L.corners.findIndex((cc) => cc.index === RANGE.corner)" in block
    assert "LINE_I = pos;" in block


def test_the_rail_is_hidden_when_printing():
    """La derivazione di stampa (`[id^="view-"]`, vedi il test sui pannelli)
    non prende `#rail`: vive apposta fuori da ogni pannello di vista, quindi
    senza un'eccezione esplicita la scheda frenate — pensata per essere
    stampata e attaccata al volante — usciva con la colonna del rail (mappa
    su fondo scuro, sette bottoni) e il resto della pagina compresso, perché
    `.stage` restava `display: flex` anche in stampa."""
    block = _CSS.split("@media print {")[1].split("\n}\n")[0]
    assert "#rail" in block, "il rail non è fra gli elementi nascosti in stampa"
    assert ".stage { display: block; }" in block, \
        "senza .stage a blocco il resto della pagina resta stretto in stampa"


# --- la pastiglia mancava a riposo sulla Mappa (2026-08-05, seconda ondata) -

def test_the_map_readout_legend_is_never_written_without_its_chip():
    """`MAP_READOUT_DEFAULT()` è la legenda a riposo della Mappa. Prima di
    questo fix veniva anteposta a mano dalla pastiglia (`rangeChip()`) in ogni
    chiamante — e un chiamante l'aveva dimenticata (vedi il test sotto): la
    finestra restava accesa ma la pastiglia spariva finché non si muoveva il
    mouse. Un solo punto della chiama (`mapReadoutHTML`, che antepone sempre
    `rangeChip()`) rende impossibile scrivere la legenda senza la pastiglia,
    invece di fidarsi che ogni chiamante se ne ricordi."""
    assert _APPJS.count("MAP_READOUT_DEFAULT()") == 1, \
        "MAP_READOUT_DEFAULT() dev'essere chiamata da un solo posto (mapReadoutHTML)"
    wrapper = _APPJS.split("function mapReadoutHTML(")[1].split("\n}")[0]
    assert "MAP_READOUT_DEFAULT()" in wrapper
    assert "rangeChip()" in wrapper


def test_the_map_readout_is_written_only_inside_drawMap():
    """`drawMap` è chiamata da tre posti (`loadCombo`, `redrawCurrentView` sul
    ramo Mappa, `hoverTo`): prima di questo fix ognuno scriveva anche
    `#map-readout` per conto proprio, e bastava che uno se ne dimenticasse —
    `redrawCurrentView` disegnava la mappa al cambio scheda senza mai toccare
    il readout, quindi la pastiglia non compariva finché non si passava da
    `loadCombo` o da un hover vero. Scritto una sola volta, dentro `drawMap`
    stessa, nessuno dei tre chiamanti può più dimenticarlo."""
    assert _APPJS.count("mapReadoutHTML(") == 2, \
        "una definizione e una sola chiamata: mapReadoutHTML deve restare interna a drawMap"
    block = _APPJS.split("function drawMap(a, cx)")[1].split("\n}")[0]
    assert "mapReadoutHTML(cx)" in block, \
        "drawMap deve scrivere #map-readout da sé, non lasciarlo ai chiamanti"


# --- il gemello: la pastiglia mancava anche su Dinamica senza dati ----------

def test_the_dyn_readout_is_written_only_inside_updateDynReadout():
    """Stesso difetto della Mappa, sull'altra scheda: `drawDynamics` ha due
    rami — canali di dinamica presenti o assenti — e prima di questo fix solo
    il primo passava da `updateDynReadout` (che antepone sempre
    `rangeChip()`). Il ramo "nessun dato" (un giro senza canali di dinamica)
    scriveva `#dyn-readout` a mano, con la sola frase di default: nessuna
    pastiglia, nessuna ✕ per annullare la finestra. Un solo punto d'accesso
    al readout — `$("dyn-readout")`, dentro `updateDynReadout` — rende
    impossibile ripetere l'errore in un ramo futuro di `drawDynamics`."""
    assert _APPJS.count('$("dyn-readout")') == 1, \
        "dyn-readout deve avere un solo punto d'accesso: dentro updateDynReadout"
    block = _APPJS.split("function drawDynamics(cx)")[1].split("\n}")[0]
    assert block.count("updateDynReadout(DATA,") == 2, \
        "entrambi i rami di drawDynamics (dati presenti e assenti) devono passare da updateDynReadout"
    assert 't("dyn.readout")' not in block, \
        "drawDynamics non deve più scrivere la frase di default a mano: solo updateDynReadout lo fa"


def test_the_dyn_readout_default_text_always_carries_the_chip():
    """`updateDynReadout` è il solo punto che scrive `#dyn-readout` (vedi il
    test sopra): se il suo stesso ramo "a riposo" dimenticasse `rangeChip()`,
    nessun chiamante potrebbe più rimediarlo."""
    block = _APPJS.split("function updateDynReadout(a, p)")[1].split("\n}")[0]
    assert "rangeChip()" in block
    assert 'chip + t("dyn.readout")' in block


# --- la curva per sessione, sotto i punti deboli (2026-08-06) ---------------

def test_the_session_series_has_a_home_on_the_trends_tab():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="corner-sessions"' in html
    # Presente non basta: deve stare sulla scheda Andamento, non su una a caso
    # — una `id="corner-sessions"` incollata altrove nel file passerebbe la
    # sola ricerca di stringa qui sopra.
    assert _view_of_ids()["corner-sessions"] == "progress"


def test_the_series_is_rendered_when_the_tab_loads():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "renderCornerSessions(p.corner_sessions)" in js
    # La sola ricerca di stringa sopra passerebbe anche con la chiamata dentro
    # un commento, o con la funzione mai definita: qui si verifica che sia
    # dichiarata davvero e che la chiamata viva nel corpo di `loadProgress`,
    # non altrove nel file.
    assert "function renderCornerSessions(rows)" in js
    block = js.split("async function loadProgress(")[1].split("\n}")[0]
    assert "renderCornerSessions(p.corner_sessions)" in block


# --- "Com'è andata": the recap, and the door onto the report (2026-08-06) ---

def test_the_recap_has_a_home_and_it_is_the_landing_view():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="view-recap"' in html
    assert 'data-view="recap"' in html
    # la vista d'ingresso è l'unica senza `hidden`
    assert 'id="view-recap" class="hidden"' not in html
    assert 'id="view-flow" class="hidden"' in html


def test_the_recap_call_is_wired_not_just_declared():
    """A bare `"renderRecap(" in js` check (the brief's original Step 1 test)
    is incapable of failing: the substring is right there in its own
    `function renderRecap(` line even if nothing ever calls it. The call has
    to live inside `renderSession`, which is what actually runs when the
    shared /api/sessions payload lands — verified by mutation: moving the
    call out of `renderSession` turns this red and leaves the bare check
    green."""
    js = (WEB / "app.js").read_text(encoding="utf-8")
    block = js.split("function renderSession(s)")[1].split("\n}")[0]
    assert "renderRecap(" in block


def _recap_render_body() -> str:
    return _APPJS.split("function renderRecap(")[1].split("\n}")[0]


def test_the_total_and_the_five_parts_share_one_sign_convention():
    """`gain_avg_s` used to print with a literal `"+"`, while the five phases
    below it — and each lap's own gap — went through `fmtLoss`, which prints
    a loss as `"−"`. `gain_avg_s` is always positive (it IS a loss, averaged),
    so every full screen showed a `+` total over five `−` rows: adding the
    five by hand gave the total's exact opposite. One call, one convention."""
    block = _recap_render_body()
    assert "fmtLoss(r.gain_avg_s)" in block
    assert '"+" + r.gain_avg_s' not in block


def test_the_empty_recap_names_only_the_cause_it_can_verify():
    """`_recap_of` (api.py) returns `None` for seven different reasons — "one
    valid lap" is only one of them. `!cur` is a different fact altogether (no
    session at all, or the fetch failed): naming the single-lap cause there
    would often be naming the wrong one, which is worse than a generic
    message.

    Exactly one of the seven is measured rather than guessed, and so may be
    named: `recap_clock_broken`, decided by the guard in `trends.py` and
    forwarded through the payload. Every other case still lands on the generic
    sentence — that is the Task 4 correction, and this keeps it closed.
    """
    block = _recap_render_body()
    assert '!cur ? t("recap.nolaps")' in block
    assert 'cur.recap_clock_broken ? t("recap.clock") : t("recap.none")' in block
    # Un solo modo di far comparire la frase specifica. Se ne avesse due, uno
    # dei due sarebbe una causa affermata senza averla misurata.
    assert block.count('"recap.clock"') == 1
    # E il criterio non si rifà qui: la soglia vive in trends.py, dove è stata
    # misurata. Una copia nel frontend è la seconda definizione che un giorno
    # dirà il contrario della prima.
    assert "250" not in block


def test_the_empty_recap_is_muted_not_green():
    """`.clean` is `var(--green)` — this report's colour for "no problem
    here". A run with nothing measurable is not that; it's the project's own
    `.nothing` (muted), the same class the Session panel uses for "no laps"
    on this exact payload."""
    block = _recap_render_body()
    assert "clean" not in block
    assert '"nothing"' in block


def test_the_lap_by_lap_heading_hides_with_its_own_empty_list():
    """A heading left on screen over an empty div reads as broken (see the
    `.nothing` CSS comment: a panel that goes silent under its own title).
    The whole section has to go, not just the list inside it."""
    assert 'id="recap-laps-sec"' in _HTML
    block = _recap_render_body()
    assert 'lpSec.classList.add("hidden")' in block
    assert 'lpSec.classList.remove("hidden")' in block


def test_the_where_heading_keeps_its_promise_out_of_the_static_markup():
    """«Dove è finito il tempo» resta sempre a schermo, anche quando non c'è
    niente da misurare: è l'unica sezione di `#view-recap` con del contenuto
    statico, e la visita guidata ci punta sopra il suo «Parti da qui». Quindi
    la **promessa** — media per giro, le parti che sommano al numero sopra —
    non può stare nel titolo statico: sopra un'uscita senza recap non c'è
    nessun numero (`#recap-head` resta vuoto e `.summary:empty` lo toglie) e
    sotto non c'è nessuna parte. Vive in un `<small>` che il JS riempie.

    Verificato per mutazione: rimetti il `<small>(...)</small>` dentro
    `recap.where` e questo diventa rosso."""
    where = _i18n_between('"recap.where"', '"recap.wherenote"')
    for promise in ("add up", "sommano", "average per lap", "media per giro"):
        assert promise not in where, f"la promessa è tornata nel titolo statico: {promise}"
    sec = re.search(r'<section id="recap-phases-sec".*?</section>', _HTML, re.S)
    assert sec, "#recap-phases-sec non è più una sezione in index.html"
    note = re.search(r'<small id="recap-where-note"[^>]*>(.*?)</small>',
                     sec.group(0), re.S)
    assert note, "manca il <small> che porta la promessa"
    assert not note.group(1).strip(), (
        "il <small> ha del testo scritto nel markup: sarebbe a schermo anche "
        "senza recap, che è esattamente il difetto"
    )


def test_the_where_heading_promises_only_when_there_is_a_recap():
    """Le due metà di `renderRecap`, una per volta. Nel ramo del vuoto il
    `<small>` va svuotato (non lasciato com'era: la scheda si ridisegna a ogni
    cambio di sessione, e la promessa della sessione prima resterebbe lì sopra
    il messaggio del vuoto); nel ramo pieno va riempito.

    Verificato per mutazione: sposta `t("recap.wherenote")` nel ramo del vuoto
    e diventa rosso; toglilo dal ramo pieno e diventa rosso."""
    block = _recap_render_body()
    empty, filled = block.split('if (lpSec) lpSec.classList.remove')
    assert 'note.textContent = ""' in empty
    assert '"recap.wherenote"' not in empty, (
        "la promessa è nel ramo dell'uscita non misurabile"
    )
    assert 't("recap.wherenote")' in filled


def test_render_recap_never_hides_the_tour_s_start_here_target():
    """La trappola già pagata una volta su questo ramo. `#recap-laps-sec` si
    nasconde quando la lista è vuota, e la tentazione è fare lo stesso con la
    sezione delle fasi. Ma `tour.js` su un bersaglio invisibile chiama
    `finish()`, non «salta»: nascondere la sezione a cui punta `tour.a12`
    chiuderebbe la visita guidata al terzo passo su dodici, in silenzio, su
    ogni uscita senza recap — e nell'archivio vero sono 6 sessioni su 17, una
    delle quali la prima combo che `/api/combos` restituisce.

    Il bersaglio non è scritto a mano qui: è letto da `tourSteps()`, così il
    test segue il passo se un giorno cambia elemento. Verificato per
    mutazione: aggiungi `$("recap-phases-sec").classList.add("hidden")` nel
    ramo del vuoto e diventa rosso."""
    steps = _APPJS.split("function tourSteps()")[1].split("\n}")[0]
    m = re.search(r'sel:\s*"#([^"]+)"[^}]*title:\s*t\("tour\.a12\.t"\)', steps)
    assert m, "no tour step uses tour.a12.t (\"Start here\")"
    target = m.group(1)
    assert target not in _recap_render_body(), (
        f"renderRecap tocca #{target}, il bersaglio di «Parti da qui»: se lo "
        "nasconde, la visita guidata finisce lì senza dirlo"
    )


def test_the_start_here_step_does_not_count_what_may_not_be_on_screen():
    """Il testo del passo diceva «cinque numeri che sommano al numero sopra di
    loro», e al primo avvio puntava su un pannello che quei numeri non li
    aveva. Un passo della visita può dire *cosa fa* la scheda; non può contare
    quello che c'è sopra, perché non lo sa."""
    x = _i18n_between('"tour.a12.x"', '"tab.session"')
    bad = re.search(r"\b(two|three|four|five|six|due|tre|quattro|cinque|sei)"
                    r"\s+(numbers|numeri)\b", x)
    assert not bad, f"il passo conta le parti a schermo: {bad.group(0) if bad else ''}"


def test_the_yardstick_key_is_actually_shown():
    """Declared in i18n.js and never read anywhere would be dead weight — or
    worse, a sign the screen forgot to say why the best lap has no gap of its
    own next to it."""
    assert 't("recap.yardstick")' in _APPJS


def test_the_recap_where_heading_does_not_promise_the_timing_screens_gap():
    """The spec is explicit: this number differs from the timing screen's own
    gap by up to a tenth, so the one word a driver would go check it against
    must never be the word used to describe it."""
    assert "gap" not in _i18n_between('"recap.where"', '"recap.laps"')


def test_the_tour_start_here_step_points_at_the_new_landing_tab():
    """The door moved from Flow to the recap; the "Start here" coachmark has
    to move with it, or a first-time driver's very first tour step points at
    a tab that is no longer where they landed."""
    block = _APPJS.split("function tourSteps()")[1].split("\n}")[0]
    m = re.search(r'sel:\s*"([^"]+)"[^}]*title:\s*t\("tour\.a12\.t"\)', block)
    assert m, "no tour step uses tour.a12.t (\"Start here\")"
    assert _view_of_ids().get(m.group(1).lstrip("#"), "") == "recap"


def test_the_tour_start_here_step_points_at_something_with_static_content():
    """`before: recap` calls `showView("recap")`, which calls `loadSession` —
    asynchronous. `tour.js`'s `render()` runs `before()` and, in the very same
    synchronous tick, checks `visible(elFor(step))`; anything still at
    `height: 0` at that instant fails the check and the whole tour calls
    `finish()` in silence. `#recap-phases` is exactly that: an empty `<div>`
    in index.html until `renderRecap` fills it after the fetch resolves, which
    can never happen before the synchronous check runs. The step has to
    target an element that already has content in the raw HTML — verified
    here by mutation: point tour.a12 back at `#recap-phases` and this goes
    red; restore `#recap-phases-sec` and it's green again."""
    block = _APPJS.split("function tourSteps()")[1].split("\n}")[0]
    m = re.search(r'sel:\s*"([^"]+)"[^}]*title:\s*t\("tour\.a12\.t"\)', block)
    assert m, "no tour step uses tour.a12.t (\"Start here\")"
    sel = m.group(1)
    assert sel.startswith("#"), sel
    target = sel[1:]
    tag = re.search(rf'<(\w+)[^>]*\bid="{re.escape(target)}"[^>]*>(.*?)</\1>',
                     _HTML, re.S)
    assert tag, f"{sel} is not a tag with a closing pair in index.html"
    inner = re.sub(r"\s+", "", tag.group(2))
    assert inner, (
        f"{sel} is empty in index.html — it is filled by JS after an async "
        "fetch, so tour.js's synchronous visibility check will always miss it"
    )


# --- la mappa entra nel Confronto, e la scheda Mappa sparisce (2026-08-07) ---
# Undici schede diventano dieci: i quattro grafici a sinistra, la mappa (con la
# sua legenda, il suo stato vuoto e la scheda frenate) a destra sullo stesso
# schermo. Erano due schede per la stessa domanda — «dove ho perso» in grafico e
# «dove ho perso» sul disegno — e si guardavano una per volta.

def test_the_map_lives_in_compare_now():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="view-map"' not in html
    assert 'data-view="map"' not in html
    # L'assenza da sola sarebbe verde anche su un file vuoto: la parte che porta
    # il carico è questa, che il contenuto trasferito esista ANCORA e stia sulla
    # vista giusta. `_view_of_ids` lavora per ordine nel documento.
    ids = _view_of_ids()
    for el in ("c-map", "map-readout", "map-missing", "brakesheet"):
        assert ids[el] == "compare", el
    # E che sia rimasto intero: la voce di legenda che compare solo sui giri
    # buttati è la prima che si perde in un taglia-e-incolla.
    assert ids["leg-lost"] == "compare"


# --- e le due colonne sono DAVVERO due colonne ------------------------------
# `_view_of_ids()` sa dire una cosa sola: «questo id sta dentro view-compare».
# Non sa niente dell'annidamento, quindi resta verde anche se la mappa finisce
# nella colonna dei grafici — e resta verde se le tre classi dello scaffale
# spariscono del tutto. Provato: togliendo `class="cmp-shell"`, `"cmp-charts"` e
# `"cmp-map"` da index.html la suite intera passava. Due guasti silenziosi: le
# colonne collassano una sotto l'altra, e la catena di stampa
# `#view-compare > .cmp-shell > .cmp-map > #brakesheet` non aggancia più niente,
# cioè il foglio esce BIANCO. Il CSS è pinnato dal testo di style.css; qui si
# pinna l'altra metà, la struttura che quel testo presuppone.

_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}


class _El:
    """Un elemento di index.html: tag, id, classi, figli DIRETTI."""

    def __init__(self, tag: str, attrs: dict):
        self.tag = tag
        self.id = attrs.get("id") or ""
        self.classes = set((attrs.get("class") or "").split())
        self.children: list["_El"] = []

    def cols(self, cls: str) -> list["_El"]:
        """I figli diretti con quella classe — «diretti» è il punto del test."""
        return [c for c in self.children if cls in c.classes]

    def find(self, el_id: str) -> "_El | None":
        """Il discendente con quell'id, a qualsiasi profondità."""
        for c in self.children:
            if c.id == el_id:
                return c
            hit = c.find(el_id)
            if hit is not None:
                return hit
        return None


def _dom() -> _El:
    from html.parser import HTMLParser

    root = _El("#document", {})

    class _Builder(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = [root]

        def handle_starttag(self, tag, attrs):
            el = _El(tag, dict(attrs))
            self.stack[-1].children.append(el)
            if tag not in _VOID_TAGS:
                self.stack.append(el)

        def handle_startendtag(self, tag, attrs):
            self.stack[-1].children.append(_El(tag, dict(attrs)))

        def handle_endtag(self, tag):
            # Chiude fino al tag omonimo più interno invece di fidarsi
            # dell'ordine: una chiusura spaiata sposterebbe tutto il resto del
            # documento di un livello, e il test mentirebbe sull'annidamento.
            for k in range(len(self.stack) - 1, 0, -1):
                if self.stack[k].tag == tag:
                    del self.stack[k:]
                    return

    p = _Builder()
    p.feed(_HTML)
    p.close()
    return root


def test_compare_is_a_shell_with_the_map_in_its_right_hand_column():
    """L'annidamento, non l'appartenenza: `.cmp-shell` figlio di `#view-compare`,
    e dentro di lui DUE colonne — i grafici a sinistra, la mappa a destra.

    È anche la catena su cui si regge la stampa: se una delle tre classi salta,
    `@media print` riaccende una discendenza che non esiste e il foglio frenate
    esce bianco, senza che niente protesti fino alla carta.
    """
    compare = _dom().find("view-compare")
    assert compare is not None, "index.html non ha più #view-compare"
    shells = compare.cols("cmp-shell")
    assert len(shells) == 1, "#view-compare deve avere un solo .cmp-shell, figlio diretto"
    shell = shells[0]

    charts, maps = shell.cols("cmp-charts"), shell.cols("cmp-map")
    assert len(charts) == 1, ".cmp-shell ha perso la colonna dei grafici"
    assert len(maps) == 1, ".cmp-shell ha perso la colonna della mappa"
    assert maps[0].tag == "aside", "la colonna della mappa è un <aside>"
    assert charts[0].find("charts") is not None, "#charts non è nella sua colonna"

    # E stanno nella colonna GIUSTA. Senza il negativo, la mappa potrebbe finire
    # in mezzo ai grafici e ogni asserzione qui sopra resterebbe verde.
    for el in ("map-readout", "c-map", "leg-lost", "map-missing", "brakesheet"):
        assert maps[0].find(el) is not None, f"{el} non è nella colonna della mappa"
        assert charts[0].find(el) is None, f"{el} è finito fra i grafici"


def test_the_rail_no_longer_lists_the_map():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    rail = js[js.index("RAIL_VIEWS"):js.index("\n", js.index("RAIL_VIEWS"))]
    assert '"map"' not in rail
    assert '"compare"' in rail


def test_no_javascript_branch_still_waits_for_a_map_view():
    """La vista non esiste più: un `VIEW === "map"` rimasto indietro è un ramo
    che non si esegue mai, e con lui la mappa che non si disegna o il messaggio
    di caricamento che non compare. Positivo accanto: il Confronto quei rami
    li ha davvero."""
    assert 'VIEW === "map"' not in _APPJS
    # Il positivo era `count(...) >= 2`, che con quattro rami veri non oppone
    # nessuna resistenza: sarebbe verde anche perdendone due. Ognuno dei tre
    # punti che la vista Mappa serviva va nominato per nome.
    for fn in ("function redrawCurrentView()", "async function loadCombo(",
               "function hoverTo("):
        body = _APPJS.split(fn)[1].split("\n}\n")[0]
        assert 'VIEW === "compare"' in body, fn


def _branch_of(fn: str, view: str) -> str:
    """Il corpo del ramo `VIEW === "<view>"` dentro `<fn>`, fino al ramo dopo.

    Ritagliato, non cercato in tutta la funzione: «`drawMap` compare da qualche
    parte in `redrawCurrentView`» era vero anche PRIMA di questo lavoro, sul
    ramo della vista Mappa — un test che non sa distinguere i due mondi è verde
    in entrambi. Il taglio verifica da sé che l'inizio venga prima della fine,
    altrimenti una fetta vuota renderebbe verde ogni `in` che la interroga.

    La fine è la graffa che CHIUDE il ramo, contata, non il prossimo
    `else if (`: il ramo del Confronto in `redrawCurrentView` è l'ultimo della
    catena, quindi il vecchio taglio arrivava a fine funzione e si portava
    dentro `drawRail()`/`drawRailList()`. `assert i < j` protegge dalla fetta
    vuota; non proteggeva da quella troppo larga, che è lo stesso difetto
    all'altro capo.
    """
    body = _APPJS.split(fn)[1].split("\n}\n")[0]
    i = body.index(f'VIEW === "{view}"')
    o = body.index("{", i)
    # Il ramo dev'essere un blocco: fra la condizione e la graffa non ci può
    # stare un'istruzione (`else if (VIEW === "x") faiQualcosa();`), altrimenti
    # la graffa trovata è di un ALTRO ramo e la fetta sarebbe di qualcun altro.
    assert ";" not in body[i:o], f"il ramo {view!r} di {fn} non è un blocco"
    depth, j = 0, None
    for k in range(o, len(body)):
        if body[k] == "{":
            depth += 1
        elif body[k] == "}":
            depth -= 1
            if depth == 0:
                j = k + 1
                break
    assert j is not None and i < j, f"fetta senza fine per il ramo {view!r} di {fn}"
    return body[i:j]


def test_opening_compare_draws_the_map_and_loads_the_braking_sheet():
    """Il disegno stava sul ramo della vista Mappa: senza portarlo qui, aprire
    il Confronto lascia la colonna destra bianca finché non si passa il mouse."""
    branch = _branch_of("function redrawCurrentView()", "compare")
    assert "redraw(LAST_HOVER)" in branch
    assert "drawMap(DATA, null)" in branch
    assert "loadBraking()" in branch
    # Che la fetta finisca dove finisce il ramo: `drawRail()` sta fuori da ogni
    # ramo, apposta (il rail non appartiene a nessuna vista). Se compare qui
    # dentro, il taglio ha inghiottito la coda della funzione e le tre
    # asserzioni sopra parlano di un pezzo di codice che non è questo ramo.
    assert "drawRail()" not in branch


def test_a_new_lap_draws_the_map_when_compare_is_open():
    block = _APPJS.split("async function loadCombo(")[1].split("\n}\n")[0]
    assert 'if (VIEW === "compare") {' in block
    assert "drawMap(a, null)" in block
    assert "loadBraking()" in block


def test_hovering_compare_moves_the_map_crosshair_too():
    """I grafici e la mappa sono ora sullo stesso schermo: un mirino che vive
    solo su metà schermata è peggio di nessun mirino."""
    branch = _branch_of("function hoverTo(", "compare")
    assert "redraw(p)" in branch
    assert "drawMap(DATA, p)" in branch


def test_compare_is_two_columns_that_can_actually_shrink():
    """`minmax(0, 1fr)` non è ornamentale: senza lo `0` la colonna dei grafici
    non può scendere sotto la larghezza minima di un canvas, e la pagina scorre
    di lato. Questa pagina ha già spedito 39 px di scroll orizzontale."""
    shell = _rule(".cmp-shell {")
    assert "grid" in shell
    assert "minmax(0, 1fr)" in shell, shell
    # La mappa ferma mentre scorri i grafici è tutto il senso della cosa.
    assert "sticky" in _rule(".cmp-map {")


def _media_blocks(query: str) -> list[str]:
    """I corpi di ogni `@media <query>` dello stylesheet da SCHERMO, delimitati
    contando le graffe.

    Uno `split()` sulla stringa `@media (…)` non delimita niente: ogni fetta
    arriva a fine file, quindi «i blocchi che nominano `.cmp-shell`» erano uno
    solo per caso — perché `_screen_css()` toglie prima il blocco `@media print`,
    che quella classe la nomina tre volte. Bastava una menzione qualsiasi sotto
    l'ultimo `@media` per far fallire il test per un motivo che non c'entra.
    """
    css, out = _screen_css(), []
    for m in re.finditer(re.escape(f"@media {query}") + r"\s*\{", css):
        depth, start = 0, m.end() - 1
        for k in range(start, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    out.append(css[start + 1:k])
                    break
    return out


def test_narrow_screens_stack_the_columns_with_the_map_on_top():
    """A schermo stretto due colonne da 320 px non ci stanno. Impilate, la mappa
    va SOPRA: è l'orientamento, e si legge prima del dettaglio."""
    # Il blocco che parla dello scaffale, non «il primo @media a 900px»: ce n'è
    # già un altro nel file (la curva ingrandita), e prendere quello darebbe una
    # fetta che non contiene niente di ciò che si cerca — verde per il motivo
    # sbagliato o rosso per il motivo sbagliato, mai per quello giusto.
    blocks = [b for b in _media_blocks("(max-width: 900px)") if ".cmp-shell" in b]
    assert len(blocks) == 1, "un solo @media a 900px deve impilare lo scaffale"
    block = blocks[0]
    assert "grid-template-columns: 1fr" in block
    assert "order: -1" in block
    assert "position: static" in block


def test_the_braking_sheet_scrolls_inside_its_column():
    """La scheda è una tabella larga; in una colonna da 320 px la sua larghezza
    minima spingerebbe la PAGINA di lato invece di scorrere da sola."""
    assert "overflow-x: auto" in _rule(".cmp-map #brakesheet")


def test_the_shortcut_row_is_exactly_as_long_as_the_tabs():
    """Il vincolo storico (`tabs <= len(KEY_ROW)`) copre solo il verso in cui si
    aggiunge una scheda. Togliendone una, la riga resta più lunga e l'ultimo
    carattere diventa un tasto che il pilota preme e che non fa NIENTE, in
    silenzio: `wireKeys` fa `if (b)` e non protesta. È lo stesso «comando che
    non risponde» per cui il rail non vive sulle schede senza giro. Con undici
    schede la riga finiva in "-"; con dieci finisce in "0"."""
    tabs = len(re.findall(r'class="tab[ "]', _HTML))
    m = re.search(r'const KEY_ROW = "([^"]+)"', _APPJS)
    assert m, "wireKeys()/wireTabs() lost their shared KEY_ROW constant"
    assert tabs == len(m.group(1)), \
        f"{tabs} schede contro {len(m.group(1))} tasti ({m.group(1)!r})"


def test_the_map_tab_label_is_not_left_orphaned_in_the_catalogue():
    """La scheda non c'è più: la sua etichetta non deve restare a catalogo in
    nessuna delle due lingue. Positivo accanto: le chiavi del contenuto
    trasferito devono invece esserci ancora, in entrambe."""
    assert '"tab.map"' not in _I18NJS
    for key in ("map.readout", "map.missing", "map.leg.lost", "map.grad.note"):
        entry = _I18NJS[_I18NJS.index(f'"{key}"'):]
        entry = entry[:entry.index("},")]
        assert "en:" in entry and "it:" in entry, key


# --- il gemello mancante: chi SPEGNE quel che il JS accende (2026-08-07) ------
#
# `test_no_rule_at_all_can_outrank_the_hidden_class` copre un verso solo: una
# regola che lascia a schermo qualcosa che deve sparire. Il verso opposto è
# costato tre messaggi muti — `#map-missing`, `#line-missing` e `#dyn-missing`
# portavano `class="empty hidden"`, e `.empty { display: none }` li teneva
# spenti anche dopo che il JS toglieva `hidden`. Il difetto è sopravvissuto
# perché nessun test legava la classe scritta nel markup alla regola scritta nel
# foglio: due file che si contraddicevano in silenzio, ognuno coerente con sé.


def _compound(part: str) -> set[str] | None:
    """Un pezzo di selettore (`aside.cmp-map`, `#c-map`) ridotto ai suoi nomi.

    `None` se non è un compound semplice: pseudo-classi, attributi e `*` sono
    condizionali o troppo larghi per essere decisi leggendo un file fermo.
    """
    if not re.fullmatch(r"(?:[a-zA-Z][\w-]*)?(?:[.#][\w-]+)*", part) or not part:
        return None
    return set(re.findall(r"[.#]?([\w-]+)", part))


def _hits(selector: str, chain: list[set[str]]) -> bool:
    """Vero se `selector` colpisce l'ultimo anello di `chain` (l'elemento) con i
    suoi antenati, dal più esterno al più interno.

    Solo la discendenza: un selettore con `>`, `+` o `~` viene lasciato stare
    (dichiarato in fondo al test) perché la posizione fra fratelli non si legge
    da qui.
    """
    if any(c in selector for c in ">+~") or not selector.strip():
        return False
    parts = selector.split()
    compounds = [_compound(p) for p in parts]
    if any(c is None for c in compounds):
        return False
    if not compounds[-1] <= chain[-1]:
        return False
    todo = list(compounds[:-1])
    for names in chain[:-1]:
        if todo and todo[0] <= names:
            todo.pop(0)
    return not todo


def _hideable_chains() -> list[tuple[str, list[set[str]]]]:
    """Ogni elemento che NASCE con `hidden` — cioè che qualcuno accende e spegne
    a mano — con la catena dei suoi antenati, ognuno ridotto a tag, id e classi.

    `hidden` è tolta da ogni insieme di proposito: la domanda non è se
    `.hidden { display: none }` lo spegne (è il suo mestiere), ma se lo spegne
    **qualcos'altro**, che nessun `classList.remove` potrà mai riaccendere.
    """
    out: list[tuple[str, list[set[str]]]] = []

    def walk(el, chain: list[set[str]]) -> None:
        names = {el.tag} | set(el.classes) | ({el.id} if el.id else set())
        names.discard("hidden")
        here = chain + [names]
        if "hidden" in el.classes:
            out.append((el.id or el.tag, here))
        for child in el.children:
            walk(child, here)

    for child in _dom().children:
        walk(child, [])
    return out


def test_nothing_switches_off_what_the_javascript_switches_on():
    """Togliere `hidden` deve bastare a far comparire un elemento.

    Il caso vero: la scatola della mappa su un giro senza coordinate mostrava il
    titolo, nascondeva la tela e **non diceva niente** — 68 px di scatola vuota.
    `drawMapTo` faceva la cosa giusta (`missing.classList.remove("hidden")`), ma
    il messaggio portava anche `.empty`, che è lo stato vuoto di TUTTA la pagina
    e vive a `display: none` finché non arriva `body.no-data`. Toglierne `hidden`
    non lo accendeva: restava spento per costruzione, e con lui gli altri due.
    Il vincolo del progetto è «assente, non un trattino»: dove un dato non c'è,
    la schermata scrive perché — e uno spazio muto è peggio del trattino.

    Nota su `body.no-data`: la classe di stato non è nel markup, quindi una
    regola che la nomina non colpisce il documento a riposo e non finisce qui.
    È giusto così — quelle regole descrivono un altro momento della pagina.
    """
    chains = _hideable_chains()
    found = {name for name, _ in chains}
    # Anti-vacuità: se il parser smette di trovare gli elementi, il ciclo qui
    # sotto gira a vuoto e il test diventa una decorazione.
    assert {"map-missing", "line-missing", "dyn-missing"} <= found, sorted(found)
    assert len(chains) >= 10, f"solo {len(chains)} elementi accendibili: parser?"

    # Anti-vacuità sul matcher: deve saper dire di sì a una classe che c'è e di
    # no a una che non c'è. Senza questo, un `_hits` sempre falso passerebbe.
    mapmiss = next(c for name, c in chains if name == "map-missing")
    assert _hits(".missing", mapmiss), "il matcher non riconosce nemmeno la classe giusta"
    assert not _hits(".empty", mapmiss), \
        "i tre messaggi per-vista sono tornati sotto `.empty`, che è lo stato vuoto della pagina"

    seen = 0
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", _screen_css()):
        decl = re.search(r"display\s*:\s*([\w-]+)", m.group(2))
        if decl is None or decl.group(1) != "none":
            continue
        seen += 1
        for part in m.group(1).split(","):
            for name, chain in chains:
                assert not _hits(part.strip(), chain), (
                    f"{part.strip()!r} spegne #{name}, che il JS accende togliendo "
                    "`hidden`: dagli una classe sua invece di una condivisa")
    assert seen >= 5, f"solo {seen} regole `display: none` esaminate: taglio rotto?"


def test_the_three_per_view_messages_are_not_the_page_wide_empty_state():
    """L'altra metà, detta in positivo e senza passare dal CSS: i tre messaggi
    portano una classe che il foglio non spegne, e lo stato vuoto della pagina
    (`#empty`, l'unico che `body.no-data` deve accendere) resta il solo `.empty`
    accendibile. La trappola da evitare era una regola che, aggiustando i tre,
    accendesse anche quello fuori dal suo caso.
    """
    for el in ("map-missing", "line-missing", "dyn-missing"):
        node = _dom().find(el)
        assert node is not None, el
        assert "missing" in node.classes, f"#{el} ha perso la sua classe"
        assert "empty" not in node.classes, f"#{el} è tornato sullo stato vuoto globale"
        assert "hidden" in node.classes, f"#{el} deve nascere spento"

    # `.empty` resta di uno solo — `#empty`, che non nasce `hidden` — così
    # `body.no-data .empty` non può accendere niente che qualcun altro voleva
    # spento. È la trappola opposta, e vale la pena pinnarla qui accanto.
    owners = [g for g in re.findall(r'class="([^"]*)"', _HTML) if "empty" in g.split()]
    assert len(owners) == 1, owners
    assert "hidden" not in _dom().find("empty").classes

    # E la classe nuova non deve portarsi dietro un `display` di default: il suo
    # unico stato a riposo è quello che le dà `hidden`.
    assert "display" not in _rule(".missing"), _rule(".missing")


def test_a_new_lap_drops_the_old_lap_s_missing_messages_before_it_fetches():
    """Il gemello simmetrico, e si vede solo ora che i messaggi si vedono.

    «Questo giro non ha coordinate» parla del giro che sta per essere
    sostituito. Se resta acceso mentre la richiesta è in volo, la Traiettoria
    dice per un secondo e mezzo che il giro non ha coordinate SOPRA la
    traiettoria del giro che ce le ha: una frase falsa sopra un disegno giusto.
    Misurato nel browser passando da `bmw_m4_gt3_acc · imola` a
    `mclaren_720s_gt3_evo · monza`. Finché i tre portavano `.empty` erano
    invisibili in ogni caso e il difetto non poteva mostrarsi.

    «Prima della richiesta» è metà del test: spegnerli dopo l'`await` lascerebbe
    la frase falsa esattamente per la finestra che conta.
    """
    body = _APPJS[_APPJS.index("async function loadCombo("):]
    body = body[:body.index("\n}")]
    head = body[:body.index("await getJSON(")]
    assert "await getJSON(" in body, "loadCombo non fa più la sua richiesta: taglio rotto?"
    for el in ("map-missing", "line-missing", "dyn-missing"):
        assert el in head, f"{el} resta acceso durante la richiesta del giro nuovo"
    assert 'classList.add("hidden")' in head
