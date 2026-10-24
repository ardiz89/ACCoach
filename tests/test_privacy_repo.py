"""Il repo e' pubblico: il nome dell'account Windows del pilota non ci sta.

Il nome e' gia' nella storia di git e non e' un segreto, ma ogni file nuovo
che lo ripete e' un'altra copia da tenere pulita. Il test non conosce il nome
vero: prende quello che sta dopo "Users" e lo confronta con un elenco di
segnaposto dichiarati. Qualunque altro nome fa fallire il test, il pilota o
un altro.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Nome catturato dopo "Users", in tre scritture: con la lettera di unita' e la
# barra rovescia, con la barra dritta, e come la stampa Git Bash (/c/ davanti).
_PERCORSO = re.compile(
    r"(?:[A-Za-z]:[\\/]+|(?<![A-Za-z0-9])/[A-Za-z]/)"
    r"Users[\\/]+([^\\/\s\"'<>%`*]+)",
    re.IGNORECASE,
)

# Segnaposto e nomi di esempio, nessuno e' un account vero. Il confronto
# ignora le maiuscole, perche' Windows le ignora.
AMMESSI = {
    "pilot": "il nome finto che usano i test e le guide",
    "pilota-finto": "la casa finta del piano di sicurezza, scritta cosi' apposta",
    "public": "la cartella `Public` che Windows crea in ogni installazione",
    "default": "il profilo modello `Default` di Windows",
    "runneradmin": "l'account del runner di GitHub Actions",
    "...": "i puntini di un percorso abbreviato in un esempio",
}


def _file_di_testo() -> list[tuple[str, str]]:
    elenco = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True,
        capture_output=True).stdout.split(b"\0")
    out = []
    for raw in elenco:
        if not raw:
            continue
        nome = raw.decode("utf-8")
        p = ROOT / nome
        if not p.is_file():
            continue
        dati = p.read_bytes()
        if b"\0" in dati[:8192]:      # binario: docx, wav, png...
            continue
        try:
            out.append((nome, dati.decode("utf-8")))
        except UnicodeDecodeError:
            continue
    return out


def test_nessun_nome_di_account_vero_nei_file_tracciati():
    trovati = []
    for nome, testo in _file_di_testo():
        for n, riga in enumerate(testo.splitlines(), 1):
            for m in _PERCORSO.finditer(riga):
                if m.group(1).lower() not in AMMESSI:
                    # Il nome non finisce mai nel messaggio: se fallisce,
                    # il fallimento non deve diventare un'altra copia.
                    trovati.append(f"{nome}:{n}  <account>")
    assert not trovati, (
        "Nomi di account non ammessi nei file tracciati (usa %USERPROFILE%, "
        "C:\\Users\\<account> oppure C:\\Users\\pilot nei test)\n" + "\n".join(trovati))


def test_il_riconoscitore_prende_le_tre_scritture_e_lascia_i_segnaposto():
    def nomi(s):
        return [m.group(1) for m in _PERCORSO.finditer(s)]

    assert nomi(r"C:\Users\pilot\Documents") == ["pilot"]
    assert nomi("c:/users/pilot/x") == ["pilot"]
    assert nomi("/c/Users/pilot/x") == ["pilot"]
    assert nomi(r"C:\Users\<account>\x") == []
    assert nomi(r"%USERPROFILE%\Documents") == []
    assert nomi("/home/runner/c/users") == []


def test_gitignore_ignora_cio_che_non_deve_finire_nel_repo():
    for p in ("tools/.dl/x", ".superpowers/x", "config.toml", "a.key",
              ".env", ".env.local", ".elevenlabs-key", "x/mia-elevenlabs-key.txt",
              "a.db", "a.sqlite", "a.sqlite3"):
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        assert r.returncode == 0, f"{p} non e' ignorato"
