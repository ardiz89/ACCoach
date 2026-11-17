"""Rigioca i giri veri di una serata nell'Ingegnere (sola lettura).

Dopo una prova in pista chi sviluppa vuole vedere cosa ha deciso il motore, giro
per giro, sugli stessi numeri. Era uno script usa-e-getta (16/11, trovo' due
difetti veri); ora e' un modulo con test e il comando ``replay-engineer``.

Due modi di decidere quando il pilota ha applicato una modifica:

* **col registro della serata** (``ingegnere-AAAAMMGG.jsonl``) gli eventi dei
  box (``setup``, ``applied``, ``base``) entrano nel motore all'ora a cui sono
  stati scritti, fra un giro e l'altro;
* **senza registro** vale la regola dello script: una proposta BOX e' applicata
  quando il giro dopo apre uno stint (benzina +1 L o salto di 0,4 psi), e la
  base richiesta e' confermata subito.

E' una simulazione: i giri veri sono stati guidati con le modifiche del motore
di allora, quindi i verdetti dicono come ragiona il motore *attuale* su quei
numeri, non cosa sarebbe successo in pista.

Orari: i giri portano l'ora in UTC (``recorded_utc``); il registro scrive l'ora
LOCALE della macchina, senza fuso. Si confrontano entrambe come istanti
(``datetime`` consapevole: il registro e' letto nel fuso locale di questa
macchina). Le righe riportano ``t`` in ora locale.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..coaching.diagnosis import build_lap_stats
from ..recording.storage import list_lap_files, load_lap
from .core import DecisionKind, SetupReport
from .factory import engineer_for

_EVENTS = ("setup", "applied", "base")
#: Quanto deve salire la benzina fra due giri per dire «sei rientrato».
_REFUEL_L = 1.0
#: Salto di pressione fra due giri che vale come «sei rientrato».
_JUMP_PSI = 0.4


def _utc(text: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _local(text: str) -> datetime | None:
    """Un'ora scritta dal registro (locale, senza fuso) come istante."""
    try:
        d = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return d.astimezone() if d.tzinfo is None else d


def _lap_files(laps_dir: Path, track: str, day: str, car: str | None) -> list[Path]:
    out = []
    for p in list_lap_files(laps_dir):
        parts = p.name.split("__")
        if len(parts) < 4 or parts[0].lower() != track.lower():
            continue
        if f"{day}T" not in parts[-1]:
            continue
        if car and parts[1].lower() != car.lower():
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.name.split("__")[-1])


def _read_events(log: Path | None,
                 mine: set[tuple[str, str]] | None = None
                 ) -> list[tuple[datetime, dict]]:
    """Gli eventi dei box del registro che sono di *questa* sessione.

    Il registro e' uno per giorno: puo' contenere anche una sessione su un'altra
    pista o un'altra auto. Un evento appartiene alla sessione della prima riga
    ``lap`` che lo segue nel tempo (o, se dopo non ce n'e', di quella che lo
    precede) e si tiene solo se quella riga ha auto e pista dei giri rigiocati
    (``mine``, in minuscolo). Senza righe ``lap`` non si puo' dire: si tengono.
    """
    if log is None or not Path(log).is_file():
        return []
    rows: list[tuple[datetime, dict]] = []
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("kind") not in (*_EVENTS, "lap"):
            continue
        when = _local(str(row.get("t", "")))
        if when is not None:
            rows.append((when, row))
    rows.sort(key=lambda e: e[0])
    laps = [(w, r) for w, r in rows if r["kind"] == "lap"]

    def keep(when: datetime) -> bool:
        if mine is None or not laps:
            return True
        owner = next((r for w, r in laps if w >= when), laps[-1][1])
        key = (str(owner.get("car", "")).lower(), str(owner.get("track", "")).lower())
        return key in mine

    return [(w, r) for w, r in rows if r["kind"] in _EVENTS and keep(w)]


def _feed(eng, row: dict):
    """Un evento del registro nel motore; ritorna la decisione, se c'e'."""
    kind = row["kind"]
    if kind == "setup":
        report = SetupReport.from_dict(row["report"])
        return eng.setup_seen(report, at_exit=row.get("at") == "exit")
    if kind == "applied":
        eng.mark_applied()
        return None
    expected = row.get("expected")
    return eng.base_confirmed(
        expected=expected if isinstance(expected, bool) else None,
        dials=row.get("dials"))


def _row(kind: str, when: datetime | None, **kw) -> dict:
    base = {"t": when.astimezone().isoformat(timespec="seconds") if when else "",
            "kind": kind, "lap_ms": None, "fuel": None, "front": None,
            "rear": None, "stint": None, "settling": None, "ok": None,
            "decision": None, "message": None, "dropped": 0}
    base.update(kw)
    return base


def replay(laps_dir: Path, track: str, day: str, car: str | None = None,
           log: Path | None = None,
           skipped: list[Path] | None = None) -> list[dict]:
    """Una riga per giro (e per evento del registro) della serata ``day``.

    Righe: ``{"t", "kind", "lap_ms", "fuel", "front", "rear", "stint",
    "settling", "ok", "decision", "message", "dropped"}``; ``kind`` e' ``"lap"`` o il tipo
    di evento, ``decision`` il tipo di decisione (``DecisionKind.value``).
    Sola lettura: apre i giri e il registro, non scrive niente. Un giro che non
    si legge si salta; se ``skipped`` e' una lista ci finisce il suo percorso.
    """
    laps = []
    for p in _lap_files(Path(laps_dir), track, day, car):
        try:
            lap = load_lap(p)
        except Exception:  # noqa: BLE001 - file rotto: si salta e si conta
            if skipped is not None:
                skipped.append(p)
            continue
        if lap.samples:
            laps.append(lap)
    mine = {(l.car_model.lower(), l.track.lower()) for l in laps}
    events = _read_events(log, mine)
    use_log = bool(events)
    rows: list[dict] = []
    eng = None
    pending_box = False
    ev = 0
    for i, lap in enumerate(laps):
        when = _utc(lap.recorded_utc)
        if eng is None:
            eng = engineer_for(lap.car_model, lap.track, is_acc=True)
        while use_log and when is not None and ev < len(events) and events[ev][0] <= when:
            at, row = events[ev]
            ev += 1
            d = _feed(eng, row)
            rows.append(_row(row["kind"], at,
                             decision=d.kind.value if d is not None else None,
                             message=d.message if d is not None else None))
        st = build_lap_stats(lap)
        d = eng.observe(st)
        p = st.pressures_hot or {}
        rows.append(_row("lap", when, lap_ms=lap.lap_time_ms, fuel=st.fuel_l,
                         front=p.get("front"), rear=p.get("rear"),
                         stint=st.stint, settling=st.settling,
                         ok=bool(st.stable and st.warmed_up),
                         decision=d.kind.value, message=d.message,
                         dropped=len(eng.last_dropped)))
        if use_log:
            continue
        if d.kind is DecisionKind.PROPOSE and d.change and d.change.tag == "BOX":
            pending_box = True
        nxt = laps[i + 1] if i + 1 < len(laps) else None
        if pending_box and nxt is not None:
            ns = build_lap_stats(nxt)
            np_ = ns.pressures_hot or {}
            jump = any(abs(np_[a] - p[a]) >= _JUMP_PSI
                       for a in ("front", "rear") if p.get(a) and np_.get(a))
            if ns.fuel_l > st.fuel_l + _REFUEL_L or jump:
                eng.mark_applied()
                pending_box = False
        if d.confirm_base:
            eng.base_confirmed()
    return rows


def _format(i: int, r: dict) -> str:
    if r["kind"] != "lap":
        said = f" | {r['decision']:10s} {(r['message'] or '')[:150]}" if r["decision"] else ""
        return f"      -- {r['kind']} {r['t'][11:16]}{said}"
    flags = ("A" if r["settling"] else " ") + ("ok" if r["ok"] else "--")
    cut = f" -{r['dropped']}" if r.get("dropped") else ""
    return (f"{i:2d} {r['t'][11:16]} {r['lap_ms'] / 1000:7.3f}s "
            f"fuel {r['fuel'] or 0:4.1f} F {r['front'] or 0:5.2f} "
            f"R {r['rear'] or 0:5.2f} stint {r['stint']} {flags}{cut} "
            f"| {r['decision']:10s} {(r['message'] or '')[:150]}")


def main(args: list[str]) -> None:
    """``replay-engineer <pista> <AAAAMMGG> [auto] [--laps DIR] [--log FILE]``.

    Le ore stampate sono LOCALI (fuso di questa macchina); i giri sono letti
    in UTC e convertiti. Senza ``--log`` si usa il registro della serata nella
    cartella dei log dell'app, se c'e'.
    """
    import argparse

    from ..config import set_language
    from ..paths import logs_dir
    from ..recording.storage import laps_root

    ap = argparse.ArgumentParser(prog="replay-engineer")
    ap.add_argument("track")
    ap.add_argument("day", help="AAAAMMGG")
    ap.add_argument("car", nargs="?")
    ap.add_argument("--laps", type=Path, default=None, help="cartella dei giri")
    ap.add_argument("--log", type=Path, default=None, help="registro della serata")
    a = ap.parse_args(args)
    set_language("it")
    log = a.log or (logs_dir() / f"ingegnere-{a.day}.jsonl")
    folder = a.laps or laps_root()
    if not Path(folder).is_dir():
        print(f"Cartella dei giri non trovata: {folder}")
        raise SystemExit(1)
    skipped: list[Path] = []
    rows = replay(folder, a.track, a.day, a.car,
                  log if log.is_file() else None, skipped)
    n = sum(r["kind"] == "lap" for r in rows)
    if skipped:
        print(f"Attenzione: {len(skipped)} file di giri illeggibili saltati.")
    if n == 0:
        print(f"Nessun giro di {a.track} del {a.day} in {folder}.")
        raise SystemExit(1)
    print(f"{n} giri ({'con' if log.is_file() else 'senza'} registro; "
          f"ore locali)\n")
    i = -1
    for r in rows:
        i += r["kind"] == "lap"
        print(_format(i, r))
