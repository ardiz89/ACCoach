"""Il guardiano del pacchetto, e le tre volte in cui non ha guardato.

La prima versione di questo controllo (2026-09-12) contava i file del bundle
contro quelli del repo, ma **con una sonda per tipo**: `*.html` per l'app web,
`*.wav` per i cue. Su `src/accoach/web` gli `.html` sono 3 su 22 file: un
bundle senza `app.js`, senza i CSS e senza i sei font passava il controllo
dicendo `ok  accoach/web: 3 / 3`. La difesa dichiarava di proteggere il
pacchetto e proteggeva un ottavo di una cartella.

Peggio: per sapere *cosa* contare, quella versione riscriveva l'elenco dei
payload dentro `release.yml` — cioè la terza copia della lista che sta nel
`.spec`, che è esattamente il difetto che il pacchetto aveva già pagato due
volte (`docs/FAQ.md` dimenticato il 28/07 e di nuovo il 04/08). Il test che
doveva impedirlo cercava la stringa `--add-data`: guardava la **forma** della
duplicazione precedente, non la sostanza, quindi ha approvato la nuova lista
scritta in un'altra forma.

Da qui le tre proprietà che questi test difendono: si conta **tutto** quello
che il payload contiene, il posto di un file conta quanto il suo nome, e
l'elenco vive in **un** posto solo.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))   # come fa `test_trackdata` per l'atlante

from verify_bundle import check, declared   # noqa: E402


def _fake_spec(tmp_path: Path) -> Path:
    """Un `.spec` con la stessa forma di quello vero: una cartella e un file."""
    spec = tmp_path / "FAKE.spec"
    spec.write_text(
        "datas = [('src/pkg/web', 'pkg/web'), ('docs/FAQ.md', 'docs')]\n",
        encoding="utf-8")
    return spec


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg" / "web").mkdir(parents=True)
    for name in ("index.html", "app.js", "style.css"):
        (root / "src" / "pkg" / "web" / name).write_text("x", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "FAQ.md").write_text("x", encoding="utf-8")
    return root


def _bundle(tmp_path: Path, *, files=("index.html", "app.js", "style.css"),
            faq_at="_internal/docs") -> Path:
    """Un `dist/APP` come lo scrive PyInstaller: i dati sotto `_internal/`."""
    dist = tmp_path / "dist" / "APP"
    web = dist / "_internal" / "pkg" / "web"
    web.mkdir(parents=True)
    for name in files:
        (web / name).write_text("x", encoding="utf-8")
    if faq_at is not None:
        faq = dist / faq_at
        faq.mkdir(parents=True, exist_ok=True)
        (faq / "FAQ.md").write_text("x", encoding="utf-8")
    return dist


def test_un_bundle_completo_non_ha_niente_da_dire(tmp_path):
    problemi = check(_repo(tmp_path), _bundle(tmp_path), _fake_spec(tmp_path))
    assert problemi == []


def test_una_cartella_mutilata_non_passa_perche_ha_ancora_gli_html(tmp_path):
    """Il difetto della prima versione, reso un test.

    Il bundle ha l'`index.html` e ha perso tutto il resto: la vecchia sonda
    `*.html` diceva `3 / 3`. Contando i file veri, dice quanti ne mancano.
    """
    problemi = check(_repo(tmp_path),
                     _bundle(tmp_path, files=("index.html",)),
                     _fake_spec(tmp_path))
    assert len(problemi) == 1
    assert "pkg/web" in problemi[0]
    assert "1" in problemi[0] and "3" in problemi[0]


def test_un_file_nel_posto_sbagliato_non_conta_come_presente(tmp_path):
    """`guide.py` apre `docs/FAQ.md`, non «un FAQ.md da qualche parte».

    Cercarlo per nome ovunque sotto `dist/` avrebbe riprodotto l'incidente del
    28/07 dicendo `ok`: il file c'è, ma il codice che lo legge non lo trova.
    """
    problemi = check(_repo(tmp_path),
                     _bundle(tmp_path, faq_at="_internal"),   # senza `docs/`
                     _fake_spec(tmp_path))
    assert len(problemi) == 1
    assert "FAQ.md" in problemi[0]


def test_un_payload_sparito_del_tutto_si_riconosce_dal_resto(tmp_path):
    problemi = check(_repo(tmp_path),
                     _bundle(tmp_path, faq_at=None),
                     _fake_spec(tmp_path))
    assert len(problemi) == 1
    assert "FAQ.md" in problemi[0]


def test_il_controllo_legge_i_payload_veri_dal_nostro_spec():
    """Non una lista scritta qui: quella del `.spec` che costruisce l'EXE."""
    coppie = declared(ROOT / "HONE.spec")
    sorgenti = [src for src, _dest in coppie]
    assert sorgenti == ["src/accoach/web", "src/accoach/voice_cues",
                        "src/accoach/tracks", "src/accoach/voice_cues_male",
                        "GUIDA.md", "docs/FAQ.md"]


def test_il_workflow_non_tiene_una_seconda_copia_dell_elenco():
    """La regola vera, al posto di quella che cercava `--add-data`.

    La versione precedente vietava **la forma** che la duplicazione aveva
    avuto la prima volta, quindi non ha visto la seconda scritta in
    PowerShell. Questa vieta la sostanza: nessun percorso dichiarato nel
    `.spec` può comparire nelle righe eseguibili del workflow.
    """
    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml")
                        .read_text(encoding="utf-8"))
    # Solo i `run:`, cioè gli script che il runner esegue. È lì che una lista
    # di payload può vivere e sbagliare — nelle due volte in cui è successo era
    # una riga di comando. Il testo delle note di rilascio non è escluso per
    # comodità: **linka** `docs/FAQ.md` su GitHub, che è un rimando a un
    # documento, non una dichiarazione di cosa entra nel pacchetto. Una regola
    # che confonde le due cose obbliga a togliere un link utile per far tacere
    # un test.
    script = "\n".join(
        "\n".join(l for l in str(s["run"]).splitlines()
                  if not l.lstrip().startswith("#"))
        for s in wf["jobs"]["build-windows"]["steps"] if "run" in s)
    for src, dest in declared(ROOT / "HONE.spec"):
        assert src not in script, (
            f"«{src}» e' riscritto negli script del workflow: e' la seconda "
            f"fonte di verita' che ha gia' fatto spedire due volte un "
            f"pacchetto incompleto")
        if dest not in (".",):
            assert dest not in script, f"«{dest}» e' riscritto negli script"


def test_nessuno_script_di_build_tiene_una_copia_dell_elenco():
    """La stessa regola, per chi costruisce l'EXE sul suo PC.

    Il difetto era vivo qui mentre lo chiudevamo altrove: `build_exe.bat`
    elencava i `--add-data` a mano e ne aveva **quattro su sei** — senza
    `tracks` (niente pista disegnata per chi non ha AC installato) e senza
    `voice_cues_male` (voce maschile robotica). Chi costruiva in locale
    otteneva un pacchetto degradato, in silenzio, esattamente come il 28/07.

    La lezione è che la lista non va tolta *da un posto*: va tolta da ovunque
    possa esistere. Questo test guarda tutti gli script di build del repo,
    quelli che ci sono oggi e quelli che qualcuno aggiungerà.
    """
    script = sorted(ROOT.glob("build*.bat")) + sorted(ROOT.glob("build*.sh"))
    assert script, "nessuno script di build trovato: il test guarda nel posto sbagliato"
    payload = declared(ROOT / "HONE.spec")
    for path in script:
        righe = "\n".join(
            l for l in path.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().lower().startswith("rem"))
        for src, dest in payload:
            assert src not in righe, (
                f"{path.name} riscrive «{src}»: e' un'altra copia della lista "
                f"del .spec, e una copia si dimentica un pezzo")


def test_lo_zip_si_carica_anche_quando_il_controllo_boccia():
    """Il pacchetto rotto è l'unico che vale davvero la pena di scaricare.

    Il commento diceva «sempre, anche sul giro a vuoto» mentre lo step stava
    dopo la verifica e senza `if: always()`: nel solo caso in cui vuoi aprire
    lo ZIP per capire cosa manca, non veniva caricato.
    """
    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml")
                        .read_text(encoding="utf-8"))
    steps = wf["jobs"]["build-windows"]["steps"]
    upload = next(s for s in steps if "upload-artifact" in str(s.get("uses", "")))
    assert upload.get("if") == "always()"


def test_la_pubblicazione_resta_appesa_al_tag():
    """La differenza fra provare e spedire è una riga, e va difesa."""
    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml")
                        .read_text(encoding="utf-8"))
    steps = wf["jobs"]["build-windows"]["steps"]
    publish = next(s for s in steps if "gh-release" in str(s.get("uses", "")))
    assert "refs/tags/" in publish.get("if", "")
