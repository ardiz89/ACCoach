"""Vocabolario e verificatore (tools/fonti): niente entra se non è citato alla lettera."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from accoach.trackdata import _CORNERS  # noqa: E402
from tools.fonti import verify, vocab  # noqa: E402


def fatto(quote, value, type_="brake", corner="Acque Minerali", offset=0):
    return {"corner": corner, "type": type_, "value": value, "quote": quote, "offset": offset}


def test_fatto_valido():
    q = "brake at the 100 board into acque minerali"
    assert verify.check_fact("imola", fatto(q, "board:100"), "so " + q + " ok") is None


def test_citazione_normalizzata_e_parola_cambiata():
    body = "you brake at the 100 board into acque minerali's"
    q = "brake  at the 100 board into acque minerali’s"
    assert verify.check_fact("imola", fatto(q, "board:100"), body) is None
    q2 = "brake at the 150 board into acque minerali"
    assert verify.check_fact("imola", fatto(q2, "board:150"), body) == "citazione_assente"


def test_numero_non_citato():
    q = "brake at the 100 board into acque minerali"
    assert verify.check_fact("imola", fatto(q, "board:150"), q) == "numero_non_citato"
    q2 = "brake at the 1000 board into acque minerali"
    assert verify.check_fact("imola", fatto(q2, "board:100"), q2) == "numero_non_citato"


def test_valore_diverso_e_non_normalizzabile():
    q2 = "brake at the 100 board or the 150 board into acque minerali"
    assert verify.check_fact("imola", fatto(q2, "board:100"), q2) == "valore_non_normalizzabile"
    q5 = "acque minerali: apex late and also 100 m"
    assert verify.check_fact("imola", fatto(q5, "early", "apex"), q5) == "valore_diverso"


def test_tipo_ignoto():
    assert verify.check_fact("imola", fatto("x", "y", "boh"), "x") == "tipo_ignoto"


def test_alias_storpiati():
    nomi = {n for n, _ in _CORNERS["imola"]}
    for testo, atteso in [("tamburelo", "Tamburello"), ("acqua minerale", "Acque Minerali"),
                          ("the rivazza", "Rivazza"), ("t7", "Piratella")]:
        trovati = [n for n in nomi
                   if any(vocab.alias_regex(a).search(testo) for a in vocab.CORNERS["imola"][n])]
        assert trovati == [atteso]


def test_nomi_canonici_e_ordine_da_trackdata():
    assert list(vocab.CORNERS["imola"]) == [n for n, _ in _CORNERS["imola"]]


def test_nessun_alias_ambiguo_e_nessun_numero_nudo():
    visti = {}
    for nome, alias in vocab.CORNERS["imola"].items():
        for a in alias:
            assert a == a.lower() and not a.isdigit()
            assert a not in visti, f"{a!r} sta in {visti.get(a)} e {nome}"
            visti[a] = nome


def test_curva_nel_contesto():
    q = "brake at the 100 board"
    pre = "acque minerali " + "x" * 200
    assert verify.check_fact("imola", fatto(q, "board:100", offset=len(pre)), pre + q) is None
    pre2 = "acque minerali " + "x" * 400
    assert verify.check_fact("imola", fatto(q, "board:100", offset=len(pre2)),
                             pre2 + q) == "curva_non_trovata"


def test_curva_non_confusa_con_numero_piu_lungo():
    q = "turn 10 brake at the 100 board"
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Tamburello"), q) == "curva_non_trovata"
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Variante Alta"), q) is None


@pytest.mark.parametrize("q", ["third gear", "3rd", "in terza", "down to 3"])
def test_gear_parole(q):
    assert vocab.normalize("gear", q) == "3"
    assert verify.check_fact("imola", fatto("t8 " + q, "3", "gear"), "t8 " + q) is None


def test_gear_non_confonde_tempi():
    assert vocab.normalize("gear", "lose 3 seconds in 3 seconds") is None
    assert vocab.normalize("gear", "second corner") is None


@pytest.mark.parametrize("q", ["the 100 board", "100 metre board", "100m marker",
                               "cartello dei 100", "100 sign"])
def test_board_forme(q):
    assert vocab.normalize("brake", q) == "board:100"


def test_board_solo_valori_ammessi_e_oggetti():
    assert vocab.normalize("brake", "the 120 board") is None
    assert vocab.normalize("brake", "the 1000 board") is None
    assert vocab.normalize("brake", "brake at the bridge") == "object:bridge"
    assert vocab.normalize("brake", "inizio del cordolo") == "object:kerb_start"
    assert vocab.normalize("brake", "the bridge or the 100 board") is None


def test_apex_e_kerb():
    assert vocab.normalize("apex", "take a late apex here") == "late"
    assert vocab.normalize("apex", "apice anticipato") == "early"
    assert vocab.normalize("apex", "early apex then late apex") is None
    assert vocab.normalize("apex", "brake late, then turn in") is None
    assert vocab.normalize("kerb", "use the kerb on exit") == "exit"
    assert vocab.normalize("kerb", "don't use the kerb") == "none"
    assert vocab.normalize("kerb", "cordolo in ingresso") == "entry"


def test_descrittivi_non_votati():
    q = "tosa you want to stay wide and be patient"
    for t in ("line", "mistake"):
        assert vocab.normalize(t, q) is None
        assert verify.check_fact("imola", fatto(q, "stay wide", t, "Tosa"), q) is None
        assert verify.check_fact("imola", fatto(q, "stay wide", t, "Rivazza"), q) == "curva_non_trovata"
        assert verify.check_fact("imola", fatto("stay narrow", "stay wide", t, "Tosa"), q) == "citazione_assente"
