"""Live coaching in a single window — engine + voice + overlay together.

The everyday way to use ACCoach: one process, no second terminal, no WebSocket.
A PySide6 timer drives the :class:`~accoach.engine.CoachEngine`, speaks cues, and
feeds the same :class:`~accoach.overlay.Overlay` widget directly (via
``apply_state``) instead of over a socket.

    python -m accoach live            # coach + on-screen overlay (voice on)
    python -m accoach live --silent   # overlay only, no audio
    python -m accoach live --demo     # synthetic lap, no game needed

For multi-client / second-screen setups use the websocket backend instead
(``python -m accoach server`` + ``python -m accoach overlay``).
"""

from __future__ import annotations

import logging
import signal
import sys
import time

from .coaching import Voice
from .config import load_config
from .engine import CoachEngine
from .serialize import state_to_dict
from .theme import load_fonts

_log = logging.getLogger(__name__)

TICK_MS = 50  # 20 Hz engine tick


def make_step(engine, overlay, *, publish=None, to_dict=state_to_dict):
    """Un giro di giostra: **un** tick, e lo stesso stato a chi lo guarda.

    `publish` e' la pagina Ingegnere quando Coach Live la sta servendo. Il punto
    da non perdere e' che il motore avanza **una volta sola**: chiedergli un
    secondo stato per la pagina vorrebbe dire vedere ogni giro due volte e
    salvarlo due volte, che e' l'incidente del 22/07 da un'altra porta.

    E la pagina non puo' fermare il coach: se trasmettere fallisce, l'overlay e
    la voce hanno gia' avuto il loro. Un accessorio che rompe l'essenziale e' un
    accessorio scritto male.
    """
    def step() -> None:
        state = engine.tick(time.monotonic())
        overlay.apply_state(to_dict(state))
        if publish is not None:
            try:
                publish(state)
            except Exception:       # noqa: BLE001 - la pagina non ferma il coach
                _log.debug("la pagina Ingegnere non ha ricevuto lo stato",
                           exc_info=True)
    return step


def _serve_engineer_page(engine):
    """Serve la pagina Ingegnere con QUESTO motore, mentre il pilota guida.

    Nato in pista il 24/09. Il coach diceva «modifica pronta, apri la pagina
    Ingegnere» e la pagina era morta: la alimentava solo il Backend live, che
    non puo' girare insieme a Coach Live perche' due motori salvano ogni giro
    due volte. Il pilota non poteva vedere la proposta, non poteva applicarla di
    li', e -- peggio -- non aveva modo di dire al motore che l'aveva applicata a
    mano: cosi' il coach l'ha richiamato ai box tre volte per una modifica che
    aveva gia' fatto.

    Qui non nasce un secondo motore: il backend gira in modalita' **spettatore**
    su quello di Coach Live. Torna la funzione con cui pubblicare lo stato, o
    `None` se la pagina non si puo' servire -- e allora Coach Live fa quello che
    ha sempre fatto, perche' la pagina e' un di piu' e non una precondizione.
    """
    from . import server as _server
    from .netinfo import port_open

    cfg = load_config()
    port = cfg.server.port
    if port_open(port):
        # C'e' gia' un backend acceso: e' lui che serve la pagina, e due
        # processi sulla stessa porta non ci stanno. Nessun danno, solo niente
        # feed da qui.
        _log.info("porta %d gia' occupata: la pagina Ingegnere non la servo io", port)
        return None
    try:
        import threading

        import uvicorn

        api = _server.create_app(engine, hz=cfg.server.hz, spettatore=True)
        # La stessa interfaccia del Backend live: in LAN il tablet deve
        # arrivare al feed, non solo alla pagina.
        srv = uvicorn.Server(uvicorn.Config(
            api, host=_server.listen_host(cfg), port=port, log_level="warning"))
        # Uvicorn installa gestori di segnale, e fuori dal thread principale
        # Python lo vieta: senza questa riga Coach Live cade all'avvio.
        srv.install_signal_handlers = lambda: None
        threading.Thread(target=srv.run, daemon=True,
                         name="ingegnere").start()
        _log.info("pagina Ingegnere alimentata da Coach Live su :%d", port)
        return api.state.publish
    except Exception:   # noqa: BLE001 - la pagina non deve impedire di guidare
        _log.warning("non sono riuscito a servire la pagina Ingegnere",
                     exc_info=True)
        return None


def main(argv: list[str] | None = None) -> None:
    from .logging_setup import setup_logging
    setup_logging()
    argv = sys.argv[1:] if argv is None else argv
    silent = "--silent" in argv or "-s" in argv
    demo = "--demo" in argv
    interactive = "--interactive" in argv or "-i" in argv

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("Live mode needs PySide6.  Install it with:  pip install PySide6")
        raise SystemExit(1)

    from .overlay import Overlay

    from .config import load_config
    cfg = load_config()
    lang = cfg.language
    voice_on = (not silent) and cfg.voice.enabled
    if demo:
        from .demo import make_demo_engine

        engine = make_demo_engine()
        if voice_on:
            engine.voice = Voice(enabled=True, rate=cfg.voice.rate, language=lang,
                                 male=cfg.voice.male, radio=cfg.voice.radio)
    else:
        engine = CoachEngine(
            voice=Voice(enabled=voice_on, rate=cfg.voice.rate, language=lang,
                        male=cfg.voice.male, radio=cfg.voice.radio),
            acquire_hz=cfg.acquire.hz, engineer_voice=cfg.voice.engineer)

    app = QApplication(sys.argv)
    load_fonts()                     # the overlay paints in the brand face too
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    overlay = Overlay(url=None, interactive=interactive)  # fed in-process
    overlay.show()

    publish = _serve_engineer_page(engine)
    step = make_step(engine, overlay, publish=publish)

    timer = QTimer()
    timer.timeout.connect(step)
    timer.start(TICK_MS)

    try:
        app.exec()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
