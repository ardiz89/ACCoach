"""Lo stato del pannello «In pista»: da /health e dal processo, senza Qt."""
from __future__ import annotations

from accoach.livepanel import (
    CLOSED_AFTER_S, SILENT_AFTER, STARTING_S, Health, LiveTracker,
    parse_health, report_url,
)


def H(connected=True, remote=0, **kw) -> Health:
    return Health(
        connected=connected, car=kw.get("car"), track=kw.get("track"),
        saved_laps=kw.get("saved_laps"), laps_done=kw.get("laps_done"),
        best=kw.get("best"), remote_clients=remote)


def test_constants():
    assert (SILENT_AFTER, CLOSED_AFTER_S, STARTING_S) == (3, 60.0, 30.0)


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
    # prima della telemetria (ma dopo una risposta) la fase precedente e' before
    t2 = LiveTracker()
    t2.feed(H(False), 0.0, True)
    t2.feed(None, 2.0, True)
    t2.feed(None, 4.0, True)
    assert t2.feed(None, 6.0, True).phase == "silent"
    assert t2.feed(H(False), 8.0, True).phase == "before"


def test_before_the_first_answer_it_is_starting_not_silent():
    """«Muto» vuol dire che rispondeva e ha smesso. Un coach che non ha mai
    risposto si sta avviando, e dopo 30 s e' acceso ma non risponde: dirgli
    «fermalo e riavvialo» come a uno che si e' piantato sarebbe un'altra cosa."""
    t = LiveTracker()
    t.begin(0.0)
    for i in range(2, 30, 2):
        assert t.feed(None, float(i), True).phase == "starting"
    assert t.feed(None, 30.0, True).phase == "unreachable"
    assert t.feed(None, 300.0, True).phase == "unreachable"
    # la prima risposta buona lo sblocca, e da li' in poi il silenzio e' silenzio
    assert t.feed(H(False), 302.0, True).phase == "before"
    t.feed(None, 304.0, True)
    t.feed(None, 306.0, True)
    assert t.feed(None, 308.0, True).phase == "silent"


def test_a_malformed_answer_is_not_a_first_answer():
    t = LiveTracker()
    t.begin(0.0)
    assert t.feed(parse_health({}), 2.0, True).phase == "starting"
    assert t.feed(parse_health("x"), 40.0, True).phase == "unreachable"


def test_the_starting_clock_begins_with_the_run_not_the_first_poll():
    t = LiveTracker()
    t.begin(100.0)
    assert t.feed(None, 129.0, True).phase == "starting"
    assert t.feed(None, 130.0, True).phase == "unreachable"
    # senza `begin` l'orologio parte dal primo feed della corsa
    t2 = LiveTracker()
    assert t2.feed(None, 50.0, True).phase == "starting"
    assert t2.feed(None, 79.0, True).phase == "starting"
    assert t2.feed(None, 80.0, True).phase == "unreachable"
    # e una corsa nuova lo fa ripartire
    t2.feed(None, 81.0, False)
    assert t2.feed(None, 200.0, True).phase == "starting"


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


# --- la corsa ricorda auto, pista e giri dopo che il gioco si chiude ---------
# Il 22/10 il pilota ha guidato a Spa, chiuso ACC e premuto «Ho finito»: col
# gioco chiuso /health risponde car="" e track="", e il report e' partito senza
# parametri (ha aperto Imola).

SPA = dict(car="mclaren_720s_gt3_evo", track="Spa")


def test_closing_the_game_does_not_forget_the_combo():
    t = LiveTracker()
    s = t.feed(H(True, saved_laps=4, **SPA), 0.0, True)
    assert (s.car, s.track, s.saved_laps) == (SPA["car"], "Spa", 4)
    # il motore col gioco chiuso: TelemetrySnapshot.disconnected()
    s = t.feed(H(False, car=None, track=None, saved_laps=None), 10.0, True)
    assert (s.car, s.track, s.saved_laps) == (SPA["car"], "Spa", 4)
    s = t.feed(H(False), 70.0, True)
    assert s.phase == "finished"
    assert (s.car, s.track, s.saved_laps) == (SPA["car"], "Spa", 4)
    u = report_url("http://127.0.0.1:8778/", s.car, s.track)
    assert u.endswith("?view=pagella&car=mclaren_720s_gt3_evo&track=Spa")


def test_saved_laps_keep_the_highest_seen_in_the_run():
    # Un motore che riparte ricomincia a contare da 0: i giri gia' salvati
    # non spariscono.
    t = LiveTracker()
    t.feed(H(True, saved_laps=4, **SPA), 0.0, True)
    assert t.feed(H(True, saved_laps=0, **SPA), 2.0, True).saved_laps == 4
    assert t.feed(H(True, saved_laps=5, **SPA), 4.0, True).saved_laps == 5


def test_an_empty_or_disconnected_frame_does_not_overwrite_the_combo():
    t = LiveTracker()
    t.feed(H(True, **SPA), 0.0, True)
    # collegato ma senza auto/pista (un frame a meta'): non cancella
    s = t.feed(H(True, car=None, track=None), 2.0, True)
    assert (s.car, s.track) == (SPA["car"], "Spa")
    # scollegato: non dice cosa si guida, anche se porta dei nomi
    s = t.feed(H(False, car="c2", track="Imola"), 4.0, True)
    assert (s.car, s.track) == (SPA["car"], "Spa")


def test_a_connected_frame_with_a_new_combo_wins():
    t = LiveTracker()
    t.feed(H(True, **SPA), 0.0, True)
    s = t.feed(H(True, car="c2", track="Imola"), 2.0, True)
    assert (s.car, s.track) == ("c2", "Imola")


def test_a_new_run_forgets_the_combo():
    t = LiveTracker()
    t.feed(H(True, saved_laps=4, **SPA), 0.0, True)
    t.feed(H(False), 2.0, True)
    assert t.feed(None, 4.0, False).phase == "idle"
    s = t.feed(H(False), 6.0, True)
    assert (s.car, s.track, s.saved_laps) == (None, None, None)
