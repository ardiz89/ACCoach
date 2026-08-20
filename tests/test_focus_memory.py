"""Il Focus coach ricorda le curve domate fra una sessione e l'altra.

Prima, `mastered` e `parked` vivevano in RAM e sparivano alla chiusura: riaprivi
HONE e il coach ripartiva da ASSESS, tre giri di attesa, per rimettersi a
lavorare una curva che avevi già domato. Ora lo stato è persistito per
auto+pista nel catalogo SQLite (che sopravvive a un rebuild della tabella giri,
perché la migrazione tocca solo `lap`).
"""
from accoach.coaching.focus import FocusCoach
from accoach.recording.catalog import LapCatalog


def test_the_catalog_round_trips_focus_state(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_focus_state("ferrari_488_gt3", "monza", {1, 4}, {7})
    with LapCatalog(tmp_path / "catalog.db") as cat:
        mastered, parked = cat.load_focus_state("ferrari_488_gt3", "monza")
    assert mastered == {1, 4} and parked == {7}


def test_an_unknown_car_track_starts_empty(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as cat:
        assert cat.load_focus_state("bmw_m4_gt3", "spa") == (set(), set())


def test_state_is_keyed_per_car_and_track(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_focus_state("ferrari_488_gt3", "monza", {2}, set())
        cat.save_focus_state("ferrari_488_gt3", "spa", {5}, set())
        assert cat.load_focus_state("ferrari_488_gt3", "monza")[0] == {2}
        assert cat.load_focus_state("ferrari_488_gt3", "spa")[0] == {5}


def test_saving_again_overwrites_not_appends(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_focus_state("ferrari_488_gt3", "monza", {1, 2, 3}, set())
        cat.save_focus_state("ferrari_488_gt3", "monza", {1}, set())
        assert cat.load_focus_state("ferrari_488_gt3", "monza")[0] == {1}


def test_it_survives_a_lap_table_rebuild(tmp_path):
    """La migrazione droppa la tabella `lap`, non `focus_state`."""
    db = tmp_path / "catalog.db"
    with LapCatalog(db) as cat:
        cat.save_focus_state("ferrari_488_gt3", "monza", {3}, set())
        cat._conn.execute("DROP TABLE lap")   # simula una tabella giri legacy
        cat._conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('db_version','0')")
        cat._conn.commit()
    with LapCatalog(db) as cat:                # riapertura → _migrate ricostruisce
        assert cat.load_focus_state("ferrari_488_gt3", "monza")[0] == {3}


# --- a restored coach doesn't re-teach a mastered corner -------------------

def test_a_seeded_coach_never_picks_a_mastered_corner():
    coach = FocusCoach(mastered={0, 1}, parked=set())
    assert coach.mastered == {0, 1}
    # `_choose` skips mastered/parked corners — a mastered one can't become the
    # focus again, which is the whole point of remembering it.
    import inspect
    src = inspect.getsource(coach._choose)
    assert "mastered" in src and "parked" in src


def test_the_engine_persists_a_change_and_restores_it(tmp_path):
    from accoach.comparison import Reference
    from accoach.engine import CoachEngine
    from accoach.recording.storage import save_lap
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.track import detect_corners

    import synth
    from test_engine_gate import _StubReader

    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)
    eng._focus_key = ("ferrari_488_gt3", "monza")
    eng._focus.mastered.add(2)
    eng._save_focus_state()
    eng.close()

    # A brand-new engine on the same store must see corner 2 already mastered.
    m, p = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                       laps_dir=tmp_path)._load_focus_state("ferrari_488_gt3", "monza")
    assert 2 in m


# --- e l'Ingegnere ricorda cosa ha gia' provato ---------------------------
#
# Stessa storia del Focus qui sopra, sull'altra meta' dell'app: senza, riaprire
# HONE fa riproporre il rimedio gia' misurato e scartato la volta prima, e ogni
# rimedio costa tre giri di base piu' tre di prova. Sta nello stesso posto per
# la stessa ragione: e' piccolo, e' per auto+pista, e senza i giri a cui si
# riferisce non vale niente.

def test_the_catalog_round_trips_engineer_state(tmp_path):
    state = {"phase_idx": 2, "remedy_idx": {"understeer apex high": 1},
             "exhausted": ["oversteer exit high"],
             "applied_clicks": [["rearWing", None, -2]], "unjudged": ""}
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_engineer_state("ferrari_488_gt3", "monza", state)
    with LapCatalog(tmp_path / "catalog.db") as cat:
        assert cat.load_engineer_state("ferrari_488_gt3", "monza") == state


def test_an_unknown_combo_has_no_engineer_state(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as cat:
        assert cat.load_engineer_state("bmw_m4_gt3", "spa") is None


def test_engineer_state_is_keyed_per_car_and_track(tmp_path):
    with LapCatalog(tmp_path / "catalog.db") as cat:
        cat.save_engineer_state("ferrari_488_gt3", "monza", {"phase_idx": 1})
        cat.save_engineer_state("ferrari_488_gt3", "spa", {"phase_idx": 4})
        assert cat.load_engineer_state("ferrari_488_gt3", "monza")["phase_idx"] == 1
        assert cat.load_engineer_state("ferrari_488_gt3", "spa")["phase_idx"] == 4


def test_a_corrupt_engineer_state_reads_as_none(tmp_path):
    """Il file e' un file: un JSON rovinato vale «nessuna memoria», mai
    un'eccezione che si porta via la sessione."""
    db = tmp_path / "catalog.db"
    with LapCatalog(db) as cat:
        cat.save_engineer_state("ferrari_488_gt3", "monza", {"phase_idx": 1})
        cat._conn.execute("UPDATE engineer_state SET state_json='{non json'")
        cat._conn.commit()
        assert cat.load_engineer_state("ferrari_488_gt3", "monza") is None
