"""La suite non scrive nella cartella di casa di chi la lancia.

Scoperto il 24/10: lanciata senza una casa finta, la suite ha creato
``config.toml`` e aperto ``laps/catalog.db`` nella ``Documents\\ACCoach`` del
pilota. Le pezze di ``conftest.py`` (config, log, chiave) coprono i nomi che
conoscono; questi due test passavano da un'altra strada. Qui si prova il
risultato, non la strada: si lancia la suite su quei due test con una casa
vuota e la casa deve restare vuota.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# I due test che il 24/10 scrivevano nella casa vera.
COLPEVOLI = [
    "tests/test_acc_out_lap_crossing.py::test_the_first_flying_lap_after_the_pits_survives",
    "tests/test_engine_integration.py::test_engine_tick_runs_clean_and_speaks",
]


def test_la_suite_lascia_vuota_la_casa_di_chi_la_lancia(tmp_path):
    casa = tmp_path / "casa"
    casa.mkdir()
    env = dict(os.environ, USERPROFILE=str(casa), HOME=str(casa))
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *COLPEVOLI],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert not (casa / "Documents").exists(), sorted(
        str(p.relative_to(casa)) for p in casa.rglob("*"))


def test_dentro_la_suite_la_casa_e_finta():
    import conftest
    assert Path.home() == conftest.CASA_FINTA
    assert Path.home() != conftest.CASA_VERA
