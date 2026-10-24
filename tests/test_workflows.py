"""I workflow di GitHub: azioni fissate, permessi minimi, provenienza dell'EXE.

Un `uses: actions/checkout@v4` segue un tag che il proprietario dell'azione
puo' spostare quando vuole: il giorno della release gira il codice che c'e'
dietro quel tag in quel momento, dentro il job che costruisce l'EXE. Fissato a
uno SHA di 40 caratteri, gira quello che e' stato letto qui.

I test leggono il testo dei .yml senza un parser YAML: niente dipendenze nuove,
e i controlli che servono sono di riga o di blocco.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"
CI = WORKFLOWS / "ci.yml"
SPEC = ROOT / "HONE.spec"


def _workflow():
    files = sorted(WORKFLOWS.glob("*.yml"))
    assert files, "nessun workflow trovato"
    return files


def _senza_commenti(testo):
    return [l for l in testo.splitlines() if not l.lstrip().startswith("#")]


def _blocchi_run(testo):
    """Il testo di ogni `run:`, sia in linea sia a blocco (`run: |`)."""
    righe = testo.splitlines()
    blocchi = []
    i = 0
    while i < len(righe):
        m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", righe[i])
        if not m:
            i += 1
            continue
        rientro = len(m.group(1))
        resto = m.group(2)
        corpo = []
        if resto and not resto.startswith(("|", ">")):
            corpo.append(resto)
            i += 1
        else:
            i += 1
            while i < len(righe) and (not righe[i].strip()
                                      or len(righe[i]) - len(righe[i].lstrip()) > rientro):
                corpo.append(righe[i])
                i += 1
        blocchi.append("\n".join(corpo))
    return blocchi


def _job(testo, nome):
    """Il testo del job `nome`, dalla sua riga fino al job successivo."""
    m = re.search(rf"^  {re.escape(nome)}:\s*$(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
                  testo, re.M | re.S)
    assert m, f"job {nome!r} non trovato"
    return m.group(1)


def _testa(testo):
    """Il testo prima di `jobs:`: quello che vale per tutto il workflow."""
    return testo.split("\njobs:", 1)[0]


def test_ogni_uses_e_fissato_a_uno_sha():
    trovati = 0
    for f in _workflow():
        for riga in _senza_commenti(f.read_text(encoding="utf-8")):
            m = re.search(r"\buses:\s*(\S+)(.*)$", riga)
            if not m:
                continue
            trovati += 1
            ref = m.group(1)
            assert re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", ref), \
                f"{f.name}: {ref} non e' fissato a uno SHA"
            # Il tag in commento serve a chi legge e a chi aggiorna: senza, lo
            # SHA e' un numero che nessuno sa piu' a che versione corrisponde.
            assert re.search(r"#\s*v\d+\.\d+\.\d+\s*$", m.group(2)), \
                f"{f.name}: {ref} senza il tag in commento"
    assert trovati >= 8, f"solo {trovati} uses: trovati"


def test_nessuna_espressione_dentro_run():
    # Un'espressione dentro `run:` e' testo incollato nello script prima che
    # giri: un nome di ramo con le virgolette diventa codice. Passa da `env:`.
    for f in _workflow():
        blocchi = _blocchi_run(f.read_text(encoding="utf-8"))
        assert blocchi, f"{f.name}: nessun run: trovato"
        for corpo in blocchi:
            assert "${{" not in corpo, f"{f.name}: espressione dentro run:\n{corpo}"


def test_il_ref_passa_da_env_e_si_ripulisce():
    testo = RELEASE.read_text(encoding="utf-8")
    assert "REF_NAME: ${{ github.ref_name }}" in testo
    assert "$ref = $env:REF_NAME -replace '[^A-Za-z0-9._-]', '-'" in testo


def test_permessi_minimi_in_testa_e_scrittura_solo_su_publish():
    for f in (RELEASE, CI):
        testa = _testa(f.read_text(encoding="utf-8"))
        assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", testa, re.M), \
            f"{f.name}: manca permissions: contents: read in testa"
        assert "write" not in "\n".join(_senza_commenti(testa)), f"{f.name}: scrittura in testa"

    testo = RELEASE.read_text(encoding="utf-8")
    build = "\n".join(_senza_commenti(_job(testo, "build")))
    publish = "\n".join(_senza_commenti(_job(testo, "publish")))
    assert "write" not in build, "il job build non deve poter scrivere"
    for permesso in ("contents: write", "id-token: write", "attestations: write"):
        assert permesso in publish, f"publish senza {permesso}"
    assert "write" not in "\n".join(_senza_commenti(CI.read_text(encoding="utf-8")))


def test_publish_solo_sui_tag_e_con_attestazione():
    testo = RELEASE.read_text(encoding="utf-8")
    build = _job(testo, "build")
    publish = "\n".join(_senza_commenti(_job(testo, "publish")))

    # build espone lo ZIP e la sua impronta; publish li riceve da li'.
    assert re.search(r"outputs:\s*\n\s+zip:\s*\$\{\{\s*steps\.pack\.outputs\.zip\s*\}\}", build)
    assert re.search(r"\n\s+sha:\s*\$\{\{\s*steps\.pack\.outputs\.sha\s*\}\}", build)
    assert "softprops/action-gh-release" not in build, "build non pubblica"

    assert re.search(r"^\s+needs:\s*build\s*$", publish, re.M)
    assert re.search(r"^\s+if:\s*startsWith\(github\.ref, 'refs/tags/'\)\s*$", publish, re.M)
    assert "actions/download-artifact@" in publish
    assert "name: HONE-build-${{ github.sha }}" in publish
    assert "actions/attest-build-provenance@" in publish
    assert re.search(r"subject-path:\s*\$\{\{\s*needs\.build\.outputs\.zip\s*\}\}", publish)
    assert "softprops/action-gh-release@" in publish
    # L'attestazione viene prima della pubblicazione: una release senza prova
    # di provenienza non deve uscire nemmeno per un attimo.
    assert publish.index("attest-build-provenance") < publish.index("action-gh-release")

    # Il corpo della release dice come verificarla, dopo l'impronta.
    verifica = "gh attestation verify ${{ needs.build.outputs.zip }} --repo ardiz89/ACCoach"
    assert verifica in publish
    assert publish.index("needs.build.outputs.sha") < publish.index(verifica)


def test_upx_spento_nello_spec():
    # UPX comprime l'EXE e le DLL con un packer: gli antivirus lo leggono come
    # un segnale di malware e segnalano anche un file pulito (falsi positivi).
    testo = SPEC.read_text(encoding="utf-8")
    valori = re.findall(r"\bupx\s*=\s*(\w+)", testo)
    assert valori == ["False", "False"], valori
