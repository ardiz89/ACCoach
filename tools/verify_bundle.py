"""Il pacchetto porta quello che il `.spec` dichiara? — controllo per la CI.

    python tools/verify_bundle.py dist/HONE [HONE.spec]

Esiste perché PyInstaller perde un payload **in silenzio**: il build resta
verde e a degradare è una funzione. È già successo due volte, e tutte e due le
volte la causa era la stessa — due liste per la stessa cosa, e a spedire era
quella che nessuno apriva. Senza `docs/FAQ.md` chi sceglieva l'inglese leggeva
la guida italiana; senza `voice_cues_male/` la voce maschile tornava SAPI5.

Per questo qui dentro **non c'è nessun elenco**: i payload si leggono dal
`.spec`, che è la lista da cui l'EXE viene davvero costruito. Un controllo con
una lista propria sarebbe la terza copia, cioè il difetto che dovrebbe
impedire.

Due regole, imparate perdendoci:

* si contano **tutti** i file di un payload, non un campione per tipo. Sotto
  `src/accoach/web` gli `.html` sono 3 su 22: una sonda `*.html` avrebbe detto
  «3 / 3, tutto a posto» su un bundle senza JS, senza CSS e senza font.
* per un file singolo conta **dove sta**, non come si chiama. `guide.py` apre
  `docs/FAQ.md`: un `FAQ.md` finito altrove è il difetto del 28/07 con un
  timbro di approvazione sopra.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def declared(spec: Path) -> list[tuple[str, str]]:
    """Le coppie ``(sorgente, destinazione)`` della riga ``datas`` del `.spec`.

    Si legge con `ast`, non eseguendo il file: un `.spec` importa gli hook di
    PyInstaller, che sulla macchina di chi lancia i test possono non esserci.
    """
    text = spec.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "datas" for t in node.targets)):
            return [tuple(pair) for pair in ast.literal_eval(node.value)]
    raise ValueError(f"{spec.name}: nessuna riga `datas = [...]`")


def _files(folder: Path) -> int:
    return sum(1 for p in folder.rglob("*") if p.is_file())


def _find_dir(dist: Path, dest: str) -> Path | None:
    """La cartella del bundle che corrisponde a ``dest``.

    Si cerca invece di comporre `dist/_internal/<dest>` perché dove PyInstaller
    metta i dati è una sua scelta, e cambia fra le versioni: quello che ci
    interessa è che la cartella ci sia e sia completa, non in quale sottocartella
    l'abbia messa.
    """
    wanted = dest.replace("\\", "/").strip("/")
    for p in dist.rglob("*"):
        if p.is_dir() and p.as_posix().endswith("/" + wanted):
            return p
    return None


def check(root: Path, dist: Path, spec: Path) -> list[str]:
    """I problemi del pacchetto, uno per riga. Lista vuota = pacchetto sano."""
    problemi: list[str] = []
    for src, dest in declared(spec):
        sorgente = root / src
        if sorgente.is_dir():
            atteso = _files(sorgente)
            cartella = _find_dir(dist, dest)
            if cartella is None:
                problemi.append(f"MANCA la cartella  {dest}  ({atteso} file nel repo)")
                continue
            trovati = _files(cartella)
            if trovati < atteso:
                problemi.append(
                    f"CORTA  {dest}: {trovati} file contro {atteso} nel repo")
        else:
            # `dest` è la cartella in cui il file finisce ('.' = la radice).
            atteso = (sorgente.name if dest in (".", "")
                      else f"{dest.strip('/')}/{sorgente.name}")
            trovato = any(p.as_posix().endswith("/" + atteso)
                          for p in dist.rglob(sorgente.name) if p.is_file())
            if not trovato:
                altrove = [p for p in dist.rglob(sorgente.name) if p.is_file()]
                dove = (f" (ce n'e' uno in {altrove[0].parent.as_posix()}, "
                        f"ma il codice lo cerca in «{dest}»)" if altrove else "")
                problemi.append(f"MANCA  {atteso}{dove}")
    return problemi


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    dist = Path(argv[0])
    root = Path(__file__).resolve().parents[1]
    spec = Path(argv[1]) if len(argv) > 1 else root / "HONE.spec"

    coppie = declared(spec)
    print(f"{spec.name} dichiara {len(coppie)} payload; controllo {dist}")
    problemi = check(root, dist, spec)
    for src, dest in coppie:
        # Il nome che si legge, non la destinazione: per un file singolo `dest`
        # e' la cartella che lo ospita ('.' o 'docs'), e una riga «ok  .» non
        # dice a nessuno che GUIDA.md c'e'.
        sorgente = root / src
        etichetta = dest if sorgente.is_dir() else (
            sorgente.name if dest in (".", "") else f"{dest.strip('/')}/{sorgente.name}")
        if not any(etichetta in p or dest in p for p in problemi):
            print(f"  ok  {etichetta}")
    if problemi:
        print(f"::error::il pacchetto non porta quello che {spec.name} dichiara")
        for p in problemi:
            print(f"::error::{p}")
        return 1
    print("il pacchetto e' completo")
    return 0


if __name__ == "__main__":   # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
