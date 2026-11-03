"""Le misure dei gesti in una curva (coaching/gestures.py)."""

from __future__ import annotations

from accoach.coaching.gestures import (
    ABS_NOISE_S, PICKUP_NOISE_S, RELEASE_NOISE_S, STEER_NOISE, GestureNote,
    Gestures, compare, measure)
from accoach.recording.lap import LapSample


def _s(t_ms, *, speed=100.0, throttle=0.0, brake=0.0, steer=0.0, gear="3",
       abs_=0.0):
    return LapSample(t_ms=t_ms, pos=t_ms / 10000.0, speed_kmh=speed,
                     throttle=throttle, brake=brake, steer_angle=steer,
                     gear=gear, rpm=5000, g_lat=0.0, g_long=0.0,
                     abs_active=abs_)


def _series(n, step=100, **fn):
    """n campioni a passo fisso; ogni argomento e' una funzione dell'indice."""
    out = []
    for i in range(n):
        out.append(_s(i * step, **{k: v(i) for k, v in fn.items()}))
    return out


def test_release_half_second():
    # picco a i=2 (0,8), poi scende; sotto 0,05 al campione i=7 -> 0,5 s
    br = [0.0, 0.5, 0.8, 0.6, 0.4, 0.2, 0.1, 0.0, 0.0]
    g = measure(_series(len(br), brake=lambda i: br[i]))
    assert g.release_s is not None and abs(g.release_s - 0.5) < 1e-9


def test_release_none_without_braking():
    # Review 2: curva presa in pieno, niente «rilasci in 0 s».
    g = measure(_series(10, brake=lambda i: 0.0, throttle=lambda i: 1.0))
    assert g.release_s is None


def test_release_none_if_never_released():
    g = measure(_series(5, brake=lambda i: 0.5 + 0.1 * i))
    assert g.release_s is None


def test_pickup_point_eight():
    # minima a i=3; gas > 0,05 da i=4 (0,2), 0,9 a i=12 -> 0,8 s
    th = [0.0] * 4 + [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 1.0]
    sp = [120, 110, 100, 90] + [95 + i for i in range(len(th) - 4)]
    g = measure(_series(len(th), throttle=lambda i: th[i],
                        speed=lambda i: sp[i]))
    assert g.pickup_s is not None and abs(g.pickup_s - 0.8) < 1e-9


def test_pickup_none_if_throttle_stays_low():
    # Review 3: gas a 0,7, mai 0,9 -> None, non «apre piu' in fretta».
    th = [0.0, 0.0, 0.3, 0.5, 0.7, 0.7, 0.7]
    sp = [100, 80, 70, 75, 80, 85, 90]
    g = measure(_series(len(th), throttle=lambda i: th[i],
                        speed=lambda i: sp[i]))
    assert g.pickup_s is None


def test_apex_gear_simple():
    sp = [100, 80, 60, 80, 100]
    gears = ["4", "3", "3", "3", "4"]
    g = measure(_series(5, speed=lambda i: sp[i], gear=lambda i: gears[i]))
    assert g.apex_gear == "3"


def test_apex_gear_isolated_neutral_ignored():
    # Review 5: un solo «N» alla minima fra due «3» -> «3».
    sp = [100, 80, 60, 80, 100]
    gears = ["3", "3", "N", "3", "3"]
    g = measure(_series(5, speed=lambda i: sp[i], gear=lambda i: gears[i]))
    assert g.apex_gear == "3"


def test_apex_gear_window_is_quarter_second():
    # fuori da +-0,25 s le marce non contano: 2 campioni «5» lontani
    # non battono i 3 «3» vicini alla minima.
    sp = [100, 100, 100, 60, 100, 100, 100]
    gears = ["5", "5", "5", "3", "3", "3", "5"]
    g = measure(_series(7, speed=lambda i: sp[i], gear=lambda i: gears[i],
                        step=200))
    assert g.apex_gear == "3"


def test_abs_seconds():
    g = measure(_series(10, abs_=lambda i: 0.4 if 2 <= i < 5 else 0.0))
    assert abs(g.abs_s - 0.3) < 1e-9


def test_old_lap_without_channels_is_zero():
    # Review 1: giro registrato prima di ABS/G (campi a 0) -> misure neutre.
    g = measure(_series(10))
    assert g.abs_s == 0.0
    assert g.steer_reversals == 0
    assert g.release_s is None


def test_steer_sawtooth_counts_four():
    vals = [0.0, 0.1, 0.0, 0.1, 0.0, 0.1]
    g = measure(_series(len(vals), steer=lambda i: vals[i]))
    assert g.steer_reversals == 4


def test_steer_straight_noise_is_zero():
    # Task 2: sul rettilineo di confronto le oscillazioni arrivano a 0,056
    # (90 percentile); con 0,02 il giro tipico contava 5 inversioni lì.
    vals = [0.0, 0.05, 0.0, 0.05, 0.0, 0.05]
    g = measure(_series(len(vals), steer=lambda i: vals[i]))
    assert g.steer_reversals == 0


def test_steer_tiny_oscillation_is_zero():
    vals = [0.0, 0.01, 0.0, 0.01, 0.0, 0.01]
    g = measure(_series(len(vals), steer=lambda i: vals[i]))
    assert g.steer_reversals == 0


def test_empty_and_tiny_input():
    for smp in ([], [_s(0)]):
        g = measure(smp)
        assert isinstance(g, Gestures)
        assert (g.release_s, g.pickup_s, g.abs_s, g.steer_reversals) == (
            None, None, 0.0, 0)


# --- compare: quanto un gesto e' diverso dal rumore (Task 2) ---

def _g(release=1.0, pickup=0.5, gear="3", abs_=0.2, steer=2):
    return Gestures(release_s=release, pickup_s=pickup, apex_gear=gear,
                    abs_s=abs_, steer_reversals=steer)


def test_compare_identical_is_none():
    assert compare(_g(), _g()) is None


def test_compare_under_noise_is_none():
    # ogni misura poco sotto la sua soglia -> niente da dire
    live = _g(release=1.0 + 0.9 * RELEASE_NOISE_S,
              pickup=0.5 + 0.9 * PICKUP_NOISE_S,
              abs_=0.2 + 0.9 * ABS_NOISE_S,
              steer=2)
    assert compare(live, _g()) is None


def test_compare_exactly_at_noise_is_none():
    # alla soglia e' ancora rumore: serve superarla
    live = _g(release=1.0 + RELEASE_NOISE_S)
    assert compare(live, _g()) is None


def test_compare_release_beats_gear():
    # rilascio a 2x la soglia, marcia diversa (rapporto 1,0) -> vince il rilascio
    live = _g(release=1.0 + 2 * RELEASE_NOISE_S, gear="4")
    note = compare(live, _g())
    assert isinstance(note, GestureNote)
    assert note.kind == "release"
    assert abs(note.score - 2.0) < 1e-9
    assert abs(note.live - (1.0 + 2 * RELEASE_NOISE_S)) < 1e-9
    assert note.ref == 1.0


def test_compare_gear_alone_is_said():
    # Decisione 2: una marcia diversa e' un gesto diverso anche da sola
    note = compare(_g(gear="4"), _g(gear="3"))
    assert note is not None
    assert (note.kind, note.live, note.ref, note.score) == ("gear", "4", "3", 1.0)


def test_compare_gear_non_numeric_ignored():
    # un «N» o una marcia mancante non e' una marcia diversa
    assert compare(_g(gear="N"), _g(gear="3")) is None
    assert compare(_g(gear=None), _g(gear="3")) is None


def test_compare_none_on_one_side_not_compared():
    # tu freni, lui no: il rilascio non si confronta
    assert compare(_g(release=3.0), _g(release=None)) is None
    assert compare(_g(pickup=None), _g(pickup=5.0)) is None


def test_compare_highest_ratio_wins():
    live = _g(release=1.0 + 1.5 * RELEASE_NOISE_S,
              abs_=0.2 + 3 * ABS_NOISE_S,
              steer=2 + 2 * STEER_NOISE)
    note = compare(live, _g())
    assert note.kind == "abs" and abs(note.score - 3.0) < 1e-9


def test_compare_tie_follows_corner_order():
    # stesso rapporto (2,0 esatto: riferimento a zero) su tutte le misure:
    # vince l'ordine della curva, freno, ABS, marcia, sterzo, gas
    zero = _g(release=0.0, pickup=0.0, abs_=0.0, steer=0)
    two = dict(release=2 * RELEASE_NOISE_S, pickup=2 * PICKUP_NOISE_S,
               abs_=2 * ABS_NOISE_S, steer=int(2 * STEER_NOISE))
    assert compare(_g(**two), zero).kind == "release"
    two["release"] = 0.0
    assert compare(_g(**two), zero).kind == "abs"
    two["abs_"] = 0.0
    assert compare(_g(**two), zero).kind == "steer"
    two["steer"] = 0
    assert compare(_g(**two), zero).kind == "pickup"


def test_compare_slower_side_also_counts():
    # la differenza e' assoluta: anche rilasciare piu' in fretta e' diverso
    note = compare(_g(release=3.0 - 2 * RELEASE_NOISE_S), _g(release=3.0))
    assert note.kind == "release" and abs(note.score - 2.0) < 1e-9


# --- Task 3: il report dice il gesto (coaching/debrief.py) -----------------

def _shape_release(lap, corner, steps):
    """Nella curva, un picco di freno a 0,95 e poi giu' a zero in ``steps``
    campioni: il rilascio dura ``steps`` passi dell'orologio del giro."""
    zone = [s for s in lap.samples if corner.entry_pos <= s.pos < corner.apex_pos]
    k = len(zone) // 2
    zone[k].brake = 0.95
    for j, s in enumerate(zone[k + 1:], start=1):
        s.brake = max(0.0, 0.95 * (1 - j / steps))
    return lap


def _release_case(live_steps=4, ref_steps=16):
    import synth
    from accoach.track import detect_corners
    ref_lap = synth.build_lap(n=2001)            # passo 50 ms
    corners = detect_corners(ref_lap.samples)
    _shape_release(ref_lap, corners[0], ref_steps)              # 0,80 s
    review = synth.build_lap(slow_corner=0, amt=30, n=2001)    # passo 56 ms
    _shape_release(review, corners[0], live_steps)             # 0,224 s
    return review, ref_lap, corners


def _corner(deb, index):
    return next((x for x in deb.losses if x.index == index), None)


def test_debrief_says_the_brake_release_in_italian():
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.comparison import Reference
    review, ref_lap, corners = _release_case()
    loss = _corner(build_lap_debrief(review, Reference(ref_lap), corners, "it"), 0)
    assert loss is not None
    assert loss.gesture is not None and loss.gesture.kind == "release"
    assert loss.detail.endswith(
        " Rilasci il freno in 0,2 s, il riferimento in 0,8 s.")


def test_debrief_says_the_brake_release_in_english():
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.comparison import Reference
    review, ref_lap, corners = _release_case()
    loss = _corner(build_lap_debrief(review, Reference(ref_lap), corners, "en"), 0)
    assert loss.detail.endswith(
        " You release the brake in 0.2 s, the reference in 0.8 s.")


def test_release_within_noise_says_nothing():
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.comparison import Reference
    # 4 passi da 56 ms contro 6 da 50 ms: 0,08 s, sotto il rumore
    review, ref_lap, corners = _release_case(live_steps=4, ref_steps=6)
    loss = _corner(build_lap_debrief(review, Reference(ref_lap), corners, "it"), 0)
    assert loss.gesture is None
    assert "Rilasci il freno" not in loss.detail


def test_gesture_sentences_one_per_kind():
    from accoach.coaching.debrief import gesture_text
    cases = [
        (GestureNote("release", 0.2, 0.8, 1.5),
         "Rilasci il freno in 0,2 s, il riferimento in 0,8 s.",
         "You release the brake in 0.2 s, the reference in 0.8 s."),
        (GestureNote("pickup", 1.24, 0.5, 1.7),
         "Apri il gas in 1,2 s, il riferimento in 0,5 s.",
         "You open the throttle in 1.2 s, the reference in 0.5 s."),
        (GestureNote("gear", "3", "2", 1.0),
         "All'apex sei in 3ª, il riferimento in 2ª.",
         "At the apex you're in 3rd, the reference in 2nd."),
        (GestureNote("abs", 1.5, 0.0, 4.0),
         "L'ABS lavora 1,5 s, nel riferimento 0,0 s.",
         "ABS is active for 1.5 s, in the reference 0.0 s."),
        (GestureNote("steer", 4, 1, 3.0),
         "Correggi lo sterzo 4 volte, il riferimento 1.",
         "You correct the steering 4 times, the reference 1."),
    ]
    for note, it, en in cases:
        assert gesture_text(note, "it") == " " + it
        assert gesture_text(note, "en") == " " + en


def test_gesture_sentence_ordinals_and_singular():
    from accoach.coaching.debrief import gesture_text
    en = [gesture_text(GestureNote("gear", g, "4", 1.0), "en")
          for g in ("1", "2", "3", "5", "11", "12", "13")]
    assert [s.split(" in ")[1].split(",")[0] for s in en] == [
        "1st", "2nd", "3rd", "5th", "11th", "12th", "13th"]
    assert gesture_text(GestureNote("steer", 1, 3, 2.0), "it") == \
        " Correggi lo sterzo una volta, il riferimento 3."
    assert gesture_text(GestureNote("steer", 1, 3, 2.0), "en") == \
        " You correct the steering once, the reference 3."


def test_gesture_uses_the_corner_reference_and_stays_before_the_comparison():
    """Con ``corner_refs`` la misura del riferimento viene dal giro della curva.

    Il principale rilascia di colpo come te: contro di lui niente frase. Il tuo
    gesto migliore in curva 1 rilascia piano: contro di lui la frase c'e', e
    sta prima di «Confronto con la tua migliore…», che resta l'ultima."""
    import synth
    from accoach.coaching.corner_refs import CornerBests
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.comparison import Reference
    from accoach.track import detect_corners
    main = synth.build_lap(slow_corner=0, amt=20, n=2001)
    corners = detect_corners(main.samples)
    _shape_release(main, corners[0], 4)
    best = synth.build_lap(n=2001)
    _shape_release(best, corners[0], 16)
    best.lap_time_ms = 108_912
    bests = CornerBests(Reference(main), corners)
    assert bests.offer(best) is True
    assert bests.at(corners[0].apex_pos) is not None
    review = synth.build_lap(slow_corner=0, amt=30, n=2001)
    _shape_release(review, corners[0], 4)

    plain = _corner(build_lap_debrief(review, Reference(main), corners, "it"), 0)
    assert plain is None or plain.gesture is None

    loss = _corner(build_lap_debrief(review, Reference(main), corners, "it",
                                     corner_refs=bests), 0)
    assert loss.gesture is not None and loss.gesture.kind == "release"
    assert loss.detail.endswith(
        " Rilasci il freno in 0,2 s, il riferimento in 0,8 s."
        " Confronto con la tua migliore in questa curva, dal giro in 1:48,912.")


def test_report_endpoint_carries_the_gesture(tmp_path):
    """Il JSON delle perdite e' scritto campo per campo: senza la voce
    ``gesture`` il dato si sarebbe perso a meta' strada."""
    from fastapi.testclient import TestClient
    from accoach.api import create_api
    from accoach.recording.storage import save_lap
    review, ref_lap, _corners = _release_case()
    paths = {}
    for name, lap, minute in (("ref", ref_lap, 1), ("review", review, 2)):
        lap.clean = True
        lap.recorded_utc = f"2026-11-01T10:{minute:02d}:00+00:00"
        paths[name] = str(save_lap(lap, tmp_path))
    c = TestClient(create_api(tmp_path))
    r = c.get("/api/analysis", params={"car": "ferrari_488_gt3",
                                       "track": "monza", "lang": "it",
                                       "lap": paths["review"],
                                       "baseline": paths["ref"]})
    assert r.status_code == 200, r.text
    by_index = {x["index"]: x for x in r.json()["losses"]}
    g = by_index[0]["gesture"]
    assert g["kind"] == "release"
    assert abs(g["live"] - 0.224) < 0.01 and abs(g["ref"] - 0.8) < 0.01
    assert "Rilasci il freno in 0,2 s" in by_index[0]["detail"]
    assert all(x["gesture"] is None for i, x in by_index.items() if i != 0)
