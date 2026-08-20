"""engineer: the GT3 convergence state machine (diagnosis -> setup change)."""
import pytest

from accoach import config
from accoach.engineer import (
    Balance,
    Decision,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
)
from accoach.engineer.profiles import GT3_PROFILE


@pytest.fixture
def it_lang(tmp_path, monkeypatch):
    """Switch the app language to Italian for the duration of a test (and reset
    the config cache afterwards so other tests see the default English)."""
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None

U, O = Balance.UNDERSTEER, Balance.OVERSTEER
EN, AP, EX = Phase.ENTRY, Phase.APEX, Phase.EXIT
LO, HI = Speed.LOW, Speed.HIGH

PRESS_OK = {"front": 27.5, "rear": 27.5}


def _lap(time_ms=100000, symptom=None, score=0.0, press=PRESS_OK,
         lock=0, spin=0, stable=True, corners=4):
    scores = {symptom: score} if symptom else {}
    sc = {symptom: corners} if symptom else {}
    return LapStats(lap_time_ms=time_ms, stable=stable, symptom_scores=scores,
                    symptom_corners=sc, pressures_hot=press,
                    lock_segments=lock, spin_segments=spin)


def _eng():
    return RaceEngineer(GT3_PROFILE, min_stable=3)


def test_collects_until_enough_laps():
    eng = _eng()
    assert eng.observe(_lap()).kind is DecisionKind.COLLECT
    assert eng.observe(_lap()).kind is DecisionKind.COLLECT
    # third stable lap → it can start working (pressures ok → phase advances)
    d = eng.observe(_lap())
    assert d.kind in (DecisionKind.PHASE_DONE, DecisionKind.PROPOSE)


def test_unstable_laps_do_not_count():
    eng = _eng()
    for _ in range(5):
        assert eng.observe(_lap(stable=False)).kind is DecisionKind.COLLECT


def test_pressure_phase_proposes_off_axle():
    eng = _eng()
    off = {"front": 29.0, "rear": 27.5}      # front 1.5 psi too high
    eng.observe(_lap(press=off)); eng.observe(_lap(press=off))
    d = eng.observe(_lap(press=off))
    assert d.kind is DecisionKind.PROPOSE
    params = {c.param for c in d.change.changes}
    slots = {c.slot for c in d.change.changes}
    assert params == {"tyrePressure"}
    assert slots == {0, 1}                    # front wheels
    assert all(c.delta_clicks < 0 for c in d.change.changes)   # lower pressure


def _drive_to_aero(eng, symptom, score):
    """Feed laps until the engine proposes a remedy for a high-speed symptom."""
    for _ in range(8):
        d = eng.observe(_lap(symptom=symptom, score=score))
        if d.kind is DecisionKind.PROPOSE:
            return d
    raise AssertionError("no proposal reached")


def test_high_speed_understeer_proposes_rear_wing_in_aero_phase():
    eng = _eng()
    d = _drive_to_aero(eng, Symptom(U, AP, HI), 0.6)
    assert eng.phase.key == "aero"
    assert d.change.changes[0].param == "rearWing"
    assert d.change.changes[0].delta_clicks == -1
    assert "rear wing" in d.change.rationale.lower()


def test_accepts_change_that_resolves_the_symptom():
    eng = _eng()
    sym = Symptom(U, AP, HI)
    _drive_to_aero(eng, sym, 0.6)
    eng.mark_applied()
    # three clean laps where the symptom is gone and time is similar
    eng.observe(_lap(symptom=sym, score=0.05))
    eng.observe(_lap(symptom=sym, score=0.05))
    d = eng.observe(_lap(symptom=sym, score=0.05))
    assert d.kind is DecisionKind.ACCEPTED
    assert len(eng.history) == 1


def test_rejects_change_that_worsens_lap_time():
    eng = _eng()
    sym = Symptom(O, EX, HI)
    d0 = _drive_to_aero(eng, sym, 0.6)       # exit-high oversteer -> aero (rear wing +1)
    first_param = d0.change.changes[0].param
    eng.mark_applied()
    # symptom unchanged but lap time clearly worse -> reject + revert
    eng.observe(_lap(time_ms=101000, symptom=sym, score=0.6))
    eng.observe(_lap(time_ms=101000, symptom=sym, score=0.6))
    d = eng.observe(_lap(time_ms=101000, symptom=sym, score=0.6))
    assert d.kind is DecisionKind.REVERTED
    # the revert undoes the original change
    assert d.change.changes[0].param == first_param
    assert d.change.changes[0].delta_clicks == -d0.change.changes[0].delta_clicks
    # and the engine advances to the next remedy for this symptom
    assert eng.remedy_idx[sym] == 1


def test_revert_is_pending_and_mark_applied_resets():
    # C1: a rejected change must be held as a pending revert so mark_applied isn't
    # a no-op, and applying it resets the window without touching the click budget.
    eng = _eng()
    sym = Symptom(O, EX, HI)
    _drive_to_aero(eng, sym, 0.6)
    eng.mark_applied()
    d = None
    for _ in range(3):
        d = eng.observe(_lap(time_ms=101000, symptom=sym, score=0.6))
    assert d.kind is DecisionKind.REVERTED
    assert eng._pending is not None            # the restore is pending, not lost
    clicks_before = dict(eng.applied_clicks)
    eng.mark_applied()                          # driver restores the setup
    assert eng.active is None
    assert eng._pending is None
    assert eng.window == []                     # fresh baseline for the next remedy
    assert eng.applied_clicks == clicks_before  # a revert must not move the budget
    assert not eng.history                      # nothing banked on a rejected change


def test_no_premature_proposal_after_revert():
    # C1: after a revert the engine must COLLECT fresh laps, not jump straight to a
    # new proposal measured on the rejected-setup laps.
    eng = _eng()
    sym = Symptom(O, EX, HI)
    _drive_to_aero(eng, sym, 0.6)
    eng.mark_applied()
    for _ in range(3):
        eng.observe(_lap(time_ms=101000, symptom=sym, score=0.6))   # -> REVERTED
    eng.mark_applied()                          # restore applied
    d = eng.observe(_lap(symptom=sym, score=0.6))
    assert d.kind is DecisionKind.COLLECT       # window was reset


def test_corners_for_unions_window_indices():
    # P3: a proposal is anchored to the corners the symptom showed in, unioned
    # across the rolling window.
    eng = _eng()
    sym = Symptom(U, AP, HI)
    eng.window = [
        LapStats(100000, symptom_corner_idx={sym: [2, 4]}),
        LapStats(100000, symptom_corner_idx={sym: [4, 6]}),
    ]
    assert eng.corners_for(sym) == [2, 4, 6]
    assert eng.corners_for(None) == []


def test_converges_to_done_when_clean():
    eng = _eng()
    last = None
    for _ in range(30):
        last = eng.observe(_lap())            # no symptoms, pressures ok
        if last.kind is DecisionKind.DONE:
            break
    assert last.kind is DecisionKind.DONE


def test_phases_run_in_order():
    eng = _eng()
    seen = []
    for _ in range(30):
        d = eng.observe(_lap())
        if d.kind is DecisionKind.PHASE_DONE:
            seen.append(d)
        if d.kind is DecisionKind.DONE:
            break
    # pressures is the first gate crossed
    assert "Pressures" in seen[0].message


def test_proposed_change_setup_payload_shape():
    eng = _eng()
    d = _drive_to_aero(eng, Symptom(O, AP, HI), 0.7)
    payload = d.change.as_setup_payload()
    assert payload == [{"param": "rearWing", "slot": None, "delta_clicks": 1}]


def test_single_corner_symptom_is_not_setup():
    # A symptom in only 1-2 corners is a driving error, not a setup problem.
    eng = _eng()
    sym = Symptom(U, AP, HI)
    last = None
    for _ in range(8):
        last = eng.observe(_lap(symptom=sym, score=0.6, corners=1))
    assert last.kind is not DecisionKind.PROPOSE


def test_proposal_carries_confidence():
    eng = _eng()
    d = _drive_to_aero(eng, Symptom(U, AP, HI), 0.6)   # corners=4, score 0.6
    assert d.confidence == "high"


def test_plateau_reverts_instead_of_drifting():
    eng = _eng()
    sym = Symptom(U, AP, HI)
    _drive_to_aero(eng, sym, 0.6)
    eng.mark_applied()
    # symptom unchanged and time unchanged -> plateau -> must revert (no drift)
    eng.observe(_lap(symptom=sym, score=0.6))
    eng.observe(_lap(symptom=sym, score=0.6))
    d = eng.observe(_lap(symptom=sym, score=0.6))
    assert d.kind is DecisionKind.REVERTED
    assert not eng.history                       # nothing banked on a plateau


def test_click_budget_caps_a_parameter():
    eng = _eng()
    sym = Symptom(O, AP, HI)                      # rearWing +1 is remedy #0
    # Drive rearWing up by repeatedly proposing + accepting (symptom keeps easing).
    accepted = 0
    score = 0.6
    for _ in range(40):
        d = eng.observe(_lap(symptom=sym, score=score))
        if d.kind is DecisionKind.PROPOSE and d.change.param == "rearWing":
            eng.mark_applied()
        elif d.kind is DecisionKind.ACCEPTED:
            accepted += 1
            score = max(0.0, score - 0.15)        # improving so it keeps the lever
            if score < 0.30:
                break
    # rearWing net clicks never exceed the budget (keyed per (param, slot))
    assert abs(eng.applied_clicks.get(("rearWing", None), 0)) <= 6


# --- i18n: messages follow config.language ---------------------------------

def test_collect_message_is_italian(it_lang):
    eng = _eng()
    d = eng.observe(_lap())
    assert d.kind is DecisionKind.COLLECT
    assert "Servono" in d.message and "giri puliti" in d.message


def test_phase_done_label_is_italian(it_lang):
    eng = _eng()
    seen = []
    for _ in range(30):
        d = eng.observe(_lap())
        if d.kind is DecisionKind.PHASE_DONE:
            seen.append(d)
        if d.kind is DecisionKind.DONE:
            break
    # the first gate crossed is pressures → "Pressioni" (label localised)
    assert "Pressioni" in seen[0].message
    assert "completata" in seen[0].message


def test_rationale_is_italian(it_lang):
    eng = _eng()
    d = _drive_to_aero(eng, Symptom(U, AP, HI), 0.6)   # rearWing −1
    assert d.change.rationale == "Sottosterzo all'apex veloce: meno ala posteriore (−1)"
    # the reverted change keeps the Italian restore prefix
    assert d.change.reversed().rationale.startswith("Ripristino: ")


def test_exhausting_remedies_flags_driving_issue():
    eng = _eng()
    sym = Symptom(O, AP, LO)                  # only 2 remedies in the table
    # Reach the mechanical/brake phase and keep rejecting until remedies run out.
    reverts = 0
    for _ in range(60):
        d = eng.observe(_lap(time_ms=100000, symptom=sym, score=0.6))
        if d.kind is DecisionKind.PROPOSE:
            eng.mark_applied()
        elif d.kind is DecisionKind.REVERTED:
            reverts += 1
        elif d.kind is DecisionKind.PHASE_DONE and "exhausted" in d.message:
            break
    assert sym in eng.exhausted


# --- perche' quel giro non e' contato --------------------------------------
#
# In pista il 14/08 il pilota ha guidato quattro giri di fila e il contatore
# dell'Ingegnere non si e' mosso di uno. Da fuori — e da dentro l'abitacolo, che
# e' l'unico posto che conta — un contatore fermo e' indistinguibile da un
# motore rotto: la domanda che si e' fatto e' «ma sta funzionando?», non «cosa
# sto sbagliando». I quattro giri erano tagliati, e il coach lo sapeva: sapeva
# anche *dove*, perche' `lost_at` e' registrato dal 22/07. Non lo diceva nessuno.

def _cut(time_ms=100000, where=""):
    st = _lap(time_ms=time_ms, stable=False)
    st.unstable_why = "cut"
    st.lost_where = where
    return st


def test_a_lap_that_did_not_count_says_so_and_says_where():
    eng = _eng()
    eng.observe(_lap())
    msg = eng.observe(_cut(where="Variante Ascari")).message
    assert "Variante Ascari" in msg
    # …senza smettere di dire a che punto siamo.
    assert "1" in msg


def test_without_a_place_it_still_says_the_lap_did_not_count():
    eng = _eng()
    plain = eng.observe(_lap()).message
    msg = eng.observe(_cut()).message
    assert msg != plain and len(msg) > len(plain)


def test_a_lap_the_game_annulled_is_not_the_same_as_going_off():
    eng = _eng()
    st = _lap(stable=False)
    st.unstable_why = "invalid"
    annulled = eng.observe(st).message
    cut = eng.observe(_cut()).message
    assert annulled != cut


def test_cold_tyres_are_named_too():
    """Confrontato con un altro giro NON contato, non con uno buono: due giri
    che fanno avanzare il contatore in modo diverso avrebbero messaggi diversi
    comunque, e il test passerebbe senza che nessuno nomini le gomme."""
    eng = _eng()
    cold = _lap()
    cold.warmed_up = False
    assert eng.observe(cold).message != eng.observe(_cut()).message


def test_the_reason_does_not_stick_to_the_next_good_lap():
    """Un giro buono cancella la spiegazione: se restasse, il pilota leggerebbe
    «sei uscito ad Ascari» su un giro in cui non e' uscito da nessuna parte."""
    eng = _eng()
    eng.observe(_cut(where="Variante Ascari"))
    assert "Ascari" not in eng.observe(_lap()).message
