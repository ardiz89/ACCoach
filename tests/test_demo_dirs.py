"""Le cartelle della demo si puliscono da sole, e non mentre servono.

Trovato sulla macchina del pilota il 19/09: **376 cartelle** `accoach_demo_*` e
`accoach_webdemo_*` nel temp, 410 file, 5.7 MB, accumulate dal 26 giugno. Una
per ogni volta che la demo e' stata aperta, da sempre, e nessuno le toglie.

Non e' una questione di spazio — sono megabyte — ma di roba nostra lasciata a
casa di chi ci prova. E cresce: il numero non torna mai indietro da solo.

La cura che NON funziona qui e' `atexit`, e vale la pena scriverlo: il launcher
chiude i figli con `taskkill /F`, che non lascia girare nessun handler. Una
pulizia che si fida della chiusura ordinata non si eseguirebbe quasi mai — e
sarebbe una difesa che sembra esserci. Quindi si spazza **all'apertura**, che e'
l'unico momento garantito.
"""
import os
import time
from pathlib import Path

from accoach.paths import demo_dir, sweep_stale_demo_dirs


def _invecchia(path: Path, giorni: float) -> None:
    """Fa sembrare la cartella vecchia di `giorni`, senza aspettarli."""
    quando = time.time() - giorni * 86400
    os.utime(path, (quando, quando))


def test_una_cartella_nuova_nasce_vuota_e_nostra(tmp_path):
    d = demo_dir("prova_", root=tmp_path)
    assert d.is_dir() and not list(d.iterdir())
    assert d.name.startswith("prova_")
    assert d.parent == tmp_path


def test_le_cartelle_vecchie_se_ne_vanno(tmp_path):
    vecchia = demo_dir("prova_", root=tmp_path)
    (vecchia / "giro.json.gz").write_bytes(b"x")
    _invecchia(vecchia, giorni=3)

    demo_dir("prova_", root=tmp_path)          # una nuova apertura spazza

    assert not vecchia.exists(), "la cartella di tre giorni fa e' ancora li'"


def test_una_cartella_di_oggi_NON_viene_toccata(tmp_path):
    """La parte che conta: due demo aperte insieme non si rubano i file.

    Se la pulizia guardasse solo il prefisso, la seconda apertura porterebbe via
    i giri alla prima mentre li sta leggendo — cioe' la cura sarebbe peggio del
    difetto.
    """
    viva = demo_dir("prova_", root=tmp_path)
    (viva / "giro.json.gz").write_bytes(b"x")

    demo_dir("prova_", root=tmp_path)

    assert viva.exists() and (viva / "giro.json.gz").exists()


def test_la_spazzata_non_esce_dalle_cartelle_della_demo(tmp_path):
    """Un `rm -rf` su una cartella temporanea altrui sarebbe un difetto grave."""
    altrui = tmp_path / "roba_di_qualcun_altro"
    altrui.mkdir()
    (altrui / "importante.txt").write_text("non toccare", encoding="utf-8")
    _invecchia(altrui, giorni=30)

    sweep_stale_demo_dirs(prefix="prova_", root=tmp_path)

    assert (altrui / "importante.txt").exists()


def test_una_cartella_che_non_si_puo_togliere_non_ferma_la_demo(tmp_path,
                                                                monkeypatch):
    """Su Windows un file aperto da un altro processo non si cancella.

    La demo deve aprirsi lo stesso: la pulizia e' un servizio, non una
    precondizione. Prima di questa guardia un file bloccato avrebbe fatto
    fallire l'avvio della demo invece di lasciare indietro una cartella.
    """
    vecchia = demo_dir("prova_", root=tmp_path)
    _invecchia(vecchia, giorni=3)

    import shutil
    def esplode(*a, **k):
        raise PermissionError("il file e' in uso")
    monkeypatch.setattr(shutil, "rmtree", esplode)

    nuova = demo_dir("prova_", root=tmp_path)      # non deve sollevare
    assert nuova.is_dir()


def test_il_prefisso_e_quello_che_usa_la_demo_davvero():
    """Il test non decide il prefisso: lo legge da chi lo usa.

    Un test che scrive `accoach_demo_` a mano continuerebbe a passare il giorno
    in cui la demo cambia nome alle sue cartelle, e la spazzata smetterebbe di
    trovarle senza che nessuno lo noti.
    """
    import inspect

    from accoach import api, demo

    for modulo in (demo.make_demo_engine, api._seed_demo):
        sorgente = inspect.getsource(modulo)
        assert "demo_dir(" in sorgente, (
            f"{modulo.__name__} non passa da demo_dir: la sua cartella non "
            f"verra' mai spazzata")
        assert "mkdtemp" not in sorgente, (
            f"{modulo.__name__} crea ancora la cartella per conto suo")
