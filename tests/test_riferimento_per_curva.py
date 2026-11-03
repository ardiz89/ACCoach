"""Il gesto migliore di ogni curva: un giro tuo più veloce in una curva sola.

Il riferimento principale è il tuo giro più veloce, ma raramente è il più veloce
in ogni curva. Questi test fissano quando un altro giro prende una curva
(Decisione 4 del piano), dove finisce la finestra di una curva (Decisione 3) e
quando la cosa è spenta (Decisione 5).

I giri vengono da ``synth.build_lap``: due curve, entry 0,1875 e 0,5875. Il
giro lento in una curva perde tempo in tutta la zona ``synth._ZONES``.
"""
from dataclasses import replace

from accoach.coaching.corner_refs import (
    MIN_GAIN_MS,
    POOL_SIZE,
    CornerBests,
    CornerRef,
    eligible,
    window_ms,
)
from accoach.comparison import Reference
from accoach.recording.catalog import LapCatalog
from accoach.recording.storage import _catalog_path, list_lap_files, save_lap
from accoach.track import detect_corners

import synth


def _bests(main_lap):
    corners = detect_corners(main_lap.samples)
    assert len(corners) == 2, "the synthetic lap must keep its two corners"
    return CornerBests(Reference(main_lap), corners), corners


def _faster_between(lap, lo: float, hi: float, ms: float):
    """``lap`` with ``ms`` taken off between ``lo`` and ``hi`` — and kept off
    after, as a quicker stretch would. Lets a test place a gain build_lap's
    per-sample step can't make small enough."""
    for s in lap.samples:
        if s.pos <= lo:
            continue
        cut = ms if s.pos >= hi else ms * (s.pos - lo) / (hi - lo)
        s.t_ms = int(round(s.t_ms - cut))
    lap.lap_time_ms = int(round(lap.lap_time_ms - ms))
    return lap


def test_the_constants_are_the_plans():
    assert MIN_GAIN_MS == 50.0
    assert POOL_SIZE == 20


def test_a_lap_faster_in_one_corner_becomes_that_corners_reference():
    main = synth.build_lap(slow_corner=1, amt=20)   # slow in the second corner
    other = synth.build_lap(slow_corner=0, amt=10)  # quick there, slow in the first
    bests, corners = _bests(main)
    assert bests.offer(other) is True

    ref = bests.at(corners[1].apex_pos)
    assert isinstance(ref, CornerRef)
    assert ref.reference.lap is other
    assert ref.gain_ms >= MIN_GAIN_MS
    assert ref.lap_time_ms == other.lap_time_ms
    main_ms = window_ms(Reference(main), corners[1].entry_pos, 1.0)
    assert abs(ref.window_ms + ref.gain_ms - main_ms) < 1e-6
    # The first corner is where `other` was slow: the main lap keeps it.
    assert bests.at(corners[0].apex_pos) is None


def test_a_gain_under_fifty_ms_is_noise():
    main = synth.build_lap()
    bests, corners = _bests(main)
    lo, hi = corners[1].entry_pos, corners[1].exit_pos
    assert bests.offer(_faster_between(synth.build_lap(), lo, hi, 30)) is False
    assert bests.at(corners[1].apex_pos) is None
    # Same construction, past the threshold: the threshold is what said no.
    assert bests.offer(_faster_between(synth.build_lap(), lo, hi, 80)) is True
    assert 79 <= bests.at(corners[1].apex_pos).gain_ms <= 81


def test_a_cut_lap_is_never_a_reference():
    main = synth.build_lap(slow_corner=1, amt=20)
    bests, corners = _bests(main)
    cut = synth.build_lap(clean=False)
    assert not eligible(cut, main)
    assert bests.offer(cut) is False
    assert bests.at(corners[1].apex_pos) is None
    # An incomplete lap is no better.
    assert not eligible(synth.build_lap(valid=False), main)
    # The same lap judged clean, or never judged, is fine.
    assert eligible(synth.build_lap(clean=True), main)
    assert eligible(synth.build_lap(clean=None), main)


def test_a_lap_with_a_hole_in_the_window_is_skipped():
    main = synth.build_lap(slow_corner=1, amt=20)
    bests, corners = _bests(main)
    c = corners[1]
    holed = synth.build_lap()
    holed.samples = [s for s in holed.samples
                     if not (c.entry_pos < s.pos < c.apex_pos)]
    assert window_ms(Reference(holed), c.entry_pos, 1.0) is None
    assert bests.offer(holed) is False
    assert bests.at(c.apex_pos) is None
    # The untouched lap is accepted: the hole is what kept it out.
    assert bests.offer(synth.build_lap()) is True


def test_window_ms_needs_both_ends_covered():
    lap = synth.build_lap()
    ref = Reference(lap)
    assert window_ms(ref, 0.2, 0.6) is not None
    late_start = synth.build_lap()
    late_start.samples = [s for s in late_start.samples if s.pos >= 0.21]
    assert window_ms(Reference(late_start), 0.2, 0.6) is None
    early_end = synth.build_lap()
    early_end.samples = [s for s in early_end.samples if s.pos <= 0.59]
    assert window_ms(Reference(early_end), 0.2, 0.6) is None
    # The window's time is the clock's, between its two ends.
    assert abs(window_ms(ref, 0.2, 0.6) - (ref.time_at(0.6) - ref.time_at(0.2))) < 1e-6


def test_another_compound_or_a_track_twelve_degrees_hotter_is_skipped():
    main = replace(synth.build_lap(slow_corner=1, amt=20, compound="dry"),
                   road_temp=30.0)
    bests, corners = _bests(main)

    wet = replace(synth.build_lap(compound="wet"), road_temp=30.0)
    hot = replace(synth.build_lap(compound="dry"), road_temp=42.0)
    assert not eligible(wet, main)
    assert not eligible(hot, main)
    assert bests.offer(wet) is False
    assert bests.offer(hot) is False
    assert bests.at(corners[1].apex_pos) is None

    # Inside the band, or with a condition never recorded on one side: allowed.
    assert eligible(replace(synth.build_lap(compound="dry"), road_temp=37.0), main)
    assert eligible(replace(synth.build_lap(compound=""), road_temp=0.0), main)
    assert bests.offer(replace(synth.build_lap(compound="dry"),
                               road_temp=35.0)) is True


def test_another_car_or_track_is_skipped():
    main = synth.build_lap(slow_corner=1, amt=20)
    assert not eligible(synth.build_lap(car="porsche_992_gt3_r"), main)
    assert not eligible(synth.build_lap(track="spa"), main)


def test_a_pro_lap_is_never_a_corner_reference():
    main = synth.build_lap(slow_corner=1, amt=20)
    bests, corners = _bests(main)
    pro = replace(synth.build_lap(), source="pro")
    assert not eligible(pro, main)
    assert bests.offer(pro) is False
    assert bests.at(corners[1].apex_pos) is None


def test_it_is_off_when_the_main_reference_is_a_pro_lap_or_there_are_no_corners():
    pro_main = replace(synth.build_lap(slow_corner=1, amt=20), source="pro")
    off, corners = _bests(pro_main)
    assert off.offer(synth.build_lap()) is False
    assert off.at(corners[1].apex_pos) is None

    none = CornerBests(Reference(synth.build_lap(slow_corner=1, amt=20)), [])
    assert none.offer(synth.build_lap()) is False
    assert none.at(0.71) is None


def test_the_main_lap_itself_is_never_a_candidate():
    main = synth.build_lap(slow_corner=1, amt=20)
    bests, _ = _bests(main)
    assert not eligible(main, main)
    assert bests.offer(main) is False


def test_offering_a_slower_lap_changes_nothing():
    main = synth.build_lap(slow_corner=1, amt=10)
    bests, corners = _bests(main)
    assert bests.offer(synth.build_lap(slow_corner=1, amt=30)) is False
    assert bests.at(corners[1].apex_pos) is None

    # Once a corner has a reference, it only goes to a lap that beats THAT.
    best = synth.build_lap()
    assert bests.offer(best) is True
    assert bests.offer(synth.build_lap(slow_corner=1, amt=5)) is False
    assert bests.at(corners[1].apex_pos).reference.lap is best


def test_a_quicker_lap_replaces_an_earlier_corner_reference():
    main = synth.build_lap(slow_corner=1, amt=30)
    bests, corners = _bests(main)
    assert bests.offer(synth.build_lap(slow_corner=1, amt=15)) is True
    first = bests.at(corners[1].apex_pos).gain_ms
    quicker = synth.build_lap()
    assert bests.offer(quicker) is True
    ref = bests.at(corners[1].apex_pos)
    assert ref.reference.lap is quicker
    assert ref.gain_ms > first


def test_positions_on_a_straight_belong_to_the_corner_before():
    main = synth.build_lap(slow_corner=0, amt=20)
    bests, corners = _bests(main)
    other = synth.build_lap()
    assert bests.offer(other) is True
    c0, c1 = corners

    straight = (c0.exit_pos + c1.entry_pos) / 2
    assert c0.exit_pos < straight < c1.entry_pos
    assert bests.at(straight).reference.lap is other
    assert bests.at(c0.entry_pos).reference.lap is other
    assert bests.at(c0.apex_pos).reference.lap is other
    # The next corner's entry starts the next window, which `other` didn't win.
    assert bests.at(c1.entry_pos) is None
    # Before the first entry no window is open: the last corner's window ends at
    # the line, as the debrief's does (`_next_entry` gives 1.01, no wrap).
    assert bests.at(c0.entry_pos / 2) is None


def test_the_last_corners_window_runs_to_the_line():
    main = synth.build_lap(slow_corner=1, amt=20)
    bests, corners = _bests(main)
    assert bests.offer(synth.build_lap()) is True
    ref = bests.at(0.999)
    assert ref is not None and ref is bests.at(corners[1].apex_pos)
    assert bests.at(1.0) is ref


# --- Decisione 7: il bacino dal catalogo ------------------------------------

def _pool_lap(tmp_path, ms, *, clean=True, compound="dry_compound",
              source="own", road_temp=0.0, grip=0.0):
    lap = synth.build_lap(clean=clean, compound=compound)
    synth.retime(lap, ms)
    lap.source = source
    lap.road_temp = road_temp
    lap.grip = grip
    lap.recorded_utc = f"2026-11-01T10:{(ms // 1000) % 60:02d}:{ms % 60:02d}+00:00"
    return save_lap(lap, tmp_path)


def _pool_dir(tmp_path):
    """25 giri: 15 buoni all'asciutto, 3 tagliati, 2 PRO, 5 sul bagnato."""
    for i in range(15):
        _pool_lap(tmp_path, 101_000 + i * 700, road_temp=20.0 if i < 4 else 0.0)
    for i in range(3):
        _pool_lap(tmp_path, 99_000 + i * 700, clean=False)        # i piu' veloci
    for i in range(2):
        _pool_lap(tmp_path, 97_000 + i * 700, source="pro")
    for i in range(5):
        _pool_lap(tmp_path, 98_000 + i * 700, compound="wet_compound",
                  road_temp=20.0)


def _pool_paths(tmp_path, **kw):
    db = _catalog_path(tmp_path)
    with LapCatalog(db) as cat:
        cat.sync(list_lap_files(tmp_path))
        return cat.reference_pool_paths("ferrari_488_gt3", "monza", **kw)


def _times(paths):
    import re
    out = []
    for p in paths:
        m = re.search(r"(\d+)m(\d+)s(\d{3})", str(p))
        out.append((int(m.group(1)) * 60 + int(m.group(2))) * 1000 + int(m.group(3)))
    return out


def test_bacino_solo_giri_tuoi_puliti_stessa_mescola_in_ordine(tmp_path):
    _pool_dir(tmp_path)
    paths = _pool_paths(tmp_path, compound="dry_compound")
    assert len(paths) == 15
    times = _times(paths)
    assert times == sorted(times)
    assert min(times) >= 101_000          # niente tagliati, PRO o bagnato


def test_bacino_senza_condizioni_prende_tutto_il_pulito(tmp_path):
    _pool_dir(tmp_path)
    paths = _pool_paths(tmp_path)
    assert len(paths) == 20               # 15 + 5 bagnato, limite 20
    assert len(_pool_paths(tmp_path, limit=3)) == 3


def test_bacino_si_rilassa_come_il_riferimento(tmp_path):
    _pool_dir(tmp_path)
    # Temperatura 20 + asciutto: solo i 4 giri con temperatura nota.
    assert len(_pool_paths(tmp_path, road_temp=20.0, compound="dry_compound")) == 4
    # Nessun giro a 50 gradi: cade la temperatura, resta la mescola.
    assert len(_pool_paths(tmp_path, road_temp=50.0, compound="dry_compound")) == 15
    # Mescola mai vista: cade la mescola per ultima, resta la temperatura.
    got = _pool_paths(tmp_path, road_temp=20.0, compound="slick_x")
    assert len(got) == 9                  # 4 asciutti + 5 bagnati a 20 gradi
    # Il grip cade per primo: nessun giro ne ha, la mescola regge.
    assert len(_pool_paths(tmp_path, grip=0.9, compound="dry_compound")) == 15


def test_bacino_senza_giri_e_vuoto(tmp_path):
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        assert cat.reference_pool_paths("ferrari_488_gt3", "monza") == []


def test_reference_pool_carica_i_giri_e_salta_quelli_rotti(tmp_path):
    from accoach.recording.storage import reference_pool
    _pool_dir(tmp_path)
    ok = reference_pool("ferrari_488_gt3", "monza", tmp_path,
                        compound="dry_compound")
    assert len(ok) == 15
    assert all(lap.lap_time_ms > 0 and lap.source == "own" for lap in ok)
    victim = _pool_paths(tmp_path, compound="dry_compound")[0]
    open(victim, "wb").write(b"non e' un giro")
    again = reference_pool("ferrari_488_gt3", "monza", tmp_path,
                           compound="dry_compound")
    assert len(again) == 14


def test_reference_pool_catalogo_inutilizzabile_da_vuoto(tmp_path):
    from accoach.recording.storage import reference_pool
    _pool_dir(tmp_path)
    _catalog_path(tmp_path).write_bytes(b"questo non e' sqlite" * 50)
    assert reference_pool("ferrari_488_gt3", "monza", tmp_path) == []
