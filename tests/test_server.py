"""server: FastAPI backend health + WebSocket broadcast of engine state."""
import json

from fastapi.testclient import TestClient

from accoach.engine import EngineState
from accoach.server import create_app
from accoach.telemetry.snapshot import TelemetrySnapshot


class _StubEngine:
    """Duck-typed engine: a fixed disconnected state, counts ticks, closeable."""

    def __init__(self):
        self.ticks = 0
        self.closed = False

    def tick(self, now):
        self.ticks += 1
        return EngineState(
            snapshot=TelemetrySnapshot.disconnected(),
            delta=None, spoken=None, saved_laps=0, reference_ms=0, history=[],
        )

    def close(self):
        self.closed = True


def test_health_endpoint():
    eng = _StubEngine()
    with TestClient(create_app(engine=eng, hz=50)) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # Enriched health: version + observability fields are present.
        assert body["version"]
        assert "tick_errors" in body
        assert "uptime_s" in body


class _EngineWithMark(_StubEngine):
    def __init__(self):
        super().__init__()
        self.marked = False

    def mark_setup_applied(self):
        self.marked = True


def test_engineer_applied_noop_without_support():
    with TestClient(create_app(engine=_StubEngine(), hz=50)) as client:
        r = client.post("/engineer/applied")
        assert r.status_code == 200 and r.json()["ok"] is False


def test_engineer_applied_advances_engine():
    eng = _EngineWithMark()
    with TestClient(create_app(engine=eng, hz=50)) as client:
        assert client.post("/engineer/applied").json()["ok"] is True
        assert eng.marked is True


def test_websocket_broadcasts_state():
    eng = _StubEngine()
    with TestClient(create_app(engine=eng, hz=50)) as client:
        with client.websocket_connect("/ws") as ws:
            payload = ws.receive_text()
            data = json.loads(payload)
            assert data["connected"] is False
            assert "history" in data and "delta" in data


def test_engine_closed_on_shutdown():
    eng = _StubEngine()
    with TestClient(create_app(engine=eng, hz=50)):
        pass
    assert eng.closed is True


def test_invalid_hz_does_not_crash():
    # A misconfigured hz=0 must not blow up (1/hz) at startup; it falls back to a
    # sane rate and still broadcasts.
    eng = _StubEngine()
    with TestClient(create_app(engine=eng, hz=0)) as client:
        with client.websocket_connect("/ws") as ws:
            json.loads(ws.receive_text())   # a broadcast still arrives
        assert client.get("/health").status_code == 200
