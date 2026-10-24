"""Il lock delle dipendenze: versione esatta e impronta per ogni pacchetto.

Senza lock una release poteva montare, il giorno del tag, qualunque versione
uscita su PyPI in quelle ore. Questi test non installano niente: guardano che
il file sia fatto come deve e che la release lo usi davvero. Un lock che nessun
workflow legge, o che non copre una riga di requirements.txt, non protegge.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements.lock"
REQ = ROOT / "requirements.txt"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


# Backslash in fondo alla riga: pip-compile spezza cosi' le impronte.
CONTINUA = chr(92) + chr(10)


def _norm(name: str) -> str:
    # PEP 503: maiuscole, punti, trattini e underscore sono lo stesso nome.
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_entries() -> dict:
    """nome normalizzato -> (versione, [impronte]); legge i blocchi del lock."""
    text = LOCK.read_text(encoding="utf-8").replace(CONTINUA, " ")
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==(\S+)(.*)$", line)
        if m:
            out[_norm(m.group(1))] = (m.group(3), re.findall(r"--hash=sha256:[0-9a-f]{64}", m.group(4)))
    return out


def _req_names() -> list:
    names = []
    for line in REQ.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if m:
            names.append(_norm(m.group(1)))
    return names


def test_ogni_riga_del_lock_ha_versione_e_impronta():
    text = LOCK.read_text(encoding="utf-8").replace(CONTINUA, " ")
    righe = [l.strip() for l in text.splitlines()
             if l.strip() and not l.lstrip().startswith(("#", "--"))]
    assert righe, "lock vuoto"
    for riga in righe:
        assert re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]*\])?==\S+", riga), riga
        assert "--hash=sha256:" in riga, f"senza impronta: {riga[:60]}"
    assert len(_lock_entries()) == len(righe)


def test_ogni_dipendenza_di_requirements_txt_e_nel_lock():
    lock = _lock_entries()
    nomi = _req_names()
    assert nomi, "requirements.txt illeggibile"
    for nome in nomi:
        assert nome in lock, f"{nome} manca dal lock"


def test_pyinstaller_e_nel_lock_e_pyside6_sotto_612():
    lock = _lock_entries()
    assert "pyinstaller" in lock
    versione = lock["pyside6"][0]
    major, minor = (int(x) for x in versione.split(".")[:2])
    assert (major, minor) < (6, 12), f"PySide6 {versione}: il tetto 6.12 e' saltato"


def test_la_release_installa_dal_lock_con_le_impronte_e_senza_cache():
    righe = [l.split("#", 1)[0] for l in RELEASE.read_text(encoding="utf-8").splitlines()]
    codice = "\n".join(righe)
    assert re.search(r"pip install\s+--require-hashes\s+--only-binary :all:\s+-r\s+requirements\.lock", codice)
    assert "requirements.txt" not in codice
    assert "cache: pip" not in codice


def test_la_release_non_ha_altri_pip_install_senza_impronte():
    # Un pip aggiornato al volo, senza versione ne' impronta, sarebbe la porta
    # da cui il lock si aggira proprio nel job che costruisce l'EXE.
    codice = "\n".join(l.split("#", 1)[0] for l in RELEASE.read_text(encoding="utf-8").splitlines())
    installi = re.findall(r"pip\s+install\b[^\n]*", codice)
    assert installi, "nessun pip install nella release"
    for riga in installi:
        assert "--require-hashes" in riga and "-r requirements.lock" in riga, riga
        assert "--only-binary :all:" in riga, riga
