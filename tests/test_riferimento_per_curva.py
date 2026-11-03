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


# --- Task 4: dal vivo ogni curva si misura col suo gesto migliore -----------

def _live_setup(*, with_refs: bool):
    """Il principale e' lento nella curva 2; un altro giro l'ha presa meglio."""
    from accoach.coaching.analyzer import CoachAnalyzer
    from accoach.comparison import LapComparator
    main = synth.build_lap(slow_corner=1, amt=20)
    bests, corners = _bests(main)
    assert bests.offer(synth.build_lap()) is True
    an = CoachAnalyzer()
    an.set_corners(corners)
    if with_refs:
        an.set_corner_refs(bests)
    return an, LapComparator(Reference(main)), main, corners


def _drive(an, cmp, lap, *, until=None, start=0.0, on_frame=None):
    """Ricalca ``lap`` frame per frame; ritorna tutti i cue emessi."""
    out = []
    for smp in lap.samples:
        if smp.pos < start:
            continue
        if until is not None and smp.pos > until:
            break
        s = synth.snap(pos=smp.pos, current_lap_ms=smp.t_ms,
                       speed_kmh=smp.speed_kmh, throttle=smp.throttle,
                       brake=smp.brake, steer_angle=smp.steer_angle, gear=smp.gear)
        out += an.update(s, cmp.compare(s))
        if on_frame is not None:
            on_frame(smp.pos)
    return out


def test_live_corner_two_loses_against_its_best_gesture_corner_one_does_not():
    from accoach.coaching.cue import CueCategory
    an, cmp, main, corners = _live_setup(with_refs=True)
    _drive(an, cmp, main)
    # Il giro ricalca il principale: sul principale non perde nulla, ma nella
    # curva 2 un tuo giro ha fatto meglio, ed e' quello il metro.
    assert set(an._advice) == {1}
    adv = an._advice[1]
    assert adv.category is not CueCategory.GOOD
    assert adv.priority >= 120.0
    # Il riquadro dell'ultima curva confronta col gesto migliore anche lui.
    assert an.last_corner is not None and an.last_corner.index == 1
    assert an.last_corner.lost_ms >= 120.0


def test_live_without_corner_refs_the_same_lap_gives_no_advice():
    an, cmp, main, _ = _live_setup(with_refs=False)
    _drive(an, cmp, main)
    assert an._advice == {}
    assert an.last_corner is not None and abs(an.last_corner.lost_ms) < 120.0
    # set_corner_refs(None) e' lo stesso che non averlo mai chiamato.
    an2, cmp2, main2, _ = _live_setup(with_refs=True)
    an2.set_corner_refs(None)
    _drive(an2, cmp2, main2)
    assert an2._advice == {}


def test_live_corner_ref_phases_split_the_same_loss():
    """Regola del controllore: i tagli di fase leggono il delta del segmento."""
    from accoach.coaching import analyzer as analyzer_mod
    an, cmp, main, _ = _live_setup(with_refs=True)
    seen = []
    real = analyzer_mod.classify_corner

    def spy(st, index, pos):
        if index == 1:
            seen.append(st)
        return real(st, index, pos)

    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(analyzer_mod, "classify_corner", spy)
    try:
        _drive(an, cmp, main)
    finally:
        mp.undo()
    assert seen
    st = seen[0]
    assert st.lost_ms >= 120.0
    assert abs(sum(st.phase_ms.values()) - st.lost_ms) < 1e-6
    # Il riferimento della curva 2 e' piu' veloce in curva: anche i canali del
    # riferimento sono i suoi, non quelli del principale.
    assert st.min_speed_ref - st.min_speed_live >= 6.0


def test_live_new_corner_refs_keep_the_advice_on_its_corner():
    """Review Focus 5: un consiglio sulla curva 2 resta sulla curva 2."""
    an, cmp, main, corners = _live_setup(with_refs=True)
    _drive(an, cmp, main)
    adv = an._advice[1]
    card = an.last_corner
    fresh, _ = _bests(main)            # nuovi riferimenti, nessuna curva vinta
    an.set_corner_refs(fresh)
    assert an._advice == {1: adv}
    assert an.last_corner is card
    an.reset()                         # come fa il motore dopo un giro salvato
    # Il giro dopo, avvicinandosi alla curva 2, il consiglio esce li'.
    cues = _drive(an, cmp, main, until=corners[1].entry_pos)
    spoken = [c for c in cues if c.category is adv.category]
    assert len(spoken) == 1 and spoken[0].segment == 1


def test_live_a_zone_in_progress_keeps_the_ref_it_started_with():
    an, cmp, main, corners = _live_setup(with_refs=True)
    apex = corners[1].apex_pos
    swapped = []

    def swap(pos):
        if not swapped and pos >= apex:
            an.set_corner_refs(None)   # a meta' curva: la zona tiene il suo
            swapped.append(pos)

    _drive(an, cmp, main, on_frame=swap)
    assert swapped
    assert set(an._advice) == {1}


# --- Task 5: il motore li tiene aggiornati senza fermare il tick ------------
#
# Il bacino si carica su un thread del motore. Qui non si aspetta mai a tempo:
# si aspetta il Future della costruzione, poi un tick fa il passaggio di mano,
# come dal vivo.

class _Feed:
    """Il feed dal vivo, guidato a mano: l'ultimo frame e i giri appena salvati."""

    def __init__(self) -> None:
        from accoach.telemetry.snapshot import TelemetrySnapshot
        self.snap = TelemetrySnapshot.disconnected()
        self.saved: list = []

    def latest(self):
        return self.snap

    def drain_saved(self):
        out, self.saved = self.saved, []
        return out


def _own(laps_dir, lap, minute):
    """Un giro tuo, pulito, salvato come lo salva il feed."""
    lap.clean = True
    lap.recorded_utc = f"2026-11-02T10:{minute:02d}:00+00:00"
    save_lap(lap, laps_dir)
    return lap


def _engine(laps_dir):
    from accoach.engine import CoachEngine
    feed = _Feed()
    return CoachEngine(feed=feed, voice=None, laps_dir=laps_dir), feed


def _tick(eng, feed, saved=(), **kw):
    feed.snap = synth.snap(pos=0.05, is_acc=True, **kw)
    feed.saved = list(saved)
    eng.tick(0.0)


def _last_corner(eng):
    return max(eng._corners, key=lambda c: c.entry_pos)


def _gated_pool(monkeypatch, *, empty=False):
    """Il bacino che aspetta un via: la costruzione resta in volo finché il
    test non la libera. ``empty``: finita, non trova nessun giro."""
    import threading
    from accoach import engine as engine_mod
    started, gate = threading.Event(), threading.Event()
    real = engine_mod.reference_pool

    def pool(*a, **kw):
        started.set()
        assert gate.wait(5)
        return [] if empty else real(*a, **kw)

    monkeypatch.setattr(engine_mod, "reference_pool", pool)
    return started, gate


def _spy_set(eng):
    seen = []
    real_set = eng.analyzer.set_corner_refs

    def spy(bests):
        seen.append(bests)
        real_set(bests)

    eng.analyzer.set_corner_refs = spy
    return seen


def _settle(eng, feed):
    """Il primo tick fa partire la costruzione. Se non è già passata di mano
    nello stesso tick, si aspetta il suo Future e un altro tick la passa."""
    _tick(eng, feed)
    fut = eng._bests_future
    if fut is not None:
        fut.result(timeout=5)
        _tick(eng, feed)


def test_motore_nuovo_riferimento_costruisce_i_gesti_migliori(tmp_path,
                                                             monkeypatch):
    import threading
    from accoach import engine as engine_mod
    threads = []
    real = engine_mod.reference_pool

    def where(*a, **kw):
        threads.append(threading.current_thread())
        return real(*a, **kw)

    monkeypatch.setattr(engine_mod, "reference_pool", where)
    main = _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    other = _own(tmp_path, synth.build_lap(slow_corner=0, amt=30), 2)
    eng, feed = _engine(tmp_path)
    try:
        _settle(eng, feed)
        assert eng._reference.lap.lap_time_ms == main.lap_time_ms
        # Il bacino si è caricato una volta, e non sul thread del tick.
        assert len(threads) == 1
        assert threads[0] is not threading.current_thread()
        bests = eng.analyzer._bests
        assert bests is not None and bests.main is eng._reference
        # Costruito dalle stesse curve date all'analyzer.
        got = bests.at(_last_corner(eng).apex_pos)
        assert got is not None and got.reference.lap.lap_time_ms == other.lap_time_ms
        first = min(eng._corners, key=lambda c: c.entry_pos)
        assert bests.at(first.apex_pos) is None
        assert eng._bests_future is None          # passato di mano una volta sola
    finally:
        eng.close()


def test_motore_il_tick_non_aspetta_e_i_giri_salvati_intanto_contano(tmp_path,
                                                                     monkeypatch):
    started, gate = _gated_pool(monkeypatch, empty=True)
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    eng, feed = _engine(tmp_path)
    try:
        _tick(eng, feed)
        fut = eng._bests_future
        assert started.wait(5)
        _tick(eng, feed)
        assert not fut.done() and eng.analyzer._bests is None   # il tick va avanti
        other = _own(tmp_path, synth.build_lap(slow_corner=0, amt=30), 2)
        _tick(eng, feed, saved=[other])
        assert eng._bests_future is fut          # stesso riferimento: nessun'altra
        gate.set()
        fut.result(timeout=5)
        _tick(eng, feed)
        # Il bacino era vuoto: la curva l'ha presa il giro salvato nel frattempo.
        got = eng.analyzer._bests.at(_last_corner(eng).apex_pos)
        assert got is not None and got.reference.lap is other
    finally:
        gate.set()
        eng.close()


def test_motore_un_giro_salvato_piu_veloce_in_una_curva_vale_subito(tmp_path,
                                                                    monkeypatch):
    from accoach import engine as engine_mod
    calls = []
    real = engine_mod.reference_pool

    def counting(*a, **kw):
        calls.append(a)
        return real(*a, **kw)

    monkeypatch.setattr(engine_mod, "reference_pool", counting)
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    eng, feed = _engine(tmp_path)
    try:
        _settle(eng, feed)
        bests = eng.analyzer._bests
        c1 = _last_corner(eng)
        assert bests is not None and bests.at(c1.apex_pos) is None
        seen = _spy_set(eng)
        other = _own(tmp_path, synth.build_lap(slow_corner=0, amt=30), 2)
        _tick(eng, feed, saved=[other])
        assert seen == [bests]                   # subito, nello stesso tick
        assert eng.analyzer._bests.at(c1.apex_pos).reference.lap is other
        assert len(calls) == 1                   # il bacino non si ricarica
        assert eng._bests_future is None
        # Un giro che non batte niente non chiama nessuno.
        slow = _own(tmp_path, synth.build_lap(slow_corner=1, amt=30), 3)
        _tick(eng, feed, saved=[slow])
        assert seen == [bests]
    finally:
        eng.close()


def test_motore_riferimento_pro_niente_gesti_migliori(tmp_path):
    from accoach.recording.pro import import_pro
    laps = tmp_path / "laps"
    _own(laps, synth.build_lap(slow_corner=1, amt=10), 1)
    _own(laps, synth.build_lap(slow_corner=0, amt=30), 2)
    eng, feed = _engine(laps)
    try:
        _settle(eng, feed)
        assert eng.analyzer._bests is not None
        # Arriva un giro PRO più veloce: diventa il principale al prossimo giro.
        pro = synth.build_lap()
        synth.retime(pro, 95_000)
        pro.recorded_utc = "2026-01-01T09:00:00+00:00"
        out = tmp_path / "fuori"
        out.mkdir()
        import_pro(save_lap(pro, out), laps)
        slow = _own(laps, synth.build_lap(slow_corner=1, amt=30), 3)
        _tick(eng, feed, saved=[slow])
        assert eng._reference.lap.source == "pro"
        assert eng.analyzer._bests is None
        assert eng._bests_future is None         # nessuna costruzione per un PRO
    finally:
        eng.close()


def test_motore_auto_nuova_spegne_i_gesti_migliori(tmp_path):
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    _own(tmp_path, synth.build_lap(slow_corner=0, amt=30), 2)
    eng, feed = _engine(tmp_path)
    try:
        _settle(eng, feed)
        assert eng.analyzer._bests is not None
        _tick(eng, feed, car_model="porsche_992_gt3_r")
        assert eng._reference is None
        assert eng.analyzer._bests is None and eng._bests_future is None
    finally:
        eng.close()


def test_motore_una_costruzione_per_un_riferimento_vecchio_si_butta(tmp_path,
                                                                    monkeypatch):
    started, gate = _gated_pool(monkeypatch)
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    eng, feed = _engine(tmp_path)
    try:
        _tick(eng, feed)
        fut_a = eng._bests_future
        assert started.wait(5)                   # A sta caricando il bacino
        seen = _spy_set(eng)
        best = _own(tmp_path, synth.build_lap(), 2)     # nuovo miglior giro
        _tick(eng, feed, saved=[best])
        assert eng._reference.lap.lap_time_ms == best.lap_time_ms
        assert seen == [None]                    # spento subito, prima del bacino
        fut_b = eng._bests_future
        assert fut_b is not None and fut_b is not fut_a
        gate.set()
        built_a = fut_a.result(timeout=5)        # A finisce, ma è vecchio
        assert built_a.main.lap.lap_time_ms != best.lap_time_ms
        fut_b.result(timeout=5)
        _tick(eng, feed)
        assert built_a not in seen
        assert eng.analyzer._bests is not None
        assert eng.analyzer._bests.main is eng._reference
    finally:
        gate.set()
        eng.close()


def test_motore_passaggio_di_mano_controlla_il_riferimento(tmp_path,
                                                          monkeypatch):
    """La costruzione si lega al riferimento per cui è partita: se all'arrivo il
    riferimento è un altro, si butta anche se è l'unica in volo."""
    started, gate = _gated_pool(monkeypatch)
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    _own(tmp_path, synth.build_lap(slow_corner=0, amt=30), 2)
    eng, feed = _engine(tmp_path)
    try:
        _tick(eng, feed)
        fut = eng._bests_future
        assert started.wait(5)
        eng._bests_token = ("2020-01-01T00:00:00+00:00", 1)   # un altro giro
        gate.set()
        assert fut.result(timeout=5) is not None
        _tick(eng, feed)
        assert eng.analyzer._bests is None and eng._bests_future is None
    finally:
        gate.set()
        eng.close()


def test_motore_un_errore_nel_bacino_non_ferma_il_tick(tmp_path, monkeypatch):
    import logging
    from accoach import engine as engine_mod

    def broken(*a, **kw):
        raise RuntimeError("disco staccato")

    monkeypatch.setattr(engine_mod, "reference_pool", broken)
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    log = logging.getLogger("accoach.coach")
    log.addHandler(handler)
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    eng, feed = _engine(tmp_path)
    try:
        _tick(eng, feed)
        fut = eng._bests_future
        if fut is not None:                      # non ancora passata di mano
            assert isinstance(fut.exception(timeout=5), RuntimeError)
            _tick(eng, feed)                     # non solleva
        assert eng.analyzer._bests is None and eng._bests_future is None
        assert any(r.levelno == logging.WARNING for r in records)
    finally:
        log.removeHandler(handler)
        eng.close()


def test_motore_chiudere_non_aspetta_una_costruzione_in_volo(tmp_path, monkeypatch):
    started, gate = _gated_pool(monkeypatch)
    _own(tmp_path, synth.build_lap(slow_corner=1, amt=10), 1)
    eng, feed = _engine(tmp_path)
    try:
        _tick(eng, feed)
        assert started.wait(5)
        fut = eng._bests_future
        eng.close()                              # ritorna con il bacino in volo
        assert eng._pool is None
        assert not fut.done()                    # chiudere non l'ha aspettata
        gate.set()
        fut.result(timeout=5)                    # e finisce da sé
    finally:
        gate.set()


# --- Task 6: il report dice con cosa confronta ------------------------------

_IT_SENTENCE = "Confronto con la tua migliore in questa curva, dal giro in 1:48,912."
_EN_SENTENCE = "Compared with your best through this corner, from the 1:48.912 lap."


def _report_setup():
    """Il principale è lento nella curva 2; ``best`` l'ha presa meglio.

    Il tempo di ``best`` è solo l'etichetta del suo giro: è quello che la frase
    stampa, e scalare l'orologio per arrivarci cambierebbe proprio le finestre
    che si misurano."""
    main = synth.build_lap(slow_corner=1, amt=20)
    best = synth.build_lap()
    best.lap_time_ms = 108_912
    bests, corners = _bests(main)
    assert bests.offer(best) is True
    review = synth.build_lap(slow_corner=1, amt=30)
    return main, best, bests, corners, review


def _loss(deb, index):
    return next((x for x in deb.losses if x.index == index), None)


def test_report_corner_two_is_measured_against_its_best_gesture():
    from accoach.coaching.debrief import build_lap_debrief
    main, best, bests, corners, review = _report_setup()
    deb = build_lap_debrief(review, Reference(main), corners, "it",
                            corner_refs=bests)
    # La stessa curva misurata direttamente contro `best`: perdita, fasi,
    # statistiche e causa devono essere quelle, non quelle del principale.
    alone = build_lap_debrief(review, Reference(best), corners, "it")
    got, want = _loss(deb, 1), _loss(alone, 1)
    assert got is not None and want is not None
    assert got.lost_ms == want.lost_ms
    assert got.phases == want.phases
    assert got.category is want.category and got.message == want.message
    assert got.min_speed_live == want.min_speed_live
    assert got.min_speed_ref == want.min_speed_ref
    assert got.compared_ms == 108_912
    assert got.detail == f"{want.detail} {_IT_SENTENCE}"
    # Contro il principale la stessa curva perde meno: il metro è cambiato.
    plain = _loss(build_lap_debrief(review, Reference(main), corners, "it"), 1)
    assert plain is None or plain.lost_ms < got.lost_ms
    # La curva 1 resta sul principale, e non dice niente del confronto.
    for x in deb.losses:
        if x.index != 1:
            assert x.compared_ms == 0
            assert "Confronto con" not in x.detail


def test_report_sentence_in_english():
    from accoach.coaching.debrief import build_lap_debrief
    main, _best, bests, corners, review = _report_setup()
    deb = build_lap_debrief(review, Reference(main), corners, "en",
                            corner_refs=bests)
    assert _loss(deb, 1).detail.endswith(" " + _EN_SENTENCE)


def test_report_without_corner_refs_is_todays_debrief():
    from accoach.coaching.debrief import build_lap_debrief
    main, _best, _bests_, corners, review = _report_setup()
    ref = Reference(main)
    today = build_lap_debrief(review, ref, corners, "it")
    assert today.losses, "the review lap must lose somewhere"
    empty = CornerBests(ref, corners)            # nessun giro offerto
    for other in (build_lap_debrief(review, ref, corners, "it", corner_refs=None),
                  build_lap_debrief(review, ref, corners, "it",
                                    corner_refs=empty)):
        assert other == today                    # campo per campo
        assert all(x.compared_ms == 0 for x in other.losses)


def _debrief_calls(path):
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "accoach" / path
    tree = ast.parse(src.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", "")) == "build_lap_debrief"]


def test_focus_trends_and_pagella_keep_the_main_reference():
    """Decisione 6: il gesto migliore vale solo per il debrief del giro rivisto.

    Il focus tiene fermo il suo metro apposta (`engine.py`), e pagella e
    tendenze confrontano giri fra loro: un metro diverso per curva li
    renderebbe incomparabili."""
    for path in ("engine.py", "pagella.py"):
        calls = _debrief_calls(path)
        assert calls, f"{path} must still build debriefs"
        for call in calls:
            assert len(call.args) <= 4, f"{path}:{call.lineno}"
            assert all(k.arg != "corner_refs" for k in call.keywords), \
                f"{path}:{call.lineno} passes corner_refs"
    # Nell'API la passa una chiamata sola: quella del giro rivisto.
    with_refs = [c for c in _debrief_calls("api.py")
                 if any(k.arg == "corner_refs" for k in c.keywords)]
    assert len(with_refs) == 1


# --- Task 6: l'endpoint del report ------------------------------------------

def _report_archive(tmp_path):
    """Principale lento in curva 2, un giro più lento ma migliore lì, e il
    giro da rivedere. Tutti puliti, stessa auto, pista, mescola."""
    from accoach.recording.storage import save_lap
    main = synth.build_lap(slow_corner=1, amt=20, clean=True)
    best = synth.build_lap(slow_corner=0, amt=40, clean=True)
    review = synth.build_lap(slow_corner=1, amt=30, clean=True)
    assert best.lap_time_ms > main.lap_time_ms, "main must stay the reference"
    assert review.lap_time_ms > main.lap_time_ms
    paths = {}
    for name, lap, minute in (("main", main, 1), ("best", best, 2),
                              ("review", review, 3)):
        lap.recorded_utc = f"2026-11-01T10:{minute:02d}:00+00:00"
        paths[name] = str(save_lap(lap, tmp_path))
    return paths, {"main": main, "best": best, "review": review}


def _api_analysis(tmp_path, **kw):
    from fastapi.testclient import TestClient
    from accoach.api import create_api
    c = TestClient(create_api(tmp_path))
    r = c.get("/api/analysis", params={"car": "ferrari_488_gt3",
                                       "track": "monza", "lang": "it", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_report_endpoint_says_which_lap_it_compares_with(tmp_path):
    from accoach.telemetry.snapshot import format_lap_time
    paths, laps = _report_archive(tmp_path)
    data = _api_analysis(tmp_path, lap=paths["review"])
    assert data["reference"]["path"] == paths["main"]
    when = format_lap_time(laps["best"].lap_time_ms).replace(".", ",")
    sentence = f"Confronto con la tua migliore in questa curva, dal giro in {when}."
    said = [x for x in data["losses"] if sentence in x["detail"]]
    assert [x["index"] for x in said] == [1]


def test_report_endpoint_a_lap_picked_by_hand_is_compared_as_is(tmp_path):
    paths, _ = _report_archive(tmp_path)
    data = _api_analysis(tmp_path, lap=paths["review"], baseline=paths["best"])
    assert data["reference"]["path"] == paths["best"]
    assert all("Confronto con" not in x["detail"] for x in data["losses"])


def test_report_endpoint_a_broken_pool_is_no_corner_refs(tmp_path, monkeypatch):
    import accoach.api as api

    def boom(*a, **kw):
        raise RuntimeError("pool down")

    monkeypatch.setattr(api, "reference_pool_paths", boom)
    paths, _ = _report_archive(tmp_path)
    data = _api_analysis(tmp_path, lap=paths["review"])
    assert all("Confronto con" not in x["detail"] for x in data["losses"])


def test_report_never_compares_the_reviewed_lap_with_itself(tmp_path):
    """Il giro rivisto sta nel bacino, e in una curva può essere il migliore.
    Lì non si confronta con sé stesso: vale il principale."""
    from accoach.api import _corner_bests_for
    paths, laps = _report_archive(tmp_path)
    main = laps["main"]
    corners = detect_corners(main.samples)
    apex = corners[1].apex_pos
    no_cond = {"road_temp": None, "grip": None, "compound": None}

    # Rivedendo un altro giro, `best` prende la curva 2.
    held = _corner_bests_for(Reference(main), corners, laps["review"],
                             "ferrari_488_gt3", "monza", tmp_path, no_cond)
    assert held.at(apex) is not None
    assert held.at(apex).lap_time_ms == laps["best"].lap_time_ms
    # Rivedendo `best` stesso, la curva 2 resta sul principale.
    alone = _corner_bests_for(Reference(main), corners, laps["best"],
                              "ferrari_488_gt3", "monza", tmp_path, no_cond)
    assert alone.at(apex) is None


def test_report_corner_speeds_use_the_same_reference_as_the_corner(tmp_path):
    """La colonna «Rif.» delle velocità minime e la scheda della curva leggono
    lo stesso giro: una curva confrontata col gesto migliore non ha due
    velocità di riferimento sulla stessa pagina."""
    paths, laps = _report_archive(tmp_path)
    data = _api_analysis(tmp_path, lap=paths["review"])
    speeds = {x["index"]: x for x in data["corner_speeds"]}
    compared = [x for x in data["losses"] if "Confronto con" in x["detail"]]
    assert compared, "the archive must have a compared corner"
    for x in compared:
        assert speeds[x["index"]]["vmin_ref"] == x["vmin_ref"]
    # E la curva confrontata ha davvero un riferimento diverso dal principale.
    main_ref = Reference(laps["main"])
    corners = detect_corners(laps["main"].samples)
    c = next(c for c in corners if c.index == compared[0]["index"])
    inside = [s for s in laps["review"].samples
              if c.entry_pos <= s.pos <= c.exit_pos]
    main_vmin = round(min(main_ref.point_at(s.pos).speed_kmh for s in inside), 0)
    assert speeds[c.index]["vmin_ref"] != main_vmin


def test_report_second_call_loads_no_pool_lap_again(tmp_path, monkeypatch):
    """Il bacino si tiene in memoria per file e data: riaprire il report non
    ricarica i giri che ha già."""
    import accoach.api as api
    paths, _ = _report_archive(tmp_path)
    loaded = []
    real = api.load_lap

    def spy(path):
        loaded.append(str(path))
        return real(path)

    monkeypatch.setattr(api, "load_lap", spy)
    mine = {paths["review"], paths["main"]}     # review e riferimento, ogni volta
    _api_analysis(tmp_path, lap=paths["review"])
    first = [p for p in loaded if p not in mine]
    assert first, "the first call must load the pool"
    loaded.clear()
    data = _api_analysis(tmp_path, lap=paths["review"])
    assert [p for p in loaded if p not in mine] == []
    assert any("Confronto con" in x["detail"] for x in data["losses"])


def test_pool_cache_reloads_a_rewritten_file_and_stays_bounded(tmp_path,
                                                               monkeypatch):
    import os
    import accoach.api as api
    paths, _ = _report_archive(tmp_path)
    loads = []
    real = api.load_lap
    monkeypatch.setattr(api, "load_lap", lambda p: loads.append(p) or real(p))
    cache = api._PoolCache(size=2)
    a = cache.get(paths["main"])
    assert cache.get(paths["main"]) is a and len(loads) == 1
    st = os.stat(paths["main"])
    os.utime(paths["main"], ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert cache.get(paths["main"]) is not a and len(loads) == 2
    cache.get(paths["best"])
    cache.get(paths["review"])
    assert len(cache._laps) == 2
    assert cache.get(str(tmp_path / "missing.lap.json.gz")) is None


def test_report_survives_corner_refs_that_break_the_debrief(tmp_path,
                                                            monkeypatch, caplog):
    """Il gesto migliore è un bonus: se fa cadere il debrief, il report si
    rifà col solo principale invece di rispondere 422."""
    import logging
    import accoach.api as api

    class _Broken:
        def at(self, pos):
            raise RuntimeError("corner refs down")

    monkeypatch.setattr(api, "_corner_bests_for", lambda *a, **kw: _Broken())
    paths, _ = _report_archive(tmp_path)
    with caplog.at_level(logging.WARNING):
        data = _api_analysis(tmp_path, lap=paths["review"])
    assert data["losses"], "the report must still list its corners"
    assert all("Confronto con" not in x["detail"] for x in data["losses"])
    assert any("corner refs" in r.getMessage() for r in caplog.records
               if r.levelno >= logging.WARNING)
