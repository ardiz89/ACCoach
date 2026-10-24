"""Nomi che Windows non sa scrivere, e percorsi che escono dalle cartelle (Task 3)."""
import json
from pathlib import Path

import pytest

from accoach import trackedges
from accoach.setup import ac_steps, store

from test_setup_api import SAMPLE, _apply_con_nome, _client, _file_sotto


@pytest.mark.parametrize("nome", [
    "CON", "con.backup", "LPT9", "a*b", 'a"b', "a|b", "a?", "fine.", "fine ",
    "..", "a\x01b", "", ".", "a<b", "a>b", "NUL", "com1.txt", "Aux",
])
def test_nomi_rifiutati(nome):
    assert not store.valid_name(nome)


@pytest.mark.parametrize("nome", [
    "Monza qualifica è", "HONE_3", "gara-2 (bagnato)", "v1.2", "CONSOLE", "COM10",
])
def test_nomi_veri_passano(nome):
    assert store.valid_name(nome)


@pytest.mark.parametrize("nome", ["CON", "a*b", 'a"b', "a|b", "a?", "fine.", "a\x01b"])
def test_apply_con_nome_non_scrivibile_e_400_e_non_scrive(tmp_path, nome):
    c, path = _client(tmp_path)
    prima = _file_sotto(tmp_path)
    r = _apply_con_nome(c, path, nome)
    assert r.status_code == 400, f"{nome!r}: {r.status_code} {r.text}"
    assert _file_sotto(tmp_path) == prima


def test_save_dice_not_a_plain_setup_name(tmp_path):
    with pytest.raises(ValueError, match="not a plain setup name"):
        store.save(object(), tmp_path, "CON")


def test_apply_dentro_accoach_backup_e_403(tmp_path):
    c, path = _client(tmp_path)
    bdir = Path(path).parent / store._BACKUP_DIR
    bdir.mkdir()
    bak = bdir / "base.20260101T000000.json"
    bak.write_text(json.dumps(SAMPLE), encoding="utf-8")
    prima = _file_sotto(tmp_path)
    corpo = {"path": str(bak), "as_name": "x", "confirm": True,
             "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    assert c.post("/api/setup/apply", json=corpo).status_code == 403
    assert c.get("/api/setup/current", params={"path": str(bak)}).status_code == 403
    assert c.post("/api/setup/preview", json={
        "path": str(bak), "changes": []}).status_code == 403
    assert c.post("/api/setup/seed", json={
        "source": str(bak), "track": "Monza"}).status_code == 403
    assert _file_sotto(tmp_path) == prima


def test_undo_sul_setup_resta_possibile(tmp_path):
    c, path = _client(tmp_path)
    corpo = {"path": path, "as_name": "run1", "confirm": True,
             "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    newp = c.post("/api/setup/apply", json=corpo).json()["path"]
    c.post("/api/setup/apply", json={**corpo, "path": newp, "overwrite": True})
    assert c.post("/api/setup/undo", json={"path": newp}).status_code == 200
    # ma non sul file di backup stesso
    bak = next((Path(newp).parent / store._BACKUP_DIR).glob("run1.*"))
    assert c.post("/api/setup/undo", json={"path": str(bak)}).status_code == 403


def test_setup_illeggibile_non_dice_la_cartella(tmp_path):
    c, path = _client(tmp_path)
    Path(path).write_text("{ non e' json", encoding="utf-8")
    r = c.get("/api/setup/current", params={"path": path})
    assert r.status_code == 404
    assert str(tmp_path) not in r.text
    assert "base.json" in r.text
    assert "Expecting" not in r.text and "line 1" not in r.text


def test_spline_path_e_car_folder_rifiutano_le_risalite(tmp_path, monkeypatch):
    tracce = tmp_path / "tracks"
    (tracce / "monza" / "ai").mkdir(parents=True)
    (tracce / "monza" / "ai" / "fast_lane.ai").write_bytes(b"x")
    # un'altra cartella sorella con una spline: raggiungibile solo risalendo
    (tmp_path / "ai").mkdir()
    (tmp_path / "ai" / "fast_lane.ai").write_bytes(b"x")
    monkeypatch.setattr(trackedges, "tracks_dir", lambda: tracce)
    assert trackedges.spline_path("monza") is not None
    for nome in ("..", ".", "../tracks", "..\tracks", "a/b", "C:x"):
        assert trackedges.spline_path(nome) is None, nome

    auto = tmp_path / "cars"
    (auto / "ks_x").mkdir(parents=True)
    assert ac_steps._car_folder(auto, "ks_x") == auto / "ks_x"
    for nome in ("..", ".", "../cars", "..\cars", "a/b", "C:x"):
        assert ac_steps._car_folder(auto, nome) is None, nome


@pytest.mark.parametrize("nome", ["a*b", "CON", "a/b", "fine.", "a\\b"])
def test_seed_con_as_name_non_scrivibile_e_400_e_non_scrive(tmp_path, nome):
    c, path = _client(tmp_path)
    prima = _file_sotto(tmp_path)
    r = c.post("/api/setup/seed", json={"source": path, "track": "monza",
                                        "as_name": nome})
    assert r.status_code == 400, f"{nome!r}: {r.status_code} {r.text}"
    assert _file_sotto(tmp_path) == prima


# Il 24/10, in prova sul PC: con la pagina in italiano un nome rifiutato
# rispondeva «not a plain setup name: 'CON'», e la pagina lo mostra così com'è.
@pytest.mark.parametrize("rotta", ["apply", "seed"])
def test_nome_rifiutato_si_spiega_nella_lingua_della_pagina(tmp_path, rotta):
    c, path = _client(tmp_path)
    if rotta == "apply":
        corpo = {"path": path, "as_name": "CON", "confirm": True,
                 "changes": [{"param": "rearWing", "delta_clicks": -1}]}
    else:
        corpo = {"source": path, "track": "monza", "as_name": "CON"}
    it = c.post(f"/api/setup/{rotta}?lang=it", json=corpo)
    en = c.post(f"/api/setup/{rotta}?lang=en", json=corpo)
    assert it.status_code == en.status_code == 400
    assert it.json()["detail"] == (
        "«CON» non si può usare come nome di un assetto. "
        "Togli \ / : * ? \" < > | e il punto finale, "
        "ed evita nomi riservati di Windows come CON o NUL.")
    assert en.json()["detail"] == (
        "“CON” can't be used as a setup name. "
        "Remove \ / : * ? \" < > | and any trailing dot, "
        "and avoid Windows reserved names such as CON or NUL.")
