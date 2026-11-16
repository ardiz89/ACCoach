"""Lo scarto del ripartitore misurato sull'archivio vale come una prima risposta.

Fino al 16/11 il ripartitore entrava nell'impronta solo dopo una risposta del
pilota sulla pagina. Per la 720S l'archivio lo dice gia': i giri registrano il
ripartitore letto dal gioco, i file i click, e tre valori diversi di click
stanno sulla stessa retta (vedi `fingerprint.MEASURED_BIAS_OFFSET`). Non e' un
file «compatibile» scelto in silenzio (la regola di `learn_bias` resta): e' una
misura per auto, e una risposta che non concorda la butta come farebbe con la
prima risposta del pilota.
"""
import pytest

from accoach.engineer.factory import engineer_for
from accoach.engineer.fingerprint import BIAS_STEP, BIAS_TOL, MEASURED_BIAS_OFFSET

CAR = "mclaren_720s_gt3_evo"


def test_the_720s_on_acc_starts_with_the_measured_offset():
    eng = engineer_for(CAR, "Imola", is_acc=True)
    assert eng.bias_offset == pytest.approx(0.64)
    assert eng.bias_pending is None


@pytest.mark.parametrize("car,is_acc", [
    ("ferrari_296_gt3", True),     # nessuna misura per quest'auto
    (CAR, None),                   # gioco non detto: l'Ingegnere prudente
    (CAR, False),                  # non e' ACC: i click non sono quelli
])
def test_without_a_measure_the_offset_waits_for_the_driver(car, is_acc):
    eng = engineer_for(car, "Imola", is_acc=is_acc)
    assert eng.bias_offset is None


@pytest.mark.parametrize("clicks,seen", [
    (0, 0.64),     # Imola, 720sEVO_Imola_0 / HONE_7 / HONE_8 (08/11, 14/11)
    (15, 0.67),    # Brands Hatch, setup_q_720evo / HONE_2 (23/08, 25/10)
    (55, 0.75),    # il predefinito del gioco (def.json, prova-base)
])
def test_the_measured_offset_explains_the_archive(clicks, seen):
    assert abs(MEASURED_BIAS_OFFSET[CAR] + BIAS_STEP * clicks - seen) <= BIAS_TOL


def test_an_old_state_without_answers_keeps_the_measure():
    for state in ({}, {"bias_offset": None, "bias_pending": None}):
        eng = engineer_for(CAR, "Imola", is_acc=True)
        eng.restore(state)
        assert eng.bias_offset == pytest.approx(0.64)


def test_a_disagreeing_answer_drops_the_measure_and_a_restart_keeps_it_dropped():
    eng = engineer_for(CAR, "Imola", is_acc=True)
    eng.learn_bias(0.70, 0)                  # non concorda con 0,64
    assert eng.bias_offset is None
    assert eng.bias_pending == pytest.approx(0.70)
    again = engineer_for(CAR, "Imola", is_acc=True)
    again.restore(eng.state())
    assert again.bias_offset is None
    assert again.bias_pending == pytest.approx(0.70)


def test_an_answer_learned_on_disk_beats_the_measure():
    eng = engineer_for(CAR, "Imola", is_acc=True)
    eng.restore({"bias_offset": 0.66, "bias_pending": None})
    assert eng.bias_offset == pytest.approx(0.66)
