"""Per-lap diagnosis (build_lap_stats) and the engine's live engineer block.

The synthetic laps inject a realistic yaw signal: the games report yaw_rate with
the OPPOSITE sign to steering (that's why balance.py uses _YAW_SIGN = -1), so a
neutral corner has raw yaw = -(ratio)*steer with ratio ~1.9. Lowering the ratio
below ~0.9 makes the car "push" (understeer); a same-sign raw yaw simulates the
countersteer of oversteer.
"""
from accoach.coaching.analyzer import _BRAKE_ON
from accoach.coaching.debrief import (
    _metres_between,
    _next_entry,
    _onset,
    build_lap_debrief,
)
from accoach.coaching.diagnosis import build_lap_stats
from accoach.comparison.reference import Reference
from accoach.engine import CoachEngine
from accoach.engineer import Balance
from accoach.recording.lap import Lap, LapSample
from accoach.telemetry.snapshot import SessionType, TelemetrySnapshot
from accoach.track import Corner, detect_corners

import synth


def _with_yaw(lap, *, ratio: float, same_sign: bool = False):
    """Set each sample's yaw_rate to model a given yaw/steer ratio.

    Default (same_sign=False) mimics the game convention (yaw opposite to steer),
    i.e. a clean corner; same_sign=True flips it to look like countersteer.
    """
    sign = 1.0 if same_sign else -1.0
    for s in lap.samples:
        s.yaw_rate = sign * ratio * s.steer_angle
    return lap


def test_understeer_lap_is_diagnosed():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=0.3)
    stats = build_lap_stats(lap)
    under = [sym for sym in stats.symptom_scores if sym.balance is Balance.UNDERSTEER]
    assert under                                       # the push is named
    assert max(stats.symptom_scores[s] for s in under) >= 0.30
    assert any(stats.symptom_corners[s] >= 1 for s in under)
    assert any(stats.symptom_corner_idx.get(s) for s in under)   # anchored to corners
    assert stats.stable is True                        # clean lap


def test_neutral_lap_has_no_understeer():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.9)
    stats = build_lap_stats(lap)
    under = [s for s in stats.symptom_scores if s.balance is Balance.UNDERSTEER]
    over = [s for s in stats.symptom_scores if s.balance is Balance.OVERSTEER]
    assert not under and not over                       # a neutral car: nothing flagged


def test_oversteer_lap_is_diagnosed():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.5, same_sign=True)
    stats = build_lap_stats(lap)
    over = [s for s in stats.symptom_scores if s.balance is Balance.OVERSTEER]
    assert over


def test_dirty_lap_is_not_stable():
    lap = _with_yaw(synth.build_lap(n=200, clean=False), ratio=0.3)
    assert build_lap_stats(lap).stable is False         # clean is False -> not stable


def test_fp_rate_zero_on_neutral_lap():
    lap = _with_yaw(synth.build_lap(n=300, clean=True), ratio=1.9)
    stats = build_lap_stats(lap)
    assert sum(stats.symptom_corners.values()) == 0     # no false positives


def test_an_aid_working_is_not_a_mistake():
    """ABS/TC modulating with the slip low is correct technique, not a lock-up.

    This test used to assert the opposite — that the flag alone was enough —
    because the live detector worked that way too when it was written. The live
    rule was tightened on 2026-07-19 (8 false wheelspin + 3 false lock on one
    clean lap) and this half kept the old one, so for three weeks the same lap
    was silent live and full of lock-ups in the engineer's eyes. Measured
    2026-08-12 at Monza with ABS 6: 5-7 phantom lock segments per clean lap.
    """
    press = (27.0, 27.0, 27.5, 27.5)
    # Braking hard with ABS 6 modulating; slip stays where a working ABS keeps it.
    abs_ok = LapSample(0, 0.10, 200.0, 0.0, 0.9, 0.0, "4", 7000, 0.0, -1.0,
                       abs_active=0.6, slip_ratio=(-0.08, -0.07, 0.0, 0.0),
                       tyre_pressure=press)
    # Full throttle out of a slow corner with TC working; rear slip likewise low.
    tc_ok = LapSample(1000, 0.60, 120.0, 1.0, 0.0, 0.0, "3", 7000, 0.0, 0.5,
                      tc_active=0.6, slip_ratio=(0.0, 0.0, 0.06, 0.05),
                      tyre_pressure=press)
    lap = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
              samples=[abs_ok, tc_ok], clean=True)
    stats = build_lap_stats(lap)
    assert stats.lock_segments == 0
    assert stats.spin_segments == 0
    # The flag is not ignored either: with the aid modulating AND the slip
    # confirming, it counts — and the low-speed gate is skipped (120 km/h here is
    # above it anyway; the point is the pair, not the speed).
    real_lock = LapSample(0, 0.10, 200.0, 0.0, 0.9, 0.0, "4", 7000, 0.0, -1.0,
                          abs_active=0.6, slip_ratio=(-1.0, -1.0, 0.0, 0.0),
                          tyre_pressure=press)
    lap2 = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
               samples=[real_lock, tc_ok], clean=True)
    assert build_lap_stats(lap2).lock_segments == 1


def test_dopo_il_giro_e_dal_vivo_rispondono_uguale():
    """The post-lap count and the live detector cannot disagree on a frame.

    Not a re-statement of the rule: it feeds the *same* frames to both paths and
    demands the same answer. This is the guard that was missing — the two used to
    hold one rule each, and nothing in the suite compared them, so the drift went
    three weeks without a failing test.
    """
    from accoach.coaching.diagnosis import _lock_spin_segments
    from accoach.coaching.events import is_lockup
    from accoach.coaching.tuning import DEFAULT_TUNING

    press = (27.0, 27.0, 27.5, 27.5)
    frames = [
        # (abs_active, front slip) across the interesting corners of the rule.
        (0.6, -0.08),    # aid working, slip low      -> no
        (0.6, -1.00),    # aid working, wheel stopped -> yes
        (0.0, -0.30),    # no aid, real lock          -> yes
        (0.0, -0.08),    # no aid, normal braking     -> no
        (0.6, -0.15),    # exactly on the threshold   -> yes
    ]
    for i, (aid, slip) in enumerate(frames):
        s = LapSample(i * 100, 0.05 + i * 0.15, 200.0, 0.0, 0.9, 0.0, "4", 7000,
                      0.0, -1.0, abs_active=aid, slip_ratio=(slip, slip, 0.0, 0.0),
                      tyre_pressure=press)
        lap = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
                  samples=[s], clean=True)
        locks, _ = _lock_spin_segments(lap.samples, DEFAULT_TUNING.spin_ratio)
        assert locks == int(is_lockup(s)), f"frame {i}: aid={aid} slip={slip}"


def test_cold_frames_excluded_from_hot_pressures():
    # A cold slick reads low pressure; those frames must not drag the hot-pressure
    # mean down, or the engineer adds pressure that over-inflates at temperature.
    cold = LapSample(0, 0.10, 200.0, 0.0, 0.0, 0.0, "4", 7000, 0.0, 0.0,
                     tyre_core_temp=(40.0, 40.0, 40.0, 40.0),
                     tyre_pressure=(20.0, 20.0, 20.0, 20.0))
    hot = LapSample(1000, 0.50, 200.0, 1.0, 0.0, 0.0, "4", 7000, 0.0, 0.0,
                    tyre_core_temp=(90.0, 90.0, 90.0, 90.0),
                    tyre_pressure=(27.0, 27.0, 27.0, 27.0))
    lap = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
              samples=[cold, hot], clean=True)
    stats = build_lap_stats(lap)
    assert stats.pressures_hot is not None
    assert round(stats.pressures_hot["front"], 1) == 27.0   # 20psi cold frame dropped


def test_lock_spin_and_pressures_from_v6_channels():
    press = (27.0, 27.0, 27.5, 27.5)
    lock = LapSample(0, 0.10, 200.0, 0.0, 0.9, 0.0, "4", 7000, 0.0, -1.0,
                     slip_ratio=(-0.3, -0.3, 0.0, 0.0), tyre_pressure=press)
    spin = LapSample(1000, 0.60, 120.0, 1.0, 0.0, 0.0, "3", 7000, 0.0, 0.5,
                     slip_ratio=(0.0, 0.0, 0.25, 0.25), tyre_pressure=press)
    clean = LapSample(2000, 0.90, 250.0, 1.0, 0.0, 0.0, "5", 7000, 0.0, 0.0,
                      slip_ratio=(0.0, 0.0, 0.0, 0.0), tyre_pressure=press)
    lap = Lap("ferrari_488_gt3", "monza", SessionType.PRACTICE, 100000, True,
              samples=[lock, spin, clean], clean=True)
    stats = build_lap_stats(lap)
    assert stats.lock_segments >= 1
    assert stats.spin_segments >= 1
    assert stats.pressures_hot is not None
    assert round(stats.pressures_hot["front"], 1) == 27.0
    assert round(stats.pressures_hot["rear"], 1) == 27.5


# --- engine wiring: the engineer decision appears in the payload --------------

class _ScriptedReader:
    def __init__(self, frames):
        self._frames = list(frames)
        self._i = 0

    def read(self):
        if self._i < len(self._frames):
            f = self._frames[self._i]
            self._i += 1
            return f
        return TelemetrySnapshot.disconnected()

    def close(self):
        pass


def _full_lap_frames():
    frames = []
    for completed in (0, 1, 2):
        for i in range(30):
            frames.append(synth.snap(
                pos=i / 30, completed_laps=completed,
                current_lap_ms=i * 100, last_lap_ms=89000, speed_kmh=150.0,
            ))
    return frames


def test_debrief_includes_handling_cause():
    fast = synth.build_lap(n=300, clean=True)                       # reference
    slow = _with_yaw(synth.build_lap(slow_corner=0, amt=30, n=300, clean=True),
                     ratio=0.3)                                     # loses time + pushes
    debrief = build_lap_debrief(slow, Reference(fast), detect_corners(fast.samples))
    assert debrief.losses
    # The handling "why" appears both as a field and woven into the detail text.
    assert any("understeer" in loss.cause.lower() for loss in debrief.losses)
    assert any("understeer" in loss.detail.lower() for loss in debrief.losses)


def test_next_entry_credits_following_straight():
    c0 = Corner(0, 0.10, 0.20, 0.30)
    c1 = Corner(1, 0.60, 0.70, 0.80)
    assert _next_entry(c0, [c0, c1]) == 0.60    # window runs into the next corner
    assert _next_entry(c1, [c0, c1]) == 1.01    # last corner -> lap end


def test_onset_interpolates_brake_crossing():
    a = LapSample(0, 0.10, 200.0, 0.0, 0.0, 0.0, "4", 7000, 0.0, 0.0)   # brake 0
    b = LapSample(0, 0.20, 200.0, 0.0, 1.0, 0.0, "4", 7000, 0.0, 0.0)   # brake 1
    onset = _onset([a, b], lambda s: s.brake)
    expected = 0.10 + (_BRAKE_ON / 1.0) * 0.10                          # linear crossing
    assert abs(onset - expected) < 1e-6


def test_metres_between_uses_world_coords():
    s0 = LapSample(0, 0.0, 100.0, 1.0, 0.0, 0.0, "4", 7000, 0.0, 0.0,
                   car_x=0.0, car_z=0.0)
    s1 = LapSample(0, 1.0, 100.0, 1.0, 0.0, 0.0, "4", 7000, 0.0, 0.0,
                   car_x=30.0, car_z=40.0)
    lap = Lap("c", "t", SessionType.PRACTICE, 1000, True, samples=[s0, s1])
    assert abs(_metres_between(lap, 0.0, 1.0) - 50.0) < 1e-6            # 3-4-5 triangle


def test_import_reference_seeds_a_clean_reference(tmp_path):
    from accoach.diagnostics import run_import_reference
    from accoach.recording.storage import find_reference_lap, save_lap

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = save_lap(synth.build_lap(n=40), src_dir)          # clean=None by default
    laps = tmp_path / "laps"
    run_import_reference([str(src)], laps_dir=laps)
    ref = find_reference_lap("ferrari_488_gt3", "monza", laps)
    assert ref is not None and ref.clean is True            # imported = trusted clean
    assert ref.source == "pro"                              # …and a PRO benchmark


def test_mark_setup_applied_is_deferred_to_tick(tmp_path):
    # C2: mark_setup_applied (called from another thread) must NOT mutate the
    # engineer inline; it's drained on the tick thread instead.
    class _RecEngineer:
        def __init__(self):
            self.applied = 0

        def observe(self, stats):
            return None

        def mark_applied(self):
            self.applied += 1

    class _DeadReader:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_DeadReader(), laps_dir=tmp_path)
    rec = _RecEngineer()
    eng._engineer = rec
    eng.mark_setup_applied()              # from "another thread"
    assert rec.applied == 0               # not applied inline
    eng.tick(0.0)                         # drained on the tick thread
    assert rec.applied == 1
    eng.close()


def test_engine_surfaces_engineer_block(tmp_path):
    frames = _full_lap_frames()
    eng = CoachEngine(reader=_ScriptedReader(frames), laps_dir=tmp_path)
    state = None
    for _ in range(len(frames)):
        state = eng.tick(0.0)
    assert eng.saved_laps >= 1
    assert state.engineer is not None          # the bridge produced a decision
    assert "kind" in state.engineer and state.engineer["message"]
    eng.close()


# --- il perche' e il dove di un giro che non conta -------------------------

def test_a_cut_lap_carries_the_reason_and_the_place():
    """`stable` collassa due fatti diversi — il giro incompleto e il giro
    tagliato — e il pilota in macchina ha bisogno di sapere quale dei due. Il
    posto lo sa gia' il file: `lost_at` e' registrato dal 22/07 e non lo mostrava
    nessuna interfaccia."""
    lap = synth.build_lap(clean=False)
    lap.lost_at = 0.71                      # dentro la seconda curva sintetica
    st = build_lap_stats(lap, corner_names={0: "Prima", 1: "Variante Ascari"})
    assert st.stable is False
    assert st.unstable_why == "cut"
    assert st.lost_where == "Variante Ascari"


def test_the_place_is_only_the_corner_you_were_actually_in():
    """Un fuori pista sul rettilineo non ha un nome di curva, e il piu' vicino
    sarebbe una bugia detta con sicurezza: mandare il pilota a rivedere una
    curva in cui non e' successo niente e' peggio del silenzio."""
    lap = synth.build_lap(clean=False)
    lap.lost_at = 0.50                      # fra le due curve
    st = build_lap_stats(lap, corner_names={0: "Prima", 1: "Variante Ascari"})
    assert st.unstable_why == "cut" and st.lost_where == ""


def test_a_lap_the_game_never_completed_says_that_instead():
    st = build_lap_stats(synth.build_lap(valid=False))
    assert st.stable is False and st.unstable_why == "invalid"


def test_a_cut_lap_that_never_said_where_does_not_invent_a_place():
    """Due modi di non sapere dove, e portano allo stesso posto: il giro non lo
    ha registrato (i giri prima del 22/07), o chi chiama non ha i nomi."""
    lap = synth.build_lap(clean=False)
    assert build_lap_stats(lap, corner_names={1: "Variante Ascari"}).lost_where == ""
    lap.lost_at = 0.71
    assert build_lap_stats(lap).lost_where == ""


def test_a_lap_that_counts_carries_no_excuse():
    st = build_lap_stats(synth.build_lap(clean=True))
    assert st.stable is True and st.unstable_why == "" and st.lost_where == ""


def test_the_engine_hands_the_engineer_the_corner_names_it_already_has(tmp_path):
    """La catena intera, perche' e' fatta di tre pezzi e ognuno funzionava da
    solo: il file sa DOVE (`lost_at`), il motore sa COME SI CHIAMA (la mappa dei
    nomi, curati + imparati + scritti dal pilota), l'Ingegnere sa DIRLO. Finche'
    i tre non si parlano il pilota legge un contatore fermo e basta."""
    from accoach.engineer import RaceEngineer
    from accoach.engineer.profiles import GT3_PROFILE
    from accoach.track import detect_corners

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    lap = synth.build_lap(clean=False)
    lap.lost_at = 0.71
    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._engineer = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng._corners = detect_corners(lap.samples)
    eng._corner_names = {c.index: "Variante Ascari" for c in eng._corners
                         if c.entry_pos <= 0.71 <= c.exit_pos}
    assert eng._corner_names, "il fixture deve avere una curva attorno a 0.71"
    eng._observe_lap(lap)
    assert "Variante Ascari" in eng._engineer_decision.message
    eng.close()


def test_the_engine_writes_the_engineer_s_memory_after_every_lap(tmp_path):
    """La catena fino al disco: senza, il registro di cosa e' gia' stato provato
    vive quanto il processo, ed e' quello che il 14/08 e' andato perso."""
    from accoach.engineer import RaceEngineer
    from accoach.engineer.profiles import GT3_PROFILE
    from accoach.recording.catalog import LapCatalog
    from accoach.recording.storage import _catalog_path

    class _Dead:
        def read(self):
            return TelemetrySnapshot.disconnected()

        def close(self):
            pass

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path)
    eng._engineer = RaceEngineer(GT3_PROFILE, min_stable=3)
    eng._engineer_key = ("mclaren_720s_gt3_evo", "monza")
    eng._engineer.phase_idx = 2
    eng._observe_lap(synth.build_lap(clean=True))
    eng.close()

    with LapCatalog(_catalog_path(tmp_path)) as cat:
        got = cat.load_engineer_state("mclaren_720s_gt3_evo", "monza")
    assert got is not None and got["phase_idx"] == 2
