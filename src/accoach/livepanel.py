"""Lo stato del pannello «In pista», ricavato da /health e dal processo.

Nessun Qt qui: il pannello disegna soltanto quello che questo modulo decide,
cosi' le regole (quando il gioco e' chiuso, quando il coach non risponde, cosa
e' spuntato) si provano con una serie di risposte e un orologio finto.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

# Risposte mancate di fila a /health prima di dire che il coach non risponde
# (con POLL_S = 2 sono circa 6 s).
SILENT_AFTER = 3
# Secondi di `connected` falso, dopo averlo visto vero in questa corsa, che
# valgono «ACC chiuso».
CLOSED_AFTER_S = 60.0
# Ogni quanto l'hub interroga /health mentre Coach Live e' acceso.
POLL_S = 2.0
# Secondi dall'avvio in cui un coach che non ha ancora mai risposto «si sta
# avviando»; dopo, e' acceso ma non risponde. Non e' «muto»: muto vuol dire
# che rispondeva e ha smesso, e il rimedio («fermalo e riavvialo») e' un altro.
STARTING_S = 30.0


@dataclass
class Health:
    connected: bool | None
    car: str | None
    track: str | None
    saved_laps: int | None
    laps_done: int | None
    best: str | None
    remote_clients: int


def _int(v) -> int | None:
    # bool e' un int in Python: True non e' «1 giro».
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _str(v) -> str | None:
    return v if isinstance(v, str) and v else None


def parse_health(d: dict | None) -> Health | None:
    """Risposta mancante o malformata -> None (conta come risposta mancata).
    Un campo di tipo sbagliato diventa «sconosciuto», non un numero inventato."""
    if not isinstance(d, dict) or not d:
        return None
    c = d.get("connected")
    return Health(
        connected=c if isinstance(c, bool) else None,
        car=_str(d.get("car")),
        track=_str(d.get("track")),
        saved_laps=_int(d.get("saved_laps")),
        laps_done=_int(d.get("laps_done")),
        best=_str(d.get("best")),
        remote_clients=_int(d.get("remote_clients")) or 0,
    )


@dataclass
class PanelState:
    # "idle" | "starting" | "unreachable" | "before" | "driving" | "finished"
    # | "silent"
    phase: str
    tablet_done: bool = False
    tablet_now: bool = False
    car: str | None = None
    track: str | None = None
    saved_laps: int | None = None
    laps_done: int | None = None
    best: str | None = None


class LiveTracker:
    """Tiene la memoria di una corsa di Coach Live (da acceso a spento)."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._seen_telemetry = False
        self._closed_since: float | None = None
        self._missed = 0
        self._tablet_done = False
        self._tablet_now = False
        self._last: Health | None = None
        self._last_now = 0.0
        # Almeno una risposta buona in questa corsa, e quando la corsa e' partita.
        self._answered = False
        self._started_at: float | None = None
        # Auto, pista e giri salvati della corsa. Col gioco chiuso il motore
        # risponde car="" e track="" (TelemetrySnapshot.disconnected()) proprio
        # quando nasce «Ho finito»: senza questa memoria il report partiva
        # senza combo e apriva quella ricordata dal browser (22/10, Spa -> Imola).
        self._car: str | None = None
        self._track: str | None = None
        self._saved: int | None = None

    def begin(self, now: float) -> None:
        """La corsa parte adesso: da qui contano i STARTING_S dell'avvio (senza,
        contano dal primo `feed`, cioe' un poll dopo)."""
        self._reset()
        self._started_at = now

    def skip_tablet(self) -> None:
        self._tablet_done = True

    def dismiss_finished(self) -> None:
        """«Resto in pista»: la vista torna a quella di guida e il conto dei
        60 s riparte da adesso (o si annulla se la telemetria torna)."""
        if self._closed_since is not None:
            self._closed_since = self._last_now

    def feed(self, health: Health | None, now: float,
             live_running: bool) -> PanelState:
        if not live_running:
            # Una corsa nuova parte pulita: niente telemetria o tablet visti
            # nella precedente.
            self._reset()
            return PanelState("idle")
        self._last_now = now
        if self._started_at is None:
            self._started_at = now

        if health is None:
            self._missed += 1
        else:
            self._missed = 0
            self._answered = True
            self._last = health
            if health.connected is not False:
                # Solo una risposta non scollegata dice quale combo si guida.
                if health.car:
                    self._car = health.car
                if health.track:
                    self._track = health.track
            if health.saved_laps is not None:
                # Il piu' alto della corsa: un motore che riparte conta da 0,
                # ma i giri che aveva salvato restano sul disco.
                self._saved = (health.saved_laps if self._saved is None
                               else max(self._saved, health.saved_laps))
            if health.connected is True:
                self._seen_telemetry = True
                self._closed_since = None
            elif health.connected is False and self._seen_telemetry:
                if self._closed_since is None:
                    self._closed_since = now
            # connected sconosciuto (None): non dice ne' si' ne' no.
            self._tablet_now = health.remote_clients > 0
            if self._tablet_now:
                self._tablet_done = True

        if not self._answered:
            phase = ("starting" if now - self._started_at < STARTING_S
                     else "unreachable")
        elif self._missed >= SILENT_AFTER:
            # Un coach che non risponde non e' «ACC chiuso».
            phase = "silent"
        elif not self._seen_telemetry:
            phase = "before"
        elif (self._closed_since is not None
              and now - self._closed_since >= CLOSED_AFTER_S):
            phase = "finished"
        else:
            phase = "driving"

        h = self._last
        return PanelState(
            phase=phase,
            tablet_done=self._tablet_done,
            tablet_now=self._tablet_now,
            car=self._car,
            track=self._track,
            saved_laps=self._saved,
            laps_done=h.laps_done if h else None,
            best=h.best if h else None,
        )


def report_url(base: str, car: str | None, track: str | None) -> str:
    """Indirizzo del report che chiede la Pagella della combo guidata; senza
    auto o pista (il gioco non e' mai partito) apre il report cosi' com'e'."""
    if not car or not track:
        return base
    return (f"{base}?view=pagella&car={quote(car, safe='')}"
            f"&track={quote(track, safe='')}")
