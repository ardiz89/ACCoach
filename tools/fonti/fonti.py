"""Fonti pubbliche per pista: raccolta, estrazione, consenso, esportazione.

    python tools/fonti/fonti.py --db <cartella o file> status

Il database sta dove dici tu con `--db`: nessun valore predefinito.
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

PLANNED = ("consensus", "export", "review")


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


def cmd_collect(args) -> int:
    import json

    from tools.fonti import apify, collect

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    conn = db.open_db(_db_path(args.db))
    try:
        if args.dry_run:
            for v in plan:
                print(f"{v['platform']}: {v['actor']} (max {v['max_items']} voci)")
            riga = conn.execute("SELECT baseline_usd, last_usd FROM spend WHERE track=?",
                                (args.track,)).fetchone()
            speso = (riga[1] - riga[0]) if riga else 0.0
            print(f"Resto del budget: {apify.CAP_USD - speso:.2f} USD (tetto {apify.CAP_USD:.2f}).")
            return 0
        try:
            client = apify.Apify(apify.load_token(Path(args.env_file) if args.env_file else None))
            r = collect.collect(conn, client, args.track, plan, force=args.force)
        except (apify.TokenMissing, apify.CapReached, apify.ApifyError) as e:
            print(str(e), file=sys.stderr)
            return 1
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            print("Rete non raggiungibile o troppo lenta: riprova fra poco. "
                  "Le voci già finite non si ripagano.", file=sys.stderr)
            return 1
        print(f"Nuove fonti: {r['sources']}, nuovi testi: {r['texts']}, voci già finite: {r['skipped']}, speso: {r['spent_usd']:.2f} USD.")
        return 0
    finally:
        conn.close()


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
            print(f"{Path(f).name}: fatti {r['facts']}, scarti {r['rejects']}.")
        return 1 if rifiutati else 0
    finally:
        conn.close()


def cmd_non_disponibile(args) -> int:
    print(f"{args.cmd}: non ancora disponibile", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fonti", description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, metavar="PATH", help="cartella o file del database")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="righe per tabella").set_defaults(func=cmd_status)
    c = sub.add_parser("collect", help="raccoglie le fonti con Apify")
    c.add_argument("--track", required=True)
    c.add_argument("--plan", required=True, metavar="FILE")
    c.add_argument("--env-file", metavar="PATH")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--force", action="store_true", help="rifà anche le voci già finite")
    c.set_defaults(func=cmd_collect)
    p = sub.add_parser("pending", help="scrive i lavori per gli agenti")
    p.add_argument("--kind", required=True, choices=("extract", "rate", "factcheck"))
    p.add_argument("--track", required=True)
    p.add_argument("--out", required=True, metavar="DIR")
    p.set_defaults(func=cmd_pending)
    i = sub.add_parser("ingest", help="congela le risposte degli agenti")
    i.add_argument("--model", required=True)
    i.add_argument("files", nargs="+", metavar="FILE")
    i.set_defaults(func=cmd_ingest)
    for name in PLANNED:
        sub.add_parser(name, help="non ancora disponibile").set_defaults(func=cmd_non_disponibile)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
