"""Il motore riconosce l'assetto ai box e lo passa all'Ingegnere e alle pagine.

L'osservatore dei box (`fingerprint.PitWatch`) e il confronto coi file stanno
nel modulo puro; qui si prova il filo che li lega: i file letti dalla cartella
dell'auto e della pista (in minuscolo, come `/api/setup/base`), il file atteso
che arriva dalle pagine con `/engineer/applied` e `/engineer/base`, il blocco
`loaded` nel frame, e le modifiche al volo tenute che una proposta ai box deve
scrivere insieme alla sua.

Le cartelle dei setup sono tutte in `tmp_path`: i file veri del pilota non si
toccano mai.
"""
import dataclasses
import json

import pytest

from accoach import config
from accoach.engine import CoachEngine
from accoach.engineer import Decision, DecisionKind, LapStats
from accoach.engineer.core import FRONT, AtomicChange, ProposedChange
from accoach.setup import store
from accoach.telemetry.snapshot import ACStatus, TelemetrySnapshot
from test_impronta import HONE_7, HONE_8, IMOLA_0, _doc

CAR, TRACK = "mclaren_720s_gt3_evo", "Imola"
# Le pressioni a freddo di HONE_8 (20,3 + 0,1 × click): 52, 47, 44, 41.
HONE_8_COLD = (25.5, 25.0, 24.7, 24.4)


@pytest.fixture(autouse=True)
def _italiano(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


class _Reader:
    def __init__(self):
        self.snap = TelemetrySnapshot.disconnected()

    def read(self):
        return self.snap

    def close(self):
        pass


def _snap(where="track", *, tc=3, abs_=4, emap=0, bias=0.64,
          psi=(0.0, 0.0, 0.0, 0.0), acc=True, track=TRACK,
          core=(0.0, 0.0, 0.0, 0.0), air=0.0):
    """Un frame di ACC: in pista, in corsia box o fermo in piazzola.

    Fermo in piazzola e' come lo pubblica ACC: `in_pit` spento anche li', la
    corsia box accesa e la velocita' a zero (`pitcall.stopped_in_box`)."""
    box, lane = where == "box", where in ("box", "lane")
    return dataclasses.replace(
        TelemetrySnapshot.disconnected(), connected=True, status=ACStatus.LIVE,
        is_acc=acc, car_model=CAR, track=track, in_pit=False, in_pit_lane=lane,
        speed_kmh=0.0 if box else (60.0 if lane else 150.0),
        tyre_pressure=psi, tc_level=tc, abs_level=abs_, engine_map=emap,
        brake_bias=bias, fuel=48.0, tyre_core_temp=core, air_temp=air)


def _lap():
    return LapStats(lap_time_ms=100000, stable=True,
                    pressures_hot={"front": 25.8, "rear": 26.9})


class _Rig:
    """Un motore vero, un lettore finto e i tre file di Imola in `tmp_path`."""

    def __init__(self, tmp_path, folder="Imola"):
        self.dir = tmp_path / "setups" / CAR / folder
        self.dir.mkdir(parents=True)
        for name, v in (("IMOLA_0", IMOLA_0), ("HONE_7", HONE_7), ("HONE_8", HONE_8)):
            (self.dir / f"{name}.json").write_text(json.dumps(_doc(v)),
                                                   encoding="utf-8")
        (tmp_path / "laps").mkdir()
        self.reader = _Reader()
        self.eng = CoachEngine(reader=self.reader, laps_dir=tmp_path / "laps",
                               engineer_voice=False,
                               setup_roots=[tmp_path / "setups"])
        self._t = 0.0

    def path(self, name):
        return str(self.dir / f"{name}.json")

    def drive(self, *snaps):
        for s in snaps:
            self.reader.snap = s
            self._t += 0.1
            self.eng.tick(self._t)

    @property
    def engineer(self):
        return self.eng._engineer

    def block(self):
        return self.eng._engineer_block()

    def propose(self, change):
        """Una proposta in attesa, con una base di tre giri dietro."""
        e = self.engineer
        e.window = [_lap() for _ in range(3)]
        e._pending = change
        self.eng._engineer_decision = Decision(DecisionKind.PROPOSE,
                                               change.rationale, change=change)

    def close(self):
        self.eng.close()


@pytest.fixture
def rig(tmp_path):
    r = _Rig(tmp_path)
    try:
        yield r
    finally:
        r.close()


def _box_change():
    return ProposedChange(
        changes=tuple(AtomicChange("tyrePressure", s, -5) for s in FRONT),
        rationale="Abbassa la pressione anteriore di 5 click.",
        phase_label="Pressioni", tag="BOX")


def _av(param, clicks=1):
    return ProposedChange(changes=(AtomicChange(param, None, clicks),),
                          rationale=f"{param} di {clicks} click.",
                          phase_label="Elettronica", tag="AV")


# --- la cartella -------------------------------------------------------------

def test_find_setup_files_ignores_the_case_of_the_track(tmp_path):
    d = tmp_path / CAR / "Imola"
    d.mkdir(parents=True)
    (d / "HONE_8.json").write_text("{}", encoding="utf-8")
    (d / "vecchio.ini").write_text("", encoding="utf-8")
    (d / ".accoach_backup").mkdir()
    (d / ".accoach_backup" / "HONE_8.20261116T000000.json").write_text("{}")
    assert store.find_setup_files(CAR, "imola", roots=[tmp_path]) == [d / "HONE_8.json"]
    assert store.find_setup_files(CAR.upper(), "IMOLA", roots=(tmp_path,)) == [
        d / "HONE_8.json"]
    assert store.find_setup_files(CAR, "monza", roots=[tmp_path]) == []
    assert store.find_setup_files(CAR, "imola", roots=[tmp_path / "manca"]) == []
    assert store.find_setup_files("", "", roots=[tmp_path]) == []


# --- il frame ----------------------------------------------------------------

def test_the_frame_says_which_file_is_in_the_car(rig):
    rig.drive(_snap())
    assert rig.block()["loaded"] is None              # nessuna sosta ancora
    rig.drive(_snap("lane"), _snap("box", psi=HONE_8_COLD))
    block = rig.block()
    # Prima del primo giro il blocco e' quello parziale, e `loaded` c'e' lo stesso.
    assert "kind" not in block
    loaded = block["loaded"]
    assert loaded["state"] == "match"
    assert loaded["name"] == "HONE_8"
    assert loaded["probable"] is True
    assert loaded["names"] == ["HONE_7", "HONE_8", "IMOLA_0"]
    assert loaded["at"] == "live"
    assert loaded["observed"]["tc"] == 3
    assert loaded["observed"]["cold_psi"] == list(HONE_8_COLD)
    # …e nel blocco intero, dopo una decisione.
    rig.eng._engineer_decision = Decision(DecisionKind.COLLECT, "x")
    assert rig.block()["loaded"]["name"] == "HONE_8"
    rig.drive(_snap("lane"), _snap())
    assert rig.block()["loaded"]["at"] == "exit"


def test_the_case_of_the_folder_does_not_hide_the_files(tmp_path):
    r = _Rig(tmp_path, folder="imola")         # il gioco dice «Imola»
    try:
        r.drive(_snap(), _snap("lane"), _snap("box", psi=HONE_8_COLD))
        assert r.block()["loaded"]["name"] == "HONE_8"
    finally:
        r.close()


def test_a_new_car_or_track_forgets_the_file(rig):
    rig.drive(_snap(), _snap("lane"), _snap("box", psi=HONE_8_COLD))
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("box", psi=HONE_8_COLD))
    assert rig.eng._expected_path == rig.path("HONE_8")
    rig.drive(_snap(track="Monza"))
    assert rig.block()["loaded"] is None
    assert rig.eng._expected_path is None


# --- il file scritto ---------------------------------------------------------

def test_the_page_tells_the_server_which_file_it_wrote(rig):
    from fastapi.testclient import TestClient

    from accoach.server import create_app

    rig.drive(_snap())
    # Da spettatore il server non fa avanzare il motore: il tick lo da' il test.
    with TestClient(create_app(engine=rig.eng, hz=50, spettatore=True)) as c:
        r = c.post("/engineer/applied", json={"path": rig.path("HONE_8")})
        assert r.json() == {"ok": True}
    rig.drive(_snap())
    assert rig.eng._expected_path == rig.path("HONE_8")
    assert rig.eng._written_path == rig.path("HONE_8")


def test_an_empty_or_odd_body_behaves_as_before():
    """La pagina di oggi manda `{}`: il motore riceve la chiamata di sempre."""
    from fastapi.testclient import TestClient

    from accoach.server import create_app

    class _Motore:
        def __init__(self):
            self.calls = []

        def tick(self, now):
            return None

        def close(self):
            pass

        def mark_setup_applied(self, **kw):
            self.calls.append(("applied", kw))

        def mark_base_confirmed(self, **kw):
            self.calls.append(("base", kw))

    m = _Motore()
    hdr = {"Content-Type": "application/json"}
    with TestClient(create_app(engine=m, hz=50)) as c:
        for body in ("{}", "[]", "null", '"x"', "non json", '{"path": 3}',
                     '{"path": ""}'):
            assert c.post("/engineer/applied", content=body, headers=hdr).json() == {"ok": True}
            assert c.post("/engineer/base", content=body, headers=hdr).json() == {"ok": True}
        c.post("/engineer/base", json={"path": "S/HONE_8.json"})
    assert m.calls[:-1] == [("applied", {}), ("base", {})] * 7
    assert m.calls[-1] == ("base", {"path": "S/HONE_8.json"})


def test_a_write_then_the_wrong_file_at_the_exit_asks_at_once(rig):
    rig.drive(_snap())
    rig.propose(_box_change())
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("lane"), _snap("box", tc=6, psi=HONE_8_COLD),
              _snap("lane", tc=6), _snap(tc=6))
    block = rig.block()
    assert block["kind"] == "stand_down"
    assert block["confirm_base"] is True
    assert "HONE_8" in block["message"]
    assert "TC 6 invece di 3" in block["message"]
    # In pausa, non buttata: la base di prima e' buona.
    assert rig.engineer.active is not None


def test_a_write_then_the_right_file_lets_the_test_run(rig):
    rig.drive(_snap())
    rig.propose(_box_change())
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("lane"), _snap("box", psi=HONE_8_COLD), _snap("lane"), _snap())
    assert rig.engineer.active is not None
    assert rig.engineer._held_wrong is None
    assert rig.block()["confirm_base"] is False


def test_a_normal_stop_with_hot_tyres_does_not_doubt_the_written_file(rig):
    """Una sosta a gomme calde dopo la scrittura: le pressioni lette non sono
    quelle a freddo, e non fanno dubitare di HONE_8."""
    rig.drive(_snap())
    rig.propose(_box_change())
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("lane"),
              _snap("box", psi=(27.6, 27.4, 27.1, 27.0), core=(85.0, 84.0, 80.0, 79.0),
                    air=20.0),
              _snap("lane"), _snap())
    assert rig.engineer.active is not None
    assert rig.engineer.active.psi_doubt == ""
    loaded = rig.block()["loaded"]
    assert loaded["at"] == "exit" and loaded["observed"]["cold_psi"] is None


# --- la risposta della pagina ------------------------------------------------

def _paused(rig):
    """HONE ha scritto HONE_8 e all'uscita c'era un altro assetto (R2)."""
    rig.drive(_snap())
    rig.propose(_box_change())
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("lane"), _snap("box", tc=6, psi=HONE_8_COLD),
              _snap("lane", tc=6), _snap(tc=6))
    assert rig.engineer._held_wrong is not None


def test_the_answer_with_the_written_file_resumes_the_test(rig):
    _paused(rig)
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap(tc=6))
    assert rig.block()["kind"] == "evaluating"
    assert rig.engineer.active is not None
    assert rig.engineer._held_wrong is None
    assert rig.eng._expected_path == rig.path("HONE_8")


def test_the_answer_with_another_file_restarts_the_base(rig):
    _paused(rig)
    rig.eng.mark_base_confirmed(path=rig.path("IMOLA_0"))
    rig.drive(_snap(tc=6))
    assert rig.block()["kind"] == "collect"
    assert rig.engineer.active is None
    assert rig.eng._expected_path == rig.path("IMOLA_0")


def test_the_answer_teaches_the_brake_bias(rig):
    """Lo scarto del ripartitore: la lettura da fermo meno i click del file
    piu' quelli girati al volante e tenuti."""
    rig.drive(_snap())
    rig.engineer._record(_av("brakeBias"))            # +1 click tenuto
    rig.drive(_snap("lane"), _snap("box", bias=0.642, psi=HONE_8_COLD))
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap("box", bias=0.642, psi=HONE_8_COLD))
    assert rig.engineer.bias_offset == pytest.approx(0.640)


def test_the_answer_on_track_does_not_learn_from_the_last_stop(rig):
    """La lettura da fermo e' della sosta di prima: in pista il ripartitore
    puo' essere stato girato, e quello che si impara sarebbe sbagliato."""
    rig.drive(_snap(), _snap("lane"), _snap("box", bias=0.642, psi=HONE_8_COLD),
              _snap("lane", bias=0.642), _snap(bias=0.642))
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap(bias=0.66))
    assert rig.engineer.bias_offset is None
    # …e nemmeno dall'uscita: e' sempre una sosta di prima.
    rig.drive(_snap("lane", bias=0.66))
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap("lane", bias=0.66))
    assert rig.engineer.bias_offset is None


def test_an_answer_that_contradicts_the_dials_teaches_nothing(rig):
    """In macchina c'e' TC 6 e il pilota sceglie HONE_8 (TC 3): o la risposta
    o la lettura non e' quella giusta, e il ripartitore non si impara."""
    rig.drive(_snap(), _snap("lane"), _snap("box", tc=6, bias=0.75, psi=HONE_8_COLD))
    rig.eng.mark_base_confirmed(path=rig.path("HONE_8"))
    rig.drive(_snap("box", tc=6, bias=0.75, psi=HONE_8_COLD))
    assert rig.engineer.bias_offset is None


def test_the_answer_without_a_file_teaches_nothing(rig):
    rig.drive(_snap(), _snap("lane"), _snap("box", psi=HONE_8_COLD))
    rig.eng.mark_base_confirmed()
    rig.drive(_snap("box", psi=HONE_8_COLD))
    assert rig.engineer.bias_offset is None


# --- le manopole al volante --------------------------------------------------

def test_hone_s_own_dial_change_in_the_box_is_not_a_change(rig):
    """Il TC +1 chiesto dall'Ingegnere e girato ai box: all'uscita il TC e'
    diverso da quello d'entrata, ma l'ha voluto HONE (non e' R1)."""
    rig.drive(_snap())
    av = _av("tC1")
    rig.propose(av)
    rig.drive(_snap("lane"), _snap("box", psi=HONE_8_COLD),
              _snap("box", tc=4, psi=HONE_8_COLD),
              _snap("lane", tc=4), _snap(tc=4))
    assert rig.engineer.active is not None and rig.engineer.active.change is av
    assert rig.engineer._held_base is None
    assert rig.block()["confirm_base"] is False
    # La manopola in prova e' gia' in macchina: il file resta riconosciuto.
    assert rig.block()["loaded"]["state"] == "match"


def test_a_dial_turned_by_the_driver_in_the_box_restarts_the_base(rig):
    rig.drive(_snap())
    rig.engineer.window = [_lap() for _ in range(3)]
    rig.drive(_snap("lane"), _snap("box", tc=4, psi=HONE_8_COLD),
              _snap("lane", tc=4), _snap(tc=4))
    block = rig.block()
    assert block["kind"] == "collect"
    assert "Hai cambiato assetto" in block["message"]
    assert "TC 4 invece di 3" in block["message"]
    assert rig.engineer.window == []


def test_a_dial_turned_on_track_does_not_cover_a_change_in_the_box(rig):
    """Il TC +1 di HONE girato in pista e' gia' nella lettura d'entrata, e non
    fa della sosta dopo una sosta di HONE."""
    rig.drive(_snap())
    av = _av("tC1")
    rig.propose(av)
    rig.drive(_snap(), _snap(tc=4))                   # girata in pista
    assert rig.engineer.active is not None
    rig.drive(_snap("lane", tc=4), _snap("box", tc=4, psi=HONE_8_COLD),
              _snap("lane", tc=5), _snap(tc=5))       # e una a mano ai box
    # La sosta non era di HONE: la manopola girata a mano ai box e' R1.
    assert rig.engineer._held_base is not None
    assert "TC 5 invece di 4" in rig.block()["message"]


def test_the_done_button_on_track_does_not_cover_a_change_in_the_box(rig):
    """«Fatto» sulla pagina per un TC +1 girato in pista: la sosta dopo non e'
    di HONE, e il TC girato a mano ai box e' R1."""
    rig.drive(_snap())
    rig.propose(_av("tC1"))
    rig.eng.mark_setup_applied()
    rig.drive(_snap(tc=4))                            # il segnale arriva in pista
    assert rig.engineer.active is not None
    rig.drive(_snap("lane", tc=4), _snap("box", tc=5, psi=HONE_8_COLD),
              _snap("lane", tc=5), _snap(tc=5))
    assert rig.engineer._held_base is not None
    assert "TC 5 invece di 4" in rig.block()["message"]


def test_the_done_button_in_the_box_is_hone_s_change(rig):
    rig.drive(_snap())
    av = _av("tC1")
    rig.propose(av)
    rig.drive(_snap("lane"), _snap("box", psi=HONE_8_COLD))
    rig.eng.mark_setup_applied()
    rig.drive(_snap("box", tc=4, psi=HONE_8_COLD), _snap("lane", tc=4), _snap(tc=4))
    assert rig.engineer.active is not None and rig.engineer.active.change is av
    assert rig.engineer._held_base is None


def test_a_write_with_nothing_proposed_is_not_hone_s_change(rig):
    """Il pilota scrive le sue modifiche dall'editor di HONE: la pagina avvisa
    il server, ma l'Ingegnere non aveva proposto niente. Il TC da 3 a 5 e' un
    cambio non chiesto."""
    rig.drive(_snap())
    rig.engineer.window = [_lap() for _ in range(3)]
    rig.drive(_snap("lane"), _snap("box", psi=HONE_8_COLD))
    rig.eng.mark_setup_applied(path=rig.path("HONE_8"))
    rig.drive(_snap("box", tc=5, psi=HONE_8_COLD), _snap("lane", tc=5), _snap(tc=5))
    block = rig.block()
    assert block["kind"] == "collect"
    assert "TC 5 invece di 3" in block["message"]
    assert rig.engineer.window == []


@pytest.mark.parametrize("bad", ["nul", "fuori", "relativo", "unc"])
@pytest.mark.parametrize("route", ["applied", "base"])
def test_a_bad_path_from_a_page_is_no_path(rig, tmp_path, bad, route):
    """Un percorso con un NUL, fuori dalle radici, relativo o di rete: il
    segnale vale come senza percorso, e il tick non salta."""
    other = tmp_path / "altrove"
    other.mkdir()
    (other / "HONE_8.json").write_text(json.dumps(_doc(HONE_8)), encoding="utf-8")
    raw = {"nul": str(rig.dir / "HONE\x008.json"),
           "fuori": str(other / "HONE_8.json"),
           "relativo": "HONE_8.json",
           "unc": r"\\pc-altro\setups\HONE_8.json"}[bad]
    rig.drive(_snap(), _snap("lane"), _snap("box", psi=HONE_8_COLD))
    mark = (rig.eng.mark_setup_applied if route == "applied"
            else rig.eng.mark_base_confirmed)
    mark(path=raw)
    rig.drive(_snap("box", psi=HONE_8_COLD))
    assert rig.eng._expected_path is None
    assert rig.eng._written_path is None
    assert rig.engineer.bias_offset is None


def test_a_file_reloaded_by_hand_drops_the_wheel_changes(rig):
    rig.drive(_snap(tc=4))
    rig.engineer._record(_av("tC1"))                  # TC +1 tenuto: 3 + 1
    assert rig.engineer.carry_clicks() == {"tC1": 1}
    rig.drive(_snap("lane", tc=4), _snap("box", tc=4, psi=HONE_8_COLD))
    assert rig.block()["loaded"]["state"] == "match"   # file + manopola
    rig.drive(_snap("box", tc=3, psi=HONE_8_COLD))      # HONE_8 ricaricato
    assert rig.engineer.carry == []
    loaded = rig.block()["loaded"]
    assert loaded["state"] == "match" and loaded["name"] == "HONE_8"


def test_a_box_proposal_carries_the_wheel_changes(rig):
    rig.drive(_snap())
    rig.engineer._record(_av("brakeBias"))            # AV ripartitore tenuto
    box = _box_change()
    rig.eng._engineer_decision = Decision(DecisionKind.PROPOSE, box.rationale,
                                          change=box)
    block = rig.block()
    extra = {"param": "brakeBias", "slot": None, "delta_clicks": 1}
    assert block["change"] == box.as_setup_payload() + [extra]
    assert block["carry"] == [extra]
    # Una proposta al volo non le porta: si gira una manopola sola.
    av = _av("tC1")
    rig.eng._engineer_decision = Decision(DecisionKind.PROPOSE, av.rationale,
                                          change=av)
    assert rig.block()["change"] == av.as_setup_payload()
    assert rig.block()["carry"] is None


# --- Assetto Corsa e i guasti ------------------------------------------------

def test_assetto_corsa_stays_as_today(rig):
    rig.drive(_snap(acc=False), _snap("lane", acc=False),
              _snap("box", acc=False, psi=HONE_8_COLD), _snap(acc=False))
    assert rig.block()["loaded"] is None
    rig.engineer._record(_av("brakeBias"))
    box = _box_change()
    rig.eng._engineer_decision = Decision(DecisionKind.PROPOSE, box.rationale,
                                          change=box)
    assert rig.block()["change"] == box.as_setup_payload()
    assert rig.block()["carry"] is None


def test_a_failure_while_recognising_never_breaks_the_tick(rig, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disco")

    monkeypatch.setattr(store, "find_setup_files", boom)
    rig.drive(_snap(), _snap("lane"), _snap("box", psi=HONE_8_COLD),
              _snap("lane"), _snap())
    assert rig.block()["loaded"] is None


def test_a_long_stop_tolerates_repeated_readings(rig):
    """Le pressioni che scivolano su un decimo rifanno «live»: niente di male."""
    rig.drive(_snap(), _snap("lane"))
    for p in (25.5, 25.54, 25.56, 25.5, 25.56):
        rig.drive(_snap("box", psi=(p, 25.0, 24.7, 24.4)))
    assert rig.block()["loaded"]["name"] == "HONE_8"
    assert rig.eng._engineer_decision is None
