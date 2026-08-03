"""TyreTempAdvisor: overdriving / temperature-window advice."""
from dataclasses import replace

from accoach.coaching.tyretemp import TyreTempAdvisor, _COOLDOWN_LAPS
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

# `is_acc=True`: la finestra 80 °C è quella della GT3 di ACC, e fuori da lì il
# detector tace apposta — tutti e 18 i cue di temperatura dell'archivio uscivano
# da giri AC, cioè solo dove la finestra non vale.
_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    max_rpm=8000, is_acc=True,
)
_FRAMES = 50


def _drive_lap(adv, temp, now=0.0, speed=160.0):
    out = []
    for i in range(_FRAMES):
        s = replace(_BASE, lap_position=i / _FRAMES + 0.001,
                    tyre_core_temp=(temp,) * 4, speed_kmh=speed)
        out += adv.update(s, now)
        now += 0.05
    s = replace(_BASE, lap_position=0.01, tyre_core_temp=(temp,) * 4, speed_kmh=speed)
    out += adv.update(s, now)
    return out, now + 0.05


def test_hot_tyres_overdriving():
    adv = TyreTempAdvisor()
    out, _ = _drive_lap(adv, 98.0)
    assert len(out) == 1 and out[0].category is CueCategory.TYRE_TEMP
    assert "troppo calde" in out[0].message


def test_cold_tyres():
    adv = TyreTempAdvisor()
    out, _ = _drive_lap(adv, 62.0)
    assert len(out) == 1 and "fredde" in out[0].message


def test_in_window_silent():
    adv = TyreTempAdvisor()
    out, _ = _drive_lap(adv, 82.0)
    assert out == []


def test_cooldown():
    adv = TyreTempAdvisor()
    out, now = _drive_lap(adv, 98.0)
    assert len(out) == 1
    for _ in range(_COOLDOWN_LAPS - 1):
        out, now = _drive_lap(adv, 98.0, now)
        assert out == []
    out, now = _drive_lap(adv, 98.0, now)
    assert len(out) == 1


# --- la finestra vale dov'è stata misurata, e altrove si tace ---------------
#
# 80 °C è la GT3 di ACC all'asciutto. Il dato che condanna la versione senza
# gate: **tutti e 18** i cue di temperatura dell'archivio uscivano da giri AC,
# **zero** da giri ACC — cioè il detector parlava solo dove la sua finestra non
# vale. Su ACC, dove il numero è nato, legge 79-81 °C e sta correttamente zitto.

def _advisor_for(cls):
    adv = TyreTempAdvisor()
    adv.set_car_class(cls)
    return adv


def test_a_formula_car_running_hot_is_not_accused_of_overdriving():
    """La SF25 gira a 90 °C e si sentiva dire «stai forzando» undici volte."""
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.FORMULA)
    out = _drive_lap(adv, 93.0)[0] + _drive_lap(adv, 93.0, now=10.0)[0]
    assert not out


def test_a_road_car_on_semislicks_is_not_told_its_tyres_are_cold():
    """La M3 E92 a 66 °C: era il suo passo, e il cue arrivava sui suoi giri più
    veloci."""
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.ROAD)
    out = _drive_lap(adv, 66.0)[0] + _drive_lap(adv, 66.0, now=10.0)[0]
    assert not out


def test_a_gt3_on_acc_still_gets_the_advice():
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.GT3)
    out, _ = _drive_lap(adv, 96.0)
    assert any(c.category is CueCategory.TYRE_TEMP for c in out)


def test_a_gt3_mod_on_ac_is_not_judged_by_accs_window():
    """Il M4 GT3 mod su AC è classe GT3 e legge 62 °C: il modello gomme del mod
    non è quello su cui 80 °C è stato misurato."""
    from accoach.engineer import CarClass

    adv = _advisor_for(CarClass.GT3)
    out = []
    for lap_no in range(2):
        for i in range(_FRAMES):
            s = replace(_BASE, lap_position=i / _FRAMES + 0.001,
                        tyre_core_temp=(62.0,) * 4, speed_kmh=160.0,
                        is_acc=False)
            out += adv.update(s, lap_no * 10.0)
    assert not out
