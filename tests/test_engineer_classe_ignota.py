"""Un'auto che il nome non dice cos'e' non riceve la finestra gomme di un'altra.

Riprodotto il 12/10 sulle cartelle setup vere del pilota, e riguardato il 13/10
su tutte le 249 auto installate, col ``ui_car.json`` del gioco a fare da
controprova: la classe usciva da pezzi di nome, e chi non ne aveva nessuno era
«stradale» — 30.0 ±1.5 psi. Ci finivano dentro le F1 (``ks_ferrari_f2004``,
tutta la griglia ``gp_2000_*``), le LMP1 (``ks_toyota_ts040``), una GT3 vera
(``ks_audi_r8_lms``) e la ``lamborghini_huracan_st`` di ACC. Al contrario
``ks_ford_gt40`` era GT3 perche' ``gt40`` contiene ``gt4``, la McLaren F1 GTR
era una monoposto perche' contiene ``_f1``, e tre stradali erano GT3 perche'
il loro allestimento si chiama cosi' (``911 GT3 RS``, ``Cayman GT4``,
``Evora GTE``).

Aggiungere nomi all'elenco non chiude il difetto: le auto di AC sono mod, e la
prossima non la conosciamo. Lo chiude il default: se il nome non lo dice, **non
lo sappiamo**, e sulle pressioni l'Ingegnere tace.
"""
import pytest

from accoach.coaching.tuning import tuning_for_car, tuning_for_class
from accoach.engineer import CarClass, DecisionKind, LapStats, classify, engineer_for
from accoach.engineer.classmap import known_class
from accoach.engineer.pressures import pressure_window, wet_pressure_window

# Ogni nome qui sotto e' una cartella vera: di un'auto installata, di un setup
# del pilota o di un giro in archivio. Nessuno e' inventato per far tornare un
# test, e la colonna «cos'e'» viene dal ui_car.json del gioco, non da me.
NON_SI_SA = [
    "lamborghini_huracan_st",        # ACC, monomarca: era Road, finestra 30 psi
    "ks_lamborghini_huracan_st",     # lo stesso su AC
    "ks_toyota_ts040",               # LMP1
    "ks_porsche_919_hybrid_2016",    # LMP1
    "ks_audi_r8_lms",                # una GT3 senza «gt3» nel nome
    "ks_ford_gt40",                  # «gt40» contiene «gt4»: era GT3
    "ks_mclaren_f1_gtr",             # contiene «_f1»: era Formula, e' una GT1
    "ks_porsche_911_gt1",
    "ks_ferrari_312_67",             # F1 del 1967: senza ali, non e' la SF25
    "bmw_m3_e92",                    # stradale davvero — ma il nome non lo dice
    "abarth500",
    "",
]


@pytest.mark.parametrize("car", NON_SI_SA)
def test_un_auto_che_il_nome_non_dice_cos_e_non_ha_una_finestra(car):
    assert known_class(car) is None
    assert pressure_window(car) is None
    assert wet_pressure_window(car) is None


@pytest.mark.parametrize("car", [
    "ks_porsche_911_gt3_rs",         # ui_car.json: class=street
    "ks_porsche_cayman_gt4_std",     # class=street
    "lotus_evora_gte",               # class=street: GTE e' l'allestimento
    "lotus_evora_gte_carbon",
])
def test_una_stradale_che_si_chiama_come_una_categoria_non_ne_prende_la_finestra(car):
    assert known_class(car) is None, "gomme stradali, non la slick da 27.5 psi"
    assert pressure_window(car) is None


@pytest.mark.parametrize("car", [
    "ks_ferrari_f2004", "ks_ferrari_sf15t", "ks_ferrari_sf70h", "ks_ferrari_f138",
    "gp_2000_f2000", "gp_2000_mp4_15", "gp_2025_sf25",
    "vrc_1988_mclaren_mp4-4_r04", "f1_1990_mclaren", "ferrari_312t", "lotus_98t",
    "rss_formula_hybrid", "tatuusfa1", "lotus_exos_125_s1",
])
def test_una_formula_uno_e_una_formula(car):
    assert known_class(car) is CarClass.FORMULA


@pytest.mark.parametrize("car", [
    "mclaren_720s_gt3_evo", "ferrari_488_gt3_evo", "bmw_m4_gt3_acc",
    "ks_ferrari_488_gt3", "ks_porsche_911_gt3_r_2016", "bmw_z4_gt3",
    "ferrari_488_gt4", "ferrari_458_gt2", "ks_maserati_gt_mc_gt4",
    "McLaren_720S_GT3_Evo",
    "mclaren-720s-gt3-evo",          # com'e' scritta nei nomi dei file dei giri
])
def test_una_gt_che_lo_dice_nel_nome_resta_una_gt(car):
    """La meta' di controllo: la prudenza non deve aver zittito l'auto su cui
    la finestra e' stata misurata."""
    assert known_class(car) is CarClass.GT3
    assert pressure_window(car) == (26.5, 0.5)


# --- cosa fa l'Ingegnere ---------------------------------------------------

def _laps(eng, n, front, rear):
    return [eng.observe(LapStats(lap_time_ms=100000,
                                 pressures_hot={"front": front, "rear": rear}))
            for _ in range(n)]


@pytest.mark.parametrize("car", ["lamborghini_huracan_st", "ks_toyota_ts040",
                                 "ks_ford_gt40"])
def test_su_un_auto_ignota_l_ingegnere_non_tocca_le_pressioni(car):
    """La Huracan ST su ACC a 27.0 psi: con la finestra «stradale» l'Ingegnere
    proponeva +8 click per portarla verso 30. Adesso dice perche' non lo fa,
    una volta, e passa oltre."""
    eng = engineer_for(car, "monza", is_acc=True)
    decisions = _laps(eng, 6, 27.0, 27.0)
    assert all(d.change is None for d in decisions), "nessuna proposta"
    said = [d for d in decisions if d.kind is DecisionKind.STAND_DOWN]
    assert len(said) == 1 and "27.0" not in said[0].message
    assert "window" in said[0].message
    assert eng.phase is None or eng.phase.key != "pressures"


def test_una_fase_senza_finestra_non_giudica_e_non_cade():
    """Il motore la salta prima di interrogarla. Chi la interroga lo stesso
    deve ottenere «niente da dire», non un confronto con ``None``."""
    from accoach.engineer.core import NO_WINDOW
    from accoach.engineer.profiles import ROAD_PROFILE
    from accoach.engineer.steps import AccSteps
    phase = ROAD_PROFILE.phases[0].reconfigure(pressure_window=NO_WINDOW,
                                               steps=AccSteps())
    lap = LapStats(lap_time_ms=100000, pressures_hot={"front": 20.0, "rear": 40.0})
    assert phase.blind()
    assert phase.gate([lap]) and phase.pressure_remedy(lap) is None
    assert phase.pressure_by_hand(lap) == ""
    assert ROAD_PROFILE.phases[0].blind() == "", "il profilo di tutti non si tocca"


def test_la_gt3_misurata_riceve_ancora_la_sua_proposta():
    eng = engineer_for("mclaren_720s_gt3_evo", "monza", is_acc=True)
    decisions = _laps(eng, 4, 24.7, 26.5)
    assert any(d.kind is DecisionKind.PROPOSE for d in decisions)


def test_il_messaggio_e_in_italiano_quando_l_app_lo_e(monkeypatch):
    from accoach.engineer.profiles import _common
    monkeypatch.setattr(_common, "current_language", lambda: "it")
    eng = engineer_for("ks_toyota_ts040", "spa", is_acc=False)
    said = [d for d in _laps(eng, 4, 27.0, 27.0)
            if d.kind is DecisionKind.STAND_DOWN]
    assert "non so" in said[0].message and "finestra" in said[0].message


# --- e il coach, che usa la stessa classe per le sue soglie ----------------

@pytest.mark.parametrize("car", ["bmw_m3_e92", "abarth500", "dodge_char_police",
                                 "ks_toyota_ts040", "lamborghini_huracan_st"])
def test_per_il_coach_un_auto_ignota_resta_dov_era(car):
    """`classify` serve anche a wheelspin, trail-brake e sottosterzo. Li' un
    «non lo so» non c'e': una soglia ci vuole comunque, e resta quella di ieri
    — la stradale, la piu' prudente delle tre (niente trail-brake, soglia di
    pattinamento piu' bassa). Cambiarla qui sarebbe ritarare il coach per 189
    auto senza averne misurata una."""
    assert classify(car) is CarClass.ROAD
    assert tuning_for_car(car) == tuning_for_class(CarClass.ROAD)


def test_le_auto_misurate_non_cambiano_soglie():
    """Le tre su cui le tarature sono nate (vedi coaching/tuning.py)."""
    assert classify("mclaren_720s_gt3_evo") is CarClass.GT3
    assert classify("gp_2025_sf25") is CarClass.FORMULA
    assert classify("bmw_m3_e92") is CarClass.ROAD
