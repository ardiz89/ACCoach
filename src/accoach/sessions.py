"""Laps grouped back into the runs they were driven in.

Everything downstream of the recorder is lap-centric: pick a car and a track,
pick two laps, compare them. That is the right shape for studying a lap and the
wrong shape for the question a driver actually has when they get up from the
wheel, which is *how did that go*. A run of laps driven in one sitting is a real
thing — same tyres, same fuel load, same track temperature, same person in the
same mood — and nothing in the app represented it.

**Why the gap, and not the ``session`` column.** The lap table has had a
``session`` field since the beginning and it cannot be used for this: it carries
the sim's session *type* (practice / qualifying / race), so every lap of every
practice run ever recorded reads ``0``. Measured on the 39 laps on disk — all of
them ``0``, across four cars, four tracks and five separate evenings.

So sessions are inferred from when the laps were written, which is a heuristic
and is treated as one. The failure it can have is chosen: a long break inside
one stint splits into two sessions, rather than two evenings merging into one.
That direction is the safe one — a merged pair would average lap times across
different track temperatures and call the result your consistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

#: A gap longer than this starts a new session. A lap takes 1.5–2.5 minutes, so
#: twenty is roughly ten laps' worth of not driving: long enough that you got up
#: from the wheel, restarted the game, or changed something. It is a judgement
#: call, not a measurement — see the module docstring for which way it errs.
SESSION_GAP_S = 20 * 60

#: Sotto questa velocità l'auto è ferma.
STOP_KMH = 5.0
#: Un giro con l'auto ferma per più di così non misura la guida. Il gioco lo dà
#: valido e senza uscite, ma il tempo è quello di una sosta. A Brands Hatch, il
#: 25/10, un giro da 3:32 era fermo 106 s alla Druids; nessuno degli altri 14
#: giri di quella sera stava fermo nemmeno un decimo. Una testacoda ripresa
#: subito resta sotto la soglia: quella è guida.
STOP_MAX_MS = 5000


def stopped_ms(samples) -> int:
    """Quanto tempo del giro l'auto sta sotto ``STOP_KMH``, in ms."""
    return sum(b.t_ms - a.t_ms for a, b in zip(samples, samples[1:])
               if a.speed_kmh < STOP_KMH and b.t_ms > a.t_ms)


def stood_still(lap) -> bool:
    """Il giro ha una sosta: non entra nei numeri della guida."""
    return stopped_ms(lap.samples) > STOP_MAX_MS


def parse_utc(text: str | None) -> datetime | None:
    """The recorder's timestamp, or ``None`` if it isn't one.

    Laps written before the field existed have nothing here, and a lap with no
    time cannot be placed in a run — it is dropped from the session view rather
    than guessed into the newest one.
    """
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class Session:
    """One run of laps, newest laps last."""

    laps: list[dict] = field(default_factory=list)

    @property
    def started(self) -> datetime | None:
        return parse_utc(self.laps[0].get("recorded_utc")) if self.laps else None

    @property
    def ended(self) -> datetime | None:
        return parse_utc(self.laps[-1].get("recorded_utc")) if self.laps else None

    @property
    def duration_s(self) -> float:
        a, b = self.started, self.ended
        return (b - a).total_seconds() if a and b else 0.0

    @property
    def valid_laps(self) -> list[dict]:
        """Laps that can carry a time. A session's numbers only ever use these.

        `valid` means the lap ran start line to start line; `clean` means it
        stayed inside the track limits. A cut lap is still a lap you drove and
        it still belongs in the list — but it is faster for a reason, so it
        cannot set the best or move the average.
        """
        return [l for l in self.laps if l.get("valid") and l.get("clean") != 0]

    @property
    def best(self) -> dict | None:
        laps = self.valid_laps
        return min(laps, key=lambda l: l["lap_time_ms"]) if laps else None

    @property
    def road_temps(self) -> list[float]:
        return [float(l["road_temp"]) for l in self.laps
                if l.get("road_temp") not in (None, 0, 0.0)]


def group_sessions(rows: list[dict], gap_s: float = SESSION_GAP_S) -> list[Session]:
    """Split ``rows`` into sessions, newest session first, laps within oldest first.

    Order is deliberate and mixed: the newest run is the one you want on screen,
    and inside it the laps read the way you drove them.
    """
    dated = [(t, r) for r in rows if (t := parse_utc(r.get("recorded_utc")))]
    dated.sort(key=lambda pair: pair[0])

    out: list[Session] = []
    prev: datetime | None = None
    for stamp, row in dated:
        if prev is None or (stamp - prev).total_seconds() > gap_s:
            out.append(Session())
        out[-1].laps.append(row)
        prev = stamp
    out.reverse()
    return out
