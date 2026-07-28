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

_FLOAT, _INT, _WCHAR = ctypes.c_float, ctypes.c_int, ctypes.c_wchar

# The ACC graphics tail as the published SDK declares it, transcribed field by
# field — including the stretch our own struct deliberately leaves opaque. This
# list exists ONLY to be counted; nothing reads it. See
# :func:`test_the_documented_layout_reproduces_the_measured_offset`.
_DOCUMENTED_TAIL_AFTER_WIND_DIRECTION = [
    ("isSetupMenuVisible", _INT),
    ("mainDisplayIndex", _INT),
    ("secondaryDisplayIndex", _INT),
    ("TC", _INT),
    ("TCCut", _INT),
    ("EngineMap", _INT),
    ("ABS", _INT),
    # --- the stretch we model as 120 opaque bytes ---
    ("fuelXLap", _FLOAT),
    ("rainLights", _INT),
    ("flashingLights", _INT),
    ("lightsStage", _INT),
    ("exhaustTemperature", _FLOAT),
    ("wiperLV", _INT),
    ("DriverStintTotalTimeLeft", _INT),
    ("DriverStintTimeLeft", _INT),
    ("rainTyres", _INT),
    ("sessionIndex", _INT),
    ("usedFuel", _FLOAT),
    ("deltaLapTime", _WCHAR * 15),
    ("iDeltaLapTime", _INT),
    ("estimatedLapTime", _WCHAR * 15),
    ("iEstimatedLapTime", _INT),
    ("isDeltaPositive", _INT),
    ("iSplit", _INT),
    # --- and back onto ground we measured ---
    ("isValidLap", _INT),
]


def _documented_graphics() -> type[ctypes.Structure]:
    """Our base fields up to ``windDirection``, then the SDK's tail, expanded."""
    head = []
    for name, typ in SPageFileGraphics._fields_:
        head.append((name, typ))
        if name == "windDirection":
            break

    class _Documented(ctypes.Structure):
        _pack_ = 4
        _fields_ = head + _DOCUMENTED_TAIL_AFTER_WIND_DIRECTION

    return _Documented


def _graphics(active_cars: int, est=_PLAUSIBLE_EST, valid=1) -> SPageFileGraphics:
    g = SPageFileGraphics()
    g.activeCars = active_cars
    g.iEstimatedLapTime = est
    g.isValidLap = valid
    return g


# --- the reader -----------------------------------------------------------

def test_the_offsets_are_where_they_were_measured():
    """Pins OUR struct: a field added or resized above ``isValidLap`` would
    silently shift it onto a neighbouring flag. A layout lock, nothing more —
    the corroboration lives in the next test.
    """
    assert SPageFileGraphics.iEstimatedLapTime.offset == 1404
    assert SPageFileGraphics.isValidLap.offset == 1408
    assert ctypes.sizeof(SPageFileGraphics) == 1412


def test_the_documented_layout_reproduces_the_measured_offset():
    """Arithmetic corroboration of an offset that was found by hand.

    1408 came from watching ACC's shared memory frame by frame, and this file
    used to say that nothing here could re-check it. Something can, cheaply:
    expand the SDK's tail field by field — *including* the stretch our struct
    carries as 120 opaque bytes precisely because its order was never verified —
    and count where ``isValidLap`` lands.

    It lands on 1408. That number is the product of every declaration above it:
    three filler ints after ``windDirection``, eleven scalars, two 15-wide
    wchar strings whose 30 bytes each need two bytes of padding to realign. Any
    field missing, extra, or wrongly sized anywhere in that chain moves the
    total. Landing on the byte we measured in the sim is therefore evidence
    about the whole chain — and in particular about the three fillers, which is
    what puts ``TC``/``ABS``/``EngineMap`` where the next test asserts they are.

    What this does NOT settle is the *identity* of any single unread field: two
    compensating errors would still sum to 1408. See
    :func:`test_the_field_names_in_the_opaque_stretch_are_not_claimed`.
    """
    documented = _documented_graphics()
    assert documented.isValidLap.offset == 1408
    assert ctypes.sizeof(documented) == ctypes.sizeof(SPageFileGraphics)


def test_the_aid_levels_sit_where_the_documented_layout_puts_them():
    """The offsets the engineer's advice and the recorded setup depend on.

    ``verify-aids`` has never been run on ACC (see ``TARATURE-ACC.md`` 0.1), so
    until it is, this arithmetic is the only thing standing behind these four
    numbers. Reading the wrong bytes here means advising knobs that do nothing
    and recording a setup that isn't the one driven.
    """
    documented = _documented_graphics()
    for name in ("TC", "TCCut", "EngineMap", "ABS"):
        assert (getattr(documented, name).offset
                == getattr(SPageFileGraphics, name).offset), name


def test_the_field_names_in_the_opaque_stretch_are_not_claimed():
    """Where the two sources disagree — recorded rather than resolved.

    Our struct calls the int at 1404 ``iEstimatedLapTime``; the transcribed SDK
    order puts ``iEstimatedLapTime`` at 1396 and ``iSplit`` at 1404. Only one of
    them can be right, and this repository cannot tell which: the field is
    declared and never read as data, so no behaviour distinguishes them. The
    live measurement (142 427 ms at Monza, lap-scale rather than sector-scale)
    leans towards our name, which is why nothing is being renamed on the
    strength of a transcription.

    The check is one line of a session that is already planned — print both
    offsets while doing ``TARATURE-ACC.md`` 0.4 — so this test records the open
    question instead of quietly picking a side.
    """
    documented = _documented_graphics()
    assert documented.iEstimatedLapTime.offset == 1396
    assert SPageFileGraphics.iEstimatedLapTime.offset == 1404


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
    """Kept, but it is not the guard the docstring used to claim it was.

    ``padded`` can only be True if the game published fewer bytes than the struct
    AND we could detect that. We can't: ``VirtualQuery`` rounds a view's
    ``RegionSize`` up to the 4 KB page and every one of these structs is smaller
    than a page, so in production this argument is always False and this branch
    is unreachable. Two guards were documented; ``_is_acc`` is the only one that
    ever runs — see :meth:`SharedMemoryReader._lap_valid`.
    """
    assert SharedMemoryReader._lap_valid(_graphics(20, valid=1), True) is None


def test_the_only_guard_that_actually_runs_is_the_title_check():
    """Pins the truth rather than the intention: with ``padded`` False — which is
    what production always passes — everything rests on ``activeCars``."""
    assert SharedMemoryReader._lap_valid(_graphics(0, valid=0), False) is None
    assert SharedMemoryReader._lap_valid(_graphics(20, valid=0), False) is False


def test_the_page_is_smaller_than_the_granularity_we_could_measure():
    """Why the structural guard can't work, as an assertion instead of a claim."""
    assert ctypes.sizeof(SPageFileGraphics) < 4096


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
