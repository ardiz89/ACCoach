"""Fonti pubbliche per pista: raccolta, estrazione, consenso, esportazione.

    python tools/fonti/fonti.py check-actors --plan FILE
    python tools/fonti/fonti.py --db <cartella o file> collect --track imola --plan FILE

Il database sta dove dici tu con `--db`: nessun valore predefinito. Il token, l'ordine
dei comandi e i file di risposta degli agenti sono in tools/fonti/README.md.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import db  # noqa: E402

DEFAULT_FACTS = ROOT / "src" / "accoach" / "trackfacts"


def _db_path(arg: str) -> Path:
    p = Path(arg)
    return p / "fonti.sqlite" if p.is_dir() or p.suffix == "" else p


def cmd_status(args) -> int:
    conn = db.open_db(_db_path(args.db))
    try:
        for tabella, n in db.count_rows(conn).items():
            print(f"{tabella}: {n}")
    finally:
        conn.close()
    return 0


_NET = "Rete non raggiungibile o troppo lenta: riprova fra poco. Le voci già finite non si ripagano."


def _client(args):
    from tools.fonti import apify

    return apify.Apify(apify.load_token(Path(args.env_file) if args.env_file else None))


def _apify_errors(fn):
    """Esegue `fn`; un errore si stampa in una riga, mai col testo di un'eccezione ignota."""
    from tools.fonti import apify

    try:
        return fn()
    except (apify.TokenMissing, apify.CapReached, apify.ApifyError) as e:
        print(str(e), file=sys.stderr)  # messaggi nostri: mai il token
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        print(_NET, file=sys.stderr)
    return None


def _dry_run(conn, args, plan) -> int:
    from tools.fonti import apify, collect

    fatte = collect.finished(conn, args.track)
    totale = 0.0
    for i, v in enumerate(plan, 1):
        prezzo = v.get("cost_per_item_usd")
        if isinstance(prezzo, (int, float)) and not isinstance(prezzo, bool):
            stima = prezzo * v["max_items"]
            totale += stima
            testo = f"stima {stima:.2f} USD"
        else:
            testo = "stima ignota: manca cost_per_item_usd"
        finita = " [già finita]" if collect.entry_key(v) in fatte else ""
        print(f"voce {i} {v['platform']}: {v['actor']} (max {v['max_items']} voci), {testo}{finita}")
    print(f"Stima totale: {totale:.2f} USD.")
    speso = apify.spent(conn, args.track)
    print(f"Resto del budget: {apify.CAP_USD - speso:.2f} USD (tetto {apify.CAP_USD:.2f}).")
    return 0


def cmd_collect(args) -> int:
    import json

    from tools.fonti import collect

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    conn = db.open_db(_db_path(args.db))
    try:
        if args.dry_run:
            return _dry_run(conn, args, plan)
        if args.only is not None and not 1 <= args.only <= len(plan):
            print(f"Il piano ha {len(plan)} voci: --only va da 1 a {len(plan)}.", file=sys.stderr)
            return 1
        try:
            r = _apify_errors(lambda: collect.collect(conn, _client(args), args.track, plan,
                                                      force=args.force, only=args.only))
        except Exception as e:  # mai str(e): potrebbe contenere il token
            print(f"Errore inatteso ({type(e).__name__}): la raccolta si ferma. "
                  "Le voci già finite non si ripagano.", file=sys.stderr)
            return 1
        if r is None:
            return 1
        print(f"Nuove fonti: {r['sources']}, nuovi testi: {r['texts']}, voci già finite: {r['skipped']}, "
              f"elementi illeggibili: {r['bad_items']}, speso: {r['spent_usd']:.2f} USD.")
        if r["subtitle_fields"]:
            campi = ", ".join(f"{k} {n}" for k, n in sorted(r["subtitle_fields"].items()))
            print(f"Sottotitoli letti da: {campi}.")
        if r["subtitle_keys"]:
            print(f"Chiavi dei sottotitoli senza un campo noto: {', '.join(r['subtitle_keys'])}.")
        for i, stato in r["failed"]:
            v = plan[i - 1]
            print(f"Voce {i} ({v['platform']}, {v['actor']}): la corsa è finita con stato {stato}. "
                  "Non la segno finita. Gli elementi arrivati restano in raw_items.", file=sys.stderr)
        for i in r["empty"]:
            v = plan[i - 1]
            print(f"Voce {i} ({v['platform']}, {v['actor']}): 0 testi. Non la segno finita. "
                  "Controlla l'input con check-actors, poi rilancia con --force --only "
                  f"{i}.", file=sys.stderr)
        return 1 if r["empty"] or r["failed"] else 0
    finally:
        conn.close()


def cmd_check_actors(args) -> int:
    import json

    from tools.fonti import collect

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    try:
        problemi = _apify_errors(lambda: collect.check_actors(_client(args), plan))
    except Exception as e:  # mai str(e): potrebbe contenere il token
        print(f"Errore inatteso ({type(e).__name__}): il controllo si ferma.", file=sys.stderr)
        return 1
    if problemi is None:
        return 1
    for riga in problemi:
        print(riga)
    if problemi:
        print(f"Problemi trovati: {len(problemi)}. Correggi il piano prima di pagare.")
        return 1
    print("Nessun problema: ogni chiave del piano è nello schema dell'attore.")
    return 0


def cmd_pending(args) -> int:
    from tools.fonti import agents

    conn = db.open_db(_db_path(args.db))
    try:
        try:
            jobs = agents.pending(conn, args.kind, args.track, Path(args.out))
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"Lavori {args.kind} da fare: {len(jobs)}, in {args.out}.")
        return 0
    finally:
        conn.close()


def cmd_ingest(args) -> int:
    from tools.fonti import agents

    conn = db.open_db(_db_path(args.db))
    rifiutati = 0
    try:
        for f in args.files:
            try:
                r = agents.ingest(conn, Path(f), args.model)
            except agents.AnswerRejected as e:
                rifiutati += 1
                print(f"{Path(f).name}: rifiutato ({e.reason})", file=sys.stderr)
                continue
            except Exception as e:  # un file guasto non ferma gli altri
                rifiutati += 1
                print(f"{Path(f).name}: errore inatteso ({type(e).__name__}), passo al prossimo.",
                      file=sys.stderr)
                continue
            print(f"{Path(f).name}: {agents.summary(Path(f), r)}")
        return 1 if rifiutati else 0
    finally:
        conn.close()


def cmd_consensus(args) -> int:
    from tools.fonti import consensus

    conn = db.open_db(_db_path(args.db))
    try:
        entries = consensus.build(conn, args.track)
    finally:
        conn.close()
    if not entries:
        print(f"Nessun fatto per {args.track}.")
        return 0
    curva = None
    for e in entries:
        if e["corner"] != curva:
            curva = e["corner"]
            print(f"{curva}:")
        valori = ", ".join(
            f"{v['value']} ({v['n']} {'autore' if v['n'] == 1 else 'autori'})"
            for v in e["values"]) or "nessun valore GT3"
        altre = ", ".join(v["value"] for v in e.get("others") or [])
        print(f"  {e['type']}: {e['state']}, {valori}" + (f"; altre classi: {altre}" if altre else ""))
    stati = [e["state"] for e in entries]
    conti = ", ".join(f"{s} {stati.count(s)}" for s in ("verificato", "conteso", "singolo", "descrittivo"))
    print(f"Totale: {conti}.")
    return 0


def cmd_export(args) -> int:
    from tools.fonti import export

    conn = db.open_db(_db_path(args.db))
    try:
        n = export.export(conn, args.track, Path(args.out) if args.out else DEFAULT_FACTS)
        path = export.target(Path(args.out) if args.out else DEFAULT_FACTS, args.track)
    finally:
        conn.close()
    print(f"Fatti esportati: {n}, in {path}.")
    return 0


def cmd_review(args) -> int:
    from tools.fonti import review

    conn = db.open_db(_db_path(args.db))
    try:
        path = review.render(conn, args.track, Path(args.out))
    finally:
        conn.close()
    print(f"Pagina di controllo scritta in {path}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fonti", description=__doc__.splitlines()[0])
    ap.add_argument("--db", metavar="PATH", help="cartella o file del database (serve a tutti i "
                    "comandi tranne check-actors)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="righe per tabella").set_defaults(func=cmd_status)
    c = sub.add_parser("collect", help="raccoglie le fonti con Apify")
    c.add_argument("--track", required=True)
    c.add_argument("--plan", required=True, metavar="FILE")
    c.add_argument("--env-file", metavar="PATH")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--force", action="store_true", help="rifà anche le voci già finite")
    c.add_argument("--only", type=int, metavar="N", help="solo la voce numero N del piano (da 1)")
    c.set_defaults(func=cmd_collect)
    a = sub.add_parser("check-actors", help="confronta il piano con lo schema degli attori (gratis)")
    a.add_argument("--plan", required=True, metavar="FILE")
    a.add_argument("--env-file", metavar="PATH")
    a.set_defaults(func=cmd_check_actors)
    p = sub.add_parser("pending", help="scrive i lavori per gli agenti")
    p.add_argument("--kind", required=True, choices=("extract", "rate", "factcheck"))
    p.add_argument("--track", required=True)
    p.add_argument("--out", required=True, metavar="DIR")
    p.set_defaults(func=cmd_pending)
    i = sub.add_parser("ingest", help="congela le risposte degli agenti")
    i.add_argument("--model", required=True)
    i.add_argument("files", nargs="+", metavar="FILE")
    i.set_defaults(func=cmd_ingest)
    k = sub.add_parser("consensus", help="il consenso fra autori, curva per curva")
    k.add_argument("--track", required=True)
    k.set_defaults(func=cmd_consensus)
    x = sub.add_parser("export", help="esporta i fatti confermati nel pacchetto dell'app")
    x.add_argument("--track", required=True)
    x.add_argument("--out", metavar="DIR|FILE",
                   help="cartella o file .json (predefinito: src/accoach/trackfacts)")
    x.set_defaults(func=cmd_export)
    r = sub.add_parser("review", help="scrive la pagina di controllo per il pilota")
    r.add_argument("--track", required=True)
    r.add_argument("--out", required=True, metavar="FILE")
    r.set_defaults(func=cmd_review)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.cmd != "check-actors" and not args.db:
        ap.error("--db è obbligatorio per questo comando")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
