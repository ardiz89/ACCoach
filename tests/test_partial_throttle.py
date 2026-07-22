"""Gas a metà tenuto in percorrenza.

Preso da come parlano i coach umani veri, non da un'idea nostra: a un pilota
fermo a un plateau viene detto che tiene l'1-90% di gas troppo a lungo in molte
curve, che così **aggiunge sottosterzo invece di accelerare l'auto**, e che la
cura è essere paziente e poi impegnarsi — se serve fai coasting *prima* del gas,
ma quando apri, apri tutto.

Il difetto è **tenere**, non modulare. Riaprire progressivamente attraversa
questa stessa banda a ogni uscita di curva ed è esattamente ciò che vogliamo dal
pilota: segnalarlo insegnerebbe il contrario della lezione. Da qui la terza
condizione, che è quella che tiene onesto il rilevatore.
"""
from dataclasses import replace

from accoach.coaching.braking import (
    _PART_THROTTLE_HOLD_S,
    _PART_THROTTLE_RAMP,
    BrakingDetector,
)
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import ACStatus, TelemetrySnapshot

_LIVE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, speed_kmh=160.0, lap_position=0.3,
)

_HZ = 20.0
_DT = 1.0 / _HZ


def _drive(frames) -> list:
    """Feed (throttle, steer) pairs at 20 Hz; return the cue categories emitted."""
    det = BrakingDetector()
    out = []
    now = 0.0
    for throttle, steer in frames:
        s = replace(_LIVE, throttle=throttle, steer_angle=steer, brake=0.0)
        out += [c.category for c in det.update(s, now)]
        now += _DT
    return out


def _held(throttle: float, seconds: float, steer: float = 0.25):
    return [(throttle, steer)] * int(seconds * _HZ)


def test_holding_half_throttle_through_a_corner_is_called_out():
    assert CueCategory.PARTIAL_THROTTLE in _drive(
        _held(0.5, _PART_THROTTLE_HOLD_S + 1.0))


def test_rolling_on_progressively_is_not():
    """La tecnica corretta attraversa la banda a ogni uscita: guai a segnalarla."""
    n = int((_PART_THROTTLE_HOLD_S + 1.0) * _HZ)
    ramp = [(0.15 + 0.85 * i / n, 0.25) for i in range(n)]
    assert CueCategory.PARTIAL_THROTTLE not in _drive(ramp)


def test_a_brief_touch_of_partial_throttle_is_not():
    assert CueCategory.PARTIAL_THROTTLE not in _drive(_held(0.5, 0.4))


def test_full_throttle_is_not():
    assert CueCategory.PARTIAL_THROTTLE not in _drive(_held(1.0, 3.0))


def test_lifting_on_a_straight_is_somebody_elses_cue():
    """Gas a metà in rettilineo è un sollevamento, non questo difetto."""
    assert CueCategory.PARTIAL_THROTTLE not in _drive(_held(0.5, 3.0, steer=0.0))


def test_it_does_not_fire_while_braking():
    """Freno e gas insieme è trail braking o left-foot, non gas parcheggiato."""
    det = BrakingDetector()
    now = 0.0
    out = []
    for _ in range(int(3.0 * _HZ)):
        s = replace(_LIVE, throttle=0.5, steer_angle=0.25, brake=0.4)
        out += [c.category for c in det.update(s, now)]
        now += _DT
    assert CueCategory.PARTIAL_THROTTLE not in out


def test_it_does_not_fire_at_parade_speed():
    det = BrakingDetector()
    now = 0.0
    out = []
    for _ in range(int(3.0 * _HZ)):
        s = replace(_LIVE, throttle=0.5, steer_angle=0.25, speed_kmh=40.0)
        out += [c.category for c in det.update(s, now)]
        now += _DT
    assert CueCategory.PARTIAL_THROTTLE not in out


def test_a_slow_creep_still_counts_as_holding():
    """Sotto la soglia di rampa è un plateau, non una riapertura."""
    n = int((_PART_THROTTLE_HOLD_S + 1.0) * _HZ)
    creep = [(0.5 + (_PART_THROTTLE_RAMP * 0.5) * i / n, 0.25) for i in range(n)]
    assert CueCategory.PARTIAL_THROTTLE in _drive(creep)


def test_it_says_what_to_do_not_just_what_is_wrong():
    det = BrakingDetector()
    now = 0.0
    msgs = []
    for _ in range(int((_PART_THROTTLE_HOLD_S + 1.0) * _HZ)):
        s = replace(_LIVE, throttle=0.5, steer_angle=0.25, brake=0.0)
        msgs += [c.message for c in det.update(s, now)
                 if c.category is CueCategory.PARTIAL_THROTTLE]
        now += _DT
    assert msgs and "apri" in msgs[0].lower()
