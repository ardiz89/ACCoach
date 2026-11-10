"""Il lettore dei fatti dalle fonti (trackfacts)."""
import pytest
import json

from accoach import trackfacts


def _src(url="https://example.org/a"):
    return [{"url": url, "start_s": 1.0, "quote": "q"}]


def _v3(**over):
    d = {
        "track": "imola",
        "version": 3,
        "facts": [{"corner": "Tosa", "type": "gear", "value": "2", "n": 3,
                   "sources": _src(), "car_class": "gt3"}],
        "single": [
            {"corner": "Tosa", "type": "brake", "state": "singolo", "value": "100",
             "n": 1, "sources": _src(), "car_class": "gt3"},
            {"corner": "Tosa", "type": "mistake", "state": "descrittivo",
             "value": "frena tardi", "n": 1, "sources": _src()},
            {"corner": "Tosa", "type": "line", "state": "singolo",
             "value": "larga", "n": 1, "sources": _src()},
        ],
        "disputed": [{"corner": "Tosa", "type": "gear", "why": "respinto",
                      "values": [{"value": "3", "n": 1, "sources": _src()}]}],
    }
    d.update(over)
    return d


def _write(tmp_path, name, data):
    p = tmp_path / f"{name}.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), "utf-8")


def test_load_pista_assente(tmp_path):
    assert trackfacts.load("monza", root=tmp_path) is None


def test_load_versione_ignota_e_json_rotto(tmp_path):
    _write(tmp_path, "a", {"version": 99})
    _write(tmp_path, "b", "{")
    _write(tmp_path, "c", "[1]")
    assert trackfacts.load("a", root=tmp_path) is None
    assert trackfacts.load("b", root=tmp_path) is None
    assert trackfacts.load("c", root=tmp_path) is None


def test_load_valido(tmp_path):
    _write(tmp_path, "imola", _v3())
    assert trackfacts.load("imola", root=tmp_path)["version"] == 3


def test_for_corner_divide_per_gruppo(tmp_path):
    _write(tmp_path, "imola", _v3())
    f = trackfacts.load("imola", root=tmp_path)
    c = trackfacts.for_corner(f, "Tosa")
    assert [x["type"] for x in c["reference"]] == ["gear"]
    assert sorted(x["type"] for x in c["single"]) == ["brake", "line"]
    assert [x["type"] for x in c["mistakes"]] == ["mistake"]
    assert [x["type"] for x in c["disputed"]] == ["gear"]
    altro = trackfacts.for_corner(f, "Rivazza")
    assert altro == {"reference": [], "single": [], "disputed": [], "mistakes": []}
    assert trackfacts.for_corner(None, "Tosa") == altro


def test_for_corner_v2_senza_disputed():
    f = {"version": 2, "facts": [{"corner": "X", "type": "gear", "value": "2"}],
         "single": []}
    c = trackfacts.for_corner(f, "X")
    assert len(c["reference"]) == 1 and c["disputed"] == []


def test_gear_compare():
    single = {"reference": [], "disputed": [],
              "single": [{"type": "gear", "value": "2"}]}
    assert trackfacts.gear_compare("3", single) == {
        "you": "3", "source": "2", "state": "single"}
    assert trackfacts.gear_compare("2", single) is None
    assert trackfacts.gear_compare(None, single) is None
    assert trackfacts.gear_compare("N", single) is None
    both = {"reference": [{"type": "gear", "value": "4"}],
            "single": [{"type": "gear", "value": "2"}], "disputed": []}
    assert trackfacts.gear_compare("3", both) == {
        "you": "3", "source": "4", "state": "reference"}
    disp = {"reference": [], "single": [],
            "disputed": [{"type": "gear", "values": [{"value": "2"}]}]}
    assert trackfacts.gear_compare("3", disp) is None


def test_file_veri_si_leggono():
    for t in ("imola", "spa"):
        d = trackfacts.load(t)
        assert isinstance(d, dict) and d["version"] == 3


@pytest.mark.parametrize("track", ["../imola", "imola/../spa", "C:/x", ""])
def test_load_mai_un_percorso(track):
    assert trackfacts.load(track) is None


def test_load_col_nome_del_gioco():
    # Il catalogo dei giri dice «Imola»: è la stessa pista.
    assert trackfacts.load("Imola")["track"] == "imola"
