"""Gli errori frequenti di una sessione: bloccaggi, pattinamenti, sotto/sovrasterzo, uscite."""
from accoach.coaching.errors import ERRORS, lap_errors, session_errors
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType
from accoach.track import detect_corners

import synth

_PRESS = (27.0, 27.0, 27.5, 27.5)


def _lap(samples, clean=True):
    return Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
               samples=samples, clean=clean)


def _lock_frame(pos=0.10, slip=-1.0):
    # Stesso profilo del test del 'bloccaggio vero' in test_diagnosis: ABS che
    # lavora e ruota anteriore ferma.
    return LapSample(0, pos, 200.0, 0.0, 0.9, 0.0, "4", 7000, 0.0, -1.0,
                     abs_active=0.6, slip_ratio=(slip, slip, 0.0, 0.0),
                     tyre_pressure=_PRESS)


def _with_yaw(lap, ratio, same_sign=False):
    sign = 1.0 if same_sign else -1.0
    for s in lap.samples:
        s.yaw_rate = sign * ratio * s.steer_angle
    return lap


def test_un_bloccaggio_chiaro_conta_uno():
    assert lap_errors(_lap([_lock_frame()]), [])["lock"] == 1


def test_lo_stesso_giro_senza_bloccaggio_conta_zero():
    assert lap_errors(_lap([_lock_frame(slip=-0.08)]), [])["lock"] == 0


def test_pattinamento_in_uscita_conta():
    spin = LapSample(1000, 0.60, 120.0, 1.0, 0.0, 0.0, "3", 7000, 0.0, 0.5,
                     slip_ratio=(0.0, 0.0, 0.25, 0.25), tyre_pressure=_PRESS)
    assert lap_errors(_lap([spin]), [])["spin"] == 1


def test_trazione_che_tiene_non_e_pattinamento():
    # Sotto la soglia della classe (GT3: 0.13) e' trazione, non pattinamento.
    ok = LapSample(1000, 0.60, 120.0, 1.0, 0.0, 0.0, "3", 7000, 0.0, 0.5,
                   slip_ratio=(0.0, 0.0, 0.08, 0.08), tyre_pressure=_PRESS)
    assert lap_errors(_lap([ok]), [])["spin"] == 0


def test_giro_non_pulito_conta_un_fuori():
    assert lap_errors(_lap([_lock_frame()], clean=False), [])["off"] == 1
    assert lap_errors(_lap([_lock_frame()], clean=True), [])["off"] == 0
    assert lap_errors(_lap([_lock_frame()], clean=None), [])["off"] == 0   # ignoto != tagliato


def test_sotto_e_sovrasterzo_contano_le_curve():
    under = _with_yaw(synth.build_lap(n=300, clean=True), ratio=0.3)
    e = lap_errors(under, detect_corners(under.samples))
    assert e["understeer"] >= 1 and e["oversteer"] == 0
    over = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.5, same_sign=True)
    e = lap_errors(over, detect_corners(over.samples))
    assert e["oversteer"] >= 1
    neutral = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.9)
    e = lap_errors(neutral, detect_corners(neutral.samples))
    assert e["understeer"] == 0 and e["oversteer"] == 0


def test_una_curva_conta_una_volta_anche_con_piu_sintomi():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=0.3)
    corners = detect_corners(lap.samples)
    assert lap_errors(lap, corners)["understeer"] <= len(corners)


def test_le_chiavi_sono_sempre_tutte():
    assert tuple(lap_errors(_lap([_lock_frame()]), [])) == ERRORS


def test_sessione_somma_filtra_e_ordina():
    assert session_errors([{"lock": 2, "off": 0}, {"lock": 1, "off": 1}]) == [("lock", 3), ("off", 1)]
    assert session_errors([{"off": 1}, {"off": 1, "spin": 5}]) == [("spin", 5), ("off", 2)]
    assert session_errors([]) == []
