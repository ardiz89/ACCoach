"""L'Ingegnere e l'assetto che c'e' davvero in macchina (R1, R2, R3).

Il motore (Task 4) riconosce ai box quale file di setup e' montato e lo passa
all'Ingegnere in un `SetupReport`, gia' in parole. Qui i report sono costruiti a
mano: si prova solo cosa decide l'Ingegnere.

* R1: un assetto cambiato senza che HONE abbia scritto niente rifa' la base;
* R2: dopo una scrittura ai box, il file sbagliato all'uscita mette in pausa la
  prova, senza buttare la base misurata prima della modifica;
* R3: su un assetto che non e' un file si misura, ma ai box non si scrive;
* le modifiche al volo accettate viaggiano fino alla scrittura dopo (`carry`);
* il ripartitore si tara solo da risposte del pilota che concordano.
"""
import pytest

from accoach import config
from accoach.engineer import (
    Balance,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
)
from accoach.engineer.core import FRONT, AtomicChange, ProposedChange, SetupReport
from accoach.engineer.profiles import GT3_PROFILE

PRESS_OK = {"front": 26.5, "rear": 26.5}
LOW = {"front": 24.7, "rear": 26.5}
# Dove arrivano gli anteriori dopo la modifica (+8 click, il massimo per sosta).
AFTER = {"front": 25.5, "rear": 26.5}
ENTRY_OVER = Symptom(Balance.OVERSTEER, Phase.ENTRY, Speed.LOW)


@pytest.fixture(autouse=True)
def _italiano(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


def _lap(press=PRESS_OK, scores=None, time_ms=100000):
    scores = scores or {}
    return LapStats(lap_time_ms=time_ms, stable=True,
                    symptom_scores=dict(scores),
                    symptom_corners={s: 4 for s in scores},
                    pressures_hot=dict(press))


def _eng():
    return RaceEngineer(GT3_PROFILE, min_stable=3)


def _until(eng, lap, kind=DecisionKind.PROPOSE, n=8):
    for _ in range(n):
        d = eng.observe(lap())
        if d.kind is kind:
            return d
    raise AssertionError(f"il motore non e' arrivato a {kind}")


def _pressure_test(eng):
    """Una modifica di pressione proposta e scritta ai box: la prova e' aperta."""
    d = _until(eng, lambda: _lap(LOW))
    assert d.change.tag == "BOX"
    eng.mark_applied()
    assert eng.active is not None
    return d


def _report(**kw):
    kw.setdefault("state", "match")
    return SetupReport(**kw)


def _wrong(**kw):
    return _report(name="HONE_7", expected="HONE_8", expected_ok=False,
                   expected_diff="TC 6 invece di 3", **kw)


def _right(**kw):
    return _report(name="HONE_8", expected="HONE_8", expected_ok=True, **kw)


# --- il report -------------------------------------------------------------

def test_the_report_goes_through_a_dict_and_back():
    rep = SetupReport(state="unsaved", name="HONE_7", probable=True,
                      changed="TC 3 invece di 6", expected="HONE_8",
                      expected_ok=False, expected_diff="TC 6 invece di 3",
                      psi_doubt="", unsaved_diff="TC 6 invece di 3")
    assert SetupReport.from_dict(rep.to_dict()) == rep
    # Un dizionario sporco non rompe niente: quello che non torna si lascia.
    odd = SetupReport.from_dict({"state": "match", "name": 3, "probable": "si",
                                 "expected_ok": "no", "extra": 1})
    assert odd.state == "match" and odd.name is None
    assert odd.probable is False and odd.expected_ok is None
    assert SetupReport.from_dict(None).state == "unknown"


# --- R1: un cambio che nessuno ha chiesto -----------------------------------

def test_an_unrequested_change_restarts_the_base():
    eng = _eng()
    for _ in range(3):
        eng.observe(_lap())
    assert len(eng.window) == 3
    d = eng.setup_seen(_report(name="HONE_8", changed="TC 3 invece di 6"),
                       at_exit=True)
    assert d.kind is DecisionKind.COLLECT
    assert len(eng.window) == 0
    assert "Rifaccio la base" in d.message
    assert "TC 3 invece di 6" in d.message


def test_a_change_seen_while_stopped_waits_for_the_exit():
    """Dal vivo ai box il pilota sta ancora scegliendo: la base cambia solo
    all'uscita, quando l'assetto e' quello con cui guidera'."""
    eng = _eng()
    for _ in range(3):
        eng.observe(_lap())
    assert eng.setup_seen(_report(name="HONE_8", changed="TC 3 invece di 6"),
                          at_exit=False) is None
    assert len(eng.window) == 3


def test_a_change_during_a_test_is_not_judged():
    eng = _eng()
    _pressure_test(eng)
    # La prima uscita dopo la scrittura: e' il file scritto, la prova parte.
    assert eng.setup_seen(_right(), at_exit=True) is None
    eng.observe(_lap(LOW))
    # Alla sosta dopo l'assetto cambia senza che HONE abbia scritto niente.
    d = eng.setup_seen(_report(name="HONE_7", changed="TC 3 invece di 6",
                               expected="HONE_8", expected_ok=False,
                               expected_diff="TC 6 invece di 3"), at_exit=True)
    assert d.kind is DecisionKind.STAND_DOWN
    assert d.confirm_base is True
    assert d.message == (
        "Hai cambiato assetto rispetto allo stint di prima. Ora hai TC 3 invece "
        "di 6. La prova in corso non la giudico e non la registro. Ai box dimmi "
        "quale assetto hai caricato, poi rifaccio la base.")
    assert eng.active is None
    assert eng.observe(_lap()) is d          # tenuta finche' il pilota risponde


def test_a_change_in_the_stop_where_hone_wrote_is_not_a_surprise():
    """La sosta in cui HONE ha scritto: il cambio e' quello scritto."""
    eng = _eng()
    _pressure_test(eng)
    assert eng.setup_seen(_right(changed="TC 3 invece di 6"), at_exit=True) is None
    assert eng.active is not None


def test_a_proposal_waiting_on_the_old_setup_is_dropped():
    """Una modifica proposta sulla base di prima non si scrive sulla nuova."""
    eng = _eng()
    _until(eng, lambda: _lap(LOW))
    assert eng._pending is not None
    d = eng.setup_seen(_report(name="HONE_8", changed="TC 3 invece di 6"),
                       at_exit=True)
    assert d.kind is DecisionKind.COLLECT
    assert eng._pending is None
    eng.mark_applied()
    assert eng.active is None


# --- R2: il file sbagliato dopo una scrittura -------------------------------

def test_the_wrong_file_after_a_write_pauses_the_test_and_keeps_the_base():
    eng = _eng()
    _pressure_test(eng)
    base = dict(eng.active.base_pressures)
    d = eng.setup_seen(_wrong(), at_exit=True)
    assert d.kind is DecisionKind.STAND_DOWN
    assert d.confirm_base is True
    assert "(HONE_8)" in d.message and "TC 6 invece di 3" in d.message
    assert "Ai box carica HONE_8." in d.message
    for _ in range(2):
        assert eng.observe(_lap(PRESS_OK)) is d
    assert eng.active is not None and eng.active.laps_seen == 0
    assert eng.window == []
    # Nessun contatore mentre aspetta: i giri non contano.
    assert eng.progress()["have"] is None
    back = eng.setup_seen(_right(), at_exit=False)
    assert back.kind is DecisionKind.EVALUATING
    assert back.message.startswith("Ora TC, ABS e mappa sono quelli di HONE_8.")
    assert eng.active.base_pressures == base
    # La prova riprende a contare.
    assert eng.observe(_lap(PRESS_OK)).kind is DecisionKind.EVALUATING
    assert eng.progress()["stage"] == "test"


def test_the_pause_holds_through_another_wrong_exit():
    eng = _eng()
    _pressure_test(eng)
    eng.setup_seen(_wrong(), at_exit=True)
    again = eng.setup_seen(_report(name="HONE_6", expected="HONE_8",
                                   expected_ok=False, expected_diff="ABS 6 invece di 4",
                                   changed="ABS 6 invece di 4"), at_exit=True)
    assert again.kind is DecisionKind.STAND_DOWN and again.confirm_base
    assert "ABS 6 invece di 4" in again.message
    assert eng.active is not None            # un cambio sul file sbagliato non e' R1
    assert eng.observe(_lap()) is again


def test_the_answer_on_the_page_resumes_or_drops_the_paused_test():
    eng = _eng()
    _pressure_test(eng)
    eng.setup_seen(_wrong(), at_exit=True)
    d = eng.base_confirmed(expected=True)
    assert d.kind is DecisionKind.EVALUATING
    assert "HONE_8" in d.message
    assert eng.active is not None
    assert eng.observe(_lap()).kind is DecisionKind.EVALUATING

    eng = _eng()
    _pressure_test(eng)
    eng.setup_seen(_wrong(), at_exit=True)
    d = eng.base_confirmed(expected=False)
    assert d.kind is DecisionKind.COLLECT
    assert eng.active is None
    assert eng.window == []
    assert eng.observe(_lap()).kind is DecisionKind.COLLECT


def test_base_confirmed_without_arguments_still_frees_nothing_when_nothing_waits():
    eng = _eng()
    assert eng.base_confirmed() is None


def test_a_psi_doubt_rides_on_the_counter():
    eng = _eng()
    _pressure_test(eng)
    doubt = "anteriore sinistra 26,1 psi invece di 25,6 psi"
    assert eng.setup_seen(_right(psi_doubt=doubt), at_exit=True) is None
    d = eng.observe(_lap(AFTER))
    assert d.kind is DecisionKind.EVALUATING
    tail = " Le pressioni a freddo non sembrano quelle di HONE_8 (" + doubt + ")."
    assert d.message.endswith(tail)
    assert d.tail.endswith(tail)
    # …fino al verdetto, e non oltre.
    d = _until(eng, lambda: _lap(AFTER), DecisionKind.ACCEPTED)
    assert doubt not in d.message


# --- R3: un assetto che non e' un file --------------------------------------

def test_an_unsaved_setup_measures_but_does_not_write():
    eng = _eng()
    diff = "TC 6 invece di 3, ABS 6 invece di 4"
    assert eng.setup_seen(_report(state="unsaved", unsaved_diff=diff),
                          at_exit=True) is None
    d = None
    for _ in range(3):
        d = eng.observe(_lap(LOW))
    assert d.kind is DecisionKind.STAND_DOWN
    assert d.message.startswith("L'assetto in macchina non è fra i file salvati.")
    assert diff in d.message
    assert eng._pending is None
    assert len(eng.window) == 3              # la base si misura lo stesso
    d = eng.setup_seen(_report(name="HONE_8"), at_exit=False)
    assert d.kind is DecisionKind.PROPOSE
    assert d.change.param == "tyrePressure"
    assert eng._pending is not None


def test_a_saved_file_found_before_the_base_says_so():
    eng = _eng()
    eng.setup_seen(_report(state="unsaved", unsaved_diff="TC 6 invece di 3"),
                   at_exit=False)
    eng.observe(_lap())
    d = eng.setup_seen(_report(name="HONE_8"), at_exit=False)
    assert d.kind is DecisionKind.COLLECT
    assert d.message.startswith("In macchina ora c'è HONE_8")


def test_an_unsaved_setup_seen_live_drops_a_waiting_box_change():
    eng = _eng()
    _until(eng, lambda: _lap(LOW))
    d = eng.setup_seen(_report(state="unsaved", unsaved_diff="TC 6 invece di 3"),
                       at_exit=False)
    assert d.kind is DecisionKind.STAND_DOWN
    assert "TC 6 invece di 3" in d.message
    assert eng._pending is None


def test_wheel_levers_still_pass_on_an_unsaved_setup():
    eng = _eng()
    eng.phase_idx = 3                        # il ripartitore
    eng.setup_seen(_report(state="unsaved", unsaved_diff="TC 6 invece di 3"),
                   at_exit=True)
    d = _until(eng, lambda: _lap(scores={ENTRY_OVER: 0.6}))
    assert d.change.tag == "AV"
    assert d.change.param == "brakeBias"


def test_choosing_a_file_on_the_page_lifts_the_block():
    eng = _eng()
    eng.setup_seen(_report(state="unsaved", unsaved_diff="TC 6 invece di 3"),
                   at_exit=True)
    for _ in range(3):
        eng.observe(_lap(LOW))
    d = eng.base_confirmed()
    assert d is not None and d.kind is DecisionKind.PROPOSE
    assert eng._pending is not None


# --- le modifiche al volo ----------------------------------------------------

def test_an_accepted_wheel_change_is_carried_until_the_next_box_write():
    eng = _eng()
    eng.phase_idx = 3
    _until(eng, lambda: _lap(scores={ENTRY_OVER: 0.6}))
    assert eng.carry_clicks() == {}
    eng.mark_applied()
    _until(eng, lambda: _lap(scores={ENTRY_OVER: 0.05}), DecisionKind.ACCEPTED)
    assert eng.carry_clicks() == {"brakeBias": +1}   # tenuta, e una volta sola
    eng._pending = ProposedChange(
        changes=tuple(AtomicChange("tyrePressure", s, 2) for s in FRONT),
        rationale="Pressione anteriore.", phase_label="Pressioni", tag="BOX")
    eng.mark_applied()
    assert eng.carry_clicks() == {}
    assert eng.carry == []


def test_a_wheel_change_under_test_is_already_in_the_car():
    """Girata sulla manopola e non ancora giudicata: una sosta adesso non deve
    leggere «assetto non salvato»."""
    eng = _eng()
    eng.phase_idx = 3
    _until(eng, lambda: _lap(scores={ENTRY_OVER: 0.6}))
    eng.mark_applied()
    assert eng.active is not None and eng.active.change.tag == "AV"
    assert eng.carry_clicks() == {"brakeBias": +1}
    assert eng.carry == []                   # tenuta non e' ancora
    # Una prova ai box non e' in macchina finche' non si carica il file.
    eng = _eng()
    _pressure_test(eng)
    assert eng.carry_clicks() == {}


# --- la taratura del ripartitore ---------------------------------------------

def test_bias_is_learned_only_from_agreeing_answers():
    eng = _eng()
    assert eng.bias_offset is None
    eng.learn_bias(0.64, 0)
    assert eng.bias_offset == pytest.approx(0.64)
    eng.learn_bias(0.6605, 10)               # 0,6605 − 10 click = 0,6405: concorda
    assert eng.bias_offset == pytest.approx(0.64)
    eng.learn_bias(0.7, 0)
    assert eng.bias_offset is None
    # La risposta in sospeso va su disco con il resto.
    state = eng.state()
    eng = _eng()
    eng.restore(state)
    assert eng.bias_offset is None and eng.bias_pending == pytest.approx(0.7)
    eng.learn_bias(0.7, 0)
    assert eng.bias_offset == pytest.approx(0.7)
    again = _eng()
    again.restore(eng.state())
    assert again.bias_offset == pytest.approx(0.7)


def test_a_bias_that_was_not_read_teaches_nothing():
    eng = _eng()
    eng.learn_bias(-1.0, 0)
    assert eng.bias_offset is None and eng.bias_pending is None
    eng.restore({"bias_offset": "x", "bias_pending": True})
    assert eng.bias_offset is None and eng.bias_pending is None
