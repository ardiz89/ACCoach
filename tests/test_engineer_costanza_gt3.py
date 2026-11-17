"""L'interruttore della costanza: acceso solo per le GT3."""

import pytest

from accoach.engineer import consistency
from accoach.engineer.classmap import is_gt3
from accoach.engineer.core import RaceEngineer
from accoach.engineer.factory import engineer_for
from accoach.engineer.profiles import GT3_PROFILE


@pytest.mark.parametrize("car", [
    "mclaren_720s_gt3_evo", "ferrari_296_gt3", "porsche_992_gt3_r",
])
def test_gt3_vere_accese(car):
    assert is_gt3(car) is True


@pytest.mark.parametrize("car", [
    "mclaren_570s_gt4", "bmw_m4_gt4", "ks_porsche_911_gt2_rs", "ford_gt_gte",
    "ks_ferrari_sf15t", "ks_mazda_mx5_cup", "sconosciuta", "",
    # GT3 che known_class non riconosce: resta spenta, vale solo il nome certo.
    "audi_r8_lms_evo_ii",
    # Monomarca Cup: "gt3" nel nome, ma non sono GT3.
    "porsche_991ii_gt3_cup", "porsche_992_gt3_cup", "ks_porsche_911_gt3_cup_2017",
])
def test_le_altre_restano_spente(car):
    assert is_gt3(car) is False


def test_engineer_for_passa_la_soglia_misurata():
    eng = engineer_for("mclaren_720s_gt3_evo", "Imola", is_acc=True)
    assert eng.consistency_kmh == consistency.KMH == 5.0


@pytest.mark.parametrize("car", ["mclaren_570s_gt4", "ks_ferrari_sf15t"])
def test_engineer_for_spento_fuori_dalle_gt3(car):
    assert engineer_for(car, "Imola", is_acc=True).consistency_kmh is None


def test_costruito_a_mano_e_spento():
    assert RaceEngineer(GT3_PROFILE).consistency_kmh is None


def test_le_cup_restano_gt3_per_il_profilo():
    # Si esclude solo dalla costanza: il profilo dell'Ingegnere resta quello.
    from accoach.engineer.classmap import CarClass, known_class
    assert known_class("porsche_992_gt3_cup") is CarClass.GT3
