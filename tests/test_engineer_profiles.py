"""engineer profiles: classmap + Formula and Road class-specific behaviour."""
from accoach.engineer import (
    Balance,
    CarClass,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
    classify,
    profile_for,
    profile_for_car,
)
from accoach.engineer.profiles import FORMULA_PROFILE, GT3_PROFILE, ROAD_PROFILE

U, O = Balance.UNDERSTEER, Balance.OVERSTEER
EN, AP, EX = Phase.ENTRY, Phase.APEX, Phase.EXIT
LO, HI = Speed.LOW, Speed.HIGH


def _lap(symptom=None, score=0.0, time_ms=100000, press=None, corners=4):
    return LapStats(lap_time_ms=time_ms,
                    symptom_scores={symptom: score} if symptom else {},
                    symptom_corners={symptom: corners} if symptom else {},
                    pressures_hot=press)


def _propose(eng, symptom, score, press=None):
    for _ in range(10):
        d = eng.observe(_lap(symptom, score, press=press))
        if d.kind is DecisionKind.PROPOSE:
            return d
    raise AssertionError("no proposal reached")


# --- classmap -------------------------------------------------------------

def test_classify_gt3():
    assert classify("mclaren_720s_gt3_evo") is CarClass.GT3
    assert classify("bmw_z4_gt3") is CarClass.GT3
    assert classify("ferrari_488_gt4") is CarClass.GT3       # GT classes ride along


def test_classify_formula():
    assert classify("f1_1990_mclaren") is CarClass.FORMULA
    assert classify("ferrari_312t") is CarClass.FORMULA      # override (no marker)
    assert classify("rss_formula_hybrid") is CarClass.FORMULA


def test_classify_road_is_default():
    assert classify("abarth500") is CarClass.ROAD
    assert classify("dodge_char_police") is CarClass.ROAD
    assert classify("") is CarClass.ROAD


def test_profile_for_car():
    assert profile_for_car("mclaren_720s_gt3_evo") is GT3_PROFILE
    assert profile_for_car("f1_1990_mclaren") is FORMULA_PROFILE
    assert profile_for_car("bmw_m3_e30") is ROAD_PROFILE
    assert profile_for(CarClass.FORMULA) is FORMULA_PROFILE


# --- Formula: aero-first, no TC -------------------------------------------

def test_formula_phase_order_is_aero_first():
    keys = [p.key for p in FORMULA_PROFILE.phases]
    assert keys.index("aero") < keys.index("mechanical")


def test_formula_high_speed_understeer_uses_front_wing():
    eng = RaceEngineer(FORMULA_PROFILE, min_stable=3)
    d = _propose(eng, Symptom(U, AP, HI), 0.6)
    assert eng.phase.key == "aero"
    assert d.change.changes[0].param == "frontWing"


def test_formula_exit_oversteer_never_uses_tc():
    # No electronic aids: the traction fix is the differential, not TC.
    eng = RaceEngineer(FORMULA_PROFILE, min_stable=3)
    d = _propose(eng, Symptom(O, EX, LO), 0.6)
    params = {c.param for c in d.change.changes}
    assert "tC1" not in params
    assert d.change.changes[0].param == "diffPower"


# --- Road: collapsed speed axis, no aids, lift-off oversteer --------------

def test_road_has_no_aero_phase():
    keys = [p.key for p in ROAD_PROFILE.phases]
    assert "aero" not in keys
    assert keys[0] == "pressures"


def test_road_same_remedy_low_and_high_speed():
    lo = _first_param(Symptom(O, EN, LO))
    hi = _first_param(Symptom(O, EN, HI))
    assert lo == hi == "toe"                 # lift-off fix, speed-independent


def _first_param(symptom):
    eng = RaceEngineer(ROAD_PROFILE, min_stable=3)
    d = _propose(eng, symptom, 0.6)
    return d.change.changes[0].param


def test_road_never_proposes_tc():
    eng = RaceEngineer(ROAD_PROFILE, min_stable=3)
    d = _propose(eng, Symptom(O, EX, HI), 0.6)
    assert all(c.param != "tC1" for c in d.change.changes)


def test_all_profiles_have_al_volo():
    for prof in (GT3_PROFILE, FORMULA_PROFILE, ROAD_PROFILE):
        assert prof.al_volo
        assert "Brake bias" in prof.al_volo


def test_engineer_for_sets_class_and_pressure_window():
    from accoach.engineer import engineer_for, pressure_window
    eng = engineer_for("f1_1990_mclaren")
    assert eng.profile is FORMULA_PROFILE
    # the formula pressure window (22.0/0.4) is applied to the pressure phase
    pp = eng.phases[0]
    assert (pp.target, pp.tol) == pressure_window("f1_1990_mclaren") == (22.0, 0.4)
    # road and gt3 differ
    assert pressure_window("dodge_char_police")[0] == 30.0
    assert pressure_window("mclaren_720s_gt3_evo") == (27.5, 0.7)


# --- una modifica di pressione dice dove arriva, non dove vorrebbe ---------
#
# Misurato in pista il 14/08: anteriori a 24.7 psi, finestra GT3 ~27.5. Il passo
# vale al massimo 8 click — 0.8 psi — quindi quel passo porta a 25.5, e servono
# tre passaggi ai box. Il messaggio pero' diceva «24.7→~27.5 psi: +8 click»:
# prometteva il bersaglio finale e consegnava un decimo di strada, e il pilota
# che ricarica il setup e rimisura non ha modo di sapere se e' andata come
# doveva o se qualcosa non ha funzionato.

def _press_change(cur, target=27.5, tol=0.7):
    from accoach.engineer.profiles._common import PressurePhase
    ph = PressurePhase(target, tol)
    return ph.pressure_remedy(_lap(press={"front": cur, "rear": target}))


def test_a_clamped_pressure_step_says_the_pressure_it_actually_reaches():
    ch = _press_change(24.7)
    assert ch is not None
    assert "+8" in ch.rationale
    assert "25.5" in ch.rationale, "la pressione a cui arriva questo passo"
    assert "27.5" in ch.rationale, "…e la finestra, che resta il bersaglio"


def test_a_step_that_reaches_the_window_does_not_promise_a_second_trip():
    """Quando il passo ci arriva davvero, la frase non deve crescere: la nota
    sul passaggio in piu' esiste solo perche' qualche volta serve."""
    full = _press_change(26.75)
    clamped = _press_change(24.7)
    assert full is not None and len(full.rationale) < len(clamped.rationale)


def test_the_step_is_capped_the_same_way_in_both_directions():
    """Sopra la finestra il taglio vale identico, e la frase pure: una pressione
    troppo alta e' lo stesso problema visto dall'altro lato."""
    ch = _press_change(30.0)
    assert ch is not None and "-8" in ch.rationale and "29.2" in ch.rationale


def test_the_italian_message_names_the_axle_in_italian(monkeypatch):
    """«Pressione front» era meta' tradotta, nell'unico punto dell'app dove il
    pilota legge un numero e poi va a girare una manopola."""
    from accoach.engineer.profiles import _common
    monkeypatch.setattr(_common, "current_language", lambda: "it")
    ph = _common.PressurePhase(27.5, 0.7)
    front = ph.pressure_remedy(_lap(press={"front": 24.7, "rear": 27.5})).rationale
    rear = ph.pressure_remedy(_lap(press={"front": 27.5, "rear": 24.7})).rationale
    assert "anteriore" in front and "front" not in front
    assert "posteriore" in rear and "rear" not in rear
