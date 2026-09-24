"""Il backend può **guardare** un motore che guida qualcun altro.

Nato in pista il 2026-09-24. Il coach dice «modifica pronta, rientra ai box e
apri la pagina Ingegnere»; il pilota rientra, apre, e la pagina è morta —
«telemetria offline». La pagina la alimenta solo `server`, e `server` non può
girare insieme a Coach Live perché **due motori salvano ogni giro due volte**.
Risultato: il coach manda il pilota in un posto che, nella configurazione in cui
lo manda, non può funzionare. Ci sono voluti quaranta minuti e io gli ho dovuto
ricostruire la modifica a mano, dal log e dal codice.

La cura non è un secondo motore: è **un motore solo con due spettatori**. Coach
Live lo fa avanzare come ha sempre fatto, e il backend si limita a pubblicare
l'ultimo stato che quello produce.

Il punto su cui si gioca tutto, ed è la ragione per cui questo file esiste:
`broadcast_loop` **faceva avanzare il motore** (`engine.tick`). Passargli il
motore di Coach Live senza altro sarebbe stato due driver sullo stesso motore —
cioè il giro contato due volte da una porta di servizio invece che dall'altra,
lo stesso incidente del 22/07 travestito. Il test che conta e' quello che
verifica che in modalità spettatore il backend **non chiami mai** `tick`.
"""
from fastapi.testclient import TestClient

from accoach.engine import EngineState
from accoach.server import create_app
from accoach.telemetry.snapshot import TelemetrySnapshot


def _stato(saved_laps: int = 0, car: str = "mclaren_720s_gt3_evo",
           track: str = "Imola") -> EngineState:
    """Uno stato **vero**, non un dizionario.

    Serve davvero: `broadcast_loop` inghiotte ogni eccezione in `tick_errors`,
    quindi un finto stato che `state_to_dict` non sa leggere farebbe passare
    lo stesso il test «il motore e' avanzato» — verde per il motivo sbagliato.
    """
    from dataclasses import replace
    snap = replace(TelemetrySnapshot.disconnected(), connected=True,
                   car_model=car, track=track)
    return EngineState(snapshot=snap, delta=None, spoken=None,
                       saved_laps=saved_laps, reference_ms=0, history=[])


class _MotoreFinto:
    """Conta chi lo fa avanzare, che è esattamente ciò che vogliamo sapere."""

    def __init__(self) -> None:
        self.tick_calls = 0
        self.closed = False
        self.applied = 0
        self._stato = _stato()

    def tick(self, now: float):
        self.tick_calls += 1
        return self._stato

    def close(self) -> None:
        self.closed = True

    def mark_setup_applied(self) -> None:
        self.applied += 1

    def acquisition_hz(self):
        return 60.0


def _gira(app, per_secondi: float = 0.25):
    """Tiene l'app viva quel tanto che basta perché il loop giri più volte."""
    with TestClient(app) as client:
        import time
        time.sleep(per_secondi)
        return client.get("/health").json()


def test_da_solo_il_backend_fa_avanzare_il_motore_come_sempre():
    """La modalità di sempre non cambia: `server` da solo guida il motore."""
    m = _MotoreFinto()
    _gira(create_app(m, hz=60.0))
    assert m.tick_calls > 0


def test_da_spettatore_il_backend_non_tocca_mai_il_motore():
    """**Il test che giustifica tutto il file.**

    Se questo cade, il backend e Coach Live stanno facendo avanzare lo stesso
    motore insieme: ogni giro verrebbe visto due volte e salvato due volte, e la
    copia è indistinguibile da un giro vero in più.
    """
    m = _MotoreFinto()
    app = create_app(m, hz=60.0, spettatore=True)
    app.state.publish(m._stato)
    _gira(app)
    assert m.tick_calls == 0, (
        f"il backend ha fatto avanzare il motore {m.tick_calls} volte mentre "
        f"lo guidava qualcun altro: e' il giro salvato due volte")


def test_da_spettatore_trasmette_lo_stato_che_gli_passano():
    m = _MotoreFinto()
    app = create_app(m, hz=60.0, spettatore=True)
    app.state.publish(_stato(saved_laps=7, car="auto", track="pista"))
    salute = _gira(app)
    assert salute["saved_laps"] == 7
    assert salute["car"] == "auto"


def test_da_spettatore_non_chiude_un_motore_che_non_e_suo():
    """Coach Live continua a girare quando la pagina si stacca.

    Senza questo, chiudere il browser porterebbe giù il motore che sta
    guidando il pilota — un difetto peggiore di quello che stiamo curando.
    """
    m = _MotoreFinto()
    app = create_app(m, hz=60.0, spettatore=True)
    app.state.publish(m._stato)
    _gira(app)
    assert not m.closed


def test_da_solo_invece_il_motore_lo_chiude_perche_e_suo():
    m = _MotoreFinto()
    _gira(create_app(m, hz=60.0))
    assert m.closed


def test_prima_di_ricevere_uno_stato_non_finge_di_averne_uno():
    """Meglio «non lo so» che un ultimo stato inventato.

    All'avvio Coach Live non ha ancora pubblicato niente: la pagina deve
    leggere che non c'è nulla, non un fotogramma vuoto spacciato per telemetria.
    """
    m = _MotoreFinto()
    salute = _gira(create_app(m, hz=60.0, spettatore=True))
    assert salute["connected"] is None
    assert salute["saved_laps"] is None


def test_lo_scritto_sul_setup_arriva_al_motore_anche_da_spettatore():
    """È la ragione pratica per cui la pagina serve mentre guidi: applichi la
    modifica dalla pagina e il motore che ti sta seguendo lo viene a sapere."""
    m = _MotoreFinto()
    app = create_app(m, hz=60.0, spettatore=True)
    with TestClient(app) as client:
        assert client.post("/engineer/applied").json() == {"ok": True}
    assert m.applied == 1
