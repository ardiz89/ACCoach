"""Registro e rigioco: i giri tolti per costanza si vedono (17/11).

Il motore e' il banco di `test_impronta_motore`; il rigioco gira su giri
sintetici in `tmp_path` con le statistiche fornite a mano (le curve di un giro
sintetico non si rilevano).
"""
import json

import pytest

from accoach.engineer import LapStats, replay as replay_mod
from accoach.engineer.replay import _format, replay
from accoach.engineer.session_log import SessionLog
from accoach.recording import Lap
from accoach.recording.lap import SessionType
from accoach.recording.storage import save_lap
from test_impronta_motore import CAR, TRACK, _Rig, _snap  # noqa: F401
from test_rigioco import DAY, _italiano, _lap  # noqa: F401 - la fixture

NAMES = ("A", "B", "C", "D", "E", "F")
APEX = (0.05, 0.12, 0.22, 0.33, 0.45, 0.80)


def _stats(fuel, delta=0.0, at=()):
    speeds = [100.0 + (delta if i in at else 0.0) for i in range(6)]
    return LapStats(lap_time_ms=100000, stable=True, warmed_up=True,
                    pressures_hot={"front": 26.5, "rear": 26.5}, fuel_l=fuel,
                    corner_vmin=tuple(zip(APEX, speeds, NAMES)),
                    dials=(3, 4, 0, 0.64))


def test_la_riga_lap_del_registro_porta_i_giri_tolti(tmp_path, monkeypatch):
    rig = _Rig(tmp_path)
    try:
        rig.eng._session_log = SessionLog(tmp_path / "logs")
        rig.drive(_snap())
        dropped = [{"stint": 1, "stint_lap": 5, "last": True,
                    "corners": [["Tosa", 6.0]]}]
        real = rig.eng._engineer.observe

        def observe(stats):
            d = real(stats)
            rig.eng._engineer.last_dropped = list(dropped)
            return d

        monkeypatch.setattr(rig.eng._engineer, "observe", observe)
        rig.eng._observe_lap(Lap(CAR, TRACK, SessionType.PRACTICE, 100000, True))
        files = list((tmp_path / "logs").glob("ingegnere-*.jsonl"))
        rows = [json.loads(x) for x in files[0].read_text(encoding="utf-8").splitlines()]
        lap = next(r for r in rows if r["kind"] == "lap")
        assert lap["dropped"] == dropped
    finally:
        rig.close()


def test_il_rigioco_conta_i_giri_tolti(tmp_path, monkeypatch):
    for n in range(7):
        save_lap(_lap(n, 26.5, 26.5, 60.0 - n), tmp_path)
    seq = iter([_stats(60 - n, -6.0 if n == 5 else 0.0, (1, 2, 3))
                for n in range(7)])
    monkeypatch.setattr(replay_mod, "build_lap_stats", lambda lap, *a, **k: next(seq))
    rows = replay(tmp_path, TRACK, DAY)
    laps = [r for r in rows if r["kind"] == "lap"]
    assert [r["dropped"] for r in laps].count(1) == 1
    assert laps[5]["dropped"] == 1
    assert "-1" in _format(5, laps[5])
    assert "-1" not in _format(4, laps[4])
