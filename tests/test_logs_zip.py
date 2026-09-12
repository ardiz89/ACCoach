"""`logs --zip`: la segnalazione di un beta tester diventa un pacchetto.

Finora `logs` apriva una cartella in Explorer, e nient'altro impacchettava
niente. Senza pacchetto la segnalazione e' «non ho sentito niente», che in
questo progetto sappiamo essere indistinguibile da un guasto muto: il 12/08 la
voce si era piantata in silenzio — thread vivo, nessuna eccezione — e solo il
log lo diceva.

Due casi che il fixture tende a far coincidere e che qui sono tenuti diversi
apposta: **log presenti** e **cartella vuota o inesistente**. Un comando
diagnostico che fallisce proprio quando le cose vanno male e' inutile, quindi
lo ZIP deve nascere anche al primo avvio, e il contesto deve *dire* che di log
non ce n'erano — invece di lasciar credere che siano andati persi.
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

import pytest

import accoach.__main__ as cli
from accoach import support


@pytest.fixture
def _quiet_logging(monkeypatch):
    """`main()` chiama `setup_logging()` prima di smistare, e quello configura
    il logger globale `accoach` (propagate=False, handler su file) *e scrive
    nella cartella dei log vera*: `logging_setup` importa `logs_dir` al
    caricamento, quindi rimpiazzarlo in `paths` non lo sposta. Lasciandolo
    girare, i test che dopo leggono i log con `caplog` non vedono piu' niente —
    l'ho misurato: 5 test altrove diventavano rossi solo per l'ordine."""
    from accoach import logging_setup
    monkeypatch.setattr(logging_setup, "setup_logging", lambda *a, **k: None)


def _names(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        return sorted(z.namelist())


def _contesto(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        return z.read(support.CONTEXT_NAME).decode("utf-8")


# --- lo ZIP -------------------------------------------------------------------

def test_lo_zip_porta_dentro_i_log_e_il_contesto(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "accoach.log").write_text("riga di log\n", encoding="utf-8")
    (logs / "crash-20260912-101500.log").write_text("boom\n", encoding="utf-8")

    z = support.build_log_zip(dest_dir=tmp_path / "out", source=logs)

    assert z.exists()
    assert _names(z) == [
        support.CONTEXT_NAME,
        "logs/accoach.log",
        "logs/crash-20260912-101500.log",
    ]
    with zipfile.ZipFile(z) as zf:
        # Byte per byte: un log che arriva troncato o riscritto non serve.
        assert zf.read("logs/accoach.log") == (logs / "accoach.log").read_bytes()


def test_lo_zip_nasce_anche_con_la_cartella_vuota(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()

    z = support.build_log_zip(dest_dir=tmp_path / "out", source=logs)

    assert z.exists()
    assert _names(z) == [support.CONTEXT_NAME]


def test_lo_zip_nasce_anche_se_la_cartella_non_esiste(tmp_path):
    z = support.build_log_zip(dest_dir=tmp_path / "out",
                              source=tmp_path / "mai-vista")

    assert z.exists()
    assert _names(z) == [support.CONTEXT_NAME]


def test_il_contesto_distingue_i_log_presenti_dalla_cartella_vuota(tmp_path):
    """I due casi devono leggersi DIVERSI: e' l'unica cosa che dice a chi legge
    la segnalazione se i log mancano o se non sono stati raccolti."""
    pieno = tmp_path / "pieni"
    pieno.mkdir()
    (pieno / "accoach.log").write_text("x\n", encoding="utf-8")
    vuoto = tmp_path / "vuoti"
    vuoto.mkdir()

    con_log = _contesto(support.build_log_zip(dest_dir=tmp_path / "a", source=pieno))
    senza = _contesto(support.build_log_zip(dest_dir=tmp_path / "b", source=vuoto))

    assert "accoach.log" in con_log
    assert "accoach.log" not in senza
    assert support.NO_LOGS in senza
    assert support.NO_LOGS not in con_log


def test_lo_zip_finisce_in_documenti_accoach(tmp_path, monkeypatch):
    from accoach import paths
    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path / "Documents" / "ACCoach")
    logs = tmp_path / "logs"
    logs.mkdir()

    z = support.build_log_zip(source=logs)

    assert z.parent == tmp_path / "Documents" / "ACCoach"
    assert z.suffix == ".zip"


def test_il_nome_dello_zip_porta_la_data(tmp_path):
    z = support.build_log_zip(dest_dir=tmp_path, source=tmp_path / "vuoto",
                              now=datetime(2026, 9, 12, 15, 30, 0))
    assert z.name == "hone-log-20260912-153000.zip"


# --- il file di contesto ------------------------------------------------------

def test_il_contesto_dice_versione_python_e_sistema():
    import platform

    from accoach import __version__

    text = support.context_report(logs=[], combos=[])

    assert __version__ in text
    assert platform.python_version() in text
    assert platform.platform() in text


def test_il_contesto_non_porta_fuori_dati_personali(tmp_path):
    """Niente oltre a cio' che sta gia' dentro i log: nessun percorso utente
    (che contiene il nome dell'account) e nessun indirizzo email."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "accoach.log").write_text("x\n", encoding="utf-8")

    text = _contesto(support.build_log_zip(dest_dir=tmp_path / "o", source=logs))

    assert str(Path.home()) not in text
    assert str(logs) not in text
    assert "@" not in text


def test_il_contesto_elenca_le_ultime_auto_e_piste():
    text = support.context_report(logs=[], combos=["720S / monza", "GT3 / imola"])
    assert "720S / monza" in text
    assert "GT3 / imola" in text


def test_il_contesto_lo_dice_quando_le_auto_non_si_sanno():
    text = support.context_report(logs=[], combos=[])
    assert support.NO_COMBOS in text


# --- il commit ----------------------------------------------------------------

def test_il_commit_si_legge_da_un_checkout(tmp_path):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text(
        "0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8")

    assert support.git_commit(tmp_path / "src" / "accoach") == "0123456"


def test_il_commit_si_legge_anche_da_packed_refs(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted \n"
        "fedcba9876543210fedcba9876543210fedcba98 refs/heads/main\n",
        encoding="utf-8")

    assert support.git_commit(tmp_path) == "fedcba9"


def test_il_commit_e_sconosciuto_fuori_da_un_checkout(tmp_path):
    assert support.git_commit(tmp_path) == ""


# --- la riga di comando -------------------------------------------------------

def test_logs_senza_argomenti_fa_ancora_solo_quello_che_faceva(monkeypatch, capsys,
                                                               tmp_path,
                                                               _quiet_logging):
    """La regola piu' importante: `logs` da solo non cambia comportamento."""
    from accoach import paths
    d = tmp_path / "logs"
    monkeypatch.setattr(paths, "logs_dir", lambda: d)
    aperte: list[Path] = []
    monkeypatch.setattr("os.startfile", lambda p: aperte.append(Path(p)),
                        raising=False)
    impacchettati: list[object] = []
    monkeypatch.setattr(support, "build_log_zip",
                        lambda *a, **k: impacchettati.append(1))
    monkeypatch.setattr(cli.sys, "argv", ["accoach", "logs"])

    cli.main()

    out = capsys.readouterr().out
    assert str(d) in out
    assert aperte == [d]
    assert impacchettati == []


def test_logs_zip_impacchetta_stampa_il_percorso_e_non_apre_explorer(monkeypatch,
                                                                     capsys,
                                                                     tmp_path,
                                                                     _quiet_logging):
    from accoach import paths
    d = tmp_path / "logs"
    d.mkdir()
    (d / "accoach.log").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(paths, "logs_dir", lambda: d)
    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path / "base")
    aperte: list[Path] = []
    monkeypatch.setattr("os.startfile", lambda p: aperte.append(Path(p)),
                        raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["accoach", "logs", "--zip"])

    cli.main()

    out = capsys.readouterr().out
    zips = list((tmp_path / "base").glob("*.zip"))
    assert len(zips) == 1
    assert str(zips[0]) in out
    assert aperte == []
    assert "logs/accoach.log" in _names(zips[0])
