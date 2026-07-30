"""Spike bordi pista: la lettura del formato, verificata senza Assetto Corsa.

Lo spike vive in ``tools/`` e non entra nel bundle, ma il pezzo che *risponde
alla domanda* — dove finisce l'asfalto — è aritmetica su byte, e un offset
sbagliato di quattro byte è esattamente ciò che nel tentativo precedente aveva
prodotto «gas = 36.79». Un errore così non si vede guardando un disegno: si vede
solo qui.

Il file di prova è costruito qui dentro, quindi questi test girano anche su una
macchina dove il gioco non è installato.
"""
import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import track_edges as te


def _spline_bytes(points, details, version=7, detail_count=None):
    """Un fast_lane.ai sintetico: intestazione, punti, conteggio RIPETUTO, dettagli."""
    n = len(points)
    out = bytearray(struct.pack("<4i", version, n, 0, 0))
    for i, (x, y, z) in enumerate(points):
        out += struct.pack("<3f f i", x, y, z, float(i), i)
    out += struct.pack("<i", n if detail_count is None else detail_count)
    for d in details:
        out += struct.pack("<18f", *d)
    return bytes(out)


def _detail(side_l=3.0, side_r=7.0, fx=0.0, fz=1.0):
    """Un record di dettaglio con solo i campi che questo strumento usa."""
    d = [0.0] * 18
    d[te._SIDE_L], d[te._SIDE_R] = side_l, side_r
    d[te._FX], d[te._FZ] = fx, fz
    return d


def _write(tmp_path, blob) -> Path:
    p = tmp_path / "fast_lane.ai"
    p.write_bytes(blob)
    return p


# --- il formato -------------------------------------------------------------

def test_the_repeated_count_is_where_the_details_start(tmp_path):
    """I quattro byte che mancavano al primo tentativo. Senza di loro ogni float
    del blocco dettagli si legge sfasato, e i valori sembrano rumore."""
    pts = [(0.0, 0.0, float(i)) for i in range(4)]
    det = [_detail(side_l=1.0 + i) for i in range(4)]
    p = _write(tmp_path, _spline_bytes(pts, det))
    got_pts, got_det = te.read_spline(p)
    assert len(got_pts) == len(got_det) == 4
    assert [round(d[te._SIDE_L], 3) for d in got_det] == [1.0, 2.0, 3.0, 4.0]


def test_a_detail_count_that_disagrees_is_refused(tmp_path):
    """Se i due conteggi non coincidono non stiamo leggendo quello che pensiamo:
    meglio fermarsi che pubblicare bordi inventati."""
    p = _write(tmp_path, _spline_bytes([(0.0, 0.0, 0.0)], [_detail()], detail_count=99))
    with pytest.raises(SystemExit):
        te.read_spline(p)


def test_only_version_7_is_claimed(tmp_path):
    p = _write(tmp_path, _spline_bytes([(0.0, 0.0, 0.0)], [_detail()], version=6))
    with pytest.raises(SystemExit):
        te.read_spline(p)


# --- la geometria -----------------------------------------------------------

def test_the_edges_are_the_stated_distances_across_the_track():
    """Auto che va verso +z: il bordo sinistro sta a sideLeft su -x, il destro a
    sideRight su +x. Le due distanze sono quelle dichiarate, non una media."""
    pts = [(0.0, 0.0, 0.0)]
    det = [_detail(side_l=3.0, side_r=7.0, fx=0.0, fz=1.0)]
    (lx, lz), (rx, rz) = te.edges(pts, det, 0)
    assert (round(lx, 3), round(lz, 3)) == (-3.0, 0.0)
    assert (round(rx, 3), round(rz, 3)) == (7.0, 0.0)


def test_width_is_measured_on_the_ground_not_along_the_slope():
    """Il vettore avanti ha anche una componente verticale in salita; usarla
    allargherebbe la pista di quanto sale, che non è larghezza."""
    pts = [(0.0, 0.0, 0.0)]
    det = [_detail(side_l=5.0, side_r=5.0, fx=0.0, fz=1.0)]
    (lx, _), (rx, _) = te.edges(pts, det, 0)
    assert math.isclose(abs(rx - lx), 10.0, abs_tol=1e-6)


def test_lateral_says_which_side_and_how_far():
    pts = [(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]
    det = [_detail(side_l=3.0, side_r=7.0), _detail(side_l=3.0, side_r=7.0)]
    off, sl, sr = te.lateral(pts, det, -2.0, 0.0)
    assert (round(off, 3), sl, sr) == (2.0, 3.0, 7.0)     # 2 m verso sinistra
    assert te.lateral(pts, det, 4.0, 0.0)[0] == pytest.approx(-4.0)
