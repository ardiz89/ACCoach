"""Il registro dell'ingegnere arriva sullo schermo.

`/api/setup/record` esisteva, era testato, restituiva prove/tenute/riuscita/
guadagno mediano/effetti collaterali — e **non lo chiamava nessuno**. Zero
occorrenze in `engineer.js`. Il loop misurato è l'unica cosa che ci distingue da
un generatore di setup, e il pilota non lo vedeva.

È anche l'unico numero della pagina che può darci torto, il che è il punto.
"""
import re
from pathlib import Path

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
_JS = (_WEB / "engineer.js").read_text(encoding="utf-8")
_HTML = (_WEB / "engineer.html").read_text(encoding="utf-8")
_I18N = (_WEB / "i18n.js").read_text(encoding="utf-8")


def test_the_page_actually_asks_for_the_record():
    """Il difetto, in una riga: l'endpoint c'era e nessuno lo chiamava."""
    assert "/api/setup/record" in _JS


def test_it_is_asked_for_the_car_and_track_on_screen():
    """Un registro globale mescolerebbe una GT3 a Monza con una Formula a Spa:
    l'endpoint filtra, e il client deve dirgli su cosa."""
    # Guardato su tutta la funzione, non sulla singola stringa: l'URL è spezzato
    # su due literal per stare negli 88 caratteri, e una regex che si ferma al
    # primo backtick vede solo metà chiamata.
    body = _JS[_JS.index("async function loadRecord"):]
    body = body[:body.index("\n}")]
    assert "car=" in body and "track=" in body


def test_the_panel_exists_and_starts_hidden():
    assert 'id="eng-record"' in _HTML
    assert re.search(r'id="eng-record"[^>]*hidden', _HTML)


def test_a_percentage_is_withheld_until_there_are_enough_tests():
    """«Un tasso di riuscita su tre campioni è rumore travestito da percentuale»
    — lo dice il modulo che lo calcola, e la pagina deve rispettarlo."""
    assert "REC_MIN_TESTS" in _JS
    n = int(re.search(r"REC_MIN_TESTS\s*=\s*(\d+)", _JS).group(1))
    assert n >= 5, "sotto i cinque campioni una percentuale non significa niente"
    assert re.search(r"r\.tests\s*>=\s*REC_MIN_TESTS", _JS), \
        "la soglia deve governare la percentuale, non solo esistere"


def test_the_counts_are_shown_even_when_the_percentage_is_not():
    """Nascondere tutto sotto soglia sarebbe la stessa opacità di prima. I
    conteggi si mostrano sempre: sono un fatto, non una stima."""
    assert '"rec.counts"' in _I18N and "{kept}" in _I18N and "{tests}" in _I18N
    assert '"rec.thin"' in _I18N, "e si dice perché la percentuale non c'è"


def test_an_empty_record_says_what_will_fill_it():
    """Sarà vuoto a lungo, ed è lo stato normale all'inizio: un pannello vuoto
    senza spiegazione è la stessa app rotta di sempre."""
    assert '"rec.none"' in _I18N


def test_the_failures_are_shown_too():
    """Il registro serve se può darci torto: le leve che non si guadagnano il
    posto e gli effetti collaterali mai predetti stanno lì apposta."""
    for key in ('"rec.byparam"', '"rec.byrank"', '"rec.side"'):
        assert key in _I18N
    assert "by_rank" in _JS and "side_effects" in _JS


def test_every_record_string_is_in_both_languages():
    for key in re.findall(r'"(rec\.[a-z_]+)"', _I18N):
        block = _I18N[_I18N.index(f'"{key}"'):][:600]
        assert "en:" in block and "it:" in block, key
