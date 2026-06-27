"""Tyre-pressure advisor — judge hot pressures against the target window.

This is the first piece of *static setup* coaching, as opposed to driving
technique. Hot tyre pressure is the highest-leverage and most measurable setup
number: a GT3 has a narrow optimal hot-pressure window, and being a psi out of it
quietly costs grip everywhere on the lap. Crucially we can judge it from
telemetry alone — the game reports live pressures — so unlike camber or springs
there's no guesswork.

How it works
------------
While the car is on track at pace and the tyres are warmed up, we average each
tyre's hot pressure over the lap. At the start/finish line we compare the front
and rear axle averages to a target window and, if an axle is out, say by how much
to change the **cold** pressure (cold and hot move roughly one-for-one, so the
psi delta is also the cold-set correction). It's spoken once and then goes quiet
for several laps — pressure only changes at a pit stop, so there's no point
repeating it every lap.

Scope / calibration
-------------------
The default target (``target_psi`` / ``tol_psi``) is the dry **ACC GT3** window
(~27.5 psi). Other categories and wet running want different numbers; the target
is a constructor parameter so it can be set per car/condition later. Pressures
are only sampled once the tyres are warm (``warmup_temp_c``) so a cold out-lap
never triggers bad advice, and implausible readings are ignored outright.
"""

from __future__ import annotations

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from .cue import Cue, CueCategory

# Dry ACC GT3 hot-pressure target and the half-width of the "fine" band: an axle
# average inside [target - tol, target + tol] gets no comment.
_DEFAULT_TARGET_PSI = 27.5
_DEFAULT_TOL_PSI = 0.7

# Don't trust pressures until the tyres are at operating temp. A GT3 slick works
# around ~80 C core; below that the pressure reads low and would trigger a bogus
# "raise pressure" call. Live data (2026-06-27, BMW M4 GT3 @ Imola) confirmed it:
# at ~68 C the tyres read 22-25 psi, but at ~80 C the same tyres read ~26 psi —
# so a 50 C gate let under-temp laps advise "+ pressure" wrongly. Gate at 75 C.
_DEFAULT_WARMUP_TEMP_C = 75.0

# Sample only when genuinely on track at pace (filters pit lane, stops, crawl).
_MIN_SPEED_KMH = 60.0
# A pressure reading outside this band is garbage (wrong page / disconnected).
_PSI_PLAUSIBLE = (10.0, 45.0)
# Need at least this many sampled frames in a lap to average meaningfully.
_MIN_SAMPLES = 30

# Pressure changes only in the pits, so re-advise rarely.
_COOLDOWN_LAPS = 5
_MIN_LAP_SPAN = 0.7
_PRIORITY = 240.0   # informational; below the in-the-moment cues and aid advisor


class PressureAdvisor:
    """Stateful: fed (snapshot, now) each frame; yields tyre-pressure advice."""

    def __init__(
        self,
        target_psi: float = _DEFAULT_TARGET_PSI,
        tol_psi: float = _DEFAULT_TOL_PSI,
        warmup_temp_c: float = _DEFAULT_WARMUP_TEMP_C,
    ) -> None:
        self.target_psi = target_psi
        self.tol_psi = tol_psi
        self.warmup_temp_c = warmup_temp_c
        self._reset_lap()
        self._cooldown = 0

    def reset(self) -> None:
        self._reset_lap()
        self._cooldown = 0

    def update(self, s: TelemetrySnapshot, now: float) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit:
            self._reset_lap()
            return []

        pos = s.lap_position
        cues = self._maybe_advise(pos)

        if s.speed_kmh >= _MIN_SPEED_KMH and self._plausible(s.tyre_pressure):
            for i in range(4):
                self._psi_sum[i] += s.tyre_pressure[i]
                self._temp_sum[i] += s.tyre_core_temp[i]
            self._samples += 1

        self._pos_min = min(self._pos_min, pos)
        self._pos_max = max(self._pos_max, pos)
        self._prev_pos = pos
        return cues

    # --- lap boundary -----------------------------------------------------
    def _maybe_advise(self, pos: float) -> list[Cue]:
        crossed = self._prev_pos > 0.7 and pos < 0.3
        if not crossed:
            return []

        cue = self._evaluate()
        cues = [cue] if cue is not None else []
        if self._cooldown > 0:
            self._cooldown -= 1
        self._reset_lap()
        return cues

    def _evaluate(self) -> Cue | None:
        full_lap = (self._pos_max - self._pos_min) >= _MIN_LAP_SPAN
        if not full_lap or self._samples < _MIN_SAMPLES or self._cooldown > 0:
            return None

        psi = [self._psi_sum[i] / self._samples for i in range(4)]
        temp = [self._temp_sum[i] / self._samples for i in range(4)]
        if sum(temp) / 4 < self.warmup_temp_c:   # tyres never came up to temp
            return None

        front = (psi[0] + psi[1]) / 2
        rear = (psi[2] + psi[3]) / 2
        f_dev = self._deviation(front)
        r_dev = self._deviation(rear)
        if f_dev == 0.0 and r_dev == 0.0:
            return None

        # Comment on the axle furthest out of the window.
        if abs(f_dev) >= abs(r_dev):
            return self._advice("anteriori", front, f_dev)
        return self._advice("posteriori", rear, r_dev)

    def _deviation(self, axle_psi: float) -> float:
        """Signed psi outside the window; 0 when inside it."""
        if axle_psi > self.target_psi + self.tol_psi:
            return axle_psi - (self.target_psi + self.tol_psi)
        if axle_psi < self.target_psi - self.tol_psi:
            return axle_psi - (self.target_psi - self.tol_psi)
        return 0.0

    def _advice(self, axle: str, axle_psi: float, dev: float) -> Cue:
        # Cold and hot pressure move ~one-for-one, so the correction back to the
        # target centre is the cold-set change to call out.
        change = abs(axle_psi - self.target_psi)
        if dev > 0:
            msg = (f"Gomme {axle} a {axle_psi:.1f} psi, troppo alte: "
                   f"cala circa {change:.1f} psi a freddo.")
        else:
            msg = (f"Gomme {axle} a {axle_psi:.1f} psi, troppo basse: "
                   f"alza circa {change:.1f} psi a freddo.")
        self._cooldown = _COOLDOWN_LAPS
        return Cue(category=CueCategory.TYRE_PRESSURE, message=msg,
                   priority=_PRIORITY, segment=0, pos=0.0)

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _plausible(pressures: tuple[float, float, float, float]) -> bool:
        lo, hi = _PSI_PLAUSIBLE
        return all(lo <= p <= hi for p in pressures)

    def _reset_lap(self) -> None:
        self._psi_sum = [0.0, 0.0, 0.0, 0.0]
        self._temp_sum = [0.0, 0.0, 0.0, 0.0]
        self._samples = 0
        self._pos_min = 1.0
        self._pos_max = 0.0
        self._prev_pos = -1.0
