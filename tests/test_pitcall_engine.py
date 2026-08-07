"""The engine's half of the pit calls: when they're armed, and when they shut up.

`PitCall` itself is pure and tested next door. Everything that can go wrong
*between* the race engineer and it lives here: which proposals count, when the
calls stop, and whether a measured pit entry survives a restart.
"""
from accoach.coaching.cue import CueCategory
from accoach.engine import CoachEngine
from accoach.engineer.core import (
    AtomicChange,
    Decision,
    DecisionKind,
    ProposedChange,
)
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import _catalog_path, save_lap

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


def _change(tag: str, rationale: str = "molla anteriore più morbida") -> Decision:
    return Decision(
        kind=DecisionKind.PROPOSE, message=rationale, confidence="high",
        change=ProposedChange(changes=(AtomicChange("aRBFront", None, -1),),
                              rationale=rationale, phase_label="Meccanica",
                              tag=tag))


def _engine(tmp_path, frames=None):
    save_lap(synth.build_lap(), tmp_path)
    return CoachEngine(reader=_StubReader(frames or [synth.snap(pos=0.5)]),
                       voice=None, laps_dir=tmp_path)


def _armed(tmp_path, decision, frames=None):
    """An engine that has already seen this car+track, then a proposal.

    The order matters and cost this file a false pass: the first tick on a new
    car/track rebuilds the engineer and clears its decision, so a test that sets
    the decision *before* ticking is testing an engine that has forgotten it.
    """
    eng = _engine(tmp_path, frames)
    eng.tick(0.0)
    eng._engineer_decision = decision
    return eng


# --- which proposals arm the call -----------------------------------------

def test_a_garage_change_arms_the_call(tmp_path):
    assert _armed(tmp_path, _change("BOX"))._garage_change_pending()


def test_a_change_you_can_make_at_the_wheel_does_not(tmp_path):
    """An AV change is a knob on the straight. Calling the driver in for it
    would cost a lap to save a click."""
    assert not _armed(tmp_path, _change("AV"))._garage_change_pending()


def test_a_decision_that_carries_no_change_does_not(tmp_path):
    """COLLECT / EVALUATING / ACCEPTED are the engineer talking about its own
    state, not asking for anything."""
    eng = _armed(tmp_path, Decision(kind=DecisionKind.EVALUATING,
                                    message="sto misurando"))
    assert not eng._garage_change_pending()


def test_writing_the_setup_stops_the_calls_for_that_change(tmp_path):
    """The engineer re-emits the same PROPOSE every lap until the next completed
    lap tells it otherwise. Without a latch here, a driver who has just applied
    the change and gone back out is called straight back in on the out-lap."""
    eng = _armed(tmp_path, _change("BOX"))
    assert eng._garage_change_pending()
    eng.mark_setup_applied()
    eng.tick(0.1)                              # drains the cross-thread command
    assert eng._engineer_decision is not None, "the proposal is still standing"
    assert not eng._garage_change_pending()


def test_the_next_proposal_arms_it_again(tmp_path):
    """The latch is per proposal. A second, different change must call the
    driver in again — otherwise applying one setup goes silent forever."""
    eng = _armed(tmp_path, _change("BOX", "molla anteriore più morbida"))
    eng.mark_setup_applied()
    eng.tick(0.1)
    eng._engineer_decision = _change("BOX", "ala posteriore giù di un click")
    assert eng._garage_change_pending()


# --- the measured pit entry survives the session --------------------------

def test_the_pit_entry_measured_today_is_there_tomorrow(tmp_path):
    """It takes a real pit visit to learn, so losing it on exit would mean the
    approach call never exists on the first lap of any session."""
    frames = [
        synth.snap(pos=0.90, speed_kmh=200.0),
        synth.snap(pos=0.94, speed_kmh=170.0),
        synth.snap(pos=0.96, speed_kmh=60.0, in_pit_lane=True),
    ]
    eng = _engine(tmp_path, frames)
    for i in range(len(frames)):
        eng.tick(i * 0.05)
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        assert cat.load_pit_entry(synth.snap().track) == [0.94]

    later = _engine(tmp_path, [synth.snap(pos=0.5)])
    later.tick(0.0)
    assert later.pitcall.pit_entry == 0.94


def test_the_calls_reach_the_scheduler_through_the_pit_gate(tmp_path):
    """End to end, in the state that gates everything else: stopped in the box,
    `quiet` says "pit", and this is the one cue that must still be spoken."""
    box = synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True)
    eng = _armed(tmp_path, _change("BOX"), frames=[box])
    spoken = [eng.tick(1.0 + i * 0.05).spoken for i in range(3)]
    said = [s for s in spoken if s is not None]
    assert [s.category for s in said] == [CueCategory.PIT_BRIEFING]


def test_the_engine_tells_the_pit_call_the_briefing_was_heard(tmp_path):
    """The briefing repeats until spoken, so something has to close the loop.
    Without this wiring it would repeat every 8 seconds forever while the driver
    sits in the garage doing what it asked."""
    box = synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True)
    eng = _armed(tmp_path, _change("BOX"), frames=[box])
    for i in range(3):
        eng.tick(1.0 + i * 0.05)
    assert eng.pitcall._briefed_spoken, "the engine heard it and said so"
    later = [eng.tick(20.0 + i * 0.05).spoken for i in range(40)]
    assert [s for s in later if s is not None] == [], "and then it stops asking"


# --- the state's own memory of the call, past the one instant it is spoken ---

def test_the_state_says_you_are_due_in(tmp_path):
    """Dopo il richiamo lo stato lo dice, e continua a dirlo il giro dopo.

    ``_armed`` itself burns the first frame on a warm-up tick (pending is still
    False there, before the decision is assigned) — so frame 0 here is that
    warm-up, and the ticks below line up with frames 1, 2, 3.
    """
    frames = [synth.snap(pos=0.50), synth.snap(pos=0.70), synth.snap(pos=0.95),
              synth.snap(pos=0.05)]
    eng = _armed(tmp_path, _change("BOX"), frames=frames)
    st1 = eng.tick(1.0)                        # last sector: the call fires
    assert st1.spoken is not None and st1.spoken.category is CueCategory.PIT_IN
    assert st1.pit_due is True
    eng.tick(1.05)                             # still lap 0, approaching the line
    st3 = eng.tick(1.10)                       # position wrapped: a new lap now
    assert st3.pit_due is True, "the call was for a lap, not an instant"


def test_the_state_stops_saying_it_in_the_lane(tmp_path):
    frames = [synth.snap(pos=0.50), synth.snap(pos=0.70),
              synth.snap(pos=0.96, in_pit_lane=True)]
    eng = _armed(tmp_path, _change("BOX"), frames=frames)
    st1 = eng.tick(1.0)
    assert st1.pit_due is True, "setup: the call must have fired first"
    st2 = eng.tick(1.05)
    assert st2.pit_due is False
