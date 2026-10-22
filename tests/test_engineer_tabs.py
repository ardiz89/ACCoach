"""La pagina Ingegnere a schede, sugli schermi stretti.

Il pilota il 21/10: sotto i 15 pollici diagnosi e assetto affiancati non ci
stanno; due schede, si cambia toccando il nome o scorrendo col dito, e si apre
sulla telemetria. Questi test tengono i contratti fra HTML, CSS e JS che una
rilettura non vede; la resa vera si e' guardata nel browser.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
HTML = (WEB / "engineer.html").read_text(encoding="utf-8")
CSS = (WEB / "engineer.css").read_text(encoding="utf-8")
JS = (WEB / "engineer.js").read_text(encoding="utf-8")


def test_the_page_opens_on_the_telemetry():
    assert '<html lang="en" data-tab="live">' in HTML
    assert '<body>' in HTML, "la demo cerca questo tag esatto per il suo avviso"
    live = re.search(r'<button[^>]*id="tab-live"[^>]*>', HTML).group(0)
    setup = re.search(r'<button[^>]*id="tab-setup"[^>]*>', HTML).group(0)
    assert 'aria-selected="true"' in live
    assert 'aria-selected="false"' in setup


def test_each_tab_names_a_pane_that_exists():
    for tab in re.findall(r'class="eng-tab"[^>]*data-tab="(\w+)"', HTML):
        pane = re.search(rf'aria-controls="(pane-{tab})"', HTML)
        assert pane and f'id="{pane.group(1)}"' in HTML, tab


def test_the_css_and_the_js_agree_on_where_tabs_start():
    """Il CSS decide quando le schede si vedono, il JS quando lo scorrimento le
    cambia: se le due soglie divergono, su una fascia di larghezze il dito
    cambierebbe una scheda che non si vede, o non cambierebbe quella che c'e'."""
    css = re.findall(r"@media \(max-width: (\d+)px\) \{\s*\.eng-tabs", CSS)
    js = re.findall(r'matchMedia\("\(max-width: (\d+)px\)"\)', JS)
    assert css and js and css[0] == js[0], (css, js)


def test_one_tab_at_a_time_and_the_tray_only_with_the_setup():
    for rule in ('html[data-tab="live"] .eng-setup',
                 'html[data-tab="setup"] .eng-live',
                 'html[data-tab="live"] .tray'):
        assert rule in CSS, rule


def test_preparing_a_change_brings_you_to_the_editor():
    """«Prepara la modifica» dalla diagnosi: l'editor e' nell'altra scheda.
    Senza il salto la modifica si preparerebbe dove non la vedi."""
    body = JS[JS.index("function prepareChange"):]
    body = body[:body.index("\n}\n")]
    assert 'setTab("setup")' in body


def test_the_swipe_leaves_the_editor_controls_alone():
    """I bottoni +/- si tengono premuti: un dito che ci scivola sopra non deve
    cambiare scheda."""
    swipe = JS[JS.index("function wireSwipe"):]
    assert ".slot" in swipe[:swipe.index("touchend")]


def test_the_trace_draws_throttle_brake_and_steering():
    draw = JS[JS.index("function traceDraw"):]
    draw = draw[:draw.index("\n}\n")]
    for colour in ('"--green"', '"--red"', '"--text"'):
        assert colour in draw, colour
    assert "s[3]" in draw, "la linea dello sterzo"


def test_the_legend_writes_numbers_and_the_side_like_the_rest_of_the_app():
    """«34 % a sinistra», non «◀ 34%»: la percentuale passa dal formattatore
    (spazio prima dell'unita') e la parte e' una parola del catalogo."""
    push = JS[JS.index("function tracePush"):]
    push = push[:push.index("\n}\n")]
    assert "fmtN(" in push
    assert 'tf("trace.steerLeft"' in push and 'tf("trace.steerRight"' in push
    assert not re.search(r"[◀▶]", push)
    cat = (WEB / "i18n.js").read_text(encoding="utf-8")
    for key in ("trace.steerLeft", "trace.steerRight"):
        entry = re.search(rf'"{re.escape(key)}":(.*)', cat)
        assert entry and entry.group(1).count("{v}") == 2, key


def test_the_guided_tour_reaches_the_setup_from_the_telemetry_tab():
    """Il giro guidato si apre sulla telemetria; sugli schermi stretti l'editor
    sta nell'altra scheda e, senza il salto, il passo dell'editor spariva."""
    steps = JS[JS.index("function tourSteps"):]
    steps = steps[:steps.index("\n}\n")]
    setup_step = re.search(r'\{ sel: "\.eng-setup".*\}', steps).group(0)
    assert "before: setup" in setup_step and 'setTab("setup")' in steps
    # #av-now spesso non c'e': un `before` li' chiuderebbe il giro.
    assert "before" not in re.search(r'\{ sel: "#av-now".*\}', steps).group(0)


def test_on_a_phone_the_setup_tab_does_not_widen_the_page():
    """A 420 px la scheda Setup allargava la pagina di 58 px: le colonne
    dell'editor volevano 430 px. Misurato nel browser prima e dopo."""
    body = re.search(r"\.setup-body \{[^}]*\}", CSS).group(0)
    assert "minmax(min(30.714rem, 100%)" in body
