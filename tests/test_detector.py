"""_detector: the shared debounce + cue-emission contract for the live detectors."""
from dataclasses import replace

from accoach.coaching._detector import Episode, make_cue, step
from accoach.coaching.cue import CueCategory
from accoach.telemetry.snapshot import TelemetrySnapshot

_S = TelemetrySnapshot.disconnected()


def test_step_fires_once_after_hold():
    ep = Episode()
    # Not yet held long enough.
    assert step(ep, True, 0.0, 0.2) is False
    assert step(ep, True, 0.1, 0.2) is False
    # Crosses the hold → fires exactly once.
    assert step(ep, True, 0.2, 0.2) is True
    # Stays held → does not re-fire.
    assert step(ep, True, 0.3, 0.2) is False


def test_step_rearms_when_condition_clears():
    ep = Episode()
    step(ep, True, 0.0, 0.1)
    assert step(ep, True, 0.1, 0.1) is True      # fired
    assert step(ep, False, 0.2, 0.1) is False    # condition clears → re-arm
    step(ep, True, 0.3, 0.1)
    assert step(ep, True, 0.4, 0.1) is True       # fires again after re-holding


def test_make_cue_tags_segment_from_position():
    c = make_cue(replace(_S, lap_position=0.5), CueCategory.LOCKED, "x", 300.0)
    assert c.category is CueCategory.LOCKED
    assert c.priority == 300.0
    assert c.segment == 10                         # 0.5 * 20
    assert c.pos == 0.5


def test_make_cue_clamps_segment_at_the_line():
    # pos just under 1.0 must not overflow past the last segment index.
    c = make_cue(replace(_S, lap_position=0.999), CueCategory.WHEELSPIN, "x", 300.0)
    assert c.segment == 19                          # clamped to segments-1
    lo = make_cue(replace(_S, lap_position=0.0), CueCategory.WHEELSPIN, "x", 300.0)
    assert lo.segment == 0
