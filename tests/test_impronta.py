"""Impronta del setup: letture, valori dei file di setup e confronto."""
import json
from pathlib import Path

from accoach.engineer.fingerprint import (
    FieldDiff, Reading, changed, compare, describe, file_values, match,
)
from accoach.engineer import fingerprint as fp

IMOLA_0 = dict(press=[57, 52, 51, 48], tc=3, abs=4, emap=0, bias=0, fuel=48)
HONE_7 = dict(press=[60, 55, 44, 41], tc=3, abs=4, emap=0, bias=0, fuel=48)
HONE_8 = dict(press=[52, 47, 44, 41], tc=3, abs=4, emap=0, bias=0, fuel=48)
PRESET = Reading(tc=6, abs=6, emap=0, bias=0.75, cold_psi=None, fuel=59.1,
                 air_temp=0, road_temp=0)


def _doc(v):
    return {
        "carName": "mclaren_720s_gt3_evo",
        "basicSetup": {
            "tyres": {"tyreCompound": 0, "tyrePressure": v["press"]},
            "electronics": {"tC1": v["tc"], "tC2": 0, "abs": v["abs"],
                            "eCUMap": v["emap"], "fuelMix": 0},
            "strategy": {"fuel": v["fuel"]},
        },
        "advancedSetup": {"mechanicalBalance": {"brakeBias": v["bias"]}},
    }


def _files(tmp_path, *vals):
    names = ["IMOLA_0", "HONE_7", "HONE_8"]
    out = []
    for name, v in zip(names, vals):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(_doc(v)), encoding="utf-8")
        out.append(file_values(p))
    assert all(out)
    return out


def _r(**kw):
    base = dict(tc=3, abs=4, emap=0, bias=0.64, cold_psi=None, fuel=48.0,
                air_temp=0, road_temp=0)
    base.update(kw)
    return Reading(**base)


def test_the_game_preset_of_0811_is_not_a_saved_file(tmp_path):
    m = match(PRESET, _files(tmp_path, IMOLA_0, HONE_7, HONE_8), carry={},
              bias_offset=None)
    assert m.state == "unsaved" and m.names == ()
    assert "TC 6 invece di 3" in describe(m.diffs[m.best], "it")


def test_three_files_with_the_same_electronics_are_ambiguous_without_pressures(tmp_path):
    m = match(_r(), _files(tmp_path, IMOLA_0, HONE_7, HONE_8), carry={},
              bias_offset=None)
    assert m.state == "ambiguous" and len(m.names) == 3 and m.best is None


def test_cold_pressures_pick_the_probable_file(tmp_path):
    m = match(_r(cold_psi=(25.5, 25.0, 24.7, 24.4)),
              _files(tmp_path, IMOLA_0, HONE_7, HONE_8), carry={}, bias_offset=None)
    assert m.state == "match" and m.best == "HONE_8" and m.probable is True


def test_an_accepted_tc_click_keeps_the_file_recognised(tmp_path):
    files = _files(tmp_path, IMOLA_0)
    m = match(_r(tc=4), files, carry={"tC1": +1}, bias_offset=None)
    assert m.state == "match" and m.names == ("IMOLA_0",) and not m.probable
    assert match(_r(tc=4), files, carry={}, bias_offset=None).state == "unsaved"


def test_bias_counts_only_once_calibrated(tmp_path):
    (f,) = _files(tmp_path, IMOLA_0)
    certain, _ = compare(_r(bias=0.75), f, carry={}, bias_offset=None)
    assert not [d for d in certain if d.field == "bias"]
    certain, _ = compare(_r(bias=0.75), f, carry={}, bias_offset=0.64)
    assert [d.field for d in certain] == ["bias"]
    # un click accettato sposta il valore atteso di 0.002
    certain, _ = compare(_r(bias=0.642), f, carry={"brakeBias": 1}, bias_offset=0.64)
    assert certain == ()


def test_pressures_do_not_decide_while_unverified(tmp_path):
    (f,) = _files(tmp_path, IMOLA_0)
    assert fp.COLD_PSI_VERIFIED is False
    certain, psi = compare(_r(cold_psi=(25.5, 25.5, 25.4, 25.1)), f, carry={},
                           bias_offset=None)
    assert certain == () and [d.field for d in psi] == ["psi_fl"]
    assert describe(psi, "it") == "anteriore sinistra 25,5 psi invece di 26,0 psi"


def test_a_broken_or_ac_file_is_skipped(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{non json", encoding="utf-8")
    ini = tmp_path / "car.ini"
    ini.write_text("[A]\nx=1\n", encoding="utf-8")
    noel = tmp_path / "noel.json"
    noel.write_text(json.dumps({"basicSetup": {"tyres": {}}}), encoding="utf-8")
    assert file_values(bad) is None
    assert file_values(ini) is None
    assert file_values(noel) is None
    assert file_values(tmp_path / "missing.json") is None


def test_changed_sees_tc_and_bias_but_not_a_tenth_of_a_percent():
    assert changed(_r(bias=0.640), _r(bias=0.6405)) == ()
    d = changed(_r(), _r(tc=6, bias=0.75))
    assert [x.field for x in d] == ["tc", "bias"]
    assert describe(d, "it") == "TC 6 invece di 3, ripartitore 75,0 % invece di 64,0 %"
    assert describe(d, "en") == "TC 6 instead of 3, brake bias 75.0 % instead of 64.0 %"
    assert changed(_r(tc=-1), _r(tc=6)) == ()


def test_unknown_when_the_aids_are_not_read(tmp_path):
    m = match(_r(tc=-1), _files(tmp_path, IMOLA_0), carry={}, bias_offset=None)
    assert m.state == "unknown"
    assert match(_r(), [], carry={}, bias_offset=None).state == "unknown"


def test_reading_round_trips_through_dict():
    r = _r(cold_psi=(25.5, 25.0, 24.7, 24.4))
    assert Reading.from_dict(json.loads(json.dumps(r.to_dict()))) == r
    assert FieldDiff("tc", 6, 3).field == "tc"


def test_engine_map_is_worded_as_the_hud_shows_it_but_kept_raw():
    d = changed(_r(emap=2), _r(emap=3))
    assert d == (FieldDiff("emap", 3, 2),)          # i valori restano grezzi
    assert describe(d, "it") == "mappa motore 4 invece di 3"
    assert describe(d, "en") == "engine map 4 instead of 3"


# --- l'osservatore dei box ---------------------------------------------------
import dataclasses

from accoach.engineer.fingerprint import PitWatch
from accoach.telemetry.snapshot import ACStatus, TelemetrySnapshot

_COLD = (26.0, 25.5, 25.4, 25.1)
# Fermo in piazzola su ACC: `in_pit` resta 0 anche li' (coaching/pitcall.py,
# `stopped_in_box`), quindi la sosta e' corsia box a velocita' zero.
_BOX = dict(lane=True, speed=0.0)


def _snap(*, pit=False, lane=False, speed=0.0, psi=(0.0, 0.0, 0.0, 0.0), tc=3,
          status=ACStatus.LIVE, acc=True, connected=True,
          core=(0.0, 0.0, 0.0, 0.0), air=0.0):
    return dataclasses.replace(
        TelemetrySnapshot.disconnected(), connected=connected, status=status,
        is_acc=acc, in_pit=pit, in_pit_lane=lane, speed_kmh=speed,
        tyre_pressure=psi, tc_level=tc, abs_level=4, engine_map=0,
        brake_bias=0.75, fuel=48.0, tyre_core_temp=core, air_temp=air)


def _run(w, snaps):
    return [w.update(s) for s in snaps]


def test_a_stop_in_the_box_gives_cold_pressures_and_an_exit():
    w = PitWatch()
    ev = _run(w, [
        _snap(speed=150, tc=5), _snap(speed=150, tc=4),
        _snap(lane=True, speed=60),
        _snap(psi=_COLD, **_BOX),
        _snap(lane=True, speed=30), _snap(speed=100)])
    assert ev == [None, None, None, "live", None, "exit"]
    assert w.exit.cold_psi == _COLD
    assert w.entry.tc == 4
    assert w.live.cold_psi == _COLD


def test_in_pit_alone_still_counts_as_stopped():
    """Come lo direbbe Assetto Corsa 1: `in_pit` acceso. La regola e' una sola
    (`stopped_in_box`), e la sua prima meta' resta."""
    w = PitWatch()
    ev = _run(w, [_snap(speed=150), _snap(lane=True, speed=60),
                  _snap(pit=True, lane=True, speed=0, psi=_COLD),
                  _snap(lane=True, speed=30), _snap(speed=100)])
    assert ev == [None, None, "live", None, "exit"]
    assert w.exit.cold_psi == _COLD


def test_moving_in_the_pit_lane_is_not_a_stop():
    w = PitWatch()
    ev = _run(w, [_snap(speed=150), _snap(lane=True, speed=60, psi=_COLD),
                  _snap(lane=True, speed=5, psi=_COLD), _snap(speed=100)])
    assert ev == [None, None, None, "exit"]
    assert w.live is None
    assert w.exit.cold_psi is None


def test_a_start_from_the_garage_has_no_entry_and_cold_pressures():
    """La sessione parte gia' ferma ai box: nessuna lettura in pista prima."""
    w = PitWatch()
    ev = _run(w, [_snap(psi=_COLD, **_BOX), _snap(psi=_COLD, **_BOX),
                  _snap(lane=True, speed=40), _snap(speed=120)])
    assert ev == ["live", None, None, "exit"]
    assert w.entry is None
    assert w.exit.cold_psi == _COLD


def test_hot_tyres_in_the_box_are_not_cold_pressures():
    """Una sosta normale a gomme calde: le pressioni lette non sono quelle a
    freddo del file, e non contano. Restano nel registro per il test."""
    w = PitWatch()
    hot = (85.0, 84.0, 80.0, 79.0)
    ev = _run(w, [_snap(speed=150), _snap(lane=True, speed=60),
                  _snap(psi=(27.6, 27.4, 27.1, 27.0), core=hot, air=20.0, **_BOX),
                  _snap(lane=True, speed=30), _snap(speed=100)])
    assert ev == [None, None, "live", None, "exit"]
    assert w.live.cold_psi is None and w.exit.cold_psi is None
    assert w.box_psi == (27.6, 27.4, 27.1, 27.0)
    assert w.box_core_c == 82.0


def test_cold_tyres_are_read_against_the_air():
    w = PitWatch()
    cool = (30.0, 30.0, 29.0, 29.0)               # aria 20: entro 15 gradi
    _run(w, [_snap(speed=150), _snap(psi=_COLD, core=cool, air=20.0, **_BOX)])
    assert w.live.cold_psi == _COLD
    assert w.box_core_c == 29.5
    assert fp.COLD_TYRE_MARGIN_C == 15.0


def test_the_box_values_start_again_at_each_stop():
    w = PitWatch()
    _run(w, [_snap(speed=150), _snap(psi=_COLD, **_BOX), _snap(speed=100)])
    assert w.box_psi == _COLD
    _run(w, [_snap(lane=True, speed=60)])
    assert w.box_psi is None and w.box_core_c is None


def test_live_fires_only_when_something_changes():
    w = PitWatch()
    box = dict(psi=_COLD, **_BOX)
    ev = _run(w, [_snap(speed=100), _snap(**box), _snap(**box), _snap(**box),
                  _snap(tc=6, **box)])
    assert ev == [None, "live", None, None, "live"]


def test_a_pause_in_the_pits_is_not_an_exit():
    w = PitWatch()
    ev = _run(w, [_snap(speed=100),
                  _snap(psi=_COLD, **_BOX),
                  _snap(status=ACStatus.PAUSE),
                  _snap(speed=100)])
    assert "exit" not in ev


def test_assetto_corsa_stays_silent():
    w = PitWatch()
    ev = _run(w, [_snap(acc=False, speed=100),
                  _snap(acc=False, pit=True, lane=True, psi=_COLD),
                  _snap(acc=False, speed=100)])
    assert ev == [None, None, None]
    assert w.live is None and w.exit is None
