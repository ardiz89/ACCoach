"""Il limite di grip di una curva si misura a quella velocità.

Fino al 2026-11-03 l'inviluppo era uno solo, il 95° percentile del G combinato
del riferimento su tutto il giro. Ma l'aderenza cresce con la velocità
(carico aerodinamico): il picco del giro lo fanno le curve veloci, e una curva
lenta presa al limite risultava al 58 %, con la frase «sulla gomma resta carico
da usare». Adesso l'inviluppo è per fasce di 40 km/h (Decisione 5 del piano
«gesti per curva e aderenza per velocità»), e una fascia con meno di 50
campioni prende quello di tutto il giro: pochi campioni darebbero un limite
basso che fa dire «sei al limite» ovunque (Review Focus 4).
"""
import pytest

from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import (
    _GRIP_BAND_KMH,
    _GRIP_BAND_MIN_SAMPLES,
    _grip_detail,
    _grip_envelope,
    _grip_state,
)
from accoach.comparison import Reference
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType


class _S:
    """Un campione di curva con le sole G e la frenata che servono qui."""

    def __init__(self, g_lat, g_long=0.0, brake=1.0, throttle=0.0, t_ms=0):
        self.g_lat, self.g_long = g_lat, g_long
        self.brake, self.throttle, self.t_ms = brake, throttle, t_ms


def _lap(points) -> Lap:
    """Un giro da una lista di (velocità, G laterale), a posizioni uniformi."""
    n = len(points)
    samples = [LapSample(i * 100, i / (n - 1), spd, 1.0, 0.0, 0.0, "4", 8000,
                         g, 0.0)
               for i, (spd, g) in enumerate(points)]
    return Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, n * 100, True,
               samples=samples)


def _ref_slow_and_fast():
    """1,2 G sotto i 120 km/h, 2,0 sopra: 200 campioni per parte."""
    slow = [(60.0 + 60.0 * i / 200, 1.2) for i in range(200)]       # 60-119
    fast = [(130.0 + 120.0 * i / 200, 2.0) for i in range(200)]     # 130-249
    return _lap(slow + fast)


def _envelope(ref_lap):
    # I campioni dell'inviluppo sono quelli del giro rivisto: qui lo stesso giro.
    return _grip_envelope(ref_lap, Reference(ref_lap))


def test_the_bands_are_the_measured_decision():
    assert _GRIP_BAND_KMH == 40.0
    assert _GRIP_BAND_MIN_SAMPLES == 50


def test_a_slow_corner_at_its_own_limit_is_at_the_limit():
    """Il difetto: 1,15 G contro il 2,0 del giro faceva «58 %»."""
    env = _envelope(_ref_slow_and_fast())
    assert env.whole == pytest.approx(2.0)
    assert env.at(90.0) == pytest.approx(1.2)
    st = _grip_state([_S(1.15)] * 20, env, 90.0)
    assert st.at_limit
    assert st.ratio == pytest.approx(1.15 / 1.2)
    out = _grip_detail(st, CueCategory.BRAKE_LATER, "it")
    assert "58" not in out
    assert "resta carico da usare" not in out
    assert "dovrebbe prenderla" in out


def test_a_fast_corner_at_its_limit_is_at_the_limit():
    env = _envelope(_ref_slow_and_fast())
    assert env.at(200.0) == pytest.approx(2.0)
    assert _grip_state([_S(1.9)] * 20, env, 200.0).at_limit


def test_a_band_with_few_samples_uses_the_whole_lap():
    """10 campioni a 0,5 G fra 0 e 40 km/h: come limite di fascia farebbero dire
    «sei al limite» a chiunque passi di lì. Prende l'inviluppo del giro."""
    few = [(20.0 + i, 0.5) for i in range(10)]
    ref = _lap(few + [(130.0 + i * 0.5, 2.0) for i in range(200)])
    env = _envelope(ref)
    assert env.at(25.0) == pytest.approx(env.whole)
    assert env.whole == pytest.approx(2.0)
    assert not _grip_state([_S(0.5)] * 20, env, 25.0).at_limit


def test_the_band_edges_are_multiples_of_40():
    """[80,120) è una fascia sola: 119 km/h sta con gli 80, non con i 120."""
    env = _envelope(_ref_slow_and_fast())
    assert env.at(80.0) == pytest.approx(1.2)
    assert env.at(119.9) == pytest.approx(1.2)
    assert env.at(120.0) == pytest.approx(2.0)   # [120,160) ha i 130-159


def test_the_band_is_the_reference_speed_not_yours():
    """I campioni si mettono in fascia con la velocità del riferimento in quel
    punto: è il suo limite a quella velocità che si misura."""
    ref = _ref_slow_and_fast()
    mine = _lap([(250.0, 0.0)] * 400)            # io sempre a 250, ma conta lui
    env = _grip_envelope(mine, Reference(ref))
    assert env.at(90.0) == pytest.approx(1.2)


def test_without_a_speed_the_whole_lap_envelope_is_used():
    env = _envelope(_ref_slow_and_fast())
    assert env.at(None) == pytest.approx(2.0)
    assert not _grip_state([_S(1.15)] * 20, env).at_limit


def test_a_lap_without_g_data_still_says_nothing():
    ref = _lap([(100.0, 0.0)] * 200)
    env = _envelope(ref)
    assert _grip_state([_S(1.0)] * 20, env, 100.0).ratio == 0.0
