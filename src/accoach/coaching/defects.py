"""I difetti di guida: i reperti del debrief, contati per giro e per sessione.

Il debrief dice dove un giro ha perso tempo e perche', curva per curva. La
pagella chiede altro: *quale abitudine* ti costa di piu' sulla sessione. Qui i
reperti di curva si raggruppano per difetto (frena troppo presto, esci tardi
dal gas...) e si mediano sui giri validi.

La media conta gli zeri: un difetto che compare in un giro su due pesa la meta'
di uno che compare sempre. Contare solo i giri in cui c'e' lo farebbe sembrare
piu' grave di com'e'.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .cue import CueCategory
from .debrief import LapDebrief
from .thresholds import RECUR_FRAC, SIGNIF_LOSS_MS

DEFECTS: tuple[str, ...] = ("brake_early", "brake_late", "over_brake",
                            "throttle_late", "min_speed", "lift", "coasting")

# `lift` (dalle note del giro) e `coasting` (dal grip) non nascono da una
# categoria di curva, quindi non hanno voce qui.
CATEGORY_OF: dict[str, CueCategory] = {
    "brake_early": CueCategory.BRAKE_LATER,
    "brake_late": CueCategory.BRAKE_EARLIER,
    "over_brake": CueCategory.LESS_BRAKE,
    "throttle_late": CueCategory.MORE_THROTTLE,
    "min_speed": CueCategory.CARRY_SPEED,
}
_KEY_OF = {c: k for k, c in CATEGORY_OF.items()}
_MS_KEYS = tuple(k for k in DEFECTS if k != "coasting")

# Secondi di folata per giro oltre i quali il coasting conta come difetto
# «principale». Misurata il 2026-10-21 su 145 giri validi dell'archivio del
# pilota (16 combo auto/pista, ognuno contro il suo giro pulito piu' veloce):
# il coasting compare solo in 14 giri su 145 (10%), quindi il 75 percentile
# *di tutti* i giri e' 0.0 e non sarebbe una soglia. Si usa il 75 percentile dei
# giri in cui c'e' (0.1-0.87 s, mediana 0.2): 0.43 -> 0.4 s. Soglia alta di
# proposito, un difetto che non scatta mai e' meglio di uno che scatta ovunque.
COAST_MAIN_S: float = 0.4

# Quanti difetti la pagella chiama «principali»: oltre, nessuno e' piu' principale.
_MAX_MAIN = 4


@dataclass
class LapDefects:
    ms: dict[str, float] = field(default_factory=dict)
    corners: dict[str, dict[int, float]] = field(default_factory=dict)
    # Solo sulle curve con una perdita (la stessa funzione della misura di
    # COAST_MAIN_S, quindi soglia e valori concordano).
    coast_s: float = 0.0
    total_gap_ms: int = 0
    # Perdita totale per curva, **tutte** le categorie (TIME_LOSS compreso):
    # «dove sbagli di piu'» non deve dipendere da come l'abbiamo etichettata.
    corner_loss: dict[int, float] = field(default_factory=dict)


@dataclass
class DefectSummary:
    key: str
    mean: float
    unit: str                      # "ms" | "s"
    laps_with: int
    laps: int
    corners: list[tuple[int, float]] = field(default_factory=list)
    main: bool = False


def lap_defects(d: LapDebrief) -> LapDefects:
    out = LapDefects(ms={k: 0.0 for k in _MS_KEYS},
                     corners={k: {} for k in _MS_KEYS},
                     total_gap_ms=d.total_gap_ms)
    for loss in d.losses:
        out.corner_loss[loss.index] = out.corner_loss.get(loss.index, 0.0) + loss.lost_ms
        key = _KEY_OF.get(loss.category)
        if key is not None:
            out.ms[key] += loss.lost_ms
            c = out.corners[key]
            c[loss.index] = c.get(loss.index, 0.0) + loss.lost_ms
        # Somma sulle curve: e' il tempo di folata del giro, non il peggiore.
        out.coast_s += loss.grip.coast_s
    out.ms["lift"] = sum(n.lost_ms for n in d.notes if n.kind == "lift")
    return out


def summarize(laps: list[LapDefects]) -> list[DefectSummary]:
    n = len(laps)
    if n == 0:
        return []
    need = math.ceil(RECUR_FRAC * n)
    found: list[DefectSummary] = []
    for key in DEFECTS:
        if key == "coasting":
            vals = [ld.coast_s for ld in laps]
            unit, thr = "s", COAST_MAIN_S
        else:
            vals = [ld.ms.get(key, 0.0) for ld in laps]
            unit, thr = "ms", SIGNIF_LOSS_MS
        mean = sum(vals) / n
        if mean <= 0:
            continue
        per_corner: dict[int, float] = {}
        for ld in laps:
            for idx, v in ld.corners.get(key, {}).items():
                per_corner[idx] = per_corner.get(idx, 0.0) + v
        corners = sorted(((i, v / n) for i, v in per_corner.items()),
                         key=lambda x: x[1], reverse=True)
        found.append(DefectSummary(
            key=key, mean=mean, unit=unit,
            laps_with=sum(1 for v in vals if v > 0), laps=n, corners=corners,
            main=sum(1 for v in vals if v > thr) >= need))
    # Prima i difetti in ms per media decrescente, poi il coasting (altra unita').
    found.sort(key=lambda s: (s.unit == "s", -s.mean))
    kept = 0
    for s in found:
        if s.main:
            kept += 1
            s.main = kept <= _MAX_MAIN
    return found


def worst_corners(laps: list[LapDefects], n: int = 3) -> list[tuple[int, float]]:
    """Le curve che costano di piu' per giro, sommando tutte le categorie."""
    if not laps:
        return []
    tot: dict[int, float] = {}
    for ld in laps:
        for idx, v in ld.corner_loss.items():
            tot[idx] = tot.get(idx, 0.0) + v
    ranked = sorted(((i, v / len(laps)) for i, v in tot.items()),
                    key=lambda x: x[1], reverse=True)
    return ranked[:n]
