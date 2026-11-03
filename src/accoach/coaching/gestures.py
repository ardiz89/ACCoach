"""Le cinque misure dei gesti del pilota in una curva.

Modulo puro: riceve i campioni gia' tagliati alla curva (da ``entry_pos`` a
``exit_pos``) e non sa niente di giri, riferimenti o frasi. La frase sta
altrove (Task 3).

Ogni misura che non si puo' fare e' ``None`` (rilascio e gas) oppure neutra
(ABS 0,0 s, sterzo 0 inversioni): un giro registrato prima dei canali ABS o G
ha i campi a 0 e non deve produrre frasi.

``compare`` dice quale gesto di un giro e' diverso dal riferimento piu' del
rumore. Le soglie sono misurate sulla copia dell'archivio (139 curve, 16 coppie
auto+pista, 144 giri validi e non sporchi): per ogni coppia le curve di
``detect_corners`` sul giro piu' veloce, per ogni curva la differenza assoluta
di ogni giro dalla mediana dei giri, poi il 75 percentile su tutte le curve.
Una curva con meno di 4 giri con un valore non conta.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..recording.lap import LapSample
from .thresholds import PEDAL_OFF

#: Gas «pieno»: la ripresa finisce quando arriva qui. Confermato sulla misura:
#: con 0,9 solo 5 curve su 139 (3,6%) non ci arrivano in nessun giro, e 91
#: valori su 1219 (7,5%) sono None. Nessun motivo di abbassarlo.
_THROTTLE_FULL = 0.9

#: Isteresi dello sterzo: una inversione vale se lo sterzo torna indietro di
#: almeno questo dall'ultimo estremo. Lo 0,02 di partenza contava rumore: sul
#: rettilineo di confronto (il tratto piu' lungo fra due curve, 144 giri) il
#: giro tipico faceva 5 inversioni (mediana, massimo 37). Le oscillazioni li'
#: arrivano a 0,028 al 75 percentile e 0,056 al 90. Provati 0,03 0,05 0,06
#: 0,07 0,08: 0,07 e' il primo con mediana 0 sul rettilineo (76 giri su 144 a
#: zero, 75 percentile 1). Nelle curve la mediana passa da 7 a 2 inversioni.
_STEER_HYST = 0.07

#: Finestra attorno alla velocita' minima in cui si legge la marcia. Un solo
#: campione «N» o «R» isolato non deve vincere sulla marcia vera.
_GEAR_WINDOW_S = 0.25


#: Rumore del rilascio del freno: 75 percentile di |giro - mediana della
#: curva|, misurato 0,399 s su 885 valori (mediana dello scarto 0,180 s).
RELEASE_NOISE_S = 0.399

#: Rumore della ripresa del gas fino a 0,9: misurato 0,438 s su 1033 valori
#: (mediana dello scarto 0,109 s).
PICKUP_NOISE_S = 0.438

#: Rumore dei secondi di ABS: misurato 0,377 s su 853 valori (mediana dello
#: scarto 0,135 s). Escluse le curve dove l'ABS e' 0 in tutti i giri: li'
#: misurano un'auto che non entra in ABS, non quanto varia il pilota, e
#: con i loro scarti a 0 la soglia scendeva a 0,298 s su 1119 valori.
#: Nessun buco di campioni piu' lungo di 3 volte l'intervallo mediano del
#: giro mentre l'ABS e' attivo (0 casi su 119 giri con ABS), quindi
#: ``_abs_s`` non tronca gli intervalli.
ABS_NOISE_S = 0.377

#: Rumore delle inversioni di sterzo con l'isteresi 0,07: misurato 1,0 su
#: 1119 valori (mediana dello scarto 0). Una inversione in piu' e' rumore.
STEER_NOISE = 1.0

#: La marcia non ha soglia (Decisione 2): diversa vale 1,0, cioe' meno di
#: qualunque altra misura sopra il suo rumore.
_GEAR_SCORE = 1.0


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


@dataclass(frozen=True, slots=True)
class GestureNote:
    """Il gesto di una curva diverso dal riferimento piu' del rumore."""
    kind: str               # "release" | "abs" | "gear" | "steer" | "pickup"
    live: float | str
    ref: float | str
    score: float            # differenza / rumore; marcia diversa = 1,0


#: Ordine della curva (Decisione 3): a parita' di rapporto vince il primo.
_ORDER = (
    ("release", "release_s", RELEASE_NOISE_S),
    ("abs", "abs_s", ABS_NOISE_S),
    ("gear", "apex_gear", None),
    ("steer", "steer_reversals", STEER_NOISE),
    ("pickup", "pickup_s", PICKUP_NOISE_S),
)


def compare(live: Gestures, ref: Gestures) -> GestureNote | None:
    """Il gesto con il rapporto piu' alto fra differenza e rumore, o None.

    Una misura None da una parte sola (tu freni, lui no) non si confronta.
    Una misura alla soglia e' ancora rumore: serve superarla. La marcia conta
    solo se e' un numero da tutte e due le parti, e solo se nient'altro
    supera il suo rumore.
    """
    best: GestureNote | None = None
    for kind, attr, noise in _ORDER:
        a, b = getattr(live, attr), getattr(ref, attr)
        if a is None or b is None:
            continue
        if noise is None:
            if not (a.isdigit() and b.isdigit()) or a == b:
                continue
            score = _GEAR_SCORE
        else:
            score = abs(a - b) / noise
            if score <= 1.0:
                continue
        # ">" stretto: a parita' resta il primo nell'ordine della curva.
        if best is None or score > best.score:
            best = GestureNote(kind=kind, live=a, ref=b, score=score)
    return best
