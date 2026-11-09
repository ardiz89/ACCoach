"""Vocabolario e verificatore (tools/fonti): niente entra se non è citato alla lettera."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import re  # noqa: E402

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
                          ("the rivazza", "Rivazza")]:
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
    pre = "acque minerali " + "x" * 200 + " "
    assert verify.check_fact("imola", fatto(q, "board:100", offset=len(pre)), pre + q) is None
    pre2 = "acque minerali " + "x" * 400 + " "
    assert verify.check_fact("imola", fatto(q, "board:100", offset=len(pre2)),
                             pre2 + q) == "curva_non_trovata"


def test_nessun_numero_di_curva_negli_alias():
    # I numeri di curva erano inventati, senza una fonte: fuori tutti.
    for alias in vocab.CORNERS["imola"].values():
        for a in alias:
            assert not re.search(r"\d", a), a
    q = "turn 10 brake at the 100 board"
    for nome, _ in _CORNERS["imola"]:
        assert verify.check_fact("imola", fatto(q, "board:100", corner=nome), q) == "curva_non_trovata"


@pytest.mark.parametrize("q", ["third gear", "3rd gear", "in terza", "down to 3"])
def test_gear_parole(q):
    assert vocab.normalize("gear", q) == "3"
    qq = "acque minerali " + q
    assert verify.check_fact("imola", fatto(qq, "3", "gear"), qq) is None


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
    assert vocab.normalize("brake", "frena all'inizio del cordolo") == "object:kerb_start"
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
        assert verify.check_fact("imola", fatto(q, q, t, "Tosa"), q) is None
        assert verify.check_fact("imola", fatto(q, q, t, "Rivazza"), q) == "curva_non_trovata"
        assert verify.check_fact("imola", fatto("stay narrow", q, t, "Tosa"), q) == "citazione_assente"


# --- Round 1: nel dubbio si rifiuta ----------------------------------------


def _at(body, quote):
    """Offset vero della citazione nel testo grezzo."""
    return body.index(quote)


@pytest.mark.parametrize("body,quote,type_,value", [
    ("at tosa brake at the 150 board", "50 board", "brake", "board:50"),
    ("at tosa brake at the 150 board", "tosa brake at the 15", "brake", "board:150"),
    ("at tosa you gain in 30 seconds", "in 3", "gear", "3"),
    ("at tosa you gain in 30 seconds", "tosa you gain in 3", "gear", "3"),
    ("tosa is the 23rd corner", "3rd", "gear", "3"),
    ("tosa is the 23rd corner", "tosa is the 2", "gear", "2"),
])
def test_citazione_su_confini_di_parola(body, quote, type_, value):
    for off in range(len(body)):
        f = fatto(quote, value, type_, "Tosa", off)
        assert verify.check_fact("imola", f, body) == "citazione_assente"


def test_negazione_lontana_non_conta():
    body = "never brake in the dark. one two three four five six, at tosa take a late apex"
    q = "at tosa take a late apex"
    assert verify.check_fact("imola", fatto(q, "late", "apex", "Tosa", _at(body, q)), body) is None


@pytest.mark.parametrize("body,quote,type_,value", [
    ("at tosa never take a late apex", "tosa never take a late apex", "apex", "late"),
    ("at tosa never take a late apex", "late apex", "apex", "late"),
    ("at tosa never take a late apex", "take a late apex", "apex", "late"),
    ("at tosa don't use the kerb on exit", "use the kerb on exit", "kerb", "exit"),
    ("at tosa dont use the kerb on exit", "use the kerb on exit", "kerb", "exit"),
    ("at tosa avoid the 100 board, it is too late", "the 100 board, it is too late", "brake", "board:100"),
    ("a tosa non frenare al cartello dei 100", "frenare al cartello dei 100", "brake", "board:100"),
    ("tosa: mai in terza, si va", "in terza, si va", "gear", "3"),
    ("tosa stay off the kerb on exit", "the kerb on exit", "kerb", "exit"),
    ("tosa brake at the 150 board instead", "tosa brake at the 150 board", "brake", "board:150"),
    ("tosa you can use the kerb on entry or not", "tosa you can use the kerb on entry", "kerb", "entry"),
    ("tosa: use the exit kerb, that will kill you", "tosa: use the exit kerb", "kerb", "exit"),
    ("tosa: line through the middle without lifting", "tosa: line through the middle without lifting", "line",
     "tosa: line through the middle without lifting"),
])
def test_negazione_nella_citazione_o_vicino(body, quote, type_, value):
    f = fatto(quote, value, type_, "Tosa", _at(body, quote))
    assert verify.check_fact("imola", f, body) is not None


@pytest.mark.parametrize("offset", [40, -1, 10_000, "3", 3.0, None, True, [3]])
def test_offset_errato(offset):
    body = "so at tosa brake at the 100 board ok and then some more words here"
    q = "tosa brake at the 100 board"
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Tosa", offset=offset), body) == "offset_errato"


def test_offset_vicino_e_seconda_occorrenza():
    q = "tosa brake at the 100 board"
    body = "so at   " + q + " and later again at " + q
    first = body.index(q)
    second = body.rindex(q)
    for off in (first, first - 5, first + 5, second, second + 4):
        assert verify.check_fact("imola", fatto(q, "board:100", corner="Tosa", offset=off), body) is None
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Tosa", offset=first + 6), body) == "offset_errato"


def test_offset_dopo_spazi_compressi():
    # La citazione normalizzata si ritrova nel grezzo attraverso la mappa degli indici.
    pre = "intro\n\n\n   " * 30
    q = "tosa brake at the 100 board"
    body = pre + "Tosa   brake at\tthe 100 board"
    off = len(pre)
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Tosa", offset=off), body) is None
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Tosa", offset=off - 60), body) == "offset_errato"


def test_curva_e_l_ultima_nominata():
    body = "at tosa brake at the 100 board. then piratella, brake at the 50 board"
    q = "then piratella, brake at the 50 board"
    off = _at(body, q)
    assert verify.check_fact("imola", fatto(q, "board:50", corner="Tosa", offset=off), body) == "curva_non_trovata"
    assert verify.check_fact("imola", fatto(q, "board:50", corner="Piratella", offset=off), body) is None
    q2 = "brake at the 50 board"
    off2 = body.rindex(q2)
    assert verify.check_fact("imola", fatto(q2, "board:50", corner="Tosa", offset=off2), body) == "curva_non_trovata"


def test_curva_ultima_dentro_la_citazione():
    q = "after tosa, at piratella brake at the 100 board"
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Tosa"), q) == "curva_non_trovata"
    # «after» è anche una parola relativa della frenata: qui il fatto non entra comunque.
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Piratella"), q) == "valore_non_normalizzabile"
    q2 = "leave tosa, at piratella brake at the 100 board"
    assert verify.check_fact("imola", fatto(q2, "board:100", corner="Tosa"), q2) == "curva_non_trovata"
    assert verify.check_fact("imola", fatto(q2, "board:100", corner="Piratella"), q2) is None


@pytest.mark.parametrize("q", [
    "not the 100 board, brake at the 150",
    "brake at the 150, not the 100 board",
    "don't brake at the 100 board",
    "100 metres after the 150 board",
    "brake 50 metres later than usual",
    "brake at 100 kph into the corner",
    "brake at the 100 board, 2.5 seconds",
    "the 100 board is too early",
    "maybe brake at the 100 board",
    "brake at the 100 board if you have the grip",
])
def test_brake_ambiguo(q):
    assert vocab.normalize("brake", q) is None
    qq = "tosa " + q
    for b in vocab.BOARDS:
        assert verify.check_fact("imola", fatto(qq, f"board:{b}", corner="Tosa"), qq) is not None


def test_brake_senza_parola_cartello():
    assert vocab.normalize("brake", "brake at the 150 into tosa") == "board:150"


@pytest.mark.parametrize("q", ["brake after the bridge", "the bridge is on the left",
                               "brake before the bridge", "frena dopo il ponte"])
def test_oggetto_solo_con_frase_di_frenata(q):
    assert vocab.normalize("brake", q) is None


@pytest.mark.parametrize("q,atteso", [
    ("brake at the bridge", "object:bridge"), ("brake by the bridge", "object:bridge"),
    ("brake when you reach the bridge", "object:bridge"), ("frena al ponte", "object:bridge"),
])
def test_oggetto_frasi_ammesse(q, atteso):
    assert vocab.normalize("brake", q) == atteso


@pytest.mark.parametrize("q", [
    "wait a second", "alla prima curva", "tosa is the 1st corner after the straight",
    "first brake then second gear", "in 2 laps", "down to 5 kph",
    "third or fourth gear", "in 3 or 4", "not in third", "3rd", "use third",
    "nella terza curva", "in 2 corners", "in 3 seconds", "in 4 m", "in second place", "maybe third gear", "terza o quarta marcia",
])
def test_gear_ambiguo(q):
    assert vocab.normalize("gear", q) is None


@pytest.mark.parametrize("q,atteso", [
    ("shift down to second", "2"), ("into 4th", "4"), ("in second gear", "2"),
    ("scala in seconda", "2"), ("4 gear", "4"), ("marcia 2", "2"),
])
def test_gear_contesti_ammessi(q, atteso):
    assert vocab.normalize("gear", q) == atteso


@pytest.mark.parametrize("q,type_,value", [
    ("never use the exit kerb", "kerb", "exit"),
    ("avoid the exit kerb", "kerb", "exit"),
    ("stay off the kerb on exit", "kerb", "exit"),
    ("the kerb on exit will kill you", "kerb", "exit"),
    ("the exit kerb is dangerous", "kerb", "exit"),
    ("il cordolo in uscita è pericoloso", "kerb", "exit"),
    ("the exit kerb will cost you time", "kerb", "exit"),
    ("you can use the kerb on entry or not", "kerb", "entry"),
    ("brake late into the apex", "apex", "late"),
    ("brake late, clip apex", "apex", "late"),
    ("midway to the apex, go late", "apex", "late"),
    ("don't take an early apex", "apex", "early"),
    ("late or early apex", "apex", "early"),
    ("exit kerb then apex kerb", "kerb", "exit"),
])
def test_apex_kerb_non_accettati(q, type_, value):
    assert vocab.normalize(type_, q) != value
    qq = "tosa " + q
    assert verify.check_fact("imola", fatto(qq, value, type_, "Tosa"), qq) is not None


@pytest.mark.parametrize("q,type_,value", [
    ("late apex", "apex", "late"), ("apex late", "apex", "late"),
    ("apice ritardato", "apex", "late"), ("exit kerb", "kerb", "exit"),
    ("kerb on exit", "kerb", "exit"),
])
def test_apex_kerb_adiacenti(q, type_, value):
    assert vocab.normalize(type_, q) == value
    qq = "at tosa take the " + q
    assert verify.check_fact("imola", fatto(qq, value, type_, "Tosa"), qq) is None


def test_citazione_almeno_quattro_parole():
    q = "tosa late apex"
    assert verify.check_fact("imola", fatto(q, "late", "apex", "Tosa"), q) == "citazione_corta"


@pytest.mark.parametrize("t", ["line", "mistake"])
def test_descrittivi_valore_uguale_alla_citazione(t):
    q = "tosa you want to stay wide and be patient"
    assert verify.check_fact("imola", fatto(q, "stay wide", t, "Tosa"), q) == "valore_diverso"
    assert verify.check_fact("imola", fatto(q, "Tosa  you want to stay wide and be patient", t, "Tosa"), q) is None
