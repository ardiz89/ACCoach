"""La roadmap dei consigli: uno alla volta, e si ricordano.

La pagella elenca i difetti della sessione; qui diventano consigli che il pilota
*segue*. Le regole sono quelle del piano di allenamento (attenzione scarsa, un
numero che si controlla) ma il pezzo di roadmap e' il difetto, non la curva:
al massimo `MAX_ADVICE` proposte, **una sola attiva**, e quelle rifiutate o
raggiunte non tornano a farsi proporre.

Nulla qui inventa contenuto: i difetti, le curve e le medie vengono da
`defects.summarize`; il giudizio «raggiunto» riusa le soglie dell'app
(`SIGNIF_LOSS_MS`, `RECUR_FRAC`).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, replace

from .defects import COAST_MAIN_S, DefectSummary, LapDefects
from .thresholds import RECUR_FRAC, SIGNIF_LOSS_MS

MAX_ADVICE = 3
MAX_CORNERS = 3

# Stati di un consiglio.
PROPOSED, ACTIVE, REACHED, DROPPED, DECLINED = (
    "proposed", "active", "reached", "dropped", "declined")

# Sotto tre giri «raggiunto» vorrebbe dire scambiare un giro buono per un'abitudine.
_MIN_LAPS_TO_JUDGE = 3
# Si chiede di riprendersi meta' della perdita, non tutta: tutta e' perfezione.
_TAKE_BACK = 0.5


@dataclass
class AdviceCorner:
    index: int
    name: str
    apex_pos: float
    mean: float


@dataclass
class Advice:
    defect: str
    corners: list[AdviceCorner] = field(default_factory=list)
    baseline: float = 0.0
    target: float = 0.0
    status: str = PROPOSED
    accepted_utc: str = ""
    closed_utc: str = ""


@dataclass
class AdviceProgress:
    laps: int
    hits: int
    needed: int
    median: float
    done: bool


def _threshold(defect: str) -> float:
    """Soglia di «principale» nell'unita' del difetto (s per il coasting, ms il resto)."""
    return COAST_MAIN_S if defect == "coasting" else SIGNIF_LOSS_MS


def _target(defect: str, baseline: float) -> float:
    # Mai sotto la soglia dell'app: non si chiede meno di cio' che non coacheremmo.
    return max(_threshold(defect), baseline * _TAKE_BACK)


def propose_advice(summaries: list[DefectSummary], stored: list[Advice],
                   names: dict[int, str], apex: dict[int, float]) -> list[Advice]:
    actives = [a for a in stored if a.status == ACTIVE]
    if len(actives) > 1:
        raise ValueError("un solo consiglio alla volta puo' essere attivo")
    taken = {a.defect for a in actives} | {
        a.defect for a in stored if a.status in (DECLINED, REACHED)}
    out: list[Advice] = list(actives)
    for s in summaries:
        if len(out) >= MAX_ADVICE:
            break
        if not s.main or s.key in taken:
            continue
        floor = _threshold(s.key) / 2
        picked = [(i, m) for i, m in s.corners if m >= floor][:MAX_CORNERS]
        if picked:
            corners = [AdviceCorner(i, names.get(i, f"Corner {i + 1}"), apex.get(i, 0.0), m)
                       for i, m in picked]
            baseline = sum(m for _, m in picked)
        elif not s.corners:
            # Difetto senza ripartizione per curva (coasting, sollevamenti): si
            # misura sul totale del giro.
            corners, baseline = [], s.mean
        else:
            continue          # ripartizione c'e', ma nessuna curva pesa abbastanza
        out.append(Advice(defect=s.key, corners=corners, baseline=baseline,
                          target=_target(s.key, baseline), status=PROPOSED))
        taken.add(s.key)
    return out


def lap_value(a: Advice, ld: LapDefects) -> float:
    """Il difetto in un giro, sommato sulle curve del consiglio.

    Coasting e sollevamenti non hanno ripartizione per curva in `LapDefects`
    (`corners["coasting"]` non esiste): se il consiglio non ha curve si usa il
    totale del giro (`coast_s` o `ms[difetto]`).
    """
    if a.corners:
        per_corner = ld.corners.get(a.defect, {})
        return sum(per_corner.get(c.index, 0.0) for c in a.corners)
    return ld.coast_s if a.defect == "coasting" else ld.ms.get(a.defect, 0.0)


def measure_advice(a: Advice, laps_since: list[LapDefects]) -> AdviceProgress:
    vals = [lap_value(a, ld) for ld in laps_since]
    n = len(vals)
    hits = sum(1 for v in vals if v <= a.target)
    needed = max(2, math.ceil(RECUR_FRAC * n))
    return AdviceProgress(laps=n, hits=hits, needed=needed,
                          median=statistics.median(vals) if vals else 0.0,
                          done=n >= _MIN_LAPS_TO_JUDGE and hits >= needed)


def corner_at(apex_pos: float, corners):
    """La curva di `corners` il cui tratto contiene `apex_pos`, o ``None``.

    Un consiglio numera le curve sul riferimento con cui e' nato; chi lo legge
    con un altro metro (il focus del motore, la Pagella dopo un riferimento
    nuovo) ritrova la curva passando per la posizione dell'apex, che non cambia
    con la numerazione. Una sola regola per tutti. Un apex a 0.0 non e' una
    posizione (obiettivo del vecchio piano, migrato): nessuna curva.
    """
    if apex_pos <= 0.0:
        return None
    return next((c for c in corners if c.entry_pos <= apex_pos <= c.exit_pos), None)


def remap(a: Advice, corners, names: dict[int, str]) -> Advice:
    """Le curve del consiglio rinumerate sulle curve `corners` di adesso.

    Per posizione dell'apex (`corner_at`); senza posizione, per nome. Una curva
    che non si ritrova si scarta: meglio una curva in meno che la curva accanto.
    Le medie restano quelle di prima, le rimisura `rebase`.
    """
    out: list[AdviceCorner] = []
    for c in a.corners:
        hit = corner_at(c.apex_pos, corners)
        if hit is None and c.apex_pos <= 0.0 and c.name:
            i = next((i for i, n in names.items() if n == c.name), None)
            hit = next((k for k in corners if k.index == i), None)
        if hit is None or any(o.index == hit.index for o in out):
            continue
        out.append(replace(c, index=hit.index, apex_pos=hit.apex_pos,
                           name=names.get(hit.index) or c.name))
    return replace(a, corners=out)


def rebase(a: Advice, summary: DefectSummary) -> Advice:
    """Ricalcola baseline e target sulle stesse curve con lo storico attuale."""
    if a.corners:
        now = dict(summary.corners)
        corners = [replace(c, mean=now.get(c.index, 0.0)) for c in a.corners]
        baseline = sum(c.mean for c in corners)
    else:
        corners, baseline = [], summary.mean
    return replace(a, corners=corners, baseline=baseline,
                   target=_target(a.defect, baseline))
