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

import re
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


# --- la dichiarazione si misura sul pacchetto, non su se stessa ----------------
# Il contesto diceva «No paths, machine name or account details are included»:
# vero del file che la contiene, FALSO del pacchetto in cui quel file vive —
# accanto c'e' `logs/accoach.log`, che i percorsi assoluti col nome dell'account
# Windows ce li ha eccome, e non li filtriamo apposta (un log ripulito non
# diagnostica niente). Un tester che legge quella riga crede di mandare un
# pacchetto pulito.
#
# Questi helper NON cercano la frase: cercano la *proprieta'*. Una riscrittura
# che torni a promettere un pacchetto senza percorsi li fa cadere comunque.

#: Un percorso utente vero e proprio, quello che il nome dell'account se lo porta
#: dietro. Il segnaposto che il contesto usa per spiegarsi (`<account>`) non e'
#: uno di questi: qui si cerca un segmento reale.
_USER_PATH = re.compile(r"[A-Za-z]:[\\/]Users[\\/](?!<)[^\\/\s<>]+", re.I)
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
_LAP_TIME = re.compile(r"\d+m\d+s\d+")

#: Le categorie di dato che il pacchetto puo' portare fuori, e le parole con cui
#: un testo puo' nominarle. Il difetto precedente era che il controllo guardava
#: SOLO la parola «path»: una bugia sul nome dell'account («Your Windows account
#: name appears nowhere in this bundle») passava con 17 test verdi. Le categorie
#: si rilevano da cosa c'e' DAVVERO negli allegati, non da cosa dice il testo.
_CATEGORY_WORDS = {
    "paths": ("path", "folder", "directory", "location"),
    "account name": ("account", "user name", "username", "who you are"),
    "when you drove": ("dated", "when you", "you drove", "timestamp", "history"),
    "lap times": ("lap time", "your times", "times you", "how fast"),
    "crash reports": ("crash", "traceback", "stack trace"),
}

#: Modi di negare. Larga apposta, e la larghezza e' *provata* dalla batteria di
#: bugie in `test_ogni_bugia_sul_contenuto_viene_intercettata`: una negazione e'
#: per forza lessicale, quindi l'unica difesa onesta e' mutare con parole
#: diverse e far vedere che cadono tutte.
_NEGATIONS = ("no ", "not ", "never", "none", "nothing", "nowhere", "without",
              "n't", "free of", "stripped", "removed", "excluded", "redact",
              "anonymi", "anonymo", "scrub", "sanitiz", "sanitis", "zero ")


def _facts_in_attachments(zip_path: Path) -> set[str]:
    """Le categorie che il pacchetto porta fuori DAVVERO, lette dagli allegati.

    Il file di contesto non si conta: e' lui l'imputato, non la prova.
    """
    facts: set[str] = set()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name == support.CONTEXT_NAME:
                continue
            if Path(name).name.startswith("crash-"):
                facts.add("crash reports")
            body = z.read(name).decode("utf-8", "replace")
            if _USER_PATH.search(body):
                facts |= {"paths", "account name"}
            if _TIMESTAMP.search(body):
                facts.add("when you drove")
            if _LAP_TIME.search(body):
                facts.add("lap times")
    return facts


def _sentences(text: str) -> list[str]:
    """Frasi, per blocchi separati da riga vuota.

    Prima flattenavo tutto il file in una stringa sola: il contesto e' fatto di
    etichette senza punti fermi, quindi l'intestazione (che dice «log») finiva
    incollata alla dichiarazione (che dice «path») e il controllo passava con la
    frase vecchia. Un test verde che non provava niente — il secondo test della
    coppia l'ha smascherato, non una rilettura.
    """
    out = []
    for block in text.split("\n\n"):
        flat = " ".join(block.split())
        out += [s for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]
    return out


def _is_scoped(low: str) -> bool:
    """La frase dice di *quale parte* del pacchetto parla.

    Dentro uno ZIP con dentro altri file, «questo file» e' proprio l'ambiguita'
    che ha creato il difetto: non conta come ambito. Contano il nome del file di
    contesto, oppure i log.
    """
    return support.CONTEXT_NAME in low or "log" in low


def _declaration_block(text: str) -> str:
    """Solo la dichiarazione: l'ultimo blocco, dopo l'ultima riga vuota.

    Sul testo intero il controllo passava per il motivo sbagliato — misurato:
    tolta la categoria «crash reports» dalla dichiarazione, il test restava
    verde perche' la parola «crash» compariva nell'ELENCO DEI FILE
    dell'intestazione (`crash-20260628-002505.log`). Il nome di un allegato non
    e' una dichiarazione di cosa quell'allegato contiene.
    """
    return text.rstrip("\n").split("\n\n")[-1]


def _categories_declared_as_present(text: str) -> set[str]:
    """Le categorie che la dichiarazione nomina **senza negarle**.

    Una frase negativa non dichiara niente: dire «no paths» non e' dire «ci sono
    dei percorsi». Serve la distinzione, altrimenti la riga su `contesto.txt`
    (che nega, correttamente) verrebbe contata come dichiarazione.
    """
    return _categories_named_affirmatively(_declaration_block(text))


def _categories_named_affirmatively(text: str) -> set[str]:
    found: set[str] = set()
    for s in _sentences(text):
        low = s.lower()
        if any(n in low for n in _NEGATIONS):
            continue
        for cat, words in _CATEGORY_WORDS.items():
            if any(w in low for w in words):
                found.add(cat)
    return found


def _denials_of_what_the_bundle_carries(text: str, facts: set[str]) -> list[str]:
    """Frasi che negano un dato che il pacchetto porta fuori davvero.

    La proprieta' difesa, e non piu' «non c'e' la parola path»: per **ogni**
    categoria che gli allegati contengono per davvero, nessuna frase puo'
    negarla senza dire di quale parte del pacchetto sta parlando — con qualunque
    parola la neghi.
    """
    out = []
    for s in _sentences(text):
        low = s.lower()
        if not any(n in low for n in _NEGATIONS) or _is_scoped(low):
            continue
        for cat in sorted(facts):
            if any(w in low for w in _CATEGORY_WORDS[cat]):
                out.append(f"[{cat}] {s}")
                break
    return out


def _unscoped_negations(text: str) -> list[str]:
    """Rete di sicurezza: qualunque negazione che non dica di cosa parla.

    Prende anche le categorie che non ho previsto — il vocabolario di
    `_CATEGORY_WORDS` e' una lista, e una lista si dimentica.
    """
    return [s for s in _sentences(text)
            if any(n in s.lower() for n in _NEGATIONS) and not _is_scoped(s.lower())]


def _con_tutto_dentro(tmp_path: Path) -> Path:
    """Una cartella di log con dentro le quattro categorie, tenute distinte."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "accoach.log").write_text(
        "2026-06-28 00:25:05 INFO accoach: === ACCoach 0.1.0 starting ===\n"
        "2026-06-28 00:31:12 INFO accoach.recording: saved "
        "mclaren-720s__monza__1m54s3__20260628-003112.json.gz\n"
        "2026-06-28 00:25:05 ERROR accoach: crash report written to "
        r"C:\Users\undrg\Documents\ACCoach\logs\crash-20260628-002505.log" "\n",
        encoding="utf-8")
    (logs / "crash-20260628-002505.log").write_text(
        "ACCoach 0.1.0 crash\nTraceback (most recent call last):\n"
        r"  File C:\Users\undrg\progetti\ACCoach\src\accoach\app.py, line 1" "\n",
        encoding="utf-8")
    return logs


def test_la_dichiarazione_nomina_tutto_quello_che_il_pacchetto_porta_fuori(tmp_path):
    z = support.build_log_zip(dest_dir=tmp_path / "out",
                              source=_con_tutto_dentro(tmp_path))
    text = _contesto(z)
    facts = _facts_in_attachments(z)

    # Precondizione: senza questa il test non proverebbe niente.
    assert facts == {"paths", "account name", "when you drove", "lap times",
                     "crash reports"}, facts
    # (a) ogni categoria che esce davvero e' nominata, non solo una parte.
    assert facts - _categories_declared_as_present(text) == set(), text
    # (b) e nessuna frase nega un dato che invece esce.
    assert _denials_of_what_the_bundle_carries(text, facts) == []
    assert _unscoped_negations(text) == []


@pytest.mark.parametrize("bugia", [
    # Quella dimostrata dal fact-check: passava con 17 test verdi perche' il
    # controllo scartava ogni frase senza la parola «path».
    "Your Windows account name appears nowhere in this bundle.",
    "This bundle is free of personal paths.",
    "Lap times have been removed before packaging.",
    "The crash reports are anonymised.",
    "Nothing here identifies your account.",
    "We never include the times you drove.",
    "Every location has been stripped out.",
])
def test_ogni_bugia_sul_contenuto_viene_intercettata(tmp_path, monkeypatch, bugia):
    """Sette modi diversi di mentire sulla stessa sostanza.

    Una negazione e' per forza lessicale: l'unica difesa onesta e' mutare con
    parole diverse e far vedere che cadono tutte, invece di proteggere una
    parola sola.
    """
    vero = support._disclosure
    monkeypatch.setattr(support, "_disclosure",
                        lambda has_logs: vero(has_logs) + [f"  {bugia}"])

    z = support.build_log_zip(dest_dir=tmp_path / "out",
                              source=_con_tutto_dentro(tmp_path))
    text = _contesto(z)
    facts = _facts_in_attachments(z)

    assert _denials_of_what_the_bundle_carries(text, facts) != [], bugia


def test_senza_allegati_non_c_e_niente_da_dichiarare(tmp_path):
    """L'altra meta' della coppia, tenuta diversa apposta: se non si allega
    niente, non c'e' niente di non filtrato di cui avvisare. Se l'avviso
    comparisse comunque sarebbe una formula, non una dichiarazione."""
    vuoto = tmp_path / "logs"
    vuoto.mkdir()

    z = support.build_log_zip(dest_dir=tmp_path / "out", source=vuoto)
    text = _contesto(z)

    assert _facts_in_attachments(z) == set()
    assert _categories_declared_as_present(text) == set(), text
    assert _unscoped_negations(text) == []


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


def test_logs_zip_avvisa_a_schermo_senza_far_aprire_l_archivio(monkeypatch, capsys,
                                                               tmp_path,
                                                               _quiet_logging):
    """Il comando stampava solo il percorso: per sapere cosa stava per mandare,
    un tester doveva aprire lo ZIP e leggere `contesto.txt`. La dichiarazione
    deve arrivare dove arriva il comando."""
    from accoach import paths
    monkeypatch.setattr(paths, "logs_dir", lambda: _con_tutto_dentro(tmp_path))
    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path / "base")
    monkeypatch.setattr("os.startfile", lambda p: None, raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["accoach", "logs", "--zip"])

    cli.main()

    out = capsys.readouterr().out
    z = next((tmp_path / "base").glob("*.zip"))
    facts = _facts_in_attachments(z)

    assert facts, "precondizione: il pacchetto deve portare fuori qualcosa"
    # Non muto: a schermo si nomina cio' che esce davvero.
    assert _categories_named_affirmatively(out) & facts, out
    # E la versione breve non puo' contraddire quella lunga.
    assert _denials_of_what_the_bundle_carries(out, facts) == []
    # Dove sta scritto il resto.
    assert support.CONTEXT_NAME in out
