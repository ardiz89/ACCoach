"""Cross-lap analysis: systematic vs sporadic losses + the benchmark ladder."""
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.trends import (
    benchmark_levels,
    classify_losses,
    session_recap,
    session_series,
)
from accoach.coaching.phases import PHASES, lap_time_split
from accoach.comparison import Reference
from accoach.track import detect_corners

import pytest

import synth


def _loss(index: int, ms: float, category: CueCategory = CueCategory.BRAKE_LATER) -> CornerLoss:
    return CornerLoss(index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4,
                      lost_ms=ms, category=category, message="m")


def _debrief(*losses: CornerLoss) -> LapDebrief:
    return LapDebrief("car", "track", 101000, 100000, losses=list(losses))


# --- systematic vs sporadic ------------------------------------------------

def test_recurring_loss_is_systematic():
    debriefs = [_debrief(_loss(0, 300)) for _ in range(4)]
    trends = classify_losses(debriefs)
    assert len(trends) == 1
    assert trends[0].corner_index == 0
    assert trends[0].systematic is True
    assert trends[0].kind == "systematic"
    assert trends[0].occurrences == 4


def test_one_off_loss_is_sporadic():
    # Big loss, but only once in four laps → not a weakness to train.
    debriefs = [_debrief(_loss(0, 900)), _debrief(), _debrief(), _debrief()]
    trends = classify_losses(debriefs)
    assert trends[0].systematic is False
    assert trends[0].kind == "sporadic"


def test_small_recurring_loss_is_not_systematic():
    debriefs = [_debrief(_loss(0, 50)) for _ in range(4)]   # recurs but trivial
    trends = classify_losses(debriefs)
    assert trends[0].systematic is False


def test_half_the_laps_really_means_half():
    """A loss in 2 laps out of 5 is 40% — it must not read as "systematic".

    Regression: recur_min used round(), and Python rounds half to even, so
    round(0.5 * 5) == 2 and the promised >=50% quietly became 40%. Same at n=9,
    where round(4.5) == 4 gave 44%.
    """
    for n, occurrences in ((5, 2), (9, 4)):
        debriefs = ([_debrief(_loss(0, 300))] * occurrences
                    + [_debrief()] * (n - occurrences))
        trends = classify_losses(debriefs)
        assert trends[0].occurrences == occurrences
        assert trends[0].systematic is False, f"{occurrences}/{n} is under half"


def test_exactly_half_the_laps_is_systematic():
    # The boundary itself stays inclusive: 3/6 is >= 50% and still counts.
    debriefs = [_debrief(_loss(0, 300))] * 3 + [_debrief()] * 3
    trends = classify_losses(debriefs)
    assert trends[0].systematic is True


def test_trends_sorted_by_total_cost():
    debriefs = [
        _debrief(_loss(0, 150), _loss(1, 400)),
        _debrief(_loss(0, 150), _loss(1, 400)),
        _debrief(_loss(0, 150), _loss(1, 400)),
    ]
    trends = classify_losses(debriefs)
    assert [t.corner_index for t in trends] == [1, 0]       # corner 1 costs more
    assert all(t.systematic for t in trends)


def test_dominant_category_wins():
    debriefs = [
        _debrief(_loss(0, 300, CueCategory.BRAKE_LATER)),
        _debrief(_loss(0, 300, CueCategory.BRAKE_LATER)),
        _debrief(_loss(0, 300, CueCategory.CARRY_SPEED)),
    ]
    assert classify_losses(debriefs)[0].category is CueCategory.BRAKE_LATER


def test_empty_debriefs():
    assert classify_losses([]) == []


# --- benchmark levels ------------------------------------------------------

def test_levels_best_only():
    levels = benchmark_levels(90000)
    assert [lv.key for lv in levels] == ["best"]
    assert levels[0].gain_ms == 0


def test_levels_with_ideal_and_pro():
    levels = benchmark_levels(90000, ideal_ms=89000, pro_ms=88000)
    keys = {lv.key: lv for lv in levels}
    assert set(keys) == {"best", "ideal", "pro"}
    assert keys["ideal"].gain_ms == 1000        # 1.0s of consistency available
    assert keys["pro"].gain_ms == 2000          # 2.0s to the PRO ceiling


def test_levels_pro_slower_than_you_is_negative_gain():
    levels = benchmark_levels(88000, pro_ms=90000)   # you beat the imported PRO
    pro = next(lv for lv in levels if lv.key == "pro")
    assert pro.gain_ms == -2000


def test_levels_empty_without_best():
    assert benchmark_levels(0) == []


def test_level_labels_translate():
    en = {lv.key: lv.label for lv in benchmark_levels(90000, ideal_ms=89000, lang="en")}
    it = {lv.key: lv.label for lv in benchmark_levels(90000, ideal_ms=89000, lang="it")}
    assert en["best"] == "Your best lap" and it["best"] == "Tuo miglior giro"
    assert it["ideal"] == "Ideale teorico"


# --- la serie per sessione -------------------------------------------------

_T = "2026-08-0{d}T{h}:{m}:00+00:00"


def _deb(lost_ms):
    """Un giro: con una perdita alla curva 0, oppure preso bene (lost_ms = 0)."""
    return _debrief(_loss(0, lost_ms)) if lost_ms else _debrief()


def _evening(day, hour, losses):
    """Una sessione: giri a due minuti l'uno dall'altro."""
    return [(_T.format(d=day, h=hour, m=f"{2 * i:02d}"), _deb(v))
            for i, v in enumerate(losses)]


def test_three_sessions_that_improve_read_as_a_falling_series():
    dated = (_evening(1, "18", [400, 380, 420]) +
             _evening(2, "18", [250, 230, 270]) +
             _evening(3, "18", [120, 100, 140]))
    pts = session_series(dated, 0)
    assert [p.median_ms for p in pts] == [400.0, 250.0, 120.0]
    assert pts[0].started < pts[-1].started        # dal più vecchio al più recente


def test_two_runs_the_same_afternoon_stay_two_points():
    """Se cambi qualcosa fra l'una e l'altra, lo devi poter vedere."""
    dated = _evening(1, "15", [400, 400, 400]) + _evening(1, "18", [200, 200, 200])
    assert len(session_series(dated, 0)) == 2


def test_a_session_without_that_corner_is_absent_not_a_zero():
    """Il buco a zero direbbe 'curva perfetta' dove invece non c'è il dato."""
    dated = _evening(1, "18", [400, 400, 400]) + _evening(2, "18", [0, 0])
    pts = session_series(dated, 0)
    assert len(pts) == 1                     # la seconda ha solo 2 giri: sotto min_laps
    dated2 = _evening(1, "18", [400, 400, 400]) + _evening(2, "18", [0, 0, 0])
    pts2 = session_series(dated2, 0)
    assert [p.median_ms for p in pts2] == [400.0, 0.0]   # tre giri buoni SONO un dato


def test_a_good_lap_counts_as_zero_not_as_missing():
    """Migliorare vuol dire anche sbagliare quella curva meno spesso."""
    dated = _evening(1, "18", [400, 0, 0])
    assert session_series(dated, 0)[0].median_ms == 0.0


def test_a_session_below_the_minimum_is_dropped():
    assert session_series(_evening(1, "18", [400, 400]), 0) == []


def test_undated_laps_are_dropped_not_guessed_into_a_session():
    dated = [("", _deb(400))] + _evening(1, "18", [200, 200, 200])
    pts = session_series(dated, 0)
    assert len(pts) == 1 and pts[0].median_ms == 200.0


# --- il recap di una sessione ----------------------------------------------


def _recap(amts):
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in amts]
    return session_recap(laps, Reference(ref_lap), corners)


def test_the_families_add_up_to_the_average_gap():
    """Con i float pieni la media delle somme È la somma delle medie: nessun
    margine largo qui, solo il rumore in virgola mobile (misurato: 0.0 su
    diverse combinazioni di giri e griglie, vedi il report)."""
    r = _recap([10, 20, 30])
    total = sum(r.by_phase.values()) + r.launch_ms
    assert abs(total - r.gain_avg_ms) < 1e-6


def test_one_row_per_lap_with_its_worst_corner():
    r = _recap([10, 20, 30])
    assert len(r.laps) == 3
    assert all(l.worst_index >= 0 for l in r.laps)
    assert r.laps[2].gap_ms > r.laps[0].gap_ms  # amt=30 perde più di amt=10


def test_the_worst_corner_is_the_one_that_cost_most():
    r = _recap([30])
    assert r.laps[0].worst_index == 0           # synth rallenta la curva 0


def test_no_laps_no_recap():
    ref_lap = synth.build_lap()
    assert session_recap([], Reference(ref_lap),
                         detect_corners(ref_lap.samples)) is None


def test_a_lap_the_split_cannot_read_is_skipped_not_faked():
    """Un giro senza abbastanza campioni non entra: meglio due righe vere che
    tre con una inventata. ``len(r.laps) == 1`` da solo non basta a provarlo:
    il giro scartato potrebbe restare dentro i denominatori delle medie senza
    comparire in ``laps``. Il confronto con una sessione che contiene SOLO il
    giro leggibile chiude anche quel buco."""
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    readable = synth.build_lap(slow_corner=0, amt=20)
    short = synth.build_lap()
    short.samples = short.samples[:2]
    reference = Reference(ref_lap)

    r = session_recap([readable, short], reference, corners)
    solo = session_recap([readable], reference, corners)

    assert len(r.laps) == 1
    assert r.gain_avg_ms == solo.gain_avg_ms
    assert r.launch_ms == solo.launch_ms
    assert r.by_phase == solo.by_phase


def test_worst_ms_is_not_rounded_and_reference_is_the_sessions_best():
    """Stessa trappola del Task 1: sulla griglia condivisa (stesso ``n`` per
    riferimento e giro) i ritardi tornano interi e ``round(x, 1)`` sarebbe
    un'operazione nulla, incapace di rilevare una regressione. Uno scarto fra
    l'``n`` del riferimento e quello del giro rompe la griglia e rende i
    ritardi genuinamente frazionari, così un ``round`` reintrodotto nel
    calcolo si vede.

    ``reference_ms`` deve essere il tempo del MIGLIOR giro della sessione (il
    riferimento passato), non quello di uno dei giri della lista.
    """
    ref_lap = synth.build_lap(n=397)
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    lap = synth.build_lap(slow_corner=0, amt=17)          # n=401 di default
    split = lap_time_split(lap, reference, corners)
    expected_worst = max(c.lost_ms for c in split.corners)
    assert expected_worst != int(expected_worst), "il fixture deve dare un valore frazionario"

    r = session_recap([lap], reference, corners)
    assert r.reference_ms == reference.lap_time_ms
    assert r.laps[0].worst_ms == expected_worst


def test_by_phase_launch_and_gain_avg_are_not_rounded():
    """I restanti tre siti di ``round(...)`` del piano originale: ``by_phase``
    (4 valori), ``launch_ms`` e ``gain_avg_ms``.

    Un margine largo come ``< 0.5`` su "la somma delle famiglie torna alla
    media del gap" NON può rilevare un arrotondamento reintrodotto qui, con
    NESSUN fixture: arrotondare in modo indipendente 4 famiglie + launch (un
    lato della somma) e gain_avg_ms (l'altro lato) sposta il confronto di al
    più 5*0.05 + 0.05 = 0.3ms per disuguaglianza triangolare, sempre sotto
    0.5ms. Serve un confronto diretto col valore medio ricalcolato a mano dai
    float pieni di ``lap_time_split``, non una verifica di somma.
    """
    # amt=(10, 20, 30) would NOT do here: gap_ms is read at the anchored
    # endpoints (pos 0.0 / 1.0), which Reference pins exactly no matter the
    # grid mismatch (see the comment on LapSplit.gap_ms in phases.py) — so a
    # gap_ms average, unlike the interior cuts, stays a round number even
    # off-grid whenever the amounts are evenly spaced (194/388/582 average to
    # exactly 388.0). An IRREGULAR amt sequence is what makes the three gaps
    # not divide evenly, and that is what makes gain_avg_ms itself fractional
    # — checked below, not assumed.
    ref_lap = synth.build_lap(n=397)
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in (10, 17, 30)]
    splits = [lap_time_split(lap, reference, corners) for lap in laps]
    n = len(splits)

    raw = ([s.launch_ms for s in splits] + [s.gap_ms for s in splits] +
           [v for s in splits for v in s.by_phase().values()])
    assert any(v != int(v) for v in raw), "il fixture deve dare valori frazionari"

    expected_launch = sum(s.launch_ms for s in splits) / n
    expected_gain = sum(s.gap_ms for s in splits) / n
    expected_by_phase = {p: sum(s.by_phase()[p] for s in splits) / n for p in PHASES}

    # The canary that matters is on the AVERAGED quantity being asserted, not
    # on its raw per-lap components: a component can be fractional while the
    # mean of several of them still lands on a clean tenth (exactly the trap
    # amt=(10, 20, 30) fell into for gain_avg_ms). round(x, 1) == x is a
    # no-op and would let a reintroduced round() through undetected.
    for name, value in [("launch", expected_launch), ("gain", expected_gain),
                        *expected_by_phase.items()]:
        assert round(value, 1) != value, \
            f"expected_{name} == its own round(x, 1): il fixture non prova nulla qui"

    r = session_recap(laps, reference, corners)
    assert r.launch_ms == pytest.approx(expected_launch, abs=1e-6)
    assert r.gain_avg_ms == pytest.approx(expected_gain, abs=1e-6)
    for p in PHASES:
        assert r.by_phase[p] == pytest.approx(expected_by_phase[p], abs=1e-6)
