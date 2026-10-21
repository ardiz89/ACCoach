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

PRESS_OK = {"front": 26.5, "rear": 26.5}


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
    off = {"front": 29.0, "rear": 26.5}      # front 2.5 psi too high
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
    assert d.change.rationale == ("Hai sottosterzo a centro curva nelle curve veloci, "
                                  "quindi togli 1 click di ala posteriore.")
    # the reverted change names the change it undoes, in Italian
    assert d.change.reversed().rationale == (
        "Annulla la modifica che hai provato, «Togli 1 click di ala posteriore».")


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
            # Il pilota rimette l'assetto di prima. Fino al 13/10 questo test
            # non lo faceva e arrivava in fondo lo stesso, cioe' guidava il
            # difetto: ogni rimedio proposto sopra quello bocciato.
            eng.mark_applied()
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


# --- la memoria dell'Ingegnere fra una sessione e l'altra -------------------
#
# Il 14/08 il pilota ha spento il gioco con un ciclo aperto e l'ha perso. Ma la
# perdita piu' cara non e' la proposta in volo: e' il **registro di cosa e' gia'
# stato provato**. Senza, alla sessione dopo il motore ripropone il rimedio che
# ha gia' misurato e scartato, e ogni rimedio costa 3 giri di base + 3 di prova.
#
# Cosa NON torna, di proposito: la finestra di giri. Sono misure, e due sessioni
# non sono confrontabili (asfalto, benzina, gomme). Un verdetto dato su una base
# di ieri e una prova di oggi sarebbe peggio di nessun verdetto.

_SYM_HI = Symptom(U, AP, HI)


def test_the_state_is_json_and_carries_what_was_tried():
    import json

    eng = _eng()
    eng.remedy_idx[_SYM_HI] = 2
    eng.exhausted.add(Symptom(O, EX, HI))
    eng.applied_clicks[("aRBFront", None)] = -3
    eng.phase_idx = 1
    state = eng.state()
    json.dumps(state)                      # deve poter finire su disco cosi' com'e'
    back = _eng()
    back.restore(state)
    assert back.phase_idx == 1
    assert back.remedy_idx[_SYM_HI] == 2
    assert Symptom(O, EX, HI) in back.exhausted
    assert back.applied_clicks[("aRBFront", None)] == -3


def test_a_remedy_already_tried_is_not_tried_again_next_session():
    """Il motivo per cui questo esiste, detto come effetto e non come campo."""
    eng = _eng()
    first = _drive_to_aero(eng, _SYM_HI, 0.6)
    eng.mark_applied()
    for _ in range(4):                     # bocciata: il sintomo non si muove
        eng.observe(_lap(symptom=_SYM_HI, score=0.6))
    state = eng.state()

    fresh = _eng()
    fresh.restore(state)
    again = _drive_to_aero(fresh, _SYM_HI, 0.6)
    assert again.change.rationale != first.change.rationale


def test_the_lap_window_does_not_come_back():
    """Due sessioni non si confrontano: asfalto, benzina e gomme sono altri. Il
    motore riparte raccogliendo."""
    eng = _eng()
    for _ in range(5):
        eng.observe(_lap())
    fresh = _eng()
    fresh.restore(eng.state())
    assert fresh.observe(_lap()).kind is DecisionKind.COLLECT


def test_a_change_applied_and_never_judged_is_declared_not_judged():
    """Il caso di giovedi': modifica scritta, gioco spento. Quel test non si puo'
    chiudere — la base di confronto stava in un'altra sessione — e fingere di
    chiuderlo sarebbe la bugia peggiore. Diventa il nuovo punto di partenza, e il
    pilota lo legge invece di indovinarlo."""
    eng = _eng()
    proposed = _drive_to_aero(eng, _SYM_HI, 0.6)
    eng.mark_applied()
    assert eng.active is not None

    fresh = _eng()
    fresh.restore(eng.state())
    assert fresh.active is None, "un test non giudicabile non resta aperto"
    msg = fresh.observe(_lap()).message
    assert proposed.change.named in msg and "without a verdict" in msg


def test_the_unjudged_note_is_said_once_not_every_lap():
    eng = _eng()
    _drive_to_aero(eng, _SYM_HI, 0.6)
    eng.mark_applied()
    fresh = _eng()
    fresh.restore(eng.state())
    first = fresh.observe(_lap()).message
    second = fresh.observe(_lap()).message
    assert first != second


def test_a_change_still_only_proposed_does_not_come_back_as_applied():
    """Proposta e non applicata: alla sessione dopo non si finge che sia sulla
    macchina. Se il sintomo c'e' ancora il motore la ripropone da solo, misurando
    oggi; se non c'e' piu', tanto meglio."""
    eng = _eng()
    _drive_to_aero(eng, _SYM_HI, 0.6)      # proposta, mai `mark_applied`
    fresh = _eng()
    fresh.restore(eng.state())
    assert fresh.active is None and fresh._pending is None


def test_restoring_junk_leaves_a_working_engineer():
    """La persistenza e' una comodita': un file rovinato non deve costare al
    pilota la sessione."""
    eng = _eng()
    eng.restore({"phase_idx": "nope", "remedy_idx": {"non un sintomo": 1},
                 "exhausted": [None], "applied_clicks": "boh"})
    assert eng.observe(_lap()).kind is DecisionKind.COLLECT


# --- le uscite di pista come indizio di assetto ----------------------------
#
# «Se non guido pulito potrebbe dipendere sempre dal setup» (il pilota, 14/10).
# Un giro tagliato resta fuori dalla finestra — i suoi TEMPI mentono, tagliare
# la Variante fa guadagnare — ma il COME e' un'altra cosa: se il pilota esce
# sempre col retrotreno che scappa in uscita dalle lente, in curve diverse,
# l'assetto e' un sospettato. Lo stesso cancello dei giri puliti: almeno tre
# giri, almeno tre curve diverse.

_OFF = Symptom(O, EX, LO)


def _off(symptom=_OFF, corner=1, where="", time_ms=97000):
    """Un giro tagliato, uscito in `corner` con l'auto in quel sintomo."""
    st = _cut(time_ms=time_ms, where=where)
    st.off_symptom = symptom
    st.off_corner = None if symptom is None else corner
    return st


def test_tre_uscite_con_lo_stesso_schema_in_tre_curve_fanno_sospettare_l_assetto():
    eng = _eng()
    eng.observe(_off(corner=2))
    eng.observe(_off(corner=5))
    d = eng.observe(_off(corner=9))
    # Lo dice, con la leva che proverebbe…
    assert "traction control" in d.message
    # …ma non la scrive: e' ancora la raccolta dei giri puliti.
    assert d.kind is DecisionKind.COLLECT and d.change is None


def test_il_pilota_legge_perche_quante_uscite_e_dove(it_lang):
    eng = _eng()
    eng.observe(_off(corner=2, where="Tosa"))
    eng.observe(_off(symptom=None, where="Rivazza"))
    eng.observe(_off(corner=5, where="Piratella"))
    eng.observe(_off(corner=2, where="Tosa"))
    msg = eng.observe(_off(corner=9, where="Acque Minerali")).message
    assert "4 uscite su 5" in msg
    assert "in 3 curve diverse" in msg
    assert "sovrasterzo in uscita dalle curve lente" in msg
    tail = msg.split("uscite su 5", 1)[1]
    assert "(Tosa, Piratella, Acque Minerali)" in tail   # una volta per curva
    # Rivazza e' un'uscita senza sintomo: conta nel totale, non fra le prove.
    assert "Rivazza" not in tail
    assert "controllo di trazione" in msg            # la leva, in italiano


def test_un_giro_che_il_gioco_non_ha_completato_non_e_un_uscita(it_lang):
    eng = _eng()
    for c in (2, 5):
        eng.observe(_off(corner=c))
    annullato = _lap(stable=False)
    annullato.unstable_why = "invalid"
    eng.observe(annullato)
    assert "3 uscite su 3" in eng.observe(_off(corner=9)).message


def test_contano_solo_le_uscite_recenti():
    """Tre uscite con lo stesso schema, poi sei tagli col muso in equilibrio:
    le tre sono uscite dalla finestra, e il sospetto con loro."""
    eng = _eng()
    for c in (2, 5, 9):
        eng.observe(_off(corner=c))
    for c in range(6):
        d = eng.observe(_off(symptom=None, corner=c))
    assert "offs" not in d.message


@pytest.mark.parametrize("chiuso", ["exhausted", "_unwritable"])
def test_un_sintomo_che_il_motore_ha_gia_chiuso_non_torna_dalle_uscite(chiuso):
    """Rimedi finiti («e' guida») o leve che su quest'auto non sa scrivere: le
    uscite non riaprono quello che il motore ha gia' chiuso."""
    eng = _eng()
    getattr(eng, chiuso).add(_OFF)
    for c in (2, 5, 9):
        d = eng.observe(_off(corner=c))
    assert "offs" not in d.message


def test_la_leva_nominata_e_quella_a_cui_il_motore_e_arrivato():
    """Se la prima leva per quel sintomo e' gia' stata provata e bocciata, il
    sospetto nomina la seconda, come farebbe una proposta."""
    eng = _eng()
    eng.remedy_idx[_OFF] = 1
    for c in (2, 5, 9):
        d = eng.observe(_off(corner=c))
    assert "Soften the rear anti-roll bar" in d.message
    assert "traction control" not in d.message


def test_senza_leve_rimaste_il_sospetto_resta_detto_senza_inventarne_una():
    eng = _eng()
    eng.remedy_idx[_OFF] = 9
    for c in (2, 5, 9):
        d = eng.observe(_off(corner=c))
    assert "could be the setup" in d.message
    assert "I'd try" not in d.message


def test_un_uscita_sola_resta_guida():
    eng = _eng()
    d = eng.observe(_off(corner=2))
    plain = _eng()
    assert d.message == plain.observe(_cut()).message


def test_due_uscite_non_bastano_anche_in_due_curve_diverse():
    eng = _eng()
    eng.observe(_off(corner=2))
    d = eng.observe(_off(corner=5))
    assert "traction control" not in d.message


def test_sempre_nella_stessa_curva_resta_guida():
    """Il principio di `test_single_corner_symptom_is_not_setup`, sulle uscite:
    una curva sola che ti butta fuori quattro volte e' quella curva."""
    eng = _eng()
    for _ in range(4):
        d = eng.observe(_off(corner=5))
    assert "traction control" not in d.message


def test_tre_uscite_in_due_curve_sole_restano_guida():
    eng = _eng()
    eng.observe(_off(corner=2))
    eng.observe(_off(corner=5))
    d = eng.observe(_off(corner=5))
    assert "traction control" not in d.message


def test_schemi_diversi_non_si_sommano():
    """Tre uscite, tre curve, ma tre sintomi diversi: non c'e' un'auto che fa
    sempre la stessa cosa, c'e' un pilota che sbaglia in tre modi."""
    eng = _eng()
    eng.observe(_off(symptom=Symptom(O, EX, LO), corner=2))
    eng.observe(_off(symptom=Symptom(U, EN, LO), corner=5))
    d = eng.observe(_off(symptom=Symptom(O, EX, HI), corner=9))
    assert "offs" not in d.message


def test_le_uscite_senza_un_sintomo_misurato_non_sono_assetto():
    """Tutte le 38 uscite dell'archivio sono cosi': tagli con l'auto in
    equilibrio. Quante che siano, non accusano l'assetto."""
    eng = _eng()
    for c in (2, 5, 9, 11):
        st = _off(symptom=None)
        st.off_corner = c                     # anche ancorate a curve diverse
        d = eng.observe(st)
    assert "offs" not in d.message


def test_servono_tante_uscite_quanti_giri_chiede_il_motore():
    """La persistenza e' quella del motore (`min_stable`), non un tre scritto
    qui: chi chiede quattro giri puliti chiede anche quattro uscite."""
    eng = RaceEngineer(GT3_PROFILE, min_stable=4)
    for c in (2, 5, 9):
        d = eng.observe(_off(corner=c))
    assert "offs" not in d.message
    d = eng.observe(_off(corner=11))
    assert "offs share" in d.message


def test_le_uscite_non_entrano_nella_base_dei_tempi():
    """La regola che resta: un giro tagliato non fa tempo. Anche quando le sue
    uscite fanno sospettare l'assetto, il contatore dei giri puliti non si
    muove — e i tempi (piu' veloci, qui: tagliare fa guadagnare) restano fuori."""
    eng = _eng()
    for c in (2, 5, 9):
        d = eng.observe(_off(corner=c, time_ms=90000))
    assert "traction control" in d.message
    assert "I have 0 so far" in d.message
    assert eng.window == []


def test_un_giro_tagliato_a_gomme_fredde_non_conta_come_uscita():
    """Fuori con le gomme fredde il sospettato e' la gomma, non l'assetto."""
    eng = _eng()
    for c in (2, 5, 9):
        st = _off(corner=c)
        st.warmed_up = False
        d = eng.observe(st)
    assert "traction control" not in d.message


def test_dopo_un_cambio_di_assetto_le_uscite_di_prima_non_contano_piu():
    """Le uscite di prima sono state fatte con un'altra macchina."""
    eng = _eng()
    off_press = {"front": 29.0, "rear": 26.5}
    eng.observe(_off(corner=2))
    eng.observe(_off(corner=5))
    for _ in range(3):
        d = eng.observe(_lap(press=off_press))
    assert d.kind is DecisionKind.PROPOSE
    eng.mark_applied()
    for _ in range(3):
        d = eng.observe(_lap(time_ms=103000, press=off_press))
    assert d.kind is DecisionKind.REVERTED
    eng.mark_applied()                       # assetto rimesso com'era
    d = eng.observe(_off(corner=9))
    assert d.kind is DecisionKind.COLLECT
    assert "traction control" not in d.message


def test_un_cambio_asciutto_bagnato_dimentica_le_uscite():
    eng = _eng()
    dry = _lap()
    dry.wet = False
    eng.observe(dry)
    for c in (2, 5):
        st = _off(corner=c)
        st.wet = False
        eng.observe(st)
    wet = _lap()
    wet.wet = True
    eng.observe(wet)                          # piove: si butta tutto
    dry2 = _lap()
    dry2.wet = False
    eng.observe(dry2)                         # e torna asciutto: di nuovo
    st = _off(corner=9)
    st.wet = False
    d = eng.observe(st)
    assert d.kind is DecisionKind.COLLECT
    assert "traction control" not in d.message

# --- le pressioni si ricontrollano anche dopo la loro fase ------------------
#
# Il pilota, in pista il 14/10: il coach mi dice che le gomme sono da sistemare
# ma non mi chiama ai box e non mi prepara la modifica. Chi chiama ai box e
# prepara il cambio e' l'Ingegnere, e la sua fase pressioni si chiudeva una volta
# sola: una gomma che usciva di finestra dopo non la guardava piu' nessuno.

def test_a_pressure_that_drifts_out_later_is_proposed_again():
    eng = _eng()
    for _ in range(3):
        d = eng.observe(_lap())
    assert eng.phase.key != "pressures", "il fixture deve aver chiuso le pressioni"
    low = {"front": 25.2, "rear": 26.5}
    d = eng.observe(_lap(press=low))
    assert d.kind is DecisionKind.PROPOSE, d
    assert {c.param for c in d.change.changes} == {"tyrePressure"}
    assert d.change.tag == "BOX", "si cambiano ai box: la chiamata la fa questo tag"
    assert all(c.delta_clicks > 0 for c in d.change.changes), "e le alza"


def test_pressures_in_the_window_do_not_hold_up_the_other_phases():
    """Il controllo: in finestra non succede niente, le fasi vanno avanti."""
    eng = _eng()
    kinds = [eng.observe(_lap()).kind for _ in range(6)]
    assert DecisionKind.PROPOSE not in kinds


def test_the_engineer_says_whether_it_can_judge_the_pressures():
    from accoach.engineer import engineer_for
    assert engineer_for("mclaren_720s_gt3_evo", is_acc=True).handles_pressures() is True
