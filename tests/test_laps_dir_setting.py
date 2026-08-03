"""`data.laps_dir` deve valere per tutti, o per nessuno.

Diceva dove tenere i giri (un altro SSD, una cartella sincronizzata) e **la
onorava solo l'app web**. Il motore live, il registratore, il debrief, la Home
dell'hub e l'import PRO usavano tutti la cartella predefinita.

Quindi: lo impostavi, guidavi una sessione, aprivi Analisi — pagina **vuota**,
perché il registratore aveva scritto in `Documents\\ACCoach\\laps` e il report
guardava altrove. La Home dell'hub però continuava a mostrare quella stessa
sessione, perché leggeva dal default. L'app si contraddiceva da sola, e il
sintomo somigliava a una perdita di dati.

La causa era strutturale, e vale la pena tenerla ferma: `DEFAULT_LAPS_DIR` era
una **costante calcolata all'import**, usata come valore di default in una
decina di firme. Una costante d'import non può vedere la configurazione
dell'utente, qualunque cosa scriva.
"""
import accoach.config as cfg_mod
import pytest

from accoach import paths
from accoach.recording import laps_root


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Una config che chiede una cartella diversa da quella predefinita."""
    cfg = cfg_mod.Config()
    cfg.data.laps_dir = str(tmp_path / "giri-altrove")
    monkeypatch.setattr(cfg_mod, "load_config", lambda *a, **k: cfg)
    return tmp_path / "giri-altrove"


def test_the_setting_moves_the_laps_directory(configured):
    assert paths.laps_dir() == configured
    assert laps_root() == configured


def test_an_empty_setting_keeps_the_default(monkeypatch):
    cfg = cfg_mod.Config()
    monkeypatch.setattr(cfg_mod, "load_config", lambda *a, **k: cfg)
    assert paths.laps_dir() == paths.base_dir() / "laps"


def test_an_unreadable_config_does_not_move_the_laps(monkeypatch):
    """Se la config esplode, i giri restano dove sono: perderli di vista è un
    danno peggiore di un'impostazione ignorata."""
    def boom(*a, **k):
        raise OSError("config gone")

    monkeypatch.setattr(cfg_mod, "load_config", boom)
    assert paths.laps_dir() == paths.base_dir() / "laps"


def test_a_tilde_in_the_path_is_expanded(monkeypatch):
    cfg = cfg_mod.Config()
    cfg.data.laps_dir = "~/giri"
    monkeypatch.setattr(cfg_mod, "load_config", lambda *a, **k: cfg)
    assert "~" not in str(paths.laps_dir())


# --- e adesso tutti la vedono ---------------------------------------------

def test_the_live_engine_writes_where_the_setting_says(configured):
    """`app.py` e `server.py` costruiscono il motore senza passare `laps_dir`:
    è esattamente il chiamante che se ne dimenticava."""
    from accoach.engine import CoachEngine

    class _R:
        def read(self):
            from accoach.telemetry.snapshot import TelemetrySnapshot
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_R(), voice=None)
    assert eng.laps_dir == configured


def test_saving_a_lap_lands_there_too(configured):
    from accoach.recording.storage import save_lap

    import synth

    path = save_lap(synth.build_lap())
    assert path.parent == configured


def test_the_hub_home_reads_the_same_place(configured):
    """Era la metà che leggeva altrove, e per questo mostrava una sessione che
    il report giurava non esistere."""
    import inspect

    from accoach import hub_home

    src = inspect.getsource(hub_home)
    assert "laps_root()" in src
    assert "DEFAULT_LAPS_DIR" not in src


def test_the_import_time_constant_is_gone():
    """La causa vera. Finché era una costante d'import, qualunque firma che la
    usasse come default era cieca alla configurazione — e riaggiungerla
    rimetterebbe il difetto senza che nessun test se ne accorga."""
    import accoach.recording as rec
    import accoach.recording.storage as storage

    assert not hasattr(rec, "DEFAULT_LAPS_DIR")
    assert not hasattr(storage, "DEFAULT_LAPS_DIR")
    assert callable(storage.laps_root)
