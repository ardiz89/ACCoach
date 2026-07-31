"""Spike: la linea IA di Assetto Corsa Competizione (`fastlane.ai`, versione 8).

ACC tiene la geometria delle piste dentro un `.pak` di Unreal Engine da 17 GB.
Ma **fuori** dal pak pubblica una `fastlane.ai` per ciascuna delle 25 piste, in
`AC2/Content/Cache/<pista>/`. Se si legge, ACC smette di dipendere dal fatto che
tu abbia anche Assetto Corsa installato.

La decodifica della versione 7 (AC) **non si trasporta**: provate tutte le
dimensioni di record da 12 a 88 byte e tutti gli offset, nessuna dava una
polilinea vicina ai 5793 m di Monza. Il motivo, guardando i byte invece che
cercando alla cieca: le coordinate sono a **64 bit**, non a 32.

Stato: **punti decodificati e validati su tutte e 25 le piste, larghezze solo su
9.** Vedi `SPIKE-ACC-SPLINE.md`. Fuori dal bundle, come lo spike dei bordi.

    python tools/acc_fastlane.py                # tutte le piste installate
    python tools/acc_fastlane.py monza --dump 5 # i primi record, in chiaro
"""
import argparse
import math
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from accoach.trackedges import _steam_libraries          # noqa: E402

#: header(16) = versione, conteggio, 0, 0. Poi i punti.
_HEAD = 16
#: Un punto: x, y, z, distanza cumulata — quattro DOUBLE — piu' cinque campi
#: che non servono qui. Nove double in tutto.
_POINT = 72
#: Il blocco dettagli, a valle del conteggio ripetuto. Regge su 9 piste su 25.
_DETAIL = 80
_SL, _SR = 5, 6

#: Lunghezze pubblicate, per avere un secondo parere su ogni decodifica.
PUBLISHED = {
    "barcelona": 4655, "brands_hatch": 3916, "cota": 5513, "donington": 4020,
    "hungaroring": 4381, "imola": 4909, "indianapolis": 3925, "kyalami": 4522,
    "laguna_seca": 3602, "misano": 4226, "monza": 5793, "mount_panorama": 6213,
    "nurburgring": 5148, "nurburgring_24h": 25378, "oulton_park": 4307,
    "paul_ricard": 5842, "red_bull_ring": 4318, "silverstone": 5891,
    "snetterton": 4779, "spa": 7004, "suzuka": 5807, "valencia": 4005,
    "watkins_glen": 5552, "zandvoort": 4259, "zolder": 4011,
}


def cache_dir():
    for lib in _steam_libraries():
        p = lib / "steamapps" / "common" / "Assetto Corsa Competizione" / "AC2" / "Content" / "Cache"
        if p.is_dir():
            return p
    return None


def read(path: Path):
    """{'points': [(x, y, z, cum)], 'sides': [(sx, dx)], 'header': n} o None.

    Il conteggio dell'header e' **il doppio** dei punti — vero su tutte e 25 le
    piste, rapporto 2.00 esatto. Che cosa conti davvero non e' chiaro, quindi i
    punti si contano camminando finche' restano sensati, non fidandosi.
    """
    b = path.read_bytes()
    if len(b) < _HEAD + _POINT:
        return None
    ver, header = struct.unpack_from("<2i", b, 0)
    if ver != 8:
        return None
    pts = []
    prev = None
    while True:
        at = _HEAD + len(pts) * _POINT
        if at + 32 > len(b):
            break
        x, y, z, d = struct.unpack_from("<4d", b, at)
        if not (abs(x) < 20000 and abs(y) < 800 and abs(z) < 20000 and 0 <= d < 60000):
            break
        if prev and math.hypot(x - prev[0], z - prev[1]) > 80:
            break
        prev = (x, z)
        pts.append((x, y, z, d))
    if len(pts) < 50:
        return None

    det = _HEAD + len(pts) * _POINT
    # Come nella v7, il conteggio si ripete: e' l'intestazione dei dettagli.
    repeated = struct.unpack_from("<i", b, det)[0] if det + 4 <= len(b) else None
    det += 4
    sides = []
    for i in range(len(pts)):
        at = det + i * _DETAIL
        if at + _DETAIL > len(b):
            break
        sl = struct.unpack_from("<f", b, at + _SL * 4)[0]
        sr = struct.unpack_from("<f", b, at + _SR * 4)[0]
        sides.append((sl, sr) if (0.3 < sl < 40 and 0.3 < sr < 40) else None)
    return {"header": header, "repeated": repeated, "points": pts,
            "sides": sides, "detail_at": det, "size": len(b)}


def length(pts):
    tot = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][2] - pts[i - 1][2])
              for i in range(1, len(pts)))
    return tot + math.hypot(pts[0][0] - pts[-1][0], pts[0][2] - pts[-1][2])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("track", nargs="?", help="una pista sola")
    ap.add_argument("--dump", type=int, default=0, help="stampa N record di dettaglio")
    a = ap.parse_args()

    root = cache_dir()
    if root is None:
        print("ACC non installato qui.")
        return
    names = [a.track] if a.track else sorted(p.name for p in root.iterdir() if p.is_dir())
    print(f"{'pista':18s} {'hdr':>6s} {'punti':>6s} {'cum':>9s} {'poli':>9s} "
          f"{'pubbl.':>8s} {'scarto':>7s} {'lati':>6s} {'largh':>6s}")
    for name in names:
        p = root / name / "fastlane.ai"
        if not p.exists():
            continue
        got = read(p)
        if not got:
            print(f"{name:18s} non decodificata")
            continue
        pts = got["points"]
        cum = pts[-1][3]
        pub = PUBLISHED.get(name, 0)
        ws = [s[0] + s[1] for s in got["sides"] if s]
        frac = len(ws) / len(pts)
        err = f"{100 * (cum - pub) / pub:+6.1f}%" if pub else "     —"
        wid = f"{statistics.median(ws):5.1f}m" if ws else "    —"
        print(f"{name:18s} {got['header']:6d} {len(pts):6d} {cum:8.0f}m "
              f"{length(pts):8.0f}m {pub:7d}m {err} {100 * frac:5.0f}% {wid}")
        if a.dump:
            b = p.read_bytes()
            print("   record di dettaglio, come float:")
            for i in range(a.dump):
                v = struct.unpack_from("<20f", b, got["detail_at"] + i * _DETAIL)
                print("     " + " ".join(f"{x:8.3f}" if abs(x) < 1e5 else "  grande"
                                         for x in v))


if __name__ == "__main__":
    main()
