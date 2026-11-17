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
                          "stint", "settling", "ok", "decision", "message",
                          "dropped"}
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


def test_a_base_row_brings_the_dials_of_the_choice():
    """La scelta sulla pagina col registro: le manopole della riga ``base``
    tengono tolto il blocco dell'assetto non salvato anche nel rigioco."""
    from accoach.engineer.factory import engineer_for
    from accoach.engineer.replay import _feed

    eng = engineer_for(CAR, TRACK, is_acc=True)
    unsaved = {"state": "unsaved", "unsaved_diff": "TC 6 invece di 3",
               "dials": [6, 6, 0, 0.75]}
    _feed(eng, {"kind": "setup", "at": "exit", "report": unsaved})
    assert eng._unsaved
    _feed(eng, {"kind": "base", "path": "x.json", "expected": None,
                "dials": [6, 6, 0, 0.75]})
    _feed(eng, {"kind": "setup", "at": "live", "report": unsaved})
    assert eng._unsaved is None


def test_an_applied_row_from_the_wheel_counts_like_one_from_the_page():
    from accoach.engineer.core import AtomicChange, ProposedChange
    from accoach.engineer.factory import engineer_for
    from accoach.engineer.replay import _feed

    for source in ("wheel", "page"):
        eng = engineer_for(CAR, TRACK, is_acc=True)
        eng._pending = ProposedChange(changes=(AtomicChange("tC1", None, 1),),
                                      rationale="TC +1.", phase_label="x", tag="AV")
        _feed(eng, {"kind": "applied", "path": None, "source": source})
        assert eng.active is not None, source


def test_the_command_is_in_the_help():
    import accoach.__main__ as cli
    assert "replay-engineer" in cli._HELP_TOOLS


def test_events_of_another_session_in_the_same_day_log_are_not_fed(tmp_path):
    _evening(tmp_path)
    plain = replay(tmp_path, TRACK, DAY)
    pi = next(i for i, r in enumerate(plain) if r["decision"] == "propose")
    mine = (START + timedelta(minutes=2 * pi + 1)).astimezone()
    other = (START - timedelta(hours=3)).astimezone()
    stamp = lambda w, s: (w + timedelta(seconds=s)).replace(tzinfo=None).isoformat()
    wrong = {"state": "match", "name": "sbagliato", "expected": "scritto",
             "expected_ok": False, "expected_diff": "TC 6 invece di 3"}
    lap_row = lambda w, car, track: {"t": stamp(w, 0), "kind": "lap",
                                     "car": car, "track": track}
    log = tmp_path / "ingegnere-20261108.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"t": stamp(other, -60), "kind": "applied", "path": "x.json"},
        {"t": stamp(other, -30), "kind": "setup", "at": "exit", "report": wrong},
        lap_row(other, "ferrari_296_gt3", "monza"),
        {"t": stamp(mine, 0), "kind": "applied", "path": "scritto.json"},
        lap_row(mine, CAR, "Imola"),
    ]) + "\n", encoding="utf-8")
    rows = replay(tmp_path, TRACK, DAY, log=log)
    assert [r["kind"] for r in rows if r["kind"] != "lap"] == ["applied"]
    assert "stand_down" not in [r["decision"] for r in rows]


def test_a_corrupt_lap_file_is_skipped_and_counted(tmp_path):
    _evening(tmp_path)
    bad = tmp_path / f"{TRACK}__{CAR}__1m40s000__{DAY}T215959z0000.lap.json.gz"
    bad.write_bytes(b"non e' un giro")
    skipped = []
    rows = replay(tmp_path, TRACK, DAY, skipped=skipped)
    assert skipped == [bad]
    assert sum(r["kind"] == "lap" for r in rows) == 15


def test_the_command_says_when_the_folder_or_the_day_is_missing(tmp_path, capsys):
    from accoach.engineer.replay import main
    with pytest.raises(SystemExit) as e:
        main([TRACK, DAY, "--laps", str(tmp_path / "non-esiste")])
    assert e.value.code == 1 and "non trovata" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        main([TRACK, DAY, "--laps", str(tmp_path)])
    assert e.value.code == 1 and "Nessun giro" in capsys.readouterr().out


def test_the_command_counts_unreadable_laps(tmp_path, capsys):
    from accoach.engineer.replay import main
    _evening(tmp_path)
    (tmp_path / f"{TRACK}__{CAR}__1m40s000__{DAY}T215959z0000.lap.json.gz"
     ).write_bytes(b"rotto")
    main([TRACK, DAY, "--laps", str(tmp_path)])
    assert "1 file di giri illeggibili" in capsys.readouterr().out


def _flat(lap: Lap, lo: float, hi: float) -> Lap:
    """Una curva che il giro non ha: pieno, dritto, senza freno fra lo e hi."""
    for s in lap.samples:
        if lo <= s.pos <= hi:
            s.speed_kmh, s.brake, s.throttle, s.steer_angle = 255.0, 0.0, 1.0, 0.0
    return lap


def test_every_lap_of_the_evening_is_read_on_the_same_corners(tmp_path, monkeypatch):
    """Come il motore in pista: le curve sono quelle di un giro solo.

    Il 17/11, rigiocando Imola, ogni giro trovava curve sue: la zona della
    Rivazza era tagliata in modo diverso da un giro all'altro, e accoppiate per
    posizione davano scarti finti di 125-140 km/h. Le curve si prendono una
    volta, dal giro piu' veloce pulito e valido della serata.
    """
    from synth import build_lap

    from accoach.engineer import replay as rigioco
    from accoach.recording.storage import load_lap
    from accoach.track import detect_corners

    # Il piu' veloce e' tagliato: non fa da riferimento.
    dirty = _flat(build_lap(car=CAR, track=TRACK, clean=False), 0.15, 0.42)
    ref = build_lap(car=CAR, track=TRACK, clean=True)
    other = _flat(build_lap(car=CAR, track=TRACK, clean=True), 0.55, 0.82)
    paths = []
    for n, (lap, ms) in enumerate([(other, 101_000), (dirty, 98_000),
                                   (ref, 99_000)]):
        lap.lap_time_ms = ms
        lap.recorded_utc = (START + timedelta(minutes=2 * n)).isoformat()
        paths.append(save_lap(lap, tmp_path))
    own = [[c.apex_pos for c in detect_corners(load_lap(p).samples)]
           for p in paths]
    assert own[0] != own[2] and own[1] != own[2]   # da soli, curve diverse
    seen = []
    real = rigioco.build_lap_stats

    def spy(lap, corners=None, *a, **kw):
        seen.append(corners)
        return real(lap, corners, *a, **kw)

    monkeypatch.setattr(rigioco, "build_lap_stats", spy)
    replay(tmp_path, TRACK, DAY)
    assert len(seen) >= 3 and seen[0] is not None
    assert all(c is seen[0] for c in seen)
    assert [c.apex_pos for c in seen[0]] == own[2]
