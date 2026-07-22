"""Il cerchio di aderenza: perché *non* puoi frenare più tardi.

`g_lat` e `g_long` erano registrati in ogni file di giro da versioni e letti solo
da un grafico. Rispondono alla domanda che dà il nome al prodotto e che su Reddit
i piloti dicono di non ricevere mai da nessun coach: **perché** qui non riesco a
frenare più tardi. Quasi sempre perché la gomma sta già spendendo l'aderenza per
girare — freno e curva attingono a un budget solo, non a due.

L'inviluppo è misurato dal giro di riferimento, non assunto: nessuna costante per
auto, e si adatta a mescola, benzina e stato della pista.
"""
import math
from dataclasses import replace

import pytest

from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import (
    _GRIP_AT_LIMIT,
    _GRIP_PCTL,
    _combined_g,
    _grip_detail,
    _grip_envelope,
)
from accoach.comparison import Reference

import synth


class _S:
    """Un campione con le sole G che servono qui."""

    def __init__(self, g_lat, g_long):
        self.g_lat, self.g_long = g_lat, g_long


def test_combined_g_is_the_radius_on_the_friction_circle():
    assert _combined_g(3.0, 4.0) == pytest.approx(5.0)


def test_at_the_limit_it_says_there_is_no_later_braking_to_find():
    """La frase che cambia il consiglio: se la gomma è satura, «frena più tardi»
    è un'istruzione che porta nella ghiaia."""
    inside = [_S(1.9, 0.4)]           # |g| ≈ 1.94 su un inviluppo di 2.0
    out = _grip_detail(inside, 2.0, CueCategory.BRAKE_LATER, "it")
    assert "non c'è una frenata più tarda" in out


def test_well_below_the_limit_it_says_there_is_grip_left():
    inside = [_S(1.2, 0.3)]           # |g| ≈ 1.24 su 2.0 → 62%
    out = _grip_detail(inside, 2.0, CueCategory.BRAKE_LATER, "it")
    assert "rimasto carico" in out


def test_in_between_it_claims_nothing():
    """Fra l'85% e il 95% non c'è niente di onesto da dire, quindi si tace."""
    inside = [_S(1.8, 0.0)]           # 90%
    assert _grip_detail(inside, 2.0, CueCategory.BRAKE_LATER, "it") == ""


def test_it_only_speaks_where_it_changes_the_advice():
    """Su «più gas in uscita» l'aderenza combinata non decide niente."""
    inside = [_S(1.95, 0.2)]
    assert _grip_detail(inside, 2.0, CueCategory.MORE_THROTTLE, "it") == ""
    assert _grip_detail(inside, 2.0, CueCategory.CARRY_SPEED, "it") != ""


def test_a_lap_without_g_data_says_nothing():
    """I giri vecchi hanno le G a zero: assenza di dato, assenza di frase."""
    assert _grip_detail([_S(0.0, 0.0)], 2.0, CueCategory.BRAKE_LATER, "it") == ""
    assert _grip_detail([_S(1.9, 0.4)], 0.0, CueCategory.BRAKE_LATER, "it") == ""


# --- l'inviluppo -----------------------------------------------------------

def test_the_envelope_is_measured_from_the_reference_not_assumed():
    lap = synth.build_lap()
    env = _grip_envelope(lap, Reference(synth.build_lap()))
    peak = max(_combined_g(s.g_lat, s.g_long) for s in lap.samples)
    assert 0.0 <= env <= peak + 1e-6


def test_one_kerb_strike_does_not_define_the_envelope():
    """Il massimo verrebbe fissato da un cordolo o da un dosso, e ogni curva
    sembrerebbe avere aderenza in avanzo. Da qui il percentile."""
    ref_lap = synth.build_lap()
    n = len(ref_lap.samples)
    spike = replace(ref_lap.samples[n // 2], g_lat=9.0, g_long=9.0)
    ref_lap.samples[n // 2] = spike
    env = _grip_envelope(synth.build_lap(), Reference(ref_lap))
    assert env < _combined_g(9.0, 9.0), "il picco isolato non deve fare da limite"


def test_the_percentile_is_high_enough_to_mean_the_limit():
    """Troppo basso e chiamerebbe «limite» la guida normale."""
    assert 0.9 <= _GRIP_PCTL <= 0.99
    assert _GRIP_AT_LIMIT >= 0.9


def test_the_two_bands_do_not_overlap():
    from accoach.coaching.debrief import _GRIP_SPARE

    assert _GRIP_SPARE < _GRIP_AT_LIMIT


def test_it_never_claims_more_than_all_the_grip():
    """Sui giri veri dell'utente diceva «sei al 120% dell'aderenza».

    Confrontava il picco GREZZO del pilota con il 95° percentile del riferimento:
    due statistiche diverse. Adesso è lo stesso percentile su entrambi i lati, e
    il numero è comunque limitato a 100 — l'inviluppo è una stima, e «sei al 104%»
    è una frase la cui risposta onesta è «il limite è approssimato».
    """
    inside = [_S(3.0, 3.0)] * 10          # ben oltre l'inviluppo
    out = _grip_detail(inside, 2.0, CueCategory.BRAKE_LATER, "it")
    assert "100%" in out
    for impossible in ("103%", "104%", "120%"):
        assert impossible not in out


def test_a_single_spike_in_the_corner_does_not_decide_it():
    """Stessa robustezza su entrambi i lati: un cordolo preso dentro la curva non
    deve far dire «sei al limite» a chi al limite non c'era."""
    inside = [_S(0.9, 0.1)] * 30 + [_S(3.0, 3.0)]
    assert "non c'è una frenata più tarda" not in _grip_detail(
        inside, 2.0, CueCategory.BRAKE_LATER, "it")
