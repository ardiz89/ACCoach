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


def lap(path, losses=(), brakes=(), lines=(), deltas=None):
    return LapCorners(path, list(losses), list(brakes), list(lines),
                      dict(deltas or {}))


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


def test_dentro_fuori_e_destra_sinistra_non_si_mescolano():
    laps = [lap("a", [loss(0, 100)], lines=[line(apex=1.0, sided=True)]),
            lap("b", [loss(0, 100)], lines=[line(apex=-9.0, sided=False)]),
            lap("c", [loss(0, 100)], lines=[line(apex=3.0, sided=True)])]
    s = aggregate(laps)[0]
    assert s.sided is True and s.line_m["apex"] == 2.0
    solo = aggregate([lap("b", [loss(0, 100)], lines=[line(apex=-9.0, sided=False)])])[0]
    assert solo.sided is False and solo.line_m["apex"] == -9.0


# --- ogni giro in ogni curva, non solo quelli che perdono -------------------

def test_conta_anche_i_giri_che_guadagnano():
    # 60 ms e' sotto la soglia del debrief, -300 e' un guadagno: nessuno dei
    # due ha una riga di perdita, ma sono giri in quella curva.
    laps = [lap("a", deltas={0: 60.0}),
            lap("b", deltas={0: -300.0}),
            lap("c", [loss(0, 130)], deltas={0: 130.0})]
    s = aggregate(laps)[0]
    assert s.laps == 3 and s.laps_losing == 1
    assert s.lost_total_ms == -110
    assert s.best_path == "b"
    assert s.typical_path == "a"          # mediana 60


def test_curva_mai_persa_resta_in_elenco():
    laps = [lap("a", [loss(1, 400)], deltas={0: -50.0, 1: 400.0}),
            lap("b", deltas={0: -20.0, 1: 10.0})]
    out = aggregate(laps)
    assert [s.index for s in out] == [1, 0]
    s0 = out[1]
    assert (s0.laps, s0.laps_losing, s0.lost_total_ms) == (2, 0, -70)
    assert s0.cause is None and s0.best_path == "a"


def test_soglia_come_nel_debrief():
    from accoach.coaching.analyzer import _LOSS_MS
    from accoach.coaching import corner_session
    assert corner_session.NOISE_MS == _LOSS_MS


def test_tipico_a_pari_distanza_il_primo():
    laps = [lap("a", deltas={0: 100.0}), lap("b", deltas={0: 300.0})]
    assert aggregate(laps)[0].typical_path == "a"


def test_causa_e_fasi_solo_dai_giri_che_perdono():
    A = CueCategory.BRAKE_LATER
    laps = [lap("a", [loss(0, 200, A, phases=[("entry", 200)])],
                deltas={0: 200.0}),
            lap("b", deltas={0: -100.0}),
            lap("c", deltas={0: -150.0})]
    s = aggregate(laps)[0]
    assert s.laps == 3 and s.laps_losing == 1
    assert s.cause == "brake_later" and s.cause_laps == 1
    assert s.phases_ms == {"entry": 200}


def test_corner_deltas_uguale_al_debrief():
    import synth
    from accoach.comparison.reference import Reference
    from accoach.coaching.debrief import build_lap_debrief, corner_deltas
    from accoach.track import detect_corners
    base = synth.build_lap()
    ref = Reference(base)
    corners = detect_corners(base.samples)
    for slow in (0, 1):
        live = synth.build_lap(slow_corner=slow, amt=25)
        deltas = corner_deltas(live, ref, corners)
        assert set(deltas) == {c.index for c in corners}
        losses = build_lap_debrief(live, ref, corners, "it").losses
        assert losses
        for x in losses:
            assert deltas[x.index] == x.lost_ms


def test_corner_deltas_col_gesto_migliore():
    import synth
    from accoach.comparison.reference import Reference
    from accoach.coaching.corner_refs import CornerRef
    from accoach.coaching.debrief import build_lap_debrief, corner_deltas
    from accoach.track import detect_corners
    base = synth.build_lap()
    ref = Reference(base)
    corners = detect_corners(base.samples)
    other = Reference(synth.build_lap(slow_corner=1, amt=30))

    class Refs:
        def at(self, pos):
            return CornerRef(other, 0.0, 0.0, other.lap_time_ms)

    live = synth.build_lap(slow_corner=0, amt=40)
    plain = corner_deltas(live, ref, corners)
    deltas = corner_deltas(live, ref, corners, Refs())
    assert deltas != plain
    for x in build_lap_debrief(live, ref, corners, "it",
                               corner_refs=Refs()).losses:
        assert deltas[x.index] == x.lost_ms


def test_ordine_per_giro_tipico_non_per_somma():
    # Curva 0: un giro solo perde tanto (una sosta, un errore). Curva 2: tutti
    # i giri perdono un po'. Di solito si perde di più alla 2.
    laps = [lap("a", deltas={0: 9000, 2: 300}),
            lap("b", deltas={0: 10, 2: 300}),
            lap("c", deltas={0: 10, 2: 300})]
    out = aggregate(laps)
    assert [s.index for s in out] == [2, 0]
    assert out[0].lost_median_ms == 300 and out[1].lost_median_ms == 10
    assert out[1].lost_total_ms == 9020
