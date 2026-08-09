"""The active theme reaches the scheduler from the FocusCoach, as an English key.

`Focus.theme` is the translated string ("frenata"): using it for the comparison
would work in Italian and break the filter in English. This test exists to pin
that down.

The two tests at the bottom cover a gap found in review: the theme belongs to a
car/track combination, and must be forgotten on a switch (or it would stay stuck,
possibly for the whole following session) but not on every lap on the SAME
combination, where `_rebuild_reference` runs again to chase the new best time
`_observe_lap` just set.
"""
from accoach.comparison import Reference
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import Focus, FocusCoach, FocusKind, FocusReport
from accoach.engine import CoachEngine, _focus_theme_key
from accoach.track import detect_corners

import synth


class _StubReader:
    """Replays a fixed list of snapshots, holding the last one once exhausted."""

    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def read(self):
        s = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return s

    def close(self):
        pass


def _focus(category, theme):
    return Focus(corner_index=3, name="Curva 4", theme=theme, category=category,
                 baseline_ms=300.0, drill="")


def test_active_focus_yields_the_english_key():
    rep = FocusReport(kind=FocusKind.DRILL,
                      message="",
                      focus=_focus(CueCategory.LESS_BRAKE, "frenata"))
    assert _focus_theme_key(rep) == "braking"


def test_the_translated_label_is_not_used():
    """Even with an Italian label, the key stays English."""
    rep = FocusReport(kind=FocusKind.DRILL,
                      message="",
                      focus=_focus(CueCategory.MORE_THROTTLE, "trazione"))
    assert _focus_theme_key(rep) == "traction"


def test_no_focus_yields_none():
    assert _focus_theme_key(None) is None
    assert _focus_theme_key(FocusReport(kind=FocusKind.ASSESS, message="")) is None
    assert _focus_theme_key(FocusReport(kind=FocusKind.CLEAN, message="")) is None


# --- the theme belongs to a car/track, not to the session ------------------

def test_car_switch_clears_the_leftover_focus_theme(tmp_path):
    """A focus theme belongs to a single car/track combination: it must be
    forgotten on a switch, or the filter would keep discarding advice about a
    theme that no longer applies — possibly for the whole following session, if
    that combination never accumulates a reference a focus could be born from."""
    frames = [
        synth.snap(pos=0.1, car_model="ferrari_488_gt3", track="monza"),
        synth.snap(pos=0.1, car_model="porsche_992_gt3", track="spa"),
    ]
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    eng.tick(0.0)                          # connects to car A / track A
    eng.scheduler.set_focus("braking")     # simulate a focus elected there
    eng.tick(0.0)                          # switches to car B / track B
    assert eng.scheduler.focus_theme is None
    eng.close()


def test_same_car_track_rebuild_does_not_clear_the_focus_theme(tmp_path):
    """`_rebuild_reference` also runs mid-session on the SAME car/track, right
    after `_observe_lap`, to chase a lap that just became the new best
    (engine.py's "chase the new best" call). That path must leave the theme
    alone, or it would erase the very theme `_observe_lap` just set."""
    frames = [synth.snap(pos=0.1)]
    eng = CoachEngine(reader=_StubReader(frames), voice=None, laps_dir=tmp_path)
    eng.tick(0.0)                          # connects, establishes eng._key
    eng.scheduler.set_focus("braking")
    eng._rebuild_reference(*eng._key)      # same combination: the mid-lap path
    assert eng.scheduler.focus_theme == "braking"
    eng.close()


# --- a theme nobody can retire ---------------------------------------------

class _Dummy:
    def read(self): ...
    def close(self): ...


def _engine_working_a_focus(tmp_path):
    """An engine that has elected a focus from real debriefs, as a session does."""
    eng = CoachEngine(reader=_Dummy(), voice=None, laps_dir=tmp_path)
    ref_lap = synth.build_lap(n=300, clean=True)
    eng._reference = Reference(ref_lap)
    eng._corners = detect_corners(ref_lap.samples)
    eng._focus = FocusCoach()
    slow = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)
    for _ in range(3):
        eng._observe_lap(slow)
    assert eng.scheduler.focus_theme is not None, "no focus elected: fixture is wrong"
    return eng, slow


def test_a_lap_the_focus_cannot_be_confirmed_on_releases_the_theme(tmp_path):
    """A reference that goes missing must free the theme, not freeze it.

    `_rebuild_reference` runs after every saved lap and can leave no reference
    (nothing in today's condition band, or the reference is unusable) or no
    corners. The FocusCoach freezes in the same instant, so it can neither park
    the focus nor elect another one: the theme would filter every technique cue
    for the rest of the session, and on a car where trail-brake advice is off by
    design a stuck "braking" leaves the coach nearly mute.
    """
    eng, slow = _engine_working_a_focus(tmp_path)
    eng._corners = []                       # detect_corners found nothing this time
    eng._observe_lap(slow)
    assert eng.scheduler.focus_theme is None
    eng.close()


def test_a_lap_with_no_reference_releases_the_theme(tmp_path):
    """The other half of the same hole: the reference itself is gone."""
    eng, slow = _engine_working_a_focus(tmp_path)
    eng._reference = None                   # no lap in today's condition band
    eng._observe_lap(slow)
    assert eng.scheduler.focus_theme is None
    eng.close()


# --- the word reaches the screen the driver is actually looking at ----------

def test_the_focus_block_carries_the_word_the_voice_will_use(tmp_path):
    """The overlay has no other way to name it: the briefing never gets there."""
    eng, _slow = _engine_working_a_focus(tmp_path)
    block = eng._focus_block()
    assert block["focus"]["trigger"], "no trigger word for the elected focus"
    eng.close()


def test_no_word_is_promised_while_the_gate_is_off(tmp_path):
    """A word shown but never spoken is the same broken promise, mirrored."""
    eng, _slow = _engine_working_a_focus(tmp_path)
    eng.scheduler.set_focus(None)           # e.g. a lap the focus can't be confirmed on
    block = eng._focus_block()
    assert block["focus"]["trigger"] is None
    eng.close()
