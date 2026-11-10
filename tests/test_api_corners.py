"""/api/corners — la sessione, curva per curva, con le fonti.

L'aggregazione e' provata in ``test_corner_session.py`` e il lettore dei fatti
in ``test_trackfacts.py``. Qui si difende l'endpoint: quale sessione, quali
giri, quale nome, quali fonti, e che un giro guasto non costa la pagina.
"""
import pytest
from fastapi.testclient import TestClient

import accoach.api as api_mod
from accoach import cornernames
from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    """I nomi scritti dal pilota, lontano dalla casa vera."""
    p = tmp_path / "corner-names.json"
    monkeypatch.setattr(cornernames, "path", lambda: p)
    return p


def _lap(laps, when, *, amt=0, corner=0):
    lap = synth.build_lap(slow_corner=corner, amt=amt) if amt else synth.build_lap()
    lap.recorded_utc = when
    lap.valid = True
    lap.clean = True
    save_lap(lap, laps)
    return lap


def _laps_dir(tmp_path):
    d = tmp_path / "laps"
    d.mkdir(exist_ok=True)
    return d


def _three(tmp_path):
    d = _laps_dir(tmp_path)
    _lap(d, "2026-07-20T18:00:00+00:00")
    _lap(d, "2026-07-20T18:03:00+00:00", amt=20, corner=1)
    _lap(d, "2026-07-20T18:06:00+00:00")
    return TestClient(create_api(d))


def _get(c, **kw):
    return c.get("/api/corners",
                 params={"car": CAR, "track": TRACK, "lang": "it", **kw})


def test_sessione_vuota(tmp_path):
    r = _get(TestClient(create_api(_laps_dir(tmp_path))))
    assert r.status_code == 200
    j = r.json()
    assert j["corners"] == [] and j["laps"] == 0
    assert j == {"index": None, "laps": 0, "skipped": 0, "reference": None,
                 "corners": [], "has_sources": False}


def test_curve_della_sessione(tmp_path):
    r = _get(_three(tmp_path))
    assert r.status_code == 200
    j = r.json()
    assert j["laps"] == 3 and j["skipped"] == 0
    assert j["reference"]["path"] and j["reference"]["lap_time_ms"] > 0
    corners = j["corners"]
    assert corners
    lost = [c["lost_total_ms"] for c in corners]
    assert lost == sorted(lost, reverse=True)
    assert corners[0]["index"] == 1          # la curva rallentata, per prima
    for c in corners:
        for key in ("phases_ms", "brake_m", "line_m", "name", "catalog_name",
                    "apex", "sources", "gear_compare"):
            assert key in c


def test_solo_la_sessione_scelta(tmp_path):
    d = _laps_dir(tmp_path)
    _lap(d, "2026-07-20T18:00:00+00:00")
    _lap(d, "2026-07-20T18:03:00+00:00", amt=20)
    _lap(d, "2026-07-27T18:00:00+00:00", amt=10)
    c = TestClient(create_api(d))
    assert _get(c).json()["laps"] == 1
    j = _get(c, index=1).json()
    assert j["index"] == 1 and j["laps"] == 2
    assert _get(c, index=99).json()["index"] == 1     # fuori scala: l'ultima


def test_senza_fatti_niente_fonti(tmp_path):
    j = _get(_three(tmp_path)).json()
    assert j["has_sources"] is False
    for c in j["corners"]:
        assert c["sources"] == {"reference": [], "single": [],
                                "disputed": [], "mistakes": []}
        assert c["gear_compare"] is None


def test_fonti_abbinate_per_posizione(tmp_path, monkeypatch):
    c = _three(tmp_path)
    first = min(_get(c).json()["corners"], key=lambda x: x["apex"])
    catalog = first["catalog_name"]
    facts = {"version": 3, "track": TRACK, "facts": [], "disputed": [],
             "single": [{"corner": catalog, "type": "gear", "value": "1",
                         "source": "s1"}]}
    monkeypatch.setattr("accoach.trackfacts.load", lambda track, root=None: facts)
    r = c.post("/api/corner-name",
               json={"track": TRACK, "pos": first["apex"], "name": "La mia prima"})
    assert r.status_code == 200

    j = _get(c).json()
    assert j["has_sources"] is True
    mine = next(x for x in j["corners"] if x["index"] == first["index"])
    assert mine["name"] == "La mia prima"
    assert mine["catalog_name"] == catalog          # le fonti non seguono il nome
    assert mine["sources"]["single"] and mine["sources"]["single"][0]["value"] == "1"
    others = [x for x in j["corners"] if x["index"] != first["index"]]
    assert all(not x["sources"]["single"] for x in others)


def test_un_giro_guasto_si_salta(tmp_path, monkeypatch):
    c = _three(tmp_path)
    real = api_mod.build_line_report
    broken = {"hit": False}

    def flaky(lap, base, corners, names):
        if not broken["hit"]:
            broken["hit"] = True
            raise RuntimeError("giro guasto")
        return real(lap, base, corners, names)

    monkeypatch.setattr(api_mod, "build_line_report", flaky)
    r = _get(c)
    assert r.status_code == 200
    j = r.json()
    assert j["skipped"] == 1 and j["laps"] == 2


def _brake_later_session(d):
    """Il riferimento frena tardi in curva 1; l'altro giro frena al solito
    punto e perde lì: la causa è «frena più tardi»."""
    ref = synth.build_lap()
    for s in ref.samples:
        if 0.15 <= s.pos < 0.26:
            s.brake = 0.0
    ref.recorded_utc, ref.valid, ref.clean = "2026-07-20T18:00:00+00:00", True, True
    save_lap(ref, d)
    lap = synth.build_lap()
    for s in lap.samples:
        if s.pos >= 0.25:
            s.t_ms += 400
    lap.lap_time_ms += 400
    lap.recorded_utc, lap.valid, lap.clean = "2026-07-20T18:03:00+00:00", True, True
    save_lap(lap, d)


def _corner0(j):
    return next(c for c in j["corners"] if c["index"] == 0)


def test_dove_esci_non_dice_frena_piu_tardi(tmp_path):
    d = _laps_dir(tmp_path)
    _brake_later_session(d)
    plain = _get(TestClient(create_api(d))).json()
    assert _corner0(plain)["cause"] == "brake_later"
    assert _corner0(plain)["cause_message"] == "Frena più tardi"

    # Due uscite recenti in curva 1, un'altra sera: giri sporchi, quindi fuori
    # dalla sessione, ma contano come in /api/analysis.
    for day in (18, 19):
        off = synth.build_lap()
        synth.retime(off, 110_000)
        off.recorded_utc = f"2026-07-{day}T18:00:00+00:00"
        off.valid, off.clean, off.lost_at = True, False, 0.31
        save_lap(off, d)
    j = _get(TestClient(create_api(d))).json()
    assert j["laps"] == 2
    c0 = _corner0(j)
    assert c0["cause"] == "brake_later"
    assert c0["cause_message"] == "Prima resta in pista all'uscita"


def test_numeri_arrotondati():
    from accoach.coaching.corner_session import CornerSummary
    s = CornerSummary(index=0, laps=3, lost_total_ms=123.456789, laps_losing=2,
                      phases_ms={"entry": 10.0444, "apex": 3.1666},
                      brake_m=101.23456, brake_spread_m=4.56789,
                      brake_kmh=212.34567, line_m={"entry": 0.123456,
                                                   "apex": -1.98765,
                                                   "exit": 2.0},
                      apex_shift_m=3.33333)
    d = api_mod._rounded_summary(s)
    assert d["lost_total_ms"] == 123.5
    assert d["phases_ms"] == {"entry": 10.0, "apex": 3.2}
    assert (d["brake_m"], d["brake_spread_m"], d["brake_kmh"],
            d["apex_shift_m"]) == (101.23, 4.57, 212.35, 3.33)
    assert d["line_m"] == {"entry": 0.12, "apex": -1.99, "exit": 2.0}
    empty = api_mod._rounded_summary(CornerSummary(index=1, laps=1,
                                                   lost_total_ms=0.0,
                                                   laps_losing=0))
    assert empty["brake_m"] is None and empty["line_m"] is None


def _beats_reference_session(d):
    """Il riferimento (il giro più veloce) perde un po' in curva 1 e vince in
    curva 2; gli altri due giri in curva 1 vanno più forte di lui."""
    _lap(d, "2026-07-20T18:00:00+00:00", amt=10, corner=0)   # riferimento
    _lap(d, "2026-07-20T18:03:00+00:00", amt=40, corner=1)
    _lap(d, "2026-07-20T18:06:00+00:00", amt=40, corner=1)


def test_curva_dove_batti_il_riferimento_resta(tmp_path, monkeypatch):
    """Contro il solo principale: in curva 1 due giri su tre guadagnano. La
    curva resta, coi giri giusti, e il totale e' netto."""
    d = _laps_dir(tmp_path)
    _beats_reference_session(d)

    def no_refs(*a, **kw):
        raise RuntimeError("niente gesto migliore")

    monkeypatch.setattr(api_mod, "corner_bests_for", no_refs)
    j = _get(TestClient(create_api(d))).json()
    assert j["laps"] == 3
    c0 = _corner0(j)
    assert (c0["laps"], c0["laps_losing"]) == (3, 0)
    assert c0["lost_total_ms"] == -292.0      # due giri a -146, il riferimento 0
    assert c0["cause"] is None
    c1 = next(c for c in j["corners"] if c["index"] == 1)
    assert (c1["laps"], c1["laps_losing"], c1["lost_total_ms"]) == (3, 2, 1360.0)
    assert [c["index"] for c in j["corners"]] == [1, 0]


def test_ogni_giro_conta_anche_col_gesto_migliore(tmp_path):
    """Col gesto migliore la curva 1 si misura sul giro che lì va più forte:
    perde solo il riferimento, ma i giri in curva restano tre."""
    d = _laps_dir(tmp_path)
    _beats_reference_session(d)
    c0 = _corner0(_get(TestClient(create_api(d))).json())
    assert (c0["laps"], c0["laps_losing"]) == (3, 1)
