"""BalanceDetector: live understeer / oversteer."""
from dataclasses import replace

from accoach.coaching.balance import BalanceDetector
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    speed_kmh=120.0,
)


def _snap(steer, yaw, speed=120.0, pos=0.3):
    return replace(_BASE, steer_angle=steer, yaw_rate=yaw, speed_kmh=speed,
                   lap_position=pos)


def _hold(det, s, frames=5, dt=0.05, start=0.0):
    out, now = [], start
    for _ in range(frames):
        out += det.update(s, now)
        now += dt
    return out, now


def test_understeer():
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.25, 0.05))
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_oversteer_opposite_lock():
    det = BalanceDetector()
    # Raw yaw_rate is signed opposite to steer in this game (see balance._YAW_SIGN);
    # oversteer = rear rotating the same RAW way as steer, caught with the wheel.
    out, _ = _hold(det, _snap(-0.15, -0.6))
    assert any(c.category is CueCategory.OVERSTEER for c in out)


def test_clean_corner_silent():
    det = BalanceDetector()
    # Clean corner: steer and RAW yaw_rate have opposite signs in this game.
    out, _ = _hold(det, _snap(0.25, -0.45), frames=10)
    assert out == []


def test_low_speed_silent():
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.30, 0.02, speed=20.0), frames=10)
    assert out == []


def test_debounce_single_frame():
    det = BalanceDetector()
    out = det.update(_snap(0.25, 0.05), 0.0)
    out += det.update(_snap(0.0, 0.4), 0.05)
    assert out == []


def test_fires_once_per_episode():
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.25, 0.05), frames=20)
    assert sum(c.category is CueCategory.UNDERSTEER for c in out) == 1


def _feed(det, frames, dt=0.05, start=0.0):
    """Feed a list of (steer, yaw) snapshots one frame apart."""
    out, now = [], start
    for steer, yaw in frames:
        out += det.update(_snap(steer, yaw), now)
        now += dt
    return out, now


def test_understeer_turnin_transient_is_silent():
    # Turn-in: the driver winds lock on (0.05 → 0.30) while yaw_rate still lags.
    # yaw/steer dips low here on ANY car — must not be called understeer.
    det = BalanceDetector()
    ramp = [(0.05, 0.02), (0.12, 0.04), (0.20, 0.06), (0.28, 0.08), (0.30, 0.10)]
    out, _ = _feed(det, ramp)
    assert not any(c.category is CueCategory.UNDERSTEER for c in out)


def test_understeer_fires_once_steering_settles():
    # Same brisk turn-in, but then the wheel settles and the car still won't
    # rotate (yaw stuck low) — that IS a push and should fire after the hold.
    det = BalanceDetector()
    ramp = [(0.05, 0.02), (0.15, 0.04), (0.25, 0.05), (0.30, 0.05)]
    settled = [(0.30, 0.05)] * 8            # wheel steady, car pushing
    out, _ = _feed(det, ramp + settled)
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_balanced_turnin_never_fires():
    # Wind lock on, then the car rotates as asked (yaw catches up to ratio ~1.9).
    # Clean corner => steer and RAW yaw have opposite signs in this game, so a
    # balanced right-hand turn-in has NEGATIVE yaw growing with the lock.
    det = BalanceDetector()
    ramp = [(0.05, -0.02), (0.15, -0.10), (0.25, -0.30), (0.30, -0.50)]
    settled = [(0.30, -0.57)] * 8          # yaw/steer ≈ 1.9, clean
    out, _ = _feed(det, ramp + settled)
    assert out == []


# --- il canale sterzo tosato ------------------------------------------------
#
# Il push è `|yaw| / |steer|`: col denominatore tosato al fondo scala il rapporto
# è al minimo per costruzione, e il coach accusa il pilota di una cosa che non ha
# fatto. Misurato sui 59 giri veri: tutti e 34 i cue di sottosterzo dell'archivio
# escono dai 15 giri col canale tosato, zero dai 44 puliti.

def _rail(det, top, visits=4, dt=0.05, start=0.0):
    """Guida che sbatte `visits` volte sullo stesso identico fondo scala."""
    now = start
    for _ in range(visits):
        for steer in (0.05, top * 0.6, top, top, top * 0.6, 0.05):
            det.update(_snap(steer, 0.9 * steer), now)
            now += dt
    return now


def test_a_channel_that_keeps_hitting_the_same_rail_stops_being_judged():
    det = BalanceDetector()
    now = _rail(det, 0.90)
    out, _ = _hold(det, _snap(0.25, 0.05), start=now)
    assert not any(c.category is CueCategory.UNDERSTEER for c in out)


def test_holding_the_wheel_still_through_one_long_corner_is_not_a_rail():
    """È il caso che ha rifiutato la mia prima regola, ed è guida vera: una curva
    lunga a sterzo fermo tiene un valore costante per molti campioni. Il
    discriminante non è il valore *tenuto*, è che alla sbarra **ci si torna**."""
    det = BalanceDetector()
    out, _ = _hold(det, _snap(0.25, 0.05), frames=40)
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_a_rising_signal_with_one_peak_is_not_a_rail():
    """Un massimo toccato una volta sola è ciò che fa un segnale continuo — e
    ciò che fanno tutti e 44 i giri puliti dell'archivio."""
    det = BalanceDetector()
    now = 0.0
    for steer in (0.10, 0.20, 0.32, 0.45, 0.32, 0.20, 0.10):
        det.update(_snap(steer, 0.9 * steer), now)
        now += 0.05
    out, _ = _hold(det, _snap(0.25, 0.05), frames=8, start=now)
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_a_rail_below_the_cornering_threshold_is_ignored():
    """Uno sterzo che sbatte a 0.05 rad non è un fondo scala: è un'auto che va
    dritta, e lì il rapporto non lo guardiamo comunque."""
    det = BalanceDetector()
    now = _rail(det, 0.06)
    out, _ = _hold(det, _snap(0.25, 0.05), start=now)
    assert any(c.category is CueCategory.UNDERSTEER for c in out)


def test_oversteer_still_works_on_a_clipped_channel():
    """Il sovrasterzo non divide per lo sterzo: guarda il **segno**. Zittirlo
    perché il canale è tosato toglierebbe il segnale più credibile che abbiamo,
    per un difetto che non lo riguarda."""
    det = BalanceDetector()
    now = _rail(det, 0.90)
    out, _ = _hold(det, _snap(-0.15, -0.6), start=now)
    assert any(c.category is CueCategory.OVERSTEER for c in out)


def test_the_rail_is_remembered_across_a_pit_visit():
    """`reset()` scatta a ogni sosta e a ogni frame non-LIVE, ma la tosatura è
    una proprietà della periferica: dimenticarla vorrebbe dire riscoprirla ogni
    volta, e nel frattempo riparlare."""
    det = BalanceDetector()
    now = _rail(det, 0.90)
    det.reset()
    out, _ = _hold(det, _snap(0.25, 0.05), start=now)
    assert not any(c.category is CueCategory.UNDERSTEER for c in out)
