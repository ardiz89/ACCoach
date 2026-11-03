"""Le cinque misure dei gesti del pilota in una curva.

Modulo puro: riceve i campioni gia' tagliati alla curva (da ``entry_pos`` a
``exit_pos``) e non sa niente di giri, riferimenti o frasi. Le soglie di rumore
e la frase stanno altrove (Task 2 e seguenti).

Ogni misura che non si puo' fare e' ``None`` (rilascio e gas) oppure neutra
(ABS 0,0 s, sterzo 0 inversioni): un giro registrato prima dei canali ABS o G
ha i campi a 0 e non deve produrre frasi.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..recording.lap import LapSample
from .thresholds import PEDAL_OFF

#: Gas «pieno»: la ripresa finisce quando arriva qui. Valore di partenza, il
#: Task 2 lo conferma o lo corregge sulla misura.
_THROTTLE_FULL = 0.9

#: Isteresi dello sterzo: una inversione vale se lo sterzo torna indietro di
#: almeno questo dall'ultimo estremo. Valore di partenza, come sopra.
_STEER_HYST = 0.02

#: Finestra attorno alla velocita' minima in cui si legge la marcia. Un solo
#: campione «N» o «R» isolato non deve vincere sulla marcia vera.
_GEAR_WINDOW_S = 0.25


@dataclass(frozen=True, slots=True)
class Gestures:
    release_s: float | None
    pickup_s: float | None
    apex_gear: str | None
    abs_s: float
    steer_reversals: int


def _release_s(samples: list[LapSample]) -> float | None:
    start = next((i for i, s in enumerate(samples) if s.brake > PEDAL_OFF), None)
    if start is None:
        return None
    # Primo tratto di frenata: finche' il freno resta sopra la soglia.
    end = start
    while end + 1 < len(samples) and samples[end + 1].brake > PEDAL_OFF:
        end += 1
    peak = max(range(start, end + 1), key=lambda i: (samples[i].brake, -i))
    for s in samples[peak + 1:]:
        if s.brake < PEDAL_OFF:
            return (s.t_ms - samples[peak].t_ms) / 1000.0
    return None


def _pickup_s(samples: list[LapSample], apex: int) -> float | None:
    after = samples[apex + 1:]
    first = next((i for i, s in enumerate(after) if s.throttle > PEDAL_OFF), None)
    if first is None:
        return None
    for s in after[first:]:
        if s.throttle >= _THROTTLE_FULL:
            return (s.t_ms - after[first].t_ms) / 1000.0
    return None


def _apex_gear(samples: list[LapSample], apex: int) -> str | None:
    t0 = samples[apex].t_ms
    near = [s.gear for s in samples
            if s.gear and abs(s.t_ms - t0) <= _GEAR_WINDOW_S * 1000.0]
    if not near:
        return None
    counts = Counter(near)
    top = max(counts.values())
    # A parita' vince la marcia al campione di minima, poi la prima vista.
    if counts.get(samples[apex].gear) == top:
        return samples[apex].gear
    return next(g for g in near if counts[g] == top)


def _abs_s(samples: list[LapSample]) -> float:
    total = 0
    for a, b in zip(samples, samples[1:]):
        if a.abs_active > 0 and b.t_ms > a.t_ms:
            total += b.t_ms - a.t_ms
    return total / 1000.0


def _steer_reversals(samples: list[LapSample]) -> int:
    count = 0
    direction = 0          # +1 sale, -1 scende, 0 non ancora deciso
    extreme = None
    for s in samples:
        v = s.steer_angle
        if extreme is None:
            extreme = v
        elif direction == 0:
            if abs(v - extreme) >= _STEER_HYST:
                direction = 1 if v > extreme else -1
                extreme = v
        elif direction > 0:
            if v > extreme:
                extreme = v
            elif extreme - v >= _STEER_HYST:
                count += 1
                direction, extreme = -1, v
        else:
            if v < extreme:
                extreme = v
            elif v - extreme >= _STEER_HYST:
                count += 1
                direction, extreme = 1, v
    return count


def measure(samples: list[LapSample]) -> Gestures:
    """Le cinque misure su campioni gia' tagliati alla curva."""
    if not samples:
        return Gestures(None, None, None, 0.0, 0)
    apex = min(range(len(samples)), key=lambda i: (samples[i].speed_kmh, i))
    return Gestures(
        release_s=_release_s(samples),
        pickup_s=_pickup_s(samples, apex),
        apex_gear=_apex_gear(samples, apex),
        abs_s=_abs_s(samples),
        steer_reversals=_steer_reversals(samples),
    )
