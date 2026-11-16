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


def test_the_engine_points_the_log_at_the_logs_dir_by_default(tmp_path):
    from accoach import paths
    eng = CoachEngine(reader=_Rig(tmp_path).reader, laps_dir=tmp_path / "laps",
                      engineer_voice=False)
    try:
        assert eng._session_log.folder == paths.logs_dir()
    finally:
        eng.close()
