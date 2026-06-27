"""SetupAdvisor: lap-aggregated TC/ABS/brake-bias advice."""
from dataclasses import replace

from accoach.coaching.advisor import SetupAdvisor, _COOLDOWN_LAPS
from accoach.coaching.cue import Cue, CueCategory
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot

_BASE = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    tc_level=4, abs_level=3,
)


def _snap(pos, in_pit=False):
    return replace(_BASE, lap_position=pos, in_pit=in_pit)


def _lock(seg):
    return Cue(CueCategory.LOCKED, "x", 300.0, seg, seg / 20)


def _spin(seg):
    return Cue(CueCategory.WHEELSPIN, "x", 300.0, seg, seg / 20)


def _drive_lap(adv, events_by_segment, now=0.0):
    """One full lap, injecting events; the terminal wrap evaluates this lap."""
    out = []
    for seg in range(20):
        out += adv.update(_snap(seg / 20 + 0.001), events_by_segment.get(seg, []), now)
        now += 0.1
    out += adv.update(_snap(0.01), [], now)
    return out, now


def test_persistent_lockup_suggests_abs():
    adv = SetupAdvisor()
    ev = {2: [_lock(2)], 6: [_lock(6)], 10: [_lock(10)], 15: [_lock(15)]}
    out, _ = _drive_lap(adv, ev)
    assert len(out) == 1
    assert out[0].category is CueCategory.ABS_UP
    assert "dal 3 al 4" in out[0].message


def test_persistent_spin_suggests_tc():
    adv = SetupAdvisor()
    ev = {3: [_spin(3)], 8: [_spin(8)], 14: [_spin(14)]}
    out, _ = _drive_lap(adv, ev)
    assert len(out) == 1 and out[0].category is CueCategory.TC_UP
    assert "dal 4 al 5" in out[0].message


def test_one_corner_is_not_setup():
    adv = SetupAdvisor()
    out, _ = _drive_lap(adv, {6: [_lock(6)]})
    assert out == []


def test_high_abs_switches_to_brake_bias():
    adv = SetupAdvisor()
    high = replace(_BASE, abs_level=9)
    now = 0.0
    for seg in range(20):
        cues = {2: [_lock(2)], 7: [_lock(7)], 12: [_lock(12)]}.get(seg, [])
        adv.update(replace(high, lap_position=seg / 20 + 0.001), cues, now)
        now += 0.1
    out = adv.update(replace(high, lap_position=0.01), [], now)
    assert len(out) == 1 and out[0].category is CueCategory.BRAKE_BIAS


def test_cooldown_silences_repeat():
    adv = SetupAdvisor()
    ev = {2: [_lock(2)], 6: [_lock(6)], 10: [_lock(10)]}
    out, now = _drive_lap(adv, ev)
    assert len(out) == 1
    for _ in range(_COOLDOWN_LAPS - 1):
        out, now = _drive_lap(adv, ev, now)
        assert out == []
    out, now = _drive_lap(adv, ev, now)
    assert len(out) == 1


def test_pit_lap_discarded():
    adv = SetupAdvisor()
    now = 0.0
    for seg in range(20):
        cues = {2: [_lock(2)], 6: [_lock(6)], 10: [_lock(10)]}.get(seg, [])
        adv.update(_snap(seg / 20 + 0.001, in_pit=True), cues, now)
        now += 0.1
    out = adv.update(_snap(0.01), [], now)
    assert out == []


def test_unknown_levels_directional():
    adv = SetupAdvisor()
    unknown = replace(_BASE, tc_level=-1, abs_level=-1)
    now = 0.0
    for seg in range(20):
        cues = {3: [_spin(3)], 8: [_spin(8)], 14: [_spin(14)]}.get(seg, [])
        adv.update(replace(unknown, lap_position=seg / 20 + 0.001), cues, now)
        now += 0.1
    out = adv.update(replace(unknown, lap_position=0.01), [], now)
    assert len(out) == 1
    assert "dal" not in out[0].message and out[0].message.endswith("il TC.")
