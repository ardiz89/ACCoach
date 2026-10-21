"""I testi che il motore scrive nel report, composti coi numeri veri.

`tests/tono.py` legge i modelli («{tl} %»), non le frasi che il pilota vede: un
`{secs:.1f}` nel modello passa il controllo e poi stampa «0.4 s» su una pagina
italiana. Qui ogni messaggio del debrief, della traiettoria, degli esercizi e
dello stint si compone con valori di esempio *con i decimali*, e alle frasi
composte si applicano le stesse regole (stesso schema di `test_howto_tono.py`).
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from accoach.coaching import chain, debrief, phases, training
from accoach.coaching.analyzer import CornerStats
from accoach.coaching.cue import CueCategory as C
from accoach.coaching.debrief import CornerLoss, GripState, LapDebrief
from accoach.coaching.plan import Goal, GoalProgress, TrainingPlan
from accoach.engineer import Balance, Phase, Speed, Symptom
from accoach.trajectory import _TAGS, tag_text
from accoach import api

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tono  # noqa: E402

LANGS = ("it", "en")

_STATS = CornerStats(lost_ms=184.0, throttle_live=0.455, throttle_ref=0.724,
                     brake_live=0.312, brake_ref=0.187, min_speed_live=96.4,
                     min_speed_ref=103.8, braking_early=True, braking_late=False)


def _debrief_texts(lang):
    out = []
    for cat in (C.BRAKE_LATER, C.BRAKE_EARLIER, C.MORE_THROTTLE, C.LESS_BRAKE,
                C.CARRY_SPEED, C.TIME_LOSS):
        out += list(debrief.explain_loss(cat, _STATS, lang))
        out += list(debrief.category_words(cat, lang))
    for b in (Balance.UNDERSTEER, Balance.OVERSTEER):
        for p in (Phase.ENTRY, Phase.APEX, Phase.EXIT):
            for s in (Speed.LOW, Speed.HIGH):
                out.append(debrief.explain_cause(Symptom(b, p, s), lang))
    out.append(debrief._grip_detail(GripState(ratio=0.973), C.BRAKE_LATER, lang))
    out.append(debrief._grip_detail(GripState(ratio=0.716), C.CARRY_SPEED, lang))
    out.append(debrief.lift_detail(42.5, 0.42, 183.0, "Eau Rouge", lang))
    out.append(debrief.lift_detail(42.5, 0.42, 183.0, "", lang))
    out.append(debrief._LIFT_MSG[lang])
    out.append(debrief.brake_early_text(12.4, lang))
    out.append(debrief._BRAKE_LANDMARK[lang].format(lm="al cordolo"))
    out.append(debrief.brake_peak_text(0.823, 0.971, lang))
    out.append(debrief.top_speed_message(6.2, lang))
    out += [debrief._TOP_SPEED_AERO[lang], debrief._TOP_SPEED_EXIT[lang]]
    for theme in ("braking", "traction", "cornering", "line"):
        out.append(debrief.headline_text(theme, 3.47, lang))
    d = LapDebrief(car_model="ks_mazda_mx5_cup", track="monza", lap_time_ms=108_456,
                   reference_lap_ms=107_912, losses=[CornerLoss(
                       index=0, entry_pos=0.1, apex_pos=0.12, exit_pos=0.14,
                       lost_ms=184.0, category=C.CARRY_SPEED, message="x",
                       name="Variante del Rettifilo")])
    text = debrief.format_debrief(d, consistency={"n": 6, "best_ms": 107_912,
                                                  "spread_ms": 1834, "std_ms": 612.4},
                                  lang=lang)
    out += [line.strip() for line in text.splitlines()[1:]]
    ref = LapDebrief(car_model="", track="", lap_time_ms=100_000, reference_lap_ms=100_000)
    out += [line.strip() for line in debrief.format_debrief(ref, lang=lang).splitlines()[1:]]
    out.append(phases.phase_note([phases.PhaseLoss("entry", 141.0),
                                  phases.PhaseLoss("apex", 32.0),
                                  phases.PhaseLoss("exit", -43.0)], 130.0, lang))
    out += [chain.chain_message(k, 6, "Lesmo 1", lang) for k in ("all", "most")]
    return [t for t in out if t]


def _tag_values(key):
    if key == "off_here":
        return {"v": 81, "vr": 96}
    if key.endswith("_arc"):
        return {"r": 35, "rr": 42}
    return {"m": 2.5}


def _trajectory_texts(lang):
    return [tag_text(k, _tag_values(k), lang) for k in _TAGS]


_FACTS = training.CornerFacts(min_speed_kmh=96.4, min_speed_ref_kmh=103.8,
                              spread_kmh=4.2, brake_speed_kmh=212.6, brake_gear="3",
                              brake_distance_m=118.3, brake_spread_m=6.4,
                              brake_spread_kmh=3.1, landmark="al cordolo")


def _training_texts(lang):
    out = []
    drills = [training.build_drill(cat, ph, f, lang, trail_brake=tb)
              for cat, ph, f, tb in (
                  ("brake_later", "entry", _FACTS, True),
                  ("brake_later", "entry", training.CornerFacts(brake_speed_kmh=212.6,
                                                               brake_spread_kmh=3.1), True),
                  ("brake_later", "entry", training.CornerFacts(), True),
                  ("less_brake", "entry", _FACTS, True),
                  ("less_brake", "entry", _FACTS, False),
                  ("carry_speed", "apex", _FACTS, True),
                  ("more_throttle", "exit", _FACTS, True),
                  ("time_loss", "", _FACTS, True))]
    for d in drills:
        out += [d.title, d.watch, d.ignore, *d.steps]
    out.append(training.assess(3, 0, lang).reason)
    out.append(training.assess(9, 0, lang).reason)
    gap = training.build_gap(101_234, 100_456, [34_100, 33_500, 33_634],
                             [33_800, 33_300, 33_356], per_lap_ms=420.0,
                             pro_ms=99_800, lang=lang)
    out += [gap.headline, gap.note]
    tight = training.build_gap(100_020, 100_000, [], [], lang=lang)
    out.append(tight.headline)
    goal = Goal(corner_index=2, name="Lesmo 1", category=C.CARRY_SPEED.value,
                what="x", fix="y", baseline_ms=412.0, target_ms=206.0, laps_seen=6)
    plan = TrainingPlan(car="c", track="t", goals=[goal], created_utc="2026-10-21T10:00:00")
    loss = CornerLoss(index=2, entry_pos=0.1, apex_pos=0.2, exit_pos=0.3, lost_ms=412.0,
                      category=C.CARRY_SPEED, message="x", name="Lesmo 1")
    debriefs = [LapDebrief(car_model="c", track="t", lap_time_ms=100_000,
                           reference_lap_ms=99_000, losses=[loss])] * 6
    prog = training.build_programme(
        plan, [GoalProgress(corner_index=2, laps=0, hits=0, needed=3, median_ms=0.0, best_ms=0.0, done=False)], debriefs, gap,
        {2: _FACTS}, valid_laps=8, lang=lang)
    for st in prog.steps:
        out += [st.why, st.target, st.done_when]
    out += prog.session.lines
    out += [g.definition for g in training.glossary_of(training._TERM_ORDER, lang)]
    return [t for t in out if t]


def _stint_texts(lang):
    out = []
    for litres, known in ((12.4, False), (0.0, True)):
        for trend in (None,
                      NS(direction="rising", significant=True, slope=184.0, error=42.0),
                      NS(direction="falling", significant=True, slope=-121.0, error=33.0),
                      NS(direction="flat", significant=False, slope=-120.0, error=145.0)):
            out += api._pace_notes(lang, litres, known, trend, counted=7, needed=5)
    for ct in (NS(direction="rising", significant=True, slope=0.83),
               NS(direction="falling", significant=True, slope=-0.61),
               NS(direction="flat", significant=False, slope=0.1)):
        out += api._tyre_notes(lang, ct)
    return out


_ALL = {"debrief": _debrief_texts, "trajectory": _trajectory_texts,
        "training": _training_texts, "stint": _stint_texts}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("part", sorted(_ALL))
def test_composed_texts_follow_the_rules(part, lang):
    texts = _ALL[part](lang)
    assert texts
    bad = [(t, tono.violations(t, lang)) for t in texts if tono.violations(t, lang)]
    assert not bad, bad


def test_the_sample_decimals_reach_the_page_with_the_right_separator():
    # Senza questa prova un numero intero per caso farebbe passare un `:.1f`.
    it = " ".join(_debrief_texts("it") + _trajectory_texts("it") + _stint_texts("it"))
    en = " ".join(_debrief_texts("en") + _trajectory_texts("en") + _stint_texts("en"))
    for num in ("2,5 m", "0,4 s", "1,8 decimi", "12,4 L", "0,14 s", "0,8 °C"):
        assert num in it, num
    for num in ("2.5 m", "0.4 s", "1.8 tenths", "12.4 L", "0.14 s", "0.8 °C"):
        assert num in en, num
    assert "−0,12" in it                      # un meno solo, quello tipografico


def test_the_speed_difference_is_the_difference_of_the_printed_speeds():
    # 96,4 e 103,8 si stampano 96 e 104: la differenza scritta è 8, non 7.
    for lang in LANGS:
        detail, _ = debrief.explain_loss(C.CARRY_SPEED, _STATS, lang)
        assert "96 km/h" in detail and "104 km/h" in detail and "8 km/h" in detail


@pytest.mark.parametrize("lang", LANGS)
def test_english_is_not_a_copy_of_italian(lang):
    other = "en" if lang == "it" else "it"
    for part in _ALL.values():
        a, b = part(lang), part(other)
        same = [x for x, y in zip(a, b) if x == y and len(x.split()) >= 4]
        assert not same, same
