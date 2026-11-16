"""Il registro della sessione: una riga per giro e per evento dei box.

Il motore e' quello finto di `test_impronta_motore`; le cartelle sono in
`tmp_path`, e il registro non deve mai rompere un giro.
"""
import json
from datetime import date, datetime

import pytest

from accoach.engine import CoachEngine
from accoach.engineer.session_log import SessionLog
from accoach.recording import Lap
from accoach.recording.lap import SessionType
from test_impronta_motore import (  # noqa: F401 - la fixture e i frame
    CAR, HONE_8_COLD, TRACK, _Rig, _box_change, _italiano, _snap,
)


@pytest.fixture
def rig(tmp_path):
    r = _Rig(tmp_path)
    r.eng._session_log = SessionLog(tmp_path / "logs")
    try:
        yield r
    finally:
        r.close()


def _rows(tmp_path):
    files = sorted((tmp_path / "logs").glob("ingegnere-*.jsonl"))
    assert len(files) == 1
    return [json.loads(x) for x in files[0].read_text(encoding="utf-8").splitlines()]


def _a_lap(rig):
    lap = Lap(CAR, TRACK, SessionType.PRACTICE, 100000, True)
    rig.eng._observe_lap(lap)


def test_the_file_is_named_after_the_day(tmp_path):
    log = SessionLog(tmp_path, clock=lambda: datetime(2026, 11, 16, 10, 0))
    assert log.path_for(date(2026, 11, 16)).name == "ingegnere-20261116.jsonl"
    log.write("x", a=1)
    row = json.loads((tmp_path / "ingegnere-20261116.jsonl").read_text())
    assert row["kind"] == "x" and row["a"] == 1 and row["t"].startswith("2026-11-16T10:00")


def test_each_lap_and_each_pit_exit_leave_a_line(rig, tmp_path):
    rig.drive(_snap())
    _a_lap(rig)
    rig.propose(_box_change())
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("lane"), _snap("box", tc=6, psi=HONE_8_COLD),
              _snap("lane", tc=6), _snap(tc=6))
    rows = _rows(tmp_path)
    kinds = [r["kind"] for r in rows]
    assert "lap" in kinds and "setup" in kinds and "applied" in kinds
    lap = next(r for r in rows if r["kind"] == "lap")
    for key in ("car", "track", "lap_ms", "stable", "warm", "stint",
                "settling", "decision", "message", "progress", "reading"):
        assert key in lap
    assert lap["car"] == CAR
    setup = [r for r in rows if r["kind"] == "setup"]
    assert {s["at"] for s in setup} >= {"exit"}
    ex = next(s for s in setup if s["at"] == "exit")
    assert ex["report"]["state"] and ex["reading"]["tc"] == 6
    assert "HONE_8" in ex["files"]
    assert ex["expected"].endswith("HONE_8.json")
    # Le pressioni lette da fermo e la temperatura interna, fredde o no: il
    # test dice dopo se la soglia delle gomme fredde regge.
    assert ex["box_psi"] == list(HONE_8_COLD)
    assert "box_core_c" in ex


def test_a_stop_with_hot_tyres_logs_what_it_read(rig, tmp_path):
    hot = (27.6, 27.4, 27.1, 27.0)
    rig.drive(_snap(), _snap("lane"),
              _snap("box", psi=hot, core=(85.0, 84.0, 80.0, 79.0), air=20.0),
              _snap("lane"), _snap())
    ex = next(r for r in _rows(tmp_path) if r["kind"] == "setup" and r["at"] == "exit")
    assert ex["reading"]["cold_psi"] is None
    assert ex["box_psi"] == list(hot)
    assert ex["box_core_c"] == 82.0


def test_an_unwritable_folder_never_breaks_a_lap(rig, tmp_path):
    blocker = tmp_path / "logs-che-e-un-file"
    blocker.write_text("x")
    rig.eng._session_log = SessionLog(blocker)
    rig.drive(_snap())
    _a_lap(rig)                                   # niente eccezione
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap())


def test_the_log_has_no_personal_data(rig, tmp_path):
    rig.drive(_snap())
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap())
    rig.eng.mark_base_confirmed(path=rig.path("HONE_7"))
    rig.drive(_snap("lane"), _snap("box", tc=6, psi=HONE_8_COLD),
              _snap("lane", tc=6), _snap(tc=6))
    rows = _rows(tmp_path)
    text = "\n".join(json.dumps(r) for r in rows)
    assert str(tmp_path) not in text and str(tmp_path).replace("\\", "\\\\") not in text
    applied = next(r for r in rows if r["kind"] == "applied")
    assert applied["path"] == f"{CAR}/Imola/HONE_8.json"
    base = next(r for r in rows if r["kind"] == "base")
    assert base["path"] == f"{CAR}/Imola/HONE_7.json"
    assert "expected" in base


def test_the_base_row_says_whether_the_brake_bias_was_learned(rig, tmp_path):
    rig.drive(_snap(), _snap("lane"), _snap("box", bias=0.642, psi=HONE_8_COLD))
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))      # concorda
    rig.drive(_snap("box", bias=0.642, psi=HONE_8_COLD),
              _snap("box", tc=6, bias=0.642, psi=HONE_8_COLD))  # TC diverso
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap("box", tc=6, bias=0.642, psi=HONE_8_COLD))
    rig.eng.mark_base_confirmed()                               # senza file
    rig.drive(_snap("box", tc=6, bias=0.642, psi=HONE_8_COLD))
    base = [r for r in _rows(tmp_path) if r["kind"] == "base"]
    assert [b["bias_learned"] for b in base] == [True, False, False]


def test_an_engine_without_a_logs_folder_writes_no_log(tmp_path, monkeypatch):
    from accoach import paths
    monkeypatch.setattr(paths, "logs_dir", lambda: tmp_path / "logs")
    r = _Rig(tmp_path)
    try:
        assert r.eng._session_log is None
        r.drive(_snap())
        r.eng._observe_lap(Lap(CAR, TRACK, SessionType.PRACTICE, 100000, True))
        r.eng.mark_setup_applied(path=r.path("HONE_8"))
        r.drive(_snap("lane"), _snap("box", tc=6, psi=HONE_8_COLD),
                _snap("lane", tc=6), _snap(tc=6))
    finally:
        r.close()
    assert not list(tmp_path.rglob("ingegnere-*.jsonl"))


def test_the_demo_engine_has_no_log():
    from accoach.demo import make_demo_engine
    eng = make_demo_engine()
    try:
        assert eng._session_log is None
    finally:
        eng.close()


def test_the_real_entry_points_pass_the_logs_folder():
    import inspect
    from accoach import app, coach_app, server
    for mod in (app, coach_app, server):
        assert "logs_dir=paths.logs_dir()" in inspect.getsource(mod)
