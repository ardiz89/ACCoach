"""PressureAdvisor: lap-aggregated hot-pressure advice."""
from dataclasses import replace

from accoach.coaching.pressure import PressureAdvisor, _COOLDOWN_LAPS
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

# `is_acc=True` non è decorazione: la finestra 27.5 psi è stata misurata su una
# GT3 di ACC, e fuori da lì il consiglio tace apposta (vedi coaching/tuning.py).
# Questi test descrivono proprio quel caso, quindi il titolo va detto.
_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=180.0, is_acc=True,
)
_FRAMES = 50   # comfortably above PressureAdvisor._MIN_SAMPLES


def _snap(pos, press, temp=85.0, speed=180.0, in_pit=False):
    return replace(_BASE, lap_position=pos, tyre_pressure=press,
                   tyre_core_temp=(temp,) * 4, speed_kmh=speed, in_pit=in_pit)


def _drive_lap(adv, press, now=0.0, temp=85.0, speed=180.0):
    out = []
    for i in range(_FRAMES):
        out += adv.update(_snap(i / _FRAMES + 0.001, press, temp, speed), now)
        now += 0.05
    out += adv.update(_snap(0.01, press, temp, speed), now)
    return out, now


def test_high_fronts():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (29.2, 29.0, 27.4, 27.5))
    assert len(out) == 1 and out[0].category is CueCategory.TYRE_PRESSURE
    assert "anteriori" in out[0].message and "troppo alte" in out[0].message
    assert "1.6 psi" in out[0].message


def test_low_rears():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (27.5, 27.4, 26.0, 26.2))
    assert len(out) == 1 and "posteriori" in out[0].message
    assert "troppo basse" in out[0].message


def test_in_window_silent():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (27.5, 27.6, 27.4, 27.3))
    assert out == []


def test_cold_tyres_silent():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (24.0, 24.1, 24.0, 23.9), temp=30.0)
    assert out == []


def test_under_temp_tyres_silent():
    # Tyres warming but not yet at operating temp (68 C): pressure reads low, but
    # advising "+pressure" here would be wrong — it comes up once hot. Stay quiet.
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (24.5, 24.6, 24.4, 24.5), temp=68.0)
    assert out == []


def test_picks_worst_axle():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (28.9, 28.9, 24.5, 24.5))
    assert "posteriori" in out[0].message


def test_pit_lap_silent():
    adv = PressureAdvisor()
    now = 0.0
    for i in range(_FRAMES):
        adv.update(_snap(i / _FRAMES + 0.001, (29.5,) * 4, in_pit=True), now)
        now += 0.05
    out = adv.update(_snap(0.01, (29.5,) * 4, in_pit=True), now)
    assert out == []


def test_cooldown():
    adv = PressureAdvisor()
    p = (29.2, 29.0, 27.4, 27.5)
    out, now = _drive_lap(adv, p)
    assert len(out) == 1
    for _ in range(_COOLDOWN_LAPS - 1):
        out, now = _drive_lap(adv, p, now)
        assert out == []
    out, now = _drive_lap(adv, p, now)
    assert len(out) == 1


def test_slow_lap_no_samples():
    adv = PressureAdvisor()
    out, _ = _drive_lap(adv, (29.2, 29.0, 27.4, 27.5), speed=40.0)
    assert out == []


# --- la finestra vale dov'è stata misurata, e altrove si tace ---------------
#
# 27.5 psi è la GT3 di ACC all'asciutto. Applicata altrove non è una stima
# approssimativa: è un'altra auto. Misurato sui giri d'archivio il 03/08 —
# la SF25 gira a 12.9 psi e si sentiva dire «alza 14.6 psi»; la BMW M3 E92 a
# 34.7, che è la sua pressione di progetto, «cala 7.2». Rigiocando l'archivio
# col gate: ACC GT3 24 cue → 24, tutto il resto 27 → 0.

def _advisor_for(cls):
    from accoach.coaching.pressure import PressureAdvisor as P
    adv = P()
    adv.set_car_class(cls)
    return adv


def test_a_formula_car_is_not_told_to_double_its_pressures():
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.FORMULA)
    out, now = _drive_lap(adv, (13.0,) * 4, temp=90.0)
    more, _ = _drive_lap(adv, (13.0,) * 4, now=now, temp=90.0)
    assert not out + more


def test_a_road_car_at_its_own_design_pressure_is_left_alone():
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.ROAD)
    out, now = _drive_lap(adv, (34.7,) * 4, temp=85.0)
    more, _ = _drive_lap(adv, (34.7,) * 4, now=now, temp=85.0)
    assert not out + more


def test_a_gt3_on_acc_still_gets_the_advice():
    """Il gate deve togliere i falsi positivi e **non** il consiglio che
    funziona: 26 psi su un 720S è la cosa che vale la pena sentirsi dire."""
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.GT3)
    out, _ = _drive_lap(adv, (26.0,) * 4)
    assert any(c.category is CueCategory.TYRE_PRESSURE for c in out)
    assert "1.5 psi" in out[0].message, "e con la correzione giusta"


def test_a_gt3_mod_on_ac_is_not_judged_by_accs_window():
    """La classe non basta: il M4 GT3 **mod su AC** è classe GT3 e legge 63 °C
    di gomma — il modello del mod non è quello su cui 27.5 psi è stato
    misurato."""
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.GT3)
    ac = lambda *a, **k: replace(_snap(*a, **k), is_acc=False)   # noqa: E731
    out = []
    for lap_no in range(2):
        for i in range(_FRAMES):
            out += adv.update(ac(i / _FRAMES + 0.001, (22.0,) * 4), lap_no * 10.0)
    assert not out
