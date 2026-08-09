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
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import Focus, FocusKind, FocusReport
from accoach.engine import CoachEngine, _focus_theme_key

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
