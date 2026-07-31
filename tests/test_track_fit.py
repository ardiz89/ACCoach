"""«È la stessa pista?» — la domanda che ha smesso di dipendere dal gioco.

La prima versione chiedeva *«le coordinate sono già gli stessi numeri?»*. È una
domanda sui formati dei file, non sui luoghi, e ha prodotto l'unico punto
dell'app in cui **quello che vedi dipende da quale simulatore hai avviato**: il
nastro d'asfalto compariva su AC e da nessun'altra parte. Peggio: rifiutava
**Monza**, che è Monza — solo scritta a partire da un'altra origine, 187 m più
in là.

Ora la forma guidata viene *posata* su quella del file (rotazione, traslazione e
una scala che deve venire 1), e il risultato si legge in metri.

Le due condizioni servono **tutte e due**, e questi test spiegano perché:

* la sola scala non basta — Spa 1998 combacia con Spa moderna a scala 1.000 ed è
  un altro tracciato (58 m di scarto al 95° percentile);
* il solo scarto non basta — un giro con le coordinate rotte combacia con
  **qualunque** circuito a 8 m, rimpicciolendolo settanta volte.

Le soglie vengono dai 39 giri veri contro le quattro piste installate: 24
confronti, tutti classificati giusti, col peggiore dei veri a 17.3 m e il
migliore dei falsi a 58.3 m.
"""
import math
import struct

import pytest

from accoach import trackedges as te

from test_trackedges import _write


class _P:
    """Il minimo che il fit guarda di un punto del giro."""

    __slots__ = ("x", "z")

    def __init__(self, x, z):
        self.x, self.z = x, z


def _loop(n=240, wobble=1.0):
    """Un anello **asimmetrico**.

    Non un cerchio: su un cerchio ogni rotazione combacia con ogni altra, quindi
    un test costruito lì passerebbe anche con il fit rotto.
    """
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = 300.0 + 120.0 * math.cos(a) + wobble * 60.0 * math.sin(2 * a)
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def _spline_of(tmp_path, pts, side_l=4.0, side_r=6.0, name="fast_lane.ai"):
    n = len(pts)
    out = bytearray(struct.pack("<4i", 7, n, 0, 0))
    for i, (x, z) in enumerate(pts):
        out += struct.pack("<3f f i", x, 0.0, z, float(i), i)
    out += struct.pack("<i", n)
    for i, (x, z) in enumerate(pts):
        x1, z1 = pts[(i + 1) % n]
        dx, dz = x1 - x, z1 - z
        d = math.hypot(dx, dz) or 1.0
        rec = [0.0] * 18
        rec[te._SIDE_L], rec[te._SIDE_R] = side_l, side_r
        rec[te._FX], rec[te._FZ] = dx / d, dz / d
        out += struct.pack("<18f", *rec)
    return te.read_edges(_write(tmp_path, bytes(out), name))


def _moved(pts, dx=0.0, dz=0.0, deg=0.0, scale=1.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [_P(scale * (x * c - z * s) + dx, scale * (x * s + z * c) + dz)
            for x, z in pts]


# --- accettare -------------------------------------------------------------

def test_the_same_circuit_written_from_another_origin_is_accepted(tmp_path):
    """Il caso Monza. Prima veniva rifiutato per 187 m di traslazione, che è
    una proprietà del file e non del posto."""
    e = _spline_of(tmp_path, _loop())
    got = te.fit(e, _moved(_loop(), dx=187.0, dz=-154.0))
    assert got is not None
    assert got.p95_m < 1.0 and got.scale == pytest.approx(1.0, abs=0.01)


def test_the_same_circuit_in_a_rotated_frame_is_accepted(tmp_path):
    """Il caso che conta per il secondo gioco: stesso circuito, assi girati.

    Nessun simulatore promette a un altro dove mettere il proprio nord.
    """
    e = _spline_of(tmp_path, _loop())
    assert te.fit(e, _moved(_loop(), deg=57.0, dx=900.0, dz=-2100.0)) is not None


def test_the_lap_ends_up_on_the_road_not_beside_it(tmp_path):
    """Non basta che il fit dica di sì: il nastro deve finire **sotto la
    macchina**. Controllo indipendente, in metri, come sui giri veri (dove la
    linea guidata risulta a 0.7-4.4 m dal centro pista)."""
    e = _spline_of(tmp_path, _loop())
    lap = _moved(_loop(), deg=57.0, dx=900.0, dz=-2100.0)
    at = te.fit(e, lap)
    road = te.placed(e, at)
    worst = max(min(math.hypot(road.x[i] - q.x, road.z[i] - q.z)
                    for i in range(len(road)))
                for q in lap[::8])
    assert worst < 2.0, f"la linea guidata dista fino a {worst:.1f} m dalla pista"


def test_the_widths_travel_with_the_fit(tmp_path):
    """Una pista posata a scala 0.99 con i bordi a grandezza naturale sarebbe
    più larga di sé stessa."""
    e = _spline_of(tmp_path, _loop(), side_l=4.0, side_r=6.0)
    at = te.fit(e, _moved(_loop(), dx=500.0))
    road = te.placed(e, at)
    assert road.width_m() == pytest.approx(10.0 * at.scale, abs=0.2)


# --- rifiutare -------------------------------------------------------------

def test_another_layout_of_the_same_circuit_is_refused(tmp_path):
    """Il caso Spa 1998 contro Spa moderna: la scala viene 1.000 e resta un
    altro tracciato. Ecco perché lo scarto va guardato **oltre** alla scala."""
    e = _spline_of(tmp_path, _loop(wobble=1.0))
    assert te.fit(e, _moved(_loop(wobble=-2.2))) is None


def test_a_shrunken_lap_matching_everything_is_refused(tmp_path):
    """Il caso Nürburgring: coordinate rotte. Lo scarto viene ottimo (8 m) su
    **qualunque** circuito, perché il fit è libero di rimpicciolirlo. Ecco
    perché la scala va guardata oltre allo scarto."""
    e = _spline_of(tmp_path, _loop())
    lap = _moved(_loop(), scale=0.02)
    small = te.fit(e, lap)
    assert small is None
    # e la prova che il rifiuto viene dalla scala e non dalla forma:
    raw = te._resample([p.x for p in lap], [p.z for p in lap], te._FIT_N)
    assert raw, "la forma c'è: è solo settanta volte più piccola"


def test_a_different_circuit_is_refused(tmp_path):
    e = _spline_of(tmp_path, _loop())
    other = [(x * 1.0, z * 2.6) for x, z in _loop()]      # stessa lunghezza, altro posto
    assert te.fit(e, [_P(x, z) for x, z in other]) is None


def test_a_lap_without_coordinates_is_refused(tmp_path):
    """Prima del fix delle coordinate AC1 alcuni giri arrivano con x e z a zero.
    Un giro senza posizione non può dire quale pista è."""
    e = _spline_of(tmp_path, _loop())
    assert te.fit(e, [_P(0.0, 0.0) for _ in range(64)]) is None


# --- trovare la pista senza sapere come si chiama ----------------------------

def test_the_circuit_is_found_by_shape_not_by_name(tmp_path, monkeypatch):
    """Mount Panorama si chiama `mount_panorama` in ACC e `rt_bathurst` nel mod
    che la porta su AC. Cercare per stringa fa comparire il disegno in un gioco
    e non nell'altro — cioè la cosa che questo modulo ha smesso di fare."""
    _spline_of(tmp_path, _loop())
    monkeypatch.setattr(te, "all_splines",
                        lambda: [("qualsiasi_nome", tmp_path / "ai" / "fast_lane.ai")])
    te._cache.clear()
    got = te.edges_for("un_nome_che_nessuno_ha_mai_visto",
                       _moved(_loop(), deg=31.0, dx=1200.0, dz=-800.0))
    assert got is not None


def test_a_circuit_of_the_wrong_length_is_never_even_tried(tmp_path):
    """Il prefiltro sulla lunghezza è ciò che rende la ricerca istantanea: 65
    piste installate diventano una manciata di candidati."""
    e = _spline_of(tmp_path, _loop())
    import math as _m
    L = sum(_m.dist((e.x[i - 1], e.z[i - 1]), (e.x[i], e.z[i]))
            for i in range(1, len(e)))
    assert L > 0
    letta = te.spline_length(tmp_path / "ai" / "fast_lane.ai")
    assert abs(letta - L) / L < 0.05, "la lunghezza letta dai soli punti dev'essere quella"


def test_the_right_circuit_beats_its_own_historic_version(tmp_path, monkeypatch):
    """Il cuore della faccenda, misurato sull'archivio: **nessuna soglia
    assoluta** separa un circuito dalla propria variante storica (il peggiore
    dei veri sta a 26.7 m, il migliore dei falsi a 22.3). A separarli è solo il
    fatto che la pista giusta prende un punteggio migliore — quindi si valutano
    TUTTI i candidati e vince il migliore, mai il primo che passa.
    """
    vera = _spline_of(tmp_path, _loop(wobble=1.0))
    storica = _spline_of(tmp_path, _loop(wobble=0.55), name="old.ai")
    assert vera and storica
    lap = _moved(_loop(wobble=1.0), deg=12.0, dx=300.0)
    # entrambe passerebbero il tetto da sole...
    assert te.fit(storica, lap) is not None, "la variante storica passa il tetto"
    # ...ma messe a confronto vince quella giusta.
    monkeypatch.setattr(te, "all_splines", lambda: [
        ("storica", tmp_path / "ai" / "old.ai"),
        ("vera", tmp_path / "ai" / "fast_lane.ai"),
    ])
    te._cache.clear()
    got = te.edges_for("qualunque", lap)
    assert got is not None and got.track == "vera"


def test_edges_for_hands_back_the_track_in_the_laps_coordinates(tmp_path,
                                                                monkeypatch):
    """La porta d'ingresso del modulo: chi chiama non deve sapere niente di fit,
    di specchi o di sistemi di riferimento — chiede l'asfalto e lo riceve dove
    stanno i suoi punti."""
    e = _spline_of(tmp_path, _loop())
    monkeypatch.setattr(te, "spline_path",
                        lambda track: tmp_path / "ai" / "fast_lane.ai")
    te._cache.clear()
    lap = _moved(_loop(), deg=120.0, dx=-4000.0, dz=750.0)
    road = te.edges_for("qualunque", lap)
    assert road is not None
    assert min(road.x) > -5000 and max(road.x) < -3000, "non è stata spostata"
