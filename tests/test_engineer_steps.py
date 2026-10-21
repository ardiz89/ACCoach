"""Un click non vale uguale dappertutto, e dove non si sa quanto vale non si scrive.

Riprodotto il 12/10 sui giri veri di Spa con la SF25 (Assetto Corsa): anteriori
a 22.7 psi a caldo, finestra 22.0. L'Ingegnere voleva togliere 0.8 psi e ha
proposto «−8 click», che e' giusto su ACC (un click = 0.1 psi) e su AC ha
scritto ``PRESSURE_LF`` da 15 a 7: otto psi, perche' li' il file porta psi
interi e un click ne vale uno.

Tutti i test qui guardano l'effetto — il numero che finisce nel file, o che non
ci finisce — e non la forma della proposta: una proposta «−8 click» e una
«−1 click» si leggono uguali finche' non si apre il setup.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from accoach import trackedges
from accoach.engineer import (
    Balance,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
    engineer_for,
)
from accoach.engineer.profiles import ROAD_PROFILE
from accoach.engineer.profiles._common import PressurePhase
from accoach.engineer.steps import AccSteps, AcSteps, UnknownSteps, steps_for
from accoach.setup import ac_steps
from accoach.setup.loader import load_any
from accoach.setup.web_api import register_setup_routes

U_APEX = Symptom(Balance.UNDERSTEER, Phase.APEX, Speed.LOW)

# Una dichiarazione d'auto come quelle misurate: pressione in psi veri, barra in
# N/m con un passo di 200, smorzatori salvati come numero di click.
CAR_INI = """
[DISPLAY_METHOD]
SHOW_CLICKS=1

[PRESSURE_LF]
SHOW_CLICKS=0
MIN=15
MAX=40
STEP={psi}        ; psi per click
[PRESSURE_RF]
SHOW_CLICKS=0
STEP={psi}
[PRESSURE_LR]
SHOW_CLICKS=0
STEP={psi}
[PRESSURE_RR]
SHOW_CLICKS=0
STEP={psi}

[ARB_FRONT]
SHOW_CLICKS=0
MIN=0
MAX=20000
STEP=200
// un commento alla maniera delle mod
[CAMBER_LF]
SHOW_CLICKS=0
STEP=1
[CAMBER_RF]
SHOW_CLICKS=0
STEP=1
[DAMP_REBOUND_LR]
SHOW_CLICKS=1
MIN=100
MAX=12000
STEP=800
[DAMP_REBOUND_RR]
SHOW_CLICKS=1
STEP=800
"""

SETUP_INI = """[CAR]
MODEL=prova

[PRESSURE_LF]
VALUE=15

[PRESSURE_RF]
VALUE=15

[PRESSURE_LR]
VALUE=15

[PRESSURE_RR]
VALUE=15

[ARB_FRONT]
VALUE=20000
"""


@pytest.fixture
def ac(tmp_path, monkeypatch):
    """Un Assetto Corsa finto: ``install(car, psi=1, packed=False, clear=True)``."""
    content = tmp_path / "assettocorsa" / "content"
    (content / "tracks").mkdir(parents=True)
    (content / "cars").mkdir()
    monkeypatch.setattr(trackedges, "tracks_dir", lambda: content / "tracks")

    def install(car, psi=1, packed=False, clear=True, text=None):
        folder = content / "cars" / car
        folder.mkdir()
        if clear:
            (folder / "data").mkdir()
            (folder / "data" / "setup.ini").write_text(
                text if text is not None else CAR_INI.format(psi=psi),
                encoding="utf-8")
        if packed:
            (folder / "data.acd").write_bytes(b"\x00")
        return car

    return install


def _lap(front=None, rear=None, symptom=None, score=0.6, time_ms=100000):
    press = None if front is None else {"front": front, "rear": rear}
    return LapStats(lap_time_ms=time_ms,
                    symptom_scores={symptom: score} if symptom else {},
                    symptom_corners={symptom: 4} if symptom else {},
                    pressures_hot=press)


def _drive(eng, n=4, **lap):
    """Gira ``n`` giri uguali e rende tutte le decisioni."""
    return [eng.observe(_lap(**lap)) for _ in range(n)]


def _proposal(decisions):
    return next((d for d in decisions if d.kind is DecisionKind.PROPOSE), None)


def _write(tmp_path, change):
    """Scrive una proposta per la strada vera (la rotta) e rilegge il file."""
    root = tmp_path / "setups"
    track = root / "prova" / "spa"
    track.mkdir(parents=True)
    src = track / "last.ini"
    src.write_text(SETUP_INI, encoding="utf-8")
    app = FastAPI()
    register_setup_routes(app, root)
    r = TestClient(app).post("/api/setup/apply", json={
        "path": str(src), "as_name": "HONE_1", "confirm": True,
        "changes": change.as_setup_payload()})
    assert r.status_code == 200, r.text
    out = load_any(r.json()["path"])
    return lambda key, slot=0: out.click(out.spec_by_key(key), slot)


# --- il difetto, sul numero che finisce nel file ---------------------------

def test_su_ac_togliere_meno_di_un_psi_scrive_un_psi_e_non_otto(ac, tmp_path):
    """I numeri sono quelli di Spa: 22.74 a caldo davanti, finestra 22.0 ±0.4."""
    eng = engineer_for(ac("f1_prova"), "spa", is_acc=False)
    d = _proposal(_drive(eng, front=22.74, rear=22.0))
    assert d is not None, "fuori finestra di 0.7 psi: una proposta ci vuole"
    value = _write(tmp_path, d.change)
    assert (value("tyrePressure", 0), value("tyrePressure", 1)) == (14, 14)
    assert (value("tyrePressure", 2), value("tyrePressure", 3)) == (15, 15)


def test_su_ac_la_frase_dice_il_click_che_scrive_e_dove_arriva(ac):
    eng = engineer_for(ac("f1_prova"), "spa", is_acc=False)
    d = _proposal(_drive(eng, front=22.74, rear=22.0))
    assert [c.delta_clicks for c in d.change.changes] == [-1, -1]
    assert "−1 click " in d.change.rationale
    assert "is 22.7 psi" in d.change.rationale and "reach 21.7 psi" in d.change.rationale


def test_un_click_che_vale_due_psi_si_scrive_come_due_psi(ac, tmp_path):
    """``seat_leon_cupra_r`` dichiara ``STEP=2``: e' l'unica delle dodici auto
    misurate, ed e' il caso in cui «un click = +1 nel file» e' falso anche
    quando la pressione e' in psi."""
    eng = engineer_for(ac("f1_due", psi=2), "spa", is_acc=False)
    d = _proposal(_drive(eng, front=24.6, rear=22.0))
    assert [c.delta_clicks for c in d.change.changes] == [-1, -1]
    assert "is 24.6 psi" in d.change.rationale and "reach 22.6 psi" in d.change.rationale
    assert _write(tmp_path, d.change)("tyrePressure", 0) == 13


def test_su_ac_quattro_psi_fuori_si_prendono_un_click_per_sosta(ac):
    """Il tetto per sosta e' 0.8 psi; dove un click ne vale gia' uno il passo e'
    quel click, non i quattro che servirebbero ne' zero. Fra una sosta e
    l'altra l'Ingegnere misura."""
    eng = engineer_for(ac("f1_prova"), "spa", is_acc=False)
    d = _proposal(_drive(eng, front=26.0, rear=22.0))
    assert [c.delta_clicks for c in d.change.changes] == [-1, -1]
    assert "is 26.0 psi" in d.change.rationale and "reach 25.0 psi" in d.change.rationale


@pytest.mark.parametrize("is_acc, kind", [(True, AccSteps), (False, AcSteps)])
def test_il_motore_dice_all_ingegnere_che_gioco_e(tmp_path, is_acc, kind):
    """La domanda ha una risposta sola in tutta l'app, ``snap.is_acc``, e deve
    arrivare fin qui: un Ingegnere costruito senza e' uno che non scrive mai."""
    import synth
    from accoach.engine import CoachEngine

    class Feed:
        def latest(self):
            return synth.snap(is_acc=is_acc)

        def drain_saved(self):
            return []

    engine = CoachEngine(feed=Feed(), voice=None, laps_dir=tmp_path)
    engine.tick(0.0)
    assert type(engine._engineer.steps) is kind


def test_su_acc_non_cambia_niente_otto_click_sono_otto_decimi(tmp_path):
    """La meta' di controllo: la cura non deve aver toccato il gioco che
    funzionava. 24.7 psi con finestra 27.5 era +8 click in pista il 14/08."""
    eng = engineer_for("mclaren_720s_gt3_evo", "monza", is_acc=True)
    d = _proposal(_drive(eng, front=24.7, rear=26.5))
    assert d.change.as_setup_payload() == [
        {"param": "tyrePressure", "slot": 0, "delta_clicks": 8},
        {"param": "tyrePressure", "slot": 1, "delta_clicks": 8}]
    assert "is 24.7 psi" in d.change.rationale and "reach 25.5 psi" in d.change.rationale


def test_il_passo_di_acc_viene_dal_registro_del_formato_non_da_una_copia():
    from accoach.setup.acc_format import SETUP_PARAMS
    spec = next(s for s in SETUP_PARAMS if s.key == "tyrePressure")
    assert AccSteps().psi_per_click((0, 1)) == spec.step == 0.1


# --- una finestra piu' stretta del click non si insegue --------------------

def test_entro_mezzo_click_dal_bersaglio_la_fase_e_chiusa(ac):
    """Finestra Formula 22.0 ±0.4, click da 1 psi. A 22.45 il click porta a
    21.45, che e' piu' lontano: senza questa regola l'Ingegnere toglie un psi,
    lo rimette, e non chiude mai."""
    car = ac("f1_prova")
    coarse = PressurePhase(22.0, 0.4, steps=AcSteps(car))
    fine = PressurePhase(22.0, 0.4, steps=AccSteps())
    lap = _lap(front=22.45, rear=22.0)
    assert coarse.gate([lap]) and coarse.pressure_remedy(lap) is None
    assert not fine.gate([lap]), "su ACC 22.45 e' fuori, e li' si arriva"
    assert fine.pressure_remedy(lap) is not None


def test_oltre_mezzo_click_si_propone_ancora(ac):
    coarse = PressurePhase(22.0, 0.4, steps=AcSteps(ac("f1_prova")))
    lap = _lap(front=22.55, rear=22.0)
    assert not coarse.gate([lap])
    assert coarse.pressure_remedy(lap).changes[0].delta_clicks == -1
    assert coarse.pressure_by_hand(lap) == "", \
        "«fallo tu a mano» e' solo per l'auto di cui non sappiamo il passo"


# --- dove il passo non si sa, non si scrive -------------------------------

def _never_writes(decisions):
    assert all(d.change is None for d in decisions)
    assert not any(d.kind is DecisionKind.PROPOSE for d in decisions)


@pytest.mark.parametrize("packed, clear, word", [
    (True, False, "data.acd"),        # solo il pacchetto: quasi tutte le auto
    (True, True, "data.acd"),         # tutt'e due: quale carica il gioco?
    (False, False, "setup.ini"),      # nessuno dei due
])
def test_un_auto_che_non_dichiara_il_passo_non_riceve_una_proposta(
        ac, packed, clear, word):
    eng = engineer_for(ac("f1_chiusa", packed=packed, clear=clear), "spa",
                       is_acc=False)
    decisions = _drive(eng, n=6, front=22.74, rear=22.0)
    _never_writes(decisions)
    last = decisions[-1]
    assert last.kind is DecisionKind.STAND_DOWN
    assert word in last.message, "il perche', non un silenzio"
    assert "22.7" in last.message and "−0.7 psi" in last.message, \
        "la misura resta buona: il pilota la corregge a mano"
    assert eng.phase.key == "pressures", "non si passa alle barre su gomme sbagliate"


def test_un_auto_che_non_e_installata_non_riceve_una_proposta(ac):
    ac("un_altra")
    eng = engineer_for("f1_mai_vista", "spa", is_acc=False)
    _never_writes(_drive(eng, n=6, front=22.74, rear=22.0))


def test_senza_il_gioco_installato_non_si_scrive(monkeypatch):
    monkeypatch.setattr(trackedges, "tracks_dir", lambda: None)
    eng = engineer_for("gp_2025_sf25", "spa", is_acc=False)
    _never_writes(_drive(eng, n=6, front=22.74, rear=22.0))


def test_chi_non_dice_che_gioco_e_ottiene_un_ingegnere_che_non_scrive():
    """Il difetto era un valore di comodo: «sara' ACC». Chi si dimentica di
    dirlo adesso ottiene la prudenza, non un'ipotesi."""
    eng = engineer_for("mclaren_720s_gt3_evo", "monza")
    decisions = _drive(eng, n=6, front=24.7, rear=26.5)
    _never_writes(decisions)
    assert decisions[-1].kind is DecisionKind.STAND_DOWN
    assert isinstance(steps_for("x", None), UnknownSteps)


def test_il_messaggio_a_mano_e_in_italiano_quando_l_app_lo_e(ac, monkeypatch):
    from accoach.engineer import core
    from accoach.engineer.profiles import _common
    monkeypatch.setattr(_common, "current_language", lambda: "it")
    monkeypatch.setattr(core, "current_language", lambda: "it")
    eng = engineer_for(ac("f1_chiusa", packed=True, clear=False), "spa",
                       is_acc=False)
    msg = _drive(eng, front=22.74, rear=22.0)[-1].message
    assert "anteriore" in msg and "Non la scrivo io" in msg
    assert "impacchettati" in msg


def test_quando_la_pressione_torna_in_finestra_l_ingegnere_riparte(ac):
    """Tacere non e' fermarsi: corretta a mano, la fase si chiude da sola."""
    eng = engineer_for(ac("f1_chiusa", packed=True, clear=False), "spa",
                       is_acc=False)
    _drive(eng, front=22.74, rear=22.0)
    d = eng.observe(_lap(front=22.1, rear=22.0))
    assert d.kind is DecisionKind.PHASE_DONE and eng.phase.key != "pressures"


# --- le altre leve: lo stesso passo, la stessa prudenza --------------------

def test_una_barra_salvata_in_newton_si_muove_del_suo_passo(ac, tmp_path):
    """«Barra anteriore piu' morbida (−1)» su un'auto con ``STEP=200`` scriveva
    20000 → 19999: un click che non e' un click. Il verdetto su una modifica
    cosi' non l'ho riprodotto, ma un duecentesimo di passo non puo' averne uno
    che dica qualcosa della leva — e nel registro ci finisce col suo nome."""
    eng = RaceEngineer(ROAD_PROFILE, steps=AcSteps(ac("strada")))
    d = _proposal(_drive(eng, symptom=U_APEX))
    atom = d.change.changes[0]
    assert (atom.param, atom.delta_clicks) == ("aRBFront", -1), \
        "il budget e il registro restano in click veri"
    assert _write(tmp_path, d.change)("aRBFront") == 19800


def test_il_ripristino_rimette_il_numero_che_c_era(ac):
    eng = RaceEngineer(ROAD_PROFILE, steps=AcSteps(ac("strada")))
    d = _proposal(_drive(eng, symptom=U_APEX))
    assert d.change.as_setup_payload()[0]["delta_clicks"] == -200
    assert d.change.reversed().as_setup_payload()[0]["delta_clicks"] == 200


def test_un_valore_salvato_come_numero_di_click_si_muove_di_uno(ac):
    """``SHOW_CLICKS=1``: lo smorzatore e' salvato come «6», non come 4900."""
    steps = AcSteps(ac("strada"))
    assert steps.units("reboundSlow", 2) == 1
    assert steps.units("aRBFront", None) == 200
    assert steps.units("aRBFront", 3) is None, "una barra non ha una quarta ruota"
    assert steps.units("splitter", None) is None, "una leva che AC non ha"


def test_una_fase_pressioni_a_cui_nessuno_ha_detto_il_passo_non_propone():
    """I profili la costruiscono senza: e' il motore che glielo da'. Se un
    giorno non glielo da', la fase tace invece di ragionare come ACC."""
    assert PressurePhase(27.5, 0.7).pressure_remedy(_lap(front=24.7, rear=27.5)) is None


def test_una_leva_senza_passo_si_salta_e_si_prova_la_successiva(ac):
    """Niente barra dichiarata, camber si': il primo rimedio non e' scrivibile
    e il secondo lo e'."""
    text = CAR_INI.format(psi=1).replace("[ARB_FRONT]", "[ARB_NON_QUESTA]")
    eng = RaceEngineer(ROAD_PROFILE, steps=AcSteps(ac("strada", text=text)))
    d = _proposal(_drive(eng, symptom=U_APEX))
    assert d.change.param == "camber"


def test_leve_tutte_senza_passo_non_e_colpa_del_pilota(ac):
    """«Rimedi esauriti — probabile questione di guida» e' un'affermazione sul
    pilota, e va nel conto di quante volte la facciamo. Non avere il passo e'
    un limite nostro: si dice quello, una volta, e non si conta."""
    eng = RaceEngineer(ROAD_PROFILE,
                       steps=AcSteps(ac("chiusa", packed=True, clear=False)))
    decisions = _drive(eng, n=6, symptom=U_APEX)
    _never_writes(decisions)
    said = [d for d in decisions if d.kind is DecisionKind.STAND_DOWN]
    assert len(said) == 1 and "anti-roll bar" in said[0].message
    assert "data.acd" in said[0].message
    assert eng.exhausted_calls == [] and U_APEX not in eng.exhausted
    assert eng.state()["remedy_idx"].get(str(U_APEX), 0) == 0, \
        "il giorno che l'auto e' leggibile quelle leve sono ancora da provare"


def test_un_sintomo_senza_leve_non_eredita_il_non_so_scrivere_di_un_altro(ac):
    """«Non la so scrivere» vale per la ricerca che l'ha trovato. Rimasto
    appeso, trasformerebbe il prossimo «rimedi esauriti» — che e' vero — in un
    limite nostro che non c'e'."""
    from accoach.engineer.core import Profile
    phase = ROAD_PROFILE.phases[1]                       # grip meccanico
    eng = RaceEngineer(Profile("x", [phase], {}), steps=AcSteps(ac("strada")))
    eng._blocked = object()                              # avanzo di un'altra ricerca
    decisions = _drive(eng, n=5, symptom=U_APEX)
    assert eng.exhausted_calls == [U_APEX]
    assert not any(d.kind is DecisionKind.STAND_DOWN for d in decisions)


def test_una_fase_che_propone_senza_chiedere_il_passo_viene_fermata_alla_porta():
    """Le fasi di oggi scartano da sole quello che non sanno scrivere. Questa
    e' la fase di domani che se ne dimentica: `_propose` e' l'unica porta verso
    il setup, e il controllo sta li'."""
    from accoach.engineer.core import AtomicChange, Profile, ProposedChange, WorkPhase

    class Distratta(WorkPhase):
        def owns(self, symptom):
            return False

        def gate(self, window):
            return False

        def pressure_remedy(self, stats):
            return ProposedChange((AtomicChange("tyrePressure", 0, -8),),
                                  "eight clicks off", "Pressures", "BOX")

    eng = RaceEngineer(Profile("x", [Distratta("p", "Pressures", "BOX")], {}),
                       steps=UnknownSteps())
    decisions = _drive(eng, n=5)
    _never_writes(decisions)
    assert decisions[-1].kind is DecisionKind.STAND_DOWN
    assert "eight clicks off" in decisions[-1].message
    eng.mark_applied()
    assert eng.active is None, "niente in sospeso da dichiarare applicato"


def test_una_leva_al_volante_non_ha_bisogno_del_passo():
    """Il bias lo gira il pilota: non finisce in un file, non c'e' niente da
    convertire, e tacere li' sarebbe tacere per niente."""
    lift_off = Symptom(Balance.OVERSTEER, Phase.ENTRY, Speed.LOW)
    eng = RaceEngineer(ROAD_PROFILE, steps=UnknownSteps())
    eng.remedy_idx[lift_off] = 3                  # le tre leve BOX gia' provate
    d = _proposal(_drive(eng, symptom=lift_off))
    assert d is not None and d.change.tag == "AV" and d.change.param == "brakeBias"


# --- leggere la dichiarazione dell'auto -----------------------------------

def test_la_dichiarazione_si_legge_solo_dove_la_si_e_gia_vista():
    got = ac_steps.parse("""
[A]
SHOW_CLICKS=0
STEP=200   ; fisico
[B]
SHOW_CLICKS=2
STEP=10
[MEZZO]
SHOW_CLICKS=0
STEP=0.5
[STRANO]
SHOW_CLICKS=3
STEP=1
[SENZA_SHOW]
STEP=1
[ZERO]
SHOW_CLICKS=0
STEP=0
""")
    assert set(got) == {"A", "B"}
    assert (got["A"].units, got["A"].physical) == (200, True)
    assert (got["B"].units, got["B"].physical) == (1, False)


def test_due_ruote_dello_stesso_asse_con_passi_diversi_non_si_scrivono(ac):
    text = CAR_INI.format(psi=1).replace(
        "[PRESSURE_RF]\nSHOW_CLICKS=0\nSTEP=1", "[PRESSURE_RF]\nSHOW_CLICKS=0\nSTEP=2")
    steps = AcSteps(ac("storta", text=text))
    assert steps.psi_per_click((0, 1)) is None
    assert steps.psi_per_click((2, 3)) == 1.0


def test_una_pressione_salvata_come_numero_di_click_non_si_scrive(ac):
    """Mai vista su nessuna delle dodici auto: non e' qui che si scopre come
    si legge."""
    text = CAR_INI.format(psi=1).replace(
        "[PRESSURE_LF]\nSHOW_CLICKS=0", "[PRESSURE_LF]\nSHOW_CLICKS=1")
    assert AcSteps(ac("indice", text=text)).psi_per_click((0, 1)) is None


def test_il_nome_dell_auto_si_trova_anche_con_altre_maiuscole(ac):
    ac("BEM_Toyota")
    assert AcSteps("bem_toyota").psi_per_click((0, 1)) == 1.0
