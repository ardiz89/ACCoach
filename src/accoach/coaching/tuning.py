"""Per-car-class tuning for the coaching detectors.

A few detector thresholds are genuinely class-dependent — a stiff, high-power
Formula car tolerates far more rear slip before it's real wheelspin than a road
car, and a class's "slow corner" is faster the more grip it makes. Front-lock
ratio and yaw sign held cross-class in the 3-class live audit; the understeer
ratio did **not**, and is parameterised here since 2026-07-20 (see
``yaw_baseline``).

Values from the 3-class cue-audit (2026-06-27: GT3 @ Monza, Formula SF25 @
Nürburgring, road M3 E92 @ Suzuka, on AC):

* ``spin_ratio`` — rear physical slip ratio counting as wheelspin. The single-car
  GT3 calibration had landed on 0.10; the broader study found that clipped the
  traction ceiling on stiffer classes, so it rises with class (Road 0.12, GT3
  0.13, Formula 0.15). GT3 0.13 still catches the hardest real GT3 spin (~0.138).
* ``speed_split_kmh`` — the low/high corner-speed band for the diagnosis taxonomy.
  A higher-grip class corners faster, so its "slow corner" boundary sits higher.
* ``yaw_baseline`` — the yaw/steer ratio a car of this class normally shows while
  cornering, measured over recorded laps (Formula SF25 @ Nürburgring 2.50 over
  1737 cornering samples; GT3 M4/720S @ Imola 1.93/1.98; road M3 E92 @ Suzuka
  1.95). Understeer is then "well under your own class's normal", not a fixed
  number — see ``UNDERSTEER_FRAC``.
* ``trail_brake_cue`` — whether to coach trail braking at all. Bleeding the brake
  to the apex buys front load a downforce car needs; on a low-downforce road car,
  stopping in a straight line and *then* turning is correct technique, and lifting
  late can snap it. The road audit (M3 E92 @ Suzuka) fired 6 trail-brake cues that
  the driver called false, and no true ones — so the class gets silence rather than
  a relaxed threshold, since nothing in the data says where a relaxed one would go.

⚠ These are best-known values pending a fresh live re-validation per class; the
table is the single place to retune them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..engineer import CarClass, classify


@dataclass(frozen=True, slots=True)
class ClassTuning:
    """The class-dependent detector thresholds."""

    spin_ratio: float          # rear slip ratio = wheelspin (events + diagnosis)
    speed_split_kmh: float     # low/high corner-speed band (diagnosis taxonomy)
    trail_brake_cue: bool      # coach trail braking for this class at all (braking)
    yaw_baseline: float        # normal yaw/steer while cornering (balance)


_TUNING: dict[CarClass, ClassTuning] = {
    CarClass.ROAD:    ClassTuning(spin_ratio=0.12, speed_split_kmh=100.0,
                                  trail_brake_cue=False, yaw_baseline=1.95),
    CarClass.GT3:     ClassTuning(spin_ratio=0.13, speed_split_kmh=120.0,
                                  trail_brake_cue=True, yaw_baseline=1.95),
    CarClass.FORMULA: ClassTuning(spin_ratio=0.15, speed_split_kmh=140.0,
                                  trail_brake_cue=True, yaw_baseline=2.50),
}

# Understeer is judged as a fraction of the class baseline, not as an absolute
# yaw/steer number. An absolute 0.9 asked a Formula car to fall to 36% of its
# normal rotation before it counted as pushing, while a GT3 only had to reach
# 46% — the same number meaning different things on cars that rotate differently.
# 0.45 puts the trigger on the worst ~5% of cornering samples in every class,
# which is where the absolute threshold already sat for GT3 and road cars: this
# changes Formula and leaves the classes that were working where they were.
UNDERSTEER_FRAC = 0.45

# Unknown / empty car → GT3: the most common class and the middle of the range,
# so a misclassification errs small in either direction.
DEFAULT_TUNING: ClassTuning = _TUNING[CarClass.GT3]


def tuning_for_class(car_class: CarClass) -> ClassTuning:
    return _TUNING.get(car_class, DEFAULT_TUNING)


def tuning_for_car(car_model: str | None) -> ClassTuning:
    """Resolve tuning from a car model id (empty/unknown → :data:`DEFAULT_TUNING`)."""
    if not car_model:
        return DEFAULT_TUNING
    return tuning_for_class(classify(car_model))
