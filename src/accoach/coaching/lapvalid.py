"""Il giro invalidato, detto a voce: che e' successo e perche'.

Il gioco dice solo che il giro non conta, non il motivo. Il motivo si legge da
dove sei rispetto alla linea del riferimento, nel momento in cui il giro cade:
piu' fuori o piu' dentro. Misurato il 30/10 su 47 giri invalidati dell'archivio:
in 32 su 43 uscite in curva lo scarto e' netto (mediana 3,7 m, contro 1,0 m dei
giri puliti nello stesso punto), 26 fuori e 6 dentro. La velocita' non entra:
solo 3 su 43 erano piu' veloci del riferimento, e 25 gia' piu' lente, quindi
«sei arrivato troppo forte» sarebbe un'invenzione.

Una chicane non ha un dentro solo, e senza riferimento non c'e' linea: la frase
resta sui limiti di pista, che e' tutto quello che si sa.
"""

from __future__ import annotations

from ..recording.recorder import _TYRES_OUT_DIRTY
from ..telemetry.snapshot import ACStatus, TelemetrySnapshot
from ..trajectory import LinePoint, _turn_sign, has_line, lateral_offsets, line_points
from .cue import Cue, CueCategory

_SIDE_M = 1.5               # sopra il rumore dei giri puliti (mediana 1,0 m)
_MAX_WAIT_S = 4.0           # senza un'uscita di curva non si aspetta oltre
_PRIORITY = 280.0           # sotto la benzina, sopra i consigli


def lap_lost_reason(side_m: float | None) -> str:
    """«wide», «cut» o «limits» dallo scarto col segno (dentro positivo)."""
    if side_m is None or abs(side_m) < _SIDE_M:
        return "limits"
    return "cut" if side_m > 0 else "wide"


class LapValidityCoach:
    """Una frase per giro, a curva finita: dirla in staccata distrae e basta."""

    def __init__(self) -> None:
        self._ref = None
        self._ref_points: list[LinePoint] = []
        self._last_error: tuple[int, str] | None = None
        self._prev_xz: tuple[float, float] | None = None
        # (curva, motivo, dove e' caduto, dove finisce la curva, quando)
        self._lost: tuple[int | None, str, float, float, float] | None = None
        self.new_lap()

    def reset(self) -> None:
        self.__init__()

    def new_lap(self) -> None:
        # Il flag torna su al traguardo, ma non per forza nel fotogramma del
        # passaggio: conta solo una caduta dopo averlo visto alto in questo giro.
        self._seen_valid = False
        self._fired = False

    def _lost_now(self, s: TelemetrySnapshot) -> bool:
        if s.lap_valid is None:     # AC: i limiti si contano dalle ruote fuori
            return s.tyres_out >= _TYRES_OUT_DIRTY
        if s.lap_valid:
            self._seen_valid = True
            return False
        return self._seen_valid

    def _side(self, s: TelemetrySnapshot, reference, corner) -> float | None:
        """Metri rispetto al riferimento, dentro positivo; None se non si sa."""
        if corner is None or corner.kind == "chicane":
            return None
        sign = _turn_sign(corner.direction)
        if not sign or reference is None or self._prev_xz is None:
            return None
        if s.car_x == 0.0 and s.car_z == 0.0:
            return None
        if reference is not self._ref:
            self._ref = reference
            self._ref_points = line_points(reference)
        if not has_line(self._ref_points):
            return None
        here = [LinePoint(pos=s.lap_position, x=x, z=z, speed_kmh=s.speed_kmh, brake=0.0)
                for x, z in (self._prev_xz, (s.car_x, s.car_z))]
        offsets = lateral_offsets(here, self._ref_points)
        return offsets[-1] * sign if offsets else None

    def update(self, s: TelemetrySnapshot, flying: bool, now: float,
               corners, reference) -> list[Cue]:
        if not (s.connected and s.status == ACStatus.LIVE) or s.in_pit or s.in_pit_lane:
            self._prev_xz = None
            self._lost = None
            return []
        cues: list[Cue] = []
        if flying and not self._fired and self._lost is None and self._lost_now(s):
            corner = next((c for c in corners
                           if c.entry_pos <= s.lap_position <= c.exit_pos), None)
            reason = lap_lost_reason(self._side(s, reference, corner))
            self._lost = (None if corner is None else corner.index, reason,
                          s.lap_position,
                          corner.exit_pos if corner is not None else s.lap_position,
                          now)
        if self._lost is not None:
            index, reason, pos, exit_pos, at = self._lost
            if s.lap_position > exit_pos or now - at >= _MAX_WAIT_S:
                self._fired = True
                self._lost = None
                again = index is not None and self._last_error == (index, reason)
                self._last_error = (index, reason) if index is not None else None
                cues.append(Cue(
                    CueCategory.LAP_INVALID,
                    "Giro invalidato, stesso errore di prima. Qui puoi fare meglio."
                    if again else
                    "Giro invalidato, sei uscito largo. Al prossimo giro la tieni dentro."
                    if reason == "wide" else
                    "Giro invalidato, hai tagliato la curva. Il prossimo lo chiudi pulito."
                    if reason == "cut" else
                    "Giro invalidato, limiti di pista. Ora ne fai uno pulito.",
                    _PRIORITY, int(pos * 20), pos))
        self._prev_xz = (s.car_x, s.car_z)
        return cues
