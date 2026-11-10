"""La sessione curva per curva: aggregazione pura, nessun file."""
from accoach.braking_points import BrakePoint
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss
from accoach.coaching.phases import PhaseLoss
from accoach.coaching.corner_session import LapCorners, aggregate
from accoach.trajectory import CornerLine


def loss(index=0, ms=100.0, cat=CueCategory.BRAKE_LATER, msg="m", phases=()):
    return CornerLoss(index=index, entry_pos=0.0, apex_pos=0.0, exit_pos=0.0,
                      lost_ms=ms, category=cat, message=msg,
                      phases=[PhaseLoss(phase=p, lost_ms=v) for p, v in phases])


def brake(index=0, dist=90.0, kmh=200.0, gear="3"):
    return BrakePoint(index=index, onset_pos=0.0, speed_kmh=kmh, gear="4",
                      distance_m=dist, vmin_kmh=80.0, gear_min=gear,
                      peak_brake=1.0)


def line(index=0, entry=1.0, apex=2.0, exit_=3.0, off=False, sided=True,
         shift=0.0):
    return CornerLine(index=index, name="", direction="left", kind="corner",
                      entry=0.0, apex=0.0, exit=0.0, entry_m=entry,
                      apex_m=apex, exit_m=exit_, apex_shift_m=shift,
                      sided=sided, off_here=off)


def lap(path, losses=(), brakes=(), lines=()):
    return LapCorners(path, list(losses), list(brakes), list(lines))


def test_ordine_per_tempo_perso():
    laps = [lap("a", [loss(0, 120), loss(2, 300)])]
    assert [s.index for s in aggregate(laps)] == [2, 0]


def test_causa_di_solito_solo_se_torna_in_meta_dei_giri():
    A = CueCategory.BRAKE_LATER
    B = CueCategory.CARRY_SPEED
    C = CueCategory.LESS_BRAKE
    D = CueCategory.MORE_THROTTLE
    due = [lap(p, [loss(0, 200, c, "msg " + p)])
           for p, c in zip("abcd", [A, A, B, C])]
    s = aggregate(due)[0]
    assert (s.cause, s.cause_laps, s.cause_message) == ("brake_later", 2, "msg b")
    una = [lap(p, [loss(0, 200, c)]) for p, c in zip("abcd", [A, B, C, D])]
    assert aggregate(una)[0].cause is None


def test_fasi_mediane():
    laps = [lap(p, [loss(0, 300, phases=[("entry", v), ("apex", 20)])])
            for p, v in zip("abc", [100, 300, 200])]
    assert aggregate(laps)[0].phases_ms["entry"] == 200


def test_frenata_mediana_e_dispersione():
    laps = [lap(p, [loss(0, 10)], brakes=[brake(0, d)])
            for p, d in zip("abcd", [80, 90, 100, 0])]
    s = aggregate(laps)[0]
    assert (s.brake_m, s.brake_spread_m) == (90, 20)


def _gear(gears):
    laps = [lap(str(i), [loss(0)], brakes=[brake(0, gear=x)])
            for i, x in enumerate(gears)]
    return aggregate(laps)[0].gear_min


def test_marcia_piu_frequente():
    assert _gear(["3", "3", "2"]) == "3"
    assert _gear(["2", "3"]) == "2"


def test_giro_migliore_e_tipico():
    laps = [lap(p, [loss(0, v)]) for p, v in zip("abcd", [50, 200, 210, 400])]
    s = aggregate(laps)[0]
    assert (s.best_path, s.typical_path) == ("a", "b")
    assert s.lost_total_ms == 860 and s.laps_losing == 3


def test_un_giro_solo():
    s = aggregate([lap("x", [loss(0, 180, phases=[("entry", 180)])],
                       [brake(0, 85, 190, "2")], [line(0, shift=1.5)])])[0]
    assert s.laps == 1 and s.typical_path == s.best_path == "x"
    assert (s.brake_m, s.brake_kmh, s.gear_min) == (85, 190, "2")
    assert s.brake_spread_m == 0 and s.apex_shift_m == 1.5
    assert s.line_m == {"entry": 1.0, "apex": 2.0, "exit": 3.0}


def test_fuori_pista_non_conta_per_la_linea():
    laps = [lap("a", [loss(0)], lines=[line(0, 1, 2, 3)]),
            lap("b", [loss(0)], lines=[line(0, 99, 99, 99, off=True)])]
    assert aggregate(laps)[0].line_m == {"entry": 1, "apex": 2, "exit": 3}
