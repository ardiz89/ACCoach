"""Lo stato del pannello «In pista»: da /health e dal processo, senza Qt."""
from __future__ import annotations

from accoach.livepanel import (
    CLOSED_AFTER_S, SILENT_AFTER, Health, LiveTracker, parse_health,
    report_url,
)


def H(connected=True, remote=0, **kw) -> Health:
    return Health(
        connected=connected, car=kw.get("car"), track=kw.get("track"),
        saved_laps=kw.get("saved_laps"), laps_done=kw.get("laps_done"),
        best=kw.get("best"), remote_clients=remote)


def test_constants():
    assert (SILENT_AFTER, CLOSED_AFTER_S) == (3, 60.0)


def test_parse_health():
    h = parse_health({"connected": True, "car": "c", "track": "t",
                      "saved_laps": 3, "laps_done": 2, "best": "1:40,1",
                      "remote_clients": 1})
    assert h == Health(True, "c", "t", 3, 2, "1:40,1", 1)
    assert parse_health(None) is None
    assert parse_health("x") is None
    assert parse_health({}) is None
    # campi di tipo sbagliato: non inventano numeri
    h = parse_health({"connected": "yes", "laps_done": True,
                      "remote_clients": "2"})
    assert h.connected is None and h.laps_done is None
    assert h.remote_clients == 0


def test_not_running_is_idle():
    t = LiveTracker()
    assert t.feed(None, 0.0, False).phase == "idle"
    assert t.feed(H(), 1.0, False).phase == "idle"


def test_running_without_telemetry_stays_before_and_never_finishes():
    t = LiveTracker()
    for i in range(0, 600, 2):
        assert t.feed(H(connected=False), float(i), True).phase == "before"
    assert t.feed(H(connected=False), 601.0, True).phase == "before"


def test_telemetry_makes_it_driving():
    t = LiveTracker()
    assert t.feed(H(False), 0.0, True).phase == "before"
    s = t.feed(H(True, car="c", track="t", laps_done=1, best="1:40,1"),
               2.0, True)
    assert s.phase == "driving"
    assert (s.car, s.track, s.laps_done, s.best) == ("c", "t", 1, "1:40,1")


def test_acc_closed_for_60s_after_driving_is_finished():
    t = LiveTracker()
    t.feed(H(True), 0.0, True)
    assert t.feed(H(False), 10.0, True).phase == "driving"
    assert t.feed(H(False), 69.0, True).phase == "driving"
    assert t.feed(H(False), 70.0, True).phase == "finished"
    # la telemetria che torna annulla la chiusura
    assert t.feed(H(True), 72.0, True).phase == "driving"
    assert t.feed(H(False), 73.0, True).phase == "driving"


def test_three_missed_answers_is_silent_and_it_recovers():
    t = LiveTracker()
    t.feed(H(True), 0.0, True)
    assert t.feed(None, 2.0, True).phase == "driving"
    assert t.feed(None, 4.0, True).phase == "driving"
    assert t.feed(None, 6.0, True).phase == "silent"
    assert t.feed(H(True), 8.0, True).phase == "driving"
    # prima della telemetria la fase precedente e' before
    t2 = LiveTracker()
    t2.feed(None, 0.0, True)
    t2.feed(None, 2.0, True)
    assert t2.feed(None, 4.0, True).phase == "silent"
    assert t2.feed(H(False), 6.0, True).phase == "before"


def test_silent_is_not_acc_closed():
    t = LiveTracker()
    t.feed(H(True), 0.0, True)
    # nessuna risposta per molto tempo: mai «finished»
    t.feed(None, 2.0, True)
    t.feed(None, 4.0, True)
    for i in range(6, 400, 2):
        assert t.feed(None, float(i), True).phase == "silent"


def test_tablet_latches_for_the_run_but_now_follows_the_socket():
    t = LiveTracker()
    s = t.feed(H(True, remote=0), 0.0, True)
    assert (s.tablet_done, s.tablet_now) == (False, False)
    s = t.feed(H(True, remote=1), 2.0, True)
    assert (s.tablet_done, s.tablet_now) == (True, True)
    s = t.feed(H(True, remote=0), 4.0, True)
    assert (s.tablet_done, s.tablet_now) == (True, False)


def test_skip_ticks_the_tablet_step():
    t = LiveTracker()
    t.feed(H(False), 0.0, True)
    t.skip_tablet()
    s = t.feed(H(False), 2.0, True)
    assert s.tablet_done is True and s.tablet_now is False


def test_a_new_run_starts_clean():
    t = LiveTracker()
    t.feed(H(True, remote=1), 0.0, True)
    t.skip_tablet()
    assert t.feed(None, 2.0, False).phase == "idle"
    s = t.feed(H(False), 4.0, True)
    assert s.tablet_done is False
    assert s.phase == "before"
    # la telemetria della corsa prima non conta: chiusa a lungo, mai finished
    assert t.feed(H(False), 500.0, True).phase == "before"


def test_resto_in_pista_returns_to_driving_view():
    t = LiveTracker()
    t.feed(H(True), 0.0, True)
    t.feed(H(False), 10.0, True)
    assert t.feed(H(False), 70.0, True).phase == "finished"
    t.dismiss_finished()
    assert t.feed(H(False), 72.0, True).phase == "driving"
    assert t.feed(H(False), 120.0, True).phase == "driving"
    # altri 60 s di gioco chiuso: ricompare
    assert t.feed(H(False), 132.0, True).phase == "finished"
    # oppure la telemetria torna
    t.dismiss_finished()
    assert t.feed(H(True), 170.0, True).phase == "driving"
    assert t.feed(H(False), 171.0, True).phase == "driving"
    assert t.feed(H(False), 230.0, True).phase == "driving"
    assert t.feed(H(False), 231.0, True).phase == "finished"


def test_report_url_encodes_and_falls_back():
    base = "http://127.0.0.1:8778/"
    u = report_url(base, "mclaren_720s_gt3_evo", "Imola")
    assert u == base + "?view=pagella&car=mclaren_720s_gt3_evo&track=Imola"
    assert report_url(base, "c", None) == base
    assert report_url(base, None, "t") == base
    assert report_url(base, "", "t") == base
    u = report_url(base, "a b", "x&y")
    assert "car=a%20b" in u and "track=x%26y" in u
