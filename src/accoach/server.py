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


def create_app(engine: CoachEngine | None = None, hz: float = 15.0) -> FastAPI:
    clients: set[WebSocket] = set()
    # These fields are exposed via /health so a silently failing tick (healthy
    # /health but no broadcasts) is observable instead of invisible.
    holder: dict = {
        "engine": engine, "task": None,
        "tick_errors": 0, "last_tick_ts": 0.0,
        "started": time.monotonic(), "prev_tick": 0.0,
        "tick_hz": None, "last_state": None,
    }
    interval = 1.0 / hz

    async def broadcast_loop() -> None:
        loop = asyncio.get_event_loop()
        while True:
            now = time.monotonic()
            try:
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
        if holder["engine"] is None:
            from .config import load_config
            holder["engine"] = CoachEngine(acquire_hz=load_config().acquire.hz)
        holder["task"] = asyncio.create_task(broadcast_loop())
        try:
            yield
        finally:
            if holder["task"] is not None:
                holder["task"].cancel()
            if holder["engine"] is not None:
                holder["engine"].close()

    app = FastAPI(title="ACCoach backend", lifespan=lifespan)
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

    @app.get("/health")
    async def health() -> dict:
        last = holder.get("last_state") or {}
        last_tick = holder.get("last_tick_ts") or 0.0
        eng = holder.get("engine")
        acquire_hz = eng.acquisition_hz() if hasattr(eng, "acquisition_hz") else None
        return {
            "ok": True,
            "version": __version__,
            "uptime_s": round(time.monotonic() - holder["started"], 1),
            "clients": len(clients),
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


def main(argv: list[str] | None = None) -> None:
    import sys

    import uvicorn

    from .config import load_config
    from .logging_setup import setup_logging
    setup_logging()
    cfg = load_config()

    argv = sys.argv[1:] if argv is None else argv
    engine = None
    if "--demo" in argv:
        from .demo import make_demo_engine

        engine = make_demo_engine()
        print("ACCoach backend in DEMO mode (synthetic lap, no game needed)")

    host, port = cfg.server.host, cfg.server.port
    print(f"ACCoach backend on ws://{host}:{port}/ws  (Ctrl+C to stop)")
    uvicorn.run(create_app(engine=engine, hz=cfg.server.hz),
                host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
