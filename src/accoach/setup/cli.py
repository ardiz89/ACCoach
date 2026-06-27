"""Command-line demo for the setup foundation (F0).

Lets us exercise read -> adjust -> preview -> write -> undo against a real ACC
setup file, with no game running. Examples::

    python -m accoach.setup.cli list  --car mclaren_720s_gt3_evo --track Imola
    python -m accoach.setup.cli show  "<path>.json"
    python -m accoach.setup.cli bump  "<path>.json" --param tyrePressure \
        --slot Post-Dx --clicks +2                       # preview only
    python -m accoach.setup.cli bump  "<path>.json" --param rearWing \
        --clicks -1 --apply --as ACCoach_test            # writes a new file
    python -m accoach.setup.cli undo  "<dir>/ACCoach_test.json"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .acc_format import SETUP_PARAMS, AccSetup, load, slot_labels
from .diff import diff, format_diff
from .store import SETUPS_ROOT, list_setups, save, undo

_SPECS = {s.key: s for s in SETUP_PARAMS}


def _resolve_slot(setup: AccSetup, spec, slot_arg: str | None) -> int:
    n = setup.slots(spec)
    if n == 1:
        return 0
    if slot_arg is None:
        raise SystemExit(f"--slot richiesto per '{spec.key}' ({n} slot: "
                         f"{', '.join(slot_labels(n))})")
    labels = slot_labels(n)
    if slot_arg in labels:
        return labels.index(slot_arg)
    if slot_arg.isdigit() and 0 <= int(slot_arg) < n:
        return int(slot_arg)
    raise SystemExit(f"slot '{slot_arg}' non valido; scegli tra: "
                     f"{', '.join(labels)} (o 0..{n - 1})")


def _cmd_list(args) -> None:
    paths = list_setups(args.car, args.track, args.root)
    if not paths:
        print(f"Nessun setup per {args.car} / {args.track} sotto {args.root}")
        return
    for p in paths:
        print(p)


def _cmd_show(args) -> None:
    setup = load(args.file)
    print(f"# {setup.car_name}  ({Path(args.file).name})\n")
    group = None
    for spec in SETUP_PARAMS:
        if not setup.present(spec):
            continue
        if spec.group != group:
            print(f"{spec.group}")
            group = spec.group
        n = setup.slots(spec)
        if n == 1:
            print(f"  {spec.label:22} {setup.physical(spec):>20}")
        else:
            labels = slot_labels(n)
            cells = "  ".join(
                f"{labels[i]}={setup.click(spec, i)}" for i in range(n)
            )
            print(f"  {spec.label:22} {cells}")


def _cmd_bump(args) -> None:
    spec = _SPECS.get(args.param)
    if spec is None:
        raise SystemExit(f"parametro sconosciuto: {args.param}\n"
                         f"disponibili: {', '.join(_SPECS)}")
    before = load(args.file)
    if not before.present(spec):
        raise SystemExit(f"'{spec.key}' non presente in questo setup")
    slot = _resolve_slot(before, spec, args.slot)
    after = before.copy()
    new_val = after.adjust(spec, slot, args.clicks)

    changes = diff(before, after)
    print(format_diff(changes))
    if not args.apply:
        print("\n(anteprima — usa --apply per scrivere)")
        return

    dest_dir = Path(args.file).parent
    name = args.as_name or (Path(args.file).stem + "_ACCoach")
    out = save(after, dest_dir, name, overwrite=args.overwrite)
    print(f"\nScritto: {out}")
    print("→ Rientra ai box → schermata Setup → carica "
          f"'{out.stem}' → riparti.")
    _ = new_val


def _cmd_undo(args) -> None:
    restored = undo(args.file)
    print(f"Ripristinato dal backup: {restored}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="accoach.setup.cli",
                                description="Demo lettura/scrittura setup ACC")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="elenca i setup per auto+pista")
    pl.add_argument("--car", required=True)
    pl.add_argument("--track", required=True)
    pl.add_argument("--root", default=SETUPS_ROOT, type=Path)
    pl.set_defaults(func=_cmd_list)

    ps = sub.add_parser("show", help="mostra i parametri di un setup")
    ps.add_argument("file")
    ps.set_defaults(func=_cmd_show)

    pb = sub.add_parser("bump", help="modifica un parametro (anteprima o scrittura)")
    pb.add_argument("file")
    pb.add_argument("--param", required=True)
    pb.add_argument("--slot", default=None)
    pb.add_argument("--clicks", required=True, type=int)
    pb.add_argument("--apply", action="store_true")
    pb.add_argument("--as", dest="as_name", default=None,
                    help="nome del file di destinazione (senza .json)")
    pb.add_argument("--overwrite", action="store_true")
    pb.set_defaults(func=_cmd_bump)

    pu = sub.add_parser("undo", help="ripristina un setup dall'ultimo backup")
    pu.add_argument("file")
    pu.set_defaults(func=_cmd_undo)
    return p


def main(argv: list[str] | None = None) -> None:
    # The Windows console defaults to cp1252, which can't encode "→" or accents;
    # switch our streams to UTF-8 so the diff/advice text renders everywhere.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")        # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
