"""/api/progress: la mediana per sessione, per le curve su cui stai lavorando."""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _lap(tmp_path, when, *, amt=0, corner=0):
    lap = synth.build_lap(slow_corner=corner, amt=amt) if amt else synth.build_lap()
    lap.recorded_utc = when
    save_lap(lap, tmp_path)


def _session(tmp_path, day, laps):
    """Una sera: `laps` è la lista `(curva, amt)` di ogni giro, a 2 minuti l'uno."""
    for i, (corner, amt) in enumerate(laps):
        _lap(tmp_path, f"2026-08-0{day}T18:{2 * i:02d}:00+00:00",
             corner=corner, amt=amt)


def _progress(tmp_path):
    c = TestClient(create_api(tmp_path))
    return c.get("/api/progress", params={"car": CAR, "track": TRACK}).json()


def _evening(tmp_path, day, amt):
    for i in range(4):
        _lap(tmp_path, f"2026-08-0{day}T18:{2 * i:02d}:00+00:00", amt=amt)


def test_the_key_is_always_there_even_with_no_laps(tmp_path):
    """Chi deve controllare se una chiave esiste, un giorno se lo dimentica."""
    assert _progress(tmp_path)["corner_sessions"] == []


def test_a_corner_that_improves_gives_a_falling_series(tmp_path):
    _lap(tmp_path, "2026-07-31T18:00:00+00:00")      # il riferimento (il più veloce)
    _evening(tmp_path, 1, 40)                        # 4 giri, −0,680 s alla curva 0
    _evening(tmp_path, 2, 20)                        # 4 giri, −0,340 s
    j = _progress(tmp_path)
    series = j["corner_sessions"]
    assert series, "una curva sistematica deve avere la sua serie"
    assert series[0]["corner_index"] == 0
    assert series[0]["name"]
    pts = series[0]["points"]
    assert len(pts) == 2
    assert pts[0]["median_s"] == 0.68 and pts[1]["median_s"] == 0.34
    assert pts[0]["laps"] == 4 and pts[1]["laps"] == 4


def test_only_systematic_corners_get_a_series(tmp_path):
    """Un errore episodico non è una cosa su cui misurare un andamento.

    Serve una curva episodica **che ci sia**, altrimenti il filtro non filtra
    niente: prima qui c'era una sola curva con perdite, ed era sistematica, così
    togliere `if not t.systematic: continue` da `api.py` non cambiava una virgola
    e il test restava verde.

    Il fixture ne costruisce due, sopra `SIGNIF_LOSS_MS` tutt'e due (amt=40 vale
    680 ms):
    - curva 0 sbagliata in 7 giri su 10 → sopra `RECUR_FRAC` = 0,5, sistematica;
    - curva 1 sbagliata in 3 giri su 10 → sotto, episodica.

    E la curva 1 avrebbe la sua serie di due punti, se il filtro non ci fosse:
    `session_series` conta *tutti* i giri della sessione (una curva presa bene
    vale 0,0, non «dato mancante»), quindi le stesse due sere che fanno due punti
    per la curva 0 li farebbero per la curva 1.
    """
    _lap(tmp_path, "2026-07-31T18:00:00+00:00")
    _session(tmp_path, 1, [(1, 40), (1, 40), (1, 40), (0, 40), (0, 40)])
    _session(tmp_path, 2, [(0, 40)] * 5)
    j = _progress(tmp_path)

    trends = {t["corner_index"]: t for t in j["trends"]}
    assert trends[0]["systematic"], "il test non vale niente senza una sistematica"
    assert 1 in trends, "la curva episodica deve comunque comparire fra i trend"
    assert not trends[1]["systematic"], "…e deve essere episodica, o non filtra nulla"

    series = {s["corner_index"]: s for s in j["corner_sessions"]}
    assert len(series[0]["points"]) == 2, "due sere sopra il minimo di tre giri"
    assert 1 not in series, "la curva episodica non deve avere una serie"


def test_the_series_reaches_past_the_trends_window(tmp_path):
    """corner_sessions must read the 60-lap window, not the 15-lap trends one.

    Three evenings of 7 laps each (21 laps) plus the reference make 22 laps in
    total. ``_RECENT_LAPS`` (15) only reaches 1 lap deep into the oldest
    evening: chrono[-15:] drops the 7 oldest rows (22 - 15 = 7 — the reference
    plus the oldest evening's first 6 laps), leaving just 1 lap of that
    evening in the narrow window. `session_series` needs at least 3 laps to
    turn a session into a point, so a 15-lap window could produce at most
    *two* session points here (evening 2 and evening 3) — the oldest evening
    would never clear the minimum. All three evenings fit inside
    ``_SERIES_LAPS`` (60) uncut, so the wide window `corner_sessions` actually
    reads must show three. If the window narrowed back to 15, this test would
    drop to `len(pts) == 2` and fail — the other three tests in this file
    would not notice, because none of them has more than 9 laps.
    """
    _lap(tmp_path, "2026-07-31T18:00:00+00:00")            # reference, fastest
    for day, amt in ((1, 60), (2, 40), (3, 20)):            # oldest to newest
        for i in range(7):
            _lap(tmp_path, f"2026-08-0{day}T18:{2 * i:02d}:00+00:00", amt=amt)
    j = _progress(tmp_path)

    # classify_losses runs on the narrow (15-lap) window and is untouched by
    # this task — corner 0 must still come out systematic there, or the test
    # below would pass for the wrong reason (no series at all, rather than a
    # series that's the wrong length).
    trends = {t["corner_index"]: t for t in j["trends"]}
    assert trends[0]["systematic"], "corner 0 must be systematic on the narrow window"

    series = {s["corner_index"]: s for s in j["corner_sessions"]}
    pts = series[0]["points"]
    assert len(pts) == 3, "a 15-lap window could reach at most 2 of the 3 evenings"
    assert pts[0]["median_s"] == 1.02 and pts[0]["laps"] == 7   # oldest evening, amt=60
    assert pts[1]["median_s"] == 0.68 and pts[1]["laps"] == 7   # amt=40
    assert pts[2]["median_s"] == 0.34 and pts[2]["laps"] == 7   # newest evening, amt=20
