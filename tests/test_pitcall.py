"""The pit calls: come in, the entry is here, and here's what to do once stopped.

Written against the gap the driver reported in their own words — the coach hands
you the change to make and never tells you to box. Each test below is one of the
ways that sentence can stay true after a fix that looks right.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.pitcall import PitCall

import synth


def _cats(cues):
    return [c.category for c in cues]


# A feed, not a slideshow. Both calls size their lead from the *measured* rate
# of position change, and `PitCall._track_rate` rejects gaps over a second as
# stale — so a test that jumps the car 4% of a lap per frame never establishes a
# rate at all, every lead collapses to its floor, and the tests pass for reasons
# that have nothing to do with the track. These two numbers make the frames look
# like the real thing: a 1:50 lap sampled at 20 Hz.
_LAP_S = 110.0
_HZ = 20.0


def _drive(pc, waypoints, lap_s=_LAP_S, **kw):
    """Drive from waypoint to waypoint at ``_HZ``; return every cue produced.

    The waypoints are places, not frames: the car is interpolated between them
    the way it actually travels, so everything in between happens too. Continues
    from wherever the previous call left the clock.
    """
    out = []
    now = pc._prev_t
    prev = pc._prev_pos if pc._prev_pos >= 0 else None
    for target in waypoints:
        # Always forwards round the lap, like a car: a waypoint behind the
        # current position means "keep going and come back to it", crossing the
        # start line on the way. Interpolating backwards instead would mean no
        # test in this file ever crosses the line — and the lap latch lives on
        # that crossing.
        delta = 0.0 if prev is None else (target - prev) % 1.0
        span = 1 if prev is None else max(1, round(delta * lap_s * _HZ))
        for i in range(1, span + 1):
            p = target if prev is None else (prev + delta * i / span) % 1.0
            now += 1.0 / _HZ
            out += pc.update(synth.snap(pos=p, **kw), now)
        prev = target
    return out


# --- nothing pending: total silence ---------------------------------------

def test_no_change_waiting_means_no_call_anywhere_on_the_lap():
    """The pit call is not a feature of driving, it's a feature of having
    something to do in the garage. With nothing to do it must not exist."""
    pc = PitCall()
    assert _drive(pc, [i / 100 for i in range(100)]) == []


def test_a_change_you_can_dial_at_the_wheel_is_never_a_reason_to_box():
    """The engineer already separates BOX from AV; the engine passes only BOX
    through `set_pending`. This pins the consequence: with pending False the
    calls stay silent even in the last sector."""
    pc = PitCall()
    pc.set_pending(False)
    assert _drive(pc, [0.70, 0.80, 0.90]) == []


# --- the call, at the start of the last sector -----------------------------

def test_the_call_comes_in_the_last_sector_and_only_once_a_lap():
    pc = PitCall()
    pc.set_pending(True)
    cues = _drive(pc, [0.10, 0.40, 0.70, 0.80, 0.90], completed_laps=3)
    assert _cats(cues) == [CueCategory.PIT_IN]
    assert "rientra ai box" in cues[0].message.lower()


def test_the_call_repeats_on_the_next_lap_if_you_stayed_out():
    """Once a lap, not once ever: a driver who ignores it (or couldn't come in)
    gets one reminder per lap, which is the cadence the engineer proposes at."""
    pc = PitCall()
    pc.set_pending(True)
    first = _drive(pc, [0.70, 0.90], completed_laps=3)
    second = _drive(pc, [0.70, 0.90], completed_laps=4)
    assert len(first) == 1 and len(second) == 1


def test_the_finish_line_does_not_produce_a_second_call():
    """Both sims bump `completed_laps` a frame or two BEFORE the position wraps —
    measured on real files: `pos=0.0001` with `current_sector` still 2. Keyed on
    the sim's counter, the call fired again on the line every single lap, and
    latched the lap that had just started. It's the same reason the recorder has
    `crossed_start_line` instead of trusting the counter."""
    pc = PitCall()
    pc.set_pending(True)
    said = _drive(pc, [0.70, 0.98], current_sector=2, sector_count=3,
                  completed_laps=3)
    assert len(said) == 1
    # The counter jumps here; the position hasn't wrapped yet.
    skew = [pc.update(synth.snap(pos=0.9998, current_sector=2, sector_count=3,
                                 completed_laps=4), pc._prev_t + 0.05)]
    skew += [pc.update(synth.snap(pos=0.9999, current_sector=2, sector_count=3,
                                  completed_laps=4), pc._prev_t + 0.05)]
    assert [c for frame in skew for c in frame] == []


def test_the_last_sector_is_the_sim_s_own_split_not_a_third():
    """synth's sectors are deliberately unequal (0/0.30/0.65). At 0.50 a
    thirds-based rule would already be in "sector 2" and call too early; the
    sim says sector 1, and the sim wins."""
    pc = PitCall()
    pc.set_pending(True)
    early = _drive(pc, [0.50], current_sector=1, sector_count=3, completed_laps=1)
    assert early == []
    late = _drive(pc, [0.70], current_sector=2, sector_count=3, completed_laps=1)
    assert _cats(late) == [CueCategory.PIT_IN]


def test_without_declared_sectors_it_falls_back_to_thirds():
    """Some AC content publishes no sectors at all. The call still has to
    happen — a track with no splits is not a track with no pit lane."""
    pc = PitCall()
    pc.set_pending(True)
    assert _drive(pc, [0.50], current_sector=-1, sector_count=0) == []
    assert _cats(_drive(pc, [0.70], current_sector=-1, sector_count=0)) \
        == [CueCategory.PIT_IN]


# --- learning where the pit lane starts ------------------------------------

def test_the_pit_entry_is_measured_from_where_you_left_the_track():
    pc = PitCall()
    pc.update(synth.snap(pos=0.90, speed_kmh=200.0), 0.0)
    pc.update(synth.snap(pos=0.94, speed_kmh=180.0), 0.1)
    pc.update(synth.snap(pos=0.96, speed_kmh=80.0, in_pit_lane=True), 0.2)
    assert pc.pit_entry == 0.94, "the last position ON TRACK, not the first in the lane"


def test_starting_the_session_parked_in_the_garage_teaches_it_nothing():
    """A session that opens in the box also reads as "in the lane". Learning an
    entry from it would poison the track's memory with wherever the car happened
    to be parked — and unlike a wrong lap time, nothing on screen would show it."""
    pc = PitCall()
    pc.update(synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True), 0.0)
    pc.update(synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True), 0.1)
    assert pc.pit_entry is None


def test_going_back_to_the_garage_with_escape_teaches_it_nothing():
    """ESC → "return to garage" is the most common thing a driver does after a
    bad lap, and it teleports: the last on-track frame can be anywhere on the
    circuit. Learning from it poisons a memory that is written to disk and
    reloaded next session, and the symptom is the worst one this module has —
    "pit entry just ahead" said in the middle of a straight."""
    pc = PitCall()
    pc.update(synth.snap(pos=0.42, speed_kmh=180.0), 0.0)
    pc.update(synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True), 1.4)
    assert pc.pit_entry is None


def test_a_long_stall_before_the_lane_is_not_an_entry_either():
    """Same guard, other half: the position may line up after a pause (alt-tab,
    a menu) without the car ever having driven in."""
    pc = PitCall()
    pc.update(synth.snap(pos=0.93, speed_kmh=150.0), 0.0)
    pc.update(synth.snap(pos=0.95, speed_kmh=60.0, in_pit_lane=True), 30.0)
    assert pc.pit_entry is None


def test_a_single_odd_entry_cannot_move_the_learned_point():
    """Median, not mean: one aborted entry or one rejoin is outvoted."""
    pc = PitCall([0.90, 0.91, 0.90, 0.905])
    pc.note_pit_entry(0.20)                     # nonsense sample
    assert 0.90 <= pc.pit_entry <= 0.91


def test_an_unmeasured_track_simply_has_no_approach_call():
    """Better silent than confidently wrong: a guessed entry would make the
    driver lift for a pit lane that isn't there."""
    pc = PitCall()
    pc.set_pending(True)
    cues = _drive(pc, [0.70, 0.80, 0.90, 0.95, 0.99], completed_laps=1)
    assert _cats(cues) == [CueCategory.PIT_IN], "the call, and nothing else"


# --- the approach ----------------------------------------------------------

def test_the_approach_fires_just_before_the_measured_entry():
    pc = PitCall([0.90])
    pc.set_pending(True)
    cues = _drive(pc, [0.70, 0.75, 0.80, 0.85, 0.88, 0.90], completed_laps=1)
    assert _cats(cues) == [CueCategory.PIT_IN, CueCategory.PIT_APPROACH]
    assert "ingresso box" in cues[1].message.lower()


def test_the_approach_is_a_warning_not_a_second_call():
    """The lead is capped. Uncapped, a fast position rate on the main straight
    puts the "entry just ahead" alongside the "box this lap" — two sentences a
    third of a lap early, which is how a warning becomes noise. Checked by
    position, because both cues share a category and a category assertion can't
    tell them apart."""
    pc = PitCall([0.90])
    pc.set_pending(True)
    cues = _drive(pc, [0.66, 0.70, 0.74, 0.78, 0.82, 0.86, 0.90],
                  completed_laps=1)
    approach = [c for c in cues if "ingresso" in c.message.lower()]
    assert len(approach) == 1
    assert approach[0].pos >= 0.90 - 0.08, "no earlier than the declared cap"
    assert approach[0].pos > cues[0].pos, "and after the call, never with it"


def test_a_pit_entry_before_the_last_sector_still_gets_called_in_time():
    """Not every circuit puts its pit entry in sector 3 — the lane can peel off
    the corner before it. Tied to the last sector alone, the call would arrive
    with the entry already behind the car and cost the driver the lap it was
    for, which is the exact failure this feature exists to end."""
    pc = PitCall([0.55])                       # entry well before the last third
    pc.set_pending(True)
    cues = _drive(pc, [0.30, 0.36, 0.42, 0.48, 0.54],
                  current_sector=1, sector_count=3, completed_laps=1)
    assert cues, "silence here is the bug"
    assert cues[0].pos < 0.55, "said before the entry, not after it"


def test_an_entry_just_after_the_start_line_is_reached_going_forwards():
    """A pit entry at 0.02 is 0.97 *ahead* of a car at 0.05, not 0.03 behind it.
    Straight subtraction goes negative here and silently disables both calls —
    on the one track layout where the driver has least room to react."""
    pc = PitCall([0.02])
    pc.set_pending(True)
    quiet = _drive(pc, [0.30, 0.45], current_sector=1, sector_count=3,
                   completed_laps=1)
    assert quiet == [], "mid-lap the entry is most of a lap away"
    late = _drive(pc, [0.99], current_sector=2, sector_count=3, completed_laps=1)
    assert any("ingresso" in c.message.lower() for c in late)


def test_the_call_and_the_approach_are_never_the_same_breath():
    """Where the entry sits right at the start of the last sector both moments
    land on one frame. Two sentences for one event is how a useful warning
    becomes noise."""
    pc = PitCall([0.67])
    pc.set_pending(True)
    cues = _drive(pc, [0.66, 0.67], current_sector=2, sector_count=3,
                  completed_laps=1)
    assert len(cues) == 1


def test_past_the_entry_there_is_nothing_left_to_warn_about():
    pc = PitCall([0.50])
    pc.set_pending(True)
    cues = _drive(pc, [0.70, 0.80, 0.90], completed_laps=1)
    assert _cats(cues) == [CueCategory.PIT_IN], "only the call; the entry is behind"


# --- the briefing, standing in the box -------------------------------------

def test_stopped_in_the_box_it_says_what_to_do_with_the_change():
    """The change lives in a browser page the driver isn't looking at. Without
    this they sit in the garage with the app three clicks away and no reason to
    open it — which is the whole complaint."""
    pc = PitCall()
    pc.set_pending(True)
    cues = pc.update(synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True,
                                in_pit_lane=True), 0.0)
    assert _cats(cues) == [CueCategory.PIT_BRIEFING]
    msg = cues[0].message.lower()
    assert "ingegnere" in msg and "ricarica" in msg, "open the page, reload the setup"


def test_the_briefing_is_said_once_not_every_frame_you_sit_there():
    pc = PitCall()
    pc.set_pending(True)
    box = synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True)
    said = [c for i in range(50) for c in pc.update(box, i * 0.05)]
    assert len(said) == 1


def test_the_briefing_keeps_asking_until_it_is_actually_heard():
    """It used to latch on *emission*, which is not the same event: the
    scheduler may drop a cue, and this one was emitted once in the life of a
    setup change — so a drop left the driver in the garage with nothing said and
    no second chance. It repeats until told it was spoken, which is also what a
    real engineer does."""
    pc = PitCall()
    pc.set_pending(True)
    box = synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True)
    again = [c for i in range(400) for c in pc.update(box, i * 0.1)]
    assert len(again) > 1, "nobody heard it; it has to ask again"
    pc.mark_briefed()
    after = [c for i in range(400) for c in pc.update(box, 100.0 + i * 0.1)]
    assert after == [], "heard once, and then silence"


def test_the_next_change_gets_its_own_briefing():
    """The latch is per change, not per session: applying one setup and being
    proposed another must brief again, or the second visit is silent."""
    pc = PitCall()
    box = synth.snap(pos=0.02, speed_kmh=0.0, in_pit=True, in_pit_lane=True)
    pc.set_pending(True)
    assert len(pc.update(box, 0.0)) == 1
    pc.set_pending(False)                        # driver wrote it
    pc.set_pending(True)                         # engineer proposes the next one
    assert len(pc.update(box, 1.0)) == 1


def test_rolling_down_the_pit_lane_is_not_the_moment_to_talk():
    """Between the entry and the box the driver is on a speed limiter watching
    for their garage. The briefing waits for the car to actually stop."""
    pc = PitCall()
    pc.set_pending(True)
    lane = synth.snap(pos=0.95, speed_kmh=48.0, in_pit_lane=True, in_pit=False)
    assert pc.update(lane, 0.0) == []


# --- the cues survive the engine's own gates -------------------------------

def test_the_calls_are_not_gated_by_the_quiet_reasons():
    """`quiet == "pit"` silences driving advice — and the briefing is spoken
    exactly there. Both pit categories are therefore in the engine's safety set;
    this test fails the day someone tidies that set."""
    from accoach.engine import _SAFETY_CATEGORIES
    assert CueCategory.PIT_IN in _SAFETY_CATEGORIES
    assert CueCategory.PIT_BRIEFING in _SAFETY_CATEGORIES


# --- through the scheduler, which is where they actually get spoken ---------
#
# Every test above interrogates PitCall directly. That is not what the driver
# hears: between the cue and the ear sits CueScheduler, with a minimum gap, a
# repeat suppressor keyed on (category, segment), and per-tier staleness. Both
# of the worst defects this module has had lived in exactly that gap.

def _spoken(cues_at, until=30.0):
    """Feed (time, cue) pairs to a real scheduler; return what it says."""
    from accoach.coaching.scheduler import CueScheduler

    sch, out, t = CueScheduler(), [], 0.0
    pending = list(cues_at)
    while t <= until:
        while pending and pending[0][0] <= t:
            sch.submit(pending.pop(0)[1], t)
        said = sch.poll(t)
        if said is not None:
            out.append((round(t, 2), said))
        t = round(t + 0.05, 2)
    return out


def _cue(cat, msg="x", pos=0.5):
    from accoach.coaching.cue import Cue

    return Cue(category=cat, message=msg, priority=290.0, segment=-1, pos=pos)


def test_the_approach_is_not_swallowed_as_a_repeat_of_the_call():
    """They shared a category AND a segment, so `dedup_key` made the approach a
    repeat of the call — suppressed for 20 s, then dropped as stale. On the lead
    path the two are exactly 15 s apart, so the warning that exists to stop you
    missing the pit entry was spoken *at* the entry, or never at all."""
    said = _spoken([(0.0, _cue(CueCategory.PIT_IN)),
                    (15.0, _cue(CueCategory.PIT_APPROACH))])
    cats = [c.category for _, c in said]
    assert cats == [CueCategory.PIT_IN, CueCategory.PIT_APPROACH]
    when = next(t for t, c in said if c.category is CueCategory.PIT_APPROACH)
    assert when < 16.0, "spoken when it was queued, not 5 s after the entry"


def test_the_briefing_survives_something_else_speaking_first():
    """In the box the cues that can beat it — lock-up, wheelspin, fuel, the pit
    calls — are exactly the ones the `quiet == "pit"` gate lets through. So
    "nothing competes with it there", which its tier assumed, was false: an acute
    cue in the same tick took the slot and the briefing was dropped."""
    said = _spoken([(0.0, _cue(CueCategory.LOCKED)),
                    (0.0, _cue(CueCategory.PIT_BRIEFING))])
    assert CueCategory.PIT_BRIEFING in [c.category for _, c in said]


def test_the_briefing_does_not_go_stale_while_it_waits_its_turn():
    """It describes a STATE — the car is stopped in the garage — which cannot
    stop being true while it queues. Queued 0.5 s after something spoke, it had
    to wait 4 s for the gap and died of a 2.5 s staleness limit."""
    said = _spoken([(0.0, _cue(CueCategory.LOCKED)),
                    (0.5, _cue(CueCategory.PIT_BRIEFING))])
    assert CueCategory.PIT_BRIEFING in [c.category for _, c in said]


def test_the_call_outranks_technique_advice_but_not_a_lock_up():
    """Missing the entry costs a lap, so it can't queue behind "more throttle
    here". It is not a safety fault either, so it must not shove one aside."""
    from accoach.coaching.cue import CueTier, tier_of
    assert tier_of(CueCategory.PIT_IN) == CueTier.ACUTE
    assert tier_of(CueCategory.PIT_BRIEFING) == CueTier.ADVISORY
