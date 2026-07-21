"""Each sim has exactly one field that carries track limits, and it's not the same one.

Measured live at Monza in a 720S GT3:

* ``numberOfTyresOut`` on ACC read **0 on every frame** with all four wheels off
  the tarmac — it's one of the legacy physics fields ACC never fills. So `clean`
  on ACC said "clean" for every lap ever recorded there, including cut ones, and
  the reference picker preferred exactly the laps it should have rejected.
* ``isValidLap`` (offset 1408) tracked reality: 0 through the out lap, 0→1 on the
  line, 1→0 at the first chicane at 69 km/h — twice, in two independent sessions,
  at lap position 0.161 and 0.164 — then latched down for the rest of the lap.

AC is the mirror image: the counter works, the verdict doesn't exist. Reading the
verdict there would be worse than useless — the page ends long before offset
1408, so our zero-padding would report every lap of every session as invalidated.
"""
import ctypes
from dataclasses import replace

from accoach.recording.recorder import LapRecorder
from accoach.telemetry.reader import SharedMemoryReader
from accoach.telemetry.snapshot import ACStatus, SessionType, TelemetrySnapshot
from accoach.telemetry.structs import SPageFileGraphics

_PLAUSIBLE_EST = 142_427        # the value measured at Monza


def _graphics(active_cars: int, est=_PLAUSIBLE_EST, valid=1) -> SPageFileGraphics:
    g = SPageFileGraphics()
    g.activeCars = active_cars
    g.iEstimatedLapTime = est
    g.isValidLap = valid
    return g


# --- the reader -----------------------------------------------------------

def test_the_offsets_are_where_they_were_measured():
    assert SPageFileGraphics.iEstimatedLapTime.offset == 1404
    assert SPageFileGraphics.isValidLap.offset == 1408


def test_acc_reports_the_sims_own_verdict():
    assert SharedMemoryReader._lap_valid(_graphics(20, valid=1), False) is True
    assert SharedMemoryReader._lap_valid(_graphics(20, valid=0), False) is False


def test_ac_reports_unknown_never_invalid():
    """The whole point of the None: AC's page is zero-padded out here.

    Read as a bool, that zero would mean "this lap is invalidated" on every
    frame of every AC lap — a total, silent failure.
    """
    assert SharedMemoryReader._lap_valid(_graphics(0, valid=0), True) is None


def test_a_page_that_did_not_reach_the_field_is_unknown():
    """The guard is structural: a field the page doesn't contain is unknown.

    Even if everything else looked like ACC. The previous attempt guarded on the
    neighbouring counter's *value* and was wrong about what that counter is — it
    mirrors the running lap clock, so it read under 20 s at the start of every
    lap and the guard rejected the first twenty seconds of every ACC lap.
    """
    assert SharedMemoryReader._lap_valid(_graphics(20, valid=1), True) is None


def test_a_flag_that_is_neither_0_nor_1_is_unknown():
    assert SharedMemoryReader._lap_valid(_graphics(20, valid=1078530011), False) is None


def test_the_neighbouring_counter_never_changes_the_verdict():
    """It is not a gate: it tracks the lap clock and legitimately reads anything."""
    for est in (0, 4_952, 142_427, 2_147_483_647):
        assert SharedMemoryReader._lap_valid(
            _graphics(20, est=est, valid=0), False) is False
        assert SharedMemoryReader._lap_valid(
            _graphics(20, est=est, valid=1), False) is True


# --- the recorder ---------------------------------------------------------

_ACC = replace(
    TelemetrySnapshot.disconnected(),
    connected=True, status=ACStatus.LIVE, session=SessionType.PRACTICE,
    car_model="mclaren_720s_gt3_evo", track="monza", speed_kmh=180.0,
    last_lap_ms=113_712, is_acc=True, lap_valid=True,
)


def _lap(**kw):
    """Sampled every 2%, so the lap carries enough telemetry to count as one."""
    return [replace(_ACC, lap_position=p / 100, **kw) for p in range(0, 100, 2)]


def _run(rec, frames):
    return [lap for f in frames if (lap := rec.update(f)) is not None]


def test_acc_lap_is_dirty_when_the_sim_dropped_the_flag():
    rec = LapRecorder()
    frames = _lap(completed_laps=0) + [replace(_ACC, lap_position=0.0, completed_laps=1)]
    # …then a lap where the flag drops at the first chicane and latches.
    frames += [replace(_ACC, lap_position=0.05, completed_laps=1),
               replace(_ACC, lap_position=0.16, completed_laps=1, lap_valid=False)]
    frames += [replace(_ACC, lap_position=p / 100, completed_laps=1, lap_valid=False)
               for p in range(20, 100, 2)]
    # The flag resets at the line — the verdict must not be read off that frame.
    frames += [replace(_ACC, lap_position=0.0, completed_laps=2, lap_valid=True)]
    laps = [lap for lap in _run(rec, frames) if lap.valid]
    assert laps and laps[-1].clean is False


def test_acc_lap_stays_clean_when_the_flag_never_dropped():
    rec = LapRecorder()
    frames = _lap(completed_laps=0) + [replace(_ACC, lap_position=0.0, completed_laps=1)]
    frames += _lap(completed_laps=1)
    frames += [replace(_ACC, lap_position=0.0, completed_laps=2)]
    laps = [lap for lap in _run(rec, frames) if lap.valid]
    assert laps and laps[-1].clean is True


def test_acc_ignores_the_dead_tyre_counter():
    """3+ wheels off but the sim says the lap counts: believe the sim.

    On ACC the counter is dead, so a non-zero reading there is noise; and where
    it isn't, the sim's own track-limits geometry is the authority anyway.
    """
    rec = LapRecorder()
    frames = _lap(completed_laps=0) + [replace(_ACC, lap_position=0.0, completed_laps=1)]
    frames += _lap(completed_laps=1, tyres_out=4)
    frames += [replace(_ACC, lap_position=0.0, completed_laps=2)]
    laps = [lap for lap in _run(rec, frames) if lap.valid]
    assert laps and laps[-1].clean is True


def test_ac_still_uses_the_wheel_counter():
    """No verdict available → the AC rule, unchanged."""
    ac = replace(_ACC, is_acc=False, lap_valid=None, car_model="gp_2025_sf25",
                 track="spa")
    rec = LapRecorder()
    frames = [replace(ac, lap_position=p / 100, completed_laps=0)
              for p in range(0, 100, 5)]
    frames += [replace(ac, lap_position=0.0, completed_laps=1)]
    frames += [replace(ac, lap_position=p / 100, completed_laps=1, tyres_out=4)
               for p in range(0, 100, 5)]
    frames += [replace(ac, lap_position=0.0, completed_laps=2)]
    laps = [lap for lap in _run(rec, frames) if lap.valid]
    assert laps and laps[-1].clean is False
