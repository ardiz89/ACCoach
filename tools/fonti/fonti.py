"""Fonti pubbliche per pista: raccolta, estrazione, consenso, esportazione.

    python tools/fonti/fonti.py --db <cartella o file> status

Il database sta dove dici tu con `--db`: nessun valore predefinito.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fonti import db  # noqa: E402

PLANNED = ("pending", "ingest", "consensus", "export", "review")


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
            r = collect.collect(conn, client, args.track, plan)
        except (apify.TokenMissing, apify.CapReached, apify.ApifyError) as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"Nuove fonti: {r['sources']}, nuovi testi: {r['texts']}, speso: {r['spent_usd']:.2f} USD.")
        return 0
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
    c.set_defaults(func=cmd_collect)
    for name in PLANNED:
        sub.add_parser(name, help="non ancora disponibile").set_defaults(func=cmd_non_disponibile)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
