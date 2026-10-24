"""File di mod rotti o malevoli: un kn5 che mente sulle misure, un assetto che
non e' fatto di numeri. Devono finire come file illeggibili, mai come un blocco
di 35 secondi, un MemoryError o un 500."""
import copy
import json
import struct
import time

import pytest
from fastapi.testclient import TestClient

from accoach import trackmesh as tm
from accoach.api import create_api

from test_setup_ac import SAMPLE_INI
from test_setup_api import CAR, SAMPLE, TRACK
from test_trackmesh import _kn5, _quad


def _s(t):
    b = t.encode("utf-8")
    return struct.pack("<i", len(b)) + b


def _kn5_con_figli(nchild):
    """Il PoC dell'audit, dai byte: una radice che dichiara ``nchild`` figli
    e il file finisce li'. Meno di cento byte."""
    out = bytearray(b"sc6969" + struct.pack("<i", 6) + struct.pack("<i", 0))
    out += struct.pack("<i", 0) + struct.pack("<i", 0)      # texture, materiali
    out += struct.pack("<i", 1) + _s("root") + struct.pack("<i", nchild) + b"\x01"
    out += b"\x00" * 64
    return bytes(out)


def _mesh_con_indici(tmp_path, indici, nv=3):
    """Un kn5 sano con un'unica mesh di superficie, indici scelti da noi."""
    nomi = [f"{n}ROAD" for n in range(12)]
    p = _kn5(tmp_path, [(n, [(0, 0, 0), (1, 0, 0), (1, 0, 1)]) for n in nomi])
    data = bytearray(p.read_bytes())
    # gli indici dell'ultima mesh stanno prima di: materiale(4)+layer(12)+16+1
    coda = 4 + 12 + 16 + 1
    fine = len(data) - coda
    inizio = fine - 3 * 2
    data[inizio:fine] = struct.pack("<3H", *indici)
    p.write_bytes(bytes(data))
    return p


def test_kn5_con_nchild_enorme_si_rifiuta_subito(tmp_path):
    p = tmp_path / "t.kn5"
    p.write_bytes(_kn5_con_figli(0x7FFFFFFF))
    assert p.stat().st_size < 200
    t0 = time.monotonic()
    assert not tm.is_physics_model(p)
    assert time.monotonic() - t0 < 1.0


def test_kn5_con_indice_fuori_misura_e_illeggibile_non_IndexError(tmp_path):
    p = _mesh_con_indici(tmp_path, (0, 1, 2))
    assert tm._walk(p, collect=True)["named"] == 12        # il fixture e' sano
    p = _mesh_con_indici(tmp_path, (0, 1, 7))
    with pytest.raises(ValueError):
        tm._walk(p, collect=True)


def test_kn5_con_indice_fuori_misura_non_rompe_la_strada(tmp_path, monkeypatch):
    p = _mesh_con_indici(tmp_path, (0, 1, 7))
    monkeypatch.setattr(tm, "physics_model", lambda track: p)
    monkeypatch.setattr(tm, "_cache", {})
    assert tm.surfaces("monza") is None


def test_kn5_con_conteggio_di_vertici_enorme_e_illeggibile(tmp_path):
    p = _kn5(tmp_path, [("1ROAD", _quad(0, 0, 1, 1))])
    data = bytearray(p.read_bytes())
    # il conteggio dei vertici e' il primo intero dopo i tre byte di flag
    k = data.index(b"\x01\x01\x00", 6 + 4 + 4 + 4 + 4) + 3
    assert struct.unpack_from("<i", data, k)[0] == 6
    data[k:k + 4] = struct.pack("<i", 0x7FFFFFFF)
    p.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        tm._walk(p, collect=True)
    assert not tm.is_physics_model(p)


def test_kn5_con_texture_enormi_e_illeggibile(tmp_path):
    out = bytearray(b"sc6969" + struct.pack("<i", 6) + struct.pack("<i", 0))
    out += struct.pack("<i", 0x7FFFFFFF)
    p = tmp_path / "t.kn5"
    p.write_bytes(bytes(out))
    assert not tm.is_physics_model(p)


def test_kn5_sano_si_legge_come_prima(tmp_path):
    nomi = [f"{n}ROAD" for n in range(tm._PHYS_MESHES)]
    p = _kn5(tmp_path, [(n, _quad(0, 0, 10, 10)) for n in nomi])
    assert tm.is_physics_model(p)
    got = tm._walk(p, collect=True)
    assert got["named"] == got["total"] == tm._PHYS_MESHES
    assert len(got["tris"]["road"]) == tm._PHYS_MESHES * 2 * 3 * 2


# --- assetti ----------------------------------------------------------------

def _client_acc(tmp_path, raw_text):
    root = tmp_path / "Setups"
    d = root / CAR / TRACK
    d.mkdir(parents=True)
    f = d / "rotto.json"
    f.write_text(raw_text, encoding="utf-8")
    return TestClient(create_api(tmp_path / "laps", setups_root=root)), str(f)


def _con(modifica):
    raw = copy.deepcopy(SAMPLE)
    modifica(raw)
    return json.dumps(raw)


def _nesting(n):
    return '{"basicSetup":' + "[" * n + "]" * n + "}"


CORPI = {
    "stringhe": _con(lambda r: r["basicSetup"]["tyres"].update(
        tyrePressure=["x", "y", "z", "w"])),
    "decimale": _con(lambda r: r["basicSetup"]["tyres"].update(
        tyrePressure=[57.5, 52, 51, 48])),
    "scalare_testo": _con(lambda r: r["basicSetup"]["strategy"].update(fuel="48")),
    "booleano": _con(lambda r: r["basicSetup"]["strategy"].update(fuel=True)),
    "oggetto": _con(lambda r: r["basicSetup"]["strategy"].update(fuel={"a": 1})),
    "infinito": json.dumps(SAMPLE).replace('"fuel": 48', '"fuel": 1e400'),
    "intero_enorme": json.dumps(SAMPLE).replace('"fuel": 48', '"fuel": ' + "9" * 400),
    "annidato_100000": _nesting(100_000),
}


@pytest.mark.parametrize("nome", list(CORPI))
@pytest.mark.parametrize("rotta", ["current", "preview"])
def test_assetto_acc_malformato_e_4xx_non_500(tmp_path, nome, rotta):
    c, path = _client_acc(tmp_path, CORPI[nome])
    if rotta == "current":
        r = c.get("/api/setup/current", params={"path": path})
    else:
        r = c.post("/api/setup/preview", json={"path": path, "changes": []})
    assert 400 <= r.status_code < 500, f"{nome}: {r.status_code} {r.text[:200]}"


def test_assetto_acc_sano_si_carica_ancora(tmp_path):
    c, path = _client_acc(tmp_path, json.dumps(SAMPLE))
    assert c.get("/api/setup/current", params={"path": path}).status_code == 200


def test_assetto_acc_load_solleva_SetupError(tmp_path):
    from accoach.setup import acc_format
    for nome in ("stringhe", "annidato_100000", "infinito"):
        f = tmp_path / f"{nome}.json"
        f.write_text(CORPI[nome], encoding="utf-8")
        with pytest.raises(acc_format.SetupError):
            acc_format.load(f)
        with pytest.raises(acc_format.SetupError):
            acc_format.loads(CORPI[nome])


def _client_ac(tmp_path, ini):
    root = tmp_path / "ac"
    d = root / "f1_1990_mclaren" / "monza"
    d.mkdir(parents=True)
    f = d / "race.ini"
    f.write_text(ini, encoding="utf-8")
    return TestClient(create_api(tmp_path / "laps", setups_root=[root])), str(f)


@pytest.mark.parametrize("valore", ["1e400", "-1e400", "nan", "boh"])
def test_assetto_ac_con_valore_impossibile_e_4xx_non_500(tmp_path, valore):
    ini = SAMPLE_INI.replace("[ARB_FRONT]\nVALUE=30", f"[ARB_FRONT]\nVALUE={valore}")
    assert valore in ini
    c, path = _client_ac(tmp_path, ini)
    r = c.get("/api/setup/current", params={"path": path})
    assert 400 <= r.status_code < 500, f"{valore}: {r.status_code} {r.text[:200]}"


def test_assetto_ac_load_solleva_AcSetupError():
    from accoach.setup import ac_format
    ini = SAMPLE_INI.replace("[ARB_FRONT]\nVALUE=30", "[ARB_FRONT]\nVALUE=1e400")
    with pytest.raises(ac_format.AcSetupError):
        ac_format.loads(ini)


def test_kn5_bloccato_non_si_ricorda_come_rotto(tmp_path, monkeypatch):
    nomi = [f"{n}ROAD" for n in range(tm._PHYS_MESHES)]
    p = _kn5(tmp_path, [(n, _quad(0, 0, 10, 10)) for n in nomi])
    monkeypatch.setattr(tm, "physics_model", lambda track: p)
    monkeypatch.setattr(tm, "_cache", {})
    vero = tm._walk
    def bloccato(path, collect):
        raise PermissionError("file in uso")
    monkeypatch.setattr(tm, "_walk", bloccato)
    assert tm.surfaces("monza") is None
    monkeypatch.setattr(tm, "_walk", vero)
    assert tm.surfaces("monza") is not None
