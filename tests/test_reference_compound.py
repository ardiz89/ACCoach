"""The reference election learns the tyre and the track's grip.

Both fields have been recorded for weeks and read by nobody. Measured on the
39 real laps in the archive this was written against, which is what decided how
each one is used:

* ``tyre_compound`` is populated on both games — ``dry_compound`` on ACC,
  ``Soft (S)`` / ``Semislicks (SM)`` on AC. It is **compared, never
  interpreted**: on AC the string is whatever the mod chose, which is useless
  for deciding *what* the tyre is and perfectly good for deciding whether two
  laps ran on the *same* one.
* ``grip`` is 0 on all 15 ACC laps — ACC leaves the legacy field at zero by
  design (see ``reader._surface_grip``) — and a flat 1.0 on the AC laps that
  postdate the offset fix. So the band it uses has never met a real spread, and
  the tests below pin the *rule*, not a calibration.

Relaxation order matters and is tested: the tyre is held onto longest, grip is
dropped first, because grip is the least evidenced of the three.
"""
from accoach.recording.catalog import _GRIP_BAND, LapCatalog
from accoach.recording.storage import find_reference_lap, save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _save(tmp_path, ms, day, road_temp=0.0, grip=0.0, compound=""):
    lap = synth.build_lap(clean=True, compound=compound)
    lap.lap_time_ms = ms
    lap.road_temp = road_temp
    lap.grip = grip
    lap.recorded_utc = f"{day}T18:00:00+00:00"
    save_lap(lap, tmp_path)
    return lap


def _elect(tmp_path, **kw):
    lap = find_reference_lap(CAR, TRACK, tmp_path, **kw)
    return lap.lap_time_ms if lap else None


# --- the tyre ---------------------------------------------------------------

def test_the_tyre_decides_before_anything_else(tmp_path):
    """A different compound is a different car: it outranks a faster time."""
    _save(tmp_path, 99_000, "2026-06-20", road_temp=25.0, compound="wet_compound")
    _save(tmp_path, 104_000, "2026-06-21", road_temp=25.0, compound="dry_compound")
    assert _elect(tmp_path, road_temp=25.0, compound="dry_compound") == 104_000


def test_an_unknown_tyre_today_leaves_the_election_as_it_was(tmp_path):
    """Most archives predate the field; asking for nothing must change nothing."""
    _save(tmp_path, 99_000, "2026-06-20", compound="wet_compound")
    _save(tmp_path, 104_000, "2026-06-21", compound="dry_compound")
    assert _elect(tmp_path) == 99_000


def test_a_lap_with_no_recorded_tyre_is_not_a_match(tmp_path):
    """Unknown conditions can't be called similar — on either side."""
    _save(tmp_path, 99_000, "2026-06-20", compound="")
    _save(tmp_path, 104_000, "2026-06-21", compound="dry_compound")
    assert _elect(tmp_path, compound="dry_compound") == 104_000


def test_no_lap_on_this_tyre_falls_back_rather_than_going_blank(tmp_path):
    """A slightly wrong benchmark still beats "no reference"."""
    _save(tmp_path, 99_000, "2026-06-20", compound="dry_compound")
    assert _elect(tmp_path, compound="wet_compound") == 99_000


def test_the_ac_style_string_works_because_it_is_only_ever_compared(tmp_path):
    """On AC the compound is a mod's own label. We never ask what it means."""
    _save(tmp_path, 99_000, "2026-06-20", compound="Semislicks (SM)")
    _save(tmp_path, 104_000, "2026-06-21", compound="Soft (S)")
    assert _elect(tmp_path, compound="Soft (S)") == 104_000


# --- grip -------------------------------------------------------------------

def test_a_lap_at_similar_grip_beats_a_faster_one_on_a_different_track(tmp_path):
    _save(tmp_path, 99_000, "2026-06-20", grip=0.80)
    _save(tmp_path, 104_000, "2026-06-21", grip=1.00)
    assert _elect(tmp_path, grip=1.00) == 104_000
    assert _elect(tmp_path, grip=0.80) == 99_000


def test_grip_inside_the_band_is_the_same_conditions(tmp_path):
    _save(tmp_path, 99_000, "2026-06-20", grip=1.00 - _GRIP_BAND / 2)
    _save(tmp_path, 104_000, "2026-06-21", grip=1.00)
    assert _elect(tmp_path, grip=1.00) == 99_000


def test_zero_grip_means_never_recorded_not_a_slippery_track(tmp_path):
    """ACC reports 0 by design. Treating that as "no grip at all" would make
    every ACC lap match every other ACC lap on a condition nobody measured."""
    _save(tmp_path, 99_000, "2026-06-20", grip=0.0)
    _save(tmp_path, 104_000, "2026-06-21", grip=0.90)
    assert _elect(tmp_path, grip=0.0) == 99_000      # asking with 0 = not asking
    assert _elect(tmp_path, grip=0.90) == 104_000    # a real 0-grip lap is no match


# --- how they are relaxed ---------------------------------------------------

def test_grip_is_the_first_thing_given_up(tmp_path):
    """Least evidenced first: no published comparison stands behind its band."""
    # Same tyre and temperature, different grip — and nothing matches all three.
    _save(tmp_path, 99_000, "2026-06-20", road_temp=25.0, grip=0.70,
          compound="dry_compound")
    _save(tmp_path, 104_000, "2026-06-21", road_temp=40.0, grip=1.00,
          compound="dry_compound")
    assert _elect(tmp_path, road_temp=25.0, grip=1.00,
                  compound="dry_compound") == 99_000


def test_the_tyre_is_the_last_thing_given_up(tmp_path):
    """Same temperature on the wrong tyre loses to the right tyre at the wrong
    temperature: a different compound is a bigger difference than 15°."""
    _save(tmp_path, 99_000, "2026-06-20", road_temp=25.0, compound="wet_compound")
    _save(tmp_path, 104_000, "2026-06-21", road_temp=40.0, compound="dry_compound")
    assert _elect(tmp_path, road_temp=25.0, compound="dry_compound") == 104_000


def test_all_three_matching_wins_over_two(tmp_path):
    _save(tmp_path, 99_000, "2026-06-20", road_temp=25.0, grip=0.60,
          compound="dry_compound")
    _save(tmp_path, 104_000, "2026-06-21", road_temp=25.0, grip=1.00,
          compound="dry_compound")
    assert _elect(tmp_path, road_temp=25.0, grip=1.00,
                  compound="dry_compound") == 104_000


def test_asking_for_nothing_still_returns_the_fastest(tmp_path):
    """The offline tools want "the best lap" to mean the best lap."""
    _save(tmp_path, 99_000, "2026-06-20", road_temp=25.0, grip=1.0,
          compound="dry_compound")
    _save(tmp_path, 104_000, "2026-06-21")
    assert _elect(tmp_path) == 99_000


def test_a_dirty_lap_is_never_elected_whatever_the_conditions(tmp_path):
    """Conditions are a preference; track limits are a rule."""
    dirty = synth.build_lap(clean=False, compound="dry_compound")
    dirty.lap_time_ms = 95_000
    dirty.road_temp = 25.0
    dirty.recorded_utc = "2026-06-19T18:00:00+00:00"
    save_lap(dirty, tmp_path)
    _save(tmp_path, 104_000, "2026-06-21", road_temp=25.0, compound="dry_compound")
    assert _elect(tmp_path, road_temp=25.0, compound="dry_compound") == 104_000


def test_the_catalog_query_is_the_one_being_exercised(tmp_path):
    """The scan fallback has no notion of conditions, so a test that silently
    fell through to it would pass while proving nothing."""
    _save(tmp_path, 99_000, "2026-06-20", compound="wet_compound")
    _save(tmp_path, 104_000, "2026-06-21", compound="dry_compound")
    from accoach.recording.storage import _catalog_path, list_lap_files

    from accoach.recording import load_lap

    with LapCatalog(_catalog_path(tmp_path)) as cat:
        cat.sync(list_lap_files(tmp_path))
        path = cat.best_reference_path(CAR, TRACK, compound="dry_compound")
    assert path is not None
    assert load_lap(path).tyre_compound == "dry_compound"
