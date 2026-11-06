"""Lo sfondo dal gioco: chi lo posa, e con quali file.

Lo sfondo si posa solo su una pista di AC, mai su un circuito del bundle: i file
grafici sono quelli della cartella del gioco e vanno posati con la linea dell'IA
di quella stessa cartella.
"""
import math

from accoach import trackart as ta
from accoach import trackedges as te

from test_track_fit import _loop, _moved, _spline_of


def test_the_background_is_never_placed_with_a_bundled_circuit(tmp_path, monkeypatch):
    _spline_of(tmp_path, _loop())
    ai = tmp_path / "ai" / "fast_lane.ai"
    lap = _moved(_loop(), deg=20.0, dx=100.0)
    monkeypatch.setattr(te, "bundled_tracks", lambda: [("circuito", ai)])
    monkeypatch.setattr(te, "all_splines", lambda: [])
    te._cache.clear()
    assert te.ac_fit(lap) is None
    road, at = te.edges_and_fit("x", lap)
    assert road is not None and at is not None


def test_the_ac_track_that_fits_best_wins(tmp_path, monkeypatch):
    giusta = tmp_path / "giusta"
    spostata = tmp_path / "spostata"
    giusta.mkdir()
    spostata.mkdir()
    _spline_of(giusta, _loop())
    shifted = [(x, z + 30.0 * math.sin(3 * math.atan2(z, x))) for x, z in _loop()]
    _spline_of(spostata, shifted)
    monkeypatch.setattr(te, "bundled_tracks", lambda: [])
    monkeypatch.setattr(te, "all_splines", lambda: [
        ("spostata", spostata / "ai" / "fast_lane.ai"),
        ("giusta", giusta / "ai" / "fast_lane.ai"),
    ])
    te._cache.clear()
    got = te.ac_fit(_moved(_loop(), deg=12.0, dx=300.0))
    assert got is not None
    path, at = got
    assert path == giusta / "ai" / "fast_lane.ai"
    assert isinstance(at, te.Fit)


def _spline_file(folder):
    p = folder / "ai" / "fast_lane.ai"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def test_models_ini_is_read_with_its_layout(tmp_path):
    track = tmp_path / "monza"
    spline = _spline_file(track / "gp")
    (track / "a.kn5").write_bytes(b"x")
    (track / "b.kn5").write_bytes(b"x")
    (track / "models_gp.ini").write_text(
        "[MODEL_0]\r\nFILE=a.kn5\r\nPOSITION=1,2,3\r\nROTATION=90,0,0\r\n",
        encoding="utf-8")
    (track / "models.ini").write_text("[MODEL_0]\r\nFILE=b.kn5\r\n", encoding="utf-8")
    assert ta.art_files(spline) == [
        ta.ArtFile(track / "a.kn5", (1.0, 2.0, 3.0), (90.0, 0.0, 0.0))]


def test_without_an_ini_every_kn5_of_the_track_is_used(tmp_path):
    track = tmp_path / "pista"
    spline = _spline_file(track / "gp")
    (track / "b.kn5").write_bytes(b"x")
    (track / "a.kn5").write_bytes(b"x")
    zero = (0.0, 0.0, 0.0)
    assert ta.art_files(spline) == [ta.ArtFile(track / "a.kn5", zero, zero),
                                    ta.ArtFile(track / "b.kn5", zero, zero)]
    direct = tmp_path / "solo"
    spline2 = _spline_file(direct)
    (direct / "c.kn5").write_bytes(b"x")
    assert [f.path for f in ta.art_files(spline2)] == [direct / "c.kn5"]


def test_missing_keys_are_zero_and_missing_files_are_skipped(tmp_path):
    track = tmp_path / "pista"
    spline = _spline_file(track)
    (track / "a.kn5").write_bytes(b"x")
    (track / "models.ini").write_text(
        "[MODEL_0]\nFILE=a.kn5\n[MODEL_1]\nFILE=manca.kn5\n[MODEL_2]\nPOSITION=1,1,1\n",
        encoding="utf-8")
    zero = (0.0, 0.0, 0.0)
    assert ta.art_files(spline) == [ta.ArtFile(track / "a.kn5", zero, zero)]


def test_a_file_named_outside_the_track_folder_is_ignored(tmp_path):
    track = tmp_path / "pista"
    spline = _spline_file(track)
    (tmp_path / "x.kn5").write_bytes(b"x")
    (track / "ok.kn5").write_bytes(b"x")
    (track / "models.ini").write_text(
        "[MODEL_0]\nFILE=..\\x.kn5\n[MODEL_1]\nFILE=ok.kn5\n", encoding="utf-8")
    assert [f.path for f in ta.art_files(spline)] == [track / "ok.kn5"]


# --- un tassello -------------------------------------------------------------
# Modelli sintetici scritti come kn5 (il costruttore di test_kn5visual) e
# texture PNG fatte in memoria: i file veri del gioco non entrano nei test.

def _png(pixels, mode="RGB"):
    """Una texture PNG; `pixels` e' una lista di righe di colori."""
    import io
    from PIL import Image
    h, w = len(pixels), len(pixels[0])
    im = Image.new(mode, (w, h))
    im.putdata([c for row in pixels for c in row])
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _quad(name, x0, z0, x1, z1, y=0.0, mat=0):
    """Un rettangolo orizzontale, con la texture stesa una volta su tutto."""
    from test_kn5visual import mesh
    a, b, c, d = (x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)
    ua, ub, uc, ud = (0, 1), (1, 1), (1, 0), (0, 0)
    return mesh(name, [a, b, c, a, c, d], mat=mat, uvs=[ua, ub, uc, ua, uc, ud])


def _model(tmp_path, nodes, textures=(), materials=(), name="art.kn5"):
    from accoach import kn5visual as kv
    from test_kn5visual import _kn5, dummy
    return kv.read(_kn5(tmp_path, dummy("root", list(nodes)), textures=textures,
                        materials=materials, name=name))


def _solid(name, rgb):
    """Una texture di un colore e il suo materiale opaco."""
    return (name + ".png", _png([[rgb] * 4] * 4)), (name, "ksPerPixel", 0, 0,
                                                       [("txDiffuse", name + ".png")])


def _rgb(img):
    import numpy as np
    return np.asarray(img.convert("RGB"), dtype=np.int16)


SIDE0 = ta.TILE_PX * ta.LEVELS_M[0]


def test_the_tile_grid_is_the_planned_one():
    assert ta.LEVELS_M == (0.1, 0.2, 0.4, 0.8, 1.6, 3.2)
    assert ta.TILE_PX == 512 and ta.ALPHA_CUT == 100


def test_a_quad_fills_the_tile_with_its_texture(tmp_path):
    tex, mat = _solid("red", (200, 30, 20))
    m = _model(tmp_path, [_quad("ground", -1, -1, SIDE0 + 1, SIDE0 + 1)], [tex], [mat])
    img = ta.render_tile(ta.Scene([m], None), 0, 0, 0)
    assert img is not None and img.size == (512, 512)
    px = _rgb(img)
    assert (abs(px - (200, 30, 20)) <= 2).all()


def test_the_tile_corner_is_x_min_z_max(tmp_path):
    tex, mat = _solid("blue", (10, 20, 230))
    m = _model(tmp_path, [_quad("dot", 0, SIDE0 - 1, 1, SIDE0)], [tex], [mat])
    px = _rgb(ta.render_tile(ta.Scene([m], None), 0, 0, 0))
    # un metro a 0,1 m per pixel: i primi 10 x 10 pixel in alto a sinistra
    assert (abs(px[:10, :10] - (10, 20, 230)) <= 2).all()
    assert (abs(px[10:, :] - (10, 20, 230)) > 2).any(axis=2).all()
    assert (abs(px[:, 10:] - (10, 20, 230)) > 2).any(axis=2).all()


def test_the_highest_surface_wins(tmp_path):
    (t1, m1), (t2, m2) = _solid("low", (200, 0, 0)), _solid("high", (0, 200, 0))
    m = _model(tmp_path, [
        _quad("high", 0, 0, SIDE0, SIDE0, y=1.0, mat=1),
        _quad("low", 0, 0, SIDE0, SIDE0, y=0.0, mat=0),
    ], [t1, t2], [m1, m2])
    px = _rgb(ta.render_tile(ta.Scene([m], None), 0, 0, 0))
    assert (abs(px - (0, 200, 0)) <= 2).all()


def test_something_above_the_road_is_not_drawn(tmp_path):
    (t1, m1), (t2, m2) = _solid("asph", (90, 90, 90)), _solid("roof", (220, 180, 0))
    art = _model(tmp_path, [
        _quad("asphalt", 0, 0, SIDE0, SIDE0, y=0.0, mat=0),
        _quad("bridge", 0, 0, SIDE0, SIDE0, y=6.0, mat=1),
    ], [t1, t2], [m1, m2])
    # la strada del modello di collisione copre solo la meta' sinistra
    road = _model(tmp_path, [_quad("1ROAD_x", 0, 0, SIDE0 / 2, SIDE0)], name="col.kn5")
    px = _rgb(ta.render_tile(ta.Scene([art], road), 0, 0, 0))
    assert (abs(px[:, :250] - (90, 90, 90)) <= 2).all()      # il ponte sopra la strada
    assert (abs(px[:, 262:] - (220, 180, 0)) <= 2).all()     # il tetto senza strada sotto


def test_a_surface_just_above_the_road_is_drawn(tmp_path):
    """Sotto OVERHEAD_M e' la strada stessa (o un cordolo), non un ponte."""
    (t1, m1), (t2, m2) = _solid("asph", (90, 90, 90)), _solid("line", (240, 240, 240))
    art = _model(tmp_path, [
        _quad("asphalt", 0, 0, SIDE0, SIDE0, y=0.0, mat=0),
        _quad("paint", 0, 0, SIDE0, SIDE0, y=ta.OVERHEAD_M - 0.5, mat=1),
    ], [t1, t2], [m1, m2])
    road = _model(tmp_path, [_quad("1ROAD_x", 0, 0, SIDE0, SIDE0)], name="col.kn5")
    px = _rgb(ta.render_tile(ta.Scene([art], road), 0, 0, 0))
    assert (abs(px - (240, 240, 240)) <= 2).all()


def test_transparent_texels_are_dropped(tmp_path):
    clear = ("clear.png", _png([[(255, 255, 255, 0)] * 4] * 4, "RGBA"))
    red, mred = _solid("red", (200, 0, 0))
    for flags in ((0, 1), (1, 0)):          # alpha test, oppure blend 1
        sub = tmp_path / f"{flags[0]}{flags[1]}"
        sub.mkdir()
        m = _model(sub, [
            _quad("leaves", 0, 0, SIDE0, SIDE0, y=3.0, mat=1),
            _quad("ground", 0, 0, SIDE0, SIDE0, y=0.0, mat=0),
        ], [red, clear], [mred, ("tree", "ksPerPixelAT", flags[0], flags[1],
                                  [("txDiffuse", "clear.png")])])
        px = _rgb(ta.render_tile(ta.Scene([m], None), 0, 0, 0))
        assert (abs(px - (200, 0, 0)) <= 2).all()


def test_bilinear_blends_two_texels(tmp_path):
    tex = ("bw.png", _png([[(0, 0, 0), (255, 255, 255)]]))
    m = _model(tmp_path, [_quad("strip", 0, 0, 2, SIDE0)], [tex],
               [("bw", "ksPerPixel", 0, 0, [("txDiffuse", "bw.png")])])
    px = _rgb(ta.render_tile(ta.Scene([m], None), 0, 0, 0))
    # 2 m a 0,1 m per pixel: il centro della striscia e' fra le colonne 9 e 10
    for col in (9, 10):
        assert 100 <= px[256, col, 0] <= 155
    assert px[256, 3, 0] < px[256, 9, 0] < px[256, 10, 0] < px[256, 16, 0]


def test_tiny_triangles_are_splatted_with_the_same_colour(tmp_path):
    from test_kn5visual import mesh
    tex, mat = _solid("green", (40, 160, 90))
    verts, uvs = [], []
    step = 0.5
    for i in range(200):
        for k in range(200):
            x, z = i * step, k * step
            a, b, c, d = (x, 0, z), (x + step, 0, z), (x + step, 0, z + step), (x, 0, z + step)
            verts += [a, b, c, a, c, d]
            uvs += [(0, 0), (1, 0), (1, 1), (0, 0), (1, 1), (0, 1)]
    # una mesh non supera 65535 vertici: la griglia si divide in strisce
    nodes = [mesh(f"g{j}", verts[j:j + 60000], uvs=uvs[j:j + 60000])
             for j in range(0, len(verts), 60000)]
    m = _model(tmp_path, nodes, [tex], [mat])
    img = ta.render_tile(ta.Scene([m], None), 5, 0, 0)
    px = _rgb(img)
    side_px = int(200 * step / ta.LEVELS_M[5])               # 31 pixel
    covered = px[512 - side_px:, :side_px]
    assert (abs(covered - (40, 160, 90)) <= 3).all()


def test_a_mesh_the_game_does_not_render_is_not_drawn(tmp_path):
    from test_kn5visual import mesh
    tex, mat = _solid("asph", (90, 90, 90))
    nm, mnm = ("nm.png", _png([[(128, 128, 255)] * 4] * 4)), ("physics", "ksPerPixel", 0, 0,
                                                               [("txDiffuse", "nm.png")])
    hidden = _quad("1ROAD_x", 0, 0, SIDE0, SIDE0, y=0.01, mat=1)
    hidden = mesh(*hidden[1:6], renderable=False)
    m = _model(tmp_path, [hidden, _quad("asphalt", 0, 0, SIDE0, SIDE0)], [tex, nm], [mat, mnm])
    px = _rgb(ta.render_tile(ta.Scene([m], None), 0, 0, 0))
    assert (abs(px - (90, 90, 90)) <= 2).all()


def test_an_unreadable_texture_draws_grey(tmp_path):
    m = _model(tmp_path, [_quad("ground", 0, 0, SIDE0, SIDE0)],
               [("bc7.dds", b"DDS not really an image")],
               [("bc7", "ksPerPixel", 0, 0, [("txDiffuse", "bc7.dds")])])
    px = _rgb(ta.render_tile(ta.Scene([m], None), 0, 0, 0))
    assert (px == 128).all()


def test_an_empty_tile_is_none(tmp_path):
    tex, mat = _solid("red", (200, 0, 0))
    m = _model(tmp_path, [_quad("ground", 0, 0, 10, 10)], [tex], [mat])
    scene = ta.Scene([m], None)
    assert ta.render_tile(scene, 0, 0, 0) is not None
    assert ta.render_tile(scene, 0, 5, 0) is None
    assert ta.render_tile(scene, 0, -1, -1) is None
    assert ta.render_tile(ta.Scene([], None), 3, 0, 0) is None
