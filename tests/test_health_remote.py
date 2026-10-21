"""`/health` dice chi e' collegato (e da dove) e a che giro sei.

L'hub lo interroga per spuntare «tablet collegato» e mostrare il giro: il
websocket del pilota stesso (il report sul PC) non deve contare come tablet.
"""
from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

import accoach.server as server
from accoach.engine import EngineState
from accoach.netinfo import local_addresses
from accoach.server import _is_remote, create_app
from accoach.telemetry.snapshot import TelemetrySnapshot


class _Motore:
    def tick(self, now):
        return None

    def close(self):
        pass

    def acquisition_hz(self):
        return 60.0


def _stato(completed=7, best_ms=101882):
    snap = replace(TelemetrySnapshot.disconnected(), connected=True,
                   completed_laps=completed, best_lap_ms=best_ms)
    return EngineState(snapshot=snap, delta=None, spoken=None,
                       saved_laps=0, reference_ms=0, history=[])


def _app_con_stato(stato=None):
    app = create_app(_Motore(), hz=60.0, spettatore=True)
    if stato is not None:
        app.state.publish(stato)
    return app


def _attendi(client, cond):
    import time
    for _ in range(100):
        h = client.get("/health").json()
        if cond(h):
            return h
        time.sleep(0.02)
    return h


def test_local_addresses_always_has_loopback():
    a = local_addresses()
    assert {"127.0.0.1", "::1"} <= a


def test_local_addresses_never_raises(monkeypatch):
    import socket

    def boom(*a, **k):
        raise OSError("no")
    monkeypatch.setattr(socket, "gethostbyname_ex", boom)
    monkeypatch.setattr(socket, "gethostname", boom)
    assert {"127.0.0.1", "::1"} <= local_addresses()


def test_is_remote_distinguishes_this_machine_from_others():
    local = {"127.0.0.1", "::1", "192.168.1.23"}
    assert not _is_remote("127.0.0.1", local)
    assert not _is_remote("192.168.1.23", local)
    assert _is_remote("192.168.1.50", local)
    assert not _is_remote("", local)  # host sconosciuto: non e' un tablet


def test_health_counts_only_clients_from_other_machines(monkeypatch):
    # Il TestClient si presenta come «testclient»: lo facciamo passare per un
    # indirizzo di rete di un'altra macchina, e per locale il secondo.
    monkeypatch.setattr(server, "local_addresses", lambda: {"127.0.0.1", "::1"})
    app = _app_con_stato()
    with TestClient(app) as c:
        with c.websocket_connect("/ws"):
            h = _attendi(c, lambda h: h["clients"] == 1)
            assert h["clients"] == 1
            assert h["remote_clients"] == 1
        # un client «locale» e uno remoto insieme
        monkeypatch.setattr(server, "_is_remote",
                            lambda host, local: host == "remoto")
        with c.websocket_connect("/ws"):
            h = _attendi(c, lambda h: h["clients"] == 1)
            assert h["clients"] == 1 and h["remote_clients"] == 0


def test_the_pc_own_lan_address_is_not_a_tablet(monkeypatch):
    monkeypatch.setattr(server, "local_addresses",
                        lambda: {"127.0.0.1", "::1", "testclient"})
    app = _app_con_stato()
    with TestClient(app) as c:
        with c.websocket_connect("/ws"):
            h = _attendi(c, lambda h: h["clients"] == 1)
            assert h["clients"] == 1
            assert h["remote_clients"] == 0


def test_health_reports_the_lap():
    with TestClient(_app_con_stato(_stato(7, 101882))) as c:
        h = _attendi(c, lambda h: h["laps_done"] is not None)
        assert h["laps_done"] == 7
        assert h["best"] == "1:41.882"


def test_health_without_state_or_best_says_none():
    with TestClient(_app_con_stato()) as c:
        h = c.get("/health").json()
        assert h["laps_done"] is None and h["best"] is None
    with TestClient(_app_con_stato(_stato(2, 0))) as c:
        h = _attendi(c, lambda h: h["laps_done"] is not None)
        assert h["laps_done"] == 2
        assert h["best"] is None
