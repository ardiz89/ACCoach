"""La strada presa dal modello di collisione di Assetto Corsa.

Perché è servito: `trackedges` ricava i bordi allargando la **linea dell'IA**,
e le distanze laterali sono misurate perpendicolarmente a quella linea. Dove
l'IA taglia una variante il piede della perpendicolare non cade sul punto giusto
del bordo, e quello che ne esce è il corridoio attorno alla traiettoria, non la
strada: la Variante del Rettifilo si disegnava come una esse morbida invece che
come il flick secco che è.

Il modello di collisione invece è la strada, poligono per poligono, coi tipi di
superficie separati — e nelle coordinate del gioco, cioè le stesse dei giri.
Misurato: la linea guidata sta a **0.34 m** dal vertice d'asfalto più vicino
(p95 1.26 m), contro i 7-14 m del dato satellitare.

Il file di prova è costruito qui, quindi questi test girano anche dove AC non c'è.
"""
import math
import struct

import pytest

from accoach import trackmesh as tm
from accoach.trackedges import Fit


def _kn5(tmp_path, meshes, name="phys.kn5", version=6):
    """Un kn5 minimo: niente texture, niente materiali, mesh in fila.

    ``meshes`` è [(nome, [(x, y, z), ...])] e i vertici vengono presi a
    triangoli nell'ordine dato.
    """
    def s(t):
        b = t.encode("utf-8")
        return struct.pack("<i", len(b)) + b

    out = bytearray(b"sc6969" + struct.pack("<i", version))
    if version > 5:
        out += struct.pack("<i", 0)
    out += struct.pack("<i", 0)                 # texture
    out += struct.pack("<i", 0)                 # materiali
    # radice: un dummy con tutti i figli
    out += struct.pack("<i", 1) + s("root") + struct.pack("<i", len(meshes)) + b"\x01"
    out += b"\x00" * 64
    for nm, verts in meshes:
        out += struct.pack("<i", 2) + s(nm) + struct.pack("<i", 0) + b"\x01"
        out += b"\x01\x01\x00"                  # castShadows, visible, transparent
        out += struct.pack("<i", len(verts))
        for (x, y, z) in verts:
            out += struct.pack("<3f", x, y, z) + b"\x00" * (tm._VERTEX - 12)
        out += struct.pack("<i", len(verts))
        out += struct.pack(f"<{len(verts)}H", *range(len(verts)))
        out += struct.pack("<i", 0)             # materiale
        out += b"\x00" * 12                     # layer, lodIn, lodOut
        out += b"\x00" * 16 + b"\x01"           # bounding sphere + renderable
    p = tmp_path / name
    p.write_bytes(bytes(out))
    return p


def _quad(x0, z0, x1, z1):
    """Due triangoli che coprono un rettangolo, come vertici (x, y, z)."""
    a, b = (x0, 0.0, z0), (x1, 0.0, z0)
    c, d = (x1, 0.0, z1), (x0, 0.0, z1)
    return [a, b, c, a, c, d]


# --- riconoscere il file giusto ---------------------------------------------

def test_the_physics_model_is_recognised_not_guessed():
    """I due file stanno nella stessa cartella e si somigliano. A distinguerli
    è quanti nomi seguono la convenzione delle superfici: misurato, il modello
    fisico di Monza sta a 328/329 e quello visivo a 0/1470 — non c'è un caso di
    mezzo, quindi la soglia serve solo a dire «questo no»."""
    assert tm._class_of("1MONZA-ASPH_kerb") == "road"
    assert tm._class_of("07CURB004") == "kerb"
    assert tm._class_of("12KERB_a") == "kerb"
    assert tm._class_of("Object112") is None
    assert tm._class_of("bush767_KSLAYER3") is None
    assert tm._class_of("wll-gr004") is None


def test_a_visual_model_is_refused(tmp_path):
    p = _kn5(tmp_path, [(f"Object{i}", _quad(0, i, 10, i + 1)) for i in range(12)])
    assert tm.is_physics_model(p) is False


def test_a_physics_model_is_accepted(tmp_path):
    p = _kn5(tmp_path, [(f"1ASPH_{i}", _quad(0, i, 10, i + 1)) for i in range(12)])
    assert tm.is_physics_model(p) is True


@pytest.mark.parametrize("blob", [b"", b"nope", b"sc6969" + b"\x00" * 4])
def test_something_that_is_not_a_kn5_reads_as_nothing(tmp_path, blob):
    p = tmp_path / "x.kn5"
    p.write_bytes(blob)
    assert tm.is_physics_model(p) is False


# --- dai triangoli al contorno ----------------------------------------------

def _straight(tmp_path, length=120.0, half=5.0):
    """Una strada dritta lunga ``length``, larga 2*``half``, in pezzi da 10 m —
    come nel gioco, dove la pista è tagliata in decine di mesh separate."""
    meshes = []
    for k in range(int(length // 10)):
        meshes.append((f"1ASPH_{k}", _quad(-half, k * 10.0, half, k * 10.0 + 10.0)))
    return _kn5(tmp_path, meshes)


def test_the_outline_of_a_straight_road_is_the_road(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "physics_model", lambda track: _straight(tmp_path))
    tm._cache.clear()
    xz = [(0.0, z) for z in range(10, 110, 5)]
    got = tm.road_shapes("qualunque", xz, None, pad=6.0)
    assert got and got["road"], got
    ring = max(got["road"], key=len)
    xs = [p[0] for p in ring]
    # Larga dieci metri, e il contorno non deve sfondare i bordi.
    assert -6.0 < min(xs) < -4.0 and 4.0 < max(xs) < 6.0, (min(xs), max(xs))


def test_pieces_side_by_side_give_one_outline_not_a_seam_each(tmp_path, monkeypatch):
    """Il dubbio che aveva portato, sbagliando, a rasterizzare.

    Se due mesh affiancate avessero vertici diversi sul confine, ogni giunzione
    diventerebbe un finto bordo in mezzo alla strada. Misurato sul modello vero
    attorno alla Variante del Rettifilo: 18.473 triangoli, 28.168 lati, **917 di
    bordo — il 3%**, e arrotondare i vertici a 1 o 5 cm non cambia un lato. Le
    mesh combaciano. Qui la stessa cosa in piccolo, perche' se un giorno
    smettessero di combaciare si vedrebbe da qui e non da uno screenshot.
    """
    monkeypatch.setattr(tm, "physics_model", lambda track: _straight(tmp_path))
    tm._cache.clear()
    got = tm.road_shapes("qualunque", [(0.0, z) for z in range(10, 110, 5)], None, pad=6.0)
    assert len(got["road"]) == 1, f"{len(got['road'])} anelli invece di uno"


def test_the_kerbs_come_back_separately(tmp_path, monkeypatch):
    """Sono la ragione principale per leggere questo file: è ciò che il pilota
    guarda, e allargare una traiettoria non ne inventa uno."""
    meshes = [("1ASPH_a", _quad(-5, 0, 5, 100)), ("2CURB_a", _quad(5, 20, 6.5, 60))]
    monkeypatch.setattr(tm, "physics_model", lambda t: _kn5(tmp_path, meshes))
    tm._cache.clear()
    got = tm.road_shapes("qualunque", [(0.0, z) for z in range(5, 95, 5)], None, pad=8.0)
    assert got and "kerb" in got and got["kerb"], got
    kx = [p[0] for ring in got["kerb"] for p in ring]
    assert min(kx) > 4.0, "il cordolo è finito dentro la strada"


def test_the_payload_is_an_outline_not_a_mesh(tmp_path, monkeypatch):
    """Attorno a una sola curva vera ci sono ventimila triangoli — un megabyte e
    mezzo. Il contorno di tutta Monza sta in ottantasei chilobyte."""
    import json
    monkeypatch.setattr(tm, "physics_model", lambda track: _straight(tmp_path, 400.0))
    tm._cache.clear()
    got = tm.road_shapes("qualunque", [(0.0, z) for z in range(10, 390, 5)], None, pad=6.0)
    assert len(json.dumps(got)) < 8_000


def test_a_window_the_size_of_half_a_circuit_is_refused(tmp_path, monkeypatch):
    """Una finestra così non è una curva: è un ritaglio andato storto, e
    rasterizzarla costerebbe secondi per un disegno che non serve."""
    monkeypatch.setattr(tm, "physics_model", lambda track: _straight(tmp_path))
    tm._cache.clear()
    assert tm.road_shapes("qualunque", [(0.0, 0.0), (0.0, 4000.0)], None) is None


def test_without_the_game_there_are_no_surfaces(monkeypatch):
    monkeypatch.setattr(tm, "physics_model", lambda track: None)
    tm._cache.clear()
    assert tm.surfaces("monza") is None
    assert tm.road_shapes("monza", [(0.0, 0.0), (1.0, 1.0)], None) is None


def test_the_surfaces_are_placed_with_the_same_fit_as_everything_else(tmp_path,
                                                                     monkeypatch):
    """Chiunque abbia altra geometria della stessa pista deve posarla nello
    stesso modo, o le due finiranno l'una accanto all'altra."""
    monkeypatch.setattr(tm, "physics_model", lambda track: _straight(tmp_path))
    tm._cache.clear()
    at = Fit(scale=1.0, cos=math.cos(0.7), sin=math.sin(0.7),
             dx=500.0, dz=-300.0, p95_m=1.0, mirror=False)
    xz = [at.apply(0.0, float(z)) for z in range(10, 110, 5)]
    got = tm.road_shapes("qualunque", xz, at, pad=6.0)
    assert got and got["road"]
    # Il contorno deve stare attorno al tratto guidato, non all'origine.
    ring = max(got["road"], key=len)
    cx = sum(p[0] for p in ring) / len(ring)
    lx = sum(p[0] for p in xz) / len(xz)
    assert abs(cx - lx) < 15.0, f"la strada è a {abs(cx - lx):.0f} m dal giro"


def test_a_straight_edge_comes_out_straight(tmp_path, monkeypatch):
    """Il difetto che si vedeva: il bordo usciva a gradini.

    Veniva dalla rasterizzazione a mezzo metro — a questo ingrandimento sono
    quattro pixel per scalino. Ora il bordo e' quello vero, quindi il lato di
    una strada dritta dev'essere fatto di pochissimi punti in fila.
    """
    monkeypatch.setattr(tm, "physics_model", lambda track: _straight(tmp_path, 200.0))
    tm._cache.clear()
    got = tm.road_shapes("qualunque", [(0.0, z) for z in range(10, 190, 5)], None, pad=6.0)
    ring = max(got["road"], key=len)
    # Un rettangolo lungo: quattro angoli, e nessuna scaletta in mezzo.
    assert len(ring) <= 8, f"{len(ring)} punti per un rettangolo"
    for x, _z in ring:
        assert abs(abs(x) - 5.0) < 0.2, f"bordo a x={x:.2f} invece che a +-5"


# --- cosa c'e' di fianco alla pista ------------------------------------------

def test_the_run_off_comes_back_with_its_own_name(tmp_path, monkeypatch):
    """La domanda che il nastro da solo non chiudeva: dove finisce la pista e
    comincia il resto.

    Nei dati del gioco è una distinzione esplicita, e la si vede proprio dove
    faceva male: l'asfalto di fuga di La Source è `ASPH` come la pista, ma
    l'erba e la ghiaia che lo circondano no.
    """
    meshes = [
        ("1ASPH_a", _quad(-5, 0, 5, 100)),
        ("2CURB_a", _quad(5, 20, 6.5, 60)),
        ("3GRASS_a", _quad(6.5, 0, 20, 100)),
        ("4SAND_a", _quad(-20, 0, -5, 100)),
        ("5CONCRETE_a", _quad(-30, 0, -20, 100)),
    ]
    monkeypatch.setattr(tm, "physics_model", lambda t: _kn5(tmp_path, meshes))
    tm._cache.clear()
    got = tm.road_shapes("qualunque", [(0.0, z) for z in range(5, 95, 5)],
                         None, pad=30.0)
    assert set(got) == {"road", "kerb", "grass", "gravel", "concrete"}, sorted(got)
    side = lambda k: sum(p[0] for r in got[k] for p in r) / sum(len(r) for r in got[k])
    assert side("grass") > 5, "l'erba è finita dalla parte sbagliata"
    assert side("gravel") < -5 and side("concrete") < side("gravel")


def test_the_walls_and_the_verdicts_stay_out():
    """I muri sono geometria verticale — in pianta sono un filo — e `OUT` /
    `OFFTRACK` non sono materiali ma verdetti, sovrapposti a tutto il resto."""
    for name in ("12WALL003", "01OUT004", "03OFFTRACK", "07EDGE"):
        assert tm._class_of(name) is None, name


def test_every_class_has_a_place_in_the_drawing_order():
    """Una classe estratta e mai disegnata è lavoro pagato e buttato; una
    disegnata e mai estratta è una riga di codice che non fa niente."""
    assert set(tm.DRAW_ORDER) == set(tm._CLASSES)
    assert tm.DRAW_ORDER[-1] == "kerb", "i cordoli stanno sopra tutto"
    assert tm.DRAW_ORDER.index("road") > tm.DRAW_ORDER.index("grass")


def test_the_pit_lane_is_ground_and_gets_its_own_colour():
    """`PITS` / `PITLANE` / `PITSPA` finivano scartati, ma sono terreno vero —
    Monza 599 triangoli per 6280 m² in pianta, la stessa densità dell'asfalto.
    Classe propria e non `road` perché la corsia box **non è pista**: dipinta
    uguale farebbe sembrare il tracciato largo il doppio dove si stacca."""
    assert tm._class_of("01PITLANE") == "pitlane"
    assert tm._class_of("12PITS003") == "pitlane"
    assert "pitlane" in tm.DRAW_ORDER
    assert tm.DRAW_ORDER.index("pitlane") < tm.DRAW_ORDER.index("road")


def test_rumble_strips_are_kerbs_under_another_name():
    """Al Red Bull Ring i cordoli si chiamano così, e venivano buttati."""
    assert tm._class_of("03RUMBLE") == "kerb"


def test_the_drawing_order_is_the_same_on_both_sides():
    """`DRAW_ORDER` è ricopiato a mano in `web/app.js` (`SURFACE_PAINT`): due
    copie della stessa decisione in due linguaggi. Finché è così, chi cambia
    solo quella Python crede di aver cambiato il disegno e non ha cambiato
    niente."""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
          / "app.js").read_text(encoding="utf-8")
    block = js[js.index("const SURFACE_PAINT = ["):]
    block = block[:block.index("];")]
    painted = re.findall(r'\["(\w+)"', block)
    assert painted == list(tm.DRAW_ORDER), \
        f"il disegno usa {painted}, il modello {list(tm.DRAW_ORDER)}"
