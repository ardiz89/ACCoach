"""The Focus/Lesson layer — the driver's twin of the race engineer.

It runs over per-lap debriefs (where you lost time vs the reference), picks the
single recurring weakness and coaches it: assess → brief → drill → improved/stuck.
These tests drive it with hand-built debriefs (cheap, exact) and then check the
engine wires a real debrief→focus path into the payload.
"""
import pytest

from accoach import config
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.focus import (
    FocusCoach,
    FocusKind,
    FocusReport,
    format_focus,
)
from accoach.engine import CoachEngine
from accoach.comparison.reference import Reference
from accoach.track import detect_corners

import synth


@pytest.fixture
def it_lang(tmp_path, monkeypatch):
    """Switch the app language to Italian, resetting the config cache after."""
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    config.load_config(reload=True)
    config.set_language("it")
    yield
    config._cache = None


def _loss(index: int, ms: float, category: CueCategory = CueCategory.BRAKE_LATER,
          cause: str = "") -> CornerLoss:
    return CornerLoss(
        index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4, lost_ms=ms,
        category=category, message="m", detail="d",
        fix="Ritarda la staccata.", cause=cause)


def _debrief(*losses: CornerLoss, lap_ms: int = 101000, ref_ms: int = 100000) -> LapDebrief:
    return LapDebrief("ferrari_488_gt3", "monza", lap_ms, ref_ms, losses=list(losses))


def _feed(coach: FocusCoach, debrief: LapDebrief, times: int, *, stable: bool = True):
    report = None
    for _ in range(times):
        report = coach.observe(debrief, stable=stable)
    return report


# --- weakness selection ----------------------------------------------------

def test_assess_until_min_laps():
    coach = FocusCoach()
    r1 = coach.observe(_debrief(_loss(0, 300)))
    r2 = coach.observe(_debrief(_loss(0, 300)))
    assert r1.kind is FocusKind.ASSESS and r2.kind is FocusKind.ASSESS


def test_brief_on_recurring_loss():
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 300)), 3)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 0
    assert report.focus.theme == "braking"             # BRAKE_LATER → braking
    assert report.drill                                # a concrete instruction
    assert "0.30s" in report.message                   # measured baseline


def test_picks_worst_recurring_not_a_one_off():
    """A single huge loss in c1 must not beat a recurring loss in c0."""
    coach = FocusCoach()
    coach.observe(_debrief(_loss(0, 300)))
    coach.observe(_debrief(_loss(0, 300), _loss(1, 900)))   # c1 spikes once
    report = coach.observe(_debrief(_loss(0, 300)))
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 0                   # recurring beats one-off


def test_baseline_uses_full_window_denominator():
    # A corner that's a loss in only some laps must get a baseline measured over
    # the WHOLE window (good laps = 0), the same denominator the drill uses — else
    # IMPROVED would fire without real progress.
    coach = FocusCoach()
    coach.observe(_debrief())                      # good
    coach.observe(_debrief())                      # good
    coach.observe(_debrief(_loss(0, 300)))         # loss, not yet recurring
    r = coach.observe(_debrief(_loss(0, 300)))     # 2/4 -> systematic -> BRIEF
    assert r.kind is FocusKind.BRIEF
    assert r.focus.baseline_ms == 150.0            # median([0,0,300,300]), not 300


def test_no_focus_when_losses_insignificant():
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 50)), 3)         # below the threshold
    assert report.kind is FocusKind.CLEAN


# --- the drill → verdict loop ----------------------------------------------

def test_focus_improved_promotes_and_praises():
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300)), 3)                 # BRIEF on c0 (baseline 300)
    report = _feed(coach, _debrief(_loss(0, 50)), 3)         # then nail it
    assert report.kind is FocusKind.IMPROVED
    assert 0 in coach.mastered
    assert coach.focus is None                               # ready for the next one
    assert "0.30s" in report.message and "0.05s" in report.message  # measured praise


def test_focus_stuck_is_parked():
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300, cause="L'auto sottosterza in ingresso.")), 3)
    report = _feed(coach, _debrief(_loss(0, 300)), 6)        # never improves
    assert report.kind is FocusKind.STUCK
    assert 0 in coach.parked
    assert coach.focus is None
    assert "setup" in report.message.lower()                # hints it may be the car


def test_next_focus_after_promotion():
    coach = FocusCoach()
    # c0 is worse; coach it, solve it, then c1 should become the focus.
    base = _debrief(_loss(0, 300), _loss(1, 200))
    _feed(coach, base, 3)                                    # BRIEF on c0
    _feed(coach, _debrief(_loss(0, 40), _loss(1, 200)), 3)   # solve c0 (IMPROVED)
    report = _feed(coach, _debrief(_loss(0, 40), _loss(1, 200)), 1)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.corner_index == 1                   # moved on to the next


# --- robustness ------------------------------------------------------------

def test_unstable_lap_does_not_move_the_plan():
    coach = FocusCoach()
    coach.observe(_debrief(_loss(0, 300)))
    coach.observe(_debrief(_loss(0, 300)))
    before = len(coach.window)
    report = coach.observe(_debrief(_loss(0, 9000)), stable=False)   # an off
    assert report.kind is FocusKind.ASSESS                  # last report stands
    assert len(coach.window) == before                      # excursion ignored


def test_brief_theme_and_message_are_italian(it_lang):
    coach = FocusCoach()
    report = _feed(coach, _debrief(_loss(0, 300)), 3)
    assert report.kind is FocusKind.BRIEF
    assert report.focus.theme == "frenata"             # BRAKE_LATER → frenata (IT)
    assert "Nuovo focus" in report.message
    assert "lavoriamo la frenata" in report.message


def test_stuck_message_is_italian(it_lang):
    coach = FocusCoach()
    _feed(coach, _debrief(_loss(0, 300, cause="L'auto sottosterza in ingresso.")), 3)
    report = _feed(coach, _debrief(_loss(0, 300)), 6)
    assert report.kind is FocusKind.STUCK
    assert "parcheggio" in report.message.lower()
    assert "causa setup" in report.message.lower()


def test_format_focus_is_a_line():
    r = FocusReport(FocusKind.CLEAN, "Guida costante.")
    assert "Guida costante." in format_focus(r)


# --- engine wiring (real debrief → focus → payload) ------------------------

def test_engine_focus_block_from_real_debriefs(tmp_path):
    class _Dummy:
        def read(self): ...
        def close(self): ...

    eng = CoachEngine(reader=_Dummy(), laps_dir=tmp_path)
    ref_lap = synth.build_lap(n=300, clean=True)
    eng._reference = Reference(ref_lap)
    eng._corners = detect_corners(ref_lap.samples)
    eng._focus = FocusCoach()

    # Three clean laps that lose time in corner 0 → a recurring weakness.
    slow = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)
    for _ in range(3):
        eng._observe_lap(slow)

    block = eng._focus_block()
    assert block is not None
    assert block["kind"] in ("brief", "drill", "assess")
    if block["kind"] == "brief":
        assert block["focus"]["theme"]
    eng.close()
