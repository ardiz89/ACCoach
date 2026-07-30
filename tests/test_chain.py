"""When a corner's loss was made in the corner before it — and when it wasn't.

Most of this file is about *not* drawing a link. An invented chain is worse than
no chain: it sends the driver to work on a corner that was fine, in the confident
voice of a diagnosis. So every reason the module has to stay quiet gets a test,
and the one case where it should speak gets two — once on hand-made numbers, once
end to end through a real debrief.
"""
import math

import pytest

from accoach.coaching.chain import (
    _MIN_ARRIVAL_DV,
    _MIN_SHARE,
    ChainLink,
    link_corners,
)
from accoach.coaching.debrief import CornerLoss, build_lap_debrief
from accoach.coaching.cue import CueCategory
from accoach.comparison import Reference
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType
from accoach.track import Corner, detect_corners


# --- the rules, on numbers we control --------------------------------------

class _FakePoint:
    def __init__(self, speed):
        self.speed_kmh = speed


class _FakeReference:
    """A reference that is at ``speed`` everywhere except where told otherwise."""

    def __init__(self, speeds: dict[float, float], default: float = 200.0):
        self._speeds = speeds
        self._default = default

    def point_at(self, pos):
        return _FakePoint(self._speeds.get(round(pos, 3), self._default))


class _FakeLap:
    def __init__(self, samples):
        self.samples = samples


def _sample(pos, speed):
    return LapSample(int(pos * 100000), pos, speed, 1.0, 0.0, 0.0, "4", 8000, 0.0, 0.0)


def _loss(index, lost_ms=400.0):
    return CornerLoss(index=index, entry_pos=0.0, apex_pos=0.0, exit_pos=0.0,
                      lost_ms=lost_ms, category=CueCategory.CARRY_SPEED,
                      message="", name=f"Turn {index + 1}")


def _corners():
    return [Corner(index=0, entry_pos=0.100, apex_pos=0.150, exit_pos=0.200),
            Corner(index=1, entry_pos=0.400, apex_pos=0.450, exit_pos=0.500)]


def _run(you_exit, you_entry, ref=200.0, losses=None):
    """One link decision: your speed leaving corner 0 and arriving at corner 1."""
    lap = _FakeLap([_sample(0.200, you_exit), _sample(0.400, you_entry)])
    reference = _FakeReference({0.2: ref, 0.4: ref})
    return link_corners(lap, reference, _corners(),
                        losses if losses is not None else [_loss(0), _loss(1)], "en")


def test_a_deficit_carried_from_the_previous_corner_is_named():
    links = _run(you_exit=192.0, you_entry=192.0)
    assert len(links) == 1
    link = links[0]
    assert (link.index, link.from_index) == (1, 0)
    assert link.arrival_dv == 8.0 and link.carried_dv == 8.0
    assert link.share == 1.0
    assert "Turn 1" in link.message and "8" in link.message


def test_a_deficit_made_on_the_straight_is_not_blamed_on_the_corner():
    """You left the corner on the pace and arrived slow: something happened in
    between — a lift, a bad shift — and the debrief's lap-wide findings own it."""
    assert _run(you_exit=199.0, you_entry=190.0) == []


def test_arriving_barely_slower_is_not_a_finding():
    """Under a few km/h we are inside one driver's own lap-to-lap repeatability."""
    assert _run(you_exit=200.0 - _MIN_ARRIVAL_DV + 0.5,
                you_entry=200.0 - _MIN_ARRIVAL_DV + 0.5) == []


def test_leaving_the_previous_corner_faster_is_never_inheritance():
    assert _run(you_exit=205.0, you_entry=190.0) == []


def test_a_partial_carry_over_is_reported_as_partial():
    """Two thirds inherited, a third made on the straight: still worth saying,
    and said with 'most', not 'all'."""
    links = _run(you_exit=194.0, you_entry=191.0)      # carried 6 of 9
    assert len(links) == 1
    assert links[0].share == pytest.approx(6 / 9, abs=0.01)
    assert "most" in links[0].message


def test_the_share_floor_is_the_line_between_the_two():
    below = _run(you_exit=200.0 - 10.0 * (_MIN_SHARE - 0.1), you_entry=190.0)
    above = _run(you_exit=200.0 - 10.0 * (_MIN_SHARE + 0.1), you_entry=190.0)
    assert below == []
    assert len(above) == 1


def test_no_link_when_this_corner_did_not_cost_anything():
    """A chain between two non-events is a sentence about nothing."""
    assert _run(192.0, 192.0, losses=[_loss(0), _loss(1, lost_ms=10.0)]) == []


def test_no_link_when_the_previous_corner_did_not_cost_anything():
    assert _run(192.0, 192.0, losses=[_loss(0, lost_ms=10.0), _loss(1)]) == []


def test_no_link_when_a_corner_has_no_finding_at_all():
    assert _run(192.0, 192.0, losses=[_loss(1)]) == []


def test_the_first_corner_of_the_lap_is_never_blamed_on_anything():
    """Its predecessor is on the previous lap, which we did not measure."""
    links = _run(192.0, 192.0)
    assert all(l.index != 0 for l in links)


def test_it_speaks_italian_too():
    lap = _FakeLap([_sample(0.200, 192.0), _sample(0.400, 192.0)])
    reference = _FakeReference({0.2: 200.0, 0.4: 200.0})
    links = link_corners(lap, reference, _corners(), [_loss(0), _loss(1)], "it")
    assert "all'uscita di Turn 1" in links[0].message


def test_a_lap_with_one_corner_produces_nothing():
    lap = _FakeLap([_sample(0.2, 190.0)])
    assert link_corners(lap, _FakeReference({}), _corners()[:1], [_loss(0)]) == []


# --- end to end, through a real debrief ------------------------------------

def _lap(deficit_from: float = 2.0, deficit_to: float = 2.0,
         penalty_zones=()) -> Lap:
    """A two-corner circuit; optionally slower over a stretch and later in time.

    ``deficit_from``/``deficit_to`` bracket the positions where 8 km/h go
    missing, so a test can put the deficit inside a corner (inherited) or out on
    the straight after it (not inherited). ``penalty_zones`` add time in a span,
    which is what makes a corner show up as a loss at all.
    """
    s = []
    penalty = 0.0
    for i in range(800):
        pos = i / 799
        # Two corners: steering up, speed down, brake before the apex.
        speed, steer, brake, thr = 250.0, 0.0, 0.0, 1.0
        for lo, apex, hi in ((0.20, 0.27, 0.35), (0.60, 0.67, 0.75)):
            if lo - 0.05 <= pos <= hi:
                d = min(1.0, abs(pos - apex) / ((hi - lo) / 2))
                speed = 100.0 + 150.0 * d
                steer = 0.30 * (1.0 - d)
                brake = 0.9 if lo - 0.05 <= pos < apex else 0.0
                thr = 1.0 if pos >= apex else 0.0
        if deficit_from <= pos <= deficit_to:
            speed -= 8.0
        for a, b in penalty_zones:
            if a <= pos <= b:
                penalty += 2.0           # ms per sample: ~320 ms over a corner
        s.append(LapSample(int(pos * 100000 + penalty), pos, speed, thr, brake,
                           steer, "4", 8000, 0.0, 0.0,
                           car_x=1000.0 * math.cos(2 * math.pi * pos),
                           car_z=1000.0 * math.sin(2 * math.pi * pos)))
    return Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE,
               int(100000 + penalty), True, samples=s)


def _debrief(review):
    ref = _lap()
    corners = detect_corners(ref.samples)
    assert len(corners) == 2, "the fixture must produce two corners"
    return build_lap_debrief(review, Reference(ref), corners, "en"), corners


def test_end_to_end_the_finding_carries_the_link():
    """Slow out of corner 1 and still slow arriving at corner 2."""
    review = _lap(deficit_from=0.27, deficit_to=0.65,
                  penalty_zones=((0.20, 0.40), (0.60, 0.80)))
    debrief, _ = _debrief(review)
    second = next(x for x in debrief.losses if x.index == 1)
    assert second.inherited, "the second corner's loss was inherited"
    assert second.inherited_from == 0
    assert "already there" in second.inherited


def test_end_to_end_a_lift_on_the_straight_does_not_blame_the_corner():
    """Same time lost, but the speed only goes missing *after* the first corner
    is over — that is a straight-line problem, not an inherited one."""
    review = _lap(deficit_from=0.45, deficit_to=0.65,
                  penalty_zones=((0.20, 0.40), (0.60, 0.80)))
    debrief, _ = _debrief(review)
    assert all(not x.inherited for x in debrief.losses)


def test_the_guided_flow_puts_the_link_where_the_driver_reads_it():
    """The landing tab must not send you to the wrong corner with more
    confidence than every other view on the page."""
    from accoach.coaching.flow import build_flow

    review = _lap(deficit_from=0.27, deficit_to=0.65,
                  penalty_zones=((0.20, 0.40), (0.60, 0.80)))
    debrief, _ = _debrief(review)
    second = next(x for x in debrief.losses if x.index == 1)
    steps = build_flow(debrief, "en", max_steps=5)
    card = next(s for s in steps if s.where == second.label)
    assert second.inherited in card.body


def test_the_link_is_a_dataclass_the_api_can_serialise():
    link = ChainLink(index=1, from_index=0, arrival_dv=8.0, carried_dv=8.0,
                     share=1.0, message="x")
    assert (link.index, link.from_index, link.share) == (1, 0, 1.0)
