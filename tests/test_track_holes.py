"""Buchi nei dati di pista: dove l'asfalto non si sa, il nastro si interrompe.

Trovato il 2026-07-31 misurando l'archivio, non ragionando. `read_edges` scarta
i punti con un lato fuori scala — giusto: un «bordo» a centinaia di metri non è
un bordo. Li scartava però **in silenzio**, e i due superstiti ai lati del buco
si univano: a Suzuka sono **228 punti di fila**, e il nastro tagliava dritto per
**343 m** attraverso il circuito.

Un buco nei dati deve restare un buco nel disegno. Qui si tiene fermo questo, e
la conseguenza meno ovvia: l'ultimo punto prima di un buco non ha un «prossimo»
da cui prendere la direzione, e prenderlo comunque butta i due bordi di lato.
"""
import math
import struct

from accoach import trackedges as te

from test_trackedges import _write


def _ring(tmp_path, lo=60, hi=140, n=200, r=400.0):
    """Un anello con un tratto dai lati assurdi, come la Suzuka installata.

    Un circuito e non un rettilineo, perché il difetto è *geometrico*: la
    scorciatoia si vede solo su una pista che si richiude su sé stessa.
    """
    pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    out = bytearray(struct.pack("<4i", 7, n, 0, 0))
    for i, (x, z) in enumerate(pts):
        out += struct.pack("<3f f i", x, 0.0, z, float(i), i)
    out += struct.pack("<i", n)
    for i, (x, z) in enumerate(pts):
        x1, z1 = pts[(i + 1) % n]
        dx, dz = x1 - x, z1 - z
        d = math.hypot(dx, dz) or 1.0
        rec = [0.0] * 18
        wide = lo <= i < hi
        rec[te._SIDE_L] = 400.0 if wide else 4.0
        rec[te._SIDE_R] = 400.0 if wide else 6.0
        rec[te._FX], rec[te._FZ] = dx / d, dz / d
        out += struct.pack("<18f", *rec)
    return te.read_edges(_write(tmp_path, bytes(out)))


def test_the_hole_is_recorded_not_just_skipped(tmp_path):
    e = _ring(tmp_path)
    assert e.breaks, "senza registrarlo, il buco diventa una scorciatoia"
    assert len(e) == 120, "i punti fuori scala restano fuori"


def test_a_crop_over_a_hole_comes_out_in_pieces(tmp_path):
    """Una curva che cade a cavallo del buco non è una curva sola da disegnare.

    Il tratto tenuto e il tratto dopo il buco non si toccano: unirli darebbe
    centinaia di metri di «asfalto» dove il file non dice niente.
    """
    e = _ring(tmp_path)
    got = te.crop(e, [(e.x[i], e.z[i]) for i in (50, 70)], pad=0)
    assert got is not None
    for r in got["runs"]:
        for side in (r["left"], r["right"]):
            steps = [math.dist(side[i - 1], side[i]) for i in range(1, len(side))]
            assert not steps or max(steps) < 60, (
                f"salto di {max(steps):.0f} m dentro un tratto continuo")


def test_no_drawn_stretch_ever_jumps_the_gap(tmp_path):
    """La stessa regola su tutto il giro, non solo su una curva."""
    e = _ring(tmp_path)
    for run in e.runs(list(range(len(e)))):
        for a, b in zip(run, run[1:]):
            assert math.dist((e.x[a], e.z[a]), (e.x[b], e.z[b])) < 60


def test_the_edge_direction_at_a_hole_comes_from_behind(tmp_path):
    """L'ultimo punto prima del buco non ha un «prossimo».

    Preso comunque, la perpendicolare si calcola su un passo che scavalca il
    buco: punta da tutt'altra parte e i due bordi finiscono buttati di lato —
    una virata finta proprio dove il dato si interrompe. Non lo si vede dalla
    larghezza (resta 10 m: i due bordi ruotano insieme) ma dall'*orientamento*.
    """
    e = _ring(tmp_path)
    left, _right = e.edge_points()

    def ang(i):
        return math.atan2(left[i][1] - e.z[i], left[i][0] - e.x[i])

    # Su un anello di 200 punti l'orientamento gira di 1.8° a passo. Dieci volte
    # tanto è già una svolta che sulla pista non c'è.
    for run in e.runs(list(range(len(e)))):
        for a, b in zip(run, run[1:]):
            d = abs(math.degrees(ang(b) - ang(a))) % 360
            assert min(d, 360 - d) < 18, f"il bordo gira di {d:.0f}° fra {a} e {b}"


def test_a_track_without_holes_is_one_single_stretch(tmp_path):
    """Il caso normale — Spa, Imola, Monza, Spa 1998: zero punti scartati. La
    macchineria dei buchi non deve spezzettare una pista sana."""
    e = _ring(tmp_path, lo=0, hi=0)
    assert not e.breaks
    assert len(e.runs(list(range(len(e))))) == 1
