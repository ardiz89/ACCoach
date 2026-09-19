"""Shared, user-writable locations for ACCoach data, logs and config.

Everything lives under ``~/Documents/ACCoach`` so the paths are identical from
source and from the frozen exe (a path relative to ``__file__`` is meaningless
once PyInstaller-frozen, and may be read-only). Single source of truth — other
modules should import from here instead of recomputing ``Path.home() / ...``.
"""

from __future__ import annotations

from pathlib import Path


def base_dir() -> Path:
    return Path.home() / "Documents" / "ACCoach"


def laps_dir() -> Path:
    """Dove stanno i giri: quella configurata, o la predefinita.

    `data.laps_dir` esisteva da tempo e **la onorava solo l'app web**: il motore
    live, il registratore, il debrief, la Home dell'hub e l'import PRO usavano
    tutti la cartella predefinita. Se lo impostavi, guidavi una sessione e aprivi
    Analisi trovavi la pagina **vuota** — mentre la Home continuava a mostrare
    quella stessa sessione, perché leggeva altrove. L'app si contraddiceva da
    sola, e il sintomo somigliava a una perdita di dati.

    La lettura sta qui e non nei chiamanti perché era proprio la dispersione il
    difetto. `load_config()` è in cache, quindi costa un accesso a dizionario.
    """
    from .config import load_config  # locale: config importa questo modulo

    try:
        configured = load_config().data.laps_dir
    except Exception:   # noqa: BLE001 - una config illeggibile non sposta i giri
        configured = ""
    return Path(configured).expanduser() if configured else base_dir() / "laps"


def logs_dir() -> Path:
    return base_dir() / "logs"


def config_path() -> Path:
    return base_dir() / "config.toml"


# --- le cartelle usa-e-getta della demo ------------------------------------
#
# La demo ha bisogno di un archivio giri finto, e lo mette in una cartella
# temporanea. Il difetto e' che non la toglieva mai piu': sulla macchina del
# pilota, il 19/09, c'erano **376** cartelle `accoach_demo_*`/`accoach_webdemo_*`
# con 410 file, accumulate dal 26 giugno. Una per ogni apertura della demo, da
# sempre.
#
# Perche' si spazza all'APERTURA e non alla chiusura: il launcher termina i
# processi figli con `taskkill /F`, che non lascia girare nessun `atexit`. Una
# pulizia appesa alla chiusura ordinata non si eseguirebbe quasi mai — sarebbe
# una difesa che sembra esserci, che in questo progetto e' la forma di difetto
# che ci costa di piu'. L'apertura invece succede sempre.
_DEMO_TTL_S = 86_400.0        # un giorno: piu' lunga di qualunque sessione


def sweep_stale_demo_dirs(*, prefix: str, root: "Path | None" = None,
                          ttl_s: float = _DEMO_TTL_S) -> int:
    """Toglie le cartelle della demo piu' vecchie di ``ttl_s``. Torna quante.

    Guarda **solo** i figli diretti che portano ``prefix``: la cartella
    temporanea di qualcun altro non si tocca. E una che non si lascia togliere
    (su Windows basta un file ancora aperto) viene saltata in silenzio — la
    pulizia e' un servizio, non una precondizione per aprire la demo.
    """
    import shutil
    import tempfile
    import time

    base = Path(root) if root is not None else Path(tempfile.gettempdir())
    adesso = time.time()
    tolte = 0
    for d in base.glob(prefix + "*"):
        try:
            if not d.is_dir() or adesso - d.stat().st_mtime < ttl_s:
                continue
            shutil.rmtree(d)
            tolte += 1
        except OSError:
            continue          # in uso, o non nostra: non e' un problema nostro
    return tolte


def demo_dir(prefix: str = "accoach_demo_", *, root: "Path | None" = None) -> Path:
    """Una cartella nuova per questa demo, dopo aver tolto quelle vecchie.

    Le cartelle *di oggi* restano: due demo aperte insieme non devono rubarsi i
    file da sotto, che sarebbe una cura peggiore del difetto.
    """
    import tempfile

    sweep_stale_demo_dirs(prefix=prefix, root=root)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(root) if root else None))
