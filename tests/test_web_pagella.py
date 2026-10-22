"""La Pagella nel report: la prima scheda, le schede in tre gruppi, il piano.

Statici sul markup e sul sorgente, come `test_web_views.py`: la pagina è un
file piatto senza toolchain, e un test che ha bisogno di un motore JS per
girare è un test che smette di girare. La prova vera (leggibilità a
1920×1080, «Lo seguo» che fa sparire gli altri bottoni) è nel browser.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "accoach" / "web"
_HTML = (WEB / "index.html").read_text(encoding="utf-8")
_APPJS = (WEB / "app.js").read_text(encoding="utf-8")
_I18NJS = (WEB / "i18n.js").read_text(encoding="utf-8")
_CSS = (WEB / "style.css").read_text(encoding="utf-8")


def _nav() -> str:
    m = re.search(r'<nav class="tabs">(.*?)</nav>', _HTML, re.S)
    assert m, "la barra delle schede non c'è più"
    return m.group(1)


def _body_of(head: str) -> str:
    """Il corpo di una funzione di primo livello di app.js, fino alla sua `}`."""
    assert head in _APPJS, f"manca {head!r} in app.js"
    return _APPJS.split(head, 1)[1].split("\n}", 1)[0]


def _i18n_entry(key: str) -> str:
    """La voce di catalogo intera. Non «fino al primo `},`»: un testo fra
    backtick può contenerlo («{first}, poi {rest}»)."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*\{{\s*en:\s*`[^`]*`,\s*it:\s*`[^`]*`\s*\}}',
                  _I18NJS)
    assert m, f"{key} non è nel catalogo con inglese e italiano"
    return m.group(0)


# --- le schede: tre gruppi, in quest'ordine (deciso col pilota) -------------

def test_the_tabs_follow_today_why_over_time_in_that_order():
    assert re.findall(r'data-view="([\w-]+)"', _nav()) == [
        "pagella", "session", "flow",
        "compare", "line", "sectors", "dynamics",
        "progress", "stint",
    ]


def test_the_three_groups_are_visible_in_the_bar_and_hold_their_tabs():
    groups = re.findall(
        r'<div class="tab-group"[^>]*data-i18n-label="(tabgroup\.\w+)"[^>]*>(.*?)</div>',
        _nav(), re.S)
    assert [(k, re.findall(r'data-view="([\w-]+)"', body)) for k, body in groups] == [
        ("tabgroup.today", ["pagella", "session", "flow"]),
        ("tabgroup.why", ["compare", "line", "sectors", "dynamics"]),
        ("tabgroup.time", ["progress", "stint"]),
    ]
    for key in ("tabgroup.today", "tabgroup.why", "tabgroup.time"):
        entry = _i18n_entry(key)
        assert "en:" in entry and "it:" in entry, key


def test_the_group_label_is_translated_and_drawn():
    """`data-i18n-label` è un attributo nuovo: senza il suo ramo in
    `applyStatic` l'etichetta resterebbe in inglese su una pagina italiana, e
    senza la regola CSS che la disegna non si vedrebbe affatto."""
    apply = _I18NJS.split("function applyStatic(")[1].split("\n  }\n")[0]
    assert "[data-i18n-label]" in apply
    assert 'setAttribute("data-label"' in apply
    assert "attr(data-label)" in _CSS


def test_the_report_opens_on_the_pagella():
    assert re.search(r'class="tab active"[^>]*data-view="pagella"', _HTML)
    assert 'let VIEW = "pagella"' in _APPJS
    assert '<div id="view-pagella">' in _HTML


def test_the_recap_and_training_views_are_gone():
    """Confluiscono nella Pagella (il recap) e fra il piano e il «Come si fa»
    (l'Allenamento). Restarci accanto vorrebbe dire due piani che possono
    dire cose diverse."""
    for gone in ('id="view-recap"', 'id="view-training"',
                 'data-view="recap"', 'data-view="training"'):
        assert gone not in _HTML, gone
    for fn in ("function renderRecap(", "function renderTraining(",
               "function loadTraining("):
        assert fn not in _APPJS, fn


def test_the_howto_view_exists_outside_the_bar():
    """Ci si arriva da «Come si fa →», non da una scheda (lo riempie il Task 8)."""
    assert 'id="view-howto"' in _HTML
    assert 'data-view="howto"' not in _HTML
    body = _body_of("function openHowto(defect, apex)")
    assert 'showView("howto")' in body
    assert "HOWTO_DEFECT = defect" in body


# --- dopo una sessione nuova si riapre sulla Pagella -------------------------

def test_a_new_session_opens_the_pagella_instead_of_the_last_tab():
    """Il report riapre l'ultima scheda vista; dopo una sessione nuova deve
    aprirsi sulla Pagella (spec, «Le schede del report»)."""
    body = _body_of("async function openPagellaIfNew(combo)")
    assert "seenSession(combo)" in body and "started_utc" in body
    assert "localStorage.getItem(seenKey(combo))" in _body_of("function seenSession(combo)")
    # Per auto e pista: un'altra combo non è una sessione nuova.
    assert 'const SEEN_KEY = "hone_seen_session"' in _APPJS
    assert 'SEEN_KEY + ":" + combo.car + "|" + combo.track' in _body_of("function seenKey(combo)")
    # Il confronto e, nel suo ramo, l'apertura della Pagella.
    branch = body.split("!== lastSeen")[1]
    assert 'showView("pagella")' in branch
    # E `init` la chiede prima di ripristinare la scheda salvata.
    init = _body_of("async function init()")
    assert init.index("openPagellaIfNew(CURRENT)") < init.index("savedView()")


def test_the_session_shown_at_the_top_is_marked_as_seen():
    body = _body_of("function renderPagella(p, index)")
    assert "localStorage.setItem(seenKey(CURRENT)" in body


# --- la Pagella segue il selettore di sessione ------------------------------

def test_the_pagella_follows_the_session_selector():
    load = _body_of("async function loadPagella(combo, index)")
    assert '"/api/pagella?"' in load
    assert "SESSION_I = want" in load
    assert "stale(seen) || SESSION_I !== want" in load
    redraw = _body_of("function redrawCurrentView()")
    assert 'VIEW === "pagella"' in redraw and "loadPagella(CURRENT, SESSION_I)" in redraw
    view = _body_of("function reloadViewData(combo)")
    assert "loadPagella(combo, SESSION_I)" in view


# --- excluded: una frase al posto dei blocchi -------------------------------

def test_an_excluded_session_shows_only_its_sentence():
    body = _body_of("function renderPagella(p, index)")
    excl, rest = body.split("if (p.excluded)", 1)[1].split("return;", 1)
    assert "p.verdict" in excl
    assert 'body.innerHTML = ""' in excl
    # I blocchi si disegnano solo dopo il ritorno.
    for block in ("pagDefects(", "pagWorst(", "pagErrors(", "pagPlan("):
        assert block not in excl and block in rest, block


# --- il piano: una regola sopra la lista, un consiglio alla volta -----------

def test_the_one_at_a_time_rule_is_said_once_above_the_list():
    it = _i18n_entry("pag.plan.rule")
    assert "Lavora su un consiglio alla volta, nell'ordine." in it
    assert _I18NJS.count("Lavora su un consiglio alla volta") == 1
    plan = _body_of("function pagPlan(advice, declined)")
    assert plan.count('t("pag.plan.rule")') == 1
    assert plan.index('t("pag.plan.rule")') < plan.index("<ol")
    # E non dentro il passo, che si ripete per ogni consiglio.
    assert "pag.plan.rule" not in _body_of("function pagStep(a, i, active, first)")


def test_only_the_right_advice_carries_the_buttons():
    step = _body_of("function pagStep(a, i, active, first)")
    act, rest = step.split('a.status === "active"', 1)[1].split("else if", 1)
    assert '"drop"' in act and '"follow"' not in act
    first = _body_of("function pagPlan(advice, declined)")
    # «Lo seguo» solo sul primo proposto, e solo se nessuno è in corso.
    assert '!active && a.status === "proposed"' in first
    assert '"follow"' in rest and '"decline"' in rest
    # «Come si fa →» su tutti, e passa da openHowto.
    assert "openHowto(" in _APPJS.split("function wirePagella(")[1].split("\n}")[0]


def test_the_advice_buttons_post_and_reload():
    body = _body_of("async function adviceAction(defect, action)")
    assert '"/api/advice"' in body and 'method: "POST"' in body
    assert "index: SESSION_I" in body
    assert "loadPagella(CURRENT, SESSION_I)" in body


# --- il mini-andamento: una barra fuori scala non schiaccia le altre --------

def test_the_spark_cuts_only_an_isolated_outlier():
    """Nell'archivio vero una sessione lentissima (22 647 ms contro 1 454 della
    seconda) appiattirebbe le altre. La barra tagliata si vede e porta il
    valore vero. Il comportamento lo prova `test_the_scale_on_the_real_series`."""
    body = _body_of("function sparkBars(vals, unit, trend, height)")
    assert "const top = second > 0 && max > 3 * second ? 1.2 * second : max;" in body
    # La barra sopra il taglio porta la classe che la segna, e il CSS la segna.
    assert "const cut = top > 0 && v > top;" in body
    assert '<i class="${cut ? "cut" : ""}' in body
    assert ".pag-spark i.cut::after" in _CSS
    # Il valore vero, anche della barra tagliata, sta nel suggerimento.
    assert 'title="${escAttr(tip)}"' in body
    assert 'tf("pag.spark.cut", { v: fmtSecs(v, unit) })' in body


# --- i numeri: la virgola in italiano, con l'unità --------------------------

def test_numbers_use_the_italian_comma():
    body = _body_of("function fmtDec(v, d, unit)")
    # La regola (virgola in italiano, mai «-0,00») sta in `HoneI18n.fmtNum`,
    # provata da `test_textfmt.py`; qui si controlla che le schede la chiamino.
    assert "fmtNum(v, d, unit)" in body and 'replace(".", ",")' not in body
    secs = _body_of("function fmtSecs(v, unit)")
    assert 'unit === "ms"' in secs and "/ 1000" in secs and 'fmtNum(s, 2, "s")' in secs


def test_the_pagella_reads_in_a_narrow_column_with_bigger_type():
    shell = _CSS[_CSS.index(".pag-shell {"):]
    shell = shell[:shell.index("}")]
    assert "max-width: 61.429rem" in shell
    assert "font-size: 1.143rem" in shell


def test_every_pagella_string_exists_in_both_languages():
    keys = set(re.findall(r'\bt\(\s*"(pag\.[\w.]+)"\s*\)', _APPJS))
    keys |= set(re.findall(r'\btf\(\s*"(pag\.[\w.]+)"', _APPJS))
    assert len(keys) >= 10, sorted(keys)
    for key in sorted(keys):
        entry = _i18n_entry(key)
        assert "en:" in entry and "it:" in entry, key


# --- compatta: verdetto, difetti e piano sullo schermo a 1920×1080 ---------

def test_the_lap_strip_is_hidden_on_the_pagella():
    """La fascia del giro (giro, confronto, distacco) parla di un giro, la
    Pagella di una sessione: lì costava ~45 px e spingeva il piano sotto il
    bordo dello schermo (misurato nel browser dal controllore)."""
    assert "body.view-pagella #lapbar { display: none; }" in _CSS
    rail = _body_of("function applyRailed(name)")
    assert 'classList.toggle("view-pagella", name === "pagella")' in rail
    # applyRailed è quella che gira a ogni cambio scheda e al primo paint.
    assert "applyRailed(name);" in _body_of("function showView(name)")
    assert "applyRailed(VIEW);" in _body_of("async function init()")


def test_the_secondary_boxes_are_compact():
    assert ".pag-grid .pag-row { padding: 3px 0;" in _CSS
    grid = _CSS[_CSS.index(".pag-grid {"):]
    assert "align-items: start" in grid[:grid.index("}")]


def test_the_spark_is_tall_enough_to_read():
    assert "const SPARK_H = 26;" in _APPJS
    assert "sparkBars(vals, unit, trend, SPARK_H)" in _body_of("function pagSpark(series, unit, trend)")
    assert "height * Math.min(v, top) / top" in \
        _body_of("function sparkBars(vals, unit, trend, height)")
    spark = _CSS[_CSS.index(".pag-spark {"):]
    assert "height: 26px" in spark[:spark.index("}")]


def test_the_picker_survives_a_failed_pagella():
    """Se la Pagella non arriva, dal selettore si sceglie un'altra uscita."""
    load = _body_of("async function loadPagella(combo, index)")
    failed = load.split("catch (e) {", 1)[1].split("\n  }\n", 1)[0]
    assert "fillPagellaPicker(list, want)" in failed


def test_the_plan_buttons_go_quiet_while_another_session_loads():
    load = _body_of("async function loadPagella(combo, index)")
    pre = load[:load.index("await ")]
    assert '#pag-body [data-action]")) b.disabled = true;' in pre


def test_the_summary_holds_only_inline_content():
    """<summary> non vuole blocchi: la riga del difetto è fatta di span."""
    body = _body_of("function pagDefects(defects)")
    line = body[body.index("const line ="):body.index("if (!corners.length)")]
    assert "<div" not in line and "<span class=\"pag-name\">" in line


# --- «Non lo seguo» si può disfare ------------------------------------------

def test_a_declined_advice_can_be_taken_back_from_under_the_plan():
    """Una riga sola, sotto il piano, con «Riprendi» per ogni difetto messo da
    parte: manda `undecline`, che il backend accetta solo su un rifiutato."""
    render = _body_of("function renderPagella(p, index)")
    assert "pagPlan(p.advice, p.declined)" in render
    plan = _body_of("function pagPlan(advice, declined)")
    # Anche quando il piano è vuoto: magari è vuoto proprio per quello.
    assert plan.count("pagDeclined(declined)") == 2
    body = _body_of("function pagDeclined(list)")
    assert 'data-action="undecline"' in body
    assert "escAttr(d.name)" in body and "escAttr(d.defect)" in body
    assert 't("pag.declined")' in body and 't("pag.undecline")' in body
    assert "Hai messo da parte" in _i18n_entry("pag.declined")
    assert "Riprendi" in _i18n_entry("pag.undecline")


# --- la vista «Come si fa» ---------------------------------------------------

def test_the_howto_view_reads_its_page_from_the_api():
    """`openHowto` resta il contratto del bottone (Task 7): ricorda il difetto,
    butta la vista di prima e apre la scheda. Il caricamento passa da
    `redrawCurrentView`, come per ogni scheda."""
    open_ = _body_of("function openHowto(defect, apex)")
    assert "HOWTO = null;" in open_
    assert open_.index("HOWTO = null;") < open_.index('showView("howto")')
    redraw = _body_of("function redrawCurrentView()")
    branch = redraw.split('VIEW === "howto"', 1)[1].split("else if", 2)
    branch = branch[0] + "else if" + branch[1]
    assert "drawHowtoFigures()" in branch and "loadHowto(CURRENT, SESSION_I)" in branch
    load = _body_of("async function loadHowto(combo, index)")
    assert '"/api/howto?"' in load
    assert "defect: HOWTO_DEFECT" in load and "index: want" in load


def test_the_howto_drops_answers_that_arrive_too_late():
    """La guardia di Task 7 più un contatore suo: due «Come si fa →» premuti
    di fila non si scrivono uno sopra l'altro."""
    load = _body_of("async function loadHowto(combo, index)")
    guard = "if (stale(seen) || SESSION_I !== want || req !== HOWTO_REQ) return;"
    # Dopo la pagina (nel ramo buono e nel `catch`) e dopo i giri delle figure.
    assert load.count(guard) == 3, load
    assert load.index("const req = ++HOWTO_REQ;") < load.index("await ")
    assert "/api/analysis?" in load
    # Le viste per car+track ripartono quando il contatore sale (lingua, combo).
    assert 'if (VIEW === "howto") loadHowto(combo, SESSION_I);' in \
        _body_of("function reloadViewData(combo)")


def test_the_howto_shows_its_parts_in_the_agreed_order():
    """Problema, figure, come si fa, esercizio, andamento, «← Torna alla
    Pagella» (spec e brief, nell'ordine)."""
    body = _body_of("function renderHowto(h)")
    order = ["howto-problem", "howto-figs", 't("howto.how")', 't("howto.drill")',
             't("howto.prog")', 'html += back("foot")']
    at = [body.index(x) for x in order]
    assert at == sorted(at), dict(zip(order, at))


def test_the_way_back_is_at_the_top_and_at_the_bottom():
    """Con tre figure il fondo è lontano: «← Torna alla Pagella» anche in alto,
    prima del titolo, con lo stesso gestore."""
    body = _body_of("function renderHowto(h)")
    assert 't("howto.back")' in body.split("let html =", 1)[0]
    assert body.index('let html = back("top")') < body.index("howto-title")
    assert 'html += back("foot");' in body
    assert ('for (const b of body.querySelectorAll(".howto-back")) '
            'b.onclick = () => showView("pagella");') in body


def test_the_drill_says_the_target_in_numbers():
    """«L'esercizio: quanti giri, obiettivo in numeri» (spec), nella forma del
    frase intera del tono nuovo («L'obiettivo è…», senza i due punti), su una riga sua, in secondi di veleggio per il
    veleggio."""
    body = _body_of("function renderHowto(h)")
    drill = body[body.index("const target ="):body.index('t("howto.prog")')]
    assert '<p class="howto-target">' in drill
    assert 'tf(h.unit === "s" ? "howto.target.coast" : "howto.target"' in drill
    assert "{ v: fmtSecs(h.target, h.unit) }" in drill
    assert "${target}" in drill
    assert "L'obiettivo è stare sotto {v} a giro." in _i18n_entry("howto.target")
    assert "L'obiettivo è veleggiare meno di {v} a giro." in _i18n_entry("howto.target.coast")
    assert "Aim for under {v} a lap." in _i18n_entry("howto.target")


def test_the_howto_says_which_lap_it_measures_against():
    body = _body_of("function renderHowto(h)")
    assert 'tf("howto.ref", { time: ref.lap_time, when: fmtWhen(ref.recorded_utc) })' in body
    assert "{time}" in _i18n_entry("howto.ref") and "{when}" in _i18n_entry("howto.ref")


def test_every_backend_string_is_escaped_in_the_howto():
    body = _body_of("function renderHowto(h)")
    for s in ("escAttr(h.name)", "escAttr(h.problem)", "escAttr(how.what)",
              "escAttr(how.drill)", "escAttr(how.done_when)", "escAttr(name)"):
        assert s in body, s
    # Nessun campo del backend scritto a crudo.
    assert not re.search(r"\$\{(?:h|how|f)\.\w+\}", body)


def test_the_howto_shows_the_glossary_from_the_backend():
    """Il glossario della vecchia scheda Allenamento: le voci arrivano dal
    backend (`glossary`), scritte con l'escape, dopo l'andamento e prima del
    ritorno in fondo. Senza voci la sezione non c'e'."""
    body = _body_of("function renderHowto(h)")
    assert "const gloss = h.glossary || [];" in body
    assert "if (gloss.length)" in body
    assert "<dt>${escAttr(g.term)}</dt><dd>${escAttr(g.definition)}</dd>" in body
    assert 't("howto.gloss")' in body
    assert body.index('t("howto.prog")') < body.index('t("howto.gloss")') \
        < body.index('html += back("foot")')
    assert "Glossario" in _i18n_entry("howto.gloss")
    assert re.search(r"\.howto-gloss dt\s*\{", _CSS)


def test_lift_and_coasting_say_why_there_is_no_figure():
    body = _body_of("function renderHowto(h)")
    nofig = body.split("if (!figs.length || !trace)", 1)[1].split("\n  }", 1)[0]
    # Con una traccia ma senza curve in questa sessione, una frase; alzate e
    # veleggio (nessuna traccia) l'altra, che dice che non stanno in una curva.
    # Un difetto che la tabella non conosce va per la seconda strada, e non
    # scrive mai «howto.tr.undefined».
    assert "const trace = HOWTO_TRACE[h.defect];" in body
    assert 't(trace ? "howto.nofig" : "howto.nofig.lap")' in nofig
    # Le alzate e il veleggio non hanno una traccia da curva: niente figura.
    assert re.search(r"const HOWTO_TRACE = \{[^}]*\}", _APPJS)
    table = re.search(r"const HOWTO_TRACE = \{([^}]*)\}", _APPJS).group(1)
    assert "lift" not in table and "coasting" not in table
    assert 'brake_early: "brake"' in table and 'min_speed: "speed"' in table
    assert 'throttle_late: "throttle"' in table


def test_a_figure_without_coordinates_or_channel_becomes_a_sentence():
    """Come `rail-nomap`: il disegno lascia il posto a una frase che dice perché."""
    fig = _body_of("function drawHowtoFigure(el, f, a, trace)")
    # La mappa: `drawMapTo` spegne la tela e accende la frase da sé.
    assert "drawMapTo(mapCv, mapNote, howtoMapSlice(a, win, f), null)" in fig
    assert 't("howto.nomap")' in fig
    # La traccia: il canale deve esserci in entrambi i giri.
    assert "!hasTrace(rv, trace) || !hasTrace(rf, trace)" in fig
    assert 'tf("howto.notrace"' in fig
    # Un giro che non si legge: la frase, non due tele vuote.
    assert 't("howto.nolap")' in fig
    # La tela spenta resta spenta: la regola che la accende non batte `.hidden`
    # (stesso duello di `.line-grid`, vedi test_web_views).
    assert ".howto-fig canvas:not(.hidden) { display: block;" in _CSS
    assert not re.search(r"\.howto-fig canvas\s*\{", _CSS)


def test_the_figures_reuse_the_compare_drawing_cut_to_the_corner():
    fig = _body_of("function drawHowtoFigure(el, f, a, trace)")
    assert "cornerWindow(" in fig
    assert re.search(r"line\(ctx, w, h, rf\.pos, rf\[trace\], lo, hi, [^)]*, win\)", fig)
    assert re.search(r"line\(ctx, w, h, rv\.pos, rv\[trace\], lo, hi, [^)]*, win\)", fig)
    # `line` proietta nella finestra data; senza, resta su `RANGE` come prima.
    line = _body_of("function line(ctx, w, h, pos, vals, lo, hi, color, lw, win)")
    assert "projX(pos[i], w, win)" in line
    # La mappa ritagliata non scrive «S/F» all'inizio della curva.
    sl = _body_of("function howtoMapSlice(a, win, f)")
    assert "window: true" in sl
    dm = _body_of("function drawMapTo(canvas, missing, a, cx, mode)")
    assert "// start/finish dot + label\n  if (!a.window) {" in dm


def test_the_lap_strip_is_hidden_on_the_howto_too():
    assert "body.view-howto #lapbar { display: none; }" in _CSS
    rail = _body_of("function applyRailed(name)")
    assert 'classList.toggle("view-howto", name === "howto")' in rail


def test_every_howto_string_exists_in_both_languages():
    keys = set(re.findall(r'\bt\(\s*"(howto\.[\w.]+)"\s*\)', _APPJS))
    keys |= {"load.howto", "err.howto", "howto.nofig", "howto.nofig.lap"}
    keys |= set(re.findall(r'\btf\(\s*"(howto\.[\w.]+)"', _APPJS))
    keys |= {"howto.ch." + c for c in ("brake", "throttle", "speed")}
    keys |= {"howto.tr." + c for c in ("brake", "throttle", "speed")}
    assert len(keys) >= 15, sorted(keys)
    for key in sorted(keys):
        entry = _i18n_entry(key)
        assert "en:" in entry and "it:" in entry, key
    assert "Torna alla Pagella" in _i18n_entry("howto.back")


# --- Andamento: i difetti sessione per sessione (Task 11) -------------------

def test_the_defect_history_sits_on_top_of_the_progress_view():
    # Dopo la riga del consiglio (spenta, senza spazio): la storia resta il
    # primo contenuto della scheda.
    assert re.search(r'<div id="view-progress" class="hidden">\s*'
                     r'(?:<div id="adv-line-progress"[^>]*></div>\s*)?'
                     r'<section id="defect-history"', _HTML)
    # E la sua parte riempita dal JS ha un posto suo.
    sec = _HTML.split('<section id="defect-history"', 1)[1].split("</section>", 1)[0]
    assert 'id="dh-body"' in sec and 'id="dh-ref"' in sec
    assert 'data-i18n="dh.title"' in sec


def test_the_defect_history_reads_its_own_endpoint_with_the_progress_view():
    load = _body_of("async function loadDefectHistory(combo)")
    assert '"/api/defect-history?"' in load and "lang: LANG()" in load
    assert "renderDefectHistory(h)" in load
    # Riparte con la scheda quando cambiano combo o lingua.
    assert "loadProgress(combo); loadDefectHistory(combo);" in \
        _body_of("function reloadViewData(combo)")


def test_a_resize_repaints_the_history_and_opening_the_tab_reads_it_again():
    """Il resize passa da `redrawCurrentView`: venti sessioni rilette a ogni
    trascinamento della finestra sarebbero secondi di attesa. Ma aprire la
    scheda rilegge: nel frattempo può essere arrivata una sessione."""
    redraw = _body_of("function redrawCurrentView()")
    assert "DEFHIST ? renderDefectHistory(DEFHIST) : loadDefectHistory(CURRENT);" in redraw
    show = _body_of("function showView(name)")
    assert show.index('if (name === "progress") DEFHIST = null;') < \
        show.index("redrawCurrentView();")
    load = _body_of("async function loadDefectHistory(combo)")
    # Buttata prima dell'attesa (un resize durante il caricamento non ridisegna
    # la combo di prima), salvata solo dopo la guardia.
    assert load.index("DEFHIST = null;") < load.index("await ")
    assert load.index("if (stale(seen)) return;\n  DEFHIST = h;") > load.index("await ")


def test_the_history_bars_are_the_pagella_bars():
    """Stessa scala, stesso segno di taglio: una funzione sola per le due viste."""
    assert "sparkBars(vals, unit, trend, SPARK_H)" in _body_of(
        "function pagSpark(series, unit, trend)")
    render = _body_of("function renderDefectHistory(h)")
    assert "sparkBars(vals, d.unit, trend, DH_H)" in render
    assert 'class="pag-spark dh-bars"' in render
    dh_h = re.search(r'const DH_H = (\d+);', _APPJS).group(1)
    assert f"height: {dh_h}px" in _CSS[_CSS.index(".dh-bars {"):].split("}", 1)[0]


def test_the_history_row_opens_the_howto_and_escapes_the_backend():
    render = _body_of("function renderDefectHistory(h)")
    assert 'data-howto="${escAttr(d.key)}"' in render
    assert "openHowto(b.dataset.howto)" in render
    assert "escAttr(d.name)" in render
    assert not re.search(r"\$\{(?:h|d|s|r)\.\w+\}", render)
    # L'ultimo valore e la freccia, le date sotto le barre.
    assert "fmtSecs(last, d.unit)" in render
    assert "dh-dates" in render and "dhDates(h.sessions || [])" in render


def test_a_defect_no_longer_main_is_not_marked_in_red():
    render = _body_of("function renderDefectHistory(h)")
    assert 'const tone = d.main ? "loss" : "ok";' in render
    assert '<span class="num ${tone}">${fmtSecs(last, d.unit)}' in render
    assert ".dh .num.ok { color: var(--green); }" in _CSS


def test_two_sessions_on_the_same_day_show_their_time():
    body = _body_of("function dhDates(sessions)")
    assert "count[day(iso)] > 1" in body
    assert 'toLocaleTimeString(LANG(), { hour: "2-digit", minute: "2-digit" })' in body
    # E la data intera, con l'ora, nel suggerimento di ogni colonna.
    assert "fmtWhen(iso)" in body and 'title="${escAttr(tip)}"' in body


def test_the_history_says_when_it_skipped_a_session_or_has_only_one():
    render = _body_of("function renderDefectHistory(h)")
    assert 'if (h.skipped === "wet" || h.skipped === "dry") notes.push(t("dh.skipped." + h.skipped));' \
        in render
    assert 'if ((h.sessions || []).length < 2) notes.push(t("dh.first"));' in render
    assert '$("dh-note").textContent = notes.join(" ");' in render
    sec = _HTML.split('<section id="defect-history"', 1)[1].split("</section>", 1)[0]
    assert sec.index('id="dh-note"') < sec.index('id="dh-body"')


def test_the_history_says_why_it_is_empty():
    render = _body_of("function renderDefectHistory(h)")
    assert 'h.excluded === "no_laps"' in render
    for key in ("dh.nolaps", "dh.noref", "dh.none"):
        assert f'"{key}"' in render, key


def test_every_history_string_exists_in_both_languages():
    keys = set(re.findall(r'\bt\(\s*"(dh\.[\w.]+)"\s*\)', _APPJS))
    keys |= set(re.findall(r'\btf\(\s*"(dh\.[\w.]+)"', _APPJS))
    keys |= {"dh.title", "dh.nolaps", "dh.noref", "load.dh", "err.dh",
             "dh.skipped.wet", "dh.skipped.dry", "dh.first"}
    assert len(keys) >= 8, sorted(keys)
    for key in sorted(keys):
        entry = _i18n_entry(key)
        assert "en:" in entry and "it:" in entry, key


# --- la scala, eseguita: sparkBars in node sulle serie vere di Monza --------

_NODE = shutil.which("node")

_SPARK_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name) {
  const i = src.indexOf("function " + name + "(");
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
const escAttr = (s) => String(s);
const fmtSecs = (v) => String(v);
const tf = (k, o) => k + ":" + o.v;
eval(grab("sparkBars"));
const out = [];
for (const vals of JSON.parse(fs.readFileSync(0, "utf8"))) {
  const html = sparkBars(vals, "ms", "", 100);
  out.push([...html.matchAll(/<i class="([^"]*)" style="height:(\d+)px"/g)]
           .map((m) => [m[1].trim(), Number(m[2])]));
}
console.log(JSON.stringify(out));
"""

# «Gas tardi in uscita» a Monza: la storia (10 sessioni) e il mini-andamento
# della Pagella (le ultime 6).
_MONZA_10 = [4089.8, 7960.1, 35507.5, 11209.5, 1453.6, 22647.0, 855.0, 872.7, 445.7, 627.1]
_MONZA_6 = [1453.6, 22647.0, 855.0, 872.7, 445.7, 627.1]


def _bars(tmp_path, *series):
    script = tmp_path / "spark.js"
    script.write_text(_SPARK_HARNESS, encoding="utf-8")
    run = subprocess.run([_NODE, str(script), str(WEB / "app.js")],
                         input=json.dumps(series), capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")
def test_the_scale_on_the_real_series(tmp_path):
    ten, six, flat, zeros = _bars(tmp_path, _MONZA_10, _MONZA_6,
                                  [0.0, 0.0, 500.0], [0.0, 0.0])
    # Dieci sessioni: la piu' alta e' 1,6 volte la seconda, non un fuori scala
    # isolato. Niente taglio, e il calo dalle prime sessioni alle ultime si vede.
    assert [c for c, _ in ten] == [""] * 10
    assert ten[2][1] == 100 and ten[0][1] == round(100 * 4089.8 / 35507.5)
    # Sei sessioni: 22 647 contro 1 453,6 della seconda. Tagliata solo quella,
    # e la scala e' la seconda x 1,2.
    assert [c for c, _ in six] == ["", "cut", "", "", "", ""]
    assert six[1][1] == 100
    assert six[0][1] == round(100 * 1453.6 / (1.2 * 1453.6))
    assert six[2][1] == round(100 * 855.0 / (1.2 * 1453.6))
    # La seconda a zero non fa una scala a zero.
    assert [c for c, _ in flat] == ["", "", ""] and flat[2][1] == 100
    assert [h for _, h in zeros] == [2, 2]


# --- l'hub chiede una Pagella precisa: ?view=pagella&car=…&track=… ----------

def _asked_branch() -> str:
    """Il tratto di `init` che legge i parametri, fino a `savedCombo()`."""
    init = _body_of("async function init()")
    return init.split("new URLSearchParams(location.search)")[1].split("savedCombo()")[0]


def test_init_reads_the_page_the_hub_asked_for():
    init = _body_of("async function init()")
    assert "new URLSearchParams(location.search)" in init
    branch = _asked_branch()
    for param in ('"view"', '"car"', '"track"'):
        assert param in branch
    # Senza maiuscole, come `sameName` di engineer.js; mai un confronto secco.
    assert 'low(c.car) === low(qs.get("car"))' in branch
    assert 'low(c.track) === low(qs.get("track"))' in branch
    # La combo chiesta diventa quella ricordata.
    assert "localStorage.setItem(_COMBO_KEY, asked.value)" in branch
    # E i parametri spariscono dall'indirizzo: un ricarica non li riapplica.
    assert "history.replaceState(" in branch


def test_the_asked_combo_wins_over_the_remembered_one():
    init = _body_of("async function init()")
    assert "const combo = asked ? null : savedCombo();" in init


def test_the_asked_pagella_opens_before_the_saved_view_is_restored():
    init = _body_of("async function init()")
    assert init.index("openAskedPagella(CURRENT)") < init.index("openPagellaIfNew(CURRENT)")
    assert init.index("openAskedPagella(CURRENT)") < init.index("savedView()")
    body = _body_of("async function openAskedPagella(combo)")
    assert 'showView("pagella")' in body
    assert "SESSION_I = 0" in body
    # L'uscita più recente della combo risulta vista.
    assert "localStorage.setItem(seenKey(combo), started)" in body
    assert "index: 0" in body


def test_an_unknown_combo_leaves_today_s_behaviour():
    """Nessuna combo trovata: `asked` resta null, quindi si salta il ramo e
    si va per `savedCombo`/`openPagellaIfNew`/`savedView` di sempre."""
    init = _body_of("async function init()")
    assert "let asked = null;" in init
    assert "if (asked) {\n    await openAskedPagella(CURRENT);\n  } else if (!(await openPagellaIfNew(CURRENT)))" in init


def test_every_failed_load_ends_with_the_shared_backend_sentence():
    """Un caricamento fallito dice cosa non è arrivato e poi la frase comune
    `err.backend`, una chiave sola (prima era la stessa domanda in quattro
    chiavi). Nessun percorso d'errore deve mostrare la prima frase da sola."""
    body = _body_of("function loadFailed(key)")
    assert 't(key)' in body and 't("err.backend")' in body
    for key in ("err.pagella", "err.dh", "err.howto", "err.progress"):
        assert f'loadFailed("{key}")' in _APPJS, key
        assert f't("{key}")' not in _APPJS, key
    entry = _i18n_entry("err.backend")
    assert "en:" in entry and "it:" in entry
