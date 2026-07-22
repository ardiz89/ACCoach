"""Il conto alla rovescia della frenata si ritira dalle curve che hai domato.

Due piloti indipendenti su r/simracing hanno descritto lo stesso processo:
imparano un tracciato con traiettoria e cartelli di frenata, poi **li tolgono uno
alla volta**. E uno avvertiva che col coach AI «è facile perdere la prospettiva e
guidare i toni di frenata invece dell'auto». La stampella è fatta per essere
superata.

Riusa il set `mastered` del Focus coach invece di inventare una seconda idea di
«questa curva la sai», così si ritira esattamente dove il piano di lezione dice
che la debolezza è sparita.
"""
from accoach.comparison import Reference
from accoach.comparison.delta import LapComparator

import synth


def _comparator():
    return LapComparator(Reference(synth.build_lap()))


def _brake_onsets(comp):
    """Le posizioni delle staccate del riferimento (curve 0 e 1 del sintetico)."""
    return list(comp._brake_onsets)


def test_the_synthetic_reference_has_braking_points():
    assert _brake_onsets(_comparator()), "servono staccate da poter silenziare"


def test_a_muted_span_removes_that_braking_countdown():
    comp = _comparator()
    onset = _brake_onsets(comp)[0]
    # Prima: il conto alla rovescia trova la staccata avvicinandosi.
    before = comp._brake_in(onset - 0.03)
    comp.set_muted_spans([(onset - 0.02, onset + 0.02)])
    after = comp._brake_in(onset - 0.03)
    assert before is not None
    assert after != before, "la staccata silenziata non deve essere contata"


def test_an_unmuted_corner_still_counts_down():
    comp = _comparator()
    onsets = _brake_onsets(comp)
    if len(onsets) < 2:
        import pytest
        pytest.skip("serve una seconda curva")
    comp.set_muted_spans([(onsets[0] - 0.02, onsets[0] + 0.02)])
    # La seconda curva non è nello span: il suo conto alla rovescia resta.
    assert comp._brake_in(onsets[1] - 0.03) is not None


def test_clearing_the_spans_brings_the_markers_back():
    comp = _comparator()
    onset = _brake_onsets(comp)[0]
    comp.set_muted_spans([(onset - 0.02, onset + 0.02)])
    comp.set_muted_spans([])
    assert comp._brake_in(onset - 0.03) is not None


# --- l'engine collega il set `mastered` agli span --------------------------

def test_the_engine_mutes_mastered_corners(tmp_path):
    from dataclasses import replace

    from accoach.engine import CoachEngine
    from accoach.recording.storage import save_lap

    from test_engine_gate import _StubReader

    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)                          # costruisce riferimento + comparatore
    assert eng._comparator is not None and eng._focus is not None

    # Simula il Focus che ha domato la curva 0.
    eng._focus.mastered = {0}
    eng._update_wean()
    spans = eng._comparator._muted_spans
    assert spans, "la curva domata deve produrre uno span silenziato"
    c0 = next(c for c in eng._corners if c.index == 0)
    assert (c0.entry_pos, c0.exit_pos) in spans
    eng.close()


def test_wean_off_mutes_nothing(tmp_path):
    from accoach.engine import CoachEngine
    from accoach.recording.storage import save_lap

    from test_engine_gate import _StubReader

    save_lap(synth.build_lap(), tmp_path)
    eng = CoachEngine(reader=_StubReader([synth.snap(pos=0.5)]), voice=None,
                      laps_dir=tmp_path)
    eng.tick(0.0)
    eng._wean = False                      # il pilota vuole i cartelli per sempre
    eng._focus.mastered = {0}
    eng._update_wean()
    assert eng._comparator._muted_spans == []
    eng.close()
