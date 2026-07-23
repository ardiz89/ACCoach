"""Un tema sopra le curve, quando il pilota è troppo lontano dal passo.

Testuale da un coach su r/simracing: «al tuo ritmo è più questione di tecnica
generale che di analisi curva per curva». A chi è a due secondi dal passo,
diciotto righe di curve sono la lente sbagliata — il tempo è sparso ovunque e
classificarlo è rumore. Sopra una certa soglia di distacco il debrief guida col
tema dominante; sotto, il dettaglio per curva è già il livello giusto.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import (
    _HEADLINE_GAP_FRAC,
    CornerLoss,
    _headline,
)


def _loss(cat, ms):
    return CornerLoss(index=0, entry_pos=0.1, apex_pos=0.15, exit_pos=0.2,
                      lost_ms=ms, category=cat, message="")


def test_a_small_gap_gets_no_headline():
    """Vicino al passo, il dettaglio per curva È il livello giusto."""
    losses = [_loss(CueCategory.BRAKE_LATER, 300)]
    assert _headline(losses, gap_ms=500, ref_ms=90_000, lg="it") == ""


def test_a_big_gap_dominated_by_braking_names_braking():
    losses = [_loss(CueCategory.BRAKE_LATER, 1500),
              _loss(CueCategory.BRAKE_LATER, 1200),
              _loss(CueCategory.CARRY_SPEED, 200)]
    out = _headline(losses, gap_ms=3000, ref_ms=90_000, lg="it")
    assert out and "frenata" in out


def test_a_big_gap_dominated_by_exits_names_traction():
    losses = [_loss(CueCategory.MORE_THROTTLE, 1800),
              _loss(CueCategory.MORE_THROTTLE, 1400)]
    out = _headline(losses, gap_ms=3200, ref_ms=90_000, lg="it")
    assert "uscita" in out


def test_scattered_losses_fall_back_to_the_line():
    """Se il tempo è davvero sparso fra cause slegate, un tema solo sarebbe una
    bugia: si ripiega sulla traiettoria."""
    losses = [_loss(CueCategory.BRAKE_LATER, 1000),
              _loss(CueCategory.MORE_THROTTLE, 950),
              _loss(CueCategory.CARRY_SPEED, 900)]
    out = _headline(losses, gap_ms=2850, ref_ms=90_000, lg="it")
    assert "traiettoria" in out


def test_the_headline_states_how_far_off_the_pace():
    losses = [_loss(CueCategory.BRAKE_LATER, 3000)]
    out = _headline(losses, gap_ms=4500, ref_ms=90_000, lg="it")
    assert "5%" in out


def test_no_losses_no_headline():
    assert _headline([], gap_ms=5000, ref_ms=90_000, lg="it") == ""


def test_the_threshold_is_a_couple_of_seconds_on_a_normal_lap():
    """~3% è circa due secondi su un giro da 90: sotto, niente titolo."""
    assert 0.02 <= _HEADLINE_GAP_FRAC <= 0.05
    just_under = int(90_000 * _HEADLINE_GAP_FRAC) - 1
    losses = [_loss(CueCategory.BRAKE_LATER, just_under)]
    assert _headline(losses, gap_ms=just_under, ref_ms=90_000, lg="it") == ""


def test_it_reaches_the_debrief_object():
    from accoach.comparison import Reference
    from accoach.coaching.debrief import build_lap_debrief
    from accoach.track import detect_corners
    import synth

    ref = synth.build_lap()
    slow = synth.build_lap(slow_corner=0, amt=800)   # deliberately far off
    slow.lap_time_ms = ref.lap_time_ms + 4000
    d = build_lap_debrief(slow, Reference(ref), detect_corners(ref.samples), "it")
    assert isinstance(d.headline, str)      # sempre presente, magari vuoto
