"""Headless backend: run the engine and broadcast its state over WebSocket.

One process owns the telemetry/coaching engine and pushes a JSON state snapshot
to every connected client at a fixed rate. The live overlay and the analysis app
are just clients — they never touch the game directly, and either can crash or
reconnect without disturbing the engine.

    python -m accoach.server          # serves ws://127.0.0.1:8777/ws

The blocking ``engine.tick`` (it reads shared memory) runs in a thread executor
so the asyncio event loop stays responsive.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .engine import CoachEngine
from .logging_setup import get_logger
from .netinfo import local_addresses
from .serialize import state_to_dict

HOST = "127.0.0.1"
PORT = 8777

_log = get_logger("server")


def _cpu_percent() -> float | None:
    """Best-effort process CPU%, only if psutil is available (optional dep)."""
    try:
        import psutil   # type: ignore
        return psutil.Process().cpu_percent(interval=None)
    except Exception:
        return None


_LOCALI_TTL_S = 60.0


def _is_remote(host: str, local: set[str]) -> bool:
    """True se `host` e' un'altra macchina (un tablet), non questo PC.

    Un host vuoto o sconosciuto non e' un tablet: meglio non spuntare un
    «tablet collegato» che non possiamo dimostrare.
    """
    if host.lower().startswith("::ffff:"):
        host = host[7:]   # IPv4 mappato su socket IPv6: e' lo stesso indirizzo
    return bool(host) and host not in local


def create_app(engine: CoachEngine | None = None, hz: float = 15.0, *,
               spettatore: bool = False) -> FastAPI:
    """Il backend. Con ``spettatore=True`` **guarda** un motore altrui.

    Nato in pista il 24/09. La pagina Ingegnere la alimenta solo questo
    processo, e questo processo non poteva girare insieme a Coach Live perche'
    due motori salvano ogni giro due volte. Cosi' il coach mandava il pilota ai
    box a leggere una proposta su una pagina che, in quella configurazione, era
    morta -- «telemetria offline».

    Da spettatore non c'e' un secondo motore: c'e' **un motore solo con due
    spettatori**. Coach Live lo fa avanzare come ha sempre fatto e chiama
    ``app.state.publish(stato)`` dopo ogni suo giro di giostra; qui si
    trasmette e basta.

    La riga che tiene in piedi tutto e' quella che **non** c'e': in questa
    modalita' il loop non chiama mai ``engine.tick``. Chiamarlo vorrebbe dire
    due driver sullo stesso motore, cioe' il giro contato due volte dalla porta
    di servizio invece che dal portone -- lo stesso incidente del 22/07
    travestito. C'e' un test che lo pretende, ed e' il piu' importante del file.
    """
    clients: set[WebSocket] = set()
    # These fields are exposed via /health so a silently failing tick (healthy
    # /health but no broadcasts) is observable instead of invisible.
    holder: dict = {
        "engine": engine, "task": None,
        "tick_errors": 0, "last_tick_ts": 0.0,
        "started": time.monotonic(), "prev_tick": 0.0,
        "tick_hz": None, "last_state": None,
        # Lo stato che ci passa chi guida il motore, da spettatore. `None`
        # finche' non arriva il primo: meglio «non lo so» che un fotogramma
        # vuoto spacciato per telemetria.
        "esterno": None,
        # Il contratto di sempre: l'app chiude il motore che le viene passato
        # (`server.main` ci conta, e un test lo pretende). L'unica eccezione e'
        # lo spettatore: li' il motore e' di Coach Live, e staccare il browser
        # non deve portare giu' il coach che sta seguendo il pilota.
        "e_nostro": not spettatore,
    }
    # A misconfigured hz (0 or negative) would make 1/hz blow up or busy-loop;
    # fall back to a sane default instead of crashing the backend at startup.
    if hz <= 0:
        _log.warning("invalid broadcast hz=%r, falling back to 15", hz)
        hz = 15.0
    interval = 1.0 / hz

    async def broadcast_loop() -> None:
        loop = asyncio.get_running_loop()
        while True:
            now = time.monotonic()
            try:
                if spettatore:
                    st = holder["esterno"]
                    if st is None:
                        await asyncio.sleep(interval)
                        continue
                else:
                    st = await loop.run_in_executor(None, holder["engine"].tick, now)
                state = state_to_dict(st)
                payload = json.dumps(state)
                holder["last_state"] = state
                holder["last_tick_ts"] = time.time()
                if holder["prev_tick"]:
                    dt = now - holder["prev_tick"]
                    if dt > 0:
                        holder["tick_hz"] = round(1.0 / dt, 1)
                holder["prev_tick"] = now
            except Exception:
                holder["tick_errors"] += 1
                # Log the first failure and then every 100th, so a persistent bug
                # is visible without flooding the log at the broadcast rate.
                if holder["tick_errors"] == 1 or holder["tick_errors"] % 100 == 0:
                    _log.error(
                        "engine tick failed (count=%d)", holder["tick_errors"], exc_info=True
                    )
                await asyncio.sleep(interval)
                continue
            for ws in list(clients):
                try:
                    await ws.send_text(payload)
                except Exception:
                    clients.discard(ws)
            await asyncio.sleep(interval)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if holder["engine"] is None and not spettatore:
            from .config import load_config
            holder["engine"] = CoachEngine(acquire_hz=load_config().acquire.hz)
        holder["task"] = asyncio.create_task(broadcast_loop())
        try:
            yield
        finally:
            task = holder["task"]
            if task is not None:
                task.cancel()
                # Wait for the loop to actually unwind (it may be mid-tick in the
                # executor) before closing the engine, so we don't tear down the
                # engine under a tick still touching shared memory.
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    _log.debug("broadcast loop ended with error", exc_info=True)
            if holder["engine"] is not None and holder["e_nostro"]:
                holder["engine"].close()

    app = FastAPI(title="HONE backend", lifespan=lifespan)

    def publish(st) -> None:
        """Chi guida il motore deposita qui l'ultimo stato. Usato da Coach Live."""
        holder["esterno"] = st

    app.state.publish = publish
    # The engineer UI is served from the analysis app (a different local port),
    # so it talks to this backend cross-origin. It's a local-only tool.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    @app.post("/engineer/applied")
    async def engineer_applied() -> dict:
        """The driver wrote the proposed setup: advance the engineer's re-test."""
        eng = holder.get("engine")
        if eng is not None and hasattr(eng, "mark_setup_applied"):
            eng.mark_setup_applied()
            return {"ok": True}
        return {"ok": False}

    async def _locali() -> set[str]:
        """Gli indirizzi del PC, in cache: il resolver puo' essere lento (VPN,
        NetBIOS) e `/health` gira sullo stesso loop del broadcast, quindi non
        lo interroga mai sul loop e non piu' di una volta ogni `_LOCALI_TTL_S`."""
        now = time.monotonic()
        if holder.get("locali") is None or now - holder["locali_ts"] > _LOCALI_TTL_S:
            holder["locali"] = await asyncio.get_running_loop().run_in_executor(
                None, local_addresses)
            holder["locali_ts"] = now
        return holder["locali"]

    @app.get("/health")
    async def health() -> dict:
        last = holder.get("last_state") or {}
        last_tick = holder.get("last_tick_ts") or 0.0
        eng = holder.get("engine")
        acquire_hz = eng.acquisition_hz() if hasattr(eng, "acquisition_hz") else None
        local = await _locali()
        remote = sum(
            1 for ws in list(clients)
            if _is_remote(ws.client.host if ws.client else "", local))
        lap = last.get("lap") or {}
        best = lap.get("best")
        return {
            "ok": True,
            "version": __version__,
            "uptime_s": round(time.monotonic() - holder["started"], 1),
            "clients": len(clients),
            "remote_clients": remote,
            "laps_done": lap.get("completed"),
            # format_lap_time scrive «--:--.---» quando il tempo non c'e'
            "best": best if best and not best.startswith("--") else None,
            "tick_errors": holder["tick_errors"],
            "tick_hz": holder.get("tick_hz"),
            "acquire_hz": acquire_hz,
            "last_tick_age_s": round(time.time() - last_tick, 2) if last_tick else None,
            "connected": last.get("connected"),
            "game": last.get("status"),
            "car": last.get("car"),
            "track": last.get("track"),
            "saved_laps": last.get("saved_laps"),
            "cpu_percent": _cpu_percent(),
        }

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        clients.add(ws)
        try:
            while True:
                await ws.receive_text()   # ignore client messages; keep alive
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            clients.discard(ws)

    return app


def listen_host(cfg, argv=()) -> str:
    """Su quale interfaccia ascolta il feed dal vivo.

    In modalita' LAN (config o ``--lan``) tutte, cosi' un tablet arriva al
    websocket; altrimenti quella configurata. Sta in una funzione perche' la
    regola ha due chiamanti -- questo processo e Coach Live quando serve la
    pagina Ingegnere da spettatore -- e la seconda copia l'aveva gia' persa:
    con ``lan = true`` il tablet apriva la pagina (l'app di analisi ascolta in
    rete) e ci leggeva «telemetria offline», perche' il feed stava solo su
    127.0.0.1.
    """
    return "0.0.0.0" if (cfg.lan or "--lan" in argv) else cfg.server.host


def _build_voice(cfg, enabled: bool = True):
    """The coach's voice, built exactly as ``live`` builds it (see ``app.py``).

    The backend used to run **voiceless**: it broadcast a state and left
    speaking to ``live``, whose overlay process it replaced. That is the wrong
    default for the one session this process exists for — the race-engineer
    loop. Its page lives on a tablet, and the two things it has to say while the
    car is moving are *"box this lap"* and, once stopped, *"go and read it"*.
    Neither can be delivered by a second screen the driver must not look at:
    speaking them is the whole protocol (TARATURE-ACC.md, after the 2026-08-02
    incident — while moving you are told, stopped you answer).

    Same construction as ``live`` on purpose, so the voice is the same voice
    whichever process is running, and ``--silent`` still buys silence.
    """
    from .coaching.voice import Voice  # noqa: PLC0415
    return Voice(enabled=enabled, rate=cfg.voice.rate, language=cfg.language,
                 male=cfg.voice.male, radio=cfg.voice.radio)


def main(argv: list[str] | None = None) -> None:
    import sys

    import uvicorn

    from .config import load_config
    from .logging_setup import setup_logging
    setup_logging()
    cfg = load_config()

    argv = sys.argv[1:] if argv is None else argv
    voice_on = ("--silent" not in argv) and cfg.voice.enabled

    if "--demo" in argv:
        from .demo import make_demo_engine  # noqa: PLC0415

        engine = make_demo_engine()
        print("HONE backend in DEMO mode (synthetic lap, no game needed)")
        if voice_on:
            engine.voice = _build_voice(cfg)
    else:
        engine = CoachEngine(voice=_build_voice(cfg, enabled=voice_on),
                             acquire_hz=cfg.acquire.hz,
                             engineer_voice=cfg.voice.engineer)

    host = listen_host(cfg, argv)
    port = cfg.server.port
    print(f"HONE backend on ws://{host}:{port}/ws  (Ctrl+C to stop)")
    uvicorn.run(create_app(engine=engine, hz=cfg.server.hz),
                host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
