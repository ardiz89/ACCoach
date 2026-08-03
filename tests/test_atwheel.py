"""An "al volo" change finishes when the dial moves, not when a button is clicked.

Until this existed, `mark_applied()` had exactly one caller — the setup-file
writer, which only runs for BOX changes. So an AV proposal was announced, never
marked applied, and re-proposed at every finish line: its phase never closed.
On the GT3 profile that is two phases out of five, brake bias and electronics.
"""
from accoach.coaching.atwheel import WheelWatch
from accoach.engine import CoachEngine
from accoach.engineer.core import (
    AtomicChange,
    Decision,
    DecisionKind,
    ProposedChange,
)
from accoach.recording.storage import save_lap

import synth


class _StubReader:
    def __init__(self, frames):
        self._frames, self._i = frames, 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


def _av(param="tC1", clicks=1, rationale="più controllo di trazione"):
    return Decision(
        kind=DecisionKind.PROPOSE, message=rationale, confidence="high",
        change=ProposedChange(changes=(AtomicChange(param, None, clicks),),
                              rationale=rationale, phase_label="Elettronica",
                              tag="AV"))


# --- the watch itself ------------------------------------------------------

def test_one_more_click_of_tc_is_seen():
    w = WheelWatch()
    assert w.arm("tC1", +1, synth.snap(tc_level=4))
    assert not w.update(synth.snap(tc_level=4)), "nothing has happened yet"
    assert w.update(synth.snap(tc_level=5))


def test_turning_it_the_other_way_is_not_an_answer():
    """The driver is doing something else with the dial. Taking that as "done"
    would start the re-test window on a car set the opposite way to the one the
    engineer is about to judge."""
    w = WheelWatch()
    w.arm("tC1", +1, synth.snap(tc_level=4))
    assert not w.update(synth.snap(tc_level=3))


def test_brake_bias_is_measured_in_the_step_the_car_actually_reports():
    """0.002 of front fraction per click — measured on a 720S at Monza
    (0.750 → 0.760 over ten clicks), which is the same number the setup format
    declares as 0.2%."""
    w = WheelWatch()
    w.arm("brakeBias", -1, synth.snap(brake_bias=0.750))
    assert not w.update(synth.snap(brake_bias=0.750))
    assert w.update(synth.snap(brake_bias=0.748))


def test_overshooting_still_counts():
    """Two clicks when one was asked is the driver answering, not disobeying."""
    w = WheelWatch()
    w.arm("tC1", +1, synth.snap(tc_level=4))
    assert w.update(synth.snap(tc_level=6))


def test_a_car_that_does_not_report_the_dial_cannot_be_watched():
    """AC leaves these at -1. Arming there would be a watch that can never fire,
    and a proposal that can never finish — which is the bug this fixes, moved
    somewhere quieter. It says no instead, and the page's button takes over."""
    w = WheelWatch()
    assert not w.arm("tC1", +1, synth.snap(tc_level=-1))
    assert not w.armed


def test_a_parameter_with_no_live_channel_is_not_watched():
    w = WheelWatch()
    assert not w.arm("aRBFront", +1, synth.snap(tc_level=4))


def test_it_disarms_once_it_has_fired():
    """Otherwise the same movement would keep answering later proposals."""
    w = WheelWatch()
    w.arm("tC1", +1, synth.snap(tc_level=4))
    assert w.update(synth.snap(tc_level=5))
    assert not w.armed
    assert not w.update(synth.snap(tc_level=9))


# --- wired into the engine -------------------------------------------------

def _engine(tmp_path, frames):
    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    eng.tick(0.0)                    # settle the car/track, which clears decisions
    return eng


def test_turning_the_dial_advances_the_engineer(tmp_path):
    """The whole point: no page, no click, no lap lost."""
    # Three frames, because the settling tick in `_engine` eats the first one.
    eng = _engine(tmp_path, [synth.snap(tc_level=4)] * 2 + [synth.snap(tc_level=5)])
    eng._engineer_decision = _av()
    eng.tick(0.1)                    # arms on tc_level=4
    assert eng.wheelwatch.armed
    eng.tick(0.2)                    # sees tc_level=5
    assert not eng.wheelwatch.armed
    assert eng._engineer_done_sig is not None, "the engineer was told"


def test_a_garage_change_never_arms_the_watch(tmp_path):
    """A BOX change is a file to write; watching a dial for it would mark it
    applied the moment the driver touched an unrelated knob."""
    eng = _engine(tmp_path, [synth.snap(tc_level=4)])
    box = _av()
    eng._engineer_decision = Decision(
        kind=DecisionKind.PROPOSE, message="x", change=ProposedChange(
            changes=box.change.changes, rationale="x", phase_label="Meccanica",
            tag="BOX"))
    eng.tick(0.1)
    assert not eng.wheelwatch.armed


def test_a_new_proposal_rearms_on_a_fresh_baseline(tmp_path):
    """Else the second proposal would be answered by the first one's movement."""
    eng = _engine(tmp_path, [synth.snap(tc_level=4)] * 2 + [synth.snap(tc_level=5)])
    eng._engineer_decision = _av(rationale="primo")
    eng.tick(0.1)
    eng.tick(0.2)                    # applied on the move 4 -> 5
    eng._engineer_decision = _av(rationale="secondo")
    eng.tick(0.3)                    # re-arms, this time with 5 as the baseline
    assert eng.wheelwatch.armed
    eng.tick(0.4)                    # still 5
    assert eng.wheelwatch.armed, "the first proposal's move is not a second answer"
