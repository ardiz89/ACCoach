"""/api/stint — one run on one tank, and the caveats it has to carry.

The maths lives in ``test_stints.py``. What is defended here is the endpoint's
honesty: it must never hand over a pace figure without saying that the figure is
not corrected for fuel, it must not dress a slope smaller than its own noise as a
finding, and it must tell a stint it verified from one it merely could not
contradict.
"""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _lap(tmp_path, when, *, ms=None, fuel_from=None, fuel_to=None,
         core=None, psi=None, valid=True, clean=True):
    lap = synth.build_lap()
    lap.recorded_utc = when
    lap.valid = valid
    lap.clean = clean
    if ms is not None:
        lap.lap_time_ms = ms
    n = len(lap.samples)
    for i, s in enumerate(lap.samples):
        f = i / (n - 1) if n > 1 else 0.0
        if fuel_from is not None:
            s.fuel = fuel_from + (fuel_to - fuel_from) * f
        if core is not None:
            s.tyre_core_temp = (core,) * 4
        if psi is not None:
            s.tyre_pressure = (psi,) * 4
    save_lap(lap, tmp_path)
    return lap


def _stint(tmp_path, n, *, start_min=0, tank=60.0, burn=3.0, ms=120_000,
           step=0, **kw):
    """``n`` laps on one tank, a minute apart, ``step`` ms slower each lap."""
    for i in range(n):
        _lap(tmp_path, f"2026-08-02T18:{start_min + i:02d}:00+00:00",
             ms=ms + i * step, fuel_from=tank - i * burn,
             fuel_to=tank - (i + 1) * burn, **kw)


def _get(c, **kw):
    return c.get("/api/stint", params={"car": CAR, "track": TRACK,
                                       "lang": "it", **kw}).json()


def _client(tmp_path):
    return TestClient(create_api(tmp_path))


def _notes(j):
    return " ".join(j["current"]["notes"])


# --- the cut nobody else makes --------------------------------------------

def test_one_tank_is_one_stint(tmp_path):
    _stint(tmp_path, 6)
    j = _get(_client(tmp_path))
    assert len(j["stints"]) == 1 and j["current"]["laps"] == 6


def test_a_refuel_inside_one_sitting_makes_two_stints(tmp_path):
    """The whole reason this tab is not a panel on the session view: these laps
    are one sitting by every timestamp, and two runs by the only measurement
    that matters to a pace."""
    _stint(tmp_path, 3, start_min=0, tank=60.0)
    _stint(tmp_path, 4, start_min=10, tank=55.0)
    j = _get(_client(tmp_path))
    assert [s["laps"] for s in j["stints"]] == [4, 3]


def test_the_newest_stint_is_the_one_on_screen(tmp_path):
    _stint(tmp_path, 3, start_min=0, tank=60.0, ms=120_000)
    _stint(tmp_path, 2, start_min=10, tank=55.0, ms=110_000)
    j = _get(_client(tmp_path))
    assert j["index"] == 0 and j["current"]["laps"] == 2


def test_an_older_stint_can_be_asked_for(tmp_path):
    _stint(tmp_path, 3, start_min=0, tank=60.0)
    _stint(tmp_path, 2, start_min=10, tank=55.0)
    j = _get(_client(tmp_path), index=1)
    assert j["index"] == 1 and j["current"]["laps"] == 3


def test_an_out_of_range_index_is_clamped_not_an_error(tmp_path):
    _stint(tmp_path, 3)
    assert _get(_client(tmp_path), index=99)["index"] == 0


def test_an_empty_archive_answers_with_nothing_rather_than_a_500(tmp_path):
    j = _get(_client(tmp_path))
    assert j["stints"] == [] and j["current"] is None


# --- the caveat that must never be dropped --------------------------------

def test_the_pace_always_says_it_is_not_corrected_for_fuel(tmp_path):
    """Without this sentence the median reads as a degradation figure, and it is
    the net of the tank emptying and the tyres giving up. See ROADMAP voce 18."""
    _stint(tmp_path, 8)
    assert "non è corretto per la benzina" in _notes(_get(_client(tmp_path)))


def test_the_caveat_survives_laps_that_never_recorded_fuel(tmp_path):
    """Older laps cannot say how many litres came off, which makes the warning
    more necessary, not less."""
    for i in range(6):
        _lap(tmp_path, f"2026-08-02T18:0{i}:00+00:00")
    assert "non è corretto per la benzina" in _notes(_get(_client(tmp_path)))


def test_a_stint_nobody_could_verify_says_so(tmp_path):
    for i in range(4):
        _lap(tmp_path, f"2026-08-02T18:0{i}:00+00:00")
    j = _get(_client(tmp_path))
    assert j["current"]["fuel"]["verified"] is False
    assert "prima che HONE leggesse il serbatoio" in _notes(j)


def test_a_measured_stint_does_not_carry_the_unverified_warning(tmp_path):
    _stint(tmp_path, 6)
    j = _get(_client(tmp_path))
    assert j["current"]["fuel"]["verified"] is True
    assert "prima che HONE leggesse" not in _notes(j)


# --- what the trend is allowed to claim -----------------------------------

def test_a_slope_inside_its_own_noise_is_told_as_flat(tmp_path):
    _stint(tmp_path, 8, step=0)
    j = _get(_client(tmp_path))
    assert j["current"]["trend"]["direction"] == "flat"
    assert "Nessuna deriva misurabile" in _notes(j)


def test_a_real_decline_is_stated_with_its_margin(tmp_path):
    _stint(tmp_path, 8, step=500)
    j = _get(_client(tmp_path))
    t = j["current"]["trend"]
    assert t["significant"] and t["direction"] == "rising"
    assert "Il passo cala" in _notes(j)


def test_too_few_laps_is_a_different_answer_from_no_drift(tmp_path):
    """"Come back with more laps" and "your pace held" must not look alike."""
    _stint(tmp_path, 3)
    j = _get(_client(tmp_path))
    assert j["current"]["trend"] is None and j["current"]["no_trend"] == "few_laps"
    assert "Servono almeno" in _notes(j)
    assert "Nessuna deriva misurabile" not in _notes(j)


# --- the laps under the numbers -------------------------------------------

def test_every_lap_of_the_stint_is_listed_even_the_ruined_ones(tmp_path):
    """A lap you drove belongs on the list. It just can't set the pace."""
    _stint(tmp_path, 5)
    _lap(tmp_path, "2026-08-02T18:05:00+00:00", ms=300_000,
         fuel_from=45.0, fuel_to=42.0)
    j = _get(_client(tmp_path))
    rows = j["current"]["laps_detail"]
    assert len(rows) == 6 and j["current"]["counted"] == 5
    assert [r["counted"] for r in rows] == [True] * 5 + [False]


def test_the_tyre_columns_arrive_when_the_channel_does(tmp_path):
    _stint(tmp_path, 6, core=82.0, psi=27.4)
    rows = _get(_client(tmp_path))["current"]["laps_detail"]
    assert all(r["tyre_c"] == 82.0 and r["tyre_psi"] == 27.4 for r in rows)


def test_a_dead_tyre_channel_is_absent_not_zero(tmp_path):
    """Formula laps on AC carry no pressures. A tyre printed at 0 psi reads as a
    puncture that never happened."""
    _stint(tmp_path, 6, core=82.0)
    rows = _get(_client(tmp_path))["current"]["laps_detail"]
    assert all(r["tyre_psi"] is None for r in rows)


def test_the_fuel_block_reports_the_burn_and_the_range(tmp_path):
    _stint(tmp_path, 5, tank=60.0, burn=3.0)
    f = _get(_client(tmp_path))["current"]["fuel"]
    assert f["start"] == 60.0 and f["used"] == 15.0
    assert f["per_lap"] == 3.0 and f["range_laps"] == 15


def test_the_four_wheels_arrive_separately_as_well_as_averaged(tmp_path):
    """A right-front running hotter than its pair is a fact the mean erases, so
    the chart gets the wheels and the drift verdict gets the mean."""
    _stint(tmp_path, 6, core=82.0, psi=27.4)
    ty = _get(_client(tmp_path))["current"]["tyres"]
    assert len(ty["wheels"]) == 6
    assert ty["wheels"][0]["temp"] == [82.0] * 4
    assert ty["core_c"][0] == 82.0


def test_the_tyre_note_never_claims_to_measure_wear(tmp_path):
    """Neither sim publishes a wear figure we record. Saying "tyre degradation"
    over a temperature trace would be inventing a channel."""
    _stint(tmp_path, 6, core=82.0, psi=27.4)
    assert "usura gomme" in _notes(_get(_client(tmp_path)))
