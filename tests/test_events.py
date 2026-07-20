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
# The aid flag only GATES now — the physical slip must corroborate — so a real
# lock/spin frame carries both the flag and slip past the threshold.
def _lock_frame(pos=0.3):
    return synth.snap(pos=pos, brake=0.9, abs_active=0.6, speed_kmh=120.0,
                      slip_ratio=(-0.4, -0.4, 0.0, 0.0))


def _spin_frame(pos=0.6):
    return synth.snap(pos=pos, throttle=0.9, tc_active=0.6, speed_kmh=120.0, gear="3",
                      slip_ratio=(0.0, 0.0, 0.4, 0.4))


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
    # M12: without an aid, the slip-ratio branch is unreliable at crawl speed (the
    # formula's denominator is tiny). Below the gate it must NOT fire on slip alone…
    det = EventDetector()
    slow = synth.snap(pos=0.3, brake=0.8, abs_active=0.0, speed_kmh=20.0,
                      slip_ratio=(-0.4, -0.4, 0.0, 0.0))
    cues, _ = _hold(det, slow, frames=6)
    assert all(c.category != CueCategory.LOCKED for c in cues)
    # …but with ABS modulating AND the slip corroborating, it fires at any speed
    # (the ACC native ratio is trustworthy at low v).
    det2 = EventDetector()
    abs_low = synth.snap(pos=0.3, brake=0.9, abs_active=0.6, speed_kmh=20.0,
                         slip_ratio=(-0.4, -0.4, 0.0, 0.0))
    cues2, _ = _hold(det2, abs_low, frames=6)
    assert any(c.category == CueCategory.LOCKED for c in cues2)


def test_aid_flag_without_slip_does_not_fire():
    # The corroboration fix: an aided car braking into ABS / on the throttle with
    # TC, but with CLEAN physical slip (aid doing its job on normal technique),
    # must NOT nag — this is what produced the false positives before 2026-07-19.
    det = EventDetector()
    abs_clean = synth.snap(pos=0.3, brake=0.9, abs_active=1.0, speed_kmh=150.0,
                           slip_ratio=(-0.07, -0.06, 0.0, 0.0))   # ABS-managed braking
    cues, _ = _hold(det, abs_clean, frames=6)
    assert all(c.category != CueCategory.LOCKED for c in cues)

    det2 = EventDetector()
    tc_clean = synth.snap(pos=0.6, throttle=1.0, tc_active=1.0, speed_kmh=90.0,
                          gear="2", slip_ratio=(0.0, 0.0, 0.06, 0.06))  # TC-managed exit
    cues2, _ = _hold(det2, tc_clean, frames=6)
    assert all(c.category != CueCategory.WHEELSPIN for c in cues2)


def test_reset_on_pit_rearms():
    det = EventDetector()
    _hold(det, _lock_frame(), frames=6)            # fires + leaves episode fired
    det.update(synth.snap(pos=0.3, in_pit=True), 0.4)   # resets
    cues, _ = _hold(det, _lock_frame(), frames=6, start=0.5)
    assert any(c.category == CueCategory.LOCKED for c in cues)   # re-armed
