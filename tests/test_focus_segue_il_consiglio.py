"""In pista il focus lavora sul consiglio che il pilota ha scelto nel report.

Il pilota sceglie un consiglio («Lo seguo») e il coach in pista, finche' quelle
curve perdono, lavora su quelle, nell'ordine — invece della curva peggiore che
avrebbe scelto da solo. Se le curve del consiglio non perdono abbastanza, la
scelta torna quella di sempre: un consiglio non deve far tacere il coach su una
curva che oggi va bene.
"""
from dataclasses import asdict

from accoach.coaching.advice import ACTIVE, PROPOSED, Advice, AdviceCorner
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.focus import FocusCoach, FocusKind
from accoach.comparison.reference import Reference
from accoach.engine import CoachEngine
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import _catalog_path, save_lap
from accoach.track import Corner

import synth
from test_engine_gate import _StubReader

CAR, TRACK = "ferrari_488_gt3", "monza"


def _loss(index: int, ms: float) -> CornerLoss:
    return CornerLoss(
        index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4, lost_ms=ms,
        category=CueCategory.BRAKE_LATER, message="m", detail="d",
        fix="Ritarda la staccata.")


def _window(coach: FocusCoach, *losses: CornerLoss):
    report = None
    for _ in range(3):
        report = coach.observe(LapDebrief(CAR, TRACK, 101000, 100000,
                                          losses=list(losses)))
    return report


# --- il FocusCoach ---------------------------------------------------------

def test_the_followed_advice_wins_over_a_worse_corner():
    # La 5 perde di piu', ma il pilota ha scelto di lavorare sulla 2.
    losses = (_loss(5, 300.0), _loss(2, 180.0))
    followed = _window(FocusCoach(preferred=[2]), *losses)
    assert followed.kind is FocusKind.BRIEF
    assert followed.focus.corner_index == 2
    # Senza consiglio, la scelta di sempre: la peggiore.
    assert _window(FocusCoach(), *losses).focus.corner_index == 5


def test_an_advice_corner_that_is_fine_falls_back_to_the_usual_choice():
    report = _window(FocusCoach(preferred=[2]), _loss(5, 300.0), _loss(2, 40.0))
    assert report.focus.corner_index == 5


def test_the_advice_corners_are_worked_in_their_order():
    # Tutte e due perdono: si comincia dalla prima del consiglio, non dalla
    # peggiore delle due.
    losses = (_loss(5, 300.0), _loss(2, 180.0), _loss(7, 250.0))
    assert _window(FocusCoach(preferred=[2, 7]), *losses).focus.corner_index == 2
    assert _window(FocusCoach(preferred=[7, 2]), *losses).focus.corner_index == 7


def test_a_mastered_advice_corner_passes_to_the_next_one():
    losses = (_loss(5, 300.0), _loss(2, 180.0), _loss(7, 150.0))
    coach = FocusCoach(preferred=[2, 7], mastered={2})
    assert _window(coach, *losses).focus.corner_index == 7


# --- il motore -------------------------------------------------------------

def _save_advice(laps_dir, *apexes: float, status: str = ACTIVE,
                 defect: str = "braking") -> None:
    advice = Advice(defect=defect, status=status, corners=[
        AdviceCorner(index=i, name=f"Curva {i + 1}", apex_pos=a, mean=200.0)
        for i, a in enumerate(apexes)])
    with LapCatalog(_catalog_path(laps_dir)) as cat:
        cat.save_advice(CAR, TRACK, asdict(advice))


def _corner(index: int, entry: float, exit_: float) -> Corner:
    return Corner(index=index, entry_pos=entry, apex_pos=(entry + exit_) / 2,
                  exit_pos=exit_)


def test_the_engine_maps_advice_corners_by_apex_position(tmp_path):
    # Apex dentro la curva 3, uno fuori da ogni curva, e uno 0.0 (consiglio
    # migrato dal vecchio piano, posizione ignota): resta solo la 3.
    _save_advice(tmp_path, 0.63, 0.50, 0.0, defect="traction")
    # Un consiglio solo proposto non conta: il pilota non l'ha scelto. (Sta
    # prima nel catalogo, che ordina per difetto.)
    _save_advice(tmp_path, 0.15, status=PROPOSED, defect="braking")

    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    ref_lap = synth.build_lap(n=300, clean=True)
    eng._reference = Reference(ref_lap)
    eng._corners = [_corner(0, 0.0, 0.20), _corner(1, 0.25, 0.35),
                    _corner(2, 0.40, 0.48), _corner(3, 0.60, 0.70),
                    _corner(4, 0.80, 0.90)]
    eng._focus_key = (CAR, TRACK)
    eng._focus = FocusCoach()
    eng._observe_lap(synth.build_lap(n=300, clean=True))
    assert eng._focus.preferred == [3]
    eng.close()


def test_the_engine_starts_the_focus_on_the_followed_advice(tmp_path):
    save_lap(synth.build_lap(), tmp_path)   # riferimento: curve 0 (0.19-0.38) e 1 (0.59-0.78)
    _save_advice(tmp_path, 0.71)
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)
    assert eng._focus.preferred == [1]
    eng.close()


def test_without_an_advice_the_focus_chooses_alone(tmp_path):
    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)
    assert eng._focus.preferred == []
    eng.close()


def test_an_unreadable_catalog_means_no_preference(tmp_path, monkeypatch):
    save_lap(synth.build_lap(), tmp_path)
    _save_advice(tmp_path, 0.71)

    def _broken(self, car, track):
        raise RuntimeError("catalogo bloccato")

    monkeypatch.setattr(LapCatalog, "load_advice", _broken)
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)
    assert eng._focus.preferred == []
    eng.close()
