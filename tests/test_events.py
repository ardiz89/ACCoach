"""EventDetector: lock-up / wheelspin cues from the live frame (no reference)."""
from accoach.coaching.cue import CueCategory
from accoach.coaching.events import EventDetector

import synth


def _hold(det, s, frames=5, dt=0.05, start=0.0):
    """Feed the same frame repeatedly; collect cues and return (cues, end_time)."""
    out, now = [], start
    for _ in range(frames):
        out += det.update(s, now)
        now += dt
    return out, now


# slip_ratio tuple is (fl, fr, rl, rr); front lock = negative front, spin = positive rear.
def _lock_frame(pos=0.3):
    return synth.snap(pos=pos, brake=0.9, abs_active=0.6, speed_kmh=120.0)


def _spin_frame(pos=0.6):
    return synth.snap(pos=pos, throttle=0.9, tc_active=0.6, speed_kmh=120.0, gear="3")


def test_lockup_fires_once_after_debounce():
    det = EventDetector()
    cues, _ = _hold(det, _lock_frame(), frames=6)
    locks = [c for c in cues if c.category == CueCategory.LOCKED]
    assert len(locks) == 1
    assert locks[0].priority == 300.0


def test_wheelspin_fires_once():
    det = EventDetector()
    cues, _ = _hold(det, _spin_frame(), frames=6)
    spins = [c for c in cues if c.category == CueCategory.WHEELSPIN]
    assert len(spins) == 1


def test_single_frame_blip_does_not_fire():
    det = EventDetector()
    # One lock frame, then released: must not fire (debounce not met).
    out = det.update(_lock_frame(), 0.0)
    out += det.update(synth.snap(pos=0.31, brake=0.0, speed_kmh=120.0), 0.05)
    assert out == []


def test_lockup_needs_meaningful_brake():
    det = EventDetector()
    # ABS flag high but barely on the brakes -> not a lock-up.
    cues, _ = _hold(det, synth.snap(pos=0.3, brake=0.1, abs_active=0.9,
                                    speed_kmh=120.0), frames=6)
    assert all(c.category != CueCategory.LOCKED for c in cues)


def test_wheelspin_ignored_in_neutral_or_reverse():
    det = EventDetector()
    cues, _ = _hold(det, synth.snap(pos=0.6, throttle=0.9, tc_active=0.9,
                                    gear="N", speed_kmh=20.0), frames=6)
    assert all(c.category != CueCategory.WHEELSPIN for c in cues)


def test_slip_ratio_triggers_without_aids():
    det = EventDetector()
    # No ABS, but front wheels turning much slower than ground (a real lock).
    frame = synth.snap(pos=0.3, brake=0.8, abs_active=0.0, speed_kmh=120.0,
                       slip_ratio=(-0.4, -0.4, 0.0, 0.0))
    cues, _ = _hold(det, frame, frames=6)
    assert any(c.category == CueCategory.LOCKED for c in cues)


def test_slip_ratio_fallback_gated_at_low_speed():
    # M12: the slip-ratio fallback is unreliable at crawl speed (its denominator is
    # tiny). Below the gate it must NOT fire on slip alone…
    det = EventDetector()
    slow = synth.snap(pos=0.3, brake=0.8, abs_active=0.0, speed_kmh=20.0,
                      slip_ratio=(-0.4, -0.4, 0.0, 0.0))
    cues, _ = _hold(det, slow, frames=6)
    assert all(c.category != CueCategory.LOCKED for c in cues)
    # …but the ABS primary still fires at any speed.
    det2 = EventDetector()
    abs_low = synth.snap(pos=0.3, brake=0.9, abs_active=0.6, speed_kmh=20.0)
    cues2, _ = _hold(det2, abs_low, frames=6)
    assert any(c.category == CueCategory.LOCKED for c in cues2)


def test_reset_on_pit_rearms():
    det = EventDetector()
    _hold(det, _lock_frame(), frames=6)            # fires + leaves episode fired
    det.update(synth.snap(pos=0.3, in_pit=True), 0.4)   # resets
    cues, _ = _hold(det, _lock_frame(), frames=6, start=0.5)
    assert any(c.category == CueCategory.LOCKED for c in cues)   # re-armed
