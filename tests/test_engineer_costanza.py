"""L'Ingegnere giudica il gruppo: un giro guidato diversamente non conta (17/11).

Un giro pulito piu' lento degli altri giri dello stesso gruppo (stint e
manopole) di oltre 5 km/h di velocita' minima in almeno 3 curve non entra in
nessuna lettura, anche a posteriori. Giri finti con la velocita' minima curva
per curva e lo stint dalla benzina.
"""
from accoach import config
from accoach.engineer import DecisionKind, LapStats, RaceEngineer
from accoach.engineer.core import (AtomicChange, Balance, Phase,
                                   ProposedChange, Speed, Symptom)
from accoach.engineer.profiles import GT3_PROFILE

PRESS_OK = {"front": 26.5, "rear": 26.5}
OFF = {"front": 29.0, "rear": 26.5}
NAMES = ("Tamburello", "Villeneuve", "Tosa", "Piratella", "Acque Minerali",
         "Rivazza")
APEX = (0.05, 0.12, 0.22, 0.33, 0.45, 0.80)
BASE = 100.0
DIALS = (3, 4, 0, 0.64)


def _v(delta=0.0, at=()):
    """La velocita' minima delle sei curve: ``delta`` km/h nelle curve ``at``."""
    return tuple(BASE + (delta if i in at else 0.0) for i in range(len(NAMES)))


def _lap(fuel, speeds=None, press=PRESS_OK, dials=DIALS):
    speeds = _v() if speeds is None else speeds
    return LapStats(lap_time_ms=100000, stable=True, warmed_up=True,
                    pressures_hot=dict(press), fuel_l=fuel,
                    corner_vmin=tuple(zip(APEX, speeds, NAMES)), dials=dials)


def _eng(kmh=5.0):
    return RaceEngineer(GT3_PROFILE, min_stable=3, consistency_kmh=kmh)


def _has(window, lap):
    return any(s is lap for s in window)


def _drive(eng, laps):
    return [eng.observe(lap) for lap in laps]


def test_a_slow_lap_does_not_enter():
    eng = _eng()
    laps = [_lap(60), _lap(59), _lap(58), _lap(57),
            _lap(56, _v(-6, at=(2, 3, 4)))]
    _drive(eng, laps)
    assert not _has(eng.window, laps[4])
    assert all(_has(eng.window, s) for s in laps[:4])
    assert eng.last_dropped == [{
        "stint": 1, "stint_lap": 5, "last": True,
        "corners": [["Tosa", 6.0], ["Piratella", 6.0], ["Acque Minerali", 6.0]],
    }]


def test_an_earlier_lap_goes_after_the_fact():
    eng = _eng()
    laps = [_lap(60), _lap(59, _v(-6, at=(0, 1, 2))), _lap(58), _lap(57)]
    _drive(eng, laps[:3])
    assert eng.last_dropped == []
    eng.observe(laps[3])
    assert not _has(eng.window, laps[1])
    assert [s.stint_lap for s in eng.window] == [1, 3, 4]
    [gone] = eng.last_dropped
    assert (gone["stint"], gone["stint_lap"], gone["last"]) == (1, 2, False)
    assert [c[0] for c in gone["corners"]] == ["Tamburello", "Villeneuve", "Tosa"]


def test_a_lap_already_in_the_window_leaves_after_the_fact():
    # R2: giri 2-4 uguali e gia' in finestra; i giri 5-7 piu' veloci di 7 km/h
    # in 3 curve. Al 7° la mediana degli altri e' quella dei giri veloci, e i
    # giri 2-4 risultano piu' lenti: escono dalla finestra a posteriori.
    eng = _eng()
    fast = _v(+7, at=(0, 2, 4))
    laps = [_lap(60), _lap(59), _lap(58), _lap(57),
            _lap(56, fast), _lap(55, fast), _lap(54, fast)]
    _drive(eng, laps[:6])
    assert all(_has(eng.window, s) for s in laps[1:6])
    assert eng.last_dropped == []
    eng.observe(laps[6])
    # Escono prima che entri il 7°: il giro d'apertura non e' spinto fuori.
    assert [s.stint_lap for s in eng.window] == [1, 5, 6, 7]
    assert [(d["stint_lap"], d["last"]) for d in eng.last_dropped] == [
        (2, False), (3, False), (4, False)]
    assert eng.last_dropped[0]["corners"] == [
        ["Tamburello", 7.0], ["Tosa", 7.0], ["Acque Minerali", 7.0]]


def test_two_slow_corners_stay():
    eng = _eng()
    laps = [_lap(60), _lap(59), _lap(58), _lap(57),
            _lap(56, _v(-6, at=(2, 3)))]
    _drive(eng, laps)
    assert _has(eng.window, laps[4])
    assert eng.last_dropped == []


def test_faster_laps_stay():
    eng = _eng()
    laps = [_lap(60), _lap(59), _lap(58), _lap(57),
            _lap(56, _v(+10, at=range(6)))]
    _drive(eng, laps)
    assert all(_has(eng.window, s) for s in laps)
    assert eng.last_dropped == []


def test_opening_lap_is_neither_judged_nor_a_yardstick():
    eng = _eng()
    # Il giro d'apertura, piu' lento ovunque: non si giudica.
    laps = [_lap(60, _v(-10, at=range(6))), _lap(59), _lap(58), _lap(57)]
    for lap in laps:
        eng.observe(lap)
        assert eng.last_dropped == []
    assert all(_has(eng.window, s) for s in laps)
    # …e non fa da metro: uno piu' veloce di 12 km/h in 3 curve, se contasse,
    # farebbe sembrare lenti gli altri due fin dal 3° giro.
    eng = _eng()
    laps = [_lap(60, _v(+12, at=(0, 1, 2))), _lap(59), _lap(58), _lap(57)]
    for lap in laps:
        eng.observe(lap)
        assert eng.last_dropped == []
    assert all(_has(eng.window, s) for s in laps)


def test_waiting_laps_are_not_read_but_are_counted():
    config.set_language("it")
    eng = _eng()
    d = _drive(eng, [_lap(60, press=OFF), _lap(59, press=OFF),
                     _lap(58, press=OFF), _lap(57, press=OFF)])[-1]
    assert d.kind is DecisionKind.PROPOSE
    eng.mark_applied()
    # Dopo la sosta: il giro d'apertura, poi due giri che aspettano il terzo.
    after = [_lap(70), _lap(69), _lap(68)]
    said = []
    for lap in after:
        said.append(eng.observe(lap))
        if lap is after[1]:
            assert not _has(eng.window, lap)
            assert eng.progress()["have"] == 1
            assert eng.progress()["need"] == 3
    assert [d.kind for d in said] == [DecisionKind.EVALUATING] * 3
    assert "Servono ancora 3 giri puliti" in said[0].message
    assert "Servono ancora 2 giri puliti" in said[1].message
    assert "Serve ancora 1 giro pulito" in said[2].message


def test_the_baseline_after_a_stop_counts_down_too():
    config.set_language("it")
    eng = _eng()
    said = _drive(eng, [_lap(60), _lap(59), _lap(58)])
    # Il giro d'apertura conta, gli altri due aspettano il terzo giudicabile:
    # la base arriva al 4° giro e il conto lo dice, senza fermarsi.
    assert [d.kind for d in said] == [DecisionKind.COLLECT] * 3
    assert [s.stint_lap for s in eng.window] == [1]
    p = eng.progress()
    assert (p["have"], p["need"]) == (3, 4)
    assert "Servono 4 giri puliti" in said[2].message
    assert "per ora ne ho 3" in said[2].message
    assert eng.observe(_lap(57)).kind is not DecisionKind.COLLECT
    assert len(eng.window) == 4


def test_a_dial_turned_mid_stint_starts_a_group():
    eng = _eng()
    tc4 = (4, 4, 0, 0.64)
    slow = _v(-6, at=(0, 1, 2, 3))
    laps = ([_lap(60), _lap(59), _lap(58), _lap(57)]
            + [_lap(56, slow, dials=tc4), _lap(55, slow, dials=tc4),
               _lap(54, slow, dials=tc4)])
    for lap in laps:
        eng.observe(lap)
        assert eng.last_dropped == []
    assert [s.stint_lap for s in eng.window] == [2, 3, 4, 5, 6, 7]


def test_a_dial_turned_early_leaves_its_laps_quietly():
    eng = _eng()
    tc4 = (4, 4, 0, 0.64)
    early = [_lap(60), _lap(59), _lap(58, _v(-6, at=(0, 1, 2)))]
    later = [_lap(57, dials=tc4), _lap(56, dials=tc4), _lap(55, dials=tc4)]
    for lap in early + later:
        eng.observe(lap)
        assert eng.last_dropped == []
    # I due giri a TC 3 dopo l'apertura non si potevano giudicare: non entrano,
    # e nessuno dice che non contano.
    assert [s.stint_lap for s in eng.window] == [1, 4, 5, 6]


def test_a_balance_test_after_a_stop_counts_down():
    config.set_language("it")
    eng = _eng()
    _drive(eng, [_lap(60), _lap(59), _lap(58), _lap(57)])
    eng._pending = ProposedChange(
        (AtomicChange("aRBFront", None, -1),), "Soften the front bar 1 click.",
        "Mechanical", "BOX",
        Symptom(Balance.UNDERSTEER, Phase.APEX, Speed.LOW))
    eng.mark_applied()
    # Il giro d'apertura conta, i due dopo aspettano il terzo: il verdetto
    # arriva al 4° giro, e il conto scende senza fermarsi.
    seen = []
    for lap in [_lap(70), _lap(69), _lap(68)]:
        d = eng.observe(lap)
        p = eng.progress()
        seen.append((d.message, p["have"], p["need"]))
        assert d.kind is DecisionKind.EVALUATING
    assert [(h, n) for _, h, n in seen] == [(1, 4), (2, 4), (3, 4)]
    assert "Servono ancora 3 giri puliti" in seen[0][0]
    assert "Servono ancora 2 giri puliti" in seen[1][0]
    assert "Serve ancora 1 giro pulito" in seen[2][0]
    assert eng.active.laps_seen == 1
    d = eng.observe(_lap(67))
    assert d.kind is not DecisionKind.EVALUATING
    assert eng.active is None


def test_a_short_stint_leaves_quietly():
    eng = _eng()
    short = [_lap(60), _lap(59), _lap(58)]
    nxt = [_lap(70), _lap(69), _lap(68), _lap(67)]
    for lap in short + nxt:
        eng.observe(lap)
        assert eng.last_dropped == []
    assert not _has(eng.window, short[1]) and not _has(eng.window, short[2])
    assert _has(eng.window, short[0])
    assert all(_has(eng.window, s) for s in nxt)


def test_a_waiting_proposal_keeps_its_laps():
    eng = _eng()
    fast = _v(+8, at=(0, 1, 2))
    laps = [_lap(60, press=OFF), _lap(59, press=OFF), _lap(58, press=OFF),
            _lap(57, fast, press=OFF)]
    d = _drive(eng, laps)[-1]
    assert d.kind is DecisionKind.PROPOSE
    # Un altro giro veloce: ora la mediana degli altri e' quella veloce, e i
    # giri 2 e 3 risulterebbero lenti. La proposta e' calcolata su di loro.
    extra = _lap(56, fast, press=OFF)
    assert eng.observe(extra).kind is DecisionKind.PROPOSE
    assert eng.last_dropped == []
    assert all(_has(eng.window, s) for s in laps + [extra])
    eng.mark_applied()
    assert eng.active.base_pressures is not None


def test_a_dropped_test_lap_is_uncounted():
    eng = _eng()
    _drive(eng, [_lap(60), _lap(59), _lap(58), _lap(57)])
    # Una prova al volante: il TC sale di un click, e cambia il gruppo.
    eng._pending = ProposedChange(
        (AtomicChange("tC1", None, 1),), "Add 1 click of traction control.",
        "Electronics", "AV",
        Symptom(Balance.OVERSTEER, Phase.EXIT, Speed.LOW))
    eng.mark_applied()
    tc4 = (4, 4, 0, 0.64)
    t1 = _lap(56, (94, 94, 94, 100, 100, 100), dials=tc4)
    t2 = _lap(55, (94, 94, 100, 100, 100, 100), dials=tc4)
    t3 = _lap(54, (100, 100, 100, 94, 94, 94), dials=tc4)
    _drive(eng, [t1, t2, t3])
    # Il 3° giro della prova e' lento in 3 curve: gli altri due contano.
    assert eng.active.laps_seen == 2
    assert _has(eng.window, t1) and _has(eng.window, t2)
    # Il 4° rende lento il 1°, gia' contato, e lento e' anche lui.
    t4 = _lap(53, (106, 106, 100, 94, 94, 94), dials=tc4)
    d = eng.observe(t4)
    assert eng.active.laps_seen == 1
    assert not _has(eng.window, t1) and _has(eng.window, t2)
    assert d.kind is DecisionKind.EVALUATING
    assert [(x["stint_lap"], x["last"]) for x in eng.last_dropped] == [
        (5, False), (8, True)]


def test_without_the_switch_nothing_changes():
    config.set_language("it")
    laps = [_lap(60), _lap(59, _v(-6, at=(0, 1, 2))), _lap(58)]
    eng = _eng(kmh=None)
    said = _drive(eng, laps)
    assert eng.window == laps and all(a is b for a, b in zip(eng.window, laps))
    assert eng.last_dropped == []
    assert said[1].message.startswith(
        "Servono 3 giri puliti per avere una base e per ora ne ho 2.")
    # La base c'e' al 3° giro, come prima: si aspetta solo la lettura delle
    # pressioni, che non conta il giro d'apertura.
    assert eng.progress()["stage"] == "diagnose"
    assert said[2].message == (
        "Le pressioni si stanno ancora assestando. Serve ancora 1 giro pulito.")
    slow = _lap(57, _v(-6, at=(2, 3, 4)))
    eng.observe(slow)
    assert _has(eng.window, slow) and eng.last_dropped == []


def test_a_dropped_lap_never_comes_back():
    eng = _eng()
    laps = [_lap(60), _lap(59), _lap(58), _lap(57),
            _lap(56, _v(-6, at=(0, 1, 2)))]
    _drive(eng, laps)
    gone = laps[4]
    assert not _has(eng.window, gone)
    # Giri dopo, piu' lenti di 3 km/h nelle stesse curve: con loro il giro
    # tolto sembrerebbe normale. Non rientra, e non si ridice.
    for fuel in (55, 54, 53):
        eng.observe(_lap(fuel, _v(-3, at=(0, 1, 2))))
        assert not _has(eng.window, gone)
        assert eng.last_dropped == []


def test_every_lap_knows_its_place_in_the_stint():
    eng = _eng()
    laps = [_lap(60), _lap(59), _lap(70), _lap(69)]
    _drive(eng, laps)
    assert [(s.stint, s.stint_lap) for s in laps] == [(1, 1), (1, 2), (2, 1),
                                                      (2, 2)]


# --- la frase, su qualunque decisione ---------------------------------------

def _unnamed_lap(fuel, speeds):
    return LapStats(lap_time_ms=100000, stable=True, warmed_up=True,
                    pressures_hot=dict(PRESS_OK), fuel_l=fuel,
                    corner_vmin=tuple(zip(APEX, speeds, [""] * len(NAMES))),
                    dials=DIALS)


def test_the_sentence_names_the_corners_it_the_last_lap():
    config.set_language("it")
    eng = _eng()
    said = _drive(eng, [_lap(60), _lap(59), _lap(58), _lap(57),
                        _lap(56, _v(-6, at=(2, 3, 5)))])
    assert ("L'ultimo giro non conta. In Tosa, Piratella e Rivazza sei passato "
            "più piano di oltre 5 km/h rispetto agli altri giri di questo "
            "stint.") in said[-1].message


def test_more_than_three_corners_say_how_many_more():
    config.set_language("it")
    eng = _eng()
    said = _drive(eng, [_lap(60), _lap(59), _lap(58), _lap(57),
                        _lap(56, _v(-6, at=(1, 2, 3, 4, 5)))])
    assert "Villeneuve, Tosa, Piratella e altre 2 curve sei" in said[-1].message
    said = _drive(_eng(), [_lap(60), _lap(59), _lap(58), _lap(57),
                           _lap(56, _v(-6, at=(1, 2, 3, 4)))])
    assert "Villeneuve, Tosa, Piratella e un'altra curva" in said[-1].message


def test_an_unnamed_corner_gives_only_the_count():
    config.set_language("it")
    eng = _eng()
    slow = _v(-6, at=(0, 1, 2, 3))
    laps = [_unnamed_lap(60, _v()), _unnamed_lap(59, _v()),
            _unnamed_lap(58, _v()), _unnamed_lap(57, _v()),
            _unnamed_lap(56, slow)]
    said = _drive(eng, laps)
    assert "In 4 curve sei passato" in said[-1].message


def test_the_sentence_rides_on_a_proposal():
    config.set_language("it")
    eng = _eng()
    laps = [_lap(60, press=OFF), _lap(59, press=OFF), _lap(58, press=OFF),
            _lap(57, press=OFF), _lap(56, _v(-6, at=(2, 3, 4)), press=OFF)]
    said = _drive(eng, laps)
    assert said[3].kind is DecisionKind.PROPOSE
    assert "non conta" not in said[3].message
    assert said[4].kind is DecisionKind.PROPOSE
    assert "L'ultimo giro non conta" in said[4].message


def test_a_collect_carries_it_in_the_tail_too():
    config.set_language("it")
    eng = _eng()
    laps = [_lap(60), _lap(59), _lap(58, _v(-6, at=(0, 1, 2)))]
    # Il 3° giro e' lento in 3 curve e viene tolto subito.
    said = _drive(eng, laps + [_lap(57)])
    d = said[3]
    assert d.kind is DecisionKind.COLLECT
    assert "Il 3° giro di questo stint non conta più" in d.message
    assert d.tail is not None and "Il 3° giro di questo stint non conta più" in d.tail
    assert "oltre 5 km/h rispetto agli altri giri." in d.message


def test_the_sentence_in_english():
    config.set_language("en")
    eng = _eng()
    said = _drive(eng, [_lap(60), _lap(59), _lap(58), _lap(57),
                        _lap(56, _v(-6, at=(2, 3, 4, 5)))])
    assert ("That last lap doesn't count. At Tosa, Piratella, Acque Minerali "
            "and 1 more corner you were more than 5 km/h slower than on your "
            "other laps this stint.") in said[-1].message
    said = _drive(_eng(), [_unnamed_lap(60, _v()), _unnamed_lap(59, _v()),
                           _unnamed_lap(58, _v()), _unnamed_lap(57, _v()),
                           _unnamed_lap(56, _v(-6, at=(0, 1, 2)))])
    assert "At 3 corners you were" in said[-1].message


def test_a_held_decision_stays_the_same_object():
    eng = _eng()
    d = eng.observe(_lap(60))
    eng._held_base = d
    assert eng.observe(_lap(59)) is d


import pytest
from accoach.engineer import Decision


@pytest.mark.parametrize("slot", ["_held_revert", "_held_base", "_held_wrong"])
def test_a_held_decision_born_on_a_dropping_lap_is_the_same_object_next_lap(slot):
    # Il motore a valle riconosce «te lo sto ripetendo» da `is`: se la risposta
    # col giro tolto fosse una copia, il giro dopo uscirebbe l'originale e il
    # registro scriverebbe due volte lo stesso esito. Si simula il giro in cui
    # nasce la risposta tenuta E un giro viene tolto, senza costruire a mano
    # un ripristino vero: qui conta solo il contratto del ripetitore.
    config.set_language("it")
    eng = _eng()
    held = Decision(DecisionKind.REVERTED, "Rimetti l'assetto di prima.")
    inner = eng._observe

    def fake(stats):
        eng.last_dropped = [{"stint": 1, "stint_lap": 3, "last": True,
                             "corners": [["Tosa", 6.0]]}]
        setattr(eng, slot, held)
        return held

    eng._observe = fake
    first = eng.observe(_lap(60))
    assert "L'ultimo giro non conta" in first.message
    eng._observe = inner
    # Il giro dopo risponde con la stessa risposta tenuta, con la frase dentro.
    second = eng.observe(_lap(59))
    assert second is first
    assert getattr(eng, slot) is first
