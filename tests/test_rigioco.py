"""Il rigioco di una serata nell'Ingegnere: il modulo e il comando.

Giri sintetici salvati in `tmp_path`: la cartella vera del pilota non si tocca.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from accoach import config
from accoach.engineer.replay import replay
from accoach.recording.lap import Lap, LapSample
from accoach.recording.storage import save_lap
from accoach.telemetry.snapshot import SessionType

CAR, TRACK, DAY = "mclaren_720s_gt3_evo", "imola", "20261108"
START = datetime(2026, 11, 8, 20, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _italiano(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


def _lap(n: int, front: float, rear: float, fuel: float, ms: int = 100_000) -> Lap:
    samples = [LapSample(
        t_ms=i * 1000, pos=i / 100, speed_kmh=150.0, throttle=1.0, brake=0.0,
        steer_angle=0.0, gear="4", rpm=6000, g_lat=0.0, g_long=0.0,
        tyre_core_temp=(85.0,) * 4,
        tyre_pressure=(front, front, rear, rear), fuel=fuel)
        for i in range(100)]
    return Lap(car_model=CAR, track=TRACK, session=SessionType.PRACTICE,
               lap_time_ms=ms, valid=True, clean=True, samples=samples,
               recorded_utc=(START + timedelta(minutes=2 * n)).isoformat())


def _evening(tmp_path):
    """Sette giri a 28,0 psi davanti, la sosta, poi giri a 27,2 col pieno."""
    laps = ([_lap(n, 28.0, 26.5, 40.0 - n) for n in range(7)]
            + [_lap(7 + n, 27.2, 26.5, 50.0 - n) for n in range(8)])
    for lap in laps:
        save_lap(lap, tmp_path)
    return laps


def test_replay_reaches_the_verdict_on_a_synthetic_evening(tmp_path):
    _evening(tmp_path)
    rows = replay(tmp_path, TRACK, DAY)
    decisions = [r["decision"] for r in rows if r["kind"] == "lap"]
    assert "propose" in decisions and "accepted" in decisions
    assert decisions.index("propose") < decisions.index("accepted")
    first = rows[0]
    assert set(first) == {"t", "kind", "lap_ms", "fuel", "front", "rear",
                          "stint", "settling", "ok", "decision", "message"}
    assert first["lap_ms"] == 100_000 and first["front"] == pytest.approx(28.0)


def test_replay_uses_the_session_log_when_there_is_one(tmp_path):
    laps = _evening(tmp_path)
    plain = replay(tmp_path, TRACK, DAY)
    pi = next(i for i, r in enumerate(plain) if r["decision"] == "propose")
    # Il registro: la modifica e' scritta subito dopo la proposta, e all'uscita
    # dai box il file in macchina non e' quello scritto (R2).
    when = (START + timedelta(minutes=2 * pi + 1)).astimezone()
    stamp = lambda s: (when + timedelta(seconds=s)).replace(tzinfo=None).isoformat()
    wrong = {"state": "match", "name": "sbagliato", "expected": "scritto",
             "expected_ok": False, "expected_diff": "TC 6 invece di 3"}
    log = tmp_path / "ingegnere-20261108.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"t": stamp(0), "kind": "applied", "path": "scritto.json"},
        {"t": stamp(30), "kind": "setup", "at": "exit", "report": wrong},
    ]) + "\n", encoding="utf-8")
    rows = replay(tmp_path, TRACK, DAY, log=log)
    events = [r for r in rows if r["kind"] != "lap"]
    assert [e["kind"] for e in events] == ["applied", "setup"]
    assert events[1]["decision"] == "stand_down"
    assert "accepted" not in [r["decision"] for r in rows]


def test_the_command_is_in_the_help():
    import accoach.__main__ as cli
    assert "replay-engineer" in cli._HELP_TOOLS
