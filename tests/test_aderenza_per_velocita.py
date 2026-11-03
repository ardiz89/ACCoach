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


# --- per campione: ogni G contro il limite alla velocità del riferimento lì ---

def test_heavy_high_speed_braking_does_not_put_a_slow_corner_at_the_limit():
    """La staccata da 230 km/h e l'apex a 90: con la fascia della mediana (90)
    il 1,6 G della frenata si misurava contro 1,2 e faceva «al limite» da
    solo (59 curve dell'archivio, 26 col picco in una fascia più alta). Ogni
    campione si misura contro il limite alla sua velocità: 1,6 su 2,0 e 0,9
    su 1,2, cioè l'80 % e il 75 %. Non al limite, e la staccata non è satura."""
    env = _envelope(_ref_slow_and_fast())
    inside = [_S(1.6, t_ms=i * 50) for i in range(10)] + \
             [_S(0.9, brake=0.0, t_ms=500 + i * 50) for i in range(30)]
    speeds = [230.0] * 10 + [90.0] * 30
    st = _grip_state(inside, env, speeds)
    assert st.ratio == pytest.approx(0.8)
    assert not st.at_limit
    assert not st.saturated_early


def test_braking_at_the_limit_of_its_own_speed_is_still_saturated():
    """L'altra metà della regola: 1,95 G a 230 km/h è il 97,5 % del 2,0 di
    quella fascia, e la staccata resta satura anche con l'apex lento."""
    env = _envelope(_ref_slow_and_fast())
    inside = [_S(1.95, t_ms=i * 50) for i in range(10)] + \
             [_S(0.9, brake=0.0, t_ms=500 + i * 50) for i in range(30)]
    st = _grip_state(inside, env, [230.0] * 10 + [90.0] * 30)
    assert st.at_limit and st.saturated_early


def test_a_missing_reference_speed_falls_back_to_the_whole_lap():
    env = _envelope(_ref_slow_and_fast())
    st = _grip_state([_S(1.15)] * 20, env, [None] * 20)
    assert st.ratio == pytest.approx(1.15 / 2.0)


# --- nel debrief: la fascia è quella del riferimento -------------------------

def _g_by_ref_band(spd):
    """G del riferimento per fascia: 1,0 fra 120 e 160, 2,0 fra 160 e 200."""
    band = int(spd // 40)
    return {3: 1.0, 4: 2.0}.get(band, 1.5)


def test_the_debrief_picks_the_band_of_the_reference_speed():
    """Il riferimento fa la curva 0 a una mediana di circa 187 km/h (fascia
    160-200, limite 2,0); tu, 40 km/h più piano, a circa 147 (fascia 120-160,
    limite 1,0). In ogni punto tieni il 95 % del limite del riferimento a
    quella velocità: il tuo grip vale 95 %. Con la tua velocità ogni punto
    finirebbe in una fascia più bassa, e il numero tagliato a 100 %. Chi va
    più piano non deve essere misurato contro un limite più basso."""
    import statistics
    from dataclasses import replace

    import synth
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.track import detect_corners

    ref_lap = synth.build_lap(n=2001)
    ref_lap.samples[:] = [replace(s, g_lat=_g_by_ref_band(s.speed_kmh), g_long=0.0)
                          for s in ref_lap.samples]
    mine = synth.build_lap(slow_corner=0, amt=40, n=2001)
    ref = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    c0 = corners[0]
    env = _grip_envelope(mine, ref)      # dalle posizioni, non dalle G di mine
    mine.samples[:] = [replace(
        s, g_lat=0.95 * env.at(ref.point_at(s.pos).speed_kmh)
        if c0.entry_pos <= s.pos <= c0.exit_pos else 0.5, g_long=0.0)
        for s in mine.samples]

    inside = [s for s in mine.samples if c0.entry_pos <= s.pos <= c0.exit_pos]
    ref_speeds = [ref.point_at(s.pos).speed_kmh for s in inside]
    ref_med = statistics.median(ref_speeds)
    my_med = statistics.median(s.speed_kmh for s in inside)
    # La premessa del test: le due mediane cadono in fasce diverse, entrambe vere.
    assert int(ref_med // 40) == 4 and int(my_med // 40) == 3
    assert env.at(ref_med) == pytest.approx(2.0)
    assert env.at(my_med) == pytest.approx(1.0)
    # Contro la tua velocità sarebbe «al limite», tagliato.
    assert _grip_state(inside, env, [s.speed_kmh for s in inside]).ratio == 1.0

    deb = build_lap_debrief(mine, ref, corners, "it")
    loss = next(l for l in deb.losses if l.index == c0.index)
    assert loss.grip.ratio == pytest.approx(0.95)
