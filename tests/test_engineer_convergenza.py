"""Il verso della convergenza, misurato nel garage il 23/10.

ACC, McLaren 720S GT3 a Spa: il tasto > sulla convergenza anteriore porta
−0,12° a −0,11° (meno toe-out), sulla posteriore +0,12° a +0,13° (piu' toe-in).
Un file scritto da HONE con un click in piu' davanti si e' caricato a −0,11°:
il click del file e' il click del garage. Il rimedio del sottosterzo in ingresso
era +1, «aumenta il toe-out», e faceva il contrario.

Assetto Corsa, SF25 a Spa: dieci click in piu' davanti portano la convergenza
dal vivo da 0,19 a 0,12, dieci dietro da −0,02 a +0,02. Lo stesso tasto va in
versi opposti sui due assi: nel file la convergenza e' la lunghezza del braccio
dello sterzo, e dove sta il braccio lo decide la sospensione di ogni auto. Li'
il verso di un click non lo sappiamo, e quello che non sappiamo non si scrive.
"""
import pytest

from accoach.engineer import (
    Balance,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
)
from accoach.engineer.core import Profile
from accoach.engineer.profiles import FORMULA_PROFILE, GT3_PROFILE, ROAD_PROFILE
from accoach.engineer.profiles._common import remedy
from accoach.engineer.steps import AccSteps, AcSteps
from accoach.engineer.voice_levers import voice_lever

U_ENTRY = Symptom(Balance.UNDERSTEER, Phase.ENTRY, Speed.LOW)

_PROFILES = [GT3_PROFILE, FORMULA_PROFILE, ROAD_PROFILE]

# Un'auto di AC che dichiara il passo della convergenza su tutte e quattro le
# ruote: anche cosi' il verso di un click resta ignoto.
CAR_INI = """
[TOE_OUT_LF]
SHOW_CLICKS=0
MIN=0
MAX=40
STEP=1
[TOE_OUT_RF]
SHOW_CLICKS=0
STEP=1
[TOE_OUT_LR]
SHOW_CLICKS=0
STEP=1
[TOE_OUT_RR]
SHOW_CLICKS=0
STEP=1
[ARB_FRONT]
SHOW_CLICKS=0
STEP=200
"""


@pytest.fixture
def ac_car(tmp_path, monkeypatch):
    from accoach.setup import ac_steps
    cars = tmp_path / "cars"
    folder = cars / "prova"
    (folder / "data").mkdir(parents=True)
    (folder / "data" / "setup.ini").write_text(CAR_INI, encoding="utf-8")
    monkeypatch.setattr(ac_steps, "cars_dir", lambda: cars)
    return "prova"


def _toe_remedies(profile):
    for builders in profile.remedy_table.values():
        for build in builders:
            change = build(U_ENTRY, profile.phases[0])
            if change.changes and change.changes[0].param == "toe":
                yield change


@pytest.mark.parametrize("profile", _PROFILES, ids=lambda p: p.name)
def test_il_toe_out_anteriore_si_aggiunge_togliendo_un_click(profile):
    front = [c for c in _toe_remedies(profile) if c.changes[0].slot in (0, 1)]
    assert front, "il profilo propone la convergenza anteriore"
    for change in front:
        assert {a.delta_clicks for a in change.changes} == {-1}
        assert voice_lever(change) == "Aumenta il toe-out anteriore."


@pytest.mark.parametrize("profile", _PROFILES, ids=lambda p: p.name)
def test_il_toe_in_posteriore_resta_un_click_in_piu(profile):
    for change in _toe_remedies(profile):
        if change.changes[0].slot in (2, 3):
            assert {a.delta_clicks for a in change.changes} == {+1}
            assert voice_lever(change) == "Aumenta il toe-in posteriore."


def test_su_acc_la_convergenza_si_scrive():
    assert AccSteps().units("toe", 0) == 1
    assert AccSteps().units("toe", 3) == 1


@pytest.mark.parametrize("slot", [0, 1, 2, 3])
def test_su_ac_la_convergenza_non_si_scrive_neanche_se_l_auto_dichiara_il_passo(
        ac_car, slot):
    steps = AcSteps(ac_car)
    assert steps.units("aRBFront", None) is not None     # l'auto e' leggibile
    assert steps.units("toe", slot) is None


def _lap():
    return LapStats(lap_time_ms=100000,
                    symptom_scores={U_ENTRY: 0.6},
                    symptom_corners={U_ENTRY: 4})


def test_su_ac_la_convergenza_si_salta_e_si_prova_la_leva_dopo(ac_car):
    phase = ROAD_PROFILE.phases[1]
    table = {U_ENTRY: [
        remedy("toe", "front", -1, "The car understeers on entry, so add 1 click of front toe-out."),
        remedy("aRBFront", None, -1, "The car understeers on entry, so soften the front anti-roll bar by 1 click."),
    ]}
    eng = RaceEngineer(Profile("x", [phase], table), steps=AcSteps(ac_car))
    d = next(d for d in (eng.observe(_lap()) for _ in range(5))
             if d.kind is DecisionKind.PROPOSE)
    assert d.change.param == "aRBFront"


@pytest.mark.parametrize("lang, word", [("it", "sospensione di ogni auto"),
                                        ("en", "suspension")])
def test_su_ac_il_perche_e_la_geometria_non_un_passo_mancante(
        ac_car, monkeypatch, lang, word):
    from accoach import i18n
    monkeypatch.setattr(i18n, "current_language", lambda: lang)
    import accoach.engineer.core as core
    monkeypatch.setattr(core, "current_language", lambda: lang)
    phase = ROAD_PROFILE.phases[1]
    table = {U_ENTRY: [
        remedy("toe", "front", -1, "The car understeers on entry, so add 1 click of front toe-out."),
    ]}
    eng = RaceEngineer(Profile("x", [phase], table), steps=AcSteps(ac_car))
    said = [d for d in (eng.observe(_lap()) for _ in range(6))
            if d.kind is DecisionKind.STAND_DOWN]
    assert len(said) == 1
    assert word in said[0].message
