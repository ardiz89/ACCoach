"""Il pacchetto che si allega a una segnalazione: log + contesto, in uno ZIP.

`logs` apriva una cartella in Explorer, e nient'altro impacchettava niente.
Senza pacchetto una segnalazione e' «non ho sentito niente», che qui sappiamo
essere **indistinguibile da un guasto muto**: il 12/08 la voce si e' piantata in
silenzio — thread vivo, nessuna eccezione — e l'unico posto dove la differenza
si vedeva era il log.

Due scelte che vale la pena dichiarare.

**Il pacchetto nasce comunque.** Anche con la cartella dei log vuota o
inesistente (primo avvio, oppure il logging non e' mai partito — che e'
esattamente il guasto peggiore). Un comando diagnostico che fallisce proprio
quando le cose vanno male non serve a niente; il file di contesto *dice* che di
log non ce n'erano, invece di lasciar credere che siano andati persi.

**Niente oltre a cio' che sta gia' dentro i log.** Il contesto porta versione,
commit, Python e sistema, e le ultime auto/pista che il catalogo dei giri gia'
conosce. Restano fuori i percorsi (contengono il nome dell'account Windows), il
nome della macchina e qualunque campo con un indirizzo: non aggiungono niente
alla diagnosi e uscirebbero di casa insieme allo ZIP. Il catalogo si apre in
sola lettura e solo se esiste — questo comando non deve creare niente, e non
apre la telemetria.

Il che vale per il **contesto**, non per il pacchetto: i log ci vanno dentro
come sono, non filtrati, e i percorsi assoluti col nome dell'account Windows li
contengono davvero. E' una scelta — un log ripulito non diagnostica niente, e
una censura invisibile sarebbe peggio del percorso — e per questo la
dichiarazione dentro lo ZIP tiene le due cose separate invece di promettere un
pacchetto pulito che non e'. Vedi :func:`_disclosure`.
"""

from __future__ import annotations

import platform
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__

#: Il file di contesto dentro lo ZIP.
CONTEXT_NAME = "contesto.txt"
#: Cosa scrive il contesto quando di log non ce n'erano. Detto per esteso
#: apposta: chi legge la segnalazione deve poter distinguere «i log mancano»
#: da «i log non sono stati raccolti».
NO_LOGS = "none - the folder was empty or did not exist"
#: Cosa scrive il contesto quando il catalogo dei giri non sa dire niente.
NO_COMBOS = "not available (no lap catalog on this machine)"

_UNKNOWN_COMMIT = "unknown (not a source checkout)"


# --- il commit -----------------------------------------------------------------

def _is_sha(text: str) -> bool:
    return len(text) >= 7 and all(c in "0123456789abcdef" for c in text.lower())


def _resolve_ref(base: Path, ref: str) -> str:
    """Lo SHA di ``ref`` sotto ``base``, come file sciolto o dentro packed-refs."""
    loose = base / ref
    if loose.is_file():
        sha = loose.read_text(encoding="utf-8", errors="replace").strip()
        return sha if _is_sha(sha) else ""
    packed = base / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line[0] in "#^":
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref and _is_sha(parts[0]):
                return parts[0]
    return ""


def git_commit(start: Path | None = None) -> str:
    """Lo SHA corto del checkout che contiene ``start``, o ``""`` se non c'e'.

    Legge i file di ``.git`` invece di lanciare ``git``: dall'exe impacchettato
    un sottoprocesso aprirebbe una console, e qui non c'e' nemmeno un checkout
    da interrogare — la risposta giusta in quel caso e' «non lo so», non un
    errore. Gestisce anche il caso in cui ``.git`` e' un *file* (worktree), che
    e' come lavoriamo di solito.
    """
    try:
        here = Path(start) if start is not None else Path(__file__).resolve().parent
        dot = None
        for d in [here, *here.parents]:
            if (d / ".git").exists():
                dot = d / ".git"
                break
        if dot is None:
            return ""

        gitdir = dot
        if dot.is_file():
            text = dot.read_text(encoding="utf-8", errors="replace").strip()
            if not text.startswith("gitdir:"):
                return ""
            p = Path(text.split(":", 1)[1].strip())
            gitdir = p if p.is_absolute() else (dot.parent / p).resolve()

        head = (gitdir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
        if not head.startswith("ref:"):
            return head[:7] if _is_sha(head) else ""
        ref = head.split(":", 1)[1].strip()

        bases = [gitdir]
        common = gitdir / "commondir"
        if common.is_file():
            p = Path(common.read_text(encoding="utf-8", errors="replace").strip())
            bases.append(p if p.is_absolute() else (gitdir / p).resolve())
        for base in bases:
            sha = _resolve_ref(base, ref)
            if sha:
                return sha[:7]
        return ""
    except OSError:
        return ""


# --- le ultime auto/pista -------------------------------------------------------

def recent_combos(limit: int = 5) -> list[str]:
    """Le ultime auto/pista guidate, dal catalogo dei giri. Mai una eccezione.

    Sorgente che esiste gia' (la stessa da cui la Home dell'hub pesca l'ultima
    sessione), aperta pero' in **sola lettura** e solo se il file c'e': un
    comando diagnostico non deve creare un catalogo, ne' farlo migrare.
    """
    try:
        from .recording import laps_root
        from .recording.storage import _catalog_path

        db = _catalog_path(laps_root())
        if not db.is_file():
            return []
        con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT car_model, track, MAX(recorded_utc) AS last FROM lap "
                "GROUP BY car_model, track ORDER BY last DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        finally:
            con.close()
    except Exception:   # noqa: BLE001 - un catalogo illeggibile non blocca il pacchetto
        return []
    out = []
    for car, track, last in rows:
        when = f"  ({str(last)[:10]})" if last else ""
        out.append(f"{car} / {track}{when}")
    return out


# --- il file di contesto ---------------------------------------------------------

def _size(path: Path) -> str:
    try:
        n = path.stat().st_size
    except OSError:
        return "?"
    return f"{n} B" if n < 1024 else f"{n / 1024:.0f} KB"


def context_report(*, logs: list[Path] | None = None,
                   combos: list[str] | None = None,
                   now: datetime | None = None,
                   commit: str | None = None,
                   skipped: list[str] | None = None) -> str:
    """Il testo di ``contesto.txt``. Stesse etichette del rapporto di crash."""
    logs = list(logs or [])
    combos = list(combos or [])
    skipped = list(skipped or [])
    now = now or datetime.now()
    if commit is None:
        commit = git_commit()

    lines = [
        f"HONE {__version__} - log bundle",
        f"when:    {now.isoformat(timespec='seconds')}",
        f"commit:  {commit or _UNKNOWN_COMMIT}",
        f"python:  {platform.python_version()}",
        f"os:      {platform.platform()}",
        f"frozen:  {'yes' if _frozen() else 'no'}",
        "",
    ]
    if logs:
        lines.append(f"logs:    {len(logs)} file(s)")
        lines += [f"         {p.name}  ({_size(p)})" for p in logs]
    else:
        lines.append(f"logs:    {NO_LOGS}")
    if skipped:
        lines.append(f"         not readable, left out: {', '.join(skipped)}")
    lines.append("")
    lines.append("cars/tracks seen, most recent first:")
    if combos:
        lines += [f"         {c}" for c in combos]
    else:
        lines.append(f"         {NO_COMBOS}")
    lines.append("")
    lines += _disclosure(bool(logs))
    return "\n".join(lines) + "\n"


def _disclosure(has_logs: bool) -> list[str]:
    """Cosa sta per uscire di casa, detto in modo che si possa decidere.

    La versione precedente diceva «No paths, machine name or account details are
    included»: vera del file che la conteneva, **falsa del pacchetto in cui quel
    file vive**. Accanto c'e' ``logs/accoach.log``, che i percorsi assoluti col
    nome dell'account Windows li ha eccome. Non li filtriamo, ed e' una scelta:
    un log ripulito non diagnostica niente, e una censura invisibile sarebbe
    peggio del percorso. Ma allora va detto, e vanno tenute distinte le due
    cose — cosa questo file lascia fuori, e cosa gli allegati portano dentro.

    L'avviso sui log compare solo se dei log ci sono davvero: avvisare di
    allegati che non esistono sarebbe una formula di copertura, non una
    dichiarazione.

    E **nomina le categorie, non una parte**. La prima versione parlava di
    percorsi, piste, auto e file aperti, e lasciava fuori la meta' piu'
    personale: le ~340 righe `=== ACCoach ... starting ===` datate, che sono il
    registro orario di ogni volta che il pilota si e' seduto a guidare per mesi;
    l'identificatore del giro, che contiene il **tempo sul giro**; i
    `crash-*.log`, che `build_log_zip` prende come tutti gli altri file e che
    portano un traceback intero; e `data.laps_dir`, che negli errori di
    configurazione puo' essere un percorso di rete. «Decido informato» e' vero
    solo se l'elenco e' completo.
    """
    out = ["What you are about to send:",
           f"  {CONTEXT_NAME} (this file) carries the lines above and nothing",
           "  else: no paths, no machine name, no account name, because none of",
           "  that would help a diagnosis."]
    if has_logs:
        out += [
            "  Everything under logs/ goes in exactly as it was written, NOT",
            "  filtered - a log with the interesting parts taken out diagnoses",
            "  nothing.",
            "  Those files carry, at least: paths, which include your Windows",
            r"  account name (C:\Users\<account>\...) and any network location",
            "  you configured; one dated line for every single time you started",
            "  HONE, which together are a record of when you sat down to drive,",
            "  going back as far as your oldest log; your lap times, and the",
            "  tracks and cars you drove; the names of files you opened; and",
            "  crash reports, each with a full traceback, the paths of our",
            "  source files, and whatever value the error carried with it.",
            "  It is an ordinary zip: open it and read it before you send it.",
        ]
    else:
        out.append("  No log files were attached, so that is all there is.")
    return out


def _frozen() -> bool:
    import sys

    return bool(getattr(sys, "frozen", False))


# --- lo ZIP -----------------------------------------------------------------------

def short_notice(zip_path: Path | str) -> str:
    """La dichiarazione in forma breve, per il terminale.

    Il comando stampava solo il percorso dello ZIP: per sapere cosa stava per
    mandare, un tester doveva **aprire l'archivio** e trovare ``contesto.txt``.
    Una dichiarazione che si legge solo dopo aver deciso non serve a decidere.

    Si legge dal pacchetto appena scritto invece che da un flag: cosi' la nota
    breve non puo' divergere da quello che e' finito dentro davvero.
    """
    try:
        with zipfile.ZipFile(zip_path) as z:
            has_logs = any(n != CONTEXT_NAME for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        has_logs = False
    if not has_logs:
        return ("Nothing was attached: there were no log files to collect.\n"
                f"{CONTEXT_NAME} inside says as much.")
    return (
        "Inside, logs/ goes in unfiltered: paths carrying your Windows account\n"
        "name, one dated line for every time you started HONE, your lap times,\n"
        "the tracks and cars you drove, and crash reports with full tracebacks.\n"
        f"Read {CONTEXT_NAME} in the zip for the whole list - and the zip\n"
        "itself, before you send it."
    )


def build_log_zip(dest_dir: Path | str | None = None,
                  source: Path | str | None = None,
                  now: datetime | None = None) -> Path:
    """Impacchetta i log piu' il contesto e restituisce il percorso dello ZIP.

    ``dest_dir`` e ``source`` esistono per i test; in produzione arrivano
    entrambi da :mod:`accoach.paths`, cosi' il pacchetto finisce accanto a tutto
    il resto in ``Documenti/ACCoach``.
    """
    from . import paths

    now = now or datetime.now()
    dest = Path(dest_dir) if dest_dir is not None else paths.base_dir()
    src = Path(source) if source is not None else paths.logs_dir()
    dest.mkdir(parents=True, exist_ok=True)

    candidates = sorted(p for p in src.iterdir() if p.is_file()) if src.is_dir() else []
    out = dest / f"hone-log-{now:%Y%m%d-%H%M%S}.zip"
    added: list[Path] = []
    skipped: list[str] = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in candidates:
            try:
                z.write(p, f"logs/{p.name}")
            except OSError:
                # Un file tenuto aperto da un altro processo non deve far
                # saltare il pacchetto: lo si dichiara e si va avanti.
                skipped.append(p.name)
            else:
                added.append(p)
        # Il contesto per ultimo: solo qui si sa quali file ci sono davvero
        # dentro.
        z.writestr(CONTEXT_NAME, context_report(logs=added, combos=recent_combos(),
                                                now=now, skipped=skipped))
    return out
