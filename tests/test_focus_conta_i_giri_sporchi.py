"""Il focus conta anche i giri sporchi. L'Ingegnere no.

Chiesto dal pilota il 2026-10-09: «se faccio 3 giri e uno non e' pulito vorrei
che me lo contasse lo stesso». Deciso **misurando**, non discutendo: rigiocati i
suoi 95 giri di Monza e Imola (26 sporchi) con e senza il filtro.

**Per il focus il filtro non comprava niente.** Contando tutto, il focus insegna
le stesse curve nello stesso ordine e ci arriva da 2 a 6 giri prima — a Imola
trova la Tosa al giro 17 invece che al 23. Divergono solo sulla quarta elezione,
dove le perdite sono 73 e 101 ms, cioe' rumore. Il motivo e' che il focus misura
**per curva**, su una mediana di sei giri: una curva sbagliata avvelena se'
stessa e la mediana assorbe.

**Per l'Ingegnere sarebbe un disastro, e non per il motivo ovvio.** Tutti e 26 i
giri sporchi cadono fuori dalla sua banda di decisione (174 ms a Monza, 162 a
Imola) -- ma soprattutto **sei su tredici sono piu' VELOCI** della mediana
pulita, fino a 2.8 s. Ovvio col senno di poi: tagli la Variante e vai forte. Se
entrassero nel giudizio, l'Ingegnere accetterebbe una modifica d'assetto sulla
forza di una chicane tagliata, e l'assetto deriverebbe dietro agli errori.

Quindi il filtro non si toglie: si **sposta**. Il focus tiene solo `valid` (un
giro incompleto o di rientro non e' una misura di come guidi); l'Ingegnere tiene
la regola intera, e la calcola per conto suo in `diagnosis.py`.
"""
import logging

import pytest

import synth
from accoach.coaching.focus import FocusCoach
from accoach.comparison import Reference
from accoach.engine import CoachEngine
from accoach.track import detect_corners


class _Dummy:
    def read(self): ...
    def close(self): ...


@pytest.fixture
def motore(tmp_path):
    eng = CoachEngine(reader=_Dummy(), voice=None, laps_dir=tmp_path)
    ref = synth.build_lap(n=300, clean=True)
    eng._reference = Reference(ref)
    eng._corners = detect_corners(ref.samples)
    eng._focus = FocusCoach()
    yield eng
    eng.close()


def _tre_giri(eng, **kw):
    lento = synth.build_lap(slow_corner=0, amt=30, n=300, **kw)
    for _ in range(3):
        eng._observe_lap(lento)
    return eng._focus_report


def test_tre_giri_sporchi_adesso_eleggono_un_focus(motore):
    """La richiesta del pilota, alla lettera.

    Prima di questa modifica tre giri sporchi lasciavano il coach a «valuto»
    per sempre: su 14 giri del 01/09 sei erano sporchi -- il piu' veloce
    compreso -- e la prova del focus non si chiuse per quello.
    """
    r = _tre_giri(motore, clean=False)
    assert r is not None and r.focus is not None, (
        "tre giri sporchi non hanno eletto niente: il filtro e' ancora li'")


def test_un_giro_non_valido_resta_fuori(motore):
    """L'altra meta', ed e' quella che impedisce di buttare il bambino.

    Un giro incompleto o di rientro ai box non e' una misura di come guidi:
    dura il triplo e la sua perdita per curva non vuol dire niente. `valid`
    resta.
    """
    r = _tre_giri(motore, valid=False, clean=True)
    assert r is None or r.focus is None, (
        "un giro non valido ha contribuito a eleggere un focus")


def test_l_ingegnere_continua_a_scartare_i_giri_sporchi():
    """Il filtro non e' stato tolto, e' stato **spostato**.

    Se un giorno qualcuno allineasse le due regole «per coerenza», l'Ingegnere
    comincerebbe ad accettare modifiche sulla forza di una chicane tagliata.
    Questo test e' li' per far fallire quel giorno.
    """
    from accoach.coaching.diagnosis import build_lap_stats

    sporco = synth.build_lap(slow_corner=0, amt=30, n=300, clean=False)
    stats = build_lap_stats(sporco, [])
    assert stats.stable is False, (
        "l'Ingegnere ha smesso di scartare i giri sporchi: con quelli "
        "giudicherebbe una modifica d'assetto contro un giro tagliato, che "
        "nell'archivio e' fino a 2.8 s PIU' VELOCE di uno pulito")


def test_la_riga_di_log_non_dice_piu_che_un_giro_sporco_non_e_contato(motore, caplog):
    """La diagnostica deve dire la verita' nuova, non quella vecchia.

    Fino a ieri la coda diceva «non contato: giro non pulito». Lasciarla
    direbbe al pilota il contrario di quello che il coach adesso fa -- e una
    riga di log che mente e' peggio di una riga assente, perche' ci si
    costruisce sopra.
    """
    with caplog.at_level(logging.INFO, logger="accoach.coach"):
        _tre_giri(motore, clean=False)
    righe = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("focus |")]
    assert righe
    assert not any("non pulito" in r for r in righe), righe
