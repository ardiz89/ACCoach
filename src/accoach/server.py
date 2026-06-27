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

from .engine import CoachEngine
from .logging_setup import get_logger
from .serialize import state_to_dict

HOST = "127.0.0.1"
PORT = 8777

_log = get_logger("server")


def create_app(engine: CoachEngine | None = None, hz: float = 15.0) -> FastAPI:
    clients: set[WebSocket] = set()
    # tick_errors/last_tick_ts are exposed via /health so a silently failing tick
    # (healthy /health but no broadcasts) is observable instead of invisible.
    holder: dict = {"engine": engine, "task": None, "tick_errors": 0, "last_tick_ts": 0.0}
    interval = 1.0 / hz

    async def broadcast_loop() -> None:
        loop = asyncio.get_event_loop()
        while True:
            now = time.monotonic()
            try:
                st = await loop.run_in_executor(None, holder["engine"].tick, now)
                payload = json.dumps(state_to_dict(st))
                holder["last_tick_ts"] = time.time()
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
            holder["engine"] = CoachEngine()
        holder["task"] = asyncio.create_task(broadcast_loop())
        try:
            yield
        finally:
            if holder["task"] is not None:
                holder["task"].cancel()
            if holder["engine"] is not None:
                holder["engine"].close()

    app = FastAPI(title="ACCoach backend", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "clients": len(clients)}

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

    from .logging_setup import setup_logging
    setup_logging()

    argv = sys.argv[1:] if argv is None else argv
    engine = None
    if "--demo" in argv:
        from .demo import make_demo_engine

        engine = make_demo_engine()
        print("ACCoach backend in DEMO mode (synthetic lap, no game needed)")

    print(f"ACCoach backend on ws://{HOST}:{PORT}/ws  (Ctrl+C to stop)")
    uvicorn.run(create_app(engine=engine), host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
