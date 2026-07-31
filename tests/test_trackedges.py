"""I bordi dell'asfalto letti dai dati di Assetto Corsa — e i modi di dire di no.

La decodifica è provata in `tests/test_track_edges.py` (lo spike) e in
`SPIKE-BORDI.md`. Qui si tiene fermo il lato prodotto, che è quasi tutto
**rifiuto**: senza il gioco installato, senza quel file, con un file di un'altra
versione, o — il caso che conta — con la pista installata che *non è* quella su
cui il giro è stato guidato, la risposta deve essere None e non un nastro
plausibile disegnato 187 metri più in là.

Il file di prova è costruito qui, quindi questi test girano anche dove AC non c'è.
"""
import struct
from pathlib import Path

import pytest

from accoach import trackedges as te


class _P:
    """Il minimo che `aligned` guarda di un punto del giro."""

    __slots__ = ("x", "z")

    def __init__(self, x, z):
        self.x, self.z = x, z


def _spline(n=64, side_l=4.0, side_r=6.0, ox=0.0, oz=0.0, version=7, repeat=None):
    """Un fast_lane.ai sintetico: un rettilineo lungo z, largo side_l + side_r."""
    pts = [(ox, 0.0, oz + i * 2.0) for i in range(n)]
    out = bytearray(struct.pack("<4i", version, n, 0, 0))
    for i, (x, y, z) in enumerate(pts):
        out += struct.pack("<3f f i", x, y, z, float(i), i)
    out += struct.pack("<i", n if repeat is None else repeat)
    for _ in range(n):
        d = [0.0] * 18
        d[te._SIDE_L], d[te._SIDE_R] = side_l, side_r
        d[te._FX], d[te._FZ] = 0.0, 1.0
        out += struct.pack("<18f", *d)
    return bytes(out)


def _write(tmp_path, blob, name="fast_lane.ai") -> Path:
    d = tmp_path / "ai"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(blob)
    return p


# --- leggere ----------------------------------------------------------------

def test_the_width_is_the_two_sides_together(tmp_path):
    e = te.read_edges(_write(tmp_path, _spline(side_l=4.0, side_r=6.0)))
    assert e is not None
    assert e.width_m() == 10.0
    left, right = e.edge_points()
    assert len(left) == len(right) == len(e)


def test_the_two_edges_come_out_either_side_of_the_line(tmp_path):
    """Linea che corre lungo +z: un bordo a 4 m da una parte, l'altro a 6
    dall'altra. Le due distanze restano quelle dichiarate, non una media."""
    e = te.read_edges(_write(tmp_path, _spline(side_l=4.0, side_r=6.0)))
    left, right = e.edge_points()
    assert left[0][0] == pytest.approx(-4.0, abs=1e-3)
    assert right[0][0] == pytest.approx(6.0, abs=1e-3)


@pytest.mark.parametrize("blob", [
    b"", b"\x00" * 8,
    _spline(version=6),                 # una versione che non abbiamo decodificato
    _spline(repeat=999),                # i due conteggi non coincidono
])
def test_anything_we_did_not_decode_reads_as_nothing(tmp_path, blob):
    """Un file che non è quello che pensiamo non va letto "alla meglio": ogni
    float sfasato di quattro byte sembra comunque un numero."""
    assert te.read_edges(_write(tmp_path, blob)) is None


# --- il controllo che conta: è la stessa pista? -----------------------------

def test_a_lap_on_the_same_track_model_is_accepted(tmp_path):
    e = te.read_edges(_write(tmp_path, _spline()))
    lap = [_P(0.0, i * 2.0) for i in range(64)]
    assert te.aligned(e, lap)


def test_a_lap_from_another_version_of_the_same_circuit_is_refused(tmp_path):
    """Stessa forma, altro posto: è esattamente il caso Monza (187 m di scarto),
    e disegnarlo darebbe un nastro credibile attorno alla macchina sbagliata."""
    e = te.read_edges(_write(tmp_path, _spline()))
    lap = [_P(187.0, i * 2.0 - 154.0) for i in range(64)]
    assert not te.aligned(e, lap)


def test_a_lap_without_coordinates_is_refused(tmp_path):
    e = te.read_edges(_write(tmp_path, _spline()))
    assert not te.aligned(e, [_P(0.0, 0.0) for _ in range(64)])


# --- ritagliare la curva ----------------------------------------------------

def test_the_crop_follows_the_stretch_that_was_driven(tmp_path):
    e = te.read_edges(_write(tmp_path, _spline(n=200)))
    drive = [(0.0, z) for z in range(40, 120, 2)]
    got = te.crop(e, drive, pad=2)
    assert got and len(got["left"]) == len(got["right"])
    zs = [p[1] for p in got["left"]]
    assert min(zs) < 40 and max(zs) > 118, "il pad deve sporgere ai due estremi"


def test_a_corner_may_straddle_the_start_line(tmp_path):
    """La linea del traguardo non è un muro: una curva che la scavalca deve avere
    il suo nastro, il che vuol dire camminare *avanti* passando dallo zero."""
    e = te.read_edges(_write(tmp_path, _spline(n=200)))   # z va da 0 a 398
    got = te.crop(e, [(0.0, 380.0), (0.0, 4.0)], pad=0)
    assert got is not None and len(got["left"]) < 30


def test_a_crop_that_would_wrap_most_of_the_lap_is_refused(tmp_path):
    """Gli stessi due estremi nell'ordine opposto sono il caso patologico: un
    'nastro' lungo quasi tutta la pista dentro il riquadro di una curva."""
    e = te.read_edges(_write(tmp_path, _spline(n=200)))
    assert te.crop(e, [(0.0, 4.0), (0.0, 380.0)]) is None


def test_the_crop_is_capped_so_the_payload_stays_small(tmp_path):
    e = te.read_edges(_write(tmp_path, _spline(n=1200)))
    got = te.crop(e, [(0.0, 20.0), (0.0, 2000.0)], max_points=40)
    assert got is None or len(got["left"]) <= 40


# --- senza il gioco ---------------------------------------------------------

def test_no_game_no_edges(monkeypatch):
    """HONE non ha mai avuto bisogno che AC fosse installato: chi guida solo ad
    ACC, o ha spostato la libreria Steam, deve vedere la pagina di sempre."""
    monkeypatch.setattr(te, "tracks_dir", lambda: None)
    te._cache.clear()
    assert te.spline_path("monza") is None
    assert te.edges_for("monza") is None
