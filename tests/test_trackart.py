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
