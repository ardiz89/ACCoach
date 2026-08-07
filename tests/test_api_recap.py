"""/api/sessions: il recap di un'uscita, e cosa dice quando non può dire niente."""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _lap(tmp_path, when, *, amt=0):
    lap = synth.build_lap(slow_corner=0, amt=amt) if amt else synth.build_lap()
    lap.recorded_utc = when
    save_lap(lap, tmp_path)


def _get(tmp_path, **kw):
    c = TestClient(create_api(tmp_path))
    return c.get("/api/sessions", params={"car": CAR, "track": TRACK, **kw}).json()


def test_the_key_is_always_there(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    assert "recap" in _get(tmp_path)["current"]


def test_the_families_add_up_to_the_average(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")            # il migliore
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=20)
    _lap(tmp_path, "2026-08-01T18:04:00+00:00", amt=30)
    r = _get(tmp_path)["current"]["recap"]
    assert r is not None
    total = sum(p["avg_s"] for p in r["phases"])
    assert abs(total - r["gain_avg_s"]) < 0.01
    assert [p["phase"] for p in r["phases"]] == \
        ["entry", "apex", "exit", "after", "launch"]


def test_the_displayed_total_matches_the_displayed_parts_exactly(tmp_path):
    """The check above tolerates 0.01s of drift, wide enough to hide the
    ±0.001s this produces: `gain_avg_s` and the five phases are each rounded
    to three decimals *independently*, and six separate roundings against one
    on the total can land a full millisecond apart even though the
    full-precision numbers behind them are exactly consistent (session_recap's
    own guarantee). (0, 29, 32) is a real repro — found by search, not by
    hand — where the un-fixed endpoint answers gain_avg_s=0.533 against a
    phase sum of 0.534. Pinned with no tolerance, on the digits actually
    shown, because `recap.where` promises on screen that they add up and a
    driver checks that by hand."""
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")            # il migliore
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=29)
    _lap(tmp_path, "2026-08-01T18:04:00+00:00", amt=32)
    r = _get(tmp_path)["current"]["recap"]
    assert r is not None
    assert r["gain_avg_s"] == round(sum(p["avg_s"] for p in r["phases"]), 3)


def test_every_lap_but_the_best_has_a_row_with_a_named_corner(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=20)
    _lap(tmp_path, "2026-08-01T18:04:00+00:00", amt=30)
    r = _get(tmp_path)["current"]["recap"]
    assert len(r["laps"]) == 2                    # il migliore è il metro
    assert all(l["corner"] for l in r["laps"])    # un nome c'è sempre


def test_a_single_lap_run_has_no_recap_not_a_zero(tmp_path):
    """Il migliore è l'unico: non c'è un gap da mostrare, e non se ne inventa uno."""
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    assert _get(tmp_path)["current"]["recap"] is None


def test_a_best_lap_with_a_broken_clock_voids_the_run_and_says_which_cause(tmp_path):
    """Il metro con l'orologio rotto: niente recap, e il payload porta la causa.

    Il flag NON è ricalcolato qui: arriva da ``session_recap``, l'unico posto
    dove quel criterio è scritto. Il giro sopravvive a ``trusted_lap_ms`` (uno
    scarto di 1.5 s contro una tolleranza di 10 s su un giro da 100 s), quindi
    quello che il recap riceve è davvero un metro con l'orologio che non chiude,
    non un giro riparato. 1.5 s è il doppio della tolleranza della guardia su un
    giro di questa durata (max(250, 100_000 × 0.007) = 700 ms).
    """
    best = synth.skew_clock(synth.build_lap(), 1500)
    best.recorded_utc = "2026-08-01T18:00:00+00:00"
    save_lap(best, tmp_path)
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=20)

    cur = _get(tmp_path)["current"]
    assert cur["best"] == "1:40.000"          # il metro è ancora lui
    assert cur["recap"] is None
    assert cur["recap_clock_broken"] is True


def test_any_other_empty_recap_does_not_blame_the_clock(tmp_path):
    """La frase specifica esce SOLO per la guardia. Qui il recap è vuoto per
    un'altra delle sette cause (un solo giro valido): il flag resta falso e la
    schermata torna alla frase generica, che è il difetto che il Task 4 ha
    appena corretto e che questo test tiene chiuso."""
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    cur = _get(tmp_path)["current"]
    assert cur["recap"] is None
    assert cur["recap_clock_broken"] is False


def test_an_empty_recap_from_session_recap_itself_still_does_not_blame_the_clock(tmp_path):
    """L'altro modo di restare senza recap, e quello che conta di più: qui a
    tornare vuoto è ``session_recap`` (l'unico altro giro ha due campioni, non
    abbastanza per tagliarlo in fasi), non uno dei rifiuti che ``_recap_of``
    decide da sé. È la riga dove il motivo viene inoltrato: se l'endpoint lo
    affermasse per conto suo invece di leggerlo dall'esito, questo test è
    l'unico che se ne accorgerebbe — l'orologio di questi giri è sano.
    """
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")            # il migliore
    short = synth.build_lap(slow_corner=0, amt=15)
    short.recorded_utc = "2026-08-01T18:02:00+00:00"
    short.samples = [short.samples[0], short.samples[-1]]   # troppo corto per le fasi
    save_lap(short, tmp_path)

    cur = _get(tmp_path)["current"]
    assert cur["recap"] is None
    assert cur["recap_clock_broken"] is False


def test_a_run_that_measures_fine_does_not_blame_the_clock_either(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=20)
    cur = _get(tmp_path)["current"]
    assert cur["recap"] is not None
    assert cur["recap_clock_broken"] is False


def test_an_older_session_can_be_asked_for(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    _lap(tmp_path, "2026-07-20T18:02:00+00:00", amt=20)
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    assert _get(tmp_path, index=1)["current"]["recap"] is not None


def test_a_dropped_lap_does_not_shift_the_row_next_to_it(tmp_path):
    """session_recap silently drops any lap it cannot split into phases (too
    few samples to find entry/apex/exit cuts in). If the endpoint pairs rows to
    laps by *position* (``zip(others, recap.laps)``) rather than by identity,
    dropping lap A here shifts lap B's row left and the surviving row is
    printed under lap A's file path — B's gap and worst corner, reported as A's.

    Lap A is real and otherwise valid, just built with only its first and last
    sample (so its own declared lap time survives ``trusted_lap_ms``'s
    span-check unchanged, and it is not mistaken for the session's best) and
    too short for ``lap_time_split`` to cut into phases. Lap B is an ordinary
    lap. Only one row can come back, and it has to be B's.
    """
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")                      # best

    lap_a = synth.build_lap(slow_corner=0, amt=15)
    lap_a.recorded_utc = "2026-08-01T18:02:00+00:00"
    lap_a.samples = [lap_a.samples[0], lap_a.samples[-1]]            # too short to split
    path_a = str(save_lap(lap_a, tmp_path))

    lap_b = synth.build_lap(slow_corner=0, amt=30)
    lap_b.recorded_utc = "2026-08-01T18:04:00+00:00"
    path_b = str(save_lap(lap_b, tmp_path))

    r = _get(tmp_path)["current"]["recap"]
    assert r is not None
    assert len(r["laps"]) == 1
    assert r["laps"][0]["path"] == path_b
    assert r["laps"][0]["path"] != path_a


def test_the_demo_opens_on_a_recap_with_real_numbers_in_it():
    """`python -m accoach web --demo` è la vetrina, e la prima schermata che
    apre è «Com'è andata» sulla prima combo che `/api/combos` restituisce.

    Fino a ieri quella schermata diceva «non c'è ancora abbastanza in questa
    uscita per misurarlo», su tutte e sette le sessioni: `_seed_demo` metteva
    un giro per giornata, `_recap_of` toglieva il migliore perché è il metro,
    e non restava niente da misurare. La vetrina mostrava lo stato vuoto.

    Non basta però che il recap **esista**: un'uscita di giri quasi identici
    ne produce uno tecnicamente valido con cinque zeri dentro, che è la stessa
    schermata vuota con più punteggiatura (la lezione «la demo non ha
    perdite», già pagata su questo ramo). Quindi qui si guarda dentro: cinque
    fasi con un numero sopra lo zero, almeno due righe giro, e la proprietà
    per cui la scheda esiste — le parti sommano esattamente al totale, sulle
    cifre mostrate.
    """
    from pathlib import Path

    from accoach.api import _seed_demo

    c = TestClient(create_api(Path(_seed_demo())))
    combos = c.get("/api/combos").json()
    first = (combos["combos"] if isinstance(combos, dict) else combos)[0]
    cur = c.get("/api/sessions",
                params={"car": first["car"], "track": first["track"]}).json()["current"]

    r = cur["recap"]
    assert r is not None, "la demo apre ancora sullo stato vuoto"
    assert cur["recap_clock_broken"] is False
    assert len(r["phases"]) == 5
    assert all(p["avg_s"] > 0 for p in r["phases"]), \
        f"una fase a zero: la demo non ha perdite da mostrare lì — {r['phases']}"
    assert len(r["laps"]) >= 2, "una riga sola non è un «giro per giro»"
    assert len({l["corner_index"] for l in r["laps"]}) > 1, \
        "tutti i giri perdono nella stessa curva: niente da leggere"
    assert r["gain_avg_s"] == round(sum(p["avg_s"] for p in r["phases"]), 3)
