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


def _valore(type_, quote):
    """Il valore che la citazione sostiene, come lo legge il verificatore."""
    got = vocab.locate(type_, vocab.fold(quote))
    return got[0] if got else None

def fatto(quote, value, type_="brake", corner="Acque Minerali", offset=0):
    return {"corner": corner, "type": type_, "value": value, "quote": quote, "offset": offset}


def test_fatto_valido():
    q = "at acque minerali brake at the 100 board"
    assert verify.check_fact("imola", fatto(q, "board:100"), "so " + q + " ok") is None


def test_citazione_normalizzata_e_parola_cambiata():
    body = "at acque minerali's you brake at the 100 board"
    q = "acque minerali’s you brake  at the 100 board"
    assert verify.check_fact("imola", fatto(q, "board:100"), body) is None
    q2 = "acque minerali's you brake at the 150 board"
    assert verify.check_fact("imola", fatto(q2, "board:150"), body) == "citazione_assente"


def test_numero_non_citato():
    q = "brake at the 100 board into acque minerali"
    assert verify.check_fact("imola", fatto(q, "board:150"), q) == "numero_non_citato"
    q2 = "brake at the 1000 board into acque minerali"
    assert verify.check_fact("imola", fatto(q2, "board:100"), q2) == "numero_non_citato"


def test_valore_diverso_e_non_normalizzabile():
    q2 = "at acque minerali brake at the 100 board or the 150 board"
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
    assert _valore("gear", q) == "3"
    qq = "acque minerali " + q
    assert verify.check_fact("imola", fatto(qq, "3", "gear"), qq) is None


def test_gear_non_confonde_tempi():
    assert _valore("gear", "lose 3 seconds in 3 seconds") is None
    assert _valore("gear", "second corner") is None


@pytest.mark.parametrize("q", ["the 100 board", "100 metre board", "100m marker",
                               "cartello dei 100", "100 sign"])
def test_board_forme(q):
    assert _valore("brake", q) == "board:100"


def test_board_solo_valori_ammessi_e_oggetti():
    assert _valore("brake", "the 120 board") is None
    assert _valore("brake", "the 1000 board") is None
    assert _valore("brake", "brake at the bridge") == "object:bridge"
    assert _valore("brake", "frena all'inizio del cordolo") == "object:kerb_start"
    assert _valore("brake", "the bridge or the 100 board") is None


def test_apex_e_kerb():
    assert _valore("apex", "take a late apex here") == "late"
    assert _valore("apex", "apice anticipato") == "early"
    assert _valore("apex", "early apex then late apex") is None
    assert _valore("apex", "brake late, then turn in") is None
    assert _valore("kerb", "use the kerb on exit") == "exit"
    assert _valore("kerb", "don't use the kerb") == "none"
    assert _valore("kerb", "cordolo in ingresso") == "entry"


def test_descrittivi_non_votati():
    q = "tosa you want to stay wide and be patient"
    for t in ("line", "mistake"):
        assert _valore(t, q) is None
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
    body = "so at   " + q + ". and again at " + q
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
    # «after» è lontano dalla frenata e dal numero: per Piratella il fatto entra.
    assert verify.check_fact("imola", fatto(q, "board:100", corner="Piratella"), q) is None
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
    assert _valore("brake", q) is None
    qq = "tosa " + q
    for b in vocab.BOARDS:
        assert verify.check_fact("imola", fatto(qq, f"board:{b}", corner="Tosa"), qq) is not None


def test_brake_senza_parola_cartello():
    assert _valore("brake", "brake at the 150 into tosa") == "board:150"


@pytest.mark.parametrize("q", ["brake after the bridge", "the bridge is on the left",
                               "brake before the bridge", "frena dopo il ponte"])
def test_oggetto_solo_con_frase_di_frenata(q):
    assert _valore("brake", q) is None


@pytest.mark.parametrize("q,atteso", [
    ("brake at the bridge", "object:bridge"), ("brake by the bridge", "object:bridge"),
    ("brake when you reach the bridge", "object:bridge"), ("frena al ponte", "object:bridge"),
])
def test_oggetto_frasi_ammesse(q, atteso):
    assert _valore("brake", q) == atteso


@pytest.mark.parametrize("q", [
    "wait a second", "alla prima curva", "tosa is the 1st corner after the straight",
    "in 2 laps", "down to 5 kph",
    "third or fourth gear", "in 3 or 4", "not in third", "3rd", "use third",
    "nella terza curva", "in 2 corners", "in 3 seconds", "in 4 m", "in second place", "maybe third gear", "terza o quarta marcia",
])
def test_gear_ambiguo(q):
    assert _valore("gear", q) is None


@pytest.mark.parametrize("q,atteso", [
    ("shift down to second", "2"), ("into 4th", "4"), ("in second gear", "2"),
    ("scala in seconda", "2"), ("4 gear", "4"), ("marcia 2", "2"),
])
def test_gear_contesti_ammessi(q, atteso):
    assert _valore("gear", q) == atteso


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
    assert _valore(type_, q) != value
    qq = "tosa " + q
    assert verify.check_fact("imola", fatto(qq, value, type_, "Tosa"), qq) is not None


@pytest.mark.parametrize("q,type_,value", [
    ("late apex", "apex", "late"), ("apex late", "apex", "late"),
    ("apice ritardato", "apex", "late"), ("exit kerb", "kerb", "exit"),
    ("kerb on exit", "kerb", "exit"),
])
def test_apex_kerb_adiacenti(q, type_, value):
    assert _valore(type_, q) == value
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


# --- Round 2: la frase intera ------------------------------------------------


def _c(quote, value, type_, body=None, corner="Tosa", segments=None):
    body = quote if body is None else body
    off = max(body.lower().find(quote.lower()), 0)
    f = fatto(quote, value, type_, corner, off)
    if segments is None:
        return verify.check_fact("imola", f, body)
    return verify.check_fact("imola", f, body, segments=segments)


def test_citazione_oltre_frase():
    body = "after villeneuve you brake at the 100 board. then tosa is easy"
    assert _c("you brake at the 100 board. then tosa is easy", "board:100", "brake", body) \
        == "citazione_oltre_frase"
    body2 = "tosa: brake at the 100 board\nsecond gear"
    assert _c("tosa: brake at the 100 board second gear", "board:100", "brake", body2) \
        == "citazione_oltre_frase"
    body3 = "tosa! brake at the 100 board? yes"
    assert _c("tosa! brake at the 100 board", "board:100", "brake", body3) == "citazione_oltre_frase"
    # Il punto finale della citazione e il punto decimale non sono attraversamenti.
    assert _c("at tosa brake at the 100 board.", "board:100", "brake") is None


def test_frase_dai_segmenti_senza_punteggiatura():
    segs = [{"start_s": 0.0, "text": "at tosa brake at the 100 board"},
            {"start_s": 2.0, "text": "or later it depends"}]
    body = " ".join(s["text"] for s in segs)
    q = "at tosa brake at the 100 board"
    assert _c(q, "board:100", "brake", body) is not None  # senza segmenti è una frase sola
    assert _c(q, "board:100", "brake", body, segments=segs) is None
    assert _c("tosa brake at the 100 board or later", "board:100", "brake", body, segments=segs) \
        == "citazione_oltre_frase"


@pytest.mark.parametrize("quote,value,type_,body", [
    ("make at tosa and brake at the 100 board", "board:100", "brake",
     "don't make the mistake lots of people make at tosa and brake at the 100 board"),
    ("at tosa you brake at the 100 board", "board:100", "brake",
     "at tosa you brake at the 100 board or later, it depends"),
    ("at tosa go down to second gear", "2", "gear", "at tosa go down to second gear or third"),
    ("at tosa you brake at the 100", "board:100", "brake", "at tosa you brake at the 100 kph point"),
    ("at tosa you brake at the 100", "board:100", "brake",
     "at tosa you brake at the 100 metres mark, the 100 board is too late"),
    ("at tosa brake at the 100 board", "board:100", "brake", "at tosa brake at the 100 board. no!"),
    ("at tosa use the exit kerb", "exit", "kerb", "at tosa use the exit kerb, it is a mistake"),
])
def test_controlli_sulla_frase_intera(quote, value, type_, body):
    assert _c(quote, value, type_, body) is not None


def test_curva_prima_del_valore():
    body = "villeneuve: brake at the 100 board, then flat to tosa"
    assert _c("brake at the 100 board, then flat to tosa", "board:100", "brake", body) \
        == "curva_non_trovata"
    assert _c("brake at the 100 board, then flat to tosa", "board:100", "brake", body,
              corner="Villeneuve") is None
    # Round 3: la curva subito dopo il valore, con una preposizione, nella stessa frase.
    assert _c("brake at the 100 board into tosa", "board:100", "brake") is None
    assert _c("use the exit kerb at tosa", "exit", "kerb") is None
    assert _c("brake at the 100 board into tosa, down to second gear", "2", "gear") is None


@pytest.mark.parametrize("q", [
    "tosa: don´t use the exit kerb", "tosa: don`t use the exit kerb", "tosa: donʼt use the exit kerb",
    "tosa: don′t use the exit kerb", "tosa: don＇t use the exit kerb",
])
def test_apostrofi_varianti(q):
    assert verify.norm_text(q) == "tosa: don't use the exit kerb"
    assert _c(q, "exit", "kerb") == "negazione"


@pytest.mark.parametrize("q,value,type_", [
    ("tosa: shouldnt use the exit kerb", "exit", "kerb"),
    ("tosa: you cant use the exit kerb", "exit", "kerb"),
    ("tosa: you cannot use the exit kerb", "exit", "kerb"),
    ("tosa: you can not use the exit kerb", "exit", "kerb"),
    ("tosa: stay away from the exit kerb", "exit", "kerb"),
    ("tosa: keep off the exit kerb", "exit", "kerb"),
    ("tosa: stay clear of the exit kerb", "exit", "kerb"),
    ("tosa: watch out for the exit kerb", "exit", "kerb"),
    ("tosa: careful with the exit kerb", "exit", "kerb"),
    ("tosa: a late apex is too slow here", "late", "apex"),
    ("tosa: the late apex is a mistake", "late", "apex"),
    ("tosa: a late apex is bad", "late", "apex"),
    ("tosa: people use third gear here, wrong", "3", "gear"),
    ("alla tosa evitate la terza marcia", "3", "gear"),
    ("alla tosa evitando il cordolo in uscita", "exit", "kerb"),
    ("alla tosa nessun cordolo in uscita", "exit", "kerb"),
    ("alla tosa niente cordolo in uscita", "exit", "kerb"),
    ("alla tosa lascia stare il cordolo in uscita", "exit", "kerb"),
    ("alla tosa stai lontano dal cordolo in uscita", "exit", "kerb"),
    ("alla tosa guai a usare il cordolo in uscita", "exit", "kerb"),
    ("alla tosa neanche la terza marcia", "3", "gear"),
    ("alla tosa nemmeno la terza marcia", "3", "gear"),
    ("alla tosa mica la terza marcia", "3", "gear"),
    ("alla tosa né la terza marcia", "3", "gear"),
    ("alla tosa sbagliato frenare al cartello dei 100", "board:100", "brake"),
    ("alla tosa scordati di frenare ai 100", "board:100", "brake"),
    ("alla tosa non dimenticare: frena ai 100", "board:100", "brake"),
    ("alla tosa attenzione al cordolo in uscita", "exit", "kerb"),
    ("alla tosa occhio al cordolo in uscita", "exit", "kerb"),
    ("alla tosa è un errore il cordolo in uscita", "exit", "kerb"),
])
def test_negazioni_nuove(q, value, type_):
    assert _c(q, value, type_) == "negazione"


def test_negazione_senza_parole_inventate():
    # «\w+nt» non è una negazione: «want», «point», «front» restano parole normali.
    assert _c("tosa, you want a late apex here", "late", "apex") is None
    assert _c("at tosa the front goes, take a late apex", "late", "apex") is None


@pytest.mark.parametrize("q,value", [
    ("at tosa you lose time in 2 places", "2"), ("at tosa i'll explain in 3 steps", "3"),
    ("into the second chicane after tosa", "2"), ("tosa in the second run i was quicker", "2"),
    ("tosa: in 3 now", "3"), ("tosa: into 3 then", "3"), ("tosa: in second, then", "2"),
    ("tosa: down to the second", "2"), ("tosa, brake around the 100 board and grab second", "2"),
    ("tosa: down to ３rd gear", "3"), ("tosa: in ３ gear now", "3"), ("tosa: in ٣ gear now", "3"),
    ("tosa: first, then second gear", "2"),
])
def test_gear_contesti_stretti(q, value):
    assert _c(q, value, "gear") is not None


@pytest.mark.parametrize("q,value", [
    ("first you brake at the 100 board for tosa then second gear", "2"),
    ("tosa: first we brake, then second gear", "2"),
    # Round 2: «first» avverbio seguito da un verbo non è una marcia.
    ("tosa: first brake then second gear", "2"),
    ("alla tosa frena al cartello dei 100 e scala in seconda", "2"),
    ("into tosa i'm in third gear", "3"),
    ("tosa: shift down to 2", "2"), ("tosa: shift to 3 here", "3"),
    ("tosa: shift into second here", "2"), ("tosa: into 4th here", "4"),
])
def test_gear_contesti_ammessi_frase(q, value):
    assert _c(q, value, "gear") is None


def test_numeri_unicode_non_sono_cifre():
    assert _c("tosa: brake at the １００ board", "board:100", "brake") is not None


def test_spazi_unicode_normalizzati():
    assert _c("tosa: brake\xa0at the 100\xa0board", "board:100", "brake", "tosa: brake at the 100 board") is None
    assert _c("tosa: brake at the 100 board", "board:100", "brake", "tosa: brake\xa0at the 100 board") is None


@pytest.mark.parametrize("q,value,type_", [
    ("tosa, brake at the 100 board, second gear and a late apex", "board:100", "brake"),
    ("tosa, brake at the 100 board, second gear and a late apex", "2", "gear"),
    ("tosa, brake at the 100 board, second gear and a late apex", "late", "apex"),
    ("tosa: 100 board, second gear, late apex", "board:100", "brake"),
    ("tosa: 100 board, second gear, late apex", "2", "gear"),
    ("tosa: 100 board, second gear, late apex", "late", "apex"),
    ("tosa, brake at the 100, second gear, use the exit kerb", "exit", "kerb"),
    ("so for tosa we're braking at the 100 board", "board:100", "brake"),
    ("alla tosa frena al cartello dei 100 e scala in seconda", "board:100", "brake"),
    ("tosa, brake at the 100 board and go down to second gear", "2", "gear"),
    ("for tosa i brake at the 100 board in second gear", "2", "gear"),
    ("after tosa, at piratella brake at the 100 board", "board:100", "brake"),
])
def test_frase_con_piu_fatti(q, value, type_):
    corner = "Piratella" if "piratella" in q else "Tosa"
    assert _c(q, value, type_, corner=corner) is None


@pytest.mark.parametrize("q", [
    "tosa: brake 50 metres later", "tosa: brake later at the 100 board",
    "tosa: brake just after the 100 board", "tosa: the 100 board, but brake later",
])
def test_relative_vicino_alla_frenata(q):
    n = re.search(r"[0-9]+", q).group()
    assert _c(q, f"board:{n}", "brake") is not None


# --- Round 3: la curva dopo il valore, e gli errori ---------------------------


@pytest.mark.parametrize("q,value,type_", [
    ("brake at the 100 board into tosa", "board:100", "brake"),
    ("use the exit kerb at tosa", "exit", "kerb"),
    ("frena al cartello dei 100 alla tosa", "board:100", "brake"),
    ("take a late apex at the tosa", "late", "apex"),
    ("go down to second gear for tosa", "2", "gear"),
    ("brake at the bridge into tosa", "object:bridge", "brake"),
])
def test_curva_subito_dopo_il_valore(q, value, type_):
    assert _c(q, value, type_) is None
    assert _c(q, value, type_, corner="Piratella") == "curva_non_trovata"


@pytest.mark.parametrize("q,body", [
    ("brake at the 100 board, then flat to tosa", None),
    ("brake at the 100 board then flat into tosa", None),
    ("brake at the 100 board and then into tosa", None),
    ("brake at the 100 board; into tosa", None),
    ("brake at the 100 board flat into tosa", None),
    ("villeneuve: brake at the 100 board into tosa", None),
    ("brake at the 100 board into tosa", "villeneuve: brake at the 100 board into tosa"),
])
def test_curva_dopo_il_valore_rifiutata(q, body):
    assert _c(q, "board:100", "brake", body) == "curva_non_trovata"


def test_curva_dopo_il_valore_ambigua_anche_per_la_prima():
    q = "villeneuve: brake at the 100 board into tosa"
    assert _c(q, "board:100", "brake", corner="Villeneuve") == "curva_non_trovata"


def test_curva_dopo_il_valore_batte_la_frase_prima():
    body = "piratella is tricky. brake at the 100 board into tosa"
    q = "brake at the 100 board into tosa"
    assert _c(q, "board:100", "brake", body) is None
    assert _c(q, "board:100", "brake", body, corner="Piratella") == "curva_non_trovata"


def test_curva_dopo_il_valore_frase_diversa():
    body = "after villeneuve you brake at the 100 board. then tosa is easy"
    q = "after villeneuve you brake at the 100 board"
    assert _c(q, "board:100", "brake", body) == "curva_non_trovata"


def test_errore_ammette_le_negazioni():
    q = "at tosa the classic mistake is braking too late"
    assert _c(q, q, "mistake") is None
    q2 = "at tosa people don't lift and spin"
    assert _c(q2, q2, "mistake") is None
    assert _c(q, "braking too late", "mistake") == "valore_diverso"
    assert _c(q, q, "mistake", corner="Rivazza") == "curva_non_trovata"
    assert _c(q, q, "line") == "negazione"


def test_curva_dopo_il_valore_stessa_curva_prima():
    q = "at tosa brake at the 100 board into tosa"
    assert _c(q, "board:100", "brake") is None


# --- Round 4: una curva per frase, i sottotitoli dividono le frasi -----------


@pytest.mark.parametrize("q,body,type_", [
    ("on the exit of villeneuve stay wide to set up tosa", None, "line"),
    ("stay wide on exit so tosa", "villeneuve: stay wide on exit so tosa", "mistake"),
])
def test_descrittivi_due_curve(q, body, type_):
    assert _c(q, q, type_, body) == "curva_non_trovata"
    assert _c(q, q, type_, body, corner="Villeneuve") == "curva_non_trovata"


def test_descrittivi_una_curva_sola_restano():
    q = "on the exit of tosa stay wide"
    assert _c(q, q, "line") is None
    body = "villeneuve is fine. at tosa stay wide on exit"
    q2 = "at tosa stay wide on exit"
    assert _c(q2, q2, "line", body) is None


def test_segmenti_dividono_anche_con_punteggiatura():
    body = "is this right? at villeneuve brake hard at the 100 board then tosa"
    segs = [{"start_s": 0.0, "text": "at villeneuve brake hard"},
            {"start_s": 2.0, "text": "at the 100 board then tosa"}]
    q = "villeneuve brake hard at the 100 board"
    assert _c(q, "board:100", "brake", body, corner="Villeneuve") is None  # senza segmenti
    assert _c(q, "board:100", "brake", body, corner="Villeneuve", segments=segs) \
        == "citazione_oltre_frase"


@pytest.mark.parametrize("sep", ["\u2028", "\u2029", "\x85", "\v", "\f"])
def test_altri_a_capo_dividono(sep):
    body = f"so brake at the 100 board{sep}into tosa"
    q = "brake at the 100 board into tosa"
    f = fatto(q, "board:100", "brake", "Tosa", body.index("brake"))
    assert verify.check_fact("imola", f, body) == "citazione_oltre_frase"
    assert verify.check_fact("imola", f, body.replace(sep, " ")) is None


def test_alias_seguito_da_trattino_e_lettera():
    q = "brake at the 100 board into tosa-like corners"
    assert _c(q, "board:100", "brake") == "curva_non_trovata"
    assert not vocab.alias_regex("tosa").search("tosa-like")
    assert vocab.alias_regex("tosa").search("tosa's")
    assert vocab.alias_regex("tosa").search("tosa-2")
    q2 = "at tosa's exit, brake at the 100 board"
    assert _c(q2, "board:100", "brake") is None


def test_gear_seconda_marcia_nella_frase():
    body = "at tosa go down to 2 gear 3"
    assert _c("at tosa go down to 2 gear", "2", "gear", body) == "valore_non_normalizzabile"
    body2 = "at tosa second gear, tosa in third gear"
    assert _c("at tosa second gear", "2", "gear", body2) == "valore_non_normalizzabile"
    body3 = "go down to second gear for tosa, then third gear"
    assert _c("go down to second gear for tosa", "2", "gear", body3) == "valore_non_normalizzabile"


def test_gear_seconda_marcia_altra_curva():
    body = "at tosa second gear, piratella in third gear"
    assert _c("at tosa second gear", "2", "gear", body) is None
    assert _c("piratella in third gear", "3", "gear", body, corner="Piratella") is None
    assert _c("piratella in third gear", "3", "gear", body) == "curva_non_trovata"
