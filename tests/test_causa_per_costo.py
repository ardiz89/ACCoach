"""La causa di una curva la sceglie quanto costa la sua fase, non un ordine fisso.

Oggi `classify_corner` prova le cause in un ordine fisso e la prima vera vince:
una frenata anticipata di pochi metri batteva un'uscita senza gas che costava
sei volte tanto. Con le fasi (entry/apex/exit/after, la stessa scomposizione di
`phases.py`) ogni causa ha un prezzo, e vince quella che costa di piu'.
"""
from accoach.coaching import analyzer as analyzer_mod
from accoach.coaching.analyzer import CoachAnalyzer, CornerStats, classify_corner
from accoach.coaching.cue import CueCategory
from accoach.coaching.diagnosis import _APEX_HALF
from accoach.comparison import LapComparator, Reference
from accoach.track import detect_corners

import synth


def _st(**kw):
    base = dict(lost_ms=300.0, throttle_live=0.5, throttle_ref=0.5, brake_live=0.2,
                brake_ref=0.2, min_speed_live=100.0, min_speed_ref=100.0,
                braking_early=False, braking_late=False, phase_ms=None)
    return CornerStats(**{**base, **kw})


def test_the_most_expensive_cause_wins_over_the_fixed_order():
    # frenata anticipata (entry 40 ms) e gas mancante (exit 260 ms): oggi vince la frenata
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6,
             phase_ms={"entry": 40.0, "apex": 0.0, "exit": 260.0, "after": 0.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.MORE_THROTTLE


def test_a_cause_whose_phase_gained_time_is_not_the_cause():
    st = _st(braking_early=True,
             phase_ms={"entry": -80.0, "apex": 150.0, "exit": 230.0, "after": 0.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.TIME_LOSS


def test_without_phases_the_old_order_holds():
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6)
    assert classify_corner(st, 0, 0.5).category is CueCategory.BRAKE_LATER


def test_a_tie_keeps_the_old_order():
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6,
             phase_ms={"entry": 150.0, "apex": 0.0, "exit": 150.0, "after": 0.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.BRAKE_LATER


def test_the_fallback_keeps_todays_message_and_voice():
    # Nessuna candidata paga: il ramo TIME_LOSS e' quello di oggi, cifra e voce.
    st = _st(lost_ms=2900.0, braking_early=True,
             phase_ms={"entry": -10.0, "apex": 0.0, "exit": 2910.0, "after": 0.0})
    cue = classify_corner(st, 0, 0.5)
    assert cue.category is CueCategory.TIME_LOSS
    assert cue.message == "Qui perdi 29 decimi"
    assert cue.voice == "Qui perdi più di due secondi e mezzo"


def test_good_and_the_threshold_come_before_the_phases():
    gain = _st(lost_ms=-300.0, braking_early=True,
               phase_ms={"entry": 50.0, "apex": 0.0, "exit": -350.0, "after": 0.0})
    assert classify_corner(gain, 0, 0.5).category is CueCategory.GOOD
    small = _st(lost_ms=100.0, braking_early=True,
                phase_ms={"entry": 100.0, "apex": 0.0, "exit": 0.0, "after": 0.0})
    assert classify_corner(small, 0, 0.5) is None


def test_after_counts_for_the_throttle():
    # Il gas mancante si paga sul rettilineo dopo: `after` e' sua.
    st = _st(braking_early=True, throttle_live=0.3, throttle_ref=0.6,
             phase_ms={"entry": 100.0, "apex": 0.0, "exit": 0.0, "after": 200.0})
    assert classify_corner(st, 0, 0.5).category is CueCategory.MORE_THROTTLE


def test_live_zone_records_its_three_phases(monkeypatch):
    """Dal vivo la zona taglia il suo delta ai bordi della finestra dell'apex.

    La perdita e' messa tutta dopo `apex + _APEX_HALF`: entry e apex devono
    restare a zero, exit deve portare tutta la perdita, e `after` dal vivo non
    esiste (la zona finisce a `exit_pos`).
    """
    ref = Reference(synth.build_lap())
    an = CoachAnalyzer()
    an.set_corners(detect_corners(ref.lap.samples))
    cmp = LapComparator(ref)
    lo, hi, mid = an._zones[0]
    start = mid + _APEX_HALF + 0.005
    assert start < hi - 0.01, "la zona deve avere un tratto d'uscita dopo l'apex"

    seen: list[CornerStats] = []
    real = analyzer_mod.classify_corner

    def spy(st, index, pos):
        if index == 0:
            seen.append(st)
        return real(st, index, pos)

    monkeypatch.setattr(analyzer_mod, "classify_corner", spy)

    lap = synth.build_lap()
    for smp in lap.samples:
        # La perdita cresce dopo l'apex e resta: 300 ms a fine zona.
        extra = 0
        if smp.pos >= start:
            extra = int(300 * min(1.0, (smp.pos - start) / (hi - start)))
        s = synth.snap(pos=smp.pos, current_lap_ms=smp.t_ms + extra,
                       speed_kmh=smp.speed_kmh, throttle=smp.throttle,
                       brake=smp.brake, steer_angle=smp.steer_angle, gear=smp.gear)
        an.update(s, cmp.compare(s))

    assert seen, "la curva 0 deve chiudersi"
    st = seen[0]
    assert st.phase_ms is not None
    assert set(st.phase_ms) == {"entry", "apex", "exit", "after"}
    assert st.lost_ms > 200.0
    assert abs(st.phase_ms["entry"]) < 1.0
    assert abs(st.phase_ms["apex"]) < 1.0
    assert abs(st.phase_ms["exit"] - st.lost_ms) < 1.0
    assert st.phase_ms["after"] == 0.0
    # Una scomposizione, non una stima: le fasi risommano la perdita.
    assert abs(sum(st.phase_ms.values()) - st.lost_ms) < 1e-6


def test_debrief_passes_its_phases(monkeypatch):
    """Il debrief da' a `classify_corner` le stesse fasi che pubblica."""
    from accoach.coaching import debrief as debrief_mod
    seen: list[CornerStats] = []
    real = debrief_mod.classify_corner

    def spy(st, index, pos):
        seen.append(st)
        return real(st, index, pos)

    monkeypatch.setattr(debrief_mod, "classify_corner", spy)
    ref = Reference(synth.build_lap())
    review = synth.build_lap(slow_corner=0, amt=30)
    debrief_mod.build_lap_debrief(review, ref, detect_corners(ref.lap.samples))
    assert seen
    for st in seen:
        assert st.phase_ms is not None
        assert set(st.phase_ms) == {"entry", "apex", "exit", "after"}
        assert abs(sum(st.phase_ms.values()) - st.lost_ms) < 1.0
