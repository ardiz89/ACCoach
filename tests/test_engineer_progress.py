"""La strada dell'Ingegnere: dove sei fra le fasi e quanti giri mancano."""
from accoach.engineer import DecisionKind, LapStats, RaceEngineer, Symptom
from accoach.engineer.profiles import GT3_PROFILE

PRESS_OK = {"front": 26.5, "rear": 26.5}
OFF = {"front": 29.0, "rear": 26.5}


def _lap(press=PRESS_OK):
    return LapStats(lap_time_ms=100000, stable=True, symptom_scores={},
                    symptom_corners={}, pressures_hot=press,
                    lock_segments=0, spin_segments=0)


def _eng():
    return RaceEngineer(GT3_PROFILE, min_stable=3)


def test_a_new_engineer_is_collecting_its_baseline():
    p = _eng().progress()
    assert p["stage"] == "baseline"
    assert (p["have"], p["need"], p["index"]) == (0, 3, 0)
    assert [ph["key"] for ph in p["phases"]] == [
        "pressures", "mechanical", "aero", "brake_bias", "electronics"]
    assert all(ph["tag"] in ("BOX", "AV") and ph["label"] for ph in p["phases"])


def test_tags_come_from_the_phases_themselves():
    eng = _eng()
    got = {ph["key"]: ph["tag"] for ph in eng.progress()["phases"]}
    assert got == {ph.key: ph.tag for ph in eng.phases}


def test_stable_laps_fill_the_baseline():
    eng = _eng()
    eng.observe(_lap()); eng.observe(_lap())
    assert eng.progress()["have"] == 2


def test_a_proposal_waiting_to_be_applied_is_a_change():
    eng = _eng()
    for _ in range(3):
        d = eng.observe(_lap(OFF))
    assert d.kind is DecisionKind.PROPOSE
    assert eng.progress()["stage"] == "change"


def test_applied_it_becomes_a_test_that_counts_laps():
    eng = _eng()
    for _ in range(3):
        eng.observe(_lap(OFF))
    eng.mark_applied()
    p = eng.progress()
    assert (p["stage"], p["have"], p["need"]) == ("test", 0, 3)
    eng.observe(_lap(OFF))
    assert eng.progress()["have"] == 1


def test_a_revert_to_put_back_is_a_restore():
    eng = _eng()
    eng._pending = object()
    eng._pending_is_revert = True
    assert eng.progress()["stage"] == "restore"
    eng._pending = None
    eng._pending_is_revert = False
    eng._held_revert = object()
    assert eng.progress()["stage"] == "restore"


def test_enough_laps_and_nothing_pending_is_diagnosing():
    eng = _eng()
    eng.window = [_lap(), _lap(), _lap()]
    assert eng.progress()["stage"] == "diagnose"


def test_past_the_last_phase_is_done():
    eng = _eng()
    eng.phase_idx = len(eng.phases)
    p = eng.progress()
    assert p["stage"] == "done" and p["index"] == 5
    assert p["have"] is None and p["need"] is None


def test_labels_follow_the_language():
    en = _eng().progress("en")["phases"][0]["label"]
    it = _eng().progress("it")["phases"][0]["label"]
    assert en and it and en != it


def test_the_frame_block_carries_progress(tmp_path):
    from accoach.engine import CoachEngine
    from accoach.engineer.core import Decision
    from accoach.telemetry import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._engineer = _eng()
    eng._engineer_decision = Decision(DecisionKind.COLLECT, "x")
    block = eng._engineer_block()
    assert block["progress"]["stage"] == "baseline"
    eng._engineer = None
    assert eng._engineer_block()["progress"] is None
    eng.close()


def _bare_engine(tmp_path):
    from accoach.engine import CoachEngine
    from accoach.telemetry import TelemetrySnapshot

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    return CoachEngine(reader=_Dead(), laps_dir=tmp_path)


def test_before_any_lap_the_block_is_the_road_and_nothing_else(tmp_path):
    """Il pilota vede la strada dall'inizio: senza decisione il blocco ha solo
    fase e progress, e nessun campo che la pagina leggerebbe come un verdetto."""
    eng = _bare_engine(tmp_path)
    eng._engineer = _eng()
    block = eng._engineer_block()
    assert set(block) == {"phase", "progress"}
    assert block["phase"]["key"] == "pressures"
    p = block["progress"]
    assert (p["stage"], p["have"], p["need"]) == ("baseline", 0, 3)
    eng.close()


def test_no_engineer_at_all_is_still_no_block(tmp_path):
    eng = _bare_engine(tmp_path)
    eng._engineer = None
    assert eng._engineer_block() is None
    eng.close()


def test_past_the_last_phase_a_pending_change_is_still_a_change():
    """Il ricontrollo delle pressioni propone anche a fasi finite (`_advance`
    guarda le gomme prima di `phase is None`): finche' c'e' una modifica da fare,
    da provare o da rimettere, la strada non e' «finita»."""
    eng = _eng()
    eng.phase_idx = len(eng.phases)
    for _ in range(3):
        d = eng.observe(_lap(OFF))
    assert d.kind is DecisionKind.PROPOSE
    p = eng.progress()
    assert (p["stage"], p["index"]) == ("change", 5)
    eng.mark_applied()
    p = eng.progress()
    assert (p["stage"], p["have"], p["need"], p["index"]) == ("test", 0, 3, 5)
    eng.active = None
    eng._held_revert = object()
    assert eng.progress()["stage"] == "restore"


# --- le fasi saltate ---------------------------------------------------------
# «Una fase cieca non e' una fase completata» (`WorkPhase.blind`): `_advance`
# la salta, e lo stesso fa con una fase in cui non trova niente da correggere
# senza che il cancello sia passato. La strada le disegnava spuntate come le
# fasi chiuse davvero.

def test_a_new_engineer_has_skipped_nothing():
    assert _eng().progress()["skipped"] == []


def test_a_blind_phase_is_reported_skipped_not_done():
    from accoach.engineer.core import NO_WINDOW
    eng = RaceEngineer(GT3_PROFILE, min_stable=3, pressure_window=NO_WINDOW)
    for _ in range(3):
        d = eng.observe(_lap())
    assert d.kind is DecisionKind.STAND_DOWN
    p = eng.progress()
    assert p["index"] == 1 and p["skipped"] == [0]


def _gate_shut(eng, i):
    # Il cancello che non passa, su una fase senza sintomi da curare: e' il
    # caso «non ho trovato nulla da correggere». Su una copia: la fase puo'
    # essere quella del profilo condiviso (`reconfigure` rende se stessa).
    import copy
    ph = copy.copy(eng.phases[i])
    ph.gate = lambda window: False
    eng.phases[i] = ph


def test_a_phase_with_nothing_to_correct_is_reported_skipped():
    eng = _eng()
    eng.phase_idx = 1
    _gate_shut(eng, 1)
    for _ in range(3):
        d = eng.observe(_lap())
    assert d.kind is DecisionKind.PHASE_DONE
    p = eng.progress()
    assert p["index"] == 2 and p["skipped"] == [1]


def test_a_phase_whose_gate_passes_is_done_not_skipped():
    eng = _eng()
    eng.phase_idx = 1
    for _ in range(3):
        d = eng.observe(_lap())
    assert d.kind is DecisionKind.PHASE_DONE
    p = eng.progress()
    assert p["index"] == 2 and p["skipped"] == []


def test_skipped_phases_come_back_next_session():
    import json
    eng = _eng()
    eng.phase_idx = 1
    _gate_shut(eng, 1)
    for _ in range(3):
        eng.observe(_lap())
    state = json.loads(json.dumps(eng.state()))
    back = _eng()
    back.restore(state)
    assert back.progress()["skipped"] == [1]
    junk = _eng()
    junk.restore({"phase_idx": 2, "skipped_phases": [1, "x", 99, -1, None]})
    assert junk.progress()["skipped"] == [1]


# --- il contatore detto una volta -------------------------------------------
# La strada dice «Giri puliti per la base, 1 di 3»; il messaggio del motore
# diceva la stessa cosa con altre parole. Il motore separa la coda (perche'
# l'ultimo giro non conta, il sospetto sulle uscite) dal contatore, e la
# pagina mostra solo la coda quando la strada conta.

def test_a_collect_carries_its_tail_apart():
    eng = _eng()
    d = eng.observe(_lap())
    assert d.kind is DecisionKind.COLLECT and d.tail == ""
    cold = LapStats(lap_time_ms=100000, stable=True, warmed_up=False,
                    symptom_scores={}, symptom_corners={}, pressures_hot=PRESS_OK,
                    lock_segments=0, spin_segments=0)
    d = eng.observe(cold)
    assert d.tail and d.message.endswith(d.tail)
    assert d.message != d.tail


def test_an_evaluating_carries_its_tail_apart():
    eng = _eng()
    for _ in range(3):
        eng.observe(_lap(OFF))
    eng.mark_applied()
    d = eng.observe(_lap(OFF))
    assert d.kind is DecisionKind.EVALUATING and d.tail == ""


def test_other_decisions_have_no_tail():
    eng = _eng()
    for _ in range(3):
        d = eng.observe(_lap(OFF))
    assert d.kind is DecisionKind.PROPOSE and d.tail is None


def test_the_frame_block_carries_the_tail(tmp_path):
    from accoach.engineer.core import Decision
    eng = _bare_engine(tmp_path)
    eng._engineer = _eng()
    eng._engineer_decision = Decision(DecisionKind.COLLECT, "x y", tail=" y")
    assert eng._engineer_block()["tail"] == " y"
    eng._engineer_decision = Decision(DecisionKind.PROPOSE, "x")
    assert eng._engineer_block()["tail"] is None
    eng.close()
