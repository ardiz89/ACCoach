"""Quello che l'EXE si porta dietro, e quello che il codice cerca a runtime.

Nasce da un difetto vero e **ripetuto**. Il workflow di release elencava i
`--add-data` a mano, cioè teneva una seconda copia della lista che sta nel
`.spec` — e ne spediva quattro su sei. I due che mancavano non rompevano niente
in modo visibile: senza `docs/FAQ.md` chi sceglieva l'inglese leggeva la guida
*italiana* (`guide.py` ripiega apposta, ma lì ripiegava sempre), e senza
`voice_cues_male/` la voce maschile suonava SAPI5 invece dei cue neurali già
renderizzati e già in repo.

`docs/FAQ.md` era già stato dimenticato una volta, il 28/07. La seconda volta
non è sfortuna: è che esistevano due fonti di verità per la stessa lista, e a
spedire era quella che nessuno apriva.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPECS = sorted(ROOT.glob("*.spec"))
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


def _datas(spec: Path) -> list[str]:
    """I percorsi sorgente dichiarati nella riga `datas = [...]` del .spec."""
    text = spec.read_text(encoding="utf-8")
    riga = text.split("datas = ", 1)[1].split("]", 1)[0]
    return re.findall(r"\('([^']+)'", riga)


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.name)
def test_every_bundled_path_exists(spec):
    """Un percorso che non esiste finisce nel pacchetto come niente."""
    for rel in _datas(spec):
        assert (ROOT / rel).exists(), f"{spec.name}: {rel} non esiste"


def test_the_release_builds_from_the_spec_and_not_from_a_second_list():
    """La regola che impedisce al difetto di tornare una terza volta."""
    # Solo le righe che ESEGUONO: il commento che spiega perché la lista a mano
    # non c'è più contiene la parola, e un test che inciampa sulla propria
    # spiegazione insegna a non scrivere spiegazioni.
    yml = "\n".join(l for l in RELEASE.read_text(encoding="utf-8").splitlines()
                    if not l.lstrip().startswith("#"))
    assert ".spec" in yml, "la release non costruisce dal .spec"
    assert "--add-data" not in yml, (
        "la release e' tornata a elencare i dati a mano: e' la seconda fonte di "
        "verita' che ha gia' fatto spedire due volte un pacchetto incompleto")


@pytest.mark.parametrize("needed", [
    "src/accoach/web",            # l'app di analisi
    "src/accoach/tracks",         # le 26 linee centrali
    "src/accoach/voice_cues",     # i cue neurali femminili
    "src/accoach/voice_cues_male",  # …e quelli maschili, che mancavano
    "GUIDA.md",                   # la guida italiana
    "docs/FAQ.md",                # quella inglese, che mancava
])
def test_the_spec_carries_what_the_code_reads_at_runtime(needed):
    """Ognuno di questi ha un lettore nel codice: `guide.py` apre i due
    documenti a ogni richiesta, `coaching/voice.py` cerca le due cartelle di
    cue, `trackedges` le linee centrali. Manca uno → degrado silenzioso."""
    assert needed in _datas(ROOT / "HONE.spec")


def test_both_specs_bundle_the_same_data():
    """Ce ne sono due, uno per marca. Possono differire nel nome e nell'icona,
    non in cosa spediscono."""
    if len(SPECS) < 2:
        pytest.skip("un solo .spec")
    liste = {s.name: _datas(s) for s in SPECS}
    prima = next(iter(liste.values()))
    for nome, lista in liste.items():
        assert lista == prima, f"{nome} spedisce dati diversi dagli altri"
