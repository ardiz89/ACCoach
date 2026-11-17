"""Quanto e' costante il pilota, misurato sui giri in archivio (sola lettura).

Serve a scegliere le soglie del controllo di costanza dell'Ingegnere (tappa
chiesta dal pilota il 16/11) sui numeri veri, non a occhio. Uso:

    python tools/costanza_archivio.py [cartella dei giri] [auto]

(predefiniti: la cartella dei giri dell'app e la McLaren 720S). Non scrive niente.

Per ogni serata: gli stint (benzina che sale, o una pausa di oltre 5 minuti), i
giri puliti e validi entro il 105 % del migliore dello stint, senza il primo
dopo la sosta. Le curve di frenata dal giro piu' veloce dello stint. Per curva
e per giro:

* **stacco**: dove il freno passa `_BRAKE_ON`, interpolato fra due campioni, in
  metri lungo la linea del giro di riferimento;
* **v meta' frenata**: la velocita' a meta' fra lo stacco e il punto piu' lento
  del giro di riferimento;
* **v minima** nella curva.

Lo scarto di un giro e' la mediana sulle curve di |valore - mediana dello
stint|; la dispersione di una finestra di 3 giri puliti (come la lettura
dell'Ingegnere) e' la mediana sulle curve di max - min.

Misurato il 16/11 su 73 giri puliti: lo **stacco** non si risolve sotto un
campione (~7,5 m in frenata a ~9 Hz), la **velocita' minima** si' (scarto 1,5
km/h sui giri puliti, 4,1 su quelli con un'uscita). Dal 16/11 il registratore
tiene il fotogramma dello stacco e quello prima: la riga «stacchi a frequenza
piena» dice quanti giri lo hanno, e solo su quelli lo stacco e' una misura.

Le curve si numerano dal giro di riferimento di ciascuno stint: fra due stint i
numeri non corrispondono, e qui non si confrontano.
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from accoach.recording.lap import BRAKE_ON as _BRAKE_ON  # noqa: E402
from accoach.recording.storage import laps_root, list_lap_files, load_lap  # noqa: E402
from accoach.track import detect_corners  # noqa: E402
from accoach.trajectory import line_points, path_length  # noqa: E402

#: Due fotogrammi piu' vicini di cosi' attorno allo stacco: preso alla frequenza
#: piena e non dalla decimazione (~100 ms).
_FULL_RATE_MS = 60


def _interp_at(samples, pos, attr):
    for a, b in zip(samples, samples[1:]):
        if a.pos <= pos <= b.pos and b.pos > a.pos:
            f = (pos - a.pos) / (b.pos - a.pos)
            return getattr(a, attr) + f * (getattr(b, attr) - getattr(a, attr))
    return None


def _onset(samples, c):
    """(posizione interpolata dello stacco, ms fra i due fotogrammi) o None."""
    prev = None
    for s in samples:
        if s.pos < c.entry_pos:
            prev = s
            continue
        if s.pos > c.exit_pos:
            return None
        if s.brake >= _BRAKE_ON:
            if prev is None or prev.brake >= _BRAKE_ON or s.brake == prev.brake:
                return s.pos, None
            f = (_BRAKE_ON - prev.brake) / (s.brake - prev.brake)
            return prev.pos + f * (s.pos - prev.pos), s.t_ms - prev.t_ms
        prev = s
    return None


def _q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))]


def _stints(laps):
    out, cur, lt, lf = [], [], None, None
    for t, lap, raw in laps:
        fields = raw.get("fields", [])
        fi = fields.index("fuel") if "fuel" in fields else None
        fuel = raw["samples"][0][fi] if fi is not None and raw.get("samples") else None
        gap = (t - lt).total_seconds() - raw["lap_time_ms"] / 1000 if lt else 0
        if (gap > 300 or (fuel is not None and lf is not None and fuel > lf + 1)) and cur:
            out.append(cur)
            cur = []
        cur.append((t, lap, raw))
        lt = t
        lf = fuel if fuel is not None else lf
    if cur:
        out.append(cur)
    return out


def main(folder: Path, car: str) -> None:
    evenings: dict[tuple[str, str], list[Path]] = {}
    for p in list_lap_files(folder):
        parts = p.name.split("__")
        if len(parts) < 4 or parts[1] != car:
            continue
        evenings.setdefault((parts[0], parts[-1][:8]), []).append(p)

    dev = {"clean": {"on": [], "vmid": [], "vmin": []},
           "off": {"on": [], "vmid": [], "vmin": []}}
    win_on, win_vmid, full, onsets = [], [], 0, 0
    for (track, day), paths in sorted(evenings.items(), key=lambda kv: kv[0][1]):
        laps = []
        for p in paths:
            try:
                lap = load_lap(p)
                raw = json.load(gzip.open(p))
            except Exception:  # noqa: BLE001 - un file rovinato non ferma la misura
                continue
            laps.append((datetime.fromisoformat(raw["recorded_utc"]), lap, raw))
        laps.sort(key=lambda x: x[0])
        for st in _stints(laps):
            body = st[1:]
            good = [x for x in body if x[2].get("clean") and x[2].get("valid")]
            if len(good) < 3:
                continue
            best = min(x[2]["lap_time_ms"] for x in good)
            good = [x for x in good if x[2]["lap_time_ms"] <= best * 1.05]
            off = [x for x in body if not (x[2].get("clean") and x[2].get("valid"))
                   and x[2]["lap_time_ms"] <= best * 1.15]
            if len(good) < 3:
                continue
            ref = min(good, key=lambda x: x[2]["lap_time_ms"])[1]
            pts = line_points(ref)
            corners = []
            for c in detect_corners(ref.samples):
                inside = [s for s in ref.samples if c.entry_pos <= s.pos <= c.exit_pos]
                if len(inside) >= 3 and max(s.brake for s in inside) >= 0.25:
                    corners.append(c)
            if not pts or not corners:
                continue

            def measure(lap):
                nonlocal full, onsets
                out = {}
                for c in corners:
                    got, ref_on = _onset(lap.samples, c), _onset(ref.samples, c)
                    li = [s for s in lap.samples if c.entry_pos <= s.pos <= c.exit_pos]
                    if got is None or ref_on is None or not li:
                        continue
                    on, gap = got
                    onsets += 1
                    full += gap is not None and gap <= _FULL_RATE_MS
                    inside = [s for s in ref.samples if c.entry_pos <= s.pos <= c.exit_pos]
                    slow = min(inside, key=lambda s: s.speed_kmh).pos
                    vmid = _interp_at(lap.samples, (ref_on[0] + slow) / 2, "speed_kmh")
                    if vmid is not None:
                        out[c.index] = (path_length(pts, 0.0, on), vmid,
                                        min(s.speed_kmh for s in li))
                return out

            G = [measure(x[1]) for x in good]
            D = [measure(x[1]) for x in off]
            med = {}
            for c in corners:
                vals = [g[c.index] for g in G if c.index in g]
                if len(vals) >= 3:
                    med[c.index] = tuple(statistics.median(v[k] for v in vals)
                                         for k in range(3))
            for key, group in (("clean", G), ("off", D)):
                for g in group:
                    for k, name in enumerate(("on", "vmid", "vmin")):
                        d = [abs(g[i][k] - med[i][k]) for i in med if i in g]
                        if d:
                            dev[key][name].append(statistics.median(d))
            for k in range(len(G) - 2):
                w = G[k:k + 3]
                common = [i for i in med if all(i in x for x in w)]
                if len(common) >= 3:
                    win_on.append(statistics.median(
                        max(x[i][0] for x in w) - min(x[i][0] for x in w) for i in common))
                    win_vmid.append(statistics.median(
                        max(x[i][1] for x in w) - min(x[i][1] for x in w) for i in common))

    if not win_on:
        print("Nessuno stint con almeno 3 giri puliti.")
        return
    print(f"Stacchi a frequenza piena: {full} su {onsets}")
    print("\nScarto di un giro dalla mediana dello stint (mediana sulle curve)")
    for name, unit in (("on", "m"), ("vmid", "km/h"), ("vmin", "km/h")):
        c, d = dev["clean"][name], dev["off"][name]
        tail = f"p50 {_q(d, .5):5.1f}  p90 {_q(d, .9):5.1f}" if d else "-"
        label = {"on": "stacco", "vmid": "v meta' frenata", "vmin": "v minima"}[name]
        print(f"  {label:16s} puliti n={len(c):3d}: p50 {_q(c, .5):5.1f}  p90 {_q(c, .9):5.1f}"
              f"  max {max(c):5.1f} {unit}  |  con uscita n={len(d):3d}: {tail} {unit}")
    print(f"\nFinestre di 3 giri puliti: {len(win_on)}")
    for label, vals, unit in (("stacco", win_on, "m"), ("v meta' frenata", win_vmid, "km/h")):
        print(f"  {label:16s} " + "  ".join(f"p{int(p * 100)} {_q(vals, p):.1f}"
                                         for p in (.1, .25, .5, .75, .9))
              + f"  max {max(vals):.1f} {unit}")


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else laps_root()
    car = sys.argv[2] if len(sys.argv) > 2 else "mclaren-720s-gt3-evo"
    main(folder, car)
