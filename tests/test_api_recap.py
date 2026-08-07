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
    scarto di 0.9 s contro una tolleranza di 5 s), quindi quello che il recap
    riceve è davvero un metro con l'orologio corto, non un giro riparato.
    """
    best = synth.skew_clock(synth.build_lap(), 900)
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
